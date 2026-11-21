#!/usr/bin/env python3
"""Höhendaten für die ganze Schweiz (+FL) kachelweise und fortsetzbar rechnen.

Stufen:
  mosaic    VRT über alle geladenen 2-m-Kacheln
  hgt       1°-HGT-Kacheln (1") für den Perimeter, --dem-poly = Perimeter
  blocks    Höhenlinien + Höhenkoten je Block (Standard 0,5° × 0,3°), parallel, mit Fertig-Marke
  merge     Block-PBF zu contours.osm.pbf und spot_heights.osm.pbf zusammenführen

  nohup .venv/bin/python src/dem/run_ch.py --work work/dem/ch --jobs 3 \
      --wait-download downloads/swissalti3d/download-ch-2m.log > work/dem/ch/run.log 2>&1 &

Abgebrochene Läufe einfach neu starten: fertige HGT und Blöcke (Datei DONE) werden übersprungen.
ID-Bereiche: Höhenlinien 7 703 000 000 000 + Block × 2·10⁹, Koten 7 704 500 000 000 + Block × 10⁷.
"""
import argparse
import concurrent.futures as cf
import glob
import json
import os
import subprocess
import sys
import time

from osgeo import ogr

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

ogr.UseExceptions()
HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


def run(cmd, logfile):
    with open(logfile, "a") as lf:
        lf.write("$ " + " ".join(cmd) + "\n"); lf.flush()
        subprocess.run(cmd, check=True, stdout=lf, stderr=subprocess.STDOUT)


def wait_download(path):
    """Warten, bis der Download-Log die Schlussstatistik ('{...}') enthält."""
    while True:
        try:
            last = open(path).read().strip().splitlines()[-1]
            if last.startswith("{"):
                log(f"Download fertig: {last}")
                return
        except (OSError, IndexError):
            pass
        time.sleep(120)


def blocks(perimeter_geojson, bw, bh, origin=(5.9, 45.8)):
    geom = ogr.CreateGeometryFromJson(json.dumps(json.load(open(perimeter_geojson))["geometry"]))
    w, e, s, n = geom.GetEnvelope()
    out = []
    i = 0
    while origin[0] + i * bw < e:
        j = 0
        while origin[1] + j * bh < n:
            x0, y0 = round(origin[0] + i * bw, 6), round(origin[1] + j * bh, 6)
            box = ogr.CreateGeometryFromWkt(
                f"POLYGON(({x0} {y0},{x0 + bw} {y0},{x0 + bw} {y0 + bh},{x0} {y0 + bh},{x0} {y0}))")
            if box.Intersects(geom):
                out.append((f"b{i:02d}_{j:02d}", [x0, y0, round(x0 + bw, 6), round(y0 + bh, 6)]))
            j += 1
        i += 1
    return out


