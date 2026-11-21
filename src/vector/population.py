"""Einwohnerzahl (`population`) am Hauptort jeder Gemeinde (Wunsch style-typ: Garmin blendet Orte
nach Grössenrang ein). Quelle: swissBOUNDARIES3D `tlm_hoheitsgebiet.einwohnerzahl` (©swisstopo, OGD).

Zuordnung je Gemeinde (nur `place`-Knoten mit Objektart `Ort` innerhalb der Gemeindefläche):
1. Ort mit dem Gemeindenamen (ohne Kantonszusatz, z. B. „Wil (SG)“ → „Wil“),
2. sonst der grösste Ort der Gemeinde (swissNAMES3D-Einwohnerkategorie), bei Gleichstand der
   zentralste (Beispiel Gaiserwald → Abtwil).
"""

from __future__ import annotations

import logging
import re

import numpy as np
import pyogrio
import shapely
from pyproj import Transformer

from .common import BOUNDARIES_GPKG, COORD_SCALE, NAMES_GPKG, Area, read_layer, val

log = logging.getLogger("vector")

# Kantonszusatz: „Wil (SG)“ (swissBOUNDARIES3D) bzw. „Wil SG“ (swissNAMES3D)
_SUFFIX = re.compile(r"\s*(\([A-Z]{2}\)|\b(AG|AI|AR|BE|BL|BS|FR|GE|GL|GR|JU|LU|NE|NW|OW|SG|SH|SO|SZ|TG|TI|UR|VD|VS|ZG|ZH))$")
# Rang der Einwohnerkategorie (swissNAMES3D)
_EW_RANK = {"> 100'000": 8, "50'000 bis 100'000": 7, "10'000 bis 49'999": 6, "2'000 bis 9'999": 5,
            "1'000 bis 1'999": 4, "100 bis 999": 3, "50 bis 99": 2, "20 bis 49": 1, "< 20": 0}


def _norm(name: str) -> str:
    return _SUFFIX.sub("", name or "").strip().casefold()


def add_population(b, area: Area) -> None:
    gem = read_layer(BOUNDARIES_GPKG, "tlm_hoheitsgebiet", area)
    gem = gem[gem["objektart"].isin(["Gemeindegebiet"])].reset_index(drop=True)
    if not len(gem):
        return
    geoms = shapely.force_2d(gem.geometry.values)
    # place-Knoten (Ort) aus dem Builder, in LV95
    to_lv = Transformer.from_crs(4326, 2056, always_xy=True)
    to_wgs = Transformer.from_crs(2056, 4326, always_xy=True)
    ids = [nid for nid, t in b.node_tags.items()
           if t.get("place") in ("city", "town", "village", "hamlet") and t.get("swisstopo:objektart") == "Ort"]
    if not ids:
        return
    lon = np.array([b.node_lon[i - 1] for i in ids]) / COORD_SCALE
    lat = np.array([b.node_lat[i - 1] for i in ids]) / COORD_SCALE
    x, y = to_lv.transform(lon, lat)
    pts = shapely.points(np.column_stack([x, y]))
    tree = shapely.STRtree(pts)
    # Alle Orte (swissNAMES3D) im Bereich der ganzen Gemeindeflächen, auch ausserhalb der Kachel:
    # Hat die Gemeinde irgendwo einen Ort mit ihrem Namen, greift die Rückfallregel nicht (sonst
    # bekämen über Kachelgrenzen reichende Gemeinden zwei Einträge).
    tb = tuple(shapely.total_bounds(geoms))
    orte = pyogrio.read_dataframe(NAMES_GPKG, layer="swissnames3d_pkt", bbox=tb, columns=["name"],
                                  where="objektklasse_tlm = 'TLM_SIEDLUNGSNAME_ZENTRUM' AND objektart = 'Ort'")
    orte_pts = shapely.force_2d(orte.geometry.values)
    orte_tree = shapely.STRtree(orte_pts)
    orte_names = [_norm(n) for n in orte["name"]]
    stats = {"name": 0, "groesster": 0, "ohne_ort": 0}
    for gi, g in enumerate(geoms):
        ew = val(gem["einwohnerzahl"].iloc[gi])
        if ew is None:
            continue
        inside = tree.query(g, predicate="contains")
        if not len(inside):
            stats["ohne_ort"] += 1
            continue
        gname = _norm(gem["name"].iloc[gi])
        same = [j for j in inside if _norm(b.node_tags[ids[j]].get("name")) == gname]
        if same:
            j = same[0]
            stats["name"] += 1
        else:
            if any(orte_names[k] == gname for k in orte_tree.query(g, predicate="contains")):
                continue  # Hauptort mit Gemeindenamen liegt in einer anderen Kachel
            c = shapely.point_on_surface(g)
            # Kachelmodus: nur die Kachel mit dem Gemeinde-Mittelpunkt entscheidet, sonst bekäme eine
            # angeschnittene Gemeinde in der Nachbarkachel einen falschen Hauptort
            lon_c, lat_c = to_wgs.transform(c.x, c.y)
            if not (area.west <= lon_c < area.east and area.south <= lat_c < area.north):
                continue
            # grösster Ort der Gemeinde (Einwohnerkategorie), bei Gleichstand der zentralste
            j = min(inside, key=lambda k: (
                -_EW_RANK.get(b.node_tags[ids[k]].get("swisstopo:einwohnerkategorie"), -1),
                pts[k].distance(c)))
            stats["groesster"] += 1
        t = b.node_tags[ids[j]]
        t["population"] = str(int(float(ew)))
        t["swisstopo:population_quelle"] = "swissBOUNDARIES3D Gemeinde " + str(gem["name"].iloc[gi])
    log.info("population an Hauptorten: %s", stats)
