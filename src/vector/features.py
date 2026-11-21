"""Übrige swissTLM3D-Objekte: Bahn, Gewässer, Bodenbedeckung, Areale, Gebäude, Bauten."""

from __future__ import annotations

import logging

import numpy as np
import shapely

from . import rivers as river_order
from .common import TLM_GPKG, Area, clip_wgs84, first_name, int_str, read_layer, val

log = logging.getLogger("vector")


def _base(layer, oa, uuid=None) -> dict:
    t = {"source": "swisstopo", "swisstopo:layer": layer, "swisstopo:objektart": oa}
    if uuid is not None:
        t["swisstopo:uuid"] = str(uuid).strip("{}").upper()
    return t


def _bridge_tunnel(t: dict, kb, stufe) -> None:
    stufe = int(float(stufe)) if val(stufe) is not None else 0
    kb = val(kb)
    if kb:
        t["swisstopo:kunstbaute"] = kb
    if kb in ("Bruecke", "Bruecke mit Galerie", "Gedeckte Bruecke"):
        t["bridge"] = "yes"
        t["layer"] = str(max(stufe, 1))
    elif kb in ("Tunnel", "Unterfuehrung"):
        t["tunnel"] = "yes"
        t["layer"] = str(min(stufe, -1))
    elif kb == "Galerie":
        t["tunnel"] = "avalanche_protector"
    elif kb == "in/auf Gebaeude":
        t["covered"] = "yes"
    elif stufe:
        t["layer"] = str(stufe)


# --- Bahn ----------------------------------------------------------------------
RAIL = {
    "Normalspur": ("rail", "1435"),
    "Schmalspur": ("narrow_gauge", "1000"),
    "Schmalspur mit Normalspur": ("rail", "1000;1435"),
    "Kleinbahn": ("miniature", None),
}
AERIAL = {
    "Luftseilbahn": ("aerialway", "cable_car"),
    "Gondelbahn": ("aerialway", "gondola"),
    "Sesselbahn": ("aerialway", "chair_lift"),
    "Skilift": ("aerialway", "drag_lift"),
    "Lift": ("aerialway", "platter"),
    "Transportseil": ("aerialway", "goods"),
    "Foerderband": ("man_made", "goods_conveyor"),
}


PARALLEL_DIST_M = 8.0     # Abstand zur Mehrspurachse (Gleisabstand Normalspur ca. 3,8–4,5 m)
PARALLEL_SHARE = 0.8      # Anteil der Länge innerhalb dieses Abstands


def parallel_axes(df) -> np.ndarray:
    """Einzelgleis-Achsen neben einer mehrspurigen DKM-Achse (Wunsch style-typ, Review 2).

    swissTLM3D führt auf Doppelspurstrecken eine kartografische Achse (achse_dkm=Wahr,
    anzahl_spuren=2) und zusätzlich jedes Gleis als eigene Achse (achse_dkm=Falsch, ohne Spurzahl).
    Markiert wird eine Achse ohne DKM-Flag und ohne Anschlussgleis, die zu ≥ 80 % ihrer Länge
    höchstens 8 m neben einer DKM-Achse gleicher Spurweite mit anzahl_spuren ≥ 2 liegt. In Bahnhöfen
    und Weichenbereichen laufen die Gleise auseinander und bleiben unmarkiert.
    """
    res = np.zeros(len(df), dtype=bool)
    g = shapely.force_2d(df.geometry.values)
    sp = df["anzahl_spuren"].map(lambda v: int(float(v)) if val(v) is not None else 0).to_numpy()
    dkm = (df["achse_dkm"] == "Wahr").to_numpy()
    side = (df["anschlussgleis"] == "Wahr").to_numpy()
    oa = df["objektart"].to_numpy()
    for gauge in np.unique(oa):
        multi = dkm & (sp >= 2) & (oa == gauge)
        cand = np.where(~dkm & ~side & (oa == gauge))[0]
        if not multi.any() or not len(cand):
            continue
        zone = shapely.union_all(shapely.buffer(g[multi], PARALLEL_DIST_M, quad_segs=2))
        shapely.prepare(zone)
        lc = shapely.length(g[cand])
        inside = shapely.length(shapely.intersection(g[cand], zone))
        ok = (lc > 0) & (inside >= PARALLEL_SHARE * np.maximum(lc, 1e-9))
        res[cand[ok]] = True
    return res


