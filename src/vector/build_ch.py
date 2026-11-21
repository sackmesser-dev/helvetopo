"""Landesbuild: swissTLM3D → OSM-PBF für die ganze Schweiz, kachelweise und fortsetzbar.

Der Konverter hält alle Knoten im Speicher (ca. 270 Byte je Knoten); die ganze Schweiz in einem
Lauf bräuchte 55–75 GB. Deshalb: Raster aus Kacheln, jede Kachel als eigener Prozess mit
global eindeutigen IDs (OsmBuilder(tile=k): Knoten-ID aus der Koordinate, Wege/Relationen/POIs je
Kachel in eigenem Bereich), danach `osmium merge` und `osmium renumber` (dichte IDs für splitter). Gemeinsame Knoten an den Kachelgrenzen haben
dieselbe ID, das Routing bleibt über die Grenzen verbunden.

Fertige Kacheln werden übersprungen (Abbruch und Neustart möglich).

    .venv/bin/python -m src.vector.build_ch --out work/vector/ch --jobs 3 \
        --routes-csv <routes-worktree>/work/routes-ch/tlm_routes.csv
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import shapely

from .common import BOUNDARIES_GPKG, read_layer, to_wgs84

log = logging.getLogger("vector")

CH_BBOX = (5.95, 45.81, 10.50, 47.81)


def tiles(bbox, dx, dy, land):
    w, s, e, n = bbox
    out = []
    k = 0
    y = s
    while y < n - 1e-9:
        x = w
        while x < e - 1e-9:
            box = (round(x, 6), round(y, 6), round(min(x + dx, e), 6), round(min(y + dy, n), 6))
            k += 1
            if land is None or land.intersects(shapely.box(*box)):
                out.append((k, box))
            x += dx
        y += dy
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="work/vector/ch")
    p.add_argument("--bbox", help="west,süd,ost,nord (Standard: Schweiz)")
    p.add_argument("--dx", type=float, default=0.4)
    p.add_argument("--dy", type=float, default=0.3)
    p.add_argument("--jobs", type=int, default=3)
    p.add_argument("--routes-csv")
    p.add_argument("--name", default="ch.osm.pbf")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    bbox = tuple(float(v) for v in a.bbox.split(",")) if a.bbox else CH_BBOX
    out = Path(a.out).resolve()
    (out / "tiles").mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(parents=True, exist_ok=True)

    # nur Kacheln, die Schweizer Gebiet (inkl. Liechtenstein) schneiden
    land = read_layer(BOUNDARIES_GPKG, "tlm_landesgebiet", None)
    land_wgs = shapely.union_all(to_wgs84(shapely.buffer(land.geometry.values, 1000)))
    todo = tiles(bbox, a.dx, a.dy, land_wgs)
    log.info("%d Kacheln (%.2f° × %.2f°)", len(todo), a.dx, a.dy)

    t0 = time.time()
    # Flussordnung einmal landesweit rechnen, bevor die Kachelprozesse sie parallel lesen
    from . import rivers
    rivers.load()

    def run(item):
        k, box = item
        dst = out / "tiles" / f"t{k:03d}.osm.pbf"
        if dst.exists():
            return k, "vorhanden", 0.0
        cmd = [sys.executable, "-m", "src.vector.convert", "--tile", str(k),
               "--bbox", ",".join(str(v) for v in box), "--out", str(dst)]
        if a.routes_csv:
            cmd += ["--routes-csv", a.routes_csv]
        s = time.time()
        with open(out / "logs" / f"t{k:03d}.log", "w") as lf:
            r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT)
        if r.returncode != 0:
            return k, f"FEHLER {r.returncode}", time.time() - s
        return k, "ok", time.time() - s

    failed = []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for k, status, dt in ex.map(run, todo):
            log.info("Kachel %03d: %s (%.0f s)", k, status, dt)
            if status.startswith("FEHLER"):
                failed.append(k)
    if failed:
        log.error("fehlgeschlagene Kacheln: %s (Logs in %s)", failed, out / "logs")
        sys.exit(1)
    log.info("Kacheln fertig in %.0f s", time.time() - t0)

    parts = [str(out / "tiles" / f"t{k:03d}.osm.pbf") for k, _ in todo]
    dst = out / a.name
    s = time.time()
    merged = out / ("merged-" + a.name)
    subprocess.run(["osmium", "merge", "--overwrite", "-o", str(merged), *parts], check=True)
    # Abstand zur nächsten Stadt an Fluss- und Autobahnwegen (braucht die Städte aller Kacheln)
    from . import stadtabstand
    log.info("stadtabstand: %s", dict(stadtabstand.process(merged, merged)))
    # Dichte IDs ab 1: splitter läuft mit den grossen Kachel-IDs (bis 2^58) aus dem Speicher
    subprocess.run(["osmium", "renumber", "--overwrite", "-o", str(dst), str(merged)], check=True)
    merged.unlink()
    # Quellenangabe (alle Kacheln gleich)
    src = Path(parts[0] + ".sources")
    if src.exists():
        Path(str(dst) + ".sources").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    log.info("merge %.0f s → %s (%.0f MB), gesamt %.0f s", time.time() - s, dst,
             dst.stat().st_size / 1e6, time.time() - t0)


if __name__ == "__main__":
    main()
