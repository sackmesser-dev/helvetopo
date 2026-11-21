"""Quellstand und Copyright-Texte der Swiss Map Raster aus den STAC-Metadaten (data.geo.admin.ch).

Grundlage:
- `downloads/smr/manifest.json`: Kachelwerke SMR25/50/100/200. Je Blatt Massstab, Blatt, Ausgabejahr
  (STAC `datetime`), Auflösung, Name, URL und BBox; das schreibt der SMR-Download.
- SMR500/1000: Einzelblätter. Deren STAC-Item wird bei Bedarf abgefragt und in
  `downloads/smr/manifest_stac_items.json` zwischengespeichert.

Die Funktionen liefern:
- `sources(scales, bbox)`: Ausgaben je Massstab für ein Gebiet (WGS84 W, S, E, N);
- `copyright_lines(...)`: TRE-Copyright-Zeilen (cp1252-tauglich);
- `quellstand_text(...)`: Text für QUELLSTAND.txt, README und Kartenbeschreibung.

Aufruf zum Testen: python3 -I quellstand.py 25,50,100,200,500 [W S E N]
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import urllib.request

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

DL = str(paths.SMR_DIR)
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.pixelkarte-farbe-pk{s}.noscale"
NAMES = {10: "Swiss Map Raster 10", 25: "Swiss Map Raster 25", 50: "Swiss Map Raster 50",
         100: "Swiss Map Raster 100", 200: "Swiss Map Raster 200", 500: "Swiss Map Raster 500",
         1000: "Swiss Map Raster 1000"}
LICENSE_LINE = ("©swisstopo, Daten unter den Nutzungsbedingungen für frei verfügbare Geodaten (OGD) "
                "des Bundesamts für Landestopografie swisstopo, https://www.swisstopo.admin.ch/ogd-conditions. "
                "Inoffizielle Karte, kein Produkt von swisstopo oder Garmin.")


def _manifest() -> list[dict]:
    with open(os.path.join(DL, "manifest.json")) as f:
        man = json.load(f)
    p10 = os.path.join(DL, "manifest_pk10.json")      # SMR10 (Landeskarte 1:10'000), nur geladene Blätter
    if os.path.exists(p10):
        with open(p10) as f:
            man += json.load(f)
    return man


def collection(scale: int) -> str:
    return ("ch.swisstopo.landeskarte-farbe-10" if scale == 10
            else f"ch.swisstopo.pixelkarte-farbe-pk{scale}.noscale")


def _single_sheet(scale: int) -> list[dict]:
    """STAC-Item(s) eines Einzelblatt-Massstabs (500, 1000), zwischengespeichert."""
    cache = os.path.join(DL, "manifest_stac_items.json")
    data = json.load(open(cache)) if os.path.exists(cache) else {}
    if str(scale) not in data:
        with urllib.request.urlopen(STAC.format(s=scale) + "/items?limit=10", timeout=30) as r:
            items = json.load(r)["features"]
        data[str(scale)] = [dict(scale=scale, sheet=it["id"], year=int(it["properties"]["datetime"][:4]),
                                 updated=it["properties"].get("updated"), bbox=it["bbox"],
                                 res=next(iter(it["assets"].values())).get("eo:gsd")) for it in items]
        with open(cache, "w") as f:
            json.dump(data, f, indent=1)
    return data[str(scale)]


def sources(scales: list[int], bbox: tuple[float, float, float, float] | None = None) -> dict[int, dict]:
    """Je Massstab: Blattzahl, Ausgabejahre (min, max), Auflösungen, STAC-Collection."""
    man = _manifest()
    out = {}
    for s in scales:
        sheets = [m for m in man if m["scale"] == s] or _single_sheet(s)
        if bbox:
            w, so, e, n = bbox
            sheets = [m for m in sheets if not (m["bbox"][2] < w or m["bbox"][0] > e or m["bbox"][3] < so
                                                 or m["bbox"][1] > n)]
        years = sorted(m["year"] for m in sheets)
        out[s] = dict(name=NAMES[s], sheets=len(sheets), year_min=years[0] if years else None,
                      year_max=years[-1] if years else None, res=sorted({m.get("res") for m in sheets}),
                      collection=collection(s))
    return out


def _years(src: dict) -> str:
    a, b = src["year_min"], src["year_max"]
    return f"Ausgabe {a}" if a == b else f"Ausgaben {a}–{b}"


def copyright_lines(scales: list[int], bbox=None, product: str = "Helvetopo") -> tuple[str, ...]:
    """TRE-Copyright: ©swisstopo, je Massstab Kartenwerk + Ausgabe, Hinweis inoffiziell."""
    src = sources(scales, bbox)
    lines = ["©swisstopo"]
    lines += [f"{v['name']} ({_years(v)}), swisstopo OGD" for v in src.values()]
    lines.append(f"{product}, inoffizielle Karte")
    return tuple(lines)


def quellstand_text(scales: list[int], bbox=None, product: str = "", fid: int | None = None) -> str:
    src = sources(scales, bbox)
    now = _dt.date.today().isoformat()
    t = [f"Quellstand {product}".strip(), f"Erstellt: {now}" + (f", Family-ID {fid}" if fid else ""), ""]
    for s, v in src.items():
        res = ", ".join(f"{r:g} m" for r in v["res"] if r)
        t.append(f"- {v['name']}: {v['sheets']} {'Blatt' if v['sheets'] == 1 else 'Blätter'}, {_years(v)}, "
                 f"Auflösung {res}, "
                 f"STAC-Collection {v['collection']} (data.geo.admin.ch)")
    t += ["", "Lizenz: " + LICENSE_LINE]
    return "\n".join(t) + "\n"


if __name__ == "__main__":
    sc = [int(x) for x in sys.argv[1].split(",")]
    bb = tuple(float(x) for x in sys.argv[2:6]) if len(sys.argv) >= 6 else None
    print(quellstand_text(sc, bb, "Test"))
    print(copyright_lines(sc, bb))