def add_rail(b, area: Area) -> None:
    L = "tlm_oev_eisenbahn"
    df = read_layer(TLM_GPKG, L, area)
    par = parallel_axes(df)
    geoms = clip_wgs84(df.geometry.values, area)
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        r = df.iloc[i]
        oa = r["objektart"]
        rw, gauge = RAIL.get(oa, ("rail", None))
        t = _base(L, oa, r["uuid"])
        t["gauge"] = gauge
        if val(r["standseilbahn"]) == "Wahr":
            rw = "funicular"
        if val(r["zahnradbahn"]) == "Wahr":
            t["rack"] = "yes"
        if val(r["anschlussgleis"]) == "Wahr":
            t["service"] = "siding"
        if val(r["museumsbahn"]) == "Wahr":
            t["usage"] = "tourism"
        if val(r["ausser_betrieb"]) == "Wahr":
            rw = "disused"
        if val(r["auf_strasse"]) == "Wahr":
            t["embedded"] = "yes"
        t["railway"] = rw
        sp = val(r["anzahl_spuren"])
        if sp is not None:
            t["tracks"] = str(int(float(sp)))
        t["swisstopo:spurweite"] = oa
        t["swisstopo:achse_dkm"] = "yes" if val(r["achse_dkm"]) == "Wahr" else "no"
        if par[i]:
            t["swisstopo:parallelachse"] = "yes"
        _bridge_tunnel(t, r["kunstbaute"], r["stufe"])
        t["name"], t["alt_name"] = first_name(r["name"])
        b.add_line(g, t)

    L = "tlm_oev_uebrige_bahn"
    df = read_layer(TLM_GPKG, L, area)
    geoms = clip_wgs84(df.geometry.values, area)
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        r = df.iloc[i]
        oa = r["objektart"]
        k, v = AERIAL.get(oa, ("aerialway", "yes"))
        t = _base(L, oa, r["uuid"])
        if val(r["ausser_betrieb"]) == "Wahr":
            k, v = "disused:aerialway", v
        t[k] = v
        t["name"], t["alt_name"] = first_name(r["name"])
        b.add_line(g, t)


# --- Gewässer ------------------------------------------------------------------
def add_water_lines(b, area: Area, river_polys) -> None:
    L = "tlm_gewaesser_fliessgewaesser"
    df = read_layer(TLM_GPKG, L, area)
    geoms_lv = shapely.force_2d(df.geometry.values)
    # Fliessgewässer, die eine Wasserfläche (Bodenbedeckung „Fliessgewaesser“) schneiden, sind Flüsse
    rivers: set = set()
    if len(river_polys):
        tree = shapely.STRtree(river_polys)
        idx_l, _ = tree.query(geoms_lv, predicate="intersects")
        for i in set(idx_l.tolist()):
            nr = val(df["gewiss_nr"].iloc[i])
            if nr is not None:
                rivers.add(nr)
    geoms = clip_wgs84(geoms_lv, area)
    order = river_order.load()  # Flussordnung (landesweit, Cache), siehe rivers.py
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        r = df.iloc[i]
        oa = r["objektart"]
        if oa == "Seeachse":
            continue
        t = _base(L, oa, r["uuid"])
        t.update(river_order.tags(order, r["uuid"]))
        verlauf = val(r["verlauf"])
        if verlauf:
            t["swisstopo:verlauf"] = verlauf
        if oa == "Fliessgewaesser":
            t["waterway"] = "river" if val(r["gewiss_nr"]) in rivers else "stream"
        elif oa == "Trockenrinne":
            t["waterway"] = "ditch"
            t["intermittent"] = "yes"
        elif oa.startswith("Druckleitung"):
            t["man_made"] = "pipeline"
            t["substance"] = "water"
            t["location"] = "underground" if verlauf and verlauf.startswith("Unterirdisch") else None
        else:
            t["waterway"] = "stream"
        if verlauf and verlauf.startswith("Unterirdisch") and "waterway" in t:
            t["tunnel"] = "culvert"
            t["layer"] = "-1"
        elif verlauf == "Wasserfall":
            t["waterfall"] = "yes"
        elif verlauf == "Bruecke":
            t["bridge"] = "aqueduct"
            t["layer"] = "1"
        t["name"], t["alt_name"] = first_name(r["name"])
        t["ref:gewiss"] = int_str(r["gewiss_nr"])
        b.add_line(g, t)


