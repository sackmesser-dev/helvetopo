#!/usr/bin/env python3
"""swissALTI3D → HGT (für mkgmap --dem) und Höhenlinien (OSM-PBF) nach Landeskarten-Vorbild.

Aufruf (im venv mit GDAL-Bindings, numpy, scipy):
  .venv/bin/python src/dem/build_dem.py all --bbox 9.0 47.2 9.5 47.5 \
      --src $HELVETOPO_DATA/swissalti3d/2m \
      --tlm $HELVETOPO_DATA/swisstlm3d/SWISSTLM3D_2026_LV95_LN02.gpkg \
      --work work/dem

Stufen (einzeln aufrufbar): mosaic, hgt, contours, pbf, all.
Details und Parameterwahl: docs/vektor/hoehen.md.
"""
import argparse
import glob
import json
import math
import os
import subprocess
import sys
import time

import numpy as np
from osgeo import gdal, ogr, osr
from scipy import ndimage

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

gdal.UseExceptions()
ogr.UseExceptions()

NODATA = -9999.0
HGT_VOID = -32768

# swissTLM3D-Bodenbedeckung → Kurvenfarbe wie Landeskarte (schwarz im Fels/Geröll, blau auf Gletscher)
ROCK = ("Fels", "Fels locker", "Felsbloecke", "Felsbloecke locker", "Lockergestein")
GLACIER = ("Gletscher", "Schneefeld Toteis")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def run(cmd):
    log("$ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------- Mosaik
def stage_mosaic(a):
    vrt = a.vrt
    tifs = sorted(glob.glob(os.path.join(a.src, "*.tif")))
    lst = os.path.splitext(vrt)[0] + ".txt"
    with open(lst, "w") as f:
        f.write("\n".join(tifs) + "\n")
    run(["gdalbuildvrt", "-q", "-overwrite", "-input_file_list", lst, vrt])
    return vrt


# ---------------------------------------------------------------- HGT
def hgt_tiles(bbox):
    w, s, e, n = bbox
    for lat in range(math.floor(s), math.ceil(n)):
        for lon in range(math.floor(w), math.ceil(e)):
            yield lat, lon


def hgt_name(lat, lon):
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}.hgt"


def relief_adaptive_smooth(arr, valid, lat, step, a):
    """Mikrorelief im Hügelland dämpfen, Gebirge unverändert lassen (Schummerung).

    Relief = max−min im Fenster von a.relief_window m. Unter a.relief_low wird voll mit
    Gauss σ = a.hgt_smooth m geglättet, über a.relief_high gar nicht, dazwischen linear gemischt.
    Höhen ändern sich nur im Hügelland und dort um wenige Meter (siehe Log: p99, max).
    """
    m_per_px = step * 111320.0  # N–S; O–W ist kürzer, für Glättung und Fenster unerheblich
    sm = masked_gaussian(arr, valid, a.hgt_smooth / m_per_px)
    k = max(3, int(a.relief_window / m_per_px) | 1)
    filled = np.where(valid, arr, np.nan)
    lo = np.nan_to_num(filled, nan=1e6); hi = np.nan_to_num(filled, nan=-1e6)
    relief = ndimage.maximum_filter(hi, k) - ndimage.minimum_filter(lo, k)
    relief = ndimage.uniform_filter(np.clip(relief, 0, 5000), k)  # weiche Übergänge
    w = np.clip((relief - a.relief_low) / (a.relief_high - a.relief_low), 0, 1)
    out = np.where(valid, w * arr + (1 - w) * sm, NODATA).astype(np.float32)
    d = np.abs(out - arr)[valid]
    log(f"  Glättung Hügelland: Höhenänderung p99 {np.percentile(d, 99):.1f} m, max {d.max():.1f} m, "
        f"Anteil geglättet (w<1) {np.mean(w[valid] < 1) * 100:.0f} %")
    return out


