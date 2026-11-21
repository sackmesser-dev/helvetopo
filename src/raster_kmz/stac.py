"""STAC-Abfrage für Swiss Map Raster (data.geo.admin.ch).

Wählt pro Kartenblatt nur die neueste Ausgabe (ältere Versionen sind laut AGENTS.md
nicht zu verwenden) und das gewünschte Asset (Variante krel, Auflösung).
"""
from __future__ import annotations

import json
import re
import urllib.request

STAC = "https://data.geo.admin.ch/api/stac/v1"
COLLECTIONS = {
    10: "ch.swisstopo.landeskarte-farbe-10",
    25: "ch.swisstopo.pixelkarte-farbe-pk25.noscale",
    50: "ch.swisstopo.pixelkarte-farbe-pk50.noscale",
    100: "ch.swisstopo.pixelkarte-farbe-pk100.noscale",
    200: "ch.swisstopo.pixelkarte-farbe-pk200.noscale",
}
UA = {"User-Agent": "Helvetopo-raster-kmz/0.1"}


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def items(scale: int, bbox: tuple[float, float, float, float]) -> list[dict]:
    url = (f"{STAC}/collections/{COLLECTIONS[scale]}/items?"
           f"bbox={','.join(map(str, bbox))}&limit=100")
    out = []
    while url:
        d = _get(url)
        out += d["features"]
        url = next((l["href"] for l in d.get("links", []) if l["rel"] == "next"), None)
    return out


def latest_assets(scale: int, bbox, variant: str = "krel") -> list[dict]:
    """Pro Blatt die neueste Ausgabe, Asset mit feinster Auflösung der Variante."""
    best: dict[str, tuple[int, dict]] = {}
    for f in items(scale, bbox):
        m = re.match(r".*_(\d{4})_([\w-]+)$", f["id"])
        if not m:  # z. B. Sammel-Items ohne Assets
            continue
        year, sheet = int(m.group(1)), m.group(2)
        if sheet not in best or year > best[sheet][0]:
            best[sheet] = (year, f)
    result = []
    for sheet, (year, f) in sorted(best.items()):
        cands = []
        for key, a in f["assets"].items():
            m = re.search(rf"_{variant}_([\d.]+)_2056\.tif$", key)
            if m:
                cands.append((float(m.group(1)), key, a["href"]))
        if not cands:
            continue
        res, key, href = min(cands)
        result.append({"scale": scale, "sheet": sheet, "year": year, "res": res,
                       "name": key, "href": href, "bbox": f["bbox"]})
    return result


if __name__ == "__main__":
    import sys
    bbox = (9.0, 47.2, 9.5, 47.5)
    for s in (25, 50, 100):
        for a in latest_assets(s, bbox):
            print(a["scale"], a["sheet"], a["year"], a["res"], a["name"], a["bbox"])
