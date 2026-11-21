"""Strassen und Wege aus swissTLM3D (TLM_STRASSE) → OSM highway=* mit Routing-Attributen.

Abbildung siehe docs/daten/tag-schema.md, Abschnitt „Strassen und Wege“.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict

import numpy as np
import shapely

from .admin import AdminLookup, is_in_tags
from .common import TLM_GPKG, Area, clip_wgs84, first_name, int_str, read_layer, read_table, val

log = logging.getLogger("vector")

LAYER = "tlm_strassen_strasse"

# Rangfolge der Klassen für die Vererbung bei objektart=Verbindung
RANK = {
    "motorway": 13, "motorway_link": 12, "trunk": 11, "primary": 10, "secondary": 9,
    "tertiary": 8, "unclassified": 7, "residential": 6, "service": 5, "pedestrian": 4,
    "track": 3, "path": 2, "steps": 1,
}
WIDTH_ROADS = {"10m Strasse", "8m Strasse", "6m Strasse", "4m Strasse", "3m Strasse"}
FOOT_CLASSES = {"path", "footway", "track", "pedestrian", "steps"}
SAC = {"Wanderweg": "hiking", "Bergwanderweg": "mountain_hiking", "Alpinwanderweg": "alpine_hiking"}
STAIR_KUNSTBAUTE = {"Treppe", "Bruecke mit Treppe", "Unterfuehrung mit Treppe"}
TRUNK_ROUTES = {"HLS Bund", "HLS Kanton", "Nationalstrasse"}
PRIMARY_ROUTES = {"Hauptstrasse A"}
SECONDARY_ROUTES = {"Hauptstrasse B", "Hauptstrasse C"}


def _uuid(u) -> str:
    return str(u).strip("{}").upper() if u is not None else ""


def load_routes(uuids: set[str]) -> dict[str, list[tuple[str, str]]]:
    """Strassen-UUID → [(routen-objektart, routennummer)]."""
    link = read_table(TLM_GPKG, "tlm_strassen_strassenroute_strasse")
    route = read_table(TLM_GPKG, "tlm_strassen_strassenroute", ["uuid", "objektart", "routennummer"])
    rinfo = {_uuid(u): (oa, val(nr)) for u, oa, nr in zip(route["uuid"], route["objektart"], route["routennummer"])}
    out: dict[str, list] = defaultdict(list)
    for s, r in zip(link["tlm_strasse_uuid"], link["tlm_strassenroute_uuid"]):
        su = _uuid(s)
        if su in uuids and _uuid(r) in rinfo:
            out[su].append(rinfo[_uuid(r)])
    return out


def load_esids(uuids: set[str]) -> dict[str, list[str]]:
    link = read_table(TLM_GPKG, "tlm_strassen_strassenname_strasse")
    names = read_table(TLM_GPKG, "tlm_strassen_strassenname", ["uuid", "esid"])
    esid = {_uuid(u): int_str(e) for u, e in zip(names["uuid"], names["esid"])}
    out: dict[str, list] = defaultdict(list)
    for s, n in zip(link["tlm_strasse_uuid"], link["tlm_strassenname_uuid"]):
        su = _uuid(s)
        if su in uuids:
            e = esid.get(_uuid(n))
            if e and e not in out[su]:
                out[su].append(e)
    return out


def base_class(r: dict, routes: list) -> tuple[str | None, dict]:
    """Highway-Klasse ohne Vererbung; None für objektart=Verbindung (später)."""
    oa = r["objektart"]
    extra: dict = {}
    route_types = {rt for rt, _ in routes}
    if oa == "Autobahn":
        return "motorway", {"oneway": "yes"}
    if oa in ("Ausfahrt", "Einfahrt"):
        return "motorway_link", {"oneway": "yes"}
    if oa == "Autostrasse":
        return "trunk", {"motorroad": "yes"}
    if oa in ("Raststaette", "Zufahrt"):
        return "service", extra
    if oa == "Dienstzufahrt":
        return "service", {"access": "no", "service": "emergency_access"}
    if oa == "Verbindung":
        return None, extra
    if oa == "Faehre":
        return "ferry", extra
    if oa in WIDTH_ROADS:
        vb = r["verkehrsbedeutung"]
        if route_types & TRUNK_ROUTES:
            return "trunk", extra
        if route_types & PRIMARY_ROUTES or vb == "Hochleistungsstrasse":
            return "primary", extra
        if route_types & SECONDARY_ROUTES or vb == "Durchgangsstrasse":
            return "secondary", extra
        if vb == "Verbindungsstrasse" or r["eigentuemer"] in ("Kanton", "Bund"):
            return "tertiary", extra
        if oa in ("10m Strasse", "8m Strasse"):
            return "tertiary", extra
        if oa == "6m Strasse":
            return "unclassified", extra
        if oa == "4m Strasse":
            return "residential", extra
        # 3m Strasse
        if r["belagsart"] == "Natur":
            return "track", {"tracktype": "grade2"}
        return "service", extra
    if oa == "2m Weg":
        if r["befahrbarkeit"] == "Wahr":
            return "track", {"tracktype": "grade3" if r["belagsart"] == "Natur" else "grade1"}
        return "path", extra
    if oa == "1m Weg":
        return "path", extra
    if oa in ("1m Wegfragment", "2m Wegfragment"):
        return "path", {"trail_visibility": "intermediate"}
    if oa == "Markierte Spur":
        return "path", {"trail_visibility": "bad"}
    if oa == "Platz":
        if r["verkehrsbeschraenkung"] not in (None, "Keine"):
            return "pedestrian", extra
        return "service", extra
    log.warning("unbekannte Strassen-objektart %r", oa)
    return "road", extra


def inherit_connections(cls: list, geoms_lv95: np.ndarray, oneway: list) -> None:
    """objektart=Verbindung: niedrigere der besten Klassen an beiden Enden übernehmen."""
    ends: dict[tuple, list[int]] = defaultdict(list)
    endpoints = []
    for i, g in enumerate(geoms_lv95):
        c = shapely.get_coordinates(g)
        a = (round(c[0][0], 2), round(c[0][1], 2))
        b = (round(c[-1][0], 2), round(c[-1][1], 2))
        endpoints.append((a, b))
        ends[a].append(i)
        ends[b].append(i)
    todo = [i for i, c in enumerate(cls) if c is None]
    inv = {v: k for k, v in RANK.items()}
    for it in range(12):
        final = it >= 10  # in den letzten Runden auch halb bekannte Enden akzeptieren
        changed = False
        for i in todo:
            if cls[i] is not None:
                continue
            best, pending = [], False
            for p in endpoints[i]:
                others = [j for j in ends[p] if j != i]
                if not others:
                    continue  # offenes Ende
                known = [RANK.get(cls[j], 0) for j in others if cls[j] is not None]
                if not known:
                    pending = True
                    continue
                best.append(max(known))
            if not best or (pending and not final):
                continue
            c = inv.get(min(best), "service")
            if c == "steps":
                c = "path"
            cls[i] = c
            if c in ("motorway", "motorway_link"):
                oneway[i] = True
            changed = True
        if not changed and final:
            break
    for i in todo:
        if cls[i] is None:
            cls[i] = "service"


def add_roads(builder, area: Area, admin: AdminLookup, routes_csv=None):
    df = read_layer(TLM_GPKG, LAYER, area)
    df = df.reset_index(drop=True)
    uuids = [_uuid(u) for u in df["uuid"]]
    uset = set(uuids)
    routes = load_routes(uset)
    esids = load_esids(uset)

    cols = [
        "objektart", "kunstbaute", "wanderwege", "befahrbarkeit", "stufe", "richtungsgetrennt",
        "belagsart", "kreisel", "verkehrsbeschraenkung", "eigentuemer", "verkehrsbedeutung",
        "name", "strassenname",
    ]
    recs = [
        {c: val(v) for c, v in zip(cols, row)}
        for row in zip(*(df[c].tolist() for c in cols))
    ]
    geoms = shapely.force_2d(df.geometry.values)

    cls: list = []
    extras: list = []
    oneway: list = []
    for r, u in zip(recs, uuids):
        c, ex = base_class(r, routes.get(u, []))
        cls.append(c)
        extras.append(ex)
        oneway.append(ex.get("oneway") == "yes" or r["richtungsgetrennt"] == "Wahr")
    inherit_connections(cls, geoms, oneway)
    geoms = orient_oneway_connections(recs, geoms, oneway)

    # Gemeinde/Kanton für benannte Strassen (Mittelpunkt der Linie)
    mids = shapely.line_interpolate_point(geoms, 0.5, normalized=True)
    gem, kt, cc = admin.lookup_points(mids)

    wgs = clip_wgs84(geoms, area)
    n = 0
    index = RoadIndex()
    all_tags = [
        road_tags(r, cls[i], extras[i], oneway[i], routes.get(uuids[i], []), esids.get(uuids[i], []))
        for i, r in enumerate(recs)
    ]
    propagate_motorway_refs(all_tags, geoms)
    from . import netz
    netz.add_tags(all_tags, recs, geoms, area.lv95_bbox())
    if routes_csv:
        from collections import Counter
        from . import routes_attr
        rmap = routes_attr.load(routes_csv)
        rstats = Counter()
        for i, u in enumerate(uuids):
            r = rmap.get(u)
            if r is not None:
                all_tags[i]["swisstopo:uuid"] = u
                routes_attr.apply(all_tags[i], r, rstats)
        log.info("Routenattribute: %s", dict(rstats))
    for i, r in enumerate(recs):
        g = wgs[i]
        if g is None or g.is_empty:
            continue
        tags = all_tags[i]
        tags["swisstopo:uuid"] = uuids[i]
        tags.update(is_in_tags(gem[i], kt[i], cc[i]))
        first = len(builder.ways)
        n += builder.add_line(g, tags)
        if tags.get("highway") and len(builder.ways) > first:
            index.add(geoms[i], tags.get("name"), tags["highway"], range(first, len(builder.ways)))
    log.info("Strassen: %d Wege", n)

    add_road_points(builder, area)
    add_ferries(builder, area)
    index.finish()
    # Kandidaten für Platz-/Kreisel-Namenpunkte (extras.add_square_points)
    index.platz = [
        (first_name(r["strassenname"])[0], geoms[i])
        for i, r in enumerate(recs)
        if r["strassenname"] and (r["objektart"] == "Platz" or r["kreisel"] == "Wahr")
    ]
    return index


def orient_oneway_connections(recs, geoms, oneway):
    """Einbahn-Verbindungsstücke (objektart=Verbindung) in Fahrrichtung drehen.

    Bei Autobahn, Rampen und richtungsgetrennten Strassen ist die Digitalisierrichtung die
    Fahrrichtung (geprüft). Bei den kurzen Verbindungsstücken nicht immer: Ein Stück, an dessen
    Anfang keine Einbahn ankommt, aber eine beginnt, und an dessen Ende eine Einbahn endet,
    ist verkehrt herum.
    """
    geoms = geoms.copy()
    conn = [i for i, r in enumerate(recs) if r["objektart"] == "Verbindung" and oneway[i]]
    if not conn:
        return geoms
    k = lambda c: (round(c[0], 2), round(c[1], 2))
    flipped = 0
    for _ in range(5):
        starts, ends = defaultdict(list), defaultdict(list)
        for i, g in enumerate(geoms):
            if oneway[i]:
                c = shapely.get_coordinates(g)
                starts[k(c[0])].append(i)
                ends[k(c[-1])].append(i)
        changed = False
        for i in conn:
            c = shapely.get_coordinates(geoms[i])
            a, b = k(c[0]), k(c[-1])
            into_a = [j for j in ends[a] if j != i]
            out_a = [j for j in starts[a] if j != i]
            into_b = [j for j in ends[b] if j != i]
            out_b = [j for j in starts[b] if j != i]
            # verkehrt: am Anfang kommt nichts an, dort beginnt aber eine Einbahn, und am Ende
            # endet eine Einbahn (z. B. die Autobahn, die dort auch weiterlaufen kann)
            if not into_a and out_a and into_b and (not out_b or len(into_b) >= len(out_b)):
                geoms[i] = shapely.reverse(geoms[i])
                flipped += 1
                changed = True
        if not changed:
            break
    log.info("Einbahn-Verbindungsstücke umgedreht: %d", flipped)
    return geoms


def propagate_motorway_refs(all_tags: list[dict], geoms_lv95) -> None:
    """Autobahnstücke ohne Strassenroute übernehmen ref/nat_ref/int_ref vom Nachbarstück."""
    ends: dict[tuple, list[int]] = defaultdict(list)
    mw = [i for i, t in enumerate(all_tags) if t.get("highway") == "motorway"]
    pts = {}
    for i in mw:
        c = shapely.get_coordinates(geoms_lv95[i])
        a = (round(c[0][0], 2), round(c[0][1], 2))
        b = (round(c[-1][0], 2), round(c[-1][1], 2))
        pts[i] = (a, b)
        ends[a].append(i)
        ends[b].append(i)
    n = 0
    for _ in range(50):
        changed = False
        for i in mw:
            if all_tags[i].get("ref"):
                continue
            for p in pts[i]:
                src = [j for j in ends[p] if j != i and all_tags[j].get("ref")]
                if src:
                    for k in ("ref", "nat_ref", "int_ref", *SHIELD_KEYS):
                        if all_tags[src[0]].get(k):
                            all_tags[i][k] = all_tags[src[0]][k]
                    changed = True
                    n += 1
                    break
        if not changed:
            break
    log.info("Autobahn-refs übernommen: %d", n)


class RoadIndex:
    """Strassen in LV95 mit Namen und Weg-Indizes im OsmBuilder (für die Adresszuordnung)."""

    def __init__(self):
        self.geoms, self.names, self.classes, self.ways = [], [], [], []

    def add(self, g, name, hw, ways):
        self.geoms.append(g)
        self.names.append(name)
        self.classes.append(hw)
        self.ways.append(list(ways))

    def finish(self):
        self.geoms = np.array(self.geoms, dtype=object)
        self.tree = shapely.STRtree(self.geoms)


def road_tags(r, hw, extra, is_oneway, routes, esids) -> dict:
    t: dict = {"source": "swisstopo", "swisstopo:layer": LAYER, "swisstopo:objektart": r["objektart"]}
    for k in ("kunstbaute", "belagsart", "befahrbarkeit", "verkehrsbeschraenkung", "verkehrsbedeutung",
              "eigentuemer", "richtungsgetrennt", "kreisel"):
        if r[k] is not None:
            t[f"swisstopo:{k}"] = r[k]
    if r["stufe"] is not None:
        t["swisstopo:stufe"] = int_str(r["stufe"])
    if r["wanderwege"]:
        t["swisstopo:wanderweg"] = r["wanderwege"]
        t["hiking"] = "yes"

    if hw == "ferry":
        t.update({"route": "ferry", "foot": "yes", "bicycle": "yes"})
        name, alt = first_name(r["name"])
        t["name"] = name
        return t

    kb = r["kunstbaute"]
    if kb in STAIR_KUNSTBAUTE and hw in FOOT_CLASSES:
        hw = "steps"
    t["highway"] = hw
    t.update({k: v for k, v in extra.items() if k != "oneway"})
    if is_oneway:
        t["oneway"] = "yes"
    if r["kreisel"] == "Wahr":
        t["junction"] = "roundabout"
        t.pop("oneway", None)  # bei Kreiseln implizit

    # Belag
    if r["belagsart"] == "Hart":
        t["surface"] = "paved"
    elif r["belagsart"] == "Natur":
        t["surface"] = "unpaved"

    # Kunstbauten und Ebenen
    stufe = int(float(r["stufe"])) if r["stufe"] is not None else 0
    if kb in ("Bruecke", "Steg", "Bruecke mit Treppe"):
        t["bridge"] = "yes"
        t["layer"] = str(max(stufe, 1))
    elif kb == "Gedeckte Bruecke":
        t["bridge"] = "covered"
        t["layer"] = str(max(stufe, 1))
    elif kb == "Bruecke mit Galerie":
        t["bridge"] = "yes"
        t["covered"] = "yes"
        t["layer"] = str(max(stufe, 1))
    elif kb in ("Tunnel", "Unterfuehrung", "Unterfuehrung mit Treppe"):
        t["tunnel"] = "yes"
        t["layer"] = str(min(stufe, -1))
    elif kb == "Galerie":
        t["tunnel"] = "avalanche_protector"
        if stufe:
            t["layer"] = str(stufe)
    elif kb == "in/auf Gebaeude":
        t["covered"] = "yes"
        if stufe:
            t["layer"] = str(stufe)
    elif kb == "Furt":
        t["ford"] = "yes"
    elif stufe:
        t["layer"] = str(stufe)

    # Zugang (Annahmen siehe docs/daten/tag-schema.md)
    vb = r["verkehrsbeschraenkung"]
    oa = r["objektart"]
    if vb == "Allgemeine Verkehrsbeschraenkung":
        if oa in ("10m Strasse", "8m Strasse", "6m Strasse", "4m Strasse"):
            t["motor_vehicle"] = "destination"
        else:
            t["motor_vehicle"] = "no"
    elif vb in ("Allgemeines Fahrverbot", "Gesperrt"):
        t["motor_vehicle"] = "no"
    elif vb == "Zeitlich geregelt":
        t["motor_vehicle"] = "destination"
    elif vb in ("Militaerstrasse", "Panzerpiste", "Rennstrecke", "Teststrecke"):
        t["access"] = "private"
    elif vb == "Gesicherte Kletterpartie":
        t["via_ferrata"] = "yes"
        t["bicycle"] = "no"
    if r["befahrbarkeit"] == "Falsch":
        t["motor_vehicle"] = "no"
    if hw in ("path", "steps", "pedestrian", "track") and "motor_vehicle" not in t:
        # Wege: keine Motorfahrzeuge. Ausnahme: 3m-Naturstrassen (track) ohne Beschränkung.
        # 2m-Wege sind auch mit befahrbarkeit=Wahr nur Land-/Forstwirtschaftswege (Annahme).
        if oa == "3m Strasse" and r["befahrbarkeit"] != "Falsch":
            pass
        else:
            t["motor_vehicle"] = "no"
            if hw == "track":
                t["agricultural"] = "yes"
                t["forestry"] = "yes"
    if hw in ("motorway", "motorway_link") or t.get("motorroad") == "yes":
        t["bicycle"] = "no"
        t["foot"] = "no"

    # Velo auf Wegen nach Breite/Belag/Schwierigkeit (Annahme)
    if "bicycle" not in t:
        if hw == "steps":
            t["bicycle"] = "no"
        elif hw == "track" or oa == "2m Weg":
            t["bicycle"] = "yes"
        elif oa in ("1m Wegfragment", "2m Wegfragment", "Markierte Spur"):
            t["bicycle"] = "no"
        elif oa == "1m Weg":
            if r["wanderwege"] in ("Bergwanderweg", "Alpinwanderweg") or r["belagsart"] != "Hart":
                t["bicycle"] = "no"
            else:
                t["bicycle"] = "yes"

    # Wanderwege
    if r["wanderwege"] in SAC and hw in FOOT_CLASSES:
        t["sac_scale"] = SAC[r["wanderwege"]]
    if vb == "Gesicherte Kletterpartie" and hw in FOOT_CLASSES:
        if t.get("sac_scale") in (None, "hiking", "mountain_hiking", "demanding_mountain_hiking"):
            t["sac_scale"] = "alpine_hiking"

    # Namen
    sname, _ = first_name(r["strassenname"])
    oname, oalt = first_name(r["name"])
    if sname:
        t["name"] = sname
    if oname:
        if t.get("bridge"):
            t["bridge:name"] = oname
        elif t.get("tunnel"):
            t["tunnel:name"] = oname
        if not sname:
            t["name"] = oname
    if esids:
        t["swisstopo:esid"] = ";".join(esids)

    # Routennummern
    refs, eref, nref = [], [], []
    for rt, nr in routes:
        if not nr:
            continue
        if rt == "Europastrasse":
            eref.append(nr)
        elif rt == "Nationalstrasse":
            if nr not in nref:
                nref.append(nr)
        elif nr not in refs:
            refs.append(nr)
    if refs:
        t["ref"] = ";".join(sorted(refs, key=lambda s: (not s.startswith("A"), s)))
    if nref:
        t["nat_ref"] = ";".join(sorted(nref))
        if not refs:
            t["ref"] = t["nat_ref"]
    if eref:
        t["int_ref"] = ";".join(sorted(set(eref)))
    t.update(shield_tags(routes))
    return t


SHIELD_KEYS = ("swisstopo:shield", "swisstopo:shield_autobahn", "swisstopo:shield_hauptstrasse",
               "swisstopo:shield_europa", "swisstopo:hauptstrasse_nr_intern")
_RX_A = re.compile(r"^A(\d+[a-z]?)")
_RX_H = re.compile(r"^(\d+[a-z]?)")


def shield_tags(routes) -> dict:
    """Nummern je Schildart für eigene Garmin-Shields (Review 1, Punkt 5).

    Schweizer Signalisation: Autobahn/Autostrasse rot „A1“, Hauptstrasse blau „7“, Europastrasse
    grün „E60“. Signalisiert sind nur die Hauptstrassen A (1–30); die Nummern der Hauptstrassen B/C
    (100–599) sind Verwaltungsnummern und stehen in swisstopo:hauptstrasse_nr_intern. TLM-Varianten werden auf die signalisierte Nummer gekürzt: A1H/A1L/A1R → A1,
    112.1 → 112. Nationalstrassen-Nummern (N1) sind Verwaltungsnummern und bleiben nur in nat_ref.
    `swisstopo:shield` nennt die führende Schildart (autobahn > hauptstrasse > europa).
    """
    a, h, e, intern = [], [], [], []
    for rt, nr in routes:
        if not nr:
            continue
        nr = str(nr).strip()
        if rt in ("HLS Bund", "HLS Kanton"):
            m = _RX_A.match(nr)
            if m and "A" + m.group(1) not in a:
                a.append("A" + m.group(1))
        elif rt == "Hauptstrasse A":
            m = _RX_H.match(nr)
            if m and m.group(1) not in h:
                h.append(m.group(1))
        elif rt in ("Hauptstrasse B", "Hauptstrasse C"):
            m = _RX_H.match(nr)
            if m and m.group(1) not in intern:
                intern.append(m.group(1))
        elif rt == "Europastrasse" and nr not in e:
            e.append(nr)
    t = {}
    key = lambda v: (len(v), v)  # noqa: E731  (A2 vor A13)
    if a:
        t["swisstopo:shield_autobahn"] = ";".join(sorted(a, key=key))
    if h:
        t["swisstopo:shield_hauptstrasse"] = ";".join(sorted(h, key=key))
    if e:
        t["swisstopo:shield_europa"] = ";".join(sorted(e, key=key))
    if t:
        t["swisstopo:shield"] = "autobahn" if a else ("hauptstrasse" if h else "europa")
    if intern:
        t["swisstopo:hauptstrasse_nr_intern"] = ";".join(sorted(intern, key=key))
    return t


def add_road_points(builder, area: Area) -> None:
    """Durchfahrtssperren (Barrieren) und Autobahnanschlüsse auf die Strassenknoten legen."""
    info = read_layer(TLM_GPKG, "tlm_strassen_strasseninfo", area,
                      where="objektart IN ('Durchfahrtssperre', 'Zollamt 24h 24h', 'Zollamt 24h eingeschraenkt', 'Zollamt eingeschraenkt')")
    pts = clip_wgs84(info.geometry.values, area)
    nb = 0
    for g, oa, uu in zip(pts, info["objektart"], info["uuid"]):
        if g is None or g.is_empty:
            continue
        if builder.has_shared_node(g.x, g.y) is None:
            continue
        if oa == "Durchfahrtssperre":
            tags = {"barrier": "bollard"}
        else:
            tags = {"barrier": "border_control"}
        tags.update({"source": "swisstopo", "swisstopo:layer": "tlm_strassen_strasseninfo",
                     "swisstopo:objektart": oa, "swisstopo:uuid": _uuid(uu)})
        builder.add_point(g.x, g.y, tags, merge=True)
        nb += 1
    log.info("Barrieren/Zoll auf Strassenknoten: %d", nb)

    ae = read_layer(TLM_GPKG, "tlm_strassen_aus_einfahrt", area)
    pts = clip_wgs84(ae.geometry.values, area)
    nj = 0
    for g, oa, name, nr in zip(pts, ae["objektart"], ae["name"], ae["nummer"]):
        if g is None or g.is_empty or oa == "Einfahrt":
            continue
        nm, _ = first_name(name)
        # ref = Anschlussnummer (OSM-Standard); swisstopo:ausfahrt_nr zusätzlich, damit der Stil sie
        # nicht mit Strassennummern verwechselt (Review 1: „24“ und „7“ nicht unterscheidbar)
        tags = {"highway": "motorway_junction", "name": nm, "ref": int_str(nr),
                "swisstopo:ausfahrt_nr": int_str(nr),
                "source": "swisstopo", "swisstopo:layer": "tlm_strassen_aus_einfahrt",
                "swisstopo:objektart": oa}
        builder.add_point(g.x, g.y, tags, merge=builder.has_shared_node(g.x, g.y) is not None)
        nj += 1
    log.info("Autobahnanschlüsse: %d", nj)


def add_ferries(builder, area: Area) -> None:
    df = read_layer(TLM_GPKG, "tlm_oev_schifffahrt", area)
    geoms = clip_wgs84(df.geometry.values, area)
    for g, oa, name in zip(geoms, df["objektart"], df["name"]):
        if g is None or g.is_empty:
            continue
        nm, _ = first_name(name)
        tags = {"route": "ferry", "name": nm, "foot": "yes", "bicycle": "yes",
                "source": "swisstopo", "swisstopo:layer": "tlm_oev_schifffahrt",
                "swisstopo:objektart": oa}
        if oa == "Autofaehre":
            tags["motor_vehicle"] = "yes"
        builder.add_line(g, tags)
