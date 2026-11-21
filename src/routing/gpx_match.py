"""Garmin-Route (GPX aus BaseCamp) kantengenau auf die Basis-PBF abbilden und auswerten.

Liest die Routengeometrie aus gpxx:rpt (RoutePointExtension) bzw. rtept/trkpt, tastet sie alle
5 m ab und ordnet jeden Abschnitt der nächsten routbaren Kante (≤ 15 m) zu. Ausgabe: km gesamt,
auf Veloland/MTB-Land, Hauptstrasse, Maut-Flag (Variante wählbar), je highway und Strassenname.
GPX aus der VM sind nicht vertrauenswürdig: Dateien mit DOCTYPE/ENTITY werden abgelehnt.

    python -I src/routing/gpx_match.py <basis.osm.pbf> <route.gpx> [...] [--variant stark]
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_routes as cr  # noqa: E402

CELL = 0.0005  # Raster ca. 40–55 m


def read_gpx(path: Path) -> list[tuple[float, float]]:
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise SystemExit(f"{path}: DOCTYPE/ENTITY nicht erlaubt")
    root = ET.fromstring(raw)
    pts = []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("rpt", "rtept", "trkpt") and "lat" in el.attrib:
            p = (float(el.attrib["lat"]), float(el.attrib["lon"]))
            if not pts or p != pts[-1]:
                pts.append(p)
    return pts


def seg_dist(p, a, b):
    k = math.cos(math.radians(p[0]))
    ax, ay, bx, by, px, py = a[1] * k, a[0], b[1] * k, b[0], p[1] * k, p[0]
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy)) * 111200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pbf")
    ap.add_argument("gpx", nargs="+")
    ap.add_argument("--variant", default="basis")
    a = ap.parse_args()
    ld = cr.Loader(["off", a.variant])
    ld.apply_file(a.pbf, locations=True)
    grid = defaultdict(list)
    for i, (u, v, L, at) in enumerate(ld.edges):
        if not at[a.variant]["bike"] and not at[a.variant]["car"]:
            continue
        p, q = ld.loc[u], ld.loc[v]
        for gy in range(int(min(p[0], q[0]) / CELL) - 1, int(max(p[0], q[0]) / CELL) + 2):
            for gx in range(int(min(p[1], q[1]) / CELL) - 1, int(max(p[1], q[1]) / CELL) + 2):
                grid[(gy, gx)].append(i)
    for g in a.gpx:
        pts = read_gpx(Path(g))
        st, hw, names = Counter(), Counter(), Counter()
        for p, q in zip(pts, pts[1:]):
            d = cr._dist(p[0], p[1], q[0], q[1])
            n = max(1, int(d / 5))
            for k in range(n):
                f = (k + 0.5) / n
                m = (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)
                L = d / n
                best, bd = None, 15.0
                for i in grid.get((int(m[0] / CELL), int(m[1] / CELL)), ()):
                    u, v, _, at = ld.edges[i]
                    dd = seg_dist(m, ld.loc[u], ld.loc[v])
                    if dd < bd:
                        best, bd = at[a.variant], dd
                st["km"] += L
                if best is None:
                    st["ohne_kante"] += L
                    continue
                st["velo_route"] += L * best["velo"]
                st["hauptstrasse"] += L * (best["hw"] in cr.MAIN)
                st["maut_flag"] += L * best["toll"]
                st["naturbelag"] += L * best["unpaved"]
                hw[best["hw"] + ("/V" if best["velo"] else "") + ("/M" if best["toll"] else "")] += L
                names[best["name"] or f"({best['hw']})"] += L
        print(f"\n## {Path(g).name} ({len(pts)} Punkte, Variante {a.variant})")
        print("  " + "  ".join(f"{k}={v / 1000:.2f}" for k, v in st.items()))
        print("  highway: " + "; ".join(f"{k} {v / 1000:.1f}" for k, v in hw.most_common(12)))
        print("  Namen: " + "; ".join(f"{k} {v / 1000:.1f}" for k, v in names.most_common(12)))


if __name__ == "__main__":
    main()
