"""Qualitätsvergleich: Resampling und JPEG-Einstellungen gegen Dateigrösse (SMR25, 1,25 m/px).

1. Drei Testorte (Schrift/Siedlung, Höhenlinien, Fels), je eine 1024er-Kachel, gewarpt mit
   mehreren Resampling-Verfahren. Vergleichsbilder: Ausschnitt 256 px in 1:1 (wie das Gerät bei
   Pixelzoom 1:1) und 3× vergrössert (Detail).
2. JPEG-Stufen auf der Lanczos-Kachel: Grösse, PSNR, Vergleichsbild.
3. Hochrechnung der KMZ-Grösse je JPEG-Stufe über alle Kacheln eines echten Pakets
   (alpstein-smr25, 100 Kacheln), damit die Zahlen nicht nur an Einzelkacheln hängen.

Ausgabe: work/raster_kmz/quality/ (PNG-Vergleiche, quality.json)
Aufruf:  python3 quality_test.py [--no-package]
"""
from __future__ import annotations

import argparse
import io
import json
import shutil

import numpy as np
from osgeo import gdal
from PIL import Image, ImageDraw, ImageFont

import build as B
import variants as V

gdal.UseExceptions()
OUT = B.WORK / "quality"
SITES = {
    "stgallen-altstadt": (9.3770, 47.4235, "Schrift, Gebäude, Strassen"),
    "hundwiler-hoehi": (9.3200, 47.3530, "Höhenlinien, Wald, Einzelhöfe"),
    "saentis": (9.3434, 47.2494, "Fels, Gipfelkote, Wanderwege"),
}
RESAMPLING = ["bilinear", "cubic", "lanczos"]
JPEG = [(70, "420"), (75, "420"), (80, "420"), (85, "420"), (90, "420"), (85, "444")]
CROP = 256
ZOOM = 3
try:
    FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 16)
except OSError:
    FONT = ImageFont.load_default()


def tile_at(lon, lat, rs, tmp):
    dlon, dlat = B.deg_per_px(1.25, lat)
    w, n = lon - 512 * dlon, lat + 512 * dlat
    bbox = (w, n - 1024 * dlat, w + 1024 * dlon, n)
    p = {"dlon": dlon, "dlat": dlat, "width": 1024, "height": 1024}
    wp = B.warp(B.sheets_for(25, bbox), bbox, p, rs, tmp)
    a = gdal.Open(str(wp)).ReadAsArray()[:3].transpose(1, 2, 0).copy()
    wp.unlink()
    return a


def psnr(a, b):
    mse = ((a.astype(float) - b.astype(float)) ** 2).mean()
    return 10 * np.log10(255 ** 2 / mse)


def sheet(panels, title, path):
    """panels: [(label, PIL.Image)] nebeneinander, zwei Zeilen: 1:1 und ZOOM×."""
    pw = CROP * ZOOM
    W = pw * len(panels)
    H = 40 + CROP + 30 + pw
    s = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(s)
    d.text((8, 8), title, fill="black", font=FONT)
    o = (1024 - CROP) // 2
    for i, (lab, im) in enumerate(panels):
        c = im.crop((o, o, o + CROP, o + CROP))
        s.paste(c, (pw * i + (pw - CROP) // 2, 40))
        d.text((pw * i + 8, 40 + CROP + 6), lab, fill="black", font=FONT)
        s.paste(c.resize((pw, pw), Image.NEAREST), (pw * i, 40 + CROP + 30))
        d.line([(pw * i, 30), (pw * i, H)], fill=(200, 0, 0))
    s.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-package", action="store_true")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "tmp"
    tmp.mkdir(exist_ok=True)
    res = {"sites": {}, "package": {}}
    for name, (lon, lat, desc) in SITES.items():
        tiles = {rs: tile_at(lon, lat, rs, tmp) for rs in RESAMPLING}
        sheet([(rs, Image.fromarray(t)) for rs, t in tiles.items()],
              f"{name} ({desc}) – Resampling, oben 1:1, unten {ZOOM}×", OUT / f"{name}_resampling.png")
        ref = tiles["lanczos"]
        panels = [("lanczos PNG (Referenz)", Image.fromarray(ref))]
        rows = []
        for q, ss in JPEG:
            data = B.jpeg_bytes(ref, q, ss)
            dec = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))
            rows.append({"quality": q, "subsampling": ss, "kb": len(data) // 1024,
                         "psnr": round(float(psnr(dec, ref)), 2)})
            panels.append((f"q{q} {ss}: {len(data) // 1024} KB", Image.fromarray(dec)))
        sheet(panels, f"{name} ({desc}) – JPEG auf Lanczos, oben 1:1, unten {ZOOM}×",
              OUT / f"{name}_jpeg.png")
        res["sites"][name] = {"desc": desc, "jpeg": rows}
        print(name, rows)

    if not a.no_package:
        # ganzes Paket alpstein-smr25 einmal warpen, dann alle JPEG-Stufen kodieren
        cfg = V.VARIANTS["alpstein-smr25"]
        p = B.plan(cfg["bbox"], cfg["res"], 1024)
        wp = B.warp(B.sheets_for(25, cfg["bbox"]), cfg["bbox"], p, "lanczos", tmp)
        ds = gdal.Open(str(wp))
        totals = {f"q{q}_{ss}": 0 for q, ss in JPEG}
        n = 0
        for r in range(p["rows"]):
            for c in range(p["cols"]):
                x0, y0 = c * 1024, r * 1024
                tw, th = min(1024, p["width"] - x0), min(1024, p["height"] - y0)
                arr = ds.ReadAsArray(x0, y0, tw, th)[:3].transpose(1, 2, 0).copy()
                n += 1
                for q, ss in JPEG:
                    totals[f"q{q}_{ss}"] += len(B.jpeg_bytes(arr, q, ss))
        res["package"] = {"name": "alpstein-smr25", "tiles": n,
                          "mb": {k: round(v / 2**20, 1) for k, v in totals.items()},
                          "mean_kb": {k: v // n // 1024 for k, v in totals.items()}}
        print(res["package"])
    shutil.rmtree(tmp)
    (OUT / "quality.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
