"""POIs aus swissTLM3D: Einzelobjekte, Haltestellen, Seilbahnstationen, Areale, Strasseninfos,
benannte Gebäude. Abbildung siehe docs/daten/tag-schema.md, Abschnitt „POIs“.

Alle POIs sind eigene Knoten mit `swisstopo:poi=<herkunft>`, damit der Stil sie gezielt
behandeln kann. Flächen-POIs liegen am inneren Punkt (point_on_surface) der Fläche.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

import numpy as np
import shapely

from .common import TLM_GPKG, Area, clip_wgs84, first_name, read_layer, to_wgs84, val

log = logging.getLogger("vector")


def _uuid(u):
    return str(u).strip("{}").upper() if u is not None else None


_SEEN: dict[tuple, list[tuple[float, float]]] = {}
DEDUP_M = 100.0


def _poi(b, pt, tags, kind, counts):
    """POI schreiben; gleiche Art (Herkunft + Objektart) mit gleichem Namen im Umkreis von
    100 m nur einmal (z. B. mehrere Haltekanten eines Bahnhofs, geteilte Parkplatzareale)."""
    if pt is None or pt.is_empty:
        return
    name = tags.get("name")
    if name:
        key = (kind, tags.get("swisstopo:objektart"), name)
        lat_m = 111_200.0
        lon_m = 111_200.0 * 0.68
        for x, y in _SEEN.get(key, ()):
            if ((pt.x - x) * lon_m) ** 2 + ((pt.y - y) * lat_m) ** 2 < DEDUP_M ** 2:
                counts["doppelt_verworfen"] += 1
                return
        _SEEN.setdefault(key, []).append((pt.x, pt.y))
    tags = {"source": "swisstopo", "swisstopo:poi": kind, **tags}
    b.add_point(pt.x, pt.y, tags)
    counts[kind] += 1


# --- Einzelobjekte ---------------------------------------------------------------
EO_TAGS = {
    "Gipfelkreuz": {"man_made": "cross", "summit:cross": "yes"},
    "Bildstock": {"historic": "wayside_shrine"},
    "Brunnen": {"amenity": "fountain"},
    "Quelle": {"natural": "spring"},
    "Wasserfall": {"waterway": "waterfall"},
    "Denkmal": {"historic": "memorial"},
    "Grotte, Hoehle": {"natural": "cave_entrance"},
    "Triangulationspyramide": {"man_made": "survey_point", "survey_point:structure": "pyramid"},
}
# Diese Einzelobjekte kommen aus tlm_eo_einzelobjekt, nicht aus swissNAMES3D (sonst doppelt)
EO_FROM_TLM = set(EO_TAGS)


def add_einzelobjekte(b, area: Area, counts) -> None:
    L = "tlm_eo_einzelobjekt"
    df = read_layer(TLM_GPKG, L, area)
    pts = clip_wgs84(df.geometry.values, area)
    for i, p in enumerate(pts):
        oa = df["objektart"].iloc[i]
        name, alt = first_name(df["name"].iloc[i])
        if oa in EO_TAGS:
            t = dict(EO_TAGS[oa])
        elif name:  # z. B. benannte Wasserversorgung
            t = {"man_made": "water_works"} if oa == "Wasserversorgung" else {}
        else:
            continue
        t.update({"name": name, "alt_name": alt, "swisstopo:layer": L, "swisstopo:objektart": oa,
                  "swisstopo:uuid": _uuid(df["uuid"].iloc[i])})
        _poi(b, p, t, "einzelobjekt", counts)


# --- Haltestellen und Seilbahnstationen ---------------------------------------------
HALT_TAGS = {
    "Haltestelle Bahn": {"railway": "station", "public_transport": "station", "train": "yes"},
    "Haltestelle Bus": {"highway": "bus_stop", "public_transport": "platform", "bus": "yes"},
    "Haltestelle Schiff": {"amenity": "ferry_terminal", "public_transport": "station", "ferry": "yes"},
    "Uebrige Bahnen": {"aerialway": "station", "public_transport": "station"},
}


# swisstopo:oev (Overlay trennt danach, die Basiskarte lässt Tramhalte weg). Tram: Haltestelle Bahn mit
# Tramgleis (tlm_oev_eisenbahn verkehrsmittel=Tram) im Umkreis von TRAM_RADIUS und ohne Bahngleis dort.
OEV_KIND = {"Haltestelle Bahn": "bahn", "Haltestelle Bus": "bus", "Haltestelle Schiff": "schiff",
            "Uebrige Bahnen": "seilbahn"}
TRAM_RADIUS = 20.0
# swisstopo:oev_art für Seilbahnen: objektart der nächsten tlm_oev_uebrige_bahn (Haltestellen bis 80 m)
OEV_ART = {"Luftseilbahn": "luftseilbahn", "Gondelbahn": "gondelbahn", "Sesselbahn": "sesselbahn",
           "Skilift": "skilift", "Lift": "lift", "Standseilbahn": "standseilbahn"}
OEV_RANK = {"Haltestelle Bahn": "2", "Haltestelle Schiff": "3", "Uebrige Bahnen": "3", "Haltestelle Bus": "4"}


def station_rank(lv, oas, area: Area, radius_perron=200.0, radius_track=100.0):
    """Bahnhof-Rang aus swissTLM3D allein (ohne Fahrplan): Perronfläche im Umkreis von 200 m und
    Zahl der Gleise auf einem Kreis von 100 m. 1 Grossbahnhof (≥ 5000 m², z. B. St. Gallen, Wil,
    Rorschach), 2 Knoten (≥ 3000 m²: Gossau, Herisau, Wattwil), 3 Bahnhof (≥ 1500 m² oder ≥ 4
    Gleise: Uzwil, Flawil, Appenzell), 4 übrige Halte. Nur für „Haltestelle Bahn“ belegt."""
    n = len(lv)
    rank = np.full(n, 4, dtype=np.int8)
    perron = np.zeros(n)
    rail_idx = np.where(oas == "Haltestelle Bahn")[0]
    if not len(rail_idx):
        return rank, perron
    per = read_layer(TLM_GPKG, "tlm_bauten_verkehrsbaute_ply", area, columns=["objektart"],
                     where="objektart = 'Perron'")
    pg = shapely.force_2d(per.geometry.values)
    rail = read_layer(TLM_GPKG, "tlm_oev_eisenbahn", area, columns=["anschlussgleis"])
    rg = shapely.force_2d(rail.geometry.values[(rail["anschlussgleis"] != "Wahr").values])
    pt = shapely.STRtree(pg) if len(pg) else None
    rt = shapely.STRtree(rg) if len(rg) else None
    for i in rail_idx:
        p = lv[i]
        if pt is not None:
            perron[i] = shapely.area(pg[pt.query(p, predicate="dwithin", distance=radius_perron)]).sum()
        tracks = 0
        if rt is not None:
            ring = p.buffer(radius_track).exterior
            hit = rg[rt.query(ring, predicate="intersects")]
            tracks = len(shapely.get_coordinates(shapely.intersection(hit, ring))) // 2
        a = perron[i]
        rank[i] = 1 if a >= 5000 else 2 if a >= 3000 else 3 if (a >= 1500 or tracks >= 4) else 4
    return rank, perron


def tram_stops(lv, oas, area: Area, radius=TRAM_RADIUS) -> np.ndarray:
    """True für Haltestellen Bahn mit Tramgleis und ohne Bahngleis (Anschlussgleise zählen nicht) im Umkreis.
    Schweiz: ca. 1100 von 3157 (Bern, Basel, Zürich, Genf, Glattal …)."""
    out = np.zeros(len(lv), dtype=bool)
    rail_idx = np.where(oas == "Haltestelle Bahn")[0]
    if not len(rail_idx):
        return out
    e = read_layer(TLM_GPKG, "tlm_oev_eisenbahn", area, columns=["verkehrsmittel", "anschlussgleis"])
    g = shapely.force_2d(e.geometry.values)
    vm = e["verkehrsmittel"].values
    tram = g[vm == "Tram"]
    if not len(tram):
        return out
    bahn = g[(vm != "Tram") & (e["anschlussgleis"].values != "Wahr")]
    tt = shapely.STRtree(tram)
    bt = shapely.STRtree(bahn) if len(bahn) else None
    pts = lv[rail_idx]
    near_t = np.zeros(len(pts), dtype=bool)
    near_t[np.unique(tt.query(pts, predicate="dwithin", distance=radius)[0])] = True
    near_b = np.zeros(len(pts), dtype=bool)
    if bt is not None:
        near_b[np.unique(bt.query(pts, predicate="dwithin", distance=radius)[0])] = True
    out[rail_idx] = near_t & ~near_b
    return out


def seilbahn_art(lv, oas, area: Area, radius=80.0) -> list:
    """oev_art je Haltestelle „Uebrige Bahnen“ aus der nächsten Seilbahn (sonst None)."""
    out = [None] * len(lv)
    idx = np.where(oas == "Uebrige Bahnen")[0]
    if not len(idx):
        return out
    u = read_layer(TLM_GPKG, "tlm_oev_uebrige_bahn", area, columns=["objektart"])
    if not len(u):
        return out
    tree = shapely.STRtree(shapely.force_2d(u.geometry.values))
    (qi, gi), dist = tree.query_nearest(lv[idx], max_distance=radius, return_distance=True, all_matches=False)
    for a, j in zip(qi.tolist(), gi.tolist()):
        out[idx[a]] = OEV_ART.get(u["objektart"].iloc[j])
    return out


def add_haltestellen(b, area: Area, counts) -> np.ndarray:
    """Gibt die Haltestellen (LV95) zurück, um doppelte Seilbahnstationen zu vermeiden."""
    L = "tlm_oev_haltestelle"
    df = read_layer(TLM_GPKG, L, area)
    lv = shapely.force_2d(df.geometry.values)
    pts = clip_wgs84(lv, area)
    oas = df["objektart"].values
    # Umsteigeknoten: Bahnhaltestelle mit Bus- oder Schiffshaltestelle im Umkreis von 150 m
    hub = np.zeros(len(lv), dtype=bool)
    other = lv[oas != "Haltestelle Bahn"]
    if len(other):
        tree = shapely.STRtree(other)
        rail = np.where(oas == "Haltestelle Bahn")[0]
        ip, _ = tree.query(lv[rail], predicate="dwithin", distance=150.0)
        hub[rail[np.unique(ip)]] = True
    rank, perron = station_rank(lv, oas, area)
    tram = tram_stops(lv, oas, area)
    art = seilbahn_art(lv, oas, area)
    for i, p in enumerate(pts):
        oa = df["objektart"].iloc[i]
        name, alt = first_name(df["name"].iloc[i])
        t = dict(HALT_TAGS.get(oa, {"public_transport": "stop_position"}))
        if oa == "Haltestelle Bahn":
            t["swisstopo:bahnhof_rang"] = str(rank[i])
            t["swisstopo:perronflaeche_m2"] = str(int(perron[i]))
        # Rang für den Stil (Review 1: Haltestellen prominenter): 1 Bahn-Umsteigeknoten, 2 Bahn,
        # 3 Schiff und übrige Bahnen (Seil-, Zahnradbahnen), 4 Bus
        t["swisstopo:oev"] = "tram" if tram[i] else OEV_KIND.get(oa, "andere")
        if tram[i]:
            t["tram"] = "yes"
            t.pop("train", None)
        t["swisstopo:oev_art"] = art[i]
        t["swisstopo:oev_rang"] = "1" if hub[i] else OEV_RANK.get(oa, "4")
        t.update({"name": name, "alt_name": alt, "swisstopo:layer": L, "swisstopo:objektart": oa,
                  "swisstopo:uuid": _uuid(df["uuid"].iloc[i]),
                  "uic_ref": val(df["dienststellen_nummer"].iloc[i])})
        if t["uic_ref"] is not None:
            t["uic_ref"] = str(int(float(t["uic_ref"])))
        _poi(b, p, t, "haltestelle", counts)
    return lv[df["objektart"].values == "Uebrige Bahnen"]


AERIAL_STATIONS = {"Luftseilbahn", "Gondelbahn", "Sesselbahn", "Skilift", "Standseilbahn"}


def add_aerialway_stations(b, area: Area, halt_lv, counts, radius=80.0) -> None:
    """Berg- und Talstation (Linienenden, Höhe aus Z) von Seilbahnen und Skiliften."""
    L = "tlm_oev_uebrige_bahn"
    df = read_layer(TLM_GPKG, L, area)
    tree = shapely.STRtree(halt_lv) if len(halt_lv) else None
    for i, g in enumerate(df.geometry.values):
        oa = df["objektart"].iloc[i]
        if oa not in AERIAL_STATIONS or val(df["ausser_betrieb"].iloc[i]) == "Wahr":
            continue
        c = shapely.get_coordinates(g, include_z=True)
        name, _ = first_name(df["name"].iloc[i])
        ends = [c[0], c[-1]]
        lower = 0 if ends[0][2] <= ends[1][2] else 1
        for k, e in enumerate(ends):
            p_lv = shapely.Point(e[0], e[1])
            if tree is not None and len(tree.query(p_lv, predicate="dwithin", distance=radius)):
                continue  # Haltestelle „Uebrige Bahnen“ vorhanden
            role = "Talstation" if k == lower else "Bergstation"
            p = clip_wgs84(np.array([p_lv]), area)[0]
            t = {"aerialway": "station", "name": f"{name} {role}" if name else role,
                 "ele": str(int(round(e[2]))) if np.isfinite(e[2]) else None,
                 "swisstopo:layer": L, "swisstopo:objektart": oa, "swisstopo:station": role,
                 "swisstopo:oev": "skilift" if oa == "Skilift" else "seilbahn",
                 "swisstopo:oev_art": OEV_ART.get(oa),
                 "swisstopo:uuid": _uuid(df["uuid"].iloc[i])}
            _poi(b, p, t, "seilbahnstation", counts)


# --- Areale ----------------------------------------------------------------------
AREA_POI = {
    # Freizeitareal
    "Campingplatzareal": {"tourism": "camp_site"},
    "Schwimmbadareal": {"leisure": "water_park"},
    "Golfplatzareal": {"leisure": "golf_course"},
    "Zooareal": {"tourism": "zoo"},
    "Sportplatzareal": {"leisure": "sports_centre"},
    "Standplatzareal": {"tourism": "caravan_site"},
    "Freizeitanlagenareal": {"leisure": "park"},
    "Pferderennbahnareal": {"leisure": "track", "sport": "horse_racing"},
    # Nutzungsareal
    "Spitalareal": {"amenity": "hospital"},
    "Friedhof": {"amenity": "grave_yard"},
    "Klosterareal": {"amenity": "monastery"},
    "Schul- und Hochschulareal": {"amenity": "school"},
    "Historisches Areal": {"historic": "yes", "tourism": "attraction"},
    "Oeffentliches Parkareal": {"leisure": "park"},
    "Abwasserreinigungsareal": {"man_made": "wastewater_plant"},
    "Kraftwerkareal": {"power": "plant"},
    "Kehrichtverbrennungsareal": {"industrial": "waste_incineration"},
    "Deponieareal": {"landuse": "landfill"},
    "Abbauareal": {"landuse": "quarry"},
    "Messeareal": {"amenity": "exhibition_centre"},
    "Truppenuebungsplatz": {"military": "training_area"},
    "Massnahmenvollzugsanstaltsareal": {"amenity": "prison"},
    # Verkehrsareal
    "Oeffentliches Parkplatzareal": {"amenity": "parking"},
    "Rastplatzareal": {"highway": "rest_area"},
    "Flugfeldareal": {"aeroway": "aerodrome"},
    "Flugplatzareal": {"aeroway": "aerodrome"},
    "Flughafenareal": {"aeroway": "aerodrome"},
    "Heliport": {"aeroway": "heliport"},
}
# auch ohne Namen als POI (z. B. öffentliche Parkplätze, Friedhöfe)
AREA_POI_UNNAMED = {"Oeffentliches Parkplatzareal", "Rastplatzareal", "Friedhof", "Campingplatzareal",
                    "Schwimmbadareal", "Heliport", "Flugfeldareal", "Flugplatzareal", "Spitalareal"}


def add_area_pois(b, area: Area, counts) -> None:
    for L in ("tlm_areale_freizeitareal", "tlm_areale_nutzungsareal", "tlm_areale_verkehrsareal"):
        df = read_layer(TLM_GPKG, L, area)
        lv = shapely.force_2d(df.geometry.values)
        inner = shapely.point_on_surface(shapely.make_valid(lv))
        pts = clip_wgs84(inner, area)
        for i, p in enumerate(pts):
            oa = df["objektart"].iloc[i]
            if oa not in AREA_POI:
                continue
            name, alt = first_name(df["name"].iloc[i])
            if not name and oa not in AREA_POI_UNNAMED:
                continue
            t = dict(AREA_POI[oa])
            if oa == "Historisches Areal" and historic_tags(name):
                t.update(historic_tags(name))
                t["swisstopo:poi_heuristik"] = "name"
            t.update({"name": name, "alt_name": alt, "swisstopo:layer": L, "swisstopo:objektart": oa,
                      "swisstopo:uuid": _uuid(df["uuid"].iloc[i])})
            _poi(b, p, t, "areal", counts)


# --- Strasseninfo ------------------------------------------------------------------
INFO_POI = {
    "Raststaette": {"highway": "services"},
    "Verladestation": {"railway": "station", "service": "car_shuttle", "motorcar": "yes"},
    "Zahlstelle": {"barrier": "toll_booth"},
    "Zollamt 24h 24h": {"amenity": "customs", "opening_hours": "24/7"},
    "Zollamt 24h eingeschraenkt": {"amenity": "customs"},
    "Zollamt eingeschraenkt": {"amenity": "customs"},
}


def add_strasseninfo_pois(b, area: Area, counts) -> None:
    L = "tlm_strassen_strasseninfo"
    names = ", ".join(f"'{k}'" for k in INFO_POI)
    df = read_layer(TLM_GPKG, L, area, where=f"objektart IN ({names})")
    pts = clip_wgs84(df.geometry.values, area)
    for i, p in enumerate(pts):
        oa = df["objektart"].iloc[i]
        name, alt = first_name(df["name"].iloc[i])
        t = dict(INFO_POI[oa])
        t.update({"name": name, "alt_name": alt, "swisstopo:layer": L, "swisstopo:objektart": oa,
                  "swisstopo:uuid": _uuid(df["uuid"].iloc[i])})
        for k in ("tankstelle", "restaurant", "shop", "toiletten"):
            v = val(df[k].iloc[i])
            if v:
                t[f"swisstopo:{k}"] = v
        _poi(b, p, t, "strasseninfo", counts)


# --- Gebäude ---------------------------------------------------------------------
BUILDING_POI = {
    "Kapelle": {"amenity": "place_of_worship", "building": "chapel"},
    "Sakrales Gebaeude": {"amenity": "place_of_worship"},
    "Sakraler Turm": {"amenity": "place_of_worship"},
    "Turm": {"man_made": "tower"},
}
NUTZUNG_POI = {
    "Aussichtsturm": {"man_made": "tower", "tower:type": "observation", "tourism": "viewpoint"},
    "Gasthof abgelegen": {"amenity": "restaurant"},
    "Observatorium": {"man_made": "observatory"},
    "Stadion": {"leisure": "stadium"},
    "Schiessstand": {"leisure": "sports_centre", "sport": "shooting"},
    "Parkhaus": {"amenity": "parking", "parking": "multi-storey"},
    "Sporthalle": {"leisure": "sports_hall"},
    "Schutzhuette": {"tourism": "wilderness_hut"},
    "Wasserturm": {"man_made": "water_tower"},
    "Leuchtturm": {"man_made": "lighthouse"},
}


def nutzung_tags(nutzung) -> dict:
    """Auch kombinierte Nutzungen („Aussichtsturm, Wasserturm“): Tags aller Teile, erster gewinnt."""
    t: dict = {}
    for part in reversed([x.strip() for x in str(nutzung or "").split(",")]):
        t.update(NUTZUNG_POI.get(part, {}))
    return t


# Historisches Areal: Art aus dem Namen (TLM kennt nur „Historisches Areal“)
HISTORIC_NAME_RULES = [  # Reihenfolge zählt: „Ruderi del Castello“ ist eine Ruine
    (re.compile(r"(?i)ruine|ruderi|rovine|ruines?\b|burgstelle|burgstall|sito castrale"),
     {"historic": "ruins", "ruins": "castle"}),
    (re.compile(r"(?i)prähistor|préhistor|preistor|römisch|roemisch|romain|romano|kastell|gutshof|"
                r"wehranlage|refugium|villa\b"), {"historic": "archaeological_site"}),
    (re.compile(r"(?i)kloster|abtei|stift\b|kartause|komturei|propstei|abbaye|couvent|convento"),
     {"historic": "monastery"}),
    (re.compile(r"(?i)burg\b|^burg|schloss|schlössli|festung|\bfort\b|wohnturm|château|chateau|"
                r"castel|chast|tour\b"), {"historic": "castle"}),
    (re.compile(r"(?i)letzi|landwehr|schanze"), {"historic": "citywalls"}),
]


def historic_tags(name) -> dict:
    for rx, tags in HISTORIC_NAME_RULES:
        if name and rx.search(name):
            return dict(tags)
    return {}
# Heuristik nach Gebäudename (in docs/daten/tag-schema.md als heuristisch gekennzeichnet)
NAME_RULES = [
    (re.compile(r"(?i)\bSAC\b|clubhütte|passhütte|berghütte|berghaus"), {"tourism": "alpine_hut"}),
    (re.compile(r"(?i)(wald|schirm|grill|forst|schützen|pfadi|feuerstellen)hütte"),
     {"amenity": "shelter", "shelter_type": "basic_hut"}),
    (re.compile(r"(?i)\bhotel\b|\w+hotel\b"), {"tourism": "hotel"}),
    (re.compile(r"(?i)berggasthaus|gasthaus|gasthof|restaurant|alpwirtschaft|beizli|wirtschaft\b"),
     {"amenity": "restaurant"}),
]


def building_name_tags(name: str) -> dict:
    for rx, tags in NAME_RULES:
        if rx.search(name):
            return dict(tags)
    return {}


def add_building_pois(b, area: Area, counts, merge_dist=150.0) -> None:
    L = "tlm_bauten_gebaeude_footprint"
    df = read_layer(TLM_GPKG, L, area, columns=["uuid", "objektart", "name", "nutzung"],
                    where="name IS NOT NULL OR nutzung IS NOT NULL")
    lv = shapely.force_2d(df.geometry.values)
    # Ein Gebäudekomplex hat oft mehrere Footprints mit gleichem Namen: einen POI je Name und
    # Umkreis (am grössten Footprint)
    order = np.argsort(-shapely.area(lv))
    taken: dict[str, list] = {}
    inner = shapely.point_on_surface(shapely.make_valid(lv))
    pts = clip_wgs84(inner, area)
    heur = Counter()
    for i in order:
        oa = df["objektart"].iloc[i]
        name, alt = first_name(df["name"].iloc[i])
        nutzung = val(df["nutzung"].iloc[i])
        t: dict = {}
        t.update(nutzung_tags(nutzung))
        if oa in BUILDING_POI:
            t = {**BUILDING_POI[oa], **t}
        if name and not t:
            t = building_name_tags(name)
            if t:
                t["swisstopo:poi_heuristik"] = "name"
                heur["/".join(f"{k}={v}" for k, v in t.items() if not k.startswith("swisstopo"))] += 1
        if not name and not t:
            continue
        if not t:
            t = {"building": "yes"}  # benanntes Gebäude ohne Klasse; Stil entscheidet
        key = name or f"{oa}/{nutzung}"
        p_lv = inner[i]
        if any(p_lv.distance(q) < merge_dist for q in taken.get(key, [])):
            continue
        taken.setdefault(key, []).append(p_lv)
        t.update({"name": name, "alt_name": alt, "swisstopo:layer": L, "swisstopo:objektart": oa,
                  "swisstopo:nutzung": nutzung, "swisstopo:uuid": _uuid(df["uuid"].iloc[i])})
        _poi(b, pts[i], t, "gebaeude", counts)
    log.info("Gebäude-POIs nach Namensheuristik: %s", dict(heur))


def add_pois(b, area: Area) -> None:
    counts: Counter = Counter()
    _SEEN.clear()
    add_einzelobjekte(b, area, counts)
    halt = add_haltestellen(b, area, counts)
    add_aerialway_stations(b, area, halt, counts)
    add_area_pois(b, area, counts)
    add_strasseninfo_pois(b, area, counts)
    add_building_pois(b, area, counts)
    log.info("POIs: %s", dict(counts))
