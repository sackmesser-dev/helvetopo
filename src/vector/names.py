"""Namen aus swissNAMES3D: Gipfel, Pässe, Orte, Flurnamen, Einzelobjekte, Flächennamen."""

from __future__ import annotations

import logging
from collections import defaultdict

import numpy as np
import pyogrio
import shapely

from . import labelclass, peaks
from .admin import AdminLookup, is_in_tags
from .common import NAMES_GPKG, Area, clip_wgs84, int_str, read_layer, val

log = logging.getLogger("vector")

PEAKS = {"Hauptgipfel", "Gipfel", "Alpiner Gipfel", "Felskopf"}
HILLS = {"Haupthuegel", "Huegel"}
PASSES = {"Pass", "Strassenpass"}

POINT_TAGS = {
    "Aussichtspunkt": {"tourism": "viewpoint"},
    "Bildstock": {"historic": "wayside_shrine"},
    "Brunnen": {"amenity": "fountain"},
    "Denkmal": {"historic": "memorial"},
    "Grotte, Hoehle": {"natural": "cave_entrance"},
    "Quelle": {"natural": "spring"},
    "Wasserfall": {"waterway": "waterfall"},
    "Landesgrenzstein": {"historic": "boundary_stone"},
    "Gebaeude": {"building": "yes"},
    "Offenes Gebaeude": {"building": "roof"},
    "Kapelle": {"amenity": "place_of_worship", "building": "chapel"},
    "Sakrales Gebaeude": {"amenity": "place_of_worship"},
    "Turm": {"man_made": "tower"},
    "Haltestelle Bahn": {"railway": "station", "public_transport": "station"},
    "Haltestelle Bus": {"highway": "bus_stop", "public_transport": "platform"},
    "Haltestelle Schiff": {"amenity": "ferry_terminal"},
    "Uebrige Bahnen": {"aerialway": "station"},
    "Erratischer Block": {"natural": "stone"},
    "Felsblock": {"natural": "stone"},
    "Flurname swisstopo": {"place": "locality"},
    "Lokalname swisstopo": {"place": "locality"},
    "Pass": {"natural": "saddle", "mountain_pass": "yes"},
    "Strassenpass": {"mountain_pass": "yes"},
}
# Diese Klassen kommen aus swissTLM3D direkt (Strassen-/Bahn-Objekte, POIs in pois.py)
SKIP_CLASSES = {"TLM_AUS_EINFAHRT", "TLM_STRASSENINFO", "TLM_HALTESTELLE", "TLM_GEBAEUDE"}
# Einzelobjekte, die pois.py aus tlm_eo_einzelobjekt nimmt
SKIP_EINZELOBJEKT = {"Gipfelkreuz", "Bildstock", "Brunnen", "Quelle", "Wasserfall", "Denkmal",
                     "Grotte, Hoehle", "Triangulationspyramide"}

AREA_LABELS = {
    "Tal": {"natural": "valley"},
    "Haupttal": {"natural": "valley"},
    "Graben": {"natural": "valley"},
    "Grat": {"natural": "ridge"},
    "Massiv": {"natural": "mountain_range"},
    "Huegelzug": {"natural": "mountain_range"},
    "Gletscher": {"natural": "glacier"},
    "Gebiet": {"place": "region"},
    "Landschaftsname": {"place": "region"},
    "Grossregion": {"place": "region"},
    "Seeteil": {"place": "locality"},
    "See": {"place": "lake"},   # Seename als Punkt (Namenklasse, src/vector/labelclass.py)
}


def place_value(oa: str, ew) -> str:
    if oa == "Ort":
        ew = val(ew) or ""
        if ew == "> 100'000":
            return "city"
        if ew in ("50'000 bis 100'000", "10'000 bis 49'999"):
            return "town"
        if ew in ("2'000 bis 9'999", "1'000 bis 1'999", "100 bis 999"):
            return "village"
        return "hamlet"
    if oa in ("Ortsteil", "Quartier"):
        return "suburb"
    return "neighbourhood"


def _group_names(df):
    """uuid → (Hauptname, weitere Namen, Index der Hauptzeile)."""
    groups = defaultdict(list)
    for i, u in enumerate(df["uuid"].tolist()):
        groups[u].append(i)
    out = {}
    status = df["status"].tolist()
    typ = df["namen_typ"].tolist()
    names = df["name"].tolist()
    for u, idx in groups.items():
        def score(i):
            s = 0 if status[i] == "offiziell" else 1
            t = 0 if typ[i] in ("einfacher Name", "Endonym", "Namenspaar") else 1
            return (s, t, i)
        idx.sort(key=score)
        main = names[idx[0]]
        alts = [names[i] for i in idx[1:] if names[i] and names[i] != main]
        out[u] = (main, ";".join(dict.fromkeys(alts)) or None, idx[0])
    return out


