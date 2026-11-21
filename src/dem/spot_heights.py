#!/usr/bin/env python3
"""Höhenkoten wie auf der Landeskarte aus swissALTI3D ableiten → OSM-PBF.

Koten entstehen auf Kuppen und lokalen Maxima (nach Dominanz gewichtet) und als Füllkoten an
flachen Stellen (Talböden, Ebenen, Sättel/Plateaus), bis eine Zieldichte erreicht ist:
Mittelland ~1 Kote je 1–2 km², Gebirge dichter. Gipfel und Pässe aus swissNAMES3D bekommen keine
zweite Kote (Abstand < 100 m) und zählen für die Dichte als vorhandene Koten.

Aufruf:
  .venv/bin/python src/dem/spot_heights.py --work work/dem --bbox 9.0 47.2 9.5 47.5
Ausgabe: work/dem/spot_heights.osm.pbf (+ spot_heights.gpkg zur Kontrolle)
Tags: natural=spot_height, ele=<m>, swisstopo:kote=yes, swisstopo:kotenart=kuppe|flach
"""
import argparse
import math
import os
import subprocess
import sys
import time

import numpy as np
from osgeo import gdal, ogr, osr
from scipy import ndimage
from scipy.spatial import cKDTree

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

gdal.UseExceptions()
ogr.UseExceptions()
NODATA = -9999.0
NAMED = ("Hauptgipfel", "Gipfel", "Alpiner Gipfel", "Huegel", "Haupthuegel", "Felskopf",
         "Pass", "Strassenpass")
