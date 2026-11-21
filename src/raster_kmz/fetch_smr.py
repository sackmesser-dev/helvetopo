"""Lädt Swiss-Map-Raster-Blätter (neueste Ausgabe, Variante krel) per STAC, fortsetzbar.

Aufrufe:
  python3 fetch_smr.py                                   # Testgebiet, SMR25/50/100
  python3 fetch_smr.py --region ch --dry-run             # Volumen Schweiz abschätzen
  python3 fetch_smr.py --region ch --scales 25 50 100 200 --max-gb 150
Ziel:   $HELVETOPO_DATA/smr/pk<scale>/
- Nur Blätter, die Schweiz/Liechtenstein (swissBOUNDARIES3D, 2 km Puffer) berühren.
- Vorhandene Dateien mit passender Grösse werden übersprungen; abgebrochene Downloads setzt
  curl fort (-C -). Nach jeder Datei wird manifest.json ergänzt (Einträge nach Dateiname),
  bei SMR10 manifest_pk10.json.
- Download nacheinander (kein paralleles Scraping); nur die HEAD-Abfragen laufen parallel.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

import stac

DEST = paths.SMR_DIR
GPKG = paths.BOUNDARIES_GPKG
CH_BBOX = (5.90, 45.80, 10.55, 47.85)
TEST_BBOX = (9.0, 47.2, 9.5, 47.5)


def land_geometry(buffer_m: float = 2000):
    """CH+LI als WGS84-Geometrie (OGR), gepuffert."""
    from osgeo import ogr, osr
    ogr.UseExceptions()
    ds = ogr.Open(str(GPKG))  # Referenz halten, sonst ist der Layer ungültig
    lyr = ds.GetLayerByName("tlm_landesgebiet")
    lyr.SetAttributeFilter("icc IN ('CH','LI')")
    geom = None
    for f in lyr:
        g = f.GetGeometryRef().Clone()
        g.FlattenTo2D()
        g = g.SimplifyPreserveTopology(50).Buffer(buffer_m, 4)
        geom = g if geom is None else geom.Union(g)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    geom.Transform(osr.CoordinateTransformation(lyr.GetSpatialRef(), dst))
    return geom


def bbox_geom(b):
    from osgeo import ogr
    w, s, e, n = b
    return ogr.CreateGeometryFromWkt(
        f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))")


def head_size(href: str) -> int:
    for i in range(4):
        try:
            r = urllib.request.urlopen(urllib.request.Request(href, method="HEAD",
                                                              headers=stac.UA), timeout=60)
            return int(r.headers["Content-Length"])
        except Exception:  # noqa: BLE001 – Netzfehler: erneut versuchen
            time.sleep(2 ** i)
    raise RuntimeError(f"HEAD fehlgeschlagen: {href}")


def select(scales, bbox, land) -> list[dict]:
    assets = []
    for scale in scales:
        for a in stac.latest_assets(scale, bbox):
            if land is not None and not bbox_geom(a["bbox"]).Intersects(land):
                continue
            assets.append(a)
    with cf.ThreadPoolExecutor(8) as ex:
        for a, size in zip(assets, ex.map(lambda x: head_size(x["href"]), assets)):
            a["size"] = size
    return assets


def manifest_name(scale: int) -> str:
    """SMR10 hat ein eigenes Manifest (nur geladene Blätter, src/raster_img/quellstand.py)."""
    return "manifest_pk10.json" if scale == 10 else "manifest.json"


def load_manifest(dest: pathlib.Path, name: str = "manifest.json") -> dict:
    p = dest / name
    if p.exists():
        return {a["name"]: a for a in json.loads(p.read_text())}
    return {}


def save_manifest(dest: pathlib.Path, man: dict, name: str = "manifest.json") -> None:
    tmp = dest / (name + ".tmp")
    tmp.write_text(json.dumps(sorted(man.values(), key=lambda a: (a["scale"], a["sheet"])),
                              indent=1))
    tmp.replace(dest / name)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--region", choices=["testgebiet", "ch"], default="testgebiet")
    ap.add_argument("--bbox", nargs=4, type=float, help="überschreibt --region")
    ap.add_argument("--scales", nargs="+", type=int, default=[25, 50, 100])
    ap.add_argument("--dest", type=pathlib.Path, default=DEST)
    ap.add_argument("--dry-run", action="store_true", help="nur Volumen anzeigen")
    ap.add_argument("--max-gb", type=float, default=150, help="Abbruch, wenn Gesamtvolumen grösser")
    args = ap.parse_args()

    if args.bbox:
        bbox, land = tuple(args.bbox), None
    elif args.region == "ch":
        bbox, land = CH_BBOX, land_geometry()
    else:
        bbox, land = TEST_BBOX, None
    assets = select(args.scales, bbox, land)
    have = 0
    for a in assets:
        t = args.dest / f"pk{a['scale']}" / a["name"]
        a["present"] = t.exists() and t.stat().st_size == a["size"]
        have += a["size"] if a["present"] else 0
    total = sum(a["size"] for a in assets)
    for s in args.scales:
        sel = [a for a in assets if a["scale"] == s]
        gb = sum(a["size"] for a in sel) / 2**30
        years = sorted({a["year"] for a in sel})
        print(f"SMR{s}: {len(sel)} Blätter, {gb:.1f} GiB, Ausgaben {years}")
    print(f"Gesamt {len(assets)} Blätter, {total / 2**30:.1f} GiB, davon vorhanden "
          f"{have / 2**30:.1f} GiB, zu laden {(total - have) / 2**30:.1f} GiB", flush=True)
    if args.dry_run:
        return
    if total / 2**30 > args.max_gb:
        sys.exit(f"Abbruch: {total / 2**30:.1f} GiB > --max-gb {args.max_gb}")

    mans = {n: load_manifest(args.dest, n) for n in {manifest_name(s) for s in args.scales}}
    done = have
    t0 = time.time()
    for i, a in enumerate(assets, 1):
        d = args.dest / f"pk{a['scale']}"
        d.mkdir(parents=True, exist_ok=True)
        target = d / a["name"]
        if not a["present"]:
            print(f"[{i}/{len(assets)}] lade {a['name']} {a['size'] // 2**20} MiB", flush=True)
            for attempt in range(5):
                r = subprocess.run(["curl", "-sS", "-f", "-C", "-", "--retry", "3",
                                    "-o", str(target), a["href"]])
                if r.returncode == 0 and target.stat().st_size == a["size"]:
                    break
                if r.returncode == 33 or (target.exists() and target.stat().st_size > a["size"]):
                    target.unlink()  # Range nicht möglich oder kaputt: neu beginnen
                time.sleep(5 * (attempt + 1))
            else:
                sys.exit(f"Download fehlgeschlagen: {a['href']}")
            done += a["size"]
            rate = (done - have) / max(time.time() - t0, 1) / 2**20
            print(f"    {done / 2**30:.1f}/{total / 2**30:.1f} GiB, {rate:.0f} MiB/s", flush=True)
        mname = manifest_name(a["scale"])
        mans[mname][a["name"]] = {k: v for k, v in a.items() if k != "present"}
        save_manifest(args.dest, mans[mname], mname)
    print("FERTIG", flush=True)


if __name__ == "__main__":
    main()