# --- Bodenbedeckung --------------------------------------------------------------
LANDCOVER = {
    "Wald": {"natural": "wood"},
    "Wald offen": {"natural": "wood", "wood": "open"},
    "Gebueschwald": {"natural": "scrub"},
    "Gehoelzflaeche": {"natural": "wood", "wood": "copse"},
    "Fels": {"natural": "bare_rock"},
    "Fels locker": {"natural": "bare_rock", "density": "sparse"},
    "Felsbloecke": {"natural": "scree", "scree": "boulders"},
    "Felsbloecke locker": {"natural": "scree", "scree": "boulders", "density": "sparse"},
    "Lockergestein": {"natural": "scree"},
    "Lockergestein locker": {"natural": "scree", "density": "sparse"},
    "Gletscher": {"natural": "glacier"},
    "Schneefeld Toteis": {"natural": "glacier", "glacier:type": "dead_ice"},
    "Feuchtgebiet": {"natural": "wetland"},
    "Stehende Gewaesser": {"natural": "water", "water": "lake"},
    "Fliessgewaesser": {"natural": "water", "water": "river"},
}


def load_landcover(area: Area):
    df = read_layer(TLM_GPKG, "tlm_bb_bodenbedeckung", area)
    df["geometry"] = shapely.force_2d(df.geometry.values)
    return df


def add_landcover(b, area: Area, df, lake_names: dict[int, str]) -> None:
    L = "tlm_bb_bodenbedeckung"
    geoms = clip_wgs84(df.geometry.values, area)
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        oa = df["objektart"].iloc[i]
        t = _base(L, oa, df["uuid"].iloc[i])
        t.update(LANDCOVER.get(oa, {}))
        if i in lake_names:
            t["name"] = lake_names[i]
        b.add_area(g, t)


# --- Areale --------------------------------------------------------------------
AREALE = {
    "Schul- und Hochschulareal": {"amenity": "school"},
    "Spitalareal": {"amenity": "hospital"},
    "Friedhof": {"landuse": "cemetery"},
    "Obstanlage": {"landuse": "orchard"},
    "Reben": {"landuse": "vineyard"},
    "Baumschule": {"landuse": "plant_nursery"},
    "Schrebergartenareal": {"landuse": "allotments"},
    "Wald nicht bestockt": {"landuse": "forest"},
    "Abbauareal": {"landuse": "quarry"},
    "Deponieareal": {"landuse": "landfill"},
    "Abwasserreinigungsareal": {"man_made": "wastewater_plant"},
    "Kehrichtverbrennungsareal": {"landuse": "industrial", "industrial": "waste_incineration"},
    "Kraftwerkareal": {"power": "plant"},
    "Unterwerkareal": {"power": "substation"},
    "Historisches Areal": {"historic": "yes"},
    "Klosterareal": {"amenity": "monastery"},
    "Oeffentliches Parkareal": {"leisure": "park"},
    "Truppenuebungsplatz": {"landuse": "military"},
    "Massnahmenvollzugsanstaltsareal": {"amenity": "prison"},
    "Messeareal": {"landuse": "commercial"},
    "Sportplatzareal": {"leisure": "sports_centre"},
    "Schwimmbadareal": {"leisure": "water_park"},
    "Campingplatzareal": {"tourism": "camp_site"},
    "Standplatzareal": {"tourism": "caravan_site"},
    "Golfplatzareal": {"leisure": "golf_course"},
    "Freizeitanlagenareal": {"leisure": "park"},
    "Zooareal": {"tourism": "zoo"},
    "Pferderennbahnareal": {"leisure": "track", "sport": "horse_racing"},
    "Oeffentliches Parkplatzareal": {"amenity": "parking"},
    "Privates Parkplatzareal": {"amenity": "parking", "access": "private"},
    "Rastplatzareal": {"highway": "rest_area"},
    "Flugfeldareal": {"aeroway": "aerodrome"},
    "Flugplatzareal": {"aeroway": "aerodrome"},
    "Flughafenareal": {"aeroway": "aerodrome"},
    "Heliport": {"aeroway": "heliport"},
    "Gleisareal": {"landuse": "railway"},
    "Verkehrsflaeche": {"area:highway": "yes"},
    "Privates Fahrareal": {"area:highway": "yes", "access": "private"},
}


