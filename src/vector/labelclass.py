"""Namenklassen 1–4 für Seen, Gletscher, Gebiets-, Tal- und Bergnamen (Flächennamen aus swissNAMES3D).

Wie bei den Gipfeln (src/vector/peaks.py) folgt die Klasse den Landeskarten-Massstäben:
- 1: Der Name steht in Swiss Map Vector 1000 (Anno-Text in der Nähe der Fläche).
- 2: Der Name steht in Swiss Map Vector 500.
- 3: swissTLMRegio hat eine gleichnamige Namenfläche (tlmregio_names_namedlocation_ply), die die Fläche
     schneidet.
- 4: alle übrigen.
Die Anno-Texte sind teilweise getrennt („Vierwald-“ / „stättersee“) oder abgekürzt („Gr. Aletschgletscher“,
„Gouwligl.“). Vergleich: Kleinschreibung, ohne Punkt, Trennstrich und Zeilenumbruch, Abkürzungen ausgeschrieben.
Ein Text gilt als Treffer, wenn er Wort für Wort dem Namen entspricht (Abkürzung mit Punkt als Präfix).
Ein über die Zeile getrenntes Fragment (≥ 5 Zeichen) zählt, wenn der Name damit beginnt oder endet.
"""

from __future__ import annotations

import logging
import re
import unicodedata

import numpy as np
import pyogrio
import shapely

from .common import SMV500_GPKG, SMV1000_GPKG, TLMREGIO_GPKG

log = logging.getLogger("vector")

# Art → Quellen (Klasse, Datei, Layer, Filter, Textspalte, Abstand m; 0 = muss schneiden)
_TLMR = "tlmregio_names_namedlocation_ply"
SOURCES = {
    "see": (
        (1, SMV1000_GPKG, "T07_DKM1M_GEWAESSER_PLY_ANNO", None, "TextString", 5000.0),
        (2, SMV500_GPKG, "T07_DKM500_GEWAESSER_PLY_ANNO", None, "TextString", 3000.0),
        (3, TLMREGIO_GPKG, _TLMR, "objval IN ('GSee','KSee','Stausee')", "namn1", 0.0),
    ),
    "gletscher": (
        (1, SMV1000_GPKG, "T05_DKM1M_GELAENDENAME_ANNO", None, "TextString", 5000.0),
        (2, SMV500_GPKG, "T05_DKM500_GELAENDENAME_ANNO", None, "TextString", 3000.0),
        (3, TLMREGIO_GPKG, _TLMR, "objval = 'Gletscher'", "namn1", 0.0),
    ),
    "gebiet": (
        (1, SMV1000_GPKG, "T05_DKM1M_GELAENDENAME_ANNO", None, "TextString", 5000.0),
        (2, SMV500_GPKG, "T05_DKM500_GELAENDENAME_ANNO", None, "TextString", 3000.0),
        (2, SMV500_GPKG, "T04_DKM500_GEBIETSNAME_ANNO", None, "TextString", 3000.0),
        (3, TLMREGIO_GPKG, _TLMR,
         "objval IN ('Gebiet','Haupttal','Nebental','Massiv','Grat','Graben')", "namn1", 0.0),
    ),
}
KIND = {"See": "see", "Gletscher": "gletscher",
        "Gebiet": "gebiet", "Landschaftsname": "gebiet", "Grossregion": "gebiet", "Tal": "gebiet",
        "Haupttal": "gebiet", "Graben": "gebiet", "Grat": "gebiet", "Massiv": "gebiet", "Huegelzug": "gebiet"}

# Abkürzungen in den Anno-Texten: Wort mit Punkt → Präfix des Namenworts („Gr.“ → „Grosser“, „M.“ → „Mont“),
# „…gl.“ → „…gletscher“
def _tokens(s) -> tuple[list, bool]:
    """(Wörter mit Abkürzungsmarke, Fragment) eines Anno-Texts. Fragment: über die Zeile getrennt („Vierwald-“)."""
    s = re.sub(r"<[^>]*>", "", str(s or "")).strip()
    frag = s.endswith("-") or s.startswith("-")
    s = re.sub(r"-\s*[\r\n]+\s*", "", s).replace("\r", " ").replace("\n", " ")
    s = unicodedata.normalize("NFC", s).lower().replace("-", " ").replace("'", "' ")
    out = []
    for w in s.split():
        out.append((w.rstrip("."), w.endswith(".")))
    return [(w, ab) for w, ab in out if w], frag


def _name_words(name) -> list:
    s = unicodedata.normalize("NFC", str(name or "")).lower().replace("-", " ").replace("'", "' ").replace(".", "")
    return s.split()


def _word_ok(w: str, ab: bool, n: str) -> bool:
    if w == n:
        return True
    if ab and w.endswith("gl") and n.endswith("gletscher"):
        return n.startswith(w[:-2])
    return ab and n.startswith(w)


# Wörter ohne Unterscheidungskraft: Ein Fragment aus nur solchen Wörtern („Lac de “, „Lago di “) zählt nicht
GENERIC = {"lac", "lago", "lai", "see", "de", "di", "du", "des", "la", "le", "les", "del", "della", "dal", "da",
           "glacier", "gletscher", "ghiacciaio", "vadret", "val", "valle", "vallon", "tal", "piz", "pizzo", "mont",
           "monte", "pointe", "gross", "klein", "massif", "der", "die", "das", "im", "am", "il", "d'", "l'"}


def _hit(tok: list, frag: bool, name: list) -> bool:
    if not tok or not name:
        return False
    if len(tok) == len(name) and all(_word_ok(w, ab, n) for (w, ab), n in zip(tok, name)):
        return True
    if not frag or all(w in GENERIC or w.isdigit() for w, _ in tok):
        return False
    # Fragment: Anfang oder Ende des Namens (ohne Leerzeichen verglichen), mindestens 5 Zeichen
    t = "".join(w for w, _ in tok)
    nm = "".join(name)
    return len(t) >= 5 and (nm.startswith(t) or nm.endswith(t))


def classify(geoms_lv95: np.ndarray, names: list, kinds: list, bbox=None) -> np.ndarray:
    """Klasse 1–4 je Fläche. kinds: Schlüssel aus SOURCES (oder None → 4)."""
    n = len(geoms_lv95)
    cls = np.full(n, 4, dtype=np.int8)
    if n == 0:
        return cls
    norm = [_name_words(x) for x in names]
    for kind, sources in SOURCES.items():
        idx = np.array([i for i, k in enumerate(kinds) if k == kind], dtype=np.int64)
        if not len(idx):
            continue
        tree = shapely.STRtree(geoms_lv95[idx])
        for k, path, layer, where, tcol, dist in sources:
            if not path.exists():
                log.warning("Namenklassen: %s fehlt, Klasse %d entfällt", path, k)
                continue
            pad = max(dist, 1.0)
            df = pyogrio.read_dataframe(path, layer=layer, where=where, columns=[tcol],
                                        bbox=None if bbox is None else tuple(np.add(bbox, (-pad, -pad, pad, pad))))
            src = shapely.force_2d(df.geometry.values)
            hit = 0
            for g, txt in zip(src, df[tcol]):
                tok, frag = _tokens(txt)
                if not tok:
                    continue
                cand = tree.query(g, predicate="intersects") if dist == 0 else \
                    tree.query(g, predicate="dwithin", distance=dist)
                for c in cand:
                    j = idx[c]
                    if cls[j] > k and _hit(tok, frag, norm[j]):
                        cls[j] = k
                        hit += 1
            log.info("Namenklasse %s %d: %d Flächen aus %s", kind, k, hit, layer)
    return cls