def add_name_points(b, area: Area, admin: AdminLookup) -> None:
    L = "swissnames3d_pkt"
    df = read_layer(NAMES_GPKG, L, area).reset_index(drop=True)
    skip = df["objektklasse_tlm"].isin(SKIP_CLASSES) | (
        (df["objektklasse_tlm"] == "TLM_EINZELOBJEKT") & df["objektart"].isin(SKIP_EINZELOBJEKT))
    df = df[~skip].reset_index(drop=True)
    groups = _group_names(df)
    rows = [g[2] for g in groups.values()]
    sub = df.iloc[rows].reset_index(drop=True)
    meta = list(groups.values())
    lv = shapely.force_2d(sub.geometry.values)
    gem, kt, cc = admin.lookup_points(lv)
    geoms = clip_wgs84(lv, area)
    counts = defaultdict(int)
    is_peak = sub["objektart"].isin(PEAKS | HILLS).values
    peak_cls = np.full(len(sub), 4, dtype=np.int8)
    if is_peak.any():
        pi = np.where(is_peak)[0]
        peak_cls[pi] = peaks.classify(lv[pi], [meta[i][0] for i in pi], list(sub["hoehe"].values[pi]),
                                      area.lv95_bbox())
    is_pass = sub["objektart"].isin(PASSES).values
    if is_pass.any():
        pi = np.where(is_pass)[0]
        peak_cls[pi] = peaks.classify(lv[pi], [meta[i][0] for i in pi], list(sub["hoehe"].values[pi]),
                                      area.lv95_bbox(), peaks.PASS_SOURCES, "Pass")
    # swissNAMES3D führt manche Pässe doppelt (Pass und Strassenpass, gleicher Name und Ort, z. B. Schwägalp
    # Passhöhe). Zwei gleiche Labels am selben Ort: mkgmap behält nur eines, die Klasse ging verloren.
    # Ein Punkt je Name im Umkreis von 50 m, mit der besten Klasse und natural=saddle, wenn einer ein Pass ist.
    pass_dup = set()
    saddle_of = {}
    if is_pass.any():
        seen: dict[str, list[int]] = defaultdict(list)
        for i in np.where(is_pass)[0]:
            nm = meta[i][0]
            keep = next((j for j in seen[nm] if shapely.distance(lv[i], lv[j]) < 50.0), None)
            if keep is None:
                seen[nm].append(i)
                continue
            pass_dup.add(int(i))
            peak_cls[keep] = min(peak_cls[keep], peak_cls[i])
            if sub["objektart"].iloc[i] == "Pass":
                saddle_of[keep] = True
    for i, g in enumerate(geoms):
        if g is None or g.is_empty or i in pass_dup:
            continue
        r = sub.iloc[i]
        oa, kl = r["objektart"], r["objektklasse_tlm"]
        main, alt, _ = meta[i]
        t = {"source": "swisstopo", "swisstopo:layer": L, "swisstopo:objektart": oa,
             "swisstopo:objektklasse": kl, "swisstopo:uuid": str(r["uuid"]).strip("{}").upper(),
             "name": main, "alt_name": alt}
        hoehe = val(r["hoehe"])
        if hoehe is not None and float(hoehe) > -1000:
            t["ele"] = int_str(round(float(hoehe)))
        if oa in PEAKS:
            t["natural"] = "peak"
            t["swisstopo:gipfelklasse"] = str(int(peak_cls[i]))
        elif oa in HILLS:
            t["natural"] = "hill"
            t["swisstopo:gipfelklasse"] = str(int(peak_cls[i]))
        elif kl == "TLM_SIEDLUNGSNAME_ZENTRUM":
            t["place"] = place_value(oa, r["einwohnerkategorie"])
            t["swisstopo:einwohnerkategorie"] = val(r["einwohnerkategorie"])
            t.update(is_in_tags(gem[i], kt[i], cc[i]))
            t.pop("ele", None)
        elif oa in POINT_TAGS:
            t.update(POINT_TAGS[oa])
            if oa in PASSES:
                t["swisstopo:passklasse"] = str(int(peak_cls[i]))
                if saddle_of.get(i):
                    t["natural"] = "saddle"
        else:
            counts["unbekannt:" + str(oa)] += 1
            continue
        if kl in ("TLM_HALTESTELLE", "TLM_GEBAEUDE", "TLM_FLURNAME"):
            t.pop("ele", None)
        b.add_point(g.x, g.y, t)
        counts[oa] += 1
        # Kotenpunkte unter benannten Gipfeln und Pässen (Pässe mit derselben Mechanik, Tag gipfelkote)
        k = t.get("swisstopo:gipfelklasse") or t.get("swisstopo:passklasse")
        if k and "ele" in t and main:
            for x, y, res in peaks.kote_points(g.x, g.y, int(k), oa in HILLS):
                b.add_point(x, y, {"source": "swisstopo", "swisstopo:layer": L, "ele": t["ele"],
                                   "swisstopo:gipfelkote": str(res), "swisstopo:gipfelklasse": k})
                counts["Gipfelkote" if oa not in PASSES else "Passkote"] += 1
    log.info("Namenpunkte: %s", dict(counts))