def stage_hgt(a):
    """1°-Kacheln im SRTM-Schema: (3600/arcsec + 1)² Punkte, Pixelmitte auf ganzen Bogensekunden.

    Ausserhalb der swissALTI3D-Abdeckung (Ausland, nicht geladene Kacheln) steht der
    SRTM-Void-Wert -32768. mkgmap wertet nur das Gebiet in --dem-poly aus.
    """
    vrt = a.vrt
    out = a.hgt_out or os.path.join(a.work, f"hgt{a.hgt_arcsec:g}")
    os.makedirs(out, exist_ok=True)
    n = int(round(3600 / a.hgt_arcsec)) + 1
    step = a.hgt_arcsec / 3600.0
    for lat, lon in hgt_tiles(a.bbox):
        path = os.path.join(out, hgt_name(lat, lon))
        if os.path.exists(path) and not a.force:  # fortsetzbar: fertige Kacheln überspringen
            log(f"{path} vorhanden, übersprungen")
            continue
        tif = os.path.join(a.work, f"tmp_{hgt_name(lat, lon)}.tif")
        # average: jeder HGT-Punkt mittelt die 2-m-Zellen seiner Fläche (Antialiasing)
        run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326",
             "-te", str(lon - step / 2), str(lat - step / 2), str(lon + 1 + step / 2), str(lat + 1 + step / 2),
             "-ts", str(n), str(n), "-r", "average", "-srcnodata", str(NODATA), "-dstnodata", str(NODATA),
             "-ot", "Float32", "-multi", "-wo", "NUM_THREADS=ALL_CPUS", "-co", "COMPRESS=DEFLATE",
             "-co", "TILED=YES", vrt, tif])
        arr = gdal.Open(tif).ReadAsArray()
        valid = arr != NODATA
        if a.hgt_smooth > 0 and valid.any():
            arr = relief_adaptive_smooth(arr, valid, lat, step, a)
        hgt = np.full(arr.shape, HGT_VOID, dtype=">i2")
        hgt[valid] = np.round(arr[valid]).astype(np.int16)
        if not valid.any():
            os.remove(tif)
            log(f"{path}: keine Daten, nicht geschrieben")
            continue
        hgt.tofile(path + ".part")
        os.replace(path + ".part", path)
        os.remove(tif)
        log(f"{path}: {n}x{n}, gültig {valid.mean() * 100:.1f} %")
    if a.poly:
        import shutil
        shutil.copy(a.poly, os.path.join(out, "dem.poly"))
    else:
        write_dem_poly(a, os.path.join(out, "dem.poly"))


def write_dem_poly(a, path):
    """Polygon für mkgmap --dem-poly: BBox (osmosis-poly-Format), wenn kein --poly gegeben ist."""
    w, s, e, n = a.bbox
    with open(path, "w") as f:
        f.write(f"dem\n1\n   {w} {s}\n   {e} {s}\n   {e} {n}\n   {w} {n}\n   {w} {s}\nEND\nEND\n")
    log(f"{path} geschrieben")


# ---------------------------------------------------------------- Höhenlinien
def lv95_grid(a):
    """5-m-Raster in LV95 (EPSG:2056) das die WGS84-BBox abdeckt (+ Rand für die Glättung)."""
    src = osr.SpatialReference(); src.ImportFromEPSG(4326); src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(2056)
    ct = osr.CoordinateTransformation(src, dst)
    w, s, e, n = a.bbox
    pts = [ct.TransformPoint(x, y)[:2] for x in np.linspace(w, e, 21) for y in (s, n)] + \
          [ct.TransformPoint(x, y)[:2] for y in np.linspace(s, n, 21) for x in (w, e)]
    xs, ys = zip(*pts)
    r, m = a.res, 500.0
    return (math.floor((min(xs) - m) / r) * r, math.floor((min(ys) - m) / r) * r,
            math.ceil((max(xs) + m) / r) * r, math.ceil((max(ys) + m) / r) * r)


def masked_gaussian(arr, valid, sigma):
    """Gauss-Filter, der Nodata nicht hineinzieht (normalisierte Faltung)."""
    z = np.where(valid, arr, 0).astype(np.float64)
    wgt = ndimage.gaussian_filter(valid.astype(np.float64), sigma)
    z = ndimage.gaussian_filter(z, sigma)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = z / wgt
    return np.where(valid, out, NODATA).astype(np.float32)