# Flächen-Tags der Areale ohne POI-Wirkung (siehe docs/daten/tag-schema.md, Areale)
AREALE_POLY = {
    "Schul- und Hochschulareal": {"landuse": "education"},
    "Spitalareal": {"landuse": "healthcare"},
    "Friedhof": {"landuse": "cemetery"},
    "Obstanlage": {"landuse": "orchard"},
    "Reben": {"landuse": "vineyard"},
    "Baumschule": {"landuse": "plant_nursery"},
    "Schrebergartenareal": {"landuse": "allotments"},
    "Wald nicht bestockt": {"landuse": "forest"},
    "Abbauareal": {"landuse": "quarry"},
    "Deponieareal": {"landuse": "landfill"},
    "Abwasserreinigungsareal": {"landuse": "industrial"},
    "Kehrichtverbrennungsareal": {"landuse": "industrial"},
    "Kraftwerkareal": {"landuse": "industrial"},
    "Unterwerkareal": {"landuse": "industrial"},
    "Klosterareal": {"landuse": "religious"},
    "Truppenuebungsplatz": {"landuse": "military"},
    "Messeareal": {"landuse": "commercial"},
    "Sportplatzareal": {"landuse": "recreation_ground"},
    "Schwimmbadareal": {"landuse": "recreation_ground"},
    "Golfplatzareal": {"landuse": "recreation_ground"},
    "Freizeitanlagenareal": {"landuse": "recreation_ground"},
    "Oeffentliches Parkareal": {"landuse": "recreation_ground"},
    "Gleisareal": {"landuse": "railway"},
    "Verkehrsflaeche": {"area:highway": "yes"},
    "Privates Fahrareal": {"area:highway": "yes", "access": "private"},
    "Privates Parkplatzareal": {"access": "private"},
}


def add_areale(b, area: Area) -> None:
    for L in ("tlm_areale_nutzungsareal", "tlm_areale_freizeitareal", "tlm_areale_verkehrsareal"):
        df = read_layer(TLM_GPKG, L, area)
        geoms = clip_wgs84(df.geometry.values, area)
        for i, g in enumerate(geoms):
            if g is None or g.is_empty:
                continue
            oa = df["objektart"].iloc[i]
            t = _base(L, oa, df["uuid"].iloc[i])
            # Fläche nur mit Flächen-Tags (landuse, area:highway, access). POI-Tags (amenity, tourism,
            # leisure, aeroway …) und der Name stehen am POI-Knoten (pois.py), damit es mit
            # --add-pois-to-areas keine Doppel gibt. Der Stil erkennt die Fläche an swisstopo:objektart.
            t.update(AREALE_POLY.get(oa, {}))
            # Ohne landuse o. ä. (z. B. Privates Parkplatzareal: nur access) wäre der geschlossene Weg
            # für OSM-Werkzeuge eine Linie (Review 2). area=yes macht ihn eindeutig zur Fläche.
            t["area"] = "yes"
            nm, _ = first_name(df["name"].iloc[i])
            if nm:
                t["swisstopo:name"] = nm
            b.add_area(g, t)

    # Schutzgebiete (in swissTLM3D nur der Schweizerische Nationalpark)
    L = "tlm_areale_schutzgebiet"
    df = read_layer(TLM_GPKG, L, area)
    geoms = clip_wgs84(df.geometry.values, area)
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        oa = df["objektart"].iloc[i]
        t = _base(L, oa, df["uuid"].iloc[i])
        t.update({"boundary": "national_park", "protect_class": "2"} if oa == "Nationalpark"
                 else {"boundary": "protected_area"})
        nm, _ = first_name(df["name"].iloc[i]) if "name" in df.columns else (None, None)
        if nm:
            t["swisstopo:name"] = nm
        b.add_area(g, t)