def lake_names(lc_df, area: Area) -> dict[int, str]:
    """Seenamen (swissNAMES3D) → Index der Wasserfläche in der Bodenbedeckung."""
    df = read_layer(NAMES_GPKG, "swissnames3d_ply", area,
                    where="objektklasse_tlm = 'TLM_STEHENDES_GEWAESSER' AND objektart = 'See'")
    if not len(df):
        return {}
    groups = _group_names(df.reset_index(drop=True))
    water_idx = np.where(lc_df["objektart"].isin(["Stehende Gewaesser"]).values)[0]
    water = lc_df.geometry.values[water_idx]
    tree = shapely.STRtree(water)
    out: dict[int, str] = {}
    for u, (main, _alt, i) in groups.items():
        g = shapely.force_2d(df.geometry.values[i])
        pt = shapely.point_on_surface(g)
        hits = tree.query(pt, predicate="intersects")
        if len(hits) == 0:
            hits = tree.query(g, predicate="intersects")
        for h in hits:
            out.setdefault(int(water_idx[h]), main)
    return out


def add_area_labels(b, area: Area) -> None:
    L = "swissnames3d_ply"
    df = read_layer(NAMES_GPKG, L, area,
                    where="objektklasse_tlm IN ('TLM_GELAENDENAME', 'TLM_GEBIETSNAME') OR "
                          "(objektklasse_tlm = 'TLM_STEHENDES_GEWAESSER' AND objektart = 'See')").reset_index(drop=True)
    groups = _group_names(df)
    # Namenklassen 1–4 nach SMV1000/SMV500/swissTLMRegio (Seen, Gletscher, Gebiets- und Talnamen)
    gi = [i for _, (_, _, i) in groups.items()]
    ncls = dict(zip(gi, labelclass.classify(
        shapely.force_2d(df.geometry.values[gi]), [df["name"].iloc[i] for i in gi],
        [labelclass.KIND.get(df["objektart"].iloc[i]) for i in gi], area.lv95_bbox())))
    # Gipfel (swissNAMES3D) für Massive: Namenpunkt am höchsten Gipfel der Massivfläche
    massive = [i for _, (_, _, i) in groups.items() if df["objektart"].iloc[i] == "Massiv"]
    peaks = None
    if massive:
        tb = tuple(shapely.total_bounds(shapely.force_2d(df.geometry.values[massive])))
        pk = pyogrio.read_dataframe(NAMES_GPKG, layer="swissnames3d_pkt", bbox=tb,
                                    columns=["name", "objektart", "hoehe"],
                                    where="objektklasse_tlm = 'TLM_NAME_PKT' AND objektart IN "
                                          "('Hauptgipfel','Gipfel','Alpiner Gipfel','Felskopf','Haupthuegel','Huegel')")
        peaks = (shapely.force_2d(pk.geometry.values), pk["name"].tolist(), pk["hoehe"].tolist())
        peak_tree = shapely.STRtree(peaks[0])
    n = nm = 0
    for u, (main, alt, i) in groups.items():
        oa = df["objektart"].iloc[i]
        if oa not in AREA_LABELS:
            continue
        g = shapely.force_2d(df.geometry.values[i])
        t = {"source": "swisstopo", "swisstopo:layer": L, "swisstopo:objektart": oa,
             "name": main, "alt_name": alt, **AREA_LABELS[oa]}
        if oa in labelclass.KIND:
            t["swisstopo:namenklasse"] = str(int(ncls.get(i, 4)))
        p_lv = shapely.point_on_surface(g)
        if oa == "Massiv" and peaks is not None:
            inside = [k for k in peak_tree.query(g, predicate="contains") if val(peaks[2][k]) is not None]
            if inside:
                k = max(inside, key=lambda j: float(peaks[2][j]))
                p_lv = peaks[0][k]
                # Suchpunkt am Hauptgipfel (Gerätetest 22): „Pilatus“ am Tomlishorn
                # ohne ele: der Style hängt sonst den Höhencode ans Label, und die Suche findet
                # „Pilatus“ evtl. nicht mehr (siehe docs/vektor/basiskarte.md, Test 22)
                t.update({"natural": "peak", "swisstopo:hauptgipfel": peaks[1][k],
                          "swisstopo:hauptgipfel_ele": int_str(round(float(peaks[2][k])))})
                nm += 1
        pt = clip_wgs84(np.array([p_lv]), area)[0]
        if (pt is None or pt.is_empty) and oa == "See" and t.get("swisstopo:namenklasse") in ("1", "2"):
            # Grosse Grenzseen (Bodensee, Léman): Der innere Punkt der ganzen Fläche liegt im Ausland.
            # Ersatz: innerer Punkt des Teils im Gebiet
            part = shapely.intersection(g, shapely.box(*area.lv95_bbox()))
            if not part.is_empty:
                pt = clip_wgs84(np.array([shapely.point_on_surface(part)]), area)[0]
        if pt is None or pt.is_empty:
            continue
        b.add_point(pt.x, pt.y, t)
        n += 1
        # Massiv der Klassen 1–3 mit Suchpunkt am Hauptgipfel (unsichtbar, 0x6612): zusätzlich ein sichtbarer
        # Name in der Massivfläche (Wunsch style-typ), z. B. „Rigi“, „Pilatus“
        if "swisstopo:hauptgipfel" in t and t.get("swisstopo:namenklasse", "4") != "4":
            ps = clip_wgs84(np.array([shapely.point_on_surface(g)]), area)[0]
            if ps is not None and not ps.is_empty:
                b.add_point(ps.x, ps.y, {"source": "swisstopo", "swisstopo:layer": L, "swisstopo:objektart": oa,
                                         "name": main, "natural": "mountain_range",
                                         "swisstopo:namenklasse": t["swisstopo:namenklasse"]})
                n += 1
    log.info("Flächennamen als Punkte: %d (davon %d Massive am Hauptgipfel)", n, nm)


