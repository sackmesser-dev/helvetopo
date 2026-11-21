"""swissTLM3D (+ swissNAMES3D, swissBOUNDARIES3D, Adressen) → OSM-PBF.

Aufruf (aus dem Repo-Wurzelverzeichnis):

    .venv/bin/python -m src.vector.convert --out work/vector/testgebiet.osm.pbf

Standardgebiet ist das Testgebiet 9.00–9.50° O / 47.20–47.50° N.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import numpy as np

from . import addresses, admin, anno, extras, features, names, pois, population, roads
from .common import TEST_AREA, Area
from .osmbuild import OsmBuilder

log = logging.getLogger("vector")

ALL_PARTS = ["roads", "rail", "water", "landcover", "trees", "areale", "buildings", "settlements", "structures",
             "names", "pois", "addresses", "boundaries"]


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default="work/vector/testgebiet.osm.pbf")
    p.add_argument("--bbox", help="west,süd,ost,nord in WGS84 (Standard: Testgebiet)")
    p.add_argument("--only", help="Kommagetrennte Teilmenge von: " + ",".join(ALL_PARTS))
    p.add_argument("--routes-csv", help="tlm_routes.csv aus routes-overlay (match_tlm.py): Velo-/MTB-/"
                   "Wanderland-Zugehörigkeit als Kanten-Tags (Quellenangabe ASTRA/SchweizMobil nötig)")
    p.add_argument("--tile", type=int, help="Kachelnummer für global eindeutige IDs (Landesbuild, build_ch.py)")
    p.add_argument("--ohne-gebaeude-raster", action="store_true",
                   help="Gebäude nicht auf das Garmin-Raster ausrichten (Vergleich, gebaeude_raster.py)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")

    area = TEST_AREA
    if a.bbox:
        w, s, e, n = (float(v) for v in a.bbox.split(","))
        area = Area(w, s, e, n)
    parts = a.only.split(",") if a.only else ALL_PARTS

    t0 = time.time()
    b = OsmBuilder(tile=a.tile)
    lookup = admin.AdminLookup(area)

    # Reihenfolge: Strassen zuerst, damit Barrieren auf die Strassenknoten fallen
    road_index = None
    if "roads" in parts:
        road_index = roads.add_roads(b, area, lookup, a.routes_csv)
    if "rail" in parts:
        features.add_rail(b, area)
    lc = None
    if "landcover" in parts or "water" in parts or "trees" in parts:
        lc = features.load_landcover(area)
    if "water" in parts:
        river_polys = lc.geometry.values[lc["objektart"].values == "Fliessgewaesser"]
        features.add_water_lines(b, area, river_polys)
    if "landcover" in parts:
        lakes = names.lake_names(lc, area) if "names" in parts else {}
        features.add_landcover(b, area, lc, lakes)
    settl = None
    if "trees" in parts or "settlements" in parts:
        settl = features.settlement_polygons(area)
    if "trees" in parts:
        features.add_trees(b, area, lc, settl)
    if "areale" in parts:
        features.add_areale(b, area)
    if "buildings" in parts:
        features.add_buildings(b, area)
    if "settlements" in parts:
        features.add_settlements(b, area, settl)
    if "structures" in parts:
        features.add_structures(b, area)
    if "names" in parts:
        names.add_name_points(b, area, lookup)
        names.add_area_labels(b, area)
        anno.move_names_to_anno(b, area)
        population.add_population(b, area)
    if "pois" in parts:
        pois.add_pois(b, area)
        extras.add_square_points(b, area, lookup, road_index)
        anno.add_anno(b, area)
    if "names" in parts:
        names.drop_names_at_peaks(b)
    if "addresses" in parts:
        addresses.add_addresses(b, area, lookup, road_index)
    if "boundaries" in parts:
        admin.add_boundaries(b, area)
    admin.add_is_in_to_points(b, lookup)

    if "buildings" in parts and not a.ohne_gebaeude_raster:
        # Gebäude auf das Garmin-Raster (Auflösung 24) ausrichten, damit die Ecken rechtwinklig bleiben
        from . import gebaeude_raster
        log.info("Gebäude ausgerichtet: %s", gebaeude_raster.align_buildings(b))

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    b.write(out)
    if a.tile is None and ("roads" in parts or "water" in parts) and "names" in parts:
        # Landesbuild: build_ch.py rechnet das nach dem Merge (Städte jenseits der Kachelgrenze)
        from . import stadtabstand
        log.info("stadtabstand: %s", dict(stadtabstand.process(out, out)))
    # Quellen für die Copyright-Zeilen (build_img.sh)
    sources = ["©swisstopo"]
    if a.routes_csv and "roads" in parts:
        from .routes_attr import ASTRA_SOURCE
        sources.append(ASTRA_SOURCE)
    Path(str(out) + ".sources").write_text("\n".join(sources) + "\n", encoding="utf-8")
    log.info("fertig in %.0f s, Statistik: %s", time.time() - t0, dict(b.stats))


if __name__ == "__main__":
    main()
