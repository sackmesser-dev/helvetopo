#!/usr/bin/env python3
"""Felsschraffen und Schattenflächen aus swissALTI3D (Prototyp Review 3).

Garmin kann keine Rasterzeichnung in Vektorkarten. Die Landeskarte zeigt Fels als gezeichnete
Schraffen und hat eine kräftige Schummerung. Dieses Skript nähert beides mit Vektorobjekten an:

* Felsschraffen: kurze Linien entlang der Falllinie, nur in swissTLM3D-Fels (Fels, Fels locker)
  und nur ab einer Mindestneigung. Die Länge wächst mit der Neigung. Zwei Klassen nach
  Beleuchtung (Licht von Nordwesten wie auf der LK): ``licht`` und ``schatten``.
* Schattenflächen: Flächen auf steilen Hängen, die im Relief mit Licht von Nordwesten
  dunkel sind. Zwei Klassen ``mittel`` und ``stark``. Der TYP zeichnet sie als Muster mit
  transparenten Pixeln über der Bodenbedeckung.

Quelle nur swissALTI3D und swissTLM3D (beide swisstopo OGD). Ausgabe: OSM-PBF mit Tags
``swisstopo:felsschraffe=licht|schatten`` (Linien) und ``swisstopo:schatten=mittel|stark``
(Flächen), IDs ab 7710·10^12 (keine Kollision mit Basis, Kurven und Koten), je Kachel 10^7.

Das Skript rechnet in LV95-Kacheln (Standard 20 km, 400 m Rechenpuffer, mehrere Prozesse) und
führt die Kachel-PBF mit osmium merge zusammen. Fertige Kacheln in <out>/tiles/ bleiben bei
einem Neustart erhalten.

Aufruf (venv mit GDAL, numpy, scipy):
  .venv/bin/python src/dem/rock_relief.py --bbox 9.25 47.20 9.50 47.30 --out work/dem/relief
  .venv/bin/python src/dem/rock_relief.py --bbox 5.95 45.81 10.50 47.81 --vrt work/dem/ch/alti3d_2m.vrt \
      --out work/dem/ch/relief --jobs 6
"""
import argparse
import concurrent.futures as cf
import math
import os
import resource
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
osr.UseExceptions()

NODATA = -9999.0
ROCK = ("Fels", "Fels locker")
ID0 = 7710 * 10 ** 12
LIGHT_AZ, LIGHT_ALT = 315.0, 45.0


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


