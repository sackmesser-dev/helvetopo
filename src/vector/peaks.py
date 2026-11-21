"""Gipfel- und Passklassen 1–4 wie die Landeskarten-Massstäbe (Gerätetest Säntis).

Ein Gipfel oder Hügel aus swissNAMES3D bekommt die kleinste Klasse, in deren Karte er vorkommt:
- 1: Swiss Map Vector 1000 (Namenpunkte 1:1 Mio., Objektart Gipfel)
- 2: Swiss Map Vector 500 (Namenpunkte 1:500 000: Hauptgipfel, Alpiner Gipfel, Gipfel, Hügel)
- 3: swissTLMRegio (Namen HGipfel, GGipfel, KGipfel, Huegel)
- 4: alle übrigen
Pässe ebenso (PASS_SOURCES: SMV1000 Pass, SMV500 Pass und Strassenpass, swissTLMRegio Strassenpass und
Fusspass).
Zuordnung: gleicher Name (Vergleich ohne Abkürzungspunkt und Gross-/Kleinschreibung) im Umkreis R,
oder Name in Doppelnamen enthalten, sonst gleiche Höhe (±3 m) im Umkreis R. Die kleinmassstäblichen Punkte sind generalisiert.
"""

from __future__ import annotations

import logging
import unicodedata

import numpy as np
import pyogrio
import shapely

from .common import SMV500_GPKG, SMV1000_GPKG, TLMREGIO_GPKG

log = logging.getLogger("vector")

PEAK_SOURCES = (  # Klasse, Datei, Layer, Filter, Namensspalte, Höhenspalte, Radius m
    (1, SMV1000_GPKG, "T14_DKM1M_NAME_PKT", "OBJEKTART = 'Gipfel'", "NAME", "HOEHE", 1500.0),
    (2, SMV500_GPKG, "T15_DKM500_NAME_PKT",
     "OBJEKTART IN ('Hauptgipfel','Alpiner_Gipfel','Gipfel','Huegel')", "NAME", "HOEHE", 800.0),
    (3, TLMREGIO_GPKG, "tlmregio_names_namedlocation",
     "objval IN ('HGipfel','GGipfel','KGipfel','Huegel')", "namn1", "altitude", 400.0),
)
SOURCES = PEAK_SOURCES   # frühere Bezeichnung
PASS_SOURCES = (
    (1, SMV1000_GPKG, "T14_DKM1M_NAME_PKT", "OBJEKTART = 'Pass'", "NAME", "HOEHE", 1500.0),
    (2, SMV500_GPKG, "T15_DKM500_NAME_PKT", "OBJEKTART IN ('Pass','Strassenpass')", "NAME", "HOEHE", 800.0),
    (3, TLMREGIO_GPKG, "tlmregio_names_namedlocation",
     "objval IN ('Strassenpass','Fusspass')", "namn1", "altitude", 400.0),
)


def _norm(s) -> str:
    s = unicodedata.normalize("NFC", str(s or "")).lower().replace(".", "").strip()
    return " ".join(s.split())


def _same_name(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b or (len(b) >= 4 and b in a) or (len(a) >= 4 and a in b):   # Doppelnamen „Rheinwaldhorn Adula“
        return True
    # SMV1000 kürzt ab („M Grand Paradis“, „Pz Bernina“): erstes Wort als Präfix
    wa, wb = a.split(), b.split()
    return len(wa) == len(wb) and wa[1:] == wb[1:] and (wb[0].startswith(wa[0]) or wa[0].startswith(wb[0]))


def classify(points_lv95: np.ndarray, names: list, eles: list, bbox=None, sources=PEAK_SOURCES,
             what: str = "Gipfel") -> np.ndarray:
    """Klasse 1–4 je Gipfel- bzw. Passpunkt (LV95, 2D)."""
    n = len(points_lv95)
    cls = np.full(n, 4, dtype=np.int8)
    if n == 0:
        return cls
    tree = shapely.STRtree(points_lv95)
    norm = [_norm(x) for x in names]
    ele = np.array([np.nan if e is None else float(e) for e in eles])
    for k, path, layer, where, ncol, hcol, r in sources:
        if not path.exists():
            log.warning("%sklassen: %s fehlt, Klasse %d entfällt", what, path, k)
            continue
        df = pyogrio.read_dataframe(path, layer=layer, where=where, columns=[ncol, hcol],
                                    bbox=None if bbox is None else tuple(np.add(bbox, (-r, -r, r, r))))
        src = shapely.force_2d(df.geometry.values)
        hit = 0
        for g, nm, h in zip(src, df[ncol], df[hcol]):
            cand = tree.query(g, predicate="dwithin", distance=r)
            if not len(cand):
                continue
            d = shapely.distance(points_lv95[cand], g)
            sn = _norm(nm)
            by_name = [(dd, c) for dd, c in zip(d, cand) if _same_name(sn, norm[c])]
            if by_name:
                c = min(by_name)[1]
            else:
                by_ele = [(dd, c) for dd, c in zip(d, cand)
                          if h is not None and abs(ele[c] - float(h)) <= 3]
                if not by_ele:
                    continue
                c = min(by_ele)[1]
            if cls[c] > k:
                cls[c] = k
                hit += 1
        log.info("%sklasse %d: %d von %d Punkten aus %s zugeordnet", what, k, hit, len(df), layer)
    return cls


# Gipfelkote als eigener Punkt unter dem Gipfel (Gerätetest 7794-klassen: am selben Punkt zeigt das GPSMAP 67
# nur den Namen, „2502“ am Säntis fehlte). Wie in der LK steht die Kote unter dem Namen. Der Abstand ist in
# Karteneinheiten der Auflösung r fest (KOTE_UNITS · 360°/2^r nach Süden), deshalb je Auflösung ein Punkt
# mit swisstopo:gipfelkote=r. Der Stil zeichnet ihn nur in der Auflösung r.
KOTE_UNITS = 12
KOTE_START = {1: 19, 2: 20, 3: 21, 4: 22}   # erste Auflösung der Kote je Klasse (Hügel Klasse 4: 23)


def kote_points(lon: float, lat: float, cls: int, hill: bool):
    """(lon, lat, r) der Kotenpunkte eines benannten Gipfels, r = erste Auflösung … 24."""
    start = 23 if hill and cls == 4 else KOTE_START[cls]
    for r in range(start, 25):
        yield lon, lat - KOTE_UNITS * 360.0 / 2 ** r, r
