#!/usr/bin/env python3
"""Ordnet SchweizMobil-Routen den Kanten von swissTLM3D TLM_STRASSE zu (Toleranz-Matching).

Die ASTRA-Routengeometrien folgen swissTLM3D, haben im GPKG aber keine TLM_ID und liegen
0,4-0,6 m neben den TLM-Stützpunkten. Eine TLM-Kante gilt als Teil einer Route, wenn
mindestens MIN_SHARE ihrer Länge (Stichproben alle STEP m) näher als TOL m an der
Routengeometrie liegt.

Ausgabe: CSV mit einer Zeile je TLM-Kante, die auf mindestens einer Route liegt:
    uuid,objektart,wanderwege,belagsart,wanderland,veloland,mountainbikeland,skatingland
Routenfelder: "netz:nummer" mit ";" getrennt, z. B. "national:4;regional:24".
Für vector-convert gedacht (Tags siehe docs/vektor/routen.md, Abschnitt Velo-Präferenz).

Aufruf:
    python3 -I src/routes/match_tlm.py --downloads $HELVETOPO_DATA \
        --bbox 9.00,47.20,9.50,47.50 --out work/routes/tlm_routes.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import convert_routes as cr  # noqa: E402

TLM = "swisstlm3d/SWISSTLM3D_2026_LV95_LN02.gpkg"
LANDS = ["wanderland", "veloland", "mountainbikeland", "skatingland"]
TOL = 3.0
STEP = 5.0
MIN_SHARE = 0.8
CELL = 25.0


def seg_dist2(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return (px - ax) ** 2 + (py - ay) ** 2
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
    qx, qy = ax + t * dx, ay + t * dy
    return (px - qx) ** 2 + (py - qy) ** 2


class SegIndex:
    def __init__(self):
        self.grid: dict[tuple[int, int], list] = {}

    def add(self, a, b, label):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for gx in range(int((x0 - TOL) // CELL), int((x1 + TOL) // CELL) + 1):
            for gy in range(int((y0 - TOL) // CELL), int((y1 + TOL) // CELL) + 1):
                self.grid.setdefault((gx, gy), []).append((a[0], a[1], b[0], b[1], label))

    def near(self, x, y):
        labels = set()
        for s in self.grid.get((int(x // CELL), int(y // CELL)), ()):
            if s[4] not in labels and seg_dist2(x, y, *s[:4]) <= TOL * TOL:
                labels.add(s[4])
        return labels


def samples(part):
    for (ax, ay), (bx, by) in zip(part, part[1:]):
        L = math.hypot(bx - ax, by - ay)
        n = max(1, int(L // STEP))
        for i in range(n):
            t = (i + 0.5) / n
            yield ax + t * (bx - ax), ay + t * (by - ay), L / n


def load_routes(downloads: Path, box):
    idx = SegIndex()
    for key, rel, *_ in cr.ROUTE_SOURCES:
        if key not in LANDS:
            continue
        con = sqlite3.connect(f"file:{downloads / rel}?mode=ro", uri=True)
        for fid in cr.rtree_ids(con, "Route", "geom", box):
            geom, nr, typ = con.execute("SELECT geom, NrR, Typ_TR FROM Route WHERE fid=?", (fid,)).fetchone()
            label = (key, typ or "unknown", nr or "")
            for part in cr.parse_gpkg_geom(geom):
                for a, b in zip(part, part[1:]):
                    if box[0] <= max(a[0], b[0]) and min(a[0], b[0]) <= box[2] and \
                            box[1] <= max(a[1], b[1]) and min(a[1], b[1]) <= box[3]:
                        idx.add(a, b, label)
        con.close()
    return idx


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--downloads", required=True, type=Path)
    ap.add_argument("--bbox", default="9.00,47.20,9.50,47.50")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    bbox = tuple(float(v) for v in args.bbox.split(","))
    box = cr.lv95_box(bbox, buffer_m=0.0)

    t0 = time.time()
    idx = load_routes(args.downloads, box)
    print(f"Routensegmente indexiert ({len(idx.grid)} Zellen) in {time.time() - t0:.1f} s", file=sys.stderr)

    con = sqlite3.connect(f"file:{args.downloads / TLM}?mode=ro", uri=True)
    ids = cr.rtree_ids(con, "tlm_strassen_strasse", "geom", box)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    stats: dict[str, list[float]] = {}
    n_out = 0
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["uuid", "objektart", "wanderwege", "belagsart", *LANDS])
        q = ("SELECT geom, uuid, objektart, wanderwege, belagsart FROM tlm_strassen_strasse WHERE id=?")
        for fid in ids:
            geom, uuid, objektart, ww, belag = con.execute(q, (fid,)).fetchone()
            total = 0.0
            hit: dict[tuple, float] = {}
            for part in cr.parse_gpkg_geom(geom):
                for x, y, l in samples(part):
                    total += l
                    for lab in idx.near(x, y):
                        hit[lab] = hit.get(lab, 0.0) + l
            if total == 0:
                continue
            members = {lab for lab, l in hit.items() if l / total >= MIN_SHARE}
            if not members:
                continue
            row = [(uuid or "").strip("{}"), objektart, ww or "", belag or ""]
            for land in LANDS:
                vals = sorted({f"{typ}:{nr}" for (k, typ, nr) in members if k == land})
                row.append(";".join(vals))
                if vals:
                    s = stats.setdefault(f"{land} | {objektart} | {ww or '-'}", [0, 0.0])
                    s[0] += 1
                    s[1] += total
            w.writerow(row)
            n_out += 1
    print(f"{n_out} TLM-Kanten auf Routen -> {args.out} ({time.time() - t0:.1f} s)", file=sys.stderr)
    for k in sorted(stats):
        print(f"{k:60s} {int(stats[k][0]):6d} Kanten {stats[k][1] / 1000:8.1f} km", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