def lv95_bbox(bbox):
    src = osr.SpatialReference(); src.ImportFromEPSG(4326)
    src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(2056)
    tr = osr.CoordinateTransformation(src, dst)
    w, s, e, n = bbox
    pts = [tr.TransformPoint(x, y) for x in (w, e) for y in (s, n)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return math.floor(min(xs)), math.floor(min(ys)), math.ceil(max(xs)), math.ceil(max(ys))


def read_dem(vrt, box, res):
    x0, y0, x1, y1 = box
    ds = gdal.Warp("", vrt, format="MEM", outputBounds=(x0, y0, x1, y1), xRes=res, yRes=res,
                   resampleAlg="average", srcNodata=NODATA, dstNodata=NODATA, outputType=gdal.GDT_Float32,
                   multithread=True)
    arr = ds.ReadAsArray().astype(np.float32)
    return arr, ds.GetGeoTransform()


def rasterize_rock(gpkg, box, res, shape):
    x0, y0, x1, y1 = box
    drv = gdal.GetDriverByName("MEM")
    out = drv.Create("", shape[1], shape[0], 1, gdal.GDT_Byte)
    out.SetGeoTransform((x0, res, 0, y1, 0, -res))
    sr = osr.SpatialReference(); sr.ImportFromEPSG(2056)
    out.SetProjection(sr.ExportToWkt())
    src = ogr.Open(gpkg)
    lyr = src.GetLayerByName("tlm_bb_bodenbedeckung")
    lyr.SetSpatialFilterRect(x0, y0, x1, y1)
    lyr.SetAttributeFilter("objektart IN (%s)" % ",".join("'%s'" % r for r in ROCK))
    gdal.RasterizeLayer(out, [1], lyr, burn_values=[1])
    return out.ReadAsArray().astype(bool)


def gradients(dem, res, sigma_px):
    valid = dem != NODATA
    d = np.where(valid, dem, np.nanmean(np.where(valid, dem, np.nan)))
    if sigma_px > 0:
        d = ndimage.gaussian_filter(d, sigma_px)
    gy, gx = np.gradient(d, res)        # Zeilen laufen nach Süden: gy = dz/d(Süd)
    gn = -gy                            # dz/d(Nord)
    slope = np.degrees(np.arctan(np.hypot(gx, gn)))
    return gx, gn, slope, valid


def hillshade(gx, gn, az=LIGHT_AZ, alt=LIGHT_ALT):
    # Normalenvektor (−dz/dx, −dz/dy, 1), Licht aus Azimut az (Grad von Nord im Uhrzeigersinn)
    a, h = math.radians(az), math.radians(alt)
    lx, ly, lz = math.sin(a) * math.cos(h), math.cos(a) * math.cos(h), math.sin(h)
    norm = np.sqrt(gx * gx + gn * gn + 1)
    return np.clip((-gx * lx - gn * ly + lz) / norm, 0, 1)


# ---------------------------------------------------------------- Felsschraffen
def hatches(dem, gt, rock, a):
    res = gt[1]
    gx, gn, slope, valid = gradients(dem, res, a.hatch_sigma / res)
    hs = hillshade(gx, gn)
    rng = np.random.default_rng(7710)
    h, w = dem.shape
    step = a.hatch_spacing / res
    ys = np.arange(step / 2, h, step)
    xs = np.arange(step / 2, w, step)
    lines = []
    for yi, y in enumerate(ys):
        for x in xs + (step / 2 if yi % 2 else 0):
            px = x + rng.uniform(-0.35, 0.35) * step
            py = y + rng.uniform(-0.35, 0.35) * step
            i, j = int(py), int(px)
            if not (0 <= i < h and 0 <= j < w) or not rock[i, j] or not valid[i, j]:
                continue
            s = slope[i, j]
            if s < a.hatch_min_slope:
                continue
            # flachere Felsen lockerer: Wahrscheinlichkeit 0.35 an der Mindestneigung, 1 ab +25°
            if rng.random() > min(1.0, 0.35 + 0.65 * (s - a.hatch_min_slope) / 25.0):
                continue
            length = a.hatch_len_min + (a.hatch_len_max - a.hatch_len_min) * min(1.0, (s - a.hatch_min_slope) / 40.0)
            pts = [(px, py)]
            seg = length / res / 2
            ok = True
            for _ in range(2):          # zwei Schritte bergab, Richtung je neu bestimmen
                ci, cj = int(pts[-1][1]), int(pts[-1][0])
                if not (0 <= ci < h and 0 <= cj < w):
                    ok = False; break
                ex, en = gx[ci, cj], gn[ci, cj]
                g = math.hypot(ex, en)
                if g == 0:
                    ok = False; break
                # bergab: −Gradient; Spalten nach Osten (+x), Zeilen nach Süden (−Nord)
                nx, ny = pts[-1][0] - ex / g * seg, pts[-1][1] + en / g * seg
                pts.append((nx, ny))
            if not ok:
                continue
            cls = "schatten" if hs[i, j] < a.hatch_shadow else "licht"
            lines.append((cls, [(gt[0] + p[0] * res, gt[3] - p[1] * res) for p in pts]))
    return lines


def comb_lines(dem, gt, rock, a):
    """Felslinien für Kamm-Signatur: Höhenlinien im Fels (Abstand a.comb_interval), getrennt nach
    Licht- und Schattenseite. Der TYP zeichnet sie als Linie mit quer stehenden Strichen
    (UseOrientation), die Striche zeigen damit entlang der Falllinie. Eine Linie trägt viele
    Striche, deshalb viel weniger Daten als Einzelschraffen."""
    res = gt[1]
    gx, gn, slope, valid = gradients(dem, res, a.hatch_sigma / res)
    hs = hillshade(gx, gn)
    d = ndimage.gaussian_filter(np.where(valid, dem, 0), a.hatch_sigma / res)
    m = rock & valid & (slope >= a.hatch_min_slope)
    m = ndimage.binary_opening(m, iterations=1)
    d = np.where(m, d, NODATA).astype(np.float32)
    drv = gdal.GetDriverByName("MEM")
    r = drv.Create("", d.shape[1], d.shape[0], 1, gdal.GDT_Float32)
    r.SetGeoTransform(gt)
    sr = osr.SpatialReference(); sr.ImportFromEPSG(2056)
    r.SetProjection(sr.ExportToWkt())
    b = r.GetRasterBand(1); b.WriteArray(d); b.SetNoDataValue(NODATA)
    vds = ogr.GetDriverByName("MEM").CreateDataSource("")
    lyr = vds.CreateLayer("c", sr, ogr.wkbLineString)
    lyr.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
    lyr.CreateField(ogr.FieldDefn("ele", ogr.OFTReal))
    gdal.ContourGenerate(b, a.comb_interval, 0, [], 1, NODATA, lyr, 0, 1)
    h, w = d.shape
    out = []
    for f in lyr:
        g = f.GetGeometryRef().SimplifyPreserveTopology(a.comb_simplify)
        pts = [g.GetPoint_2D(i) for i in range(g.GetPointCount())]
        if len(pts) < 2:
            continue
        # Klassen je Stützpunkt, dann in Läufe gleicher Klasse teilen
        cls = []
        for x, y in pts:
            j, i = int((x - gt[0]) / res), int((gt[3] - y) / res)
            cls.append("schatten" if 0 <= i < h and 0 <= j < w and hs[i, j] < a.hatch_shadow else "licht")
        run = [pts[0]]
        for k in range(1, len(pts)):
            run.append(pts[k])
            if k == len(pts) - 1 or cls[k] != cls[k - 1]:
                if len(run) >= 2 and ogr.CreateGeometryFromWkt(
                        "LINESTRING(%s)" % ",".join("%f %f" % p for p in run)).Length() >= a.comb_min_len:
                    out.append((cls[k - 1], run))
                run = [pts[k]]
    return out


# ---------------------------------------------------------------- Schattenflächen
def shadow_polys(dem, gt, a):
    res = gt[1]
    gx, gn, slope, valid = gradients(dem, res, a.shadow_sigma / res)
    hs = hillshade(gx, gn)
    flat = hillshade(np.zeros(1), np.zeros(1))[0]   # Helligkeit einer ebenen Fläche
    cls = np.zeros(dem.shape, np.uint8)
    rel = hs / flat
    steep = slope >= a.shadow_min_slope
    cls[(rel < a.shadow_mittel) & steep & valid] = 1
    cls[(rel < a.shadow_stark) & steep & valid] = 2
    minpx = int(a.shadow_min_area / (res * res))
    out = np.zeros_like(cls)
    for k in (1, 2):
        m = cls >= k
        m = ndimage.binary_opening(m, iterations=1)
        m = ndimage.binary_closing(m, iterations=2)
        lab, n = ndimage.label(m)
        if n:
            sizes = ndimage.sum(m, lab, range(1, n + 1))
            keep = np.zeros(n + 1, bool); keep[1:] = sizes >= minpx
            m = keep[lab]
        out[m] = k
    drv = gdal.GetDriverByName("MEM")
    r = drv.Create("", out.shape[1], out.shape[0], 1, gdal.GDT_Byte)
    r.SetGeoTransform(gt)
    sr = osr.SpatialReference(); sr.ImportFromEPSG(2056)
    r.SetProjection(sr.ExportToWkt())
    polys = []
    for k, name in ((1, "mittel"), (2, "stark")):
        r.GetRasterBand(1).WriteArray((out >= k).astype(np.uint8))
        vds = ogr.GetDriverByName("MEM").CreateDataSource("")
        lyr = vds.CreateLayer("p", sr, ogr.wkbPolygon)
        lyr.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
        gdal.Polygonize(r.GetRasterBand(1), r.GetRasterBand(1), lyr, 0)
        for f in lyr:
            if f.GetField("v") != 1:
                continue
            g = f.GetGeometryRef().SimplifyPreserveTopology(a.shadow_simplify)
            if g is None or g.IsEmpty() or g.GetArea() < a.shadow_min_area:
                continue
            rings = []
            for ri in range(g.GetGeometryCount()):
                ring = g.GetGeometryRef(ri)
                if ri > 0 and abs(ogr.CreateGeometryFromWkt(
                        "POLYGON((%s))" % ",".join("%f %f" % ring.GetPoint_2D(p) for p in range(ring.GetPointCount())))
                        .GetArea()) < a.shadow_min_area:
                    continue          # kleine Löcher füllen
                rings.append([ring.GetPoint_2D(p) for p in range(ring.GetPointCount())])
            polys.append((name, rings))
    return polys


# ---------------------------------------------------------------- OSM-Ausgabe
def write_osm(path, lines, polys, id_base=ID0):
    src = osr.SpatialReference(); src.ImportFromEPSG(2056)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(src, dst)
    nid, wid, rid = id_base, id_base, id_base
    nodes, ways, rels = [], [], []

    def add_way(coords, tags, closed=False):
        nonlocal nid, wid
        pts = tr.TransformPoints([(x, y) for x, y in coords])
        refs = []
        for lon, lat, _ in (pts[:-1] if closed else pts):
            nid += 1
            nodes.append((nid, lat, lon))
            refs.append(nid)
        if closed:
            refs.append(refs[0])
        wid += 1
        ways.append((wid, refs, tags))
        return wid

    for cls, coords in lines:
        add_way(coords, {"swisstopo:felsschraffe": cls, "source": "swissALTI3D"})
    for cls, rings in polys:
        tags = {"swisstopo:schatten": cls, "source": "swissALTI3D"}
        if len(rings) == 1:
            add_way(rings[0], dict(tags, area="yes"), closed=True)
        else:
            members = [("outer" if i == 0 else "inner", add_way(r, {}, closed=True)) for i, r in enumerate(rings)]
            rid += 1
            rels.append((rid, members, dict(tags, type="multipolygon")))
    with open(path, "w", encoding="utf-8") as f:
        f.write("<?xml version='1.0' encoding='UTF-8'?>\n<osm version='0.6' generator='rock_relief'>\n")
        for i, lat, lon in nodes:
            f.write("<node id='%d' version='1' lat='%.7f' lon='%.7f'/>\n" % (i, lat, lon))
        for i, refs, tags in ways:
            f.write("<way id='%d' version='1'>" % i + "".join("<nd ref='%d'/>" % r for r in refs)
                    + "".join("<tag k='%s' v='%s'/>" % kv for kv in tags.items()) + "</way>\n")
        for i, members, tags in rels:
            f.write("<relation id='%d' version='1'>" % i
                    + "".join("<member type='way' ref='%d' role='%s'/>" % (ref, role) for role, ref in members)
                    + "".join("<tag k='%s' v='%s'/>" % kv for kv in tags.items()) + "</relation>\n")
        f.write("</osm>\n")
    return len(nodes), len(ways), len(rels)


# ---------------------------------------------------------------- Kacheln
# Festes LV95-Raster, damit Kachel-IDs und Pixelraster nicht vom Gebiet abhängen. Jede Kachel
# rechnet auf einem Puffer (--buffer) und schneidet das Ergebnis auf ihr Kerngebiet zu.
GRID_X0, GRID_Y0 = 2_400_000, 1_000_000
TILE_IDS = 10 ** 7            # IDs je Kachel (Testgebiet gesamt: 0,12 Mio. Knoten)


def tile_grid(box, size):
    x0, y0, x1, y1 = box
    out = []
    for ix in range(int((x0 - GRID_X0) // size), int(math.ceil((x1 - GRID_X0) / size))):
        for iy in range(int((y0 - GRID_Y0) // size), int(math.ceil((y1 - GRID_Y0) / size))):
            tx, ty = GRID_X0 + ix * size, GRID_Y0 + iy * size
            core = (max(x0, tx), max(y0, ty), min(x1, tx + size), min(y1, ty + size))
            k = ix * 1000 + iy
            if (k + 1) * TILE_IDS >= 10 ** 12:
                raise SystemExit(f"Kachel {ix}/{iy}: ID-Bereich zu gross, --tile-km grösser wählen")
            out.append((f"t{ix:03d}_{iy:03d}", k, core))
    return out


def box_geom(box):
    x0, y0, x1, y1 = box
    return ogr.CreateGeometryFromWkt(f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))")


def parts(g, kind):
    """Teilgeometrien eines Schnittergebnisses mit dem flachen Typ kind."""
    if g is None or g.IsEmpty():
        return []
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t == kind:
        return [g]
    if t in (ogr.wkbMultiLineString, ogr.wkbMultiPolygon, ogr.wkbGeometryCollection):
        return [p for i in range(g.GetGeometryCount()) for p in parts(g.GetGeometryRef(i), kind)]
    return []


def clip_lines(lines, core):
    x0, y0, x1, y1 = core
    poly = box_geom(core)
    out = []
    for cls, pts in lines:
        if all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in pts):
            out.append((cls, pts))
            continue
        g = ogr.CreateGeometryFromWkt("LINESTRING(%s)" % ",".join("%f %f" % p for p in pts))
        for p in parts(g.Intersection(poly), ogr.wkbLineString):
            if p.GetPointCount() >= 2:
                out.append((cls, [p.GetPoint_2D(i) for i in range(p.GetPointCount())]))
    return out


def clip_polys(polys, core):
    x0, y0, x1, y1 = core
    poly = box_geom(core)
    out = []
    for cls, rings in polys:
        if all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in rings[0]):
            out.append((cls, rings))
            continue
        g = ogr.CreateGeometryFromWkt("POLYGON(%s)" % ",".join(
            "(%s)" % ",".join("%f %f" % p for p in r) for r in rings))
        if not g.IsValid():
            g = g.MakeValid()
        for p in parts(g.Intersection(poly), ogr.wkbPolygon):
            rr = [[p.GetGeometryRef(i).GetPoint_2D(j) for j in range(p.GetGeometryRef(i).GetPointCount())]
                  for i in range(p.GetGeometryCount())]
            if rr and len(rr[0]) >= 4:
                out.append((cls, rr))
    return out


def compute(box, a, quiet=False):
    """Felsschraffen und Schattenflächen für ein LV95-Rechteck (ohne Zuschnitt)."""
    say = (lambda m: None) if quiet else log
    lines, polys = [], []
    if not a.no_hatch:
        dem, gt = read_dem(a.vrt, box, a.hatch_res)
        if (dem != NODATA).any():
            say(f"DEM {dem.shape[1]}×{dem.shape[0]} zu {a.hatch_res:g} m")
            rock = rasterize_rock(a.tlm, box, a.hatch_res, dem.shape)
            say(f"Fels {rock.sum() * a.hatch_res ** 2 / 1e6:.1f} km²")
            if rock.any():
                lines = comb_lines(dem, gt, rock, a) if a.mode == "kamm" else hatches(dem, gt, rock, a)
            del rock
        del dem
    if not a.no_shadow:
        dem, gt = read_dem(a.vrt, box, a.shadow_res)
        if (dem != NODATA).any():
            polys = shadow_polys(dem, gt, a)
        del dem
    return lines, polys


def summary(lines, polys):
    n_s = sum(1 for c, _ in lines if c == "schatten")
    return (f"Felsschraffen: {len(lines)} Linien ({n_s} Schatten), {sum(len(p) for _, p in lines)} Stützpunkte; "
            f"Schattenflächen: {sum(1 for c, _ in polys if c == 'mittel')} mittel, "
            f"{sum(1 for c, _ in polys if c == 'stark')} stark, {sum(len(r) for _, rs in polys for r in rs)} Stützpunkte")


def to_pbf(osm, pbf):
    tmp = pbf + ".tmp.osm.pbf"
    subprocess.run(["osmium", "cat", "--overwrite", "-o", tmp, osm], check=True)
    os.remove(osm)
    os.replace(tmp, pbf)


def run_tile(tid, k, core, a, tile_dir):
    """Eine Kachel rechnen (eigener Prozess). Ergebnis <tid>.osm.pbf oder Marke <tid>.leer."""
    gdal.SetCacheMax(256 * 2 ** 20)
    t0 = time.time()
    b = a.buffer
    lines, polys = compute((core[0] - b, core[1] - b, core[2] + b, core[3] + b), a, quiet=True)
    lines, polys = clip_lines(lines, core), clip_polys(polys, core)
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    rss = rss if sys.platform == "darwin" else rss * 1024          # macOS: Bytes, Linux: KiB
    if not lines and not polys:
        open(os.path.join(tile_dir, tid + ".leer"), "w").close()
        return tid, time.time() - t0, rss, "leer", 0
    osm = os.path.join(tile_dir, tid + ".osm")
    write_osm(osm, lines, polys, ID0 + k * TILE_IDS)
    pbf = os.path.join(tile_dir, tid + ".osm.pbf")
    to_pbf(osm, pbf)
    return tid, time.time() - t0, rss, summary(lines, polys), os.path.getsize(pbf)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("W", "S", "E", "N"))
    ap.add_argument("--out", required=True, help="Ausgabeordner")
    ap.add_argument("--vrt", default=os.path.join(paths.MAIN, "work", "dem", "alti3d_2m.vrt"))
    ap.add_argument("--tlm", default=str(paths.TLM_GPKG))
    ap.add_argument("--no-hatch", action="store_true")
    ap.add_argument("--no-shadow", action="store_true")
    g = ap.add_argument_group("Kacheln")
    g.add_argument("--tile-km", type=float, default=20.0,
                   help="Kantenlänge der LV95-Kacheln in km; 0 = ganzes Gebiet auf einmal (viel RAM)")
    g.add_argument("--buffer", type=float, default=400.0, help="Rechenpuffer um jede Kachel in m (Vielfaches von 20)")
    g.add_argument("--jobs", type=int, default=4, help="parallele Kacheln (je ca. 1,5 GB RAM)")
    g.add_argument("--only", help="nur diese Kachel-IDs rechnen (Komma, z. B. t017_009), ohne Zusammenführen")
    g = ap.add_argument_group("Felsschraffen")
    g.add_argument("--mode", choices=("kamm", "striche"), default="kamm",
                   help="kamm = Höhenlinien im Fels mit Kamm-Signatur (wenig Daten), striche = Einzelschraffen")
    g.add_argument("--comb-interval", type=float, default=20.0, help="Abstand der Felslinien in m Höhe")
    g.add_argument("--comb-simplify", type=float, default=2.0, help="m")
    g.add_argument("--comb-min-len", type=float, default=12.0, help="kürzere Stücke entfallen, m")
    g.add_argument("--hatch-res", type=float, default=4.0, help="DEM-Rasterweite in m")
    g.add_argument("--hatch-sigma", type=float, default=6.0, help="Glättung in m")
    g.add_argument("--hatch-spacing", type=float, default=11.0, help="Abstand der Startpunkte in m")
    g.add_argument("--hatch-min-slope", type=float, default=30.0, help="Mindestneigung in Grad")
    g.add_argument("--hatch-len-min", type=float, default=8.0)
    g.add_argument("--hatch-len-max", type=float, default=24.0)
    g.add_argument("--hatch-shadow", type=float, default=0.55, help="Relief-Helligkeit unter diesem Wert = Schattenschraffe")
    g = ap.add_argument_group("Schattenflächen")
    g.add_argument("--shadow-res", type=float, default=10.0)
    g.add_argument("--shadow-sigma", type=float, default=20.0)
    g.add_argument("--shadow-min-slope", type=float, default=25.0)
    g.add_argument("--shadow-mittel", type=float, default=0.70, help="Helligkeit relativ zur Ebene")
    g.add_argument("--shadow-stark", type=float, default=0.45)
    g.add_argument("--shadow-min-area", type=float, default=5000.0, help="m²")
    g.add_argument("--shadow-simplify", type=float, default=8.0, help="m")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    box = lv95_bbox(a.bbox)
    pbf = os.path.join(a.out, "rock_relief.osm.pbf")
    t0 = time.time()

    if a.tile_km <= 0:
        lines, polys = compute(box, a)
        log(summary(lines, polys))
        osm = os.path.join(a.out, "rock_relief.osm")
        write_osm(osm, lines, polys)
        to_pbf(osm, pbf)
        log(f"{pbf}: {os.path.getsize(pbf) / 1e6:.1f} MB")
        return

    tile_dir = os.path.join(a.out, "tiles")
    os.makedirs(tile_dir, exist_ok=True)
    tiles = tile_grid(box, a.tile_km * 1000)
    if a.only:
        keep = set(a.only.split(","))
        tiles = [t for t in tiles if t[0] in keep]
    todo = [t for t in tiles if not any(os.path.exists(os.path.join(tile_dir, t[0] + ext))
                                        for ext in (".osm.pbf", ".leer"))]
    log(f"{len(tiles)} Kacheln zu {a.tile_km:g} km, {len(tiles) - len(todo)} vorhanden, {a.jobs} parallel")
    failed = 0
    # Ein Prozess je Kachel: der Speicher geht nach jeder Kachel ans System zurück
    with cf.ProcessPoolExecutor(a.jobs, max_tasks_per_child=1) as ex:
        futs = {ex.submit(run_tile, tid, k, core, a, tile_dir): tid for tid, k, core in todo}
        for n, fu in enumerate(cf.as_completed(futs), 1):
            try:
                tid, dt, rss, info, size = fu.result()
                log(f"[{n}/{len(todo)}] {tid} {dt:.0f} s, RAM max {rss / 2 ** 30:.2f} GB, "
                    f"{size / 1e6:.2f} MB: {info}")
            except Exception as e:  # noqa: BLE001 – eine Kachel darf den Lauf nicht abbrechen
                failed += 1
                log(f"[{n}/{len(todo)}] {futs[fu]} FEHLER {e!r}")
    if failed:
        raise SystemExit(f"{failed} Kacheln fehlgeschlagen, Lauf neu starten (fertige Kacheln bleiben)")
    if a.only:
        log(f"fertig in {time.time() - t0:.0f} s (nur --only, kein Zusammenführen)")
        return
    parts_ = sorted(os.path.join(tile_dir, t[0] + ".osm.pbf") for t in tiles
                    if os.path.exists(os.path.join(tile_dir, t[0] + ".osm.pbf")))
    if not parts_:
        raise SystemExit("keine Kachel mit Fels oder Schatten im Gebiet")
    tmp = pbf + ".tmp.osm.pbf"
    subprocess.run(["osmium", "merge", "--overwrite", "-o", tmp, *parts_], check=True)
    os.replace(tmp, pbf)
    log(f"{pbf}: {len(parts_)} Kacheln, {os.path.getsize(pbf) / 1e6:.1f} MB, {(time.time() - t0) / 60:.1f} min")


if __name__ == "__main__":
    main()
