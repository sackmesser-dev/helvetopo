"""Ergänzung nach BaseCamp-Test 10: Namenpunkte für Plätze, Tore und benannte Kreisel
(z. B. „Marktplatz“, „Spisertor“), siehe docs/daten/tag-schema.md „Platz-Namenpunkte“.
"""

from __future__ import annotations

import csv
import logging

import numpy as np
import shapely

from .common import STREET_CSV, Area, clip_wgs84

log = logging.getLogger("vector")

import re

# Kreisel und Platzkanten tragen meist nur den Namen der durchgehenden Strasse (Testgebiet: 162 von
# 163 Kreiselnamen). Solche Namen ergeben keinen Platz-Namenpunkt.
STREET_NAME = re.compile(
    r"(?i)(strasse|str\.|weg|gasse|gässli|rain|steig|stieg|allee|ring|ausfahrt|einfahrt|"
    r"zufahrt|quai|promenade|route|chemin|rue|avenue|via|viale|strada)$|^(rue|avenue|chemin|route|via) ")


SQUARE_NAME = re.compile(r"(?i)(platz|tor|markt)$")


def add_square_points(b, area: Area, admin, road_index=None, dedup_m: float = 100.0,
                      cluster_m: float = 30.0) -> None:
    """Namenpunkte für Plätze und Kreisel (Entscheid nach Gerätetest 10).

    Quellen: TLM-Strassenkanten mit objektart=Platz oder kreisel=Wahr und Strassenname (Punkt am
    Schwerpunkt der zusammenhängenden Kanten gleichen Namens), ergänzt um Einträge
    STR_TYPE=Place des Strassenverzeichnisses (Tore, Pärke …). Tags: place=square, name,
    swisstopo:namenpunkt=platz. Kein Punkt, wenn ein Punkt gleichen Namens (z. B. swissNAMES3D)
    näher als 100 m liegt.
    """
    from .admin import is_in_tags
    from .common import COORD_SCALE
    from pyproj import Transformer
    cands = []  # (name, Punkt LV95, Quelle)
    place_names = set()
    x0, y0, x1, y1 = area.lv95_bbox()
    sv = []
    with open(STREET_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            if r["STR_TYPE"] != "Place" or r["STR_STATUS"] != "real":
                continue
            place_names.add(r["STN_LABEL"].strip())
            try:
                x, y = float(r["STR_EASTING"]), float(r["STR_NORTHING"])
            except ValueError:
                continue
            if x0 <= x <= x1 and y0 <= y <= y1:
                sv.append((r["STN_LABEL"].strip(), shapely.Point(x, y), "strassenverzeichnis"))
    if road_index is not None and getattr(road_index, "platz", None):
        by_name: dict[str, list] = {}
        for name, g in road_index.platz:
            # nur echte Platznamen: im Strassenverzeichnis als Place geführt oder …platz/…tor/…markt
            if name and not STREET_NAME.search(name) and (name in place_names or SQUARE_NAME.search(name)):
                by_name.setdefault(name, []).append(g)
        for name, gs in by_name.items():
            merged = shapely.union_all(shapely.buffer(np.array(gs, dtype=object), cluster_m / 2))
            for part in shapely.get_parts(merged):
                members = [g for g in gs if g.intersects(part)]
                cands.append((name, shapely.centroid(shapely.union_all(members)), "tlm"))
    cands += sv
    if not cands:
        return
    # vorhandene benannte Punkte (swissNAMES3D, POIs) in LV95
    to_lv = Transformer.from_crs(4326, 2056, always_xy=True)
    names = {c[0] for c in cands}
    existing: dict[str, list] = {}
    for nid, tg in b.node_tags.items():
        nm = tg.get("name")
        if nm in names and "addr:housenumber" not in tg:
            x, y = to_lv.transform(b.node_lon[nid - 1] / COORD_SCALE, b.node_lat[nid - 1] / COORD_SCALE)
            existing.setdefault(nm, []).append((x, y))
    lv = np.array([c[1] for c in cands], dtype=object)
    gem, kt, cc = admin.lookup_points(lv)
    pts = clip_wgs84(lv, area)
    stats = {"tlm": 0, "strassenverzeichnis": 0, "doppelt": 0}
    for i, (name, p_lv, src) in enumerate(cands):
        p = pts[i]
        if p is None or p.is_empty:
            continue
        near = existing.get(name, [])
        if any((p_lv.x - x) ** 2 + (p_lv.y - y) ** 2 < dedup_m ** 2 for x, y in near):
            stats["doppelt"] += 1
            continue
        existing.setdefault(name, []).append((p_lv.x, p_lv.y))
        t = {"place": "square", "name": name, "swisstopo:namenpunkt": "platz", "source": "swisstopo",
             "swisstopo:quelle": src}
        t.update(is_in_tags(gem[i], kt[i], cc[i]))
        b.add_point(p.x, p.y, t)
        stats[src] += 1
    log.info("Platz-/Kreisel-Namenpunkte: %s", stats)
