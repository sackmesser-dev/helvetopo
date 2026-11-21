#!/usr/bin/env python3
"""POIs für das Routen-Overlay (FID 7702) als OSM-XML.

Nutzt die POI-Erzeugung der Basiskarte (src/vector/pois.py) unverändert, damit Tags und Namen
gleich sind wie in der Basis. Welche POIs das Overlay zeigt, legt der Stil fest
(src/style/routes/points). Haltestellen und Seilbahnstationen erzeugt convert_routes.py selbst,
deshalb fallen sie hier weg.

Aufruf aus dem Repo-Ordner (Paketimport, braucht geopandas aus dem venv):
    .venv/bin/python -E -s -m src.routes.pois_overlay --bbox 9.00,47.20,9.50,47.50 --out pois.osm
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import quoteattr

from ..vector.common import Area
from ..vector.pois import add_pois

# POI-Herkünfte (swisstopo:poi), die convert_routes.py selbst liefert
SKIP_KINDS = {"haltestelle", "seilbahnstation"}
# Erste Knoten-ID, damit die IDs nicht mit routes.osm kollidieren (osmium merge)
FIRST_ID = 1_000_000_000


class PointCollector:
    """Minimaler Ersatz für den OSM-Builder der Basis: sammelt nur Punkte."""

    def __init__(self) -> None:
        self.points: list[tuple[float, float, dict]] = []

    def add_point(self, lon: float, lat: float, tags: dict) -> None:
        if tags.get("swisstopo:poi") in SKIP_KINDS:
            return
        self.points.append((lon, lat, {k: v for k, v in tags.items() if v is not None}))


def write_osm(points, path: Path, bbox) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write("<?xml version='1.0' encoding='UTF-8'?>\n")
        f.write("<osm version='0.6' generator='Helvetopo pois_overlay.py'>\n")
        f.write(f"  <bounds minlon='{bbox[0]}' minlat='{bbox[1]}' maxlon='{bbox[2]}' maxlat='{bbox[3]}'/>\n")
        for i, (lon, lat, tags) in enumerate(points, start=FIRST_ID):
            f.write(f"  <node id='{i}' version='1' lat='{lat:.7f}' lon='{lon:.7f}'>\n")
            for k, v in sorted(tags.items()):
                f.write(f"    <tag k={quoteattr(k)} v={quoteattr(str(v))}/>\n")
            f.write("  </node>\n")
        f.write("</osm>\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", default="9.00,47.20,9.50,47.50", help="minlon,minlat,maxlon,maxlat (WGS84)")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    bbox = tuple(float(v) for v in args.bbox.split(","))
    b = PointCollector()
    add_pois(b, Area(*bbox))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_osm(b.points, args.out, bbox)
    kinds = Counter(t.get("swisstopo:poi") for _, _, t in b.points)
    print(f"{len(b.points)} POIs -> {args.out}: {dict(kinds)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