# --- Gebäude -------------------------------------------------------------------
BUILDINGS = {
    "Gebaeude": {"building": "yes"},
    "Offenes Gebaeude": {"building": "roof"},
    "Flugdach": {"building": "roof"},
    "Lagertank": {"man_made": "storage_tank"},
    "Im Bau": {"building": "construction"},
    "Sakrales Gebaeude": {"building": "church", "amenity": "place_of_worship"},
    "Kapelle": {"building": "chapel", "amenity": "place_of_worship"},
    "Sakraler Turm": {"building": "church", "man_made": "tower", "tower:type": "bell_tower"},
    "Hochhaus": {"building": "yes"},
    "Treibhaus": {"building": "greenhouse"},
    "Turm": {"man_made": "tower", "building": "yes"},
    "Hochkamin": {"man_made": "chimney"},
    "Verbindungsbruecke": {"building": "bridge"},
    # 22 Objekte landesweit, fast alle Mauerreste in archäologischen Stätten (Amphitheater Lentia)
    "Historische Baute": {"building": "ruins", "ruins": "yes"},
    "Unterirdisches Gebaeude": {"building": "yes", "location": "underground", "layer": "-1"},
    "Lueftungsschacht": {"man_made": "ventilation_shaft"},
}
NUTZUNG = {
    "Gasthof abgelegen": {"amenity": "restaurant"},
    "Reservoir": {"man_made": "reservoir_covered"},
    "Parkhaus": {"amenity": "parking", "parking": "multi-storey"},
    "Stadion": {"leisure": "stadium"},
    "Schiessstand": {"leisure": "sports_centre", "sport": "shooting"},
    "Observatorium": {"man_made": "observatory"},
    "Aussichtsturm": {"tower:type": "observation", "tourism": "viewpoint"},
    "Sporthalle": {"leisure": "sports_hall"},
}


BUILDING_POI_KEYS = ("amenity", "tourism", "leisure", "sport", "parking", "tower:type", "man_made", "barrier", "location")
# Gebäudeart für Footprints, deren Objektart sonst nur man_made/barrier liefert
BUILDING_FALLBACK = {"Lagertank": "storage_tank", "Turm": "tower", "Hochkamin": "chimney",
                     "Lueftungsschacht": "ventilation_shaft"}


BUILDING_SIMPLIFY_M = 0.2
# Footprints, die keine Gebäude sind (Review 2): grosse Mauern, v. a. Burg- und Ruinenmauern
# (landesweit 11 422, davon 3804 in einem Historischen Areal). Kein building-Tag, sonst zeichnet der
# Stil sie als schwarzes Haus (Burgruine Helfenberg).
WALL_FOOTPRINTS = {"Mauer gross", "Mauer gross gedeckt"}
# Historische Areale, deren Mauern als Ruine gelten (Namensheuristik aus pois.historic_tags)
RUIN_HISTORIC = {"ruins", "archaeological_site"}


def _historic_areas(area: Area):
    """Historische Areale im Gebiet: (STRtree, historic-Wert je Areal) aus der Namensheuristik."""
    from .pois import historic_tags
    df = read_layer(TLM_GPKG, "tlm_areale_nutzungsareal", area, columns=["objektart", "name"],
                    where="objektart = 'Historisches Areal'")
    hist = [historic_tags(first_name(n)[0] or "").get("historic", "yes") for n in df["name"]]
    return shapely.STRtree(shapely.force_2d(df.geometry.values)), hist