WATER = ("Stehende Gewaesser", "Fliessgewaesser")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def lv95_extent(bbox, margin):
    src = osr.SpatialReference(); src.ImportFromEPSG(4326); src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(2056)
    ct = osr.CoordinateTransformation(src, dst)
    w, s, e, n = bbox
    pts = [ct.TransformPoint(x, y)[:2] for x in np.linspace(w, e, 11) for y in np.linspace(s, n, 11)]
    xs, ys = zip(*pts)
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", default="work/dem")
    ap.add_argument("--vrt", help="2-m-Mosaik (Standard: <work>/alti3d_2m.vrt)")
    ap.add_argument("--bbox", nargs=4, type=float, default=[9.0, 47.2, 9.5, 47.5])
    ap.add_argument("--names", default=str(paths.DOWNLOADS / "swissnames3d/swissnames3d_2026_2056.gpkg"))
    ap.add_argument("--tlm", default=str(paths.DOWNLOADS / "swisstlm3d/SWISSTLM3D_2026_LV95_LN02.gpkg"))
    ap.add_argument("--res", type=float, default=10.0)
    ap.add_argument("--spacing-flat", type=float, default=1000.0, help="Mindestabstand Mittelland (m)")
    ap.add_argument("--spacing-mountain", type=float, default=550.0, help="Mindestabstand Gebirge (m)")
    ap.add_argument("--mountain-relief", type=float, default=250.0, help="Relief (max-min in 1 km) ab dem Gebirge gilt")
    ap.add_argument("--named-exclude", type=float, default=100.0, help="kein Kote näher an swissNAMES3D-Gipfel/Pass (m)")
    ap.add_argument("--min-drop", type=float, default=8.0, help="Kuppe: mind. so viel über dem Mittel im Umkreis 250 m")
    ap.add_argument("--flat-slope", type=float, default=4.0, help="Füllkoten nur unter dieser Neigung (Grad)")
    ap.add_argument("--id-base", type=int, default=7_704_500_000_000)
    a = ap.parse_args()
    t0 = time.time()

    vrt = a.vrt or os.path.join(a.work, "alti3d_2m.vrt")
    x0, y0, x1, y1 = lv95_extent(a.bbox, 1500)
    r = a.res
    te = [math.floor(x0 / r) * r, math.floor(y0 / r) * r, math.ceil(x1 / r) * r, math.ceil(y1 / r) * r]
    ds = gdal.Warp("/vsimem/d10.tif", vrt, outputBounds=te, xRes=r, yRes=r, resampleAlg="average",
                   srcNodata=NODATA, dstNodata=NODATA, multithread=True)
    gt = ds.GetGeoTransform()
    dem = ds.ReadAsArray().astype(np.float32)
    valid = dem != NODATA
    z = np.where(valid, dem, np.nan)
    zf = np.where(valid, dem, np.nanmin(z))  # für Filter: Nodata tief
    sm = ndimage.gaussian_filter(zf, 1.5)
    log(f"DEM {dem.shape[1]}x{dem.shape[0]} @ {r} m")

    # Wasser (Seen, Flussflächen) ausschliessen
    water = np.zeros(dem.shape, bool)
    if a.tlm and os.path.exists(a.tlm):
        wl = ",".join(f"'{v}'" for v in WATER)
        wds = gdal.Rasterize("/vsimem/w.tif", a.tlm, format="GTiff", outputBounds=te, xRes=r, yRes=r,
                             burnValues=[1], outputType=gdal.GDT_Byte, SQLDialect="SQLITE",
                             SQLStatement=f"SELECT geom FROM tlm_bb_bodenbedeckung WHERE objektart IN ({wl})")
        water = wds.ReadAsArray().astype(bool)
    usable = valid & ~ndimage.binary_dilation(water, iterations=3) & ~ndimage.binary_dilation(~valid, iterations=5)

    # Gebirge: Relief im 1-km-Fenster
    k = int(1000 / r) | 1
    relief = ndimage.maximum_filter(sm, k) - ndimage.minimum_filter(sm, k)
    mountain = ndimage.gaussian_filter((relief >= a.mountain_relief).astype(float), 20) > 0.5
    spacing = np.where(mountain, a.spacing_mountain, a.spacing_flat)

    gy, gx = np.gradient(sm, r)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))

    # --- Kuppen: lokale Maxima mit Dominanz (grösster Radius, in dem der Punkt Maximum bleibt)
    cand = sm == ndimage.maximum_filter(sm, int(150 / r) * 2 + 1)
    mean250 = ndimage.uniform_filter(sm, int(250 / r) * 2 + 1)
    cand &= usable & ((sm - mean250) >= a.min_drop)
    dom = np.zeros(dem.shape, np.float32)
    for rad in (150, 300, 600, 1200, 2400):
        dom[cand & (sm >= ndimage.maximum_filter(sm, int(rad / r) * 2 + 1))] = rad
    iy, ix = np.nonzero(cand)
    drop = (sm - mean250)[iy, ix]
    score = dom[iy, ix] * (1 + drop / 50.0)
    peaks = [(s, y, x, "kuppe") for s, y, x in zip(score, iy, ix)]
    log(f"Kuppen-Kandidaten: {len(peaks)}")

    # --- Füllkoten: je Rasterzelle (≈ Mindestabstand) die flachste Stelle, bevorzugt tief (Talboden)
    fills = []
    for cell_m, mask in ((a.spacing_flat, ~mountain), (a.spacing_mountain, mountain)):
        c = int(cell_m / r)
        for yy in range(0, dem.shape[0], c):
            for xx in range(0, dem.shape[1], c):
                win = (slice(yy, yy + c), slice(xx, xx + c))
                ok = usable[win] & mask[win] & (slope[win] < a.flat_slope)
                if ok.sum() < 20:
                    continue
                # tief im Umfeld (Talboden) und flach: Rang aus Neigung + relativer Höhe
                loc = sm[win]
                rel = (loc - np.nanmin(np.where(ok, loc, np.nan))) / max(1.0, float(np.ptp(loc[ok])))
                cost = np.where(ok, slope[win] / a.flat_slope + rel, np.inf)
                j = np.unravel_index(np.argmin(cost), cost.shape)
                fills.append((0.0, yy + j[0], xx + j[1], "flach"))
    log(f"Füllkoten-Kandidaten: {len(fills)}")

    # --- benannte Gipfel/Pässe (swissNAMES3D)
    named = []
    if a.names and os.path.exists(a.names):
        nd = ogr.Open(a.names)
        lyr = nd.GetLayerByName("swissnames3d_pkt")
        lyr.SetAttributeFilter("objektart IN (" + ",".join(f"'{v}'" for v in NAMED) + ")")
        lyr.SetSpatialFilterRect(te[0], te[1], te[2], te[3])
        named = [f.GetGeometryRef().GetPoint_2D(0) for f in lyr]
    log(f"swissNAMES3D Gipfel/Pässe im Gebiet: {len(named)}")
    ntree = cKDTree(np.array(named)) if named else None

    # --- gierige Auswahl: Kuppen nach Score, dann Füllkoten
    def xy(y, x):
        return gt[0] + (x + 0.5) * gt[1], gt[3] + (y + 0.5) * gt[5]

    accepted = []  # (x, y)
    taken = list(named)
    tree = cKDTree(np.array(taken)) if taken else None
    added = []
    peaks.sort(key=lambda p: -p[0])
    for group in (peaks, fills):
        for s, y, x, kind in group:
            px, py = xy(y, x)
            if ntree is not None and ntree.query_ball_point((px, py), a.named_exclude):
                continue
            d = spacing[y, x]
            if tree is not None and tree.query_ball_point((px, py), d):
                continue
            if added and cKDTree(np.array(added)).query_ball_point((px, py), d):
                continue
            added.append((px, py))
            accepted.append((px, py, kind, y, x))
            if len(added) % 200 == 0:  # Baum gelegentlich neu aufbauen
                taken += added; added = []; tree = cKDTree(np.array(taken))
    log(f"Koten gewählt: {len(accepted)}, davon Kuppen {sum(p[2] == 'kuppe' for p in accepted)}")

    # Höhe aus dem 2-m-Modell: Kuppe = Maximum im 20-m-Umkreis, flach = Wert am Punkt
    src = gdal.Open(vrt)
    sgt = src.GetGeoTransform(); band = src.GetRasterBand(1)
    out = []
    for px, py, kind, y, x in accepted:
        cx, cy = int((px - sgt[0]) / sgt[1]), int((py - sgt[3]) / sgt[5])
        w = 10 if kind == "kuppe" else 1
        try:
            arr = band.ReadAsArray(cx - w, cy - w, 2 * w + 1, 2 * w + 1)
        except RuntimeError:
            continue
        if arr is None:
            continue
        m = arr != NODATA
        if not m.any():
            continue
        if kind == "kuppe":
            k2 = np.unravel_index(np.argmax(np.where(m, arr, -1e9)), arr.shape)
            px, py = sgt[0] + (cx - w + k2[1] + 0.5) * sgt[1], sgt[3] + (cy - w + k2[0] + 0.5) * sgt[5]
            ele = float(arr[k2])
        else:
            ele = float(arr[w, w]) if m[w, w] else float(arr[m].mean())
        out.append((px, py, round(ele), kind))

    # Zuschneiden auf die WGS84-BBox, GPKG und PBF schreiben
    s2056 = osr.SpatialReference(); s2056.ImportFromEPSG(2056)
    s4326 = osr.SpatialReference(); s4326.ImportFromEPSG(4326); s4326.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(s2056, s4326)
    gpkg = os.path.join(a.work, "spot_heights.gpkg")
    if os.path.exists(gpkg):
        os.remove(gpkg)
    gds = ogr.GetDriverByName("GPKG").CreateDataSource(gpkg)
    gl = gds.CreateLayer("spot_heights", s2056, ogr.wkbPoint)
    gl.CreateField(ogr.FieldDefn("ele", ogr.OFTInteger)); gl.CreateField(ogr.FieldDefn("kind", ogr.OFTString))
    opl = os.path.join(a.work, "spot_heights.opl")
    nid = a.id_base
    w_, s_, e_, n_ = a.bbox
    stats = {"kuppe": 0, "flach": 0}
    with open(opl, "w") as f:
        for px, py, ele, kind in out:
            lon, lat = ct.TransformPoint(px, py)[:2]
            if not (w_ <= lon <= e_ and s_ <= lat <= n_):
                continue
            ft = ogr.Feature(gl.GetLayerDefn())
            g = ogr.Geometry(ogr.wkbPoint); g.AddPoint_2D(px, py); ft.SetGeometry(g)
            ft["ele"] = ele; ft["kind"] = kind; gl.CreateFeature(ft)
            nid += 1
            f.write(f"n{nid} v1 x{lon:.7f} y{lat:.7f} Tnatural=spot_height,ele={ele},"
                    f"swisstopo:kote=yes,swisstopo:kotenart={kind}\n")
            stats[kind] += 1
    gds = None
    pbf = os.path.join(a.work, "spot_heights.osm.pbf")
    subprocess.run(["osmium", "cat", "--overwrite", "-o", pbf, opl], check=True)
    os.remove(opl)
    log(f"{pbf}: {sum(stats.values())} Koten {stats}, {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