def rasterize_surface(a, te, shape):
    """0 = normal, 1 = Fels/Geröll, 2 = Gletscher (aus swissTLM3D-Bodenbedeckung)."""
    surf = np.zeros(shape, dtype=np.uint8)
    if not a.tlm:
        return surf
    path = os.path.join(a.work, "surface.tif")
    rock = ",".join(f"'{v}'" for v in ROCK)
    glac = ",".join(f"'{v}'" for v in GLACIER)
    sql = (f"SELECT geom, CASE WHEN objektart IN ({glac}) THEN 2 ELSE 1 END AS cls "
           f"FROM tlm_bb_bodenbedeckung WHERE objektart IN ({rock},{glac})")
    run(["gdal_rasterize", "-q", "-a", "cls", "-dialect", "SQLITE", "-sql", sql,
         "-te", *map(str, te), "-tr", str(a.res), str(a.res), "-ot", "Byte", "-init", "0",
         "-co", "COMPRESS=DEFLATE", a.tlm, path])
    raw = gdal.Open(path).ReadAsArray()
    # Kleinstflächen (einzelne Felsköpfe, schmale Geröllstreifen) nicht umfärben, sonst
    # zerfallen die Kurven in viele kurze Stücke. Öffnen + Mindestfläche je Klasse.
    surf = np.zeros(shape, dtype=np.uint8)
    for code in (1, 2):
        m = ndimage.binary_closing(raw == code, iterations=1)
        m = ndimage.binary_opening(m, iterations=2)
        lab, n = ndimage.label(m)
        if n:
            sizes = ndimage.sum_labels(m, lab, index=np.arange(1, n + 1)) * a.res * a.res
            m = np.isin(lab, np.nonzero(sizes >= a.min_surface_area)[0] + 1)
        surf[m] = code
    return surf


def stage_contours(a):
    t0 = time.time()
    vrt = a.vrt
    te = lv95_grid(a)
    dem5 = os.path.join(a.work, f"alti3d_{a.res:g}m.tif")
    # 2 m → 5 m mitteln (erste Generalisierung, entfernt Mikrorelief)
    run(["gdalwarp", "-q", "-overwrite", "-te", *map(str, te), "-tr", str(a.res), str(a.res),
         "-r", "average", "-srcnodata", str(NODATA), "-dstnodata", str(NODATA), "-multi",
         "-wo", "NUM_THREADS=ALL_CPUS", "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES", vrt, dem5])
    ds = gdal.Open(dem5)
    gt, proj = ds.GetGeoTransform(), ds.GetProjection()
    dem = ds.ReadAsArray().astype(np.float32)
    valid = dem != NODATA
    log(f"DEM {dem.shape[1]}x{dem.shape[0]} @ {a.res} m, gültig {valid.mean() * 100:.1f} %")

    # Geländeglättung vor dem Konturieren (Generalisierung wie Landeskarte)
    smooth = masked_gaussian(dem, valid, a.sigma / a.res)

    # Gebirgszone: regionale Neigung (stark geglättet) und Höhe → 20 m Äquidistanz
    regional = masked_gaussian(dem, valid, a.alpine_sigma / a.res)
    gy, gx = np.gradient(np.where(valid, regional, np.nan), a.res)
    reg_slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    alpine = valid & (np.nan_to_num(reg_slope) >= a.alpine_slope) & (regional >= a.alpine_min_ele)
    alpine = ndimage.binary_opening(alpine, iterations=4)  # Splitter entfernen
    # Zwischenkurven (10 m, gestrichelt) in flachen Stellen der Gebirgszone
    gy, gx = np.gradient(np.where(valid, masked_gaussian(dem, valid, 25 / a.res), np.nan), a.res)
    loc_slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    flat = np.nan_to_num(loc_slope, nan=90) < a.aux_slope
    log(f"Gebirgszone {alpine[valid].mean() * 100:.1f} % der Fläche, davon flach {flat[alpine].mean() * 100:.1f} %")

    surf = rasterize_surface(a, te, dem.shape)
    log("Fels/Geröll {:.1f} %, Gletscher {:.2f} %".format((surf == 1).mean() * 100, (surf == 2).mean() * 100))

    gpkg = os.path.join(a.work, "contours_lv95.gpkg")
    if os.path.exists(gpkg):
        os.remove(gpkg)
    srs = osr.SpatialReference(); srs.ImportFromWkt(proj)
    out = ogr.GetDriverByName("GPKG").CreateDataSource(gpkg)
    lyr = out.CreateLayer("contours", srs, ogr.wkbLineString)
    for name, typ in (("ele", ogr.OFTReal), ("surface", ogr.OFTString), ("aux", ogr.OFTInteger)):
        lyr.CreateField(ogr.FieldDefn(name, typ))

    mem = gdal.GetDriverByName("MEM")
    dil = lambda m: ndimage.binary_dilation(m, iterations=1)  # 1 px Überlappung an Maskengrenzen
    passes = []
    for code, sname in ((0, "normal"), (1, "rock"), (2, "glacier")):
        sm = surf == code
        if not sm.any():
            continue
        # gerade Höhen (Vielfache von 2×Äquidistanz) überall
        passes.append((sname, 0, dil(sm), 0))
        # ungerade 10er-Stufen: ausserhalb Gebirgszone normal, darin nur flach als Zwischenkurve
        passes.append((sname, 0, dil(sm & ~alpine), a.interval))
        passes.append((sname, 1, dil(sm & alpine & flat), a.interval))
    for sname, aux, mask, offset in passes:
        if not mask.any():
            continue
        tmp = mem.Create("", dem.shape[1], dem.shape[0], 1, gdal.GDT_Float32)
        tmp.SetGeoTransform(gt); tmp.SetProjection(proj)
        b = tmp.GetRasterBand(1); b.SetNoDataValue(NODATA)
        b.WriteArray(np.where(mask & valid, smooth, NODATA))
        lmem = ogr.GetDriverByName("MEM").CreateDataSource("")
        ll = lmem.CreateLayer("c", srs, ogr.wkbLineString)
        ll.CreateField(ogr.FieldDefn("id", ogr.OFTInteger)); ll.CreateField(ogr.FieldDefn("ele", ogr.OFTReal))
        gdal.ContourGenerateEx(b, ll, options=[f"LEVEL_INTERVAL={2 * a.interval}", f"LEVEL_BASE={offset}",
                                               f"NODATA={NODATA}", "ID_FIELD=0", "ELEV_FIELD=1"])
        kept = dropped = 0
        lyr.StartTransaction()
        for f in ll:
            g = f.GetGeometryRef().SimplifyPreserveTopology(a.simplify)
            length = g.Length()
            closed = g.GetPointCount() > 2 and g.GetPoint_2D(0) == g.GetPoint_2D(g.GetPointCount() - 1)
            if length < a.min_open or (closed and length < a.min_closed):
                dropped += 1
                continue
            o = ogr.Feature(lyr.GetLayerDefn())
            o.SetGeometry(g); o["ele"] = round(f["ele"]); o["surface"] = sname; o["aux"] = aux
            lyr.CreateFeature(o); kept += 1
        lyr.CommitTransaction()
        log(f"Pass {sname} aux={aux} offset={offset}: {kept} Linien (verworfen {dropped})")
    out = None
    log(f"Höhenlinien fertig in {time.time() - t0:.0f} s → {gpkg}")