def wall_tags(oa: str, hist: str | None) -> dict:
    t = {"barrier": "wall", "area": "yes", "swisstopo:mauer": "gross"}
    if oa == "Mauer gross gedeckt":
        t["covered"] = "yes"
    if hist:
        t["swisstopo:historisches_areal"] = hist
        if hist in RUIN_HISTORIC:
            t["ruins"] = "yes"
    return t


def add_buildings(b, area: Area) -> None:
    L = "tlm_bauten_gebaeude_footprint"
    df = read_layer(TLM_GPKG, L, area, columns=["uuid", "objektart", "name", "nutzung"])
    # swissTLM3D zerlegt gerade Wände in gleich lange Stücke (Zwischenpunkte alle 3–5 m). mkgmap
    # rundet jeden Punkt auf das Garmin-Raster (Auflösung 24: 1,6 × 2,4 m), aus den Zwischenpunkten
    # wird ein Zickzack („zittrige“ Gebäude, Review 1). Kollineare Punkte vorab in LV95 entfernen;
    # 0,2 m lässt alle Ecken stehen.
    geoms = clip_wgs84(shapely.simplify(shapely.force_2d(df.geometry.values), BUILDING_SIMPLIFY_M), area)
    oas = df["objektart"].tolist()
    nut = df["nutzung"].tolist()
    names = df["name"].tolist()
    uu = df["uuid"].tolist()
    hist_at = {}
    special = [i for i, oa in enumerate(oas) if oa in WALL_FOOTPRINTS or oa == "Historische Baute"]
    if special:
        tree, hist = _historic_areas(area)
        si, ai = tree.query(shapely.force_2d(df.geometry.values[special]), predicate="intersects")
        for x, y in zip(si, ai):
            hist_at.setdefault(special[x], hist[y])
    for i, g in enumerate(geoms):
        if g is None or g.is_empty:
            continue
        t = _base(L, oas[i], uu[i])
        if oas[i] in WALL_FOOTPRINTS:
            t.update(wall_tags(oas[i], hist_at.get(i)))
            b.add_area(g, t)
            continue
        t.update(BUILDINGS.get(oas[i], {"building": "yes"}))
        if i in hist_at:
            t["swisstopo:historisches_areal"] = hist_at[i]
        n = val(nut[i])
        if n:
            t["swisstopo:nutzung"] = n
            t.update(NUTZUNG.get(n, {}))
        # POI-Tags und Namen nur am POI-Knoten (pois.py), nicht an jedem Footprint. Sonst macht
        # mkgmap mit --add-pois-to-areas aus jedem Footprint eines Gebäudekomplexes einen POI.
        for k in BUILDING_POI_KEYS:
            t.pop(k, None)
        t.pop("area", None)
        t.setdefault("building", BUILDING_FALLBACK.get(oas[i], "yes"))
        nm, _ = first_name(names[i])
        if nm:
            t["swisstopo:name"] = nm
        b.add_area(g, t)


