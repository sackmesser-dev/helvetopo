#!/usr/bin/env python3
"""swissALTI3D-Kacheln (COG, LV95) für eine WGS84-BBox über den STAC-Katalog laden.

Pro 1-km-Kachel wird nur der jüngste Stand genommen. Die Prüfsumme (SHA-256-Multihash)
wird kontrolliert, vorhandene korrekte Dateien werden übersprungen. Nur Standardbibliothek.

Beispiel:
  python3 -I src/dem/download_swissalti3d.py --bbox 9.0 47.2 9.5 47.5 --gsd 2 \
      --out $HELVETOPO_DATA/swissalti3d/2m
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import re
import sys
import urllib.request

STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissalti3d/items"
UA = {"User-Agent": "Helvetopo-dem/0.1"}


def fetch_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def list_items(bbox):
    url = f"{STAC}?bbox={','.join(map(str, bbox))}&limit=100"
    while url:
        page = fetch_json(url)
        yield from page["features"]
        url = next((l["href"] for l in page.get("links", []) if l.get("rel") == "next"), None)


def sha256_ok(path, multihash):
    if not os.path.exists(path) or not multihash or not multihash.upper().startswith("1220"):
        return False
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper() == multihash[4:].upper()


def download(asset, out):
    name = asset["href"].rsplit("/", 1)[1]
    path = os.path.join(out, name)
    mh = asset.get("checksum:multihash")
    if sha256_ok(path, mh):
        return name, "ok"
    tmp = path + ".part"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(asset["href"], headers=UA), timeout=120) as r, open(tmp, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            os.replace(tmp, path)
            if mh and not sha256_ok(path, mh):
                raise IOError("Prüfsumme falsch")
            return name, "neu"
        except Exception as e:  # noqa: BLE001
            err = e
    return name, f"FEHLER {err}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    ap.add_argument("--gsd", default="2", choices=["0.5", "2"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--estimate", type=int, default=0, metavar="N",
                    help="nur Kacheln zählen und Volumen aus N zufälligen HEAD-Anfragen schätzen")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    latest = {}  # Kachel "2717-1244" -> (Jahr, Asset)
    for item in list_items(a.bbox):
        m = re.match(r"swissalti3d_(\d{4})_(\d{4}-\d{4})", item["id"])
        if not m:
            continue
        year, tile = int(m.group(1)), m.group(2)
        for key, asset in item["assets"].items():
            if key.endswith(f"_{a.gsd}_2056_5728.tif"):
                if tile not in latest or year > latest[tile][0]:
                    latest[tile] = (year, asset)
    print(f"{len(latest)} Kacheln (gsd {a.gsd} m)", file=sys.stderr)
    with open(os.path.join(a.out, "tiles.json"), "w") as f:
        json.dump({t: {"year": y, "href": s["href"]} for t, (y, s) in sorted(latest.items())}, f, indent=0)

    if a.estimate:
        import random
        sample = random.Random(1).sample(list(latest.values()), min(a.estimate, len(latest)))

        def head(v):
            req = urllib.request.Request(v[1]["href"], headers=UA, method="HEAD")
            with urllib.request.urlopen(req, timeout=60) as r:
                return int(r.headers.get("Content-Length", 0))
        with cf.ThreadPoolExecutor(4) as ex:
            sizes = list(ex.map(head, sample))
        mean = sum(sizes) / len(sizes)
        print(f"Stichprobe {len(sizes)}: Mittel {mean / 1e6:.2f} MB, Min {min(sizes) / 1e6:.2f}, "
              f"Max {max(sizes) / 1e6:.2f} → geschätzt {mean * len(latest) / 1e9:.1f} GB für {len(latest)} Kacheln",
              file=sys.stderr)
        return 0

    stats = {}
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, (name, status) in enumerate(ex.map(lambda v: download(v[1], a.out), latest.values()), 1):
            key = status.split()[0]
            stats[key] = stats.get(key, 0) + 1
            if key == "FEHLER":
                print(name, status, file=sys.stderr)
            if i % 100 == 0:
                print(f"  {i}/{len(latest)}", file=sys.stderr)
    print(stats, file=sys.stderr)
    return 1 if "FEHLER" in stats else 0


if __name__ == "__main__":
    sys.exit(main())
