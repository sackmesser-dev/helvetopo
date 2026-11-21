"""Objektnamen wie auf der LK aus den SMV25-Annotation-Layern (swisstopo, OGD).

Quelle: Swiss Map Vector 25, blattweise GPKG unter downloads/smv25-2026/<blatt>/*.gpkg.
Je beschriftetes Objekt ein Knoten `name=<Text>`, `swisstopo:anno=<klasse>` am Mittelpunkt der
Beschriftung. Mehrzeilige Texte (gleiche DKM_UUID) werden von oben nach unten, links nach rechts
zusammengesetzt; „Kantons-“ + „spital“ → „Kantonsspital“, „Gross-“ + „-Hütten“ → „Gross-Hütten“.
Doppel aus überlappenden Blättern fallen weg.

Abgleich mit den Areal-/Gebäude-POIs (pois.py): Die DKM_UUID entspricht nicht der TLM-UUID, deshalb
räumlich: POI derselben Klasse < 150 m mit passendem Text (text_matches) bzw. < 300 m, wenn der LK-Text
nur die Gattung des POI-Namens ist („Burgruine“ ↔ „Burgruine Helfenberg“; dann wird der POI-Name das Label)
→ sonst wird dessen Name `alt_name` am Anno-Knoten, seine
POI-Tags (amenity, tourism …) gehen auf den Anno-Knoten über, der POI-Knoten entfällt. Der zusammengelegte
Knoten liegt an der Objektposition des POI (im Areal bzw. Gebäude), nicht an der LK-Textposition (Review 3).
"""

from __future__ import annotations

import glob
import logging
from pathlib import Path

import numpy as np
import pyogrio
import shapely
from pyproj import Transformer

from .common import COORD_SCALE, DOWNLOADS, Area, clip_wgs84

log = logging.getLogger("vector")

SMV25_DIR = DOWNLOADS / "smv25-2026"
LAYERS = {
    "T07_DKM25_GEBAEUDE_ANNO": ("gebaeude", "gebaeude", None),
    "T08_DKM25_BAUTE_PKT_ANNO": ("baute", "einzelobjekt", None),
    "T10_DKM25_BAUTE_PLY_ANNO": ("baute", "einzelobjekt", None),
    "T25_DKM25_FREIZEITAREAL_ANNO": ("freizeitareal", "areal", "tlm_areale_freizeitareal"),
    "T26_DKM25_NUTZUNGSAREAL_ANNO": ("nutzungsareal", "areal", "tlm_areale_nutzungsareal"),
    "T27_DKM25_VERKEHRSAREAL_ANNO": ("verkehrsareal", "areal", "tlm_areale_verkehrsareal"),
}
POI_KEYS = ("amenity", "tourism", "leisure", "historic", "aeroway", "highway", "man_made",
            "power", "landuse", "industrial", "military", "sport", "parking", "access", "building",
            "tower:type")
MATCH_M = 150.0
# Gattungsbeschriftung („Burgruine“, „Ruine“, „Kloster“) zum POI mit Eigennamen: grösserer Radius, weil
# die LK den Gattungsnamen oft neben das Objekt setzt (Helfenberg: 170 m)
MATCH_GENERIC_M = 300.0


def is_generic_of(anno: str, name: str) -> bool:
    """Ist die LK-Beschriftung ein ganzes Wort am Anfang bzw. im POI-Namen, der länger ist?"""
    a, n = _words(anno), _words(name)
    return bool(a) and len(n) > len(a) and all(w in n for w in a) and len(" ".join(a)) >= 4


def _words(s: str) -> list[str]:
    import re
    return [w for w in re.split(r"[\s\-/,()]+", s.lower()) if w]


def text_matches(anno: str, name: str) -> bool:
    """Passt die LK-Beschriftung zum POI-Namen? Verhindert Fehlzuordnungen wie „KW“ (Kraftwerk)
    an der Burgruine Helfenberg (Review 1). Treffer: Teilstring, gemeinsames Wort ≥ 4 Zeichen oder
    abgekürztes Wort („Schulh.“ → „Schulhaus …“)."""
    a, n = anno.lower().strip(), name.lower().strip()
    if not a or not n:
        return False
    if a in n or n in a:
        return True
    wa, wn = _words(a), _words(n)
    for x in wa:
        if x.endswith(".") and len(x) >= 3 and any(y.startswith(x[:-1]) for y in wn):
            return True
        if len(x) >= 4 and any(x == y or (len(y) >= 4 and (x in y or y in x)) for y in wn):
            return True
    return False