# --- Bauten --------------------------------------------------------------------
def add_structures(b, area: Area) -> None:
    lines = {
        "tlm_bauten_mauer": {"Mauer": {"barrier": "wall"}},
        "tlm_bauten_verbauung": {
            "Trockenmauer": {"barrier": "wall", "wall": "dry_stone"},
            "Schutzverbauung": {"man_made": "avalanche_protection"},
            "Gewaesserverbauung": {"man_made": "embankment"},
        },
        "tlm_bauten_leitung": {"Stromleitung": {"power": "line"}},
        "tlm_bauten_sportbaute_lin": {
            "Laufbahn": {"leisure": "track"},
            "Scheibenstand": {"man_made": "yes"},
            "Skisprungschanze": {"piste:type": "ski_jump"},
            "Rodelbahn": {"piste:type": "sled"},
            "Bobbahn": {"piste:type": "sled"},
        },
        "tlm_bauten_verkehrsbaute_lin": {"Hafensteg": {"man_made": "pier"}},
    }
    areas = {
        "tlm_bauten_staubaute": {
            "Staumauer": {"waterway": "dam", "area": "yes"},
            "Staudamm": {"waterway": "dam", "area": "yes"},
            "Wehr": {"waterway": "weir", "area": "yes"},
            "Schutzdamm": {"man_made": "dyke", "area": "yes"},
            "Wasserbecken": {"natural": "water", "water": "basin"},
        },
        "tlm_bauten_sportbaute_ply": {"Sportplatz": {"leisure": "pitch"}},
        "tlm_bauten_verkehrsbaute_ply": {
            "Perron": {"railway": "platform", "area": "yes"},
            "Rollfeld Hartbelag": {"aeroway": "runway", "area": "yes", "surface": "paved"},
            "Rollfeld Gras": {"aeroway": "runway", "area": "yes", "surface": "grass"},
            "Graspiste": {"aeroway": "runway", "area": "yes", "surface": "grass"},
            "Hartbelagpiste": {"aeroway": "runway", "area": "yes", "surface": "paved"},
            "Schleuse": {"waterway": "lock_gate", "lock": "yes", "area": "yes"},
        },
    }
    for L, mapping in lines.items():
        df = read_layer(TLM_GPKG, L, area)
        geoms = clip_wgs84(df.geometry.values, area)
        has_name = "name" in df.columns
        for i, g in enumerate(geoms):
            if g is None or g.is_empty:
                continue
            oa = df["objektart"].iloc[i]
            t = _base(L, oa, df["uuid"].iloc[i])
            t.update(mapping.get(oa, {}))
            if has_name:
                t["name"], _ = first_name(df["name"].iloc[i])
            if L == "tlm_bauten_leitung":
                t["swisstopo:netzebene"] = val(df["netzebene"].iloc[i])
            b.add_line(g, t)
    for L, mapping in areas.items():
        df = read_layer(TLM_GPKG, L, area)
        geoms = clip_wgs84(df.geometry.values, area)
        has_name = "name" in df.columns
        for i, g in enumerate(geoms):
            if g is None or g.is_empty:
                continue
            oa = df["objektart"].iloc[i]
            t = _base(L, oa, df["uuid"].iloc[i])
            t.update(mapping.get(oa, {}))
            if has_name:
                t["name"], _ = first_name(df["name"].iloc[i])
            b.add_area(g, t)

    L = "tlm_bauten_versorgungsbaute_pkt"
    df = read_layer(TLM_GPKG, L, area)
    geoms = clip_wgs84(df.geometry.values, area)
    pmap = {"Antenne gross": {"man_made": "mast"},
            "Windturbine": {"power": "generator", "generator:source": "wind"}}
    for i, g in enumerate(geoms):
        oa = df["objektart"].iloc[i]
        if g is None or g.is_empty or oa not in pmap:
            continue
        t = _base(L, oa, df["uuid"].iloc[i])
        t.update(pmap[oa])
        b.add_point(g.x, g.y, t)


# --- Einzelbäume ------------------------------------------------------------------
TREE_EXCLUDE = {"Wald", "Wald offen", "Gebueschwald", "Gehoelzflaeche"}