# ---------------------------------------------------------------- PBF
def write_way(f, g, feat, nid, wid, stats):
    pts = g.GetPoints() or []
    if len(pts) < 2:
        return nid, wid
    ele = int(feat["ele"])
    # medium = Vielfache von 20 m: die Äquidistanz der LK50, damit 1:50'000 alle 20-m-Kurven zeigt
    ext = "elevation_major" if ele % 100 == 0 else "elevation_medium" if ele % 20 == 0 else "elevation_minor"
    refs = []
    for x, y in pts:
        nid += 1
        f.write(f"n{nid} v1 x{x:.7f} y{y:.7f}\n")
        refs.append(f"n{nid}")
    tags = f"contour=elevation,ele={ele},contour_ext={ext}"
    if feat["surface"] != "normal":
        # contour_surface für den Overlay-Style, swisstopo:untergrund für den Basis-Style (7701)
        tags += f",contour_surface={feat['surface']}"
        tags += ",swisstopo:untergrund=" + {"rock": "fels", "glacier": "gletscher"}[feat["surface"]]
    if feat["aux"]:
        tags += ",contour_aux=yes"
    wid += 1
    f.write(f"w{wid} v1 T{tags} N{','.join(refs)}\n")
    key = (ext, feat["surface"], feat["aux"])
    stats[key] = stats.get(key, 0) + 1
    return nid, wid