def do_block(k, bid, bbox, a):
    d = os.path.join(a.work, "blocks", bid)
    if os.path.exists(os.path.join(d, "DONE")):
        return bid, "vorhanden", 0
    os.makedirs(d, exist_ok=True)
    lf = os.path.join(d, "build.log")
    t0 = time.time()
    bb = [str(v) for v in bbox]
    base_c = 7_703_000_000_000 + k * 2_000_000_000
    run([PY, os.path.join(HERE, "build_dem.py"), "contours", "--bbox", *bb, "--vrt", a.vrt, "--work", d], lf)
    run([PY, os.path.join(HERE, "build_dem.py"), "pbf", "--bbox", *bb, "--vrt", a.vrt, "--work", d,
         "--node-id-base", str(base_c), "--way-id-base", str(base_c)], lf)
    run([PY, os.path.join(HERE, "spot_heights.py"), "--bbox", *bb, "--vrt", a.vrt, "--work", d,
         "--id-base", str(7_704_500_000_000 + k * 10_000_000)], lf)
    # Zwischenstände löschen (gross), Ergebnis-PBF und Kontroll-GPKG behalten
    for f in ("alti3d_5m.tif", "surface.tif", "contours_lv95.gpkg"):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    dt = time.time() - t0
    with open(os.path.join(d, "DONE"), "w") as f:
        f.write(f"{dt:.0f}\n")
    return bid, "fertig", dt


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(paths.DOWNLOADS / "swissalti3d/2m"))
    ap.add_argument("--work", default="work/dem/ch")
    ap.add_argument("--perimeter", default="work/perimeter/ch_fl.geojson")
    ap.add_argument("--poly", default="work/perimeter/ch_fl.poly")
    ap.add_argument("--block", nargs=2, type=float, default=[0.5, 0.3], metavar=("DLON", "DLAT"))
    ap.add_argument("--jobs", type=int, default=3, help="parallele Blöcke (je ~3–5 GB RAM)")
    ap.add_argument("--stages", default="mosaic,hgt,blocks,merge")
    ap.add_argument("--only", help="nur diese Block-IDs (Komma)")
    ap.add_argument("--hgt-arcsec", default="0.5", help="HGT-Rasterweite in Bogensekunden (0.5 oder 1)")
    ap.add_argument("--wait-download", help="Download-Log; erst rechnen, wenn der Download fertig ist")
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    a.vrt = os.path.join(a.work, "alti3d_2m.vrt")
    stages = a.stages.split(",")
    t0 = time.time()
    if a.wait_download:
        wait_download(a.wait_download)

    bbox = open(os.path.join(os.path.dirname(a.poly), "bbox.txt")).read().strip().split(",")
    if "mosaic" in stages:
        log("Mosaik …")
        run([PY, os.path.join(HERE, "build_dem.py"), "mosaic", "--src", a.src, "--vrt", a.vrt,
             "--work", a.work], os.path.join(a.work, "mosaic.log"))
        log(f"Mosaik: {len(glob.glob(os.path.join(a.src, '*.tif')))} Kacheln")
    if "hgt" in stages:
        log("HGT …")
        t = time.time()
        run([PY, os.path.join(HERE, "build_dem.py"), "hgt", "--bbox", *bbox, "--vrt", a.vrt, "--work", a.work,
             "--hgt-arcsec", a.hgt_arcsec, "--hgt-out", os.path.join(a.work, f"hgt{a.hgt_arcsec}"),
             "--poly", a.poly], os.path.join(a.work, "hgt.log"))
        log(f"HGT {a.hgt_arcsec}\" fertig in {time.time() - t:.0f} s: "
            f"{len(glob.glob(os.path.join(a.work, f'hgt{a.hgt_arcsec}', '*.hgt')))} Kacheln")
    if "blocks" in stages:
        bl = blocks(a.perimeter, *a.block)
        if a.only:
            keep = set(a.only.split(","))
            bl = [b for b in bl if b[0] in keep]
        log(f"{len(bl)} Blöcke, {a.jobs} parallel")
        index = {bid: k for k, (bid, _) in enumerate(blocks(a.perimeter, *a.block))}
        with cf.ThreadPoolExecutor(a.jobs) as ex:
            futs = {ex.submit(do_block, index[bid], bid, bb, a): bid for bid, bb in bl}
            done = 0
            for fu in cf.as_completed(futs):
                done += 1
                try:
                    bid, st, dt = fu.result()
                    log(f"[{done}/{len(bl)}] {bid} {st} ({dt:.0f} s)")
                except subprocess.CalledProcessError as e:
                    log(f"[{done}/{len(bl)}] {futs[fu]} FEHLER {e} (Log im Blockordner)")
    if "merge" in stages:
        for name in ("contours", "spot_heights"):
            parts = sorted(glob.glob(os.path.join(a.work, "blocks", "*", f"{name}.osm.pbf")))
            out = os.path.join(a.work, f"{name}.osm.pbf")
            run(["osmium", "merge", "--overwrite", "-o", out, *parts], os.path.join(a.work, "merge.log"))
            log(f"{out}: {len(parts)} Blöcke, {os.path.getsize(out) / 1e6:.0f} MB")
    log(f"fertig in {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