def join_lines(lines: list[str]) -> str:
    out = ""
    flat = [x for l in lines if l for x in str(l).replace("\r", "\n").split("\n")]
    for s in (l.strip() for l in flat if l.strip()):
        if not out:
            out = s
        elif out.endswith("-"):
            if s.startswith("-"):
                out += s[1:]
            elif s[:1].islower():
                out = out[:-1] + s          # Trennung: „Kantons-“ + „spital“
            else:
                out += s                     # Bindestrich bleibt: „Gross-“ + „Hütten“
        else:
            out += " " + s
    return out


def read_anno(area: Area, layers=None):
    layers = LAYERS if layers is None else layers
    bbox = area.lv95_bbox()
    items = {}  # (layer, uuid) → [(y, x, text, geom)]
    for f in sorted(glob.glob(str(SMV25_DIR / "*" / "*.gpkg"))):
        info_layers = {n for n, _ in pyogrio.list_layers(f)}
        for layer in layers:
            if layer not in info_layers:
                continue
            df = pyogrio.read_dataframe(f, layer=layer, bbox=bbox,
                                        columns=["DKM_UUID", "TEXTSTRING", "FEATUREID"])
            for u, t, g in zip(df["DKM_UUID"], df["TEXTSTRING"], df.geometry.values):
                if not t or g is None or g.is_empty:
                    continue
                g = shapely.force_2d(g)
                c = g.centroid
                key = (layer, u or f"fid:{f}:{t}")
                lst = items.setdefault(key, [])
                # gleiche Zeile aus einem überlappenden Blatt nicht doppelt
                if any(tt == t and abs(cy - c.y) < 1 and abs(cx - c.x) < 1 for cy, cx, tt, _ in lst):
                    continue
                lst.append((c.y, c.x, t, g))
    out = []
    for (layer, u), lst in items.items():
        # Zeilen: oben nach unten (y absteigend, auf 2 m gerundet), dann links nach rechts
        lst.sort(key=lambda r: (-round(r[0] / 2), r[1]))
        text = join_lines([r[2] for r in lst])
        geom = shapely.union_all([r[3] for r in lst])
        out.append((layer, u, text, geom.centroid))
    return out


def add_anno(b, area: Area) -> None:
    annos = read_anno(area)
    if not annos:
        return
    lv = np.array([a[3] for a in annos], dtype=object)
    pts = clip_wgs84(lv, area)
    # vorhandene POIs (pois.py) je Klasse in LV95
    to_lv = Transformer.from_crs(4326, 2056, always_xy=True)
    pois: dict[str, list] = {}
    for nid, t in b.node_tags.items():
        kind = t.get("swisstopo:poi")
        if kind in ("areal", "gebaeude", "einzelobjekt") and t.get("name"):
            x, y = to_lv.transform(b.node_lon[nid - 1] / COORD_SCALE, b.node_lat[nid - 1] / COORD_SCALE)
            pois.setdefault(kind, []).append((x, y, nid, t.get("swisstopo:layer")))
    stats = {"anno": 0, "zusammengelegt": 0, "an_objektposition_ueber_30m": 0}
    used = set()
    for i, (layer, u, text, c) in enumerate(annos):
        p = pts[i]
        if p is None or p.is_empty:
            continue
        cls, kind, tlm_layer = LAYERS[layer]
        t = {"name": text, "swisstopo:anno": cls, "source": "swisstopo",
             "swisstopo:layer": "smv25:" + layer, "swisstopo:dkm_uuid": (u or "").strip("{}").upper() or None}
        best = None
        for x, y, nid, pl in pois.get(kind, ()):
            if nid in used or (tlm_layer and pl != tlm_layer):
                continue
            d = (x - c.x) ** 2 + (y - c.y) ** 2
            pn = b.node_tags[nid].get("name") or ""
            if best is not None and d >= best[0]:
                continue
            if d < MATCH_M ** 2 and text_matches(text, pn):
                best = (d, nid)
            elif d < MATCH_GENERIC_M ** 2 and is_generic_of(text, pn):
                best = (d, nid)
        if best is not None:
            nid = best[1]
            used.add(nid)
            old = b.node_tags[nid]
            if old.get("name") and is_generic_of(text, old["name"]):
                # LK-Text ist nur die Gattung („Burgruine“), der POI hat den Eigennamen
                # („Burgruine Helfenberg“, Review BaseCamp-Test 24) → POI-Name wird das Label
                t["name"], t["alt_name"] = old["name"], text
            elif old.get("name") and old["name"] != text:
                t["alt_name"] = old["name"]
                # mkgmap indexiert nur das Label, nicht alt_name → amtlicher Name zusätzlich für den Stil
                t["swisstopo:amtlicher_name"] = old["name"]
            for k in POI_KEYS:
                if k in old:
                    t[k] = old[k]
            for k in ("is_in:country", "is_in:county", "is_in:city"):
                if k in old:
                    t[k] = old[k]
            b.node_tags[nid] = {}  # POI-Knoten entfällt (unbenannt, ohne Tags → ignoriert)
            stats["zusammengelegt"] += 1
            # Symbol am Objekt, nicht an der LK-Textposition (Review 3: Burgruine Helfenberg stand
            # 170 m daneben auf der Wiese, wo die LK das Wort „Burgruine“ freigestellt hat).
            # Der POI-Knoten liegt im Areal bzw. Gebäude (point_on_surface) oder am TLM-Punkt.
            if best[0] > 30.0 ** 2:
                stats["an_objektposition_ueber_30m"] += 1
            b.add_point(b.node_lon[nid - 1] / COORD_SCALE, b.node_lat[nid - 1] / COORD_SCALE, t)
            stats["anno"] += 1
            continue
        b.add_point(p.x, p.y, t)
        stats["anno"] += 1
    log.info("SMV25-Annotationen: %s", stats)


