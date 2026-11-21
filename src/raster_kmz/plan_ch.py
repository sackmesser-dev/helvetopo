"""Hochrechnung: Kacheln und KMZ-Pakete für die ganze Schweiz.

Rastert das Landesgebiet (swissBOUNDARIES3D, OGD) auf das Kachelraster jeder Auflösungsstufe
(1 Rasterpixel = 1 Kachel, ALL_TOUCHED) und zählt:
  - Kacheln, die die Schweiz berühren (Kacheln ausserhalb würden weggelassen)
  - Pakete bei quadratischen Paketen von k × k Kacheln (k = 22 → ≤ 484, k = 10 → ≤ 100)
  - Kacheln je Kanton (für kantonale Pakete)
Die mittlere JPEG-Grösse stammt aus den Testbuilds (≈ 330–350 KB bei q85/4:2:0).

Aufruf: python3 plan_ch.py [--json work/raster_kmz/plan_ch.json]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import sys

import numpy as np
from osgeo import gdal, ogr, osr

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

import build as B

gdal.UseExceptions()
ogr.UseExceptions()

GPKG = paths.BOUNDARIES_GPKG
LEVELS = [("SMR25", 1.25), ("SMR50", 2.5), ("SMR100", 5.0), ("SMR200", 10.0)]
JPEG_KB = 340
TILE = 1024


def layer_4326(layer_name: str, where: str | None = None):
    """Gibt (Memory-Datasource, Layer) in EPSG:4326 zurück."""
    src = ogr.Open(str(GPKG))
    lyr = src.GetLayerByName(layer_name)
    if where:
        lyr.SetAttributeFilter(where)
    srs = osr.SpatialReference(); srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(lyr.GetSpatialRef(), srs)
    mem = ogr.GetDriverByName("MEM").CreateDataSource("m")
    out = mem.CreateLayer("l", srs, ogr.wkbMultiPolygon)
    out.CreateField(ogr.FieldDefn("name", ogr.OFTString))
    for f in lyr:
        g = f.GetGeometryRef().Clone()
        g.FlattenTo2D(); g.Transform(ct)
        g = g.SimplifyPreserveTopology(0.0002)  # ≈ 20 m, reicht für Kachelzählung
        nf = ogr.Feature(out.GetLayerDefn())
        nf.SetGeometry(g); nf.SetField("name", f.GetField("name"))
        out.CreateFeature(nf)
    return mem, out


def tile_mask(lyr, bbox, res_m: float, where: str | None = None) -> np.ndarray:
    w, s, e, n = bbox
    dlon, dlat = B.deg_per_px(res_m, (s + n) / 2)
    tw, th = dlon * TILE, dlat * TILE
    cols, rows = math.ceil((e - w) / tw), math.ceil((n - s) / th)
    ds = gdal.GetDriverByName("MEM").Create("", cols, rows, 1, gdal.GDT_Byte)
    ds.SetGeoTransform((w, tw, 0, n, 0, -th))
    srs = osr.SpatialReference(); srs.ImportFromEPSG(4326)
    ds.SetProjection(srs.ExportToWkt())
    lyr.SetAttributeFilter(where)
    gdal.RasterizeLayer(ds, [1], lyr, burn_values=[1], options=["ALL_TOUCHED=TRUE"])
    lyr.SetAttributeFilter(None)
    return ds.ReadAsArray().astype(bool)


def packages(mask: np.ndarray, k: int) -> list[int]:
    rows, cols = mask.shape
    out = []
    for r in range(0, rows, k):
        for c in range(0, cols, k):
            n = int(mask[r:r + k, c:c + k].sum())
            if n:
                out.append(n)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=pathlib.Path,
                    default=B.WORK / "plan_ch.json")
    a = ap.parse_args()
    _m1, ch = layer_4326("tlm_landesgebiet", "icc = 'CH'")
    _m2, kt = layer_4326("tlm_kantonsgebiet")
    canton_names = sorted({f.GetField("name") for f in kt})
    kt.ResetReading()
    w, e, s, n = ch.GetExtent()
    bbox = (w, s, e, n)
    result = {"bbox_ch": bbox, "levels": []}
    for name, res in LEVELS:
        mask = tile_mask(ch, bbox, res)
        p100 = packages(mask, 10)
        p484 = packages(mask, 22)
        cantons = {}
        for cn in canton_names:
            cm = tile_mask(kt, bbox, res, f"name = '{cn.replace(chr(39), chr(39) * 2)}'")
            cantons[cn] = int(cm.sum())
        lvl = {
            "level": name, "res_m": res, "grid": list(mask.shape[::-1]),
            "tiles_bbox": int(mask.size), "tiles_ch": int(mask.sum()),
            "gb": round(mask.sum() * JPEG_KB / 2**20, 1),
            "packages_484": len(p484), "packages_484_max": max(p484),
            "packages_100": len(p100),
            "tile_km": round(res * TILE / 1000, 2),
            "package_484_km": round(res * TILE * 22 / 1000, 1),
            "cantons": dict(sorted(cantons.items(), key=lambda x: -x[1])),
        }
        result["levels"].append(lvl)
        print(f"{name:7s} {res:5.2f} m/px  Kachel {lvl['tile_km']:5.2f} km  "
              f"Kacheln CH {lvl['tiles_ch']:6d} (Rechteck {lvl['tiles_bbox']:6d})  "
              f"≈ {lvl['gb']:5.1f} GB  Pakete ≤484: {lvl['packages_484']:3d} "
              f"(je {lvl['package_484_km']} km)  Pakete ≤100: {lvl['packages_100']:4d}")
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print("Kantone SMR25:", result["levels"][0]["cantons"])


if __name__ == "__main__":
    main()
