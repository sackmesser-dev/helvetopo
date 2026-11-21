"""SWISSIMAGE 10 cm (STAC `ch.swisstopo.swissimage-dop10`) für ein Gebiet laden.

Das Kachelwerk besteht aus 1-km-Kacheln (LV95, Name `<Jahr>_<E>-<N>`). Jede Kachel gibt es für jedes
Befliegungsjahr als eigenes STAC-Item mit zwei Assets:
- `…_0.1_2056.tif`: 10 cm (25 cm im Hochgebirge), COG mit JPEG q95 und Übersichten 0,2/0,4/0,8/1,6/3,2 m,
  ca. 65 MB je Kachel;
- `…_2_2056.tif`: 2 m, COG, ca. 0,15 MB je Kachel.

Geladen wird je Kachel nur das neueste Jahr:
- `2m/`: das 2-m-Asset unverändert (Quelle der groben Zoomstufen);
- `fein/`: aus dem 10-cm-COG nur eine interne Übersicht (Standard 0,4 m), per HTTP-Range-Abfrage
  mit GDAL `/vsicurl/`. Es wird also nicht die volle 10-cm-Datei übertragen, sondern ca. 1/16.

`manifest.json` hält je Kachel Jahr, BBox (WGS84), Item-ID und Asset-URLs fest (Quellstand).

Aufruf:
  python3 -I swissimage.py --bbox 9.00 47.20 9.50 47.50 [--fine 0.4] [--jobs 8] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from multiprocessing.pool import ThreadPool

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

COLLECTION = "ch.swisstopo.swissimage-dop10"
STAC = f"https://data.geo.admin.ch/api/stac/v0.9/collections/{COLLECTION}/items"
DL = str(paths.DOWNLOADS / "swissimage")
OVR = {0.2: 0, 0.4: 1, 0.8: 2, 1.6: 3}       # Übersichtsstufe im 10-cm-COG (GDAL -ovr)


def stac_items(bbox) -> list[dict]:
    """Alle Items, die die Box berühren (alle Jahre)."""
    url = STAC + "?" + urllib.parse.urlencode({"bbox": ",".join(map(repr, bbox)), "limit": 100})
    out = []
    while url:
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.load(r)
        out += d["features"]
        url = next((lk["href"] for lk in d.get("links", []) if lk.get("rel") == "next"), None)
    return out


def latest_per_tile(items) -> list[dict]:
    best: dict[str, dict] = {}
    for it in items:
        _, year, tile = it["id"].rsplit("_", 2)
        if tile not in best or int(year) > best[tile]["year"]:
            a = {k: v["href"] for k, v in it["assets"].items()}
            best[tile] = dict(tile=tile, year=int(year), item=it["id"], bbox=it["bbox"],
                              updated=it["properties"].get("updated"),
                              fine=next(h for k, h in a.items() if k.endswith("_0.1_2056.tif")),
                              coarse=next(h for k, h in a.items() if k.endswith("_2_2056.tif")))
    return sorted(best.values(), key=lambda m: m["tile"])


def load_manifest() -> list[dict]:
    p = os.path.join(DL, "manifest.json")
    return json.load(open(p)) if os.path.exists(p) else []


def save_manifest(entries: list[dict]):
    old = {m["tile"]: m for m in load_manifest()}
    old.update({m["tile"]: m for m in entries})
    os.makedirs(DL, exist_ok=True)
    tmp = os.path.join(DL, "manifest.json.part")
    with open(tmp, "w") as f:
        json.dump(sorted(old.values(), key=lambda m: m["tile"]), f, indent=0)
    os.replace(tmp, os.path.join(DL, "manifest.json"))


def fine_dir(res: float) -> str:
    return os.path.join(DL, f"fein_{res:g}m")


def fetch(job) -> tuple[str, int]:
    m, res = job
    n = 0
    c = os.path.join(DL, "2m", f"{m['tile']}.tif")
    if not os.path.exists(c):
        os.makedirs(os.path.dirname(c), exist_ok=True)
        urllib.request.urlretrieve(m["coarse"], c + ".part")
        os.replace(c + ".part", c)
        n += os.path.getsize(c)
    if res is None:                  # nur 2-m-Asset (Luftbild kompakt)
        return m["tile"], n
    f = os.path.join(fine_dir(res), f"{m['tile']}.tif")
    if not os.path.exists(f):
        os.makedirs(os.path.dirname(f), exist_ok=True)
        subprocess.run(["gdal_translate", "-q", "-ovr", str(OVR[res]), "-co", "TILED=YES", "-co", "COMPRESS=JPEG",
                        "-co", "PHOTOMETRIC=YCBCR", "-co", "JPEG_QUALITY=92", "/vsicurl/" + m["fine"], f + ".part.tif"],
                       check=True, env={**os.environ, "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
                                        "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif"})
        os.replace(f + ".part.tif", f)
        n += os.path.getsize(f)
    return m["tile"], n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), required=True)
    ap.add_argument("--fine", type=float, default=0.4, choices=sorted(OVR))
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    items = stac_items(a.bbox)
    tiles = latest_per_tile(items)
    years: dict[int, int] = {}
    for m in tiles:
        years[m["year"]] = years.get(m["year"], 0) + 1
    print(f"{len(items)} Items, {len(tiles)} Kacheln (neuestes Jahr je Kachel: {dict(sorted(years.items()))})")
    save_manifest(tiles)
    if a.dry_run:
        return
    done, nbytes = 0, 0
    with ThreadPool(a.jobs) as pool:
        for _, n in pool.imap_unordered(fetch, [(m, a.fine) for m in tiles]):
            done += 1
            nbytes += n
            if done % 50 == 0 or done == len(tiles):
                print(f"  {done}/{len(tiles)} Kacheln, {nbytes / 1e9:.2f} GB neu", flush=True)


if __name__ == "__main__":
    main()
