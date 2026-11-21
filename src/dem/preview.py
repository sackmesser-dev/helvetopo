#!/usr/bin/env python3
"""Vorschau-PNG: Schummerung + Höhenlinien (Farben wie TYP) für einen LV95-Ausschnitt.

  .venv/bin/python src/dem/preview.py work/dem 2742000 1230000 2748000 1236000 out.png
"""
import os
import sys

import numpy as np
from osgeo import gdal

gdal.UseExceptions()
work, x0, y0, x1, y1, png = sys.argv[1], *map(float, sys.argv[2:6]), sys.argv[6]
res = 2.0
w, h = int((x1 - x0) / res), int((y1 - y0) / res)
hs = gdal.DEMProcessing("/vsimem/hs.tif", os.path.join(work, "alti3d_2m.vrt"), "hillshade",
                        options=["-multidirectional", "-z", "1.5"])
hs = gdal.Translate("/vsimem/hs2.tif", hs, projWin=[x0, y1, x1, y0], width=w, height=h).ReadAsArray().astype(float)
img = np.stack([255 - (255 - hs) * 0.45] * 3, axis=-1)
cols = {"normal": (215, 150, 60), "rock": (62, 62, 62), "glacier": (0, 136, 208)}
gpkg = os.path.join(work, "contours_lv95.gpkg")
for surf, col in cols.items():
    for major in (0, 1):
        where = f"surface='{surf}' AND " + ("CAST(ele AS INT) % 100 = 0" if major else "CAST(ele AS INT) % 100 <> 0")
        ds = gdal.Rasterize("/vsimem/r.tif", gpkg, format="GTiff", outputBounds=[x0, y0, x1, y1], width=w, height=h,
                            burnValues=[1], where=where, outputType=gdal.GDT_Byte, allTouched=bool(major))
        m = ds.ReadAsArray().astype(bool)
        img[m] = col
spots = os.path.join(work, "spot_heights.gpkg")
if os.path.exists(spots):  # Höhenkoten als schwarze Punkte, Kuppen rot umrandet zur Kontrolle
    for kind, col in (("kuppe", (200, 0, 0)), ("flach", (0, 0, 200))):
        ds = gdal.Rasterize("/vsimem/s.tif", spots, format="GTiff", outputBounds=[x0, y0, x1, y1], width=w, height=h,
                            burnValues=[1], where=f"kind='{kind}'", outputType=gdal.GDT_Byte)
        m = ds.ReadAsArray().astype(bool)
        from scipy import ndimage
        img[ndimage.binary_dilation(m, iterations=6)] = col
        img[ndimage.binary_dilation(m, iterations=3)] = (0, 0, 0)
out = gdal.GetDriverByName("MEM").Create("", w, h, 3, gdal.GDT_Byte)
for i in range(3):
    out.GetRasterBand(i + 1).WriteArray(img[..., i].clip(0, 255).astype(np.uint8))
gdal.GetDriverByName("PNG").CreateCopy(png, out)
print(png)