# Gleichnamige Punkte neben einem Gipfel verlieren den Namen (zwei gleiche Labels an einer Stelle).
# Je Art: Erkennung, Abstand in m, Tag für den entfernten Namen.
NAME_AT_PEAK = (
    ("Aussichtspunkt", lambda t: t.get("tourism") == "viewpoint", 50.0, "swisstopo:aussicht_name"),
    ("Station", lambda t: "aerialway" in t or t.get("railway") in ("station", "halt"), 150.0,
     "swisstopo:station_name"),
)


def drop_names_at_peaks(b) -> dict:
    """Aussichtspunkte (< 50 m) und Stationen (< 150 m) ohne Namen, wenn ein gleichnamiger Gipfel oder Hügel
    so nahe liegt.

    Beispiel Säntis: Gipfel, Aussichtspunkt (10 m) und Bergstation (87 m) heissen „Säntis“. Gleiche Labels
    nebeneinander verdrängen sich in BaseCamp, auf dem GPSMAP 67 stehen sie doppelt. Das Symbol bleibt,
    der Name steht im Tag der Tabelle NAME_AT_PEAK. Die Suche findet den Gipfel.
    """
    from .common import COORD_SCALE
    at: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for nid, t in b.node_tags.items():
        if t.get("natural") in ("peak", "hill") and t.get("name") and "swisstopo:hauptgipfel" not in t:
            at[t["name"]].append((b.node_lon[nid - 1] / COORD_SCALE, b.node_lat[nid - 1] / COORD_SCALE))
    stats = {}
    for label, match, dist, key in NAME_AT_PEAK:
        n = 0
        for nid, t in b.node_tags.items():
            name = t.get("name")
            if not name or name not in at or t.get("natural") in ("peak", "hill") or not match(t):
                continue
            lon, lat = b.node_lon[nid - 1] / COORD_SCALE, b.node_lat[nid - 1] / COORD_SCALE
            kx = 111_320.0 * np.cos(np.radians(lat))
            if any(np.hypot((plon - lon) * kx, (plat - lat) * 110_540.0) < dist for plon, plat in at[name]):
                t[key] = t.pop("name")
                n += 1
        stats[label] = n
    log.info("Namen neben gleichnamigem Gipfel entfernt: %s", stats)
    return stats