def stage_pbf(a):
    """Höhenlinien auf die WGS84-BBox schneiden und als OSM-PBF schreiben (OPL → osmium)."""
    gpkg = os.path.join(a.work, "contours_lv95.gpkg")
    wgs = os.path.join(a.work, "contours_wgs84.gpkg")
    run(["ogr2ogr", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-clipdst", *map(str, a.bbox),
         "-explodecollections", "-nlt", "MULTILINESTRING", wgs, gpkg])
    opl = os.path.join(a.work, "contours.opl")
    pbf = os.path.join(a.work, "contours.osm.pbf")
    nid, wid = a.node_id_base, a.way_id_base
    stats = {}
    ds = ogr.Open(wgs)
    with open(opl, "w") as f:
        for feat in ds.GetLayer(0):
            g = feat.GetGeometryRef()
            parts = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())] if g.GetGeometryCount() else [g]
            for part in parts:
                nid, wid = write_way(f, part, feat, nid, wid, stats)
    # OPL ist nach Typ sortiert nötig: osmium sort erledigt das
    run(["osmium", "sort", "--overwrite", "-o", pbf, opl])
    os.remove(opl)
    for k, v in sorted(stats.items()):
        log(f"  {k}: {v}")
    log(f"{pbf}: {os.path.getsize(pbf) / 1e6:.1f} MB, Knoten bis {nid}, Wege bis {wid}")
    with open(os.path.join(a.work, "contours_stats.json"), "w") as f:
        json.dump({"|".join(map(str, k)): v for k, v in stats.items()}, f, indent=1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["mosaic", "hgt", "contours", "pbf", "all"])
    ap.add_argument("--bbox", nargs=4, type=float, default=[9.0, 47.2, 9.5, 47.5], metavar=("W", "S", "E", "N"))
    ap.add_argument("--src", default=str(paths.DOWNLOADS / "swissalti3d/2m"))
    ap.add_argument("--tlm", default=str(paths.DOWNLOADS / "swisstlm3d/SWISSTLM3D_2026_LV95_LN02.gpkg"),
                    help="swissTLM3D-GPKG für Fels-/Gletscherkurven ('' = aus)")
    ap.add_argument("--work", default="work/dem")
    ap.add_argument("--vrt", help="2-m-Mosaik (Standard: <work>/alti3d_2m.vrt)")
    ap.add_argument("--hgt-out", help="Ordner für HGT (Standard: <work>/hgt<arcsec>)")
    ap.add_argument("--hgt-smooth", type=float, default=0.0, help="Glättung im Hügelland, Gauss σ in m (0 = aus)")
    ap.add_argument("--relief-low", type=float, default=150.0, help="Relief (m) bis zu dem voll geglättet wird")
    ap.add_argument("--relief-high", type=float, default=400.0, help="Relief (m) ab dem nicht geglättet wird")
    ap.add_argument("--relief-window", type=float, default=1000.0, help="Fenster für das Relief (m)")
    ap.add_argument("--poly", help="osmosis-.poly für --dem-poly (Standard: BBox)")
    ap.add_argument("--force", action="store_true", help="vorhandene HGT neu rechnen")
    ap.add_argument("--hgt-arcsec", type=float, default=1.0, help="HGT-Rasterweite in Bogensekunden (1 = 3601²)")
    ap.add_argument("--res", type=float, default=5.0, help="Rasterweite für die Konturierung in m")
    ap.add_argument("--sigma", type=float, default=12.0, help="Gauss-Glättung in m")
    ap.add_argument("--interval", type=int, default=10, help="Äquidistanz Mittelland in m (Gebirge: doppelt)")
    ap.add_argument("--alpine-sigma", type=float, default=150.0, help="Glättung für die regionale Neigung in m")
    ap.add_argument("--alpine-slope", type=float, default=22.0, help="regionale Neigung in Grad ab der 20 m gilt")
    ap.add_argument("--alpine-min-ele", type=float, default=1000.0, help="Mindesthöhe der Gebirgszone in m")
    ap.add_argument("--aux-slope", type=float, default=12.0, help="Zwischenkurven in der Gebirgszone unter dieser Neigung")
    ap.add_argument("--min-surface-area", type=float, default=5000.0, help="Fels-/Gletscherflächen kleiner als das (m²) bleiben braun")
    ap.add_argument("--simplify", type=float, default=1.5, help="Douglas-Peucker-Toleranz in m")
    ap.add_argument("--min-closed", type=float, default=80.0, help="geschlossene Kurven kürzer als das weglassen (m)")
    ap.add_argument("--min-open", type=float, default=15.0, help="offene Stücke kürzer als das weglassen (m)")
    ap.add_argument("--node-id-base", type=int, default=7_703_000_000_000)
    ap.add_argument("--way-id-base", type=int, default=7_703_000_000_000)
    a = ap.parse_args()
    a.tlm = a.tlm or None
    a.vrt = a.vrt or os.path.join(a.work, "alti3d_2m.vrt")
    os.makedirs(a.work, exist_ok=True)
    t0 = time.time()
    if a.stage in ("mosaic", "all"):
        stage_mosaic(a)
    if a.stage in ("hgt", "all"):
        stage_hgt(a)
    if a.stage in ("contours", "all"):
        stage_contours(a)
    if a.stage in ("pbf", "all"):
        stage_pbf(a)
    log(f"fertig in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