# --- Namen an der LK-Textposition (Wunsch style-typ, Test 24) -----------------------------------
# swissNAMES3D-Flur-, Gelände- und Gebietsnamen liegen an einem Referenzpunkt; die LK setzt den Text
# freigestellt daneben. An der Referenzposition kollidieren sie mit LK-platzierten Labels (Ruine
# Helfenberg ↔ Flurname „Oberhof“, 17 m). Hat der Name eine SMV25-Beschriftung mit gleichem Text in
# der Nähe, wandert der Punkt an deren Textmitte; ohne Gegenstück bleibt er und bekommt
# swisstopo:lk_text=no (die LK25 zeigt ihn nicht).
NAME_ANNO_LAYERS = ("T14_DKM25_FLURNAME_ANNO", "T12_DKM25_GELAENDENAME_ANNO", "T13_DKM25_GEBIETSNAME_ANNO")
NAME_MOVE_M = 600.0


def _norm(s: str) -> str:
    return " ".join((s or "").split()).lower()


def move_names_to_anno(b, area: Area) -> dict:
    annos = read_anno(area, NAME_ANNO_LAYERS)
    by_text: dict[str, list] = {}
    for _, _, text, c in annos:
        by_text.setdefault(_norm(text), []).append([c.x, c.y, False])
    to_lv = Transformer.from_crs(4326, 2056, always_xy=True)
    to_wgs = Transformer.from_crs(2056, 4326, always_xy=True)
    stats = {"verschoben": 0, "ohne_gegenstueck": 0}
    dist = []
    for nid, t in b.node_tags.items():
        lay, kl = t.get("swisstopo:layer"), t.get("swisstopo:objektklasse")
        if not t.get("name") or "swisstopo:hauptgipfel" in t:
            continue
        if not ((lay == "swissnames3d_pkt" and kl == "TLM_FLURNAME") or lay == "swissnames3d_ply"):
            continue
        x, y = to_lv.transform(b.node_lon[nid - 1] / COORD_SCALE, b.node_lat[nid - 1] / COORD_SCALE)
        best = None
        for cand in by_text.get(_norm(t["name"]), ()):
            if cand[2]:
                continue
            d = ((cand[0] - x) ** 2 + (cand[1] - y) ** 2) ** 0.5
            if d < NAME_MOVE_M and (best is None or d < best[0]):
                best = (d, cand)
        if best is None:
            t["swisstopo:lk_text"] = "no"
            stats["ohne_gegenstueck"] += 1
            continue
        d, cand = best
        cand[2] = True
        lon, lat = to_wgs.transform(cand[0], cand[1])
        b.node_lon[nid - 1] = int(round(lon * COORD_SCALE))
        b.node_lat[nid - 1] = int(round(lat * COORD_SCALE))
        t["swisstopo:lk_text"] = "yes"
        stats["verschoben"] += 1
        dist.append(d)
    if dist:
        stats["median_m"] = round(float(np.median(dist)))
    log.info("Namen an LK-Textposition: %s", stats)
    return stats

