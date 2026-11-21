"""Gemeinde-/Kantonszuordnung und Grenzlinien aus swissBOUNDARIES3D."""

from __future__ import annotations

import logging

import numpy as np
import shapely

from .common import BOUNDARIES_GPKG, Area, clip_wgs84, read_layer, val

log = logging.getLogger("vector")

ADMIN_LEVEL = {1: "2", 2: "4", 3: "6", 4: "8"}


class AdminLookup:
    """Punkt (LV95) → (Gemeinde, Kanton)."""

    def __init__(self, area: Area | None):
        gem = read_layer(BOUNDARIES_GPKG, "tlm_hoheitsgebiet", area)
        gem = gem[gem["objektart"].isin(["Gemeindegebiet", "Kommunanz"])].reset_index(drop=True)
        kt = read_layer(BOUNDARIES_GPKG, "tlm_kantonsgebiet", None)
        canton = {int(k): n for k, n in zip(kt["kantonsnummer"], kt["name"])}
        self.geoms = shapely.force_2d(gem.geometry.values)
        shapely.prepare(self.geoms)
        self.tree = shapely.STRtree(self.geoms)
        self.gemeinde = gem["name"].tolist()
        self.kanton = [
            canton.get(int(k)) if val(k) is not None else None for k in gem["kantonsnummer"]
        ]
        # ausländische Gebiete (icc != CH) nicht als Schweizer Gemeinde behandeln
        self.icc = gem["icc"].tolist()
        self.max_nearest = 1000.0  # m, Rückfall für Punkte auf/neben der Landesgrenze

    def lookup_points(self, pts: np.ndarray) -> tuple[list, list, list]:
        """pts: Shapely-Punkte in LV95. Liefert Listen (gemeinde, kanton, land)."""
        n = len(pts)
        gem = [None] * n
        kt = [None] * n
        cc = [None] * n
        idx_pt, idx_poly = self.tree.query(pts, predicate="intersects")
        for i, j in zip(idx_pt.tolist(), idx_poly.tolist()):
            if gem[i] is None:
                gem[i] = self.gemeinde[j]
                kt[i] = self.kanton[j]
                cc[i] = self.icc[j]
        # Punkte ausserhalb jeder Gemeinde (z. B. Gipfel genau auf der Landesgrenze wie das
        # Matterhorn): nächste Gemeinde im Umkreis von 1 km
        rest = [i for i in range(n) if gem[i] is None]
        if rest:
            ip, ig = self.tree.query_nearest(pts[rest], max_distance=self.max_nearest, all_matches=False)
            for a, j in zip(ip.tolist(), ig.tolist()):
                i = rest[a]
                gem[i] = self.gemeinde[j]
                kt[i] = self.kanton[j]
                cc[i] = self.icc[j]
        return gem, kt, cc


def is_in_tags(gem, kt, cc) -> dict:
    if gem is None:
        return {}
    if cc not in (None, "CH"):
        return {"is_in:country": cc}
    # is_in:country=CH an jedem Objekt: mkgmap gleicht mkgmap:country mit LocatorConfig.xml ab
    # (Schweiz/CHE, streetBeforeHousenumber → „Marktgasse 20“). Objekte ohne Land bekämen nur den
    # Standard aus --country-name, ohne diese Regel („20 Marktgasse“, BaseCamp-Test 9).
    return {"is_in:country": "CH", "is_in:county": kt, "is_in:city": gem}

    
def add_is_in_to_points(builder, admin: "AdminLookup") -> None:
    """Alle benannten Punkte (POIs, Namen, Anschlüsse) ohne is_in:city bekommen Gemeinde/Kanton/Land.

    Sonst fehlen ihnen im Suchindex Ort und Region, und BaseCamp zeigt nur das Standardland.
    """
    from .common import COORD_SCALE
    from pyproj import Transformer
    t = Transformer.from_crs(4326, 2056, always_xy=True)
    ids = [nid for nid, tg in builder.node_tags.items()
           if tg.get("name") and "is_in:city" not in tg and "addr:housenumber" not in tg]
    if not ids:
        return
    lon = np.array([builder.node_lon[i - 1] for i in ids]) / COORD_SCALE
    lat = np.array([builder.node_lat[i - 1] for i in ids]) / COORD_SCALE
    x, y = t.transform(lon, lat)
    gem, kt, cc = admin.lookup_points(shapely.points(np.column_stack([x, y])))
    n = 0
    for nid, g, k, c in zip(ids, gem, kt, cc):
        tags = is_in_tags(g, k, c)
        if tags:
            builder.node_tags[nid].update({a: b for a, b in tags.items() if b})
            n += 1
    log.info("is_in für Punkte ergänzt: %d von %d", n, len(ids))


def add_boundaries(builder, area: Area) -> None:
    df = read_layer(BOUNDARIES_GPKG, "tlm_hoheitsgrenze", area)
    geoms = clip_wgs84(df.geometry.values, area)
    n = 0
    for g, oa in zip(geoms, df["objektart"]):
        lvl = ADMIN_LEVEL.get(int(oa)) if val(oa) is not None else None
        if lvl is None or g is None or g.is_empty:
            continue
        n += builder.add_line(
            g,
            {
                "boundary": "administrative",
                "admin_level": lvl,
                "source": "swisstopo",
                "swisstopo:layer": "tlm_hoheitsgrenze",
            },
        )
    log.info("Grenzlinien: %d Wege", n)