def add_trees(b, area: Area, lc_df, settlements, spacing: float = 20.0,
              spacing_settlement: float = 80.0) -> None:
    """Einzelbäume ausserhalb von Wald/Gebüsch, ausgedünnt auf etwa die LK25-Dichte.

    Ein Baum je Rasterzelle: ausserhalb der Siedlungskerne 20 m, innerhalb 80 m. Geeicht an den
    LK-Referenzzählungen der Stil-QA (fünf Ausschnitte 1:25 000: 6 264 gegenüber 6 578 LK-Bäumen).
    Baumreihen und Obstgärten werden so nicht vollständig aufgelöst.
    """
    L = "tlm_bb_einzelbaum"
    df = read_layer(TLM_GPKG, L, area, columns=["uuid", "objektart"])
    lv = shapely.force_2d(df.geometry.values)
    xy = shapely.get_coordinates(lv)
    woods = lc_df.geometry.values[lc_df["objektart"].isin(TREE_EXCLUDE).values]
    inside = np.zeros(len(lv), dtype=bool)
    if len(woods):
        tree = shapely.STRtree(woods)
        ip, _ = tree.query(lv, predicate="intersects")
        inside[np.unique(ip)] = True
    in_settl = np.zeros(len(lv), dtype=bool)
    if settlements:
        cores = shapely.union_all([shapely.Polygon(p.exterior) for p in settlements])
        in_settl = shapely.contains_xy(cores, xy[:, 0], xy[:, 1])
    cells = {}
    for i in np.where(~inside)[0].tolist():
        s = spacing_settlement if in_settl[i] else spacing
        k = (s, int(xy[i, 0] // s), int(xy[i, 1] // s))
        cells.setdefault(k, i)
    sel = np.array(sorted(cells.values()), dtype=int)
    pts = clip_wgs84(lv[sel], area) if len(sel) else []
    n = 0
    for p in pts:
        if p is None or p.is_empty:
            continue
        b.add_point(p.x, p.y, {"natural": "tree", "source": "swisstopo",
                                "swisstopo:layer": L, "swisstopo:objektart": "Einzelbaum"})
        n += 1
    log.info("Einzelbäume: %d gelesen, %d im Wald/Gebüsch, %d in Siedlungskernen, %d übernommen",
             len(lv), int(inside.sum()), int(in_settl.sum()), n)


# --- Generalisierte Siedlungsflächen -------------------------------------------------
def settlement_polygons(area: Area, grow=30.0, shrink=20.0, simplify=10.0,
                        min_area=30_000.0, min_hole=10_000.0) -> list:
    """Generalisierte Siedlungsflächen in LV95 (siehe add_settlements)."""
    import time
    t0 = time.time()
    df = read_layer(TLM_GPKG, "tlm_bauten_gebaeude_footprint", area, columns=["objektart"])
    df = df[~df["objektart"].isin(["Unterirdisches Gebaeude", "Lueftungsschacht", "Mauer gross",
                                   "Mauer gross gedeckt"])]
    g = shapely.force_2d(df.geometry.values)
    g = shapely.buffer(shapely.make_valid(g), grow, quad_segs=2)
    u = shapely.union_all(g, grid_size=0.5)
    u = shapely.buffer(u, -shrink, quad_segs=2)
    u = shapely.simplify(u, simplify, preserve_topology=True)
    polys = []
    for p in shapely.get_parts(u):
        if p.geom_type != "Polygon" or p.area < min_area:
            continue
        holes = [r for r in p.interiors if shapely.Polygon(r).area >= min_hole]
        polys.append(shapely.Polygon(p.exterior, holes))
    log.info("Siedlungsflächen berechnet: %d in %.0f s", len(polys), time.time() - t0)
    return polys


def add_settlements(b, area: Area, polys) -> None:
    """Siedlungsflächen aus Gebäuden für grobe Zoomstufen (Wunsch style-typ).

    Gebäude (LV95) +30 m puffern, vereinigen, −20 m puffern, auf 10 m vereinfachen, Löcher
    < 1 ha füllen, Flächen < 3 ha weglassen. Tags: landuse=residential,
    swisstopo:generalisiert=siedlung.
    """
    if not polys:
        return
    geoms = clip_wgs84(np.array(polys, dtype=object), area)
    n = 0
    for gg in geoms:
        if gg is None or gg.is_empty:
            continue
        n += b.add_area(gg, {"landuse": "residential", "swisstopo:generalisiert": "siedlung",
                             "source": "swisstopo", "swisstopo:layer": "tlm_bauten_gebaeude_footprint"})
    log.info("Siedlungsflächen (generalisiert): %d", n)
