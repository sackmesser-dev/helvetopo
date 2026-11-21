#!/usr/bin/env python3
"""Höhenkurven und Höhenkoten der Landeskarte aus Swiss Map Vector 25 (©swisstopo, OGD).

SMV25 enthält die kartografischen Daten der LK25 (DKM25), darunter
  T62_DKM25_HOEHENKURVE  Normal-, Zähl- und Zwischenkurven, Oberfläche Fels/Geröll/Gletscher/übrig
  T38_DKM25_HOEHENKOTE   Höhen-, Gelände- und Seebodenkoten mit Wert
Das ist die Landeskarte selbst; die Ableitung aus swissALTI3D (build_dem.py, spot_heights.py)
bleibt als Ausweichweg.

  download  SMV25-GPKG (jüngste Ausgabe) für eine BBox über STAC laden und entpacken
  convert   Kurven und Koten → OSM-PBF (Tags kompatibel zu build_dem.py / spot_heights.py)

  python3 -I src/dem/smv25_heights.py download --bbox 9.0 47.2 9.5 47.5 --out $HELVETOPO_DATA/smv25-2026
  .venv/bin/python src/dem/smv25_heights.py convert --src $HELVETOPO_DATA/smv25-2026 \
      --bbox 9.0 47.2 9.5 47.5 --work work/dem/smv25

Tags Kurven: contour=elevation, ele, contour_ext=elevation_major (Zählkurve) | elevation_medium
  (Vielfache von 20 m, für 1:50'000) | elevation_minor, contour_aux=yes (Zwischenkurve),
  swisstopo:untergrund=fels|gletscher (wie build_dem.py), source:contour=SMV25
Tags Koten: natural=spot_height, ele, swisstopo:kote=yes, swisstopo:kotenart=hoehenkote|gelaendekote,
  swisstopo:koten_rang=1|2|3 (1 = auch in groben Zoomstufen); Seebodenkoten: swisstopo:kote=seeboden
  ohne natural=spot_height. Koten < 100 m neben swissNAMES3D-Gipfeln/-Pässen fallen weg.
"""
import argparse
import concurrent.futures as cf
import glob
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
import zipfile

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swiss-map-vector25/items"
UA = {"User-Agent": "Helvetopo-dem/0.1"}
NAMED = ("Hauptgipfel", "Gipfel", "Alpiner Gipfel", "Huegel", "Haupthuegel", "Felskopf", "Pass", "Strassenpass")


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- download
def stac_items(bbox):
    url = f"{STAC}?bbox={','.join(map(str, bbox))}&limit=100"
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            d = json.load(r)
        yield from d["features"]
        url = next((l["href"] for l in d.get("links", []) if l.get("rel") == "next"), None)


def download(a):
    os.makedirs(a.out, exist_ok=True)
    latest = {}
    for it in stac_items(a.bbox):
        _, year, tile = it["id"].rsplit("_", 2)
        for k, v in it["assets"].items():
            if k.endswith("_2056.gpkg.zip") and (tile not in latest or int(year) > latest[tile][0]):
                latest[tile] = (int(year), v)
    log(f"{len(latest)} SMV25-Kacheln, Ausgabe {sorted({y for y, _ in latest.values()})}")

    def one(item):
        tile, (year, asset) = item
        d = os.path.join(a.out, f"{year}_{tile}")
        if os.path.exists(os.path.join(d, "DONE")):
            return tile, "ok"
        os.makedirs(d, exist_ok=True)
        z = os.path.join(d, "smv25.gpkg.zip")
        h = hashlib.sha256()
        with urllib.request.urlopen(urllib.request.Request(asset["href"], headers=UA), timeout=300) as r, open(z, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk); h.update(chunk)
        mh = asset.get("checksum:multihash", "")
        if mh.upper().startswith("1220") and h.hexdigest().upper() != mh[4:].upper():
            return tile, "FEHLER Prüfsumme"
        with zipfile.ZipFile(z) as zf:  # nur die GPKG entpacken, Pfade flach
            for n in zf.namelist():
                # Einige ZIPs trennen Ordner mit "\" (Windows). os.path.basename trennt unter
                # macOS/Linux nur an "/", sonst stünde "<nr>\SMV25_….gpkg" im Dateinamen.
                name = n.replace("\\", "/").rsplit("/", 1)[-1]
                if name.lower().endswith(".gpkg"):
                    with zf.open(n) as src, open(os.path.join(d, name), "wb") as dst:
                        while chunk := src.read(1 << 20):
                            dst.write(chunk)
        os.remove(z)
        open(os.path.join(d, "DONE"), "w").write(f"{year} {asset['href']}\n")
        return tile, "neu"

    errors = 0
    with cf.ThreadPoolExecutor(a.workers) as ex:
        for i, (tile, st) in enumerate(ex.map(one, sorted(latest.items())), 1):
            log(f"[{i}/{len(latest)}] {tile} {st}")
            errors += st.startswith("FEHLER")
    return 1 if errors else 0



SURFACE = {1: ("Fels", "Fels locker", "Felsbloecke", "Felsbloecke locker"),
           2: ("Lockergestein",),
           3: ("Gletscher", "Schneefeld Toteis")}


def surface_mask(a, x0, y0, x1, y1):
    """swissTLM3D-Bodenbedeckung als Raster (LV95): 0 Boden, 1 Fels, 2 Geröll, 3 Gletscher."""
    import numpy as np
    from osgeo import gdal
    r = a.surface_res
    w, h = int((x1 - x0) / r) + 1, int((y1 - y0) / r) + 1
    out = np.zeros((h, w), np.uint8)
    if not a.tlm or not os.path.exists(a.tlm):
        return out, (x0, y1, r)
    for code, arten in SURFACE.items():
        sql = ("SELECT geom FROM tlm_bb_bodenbedeckung WHERE objektart IN ("
               + ",".join(f"'{v}'" for v in arten) + ")")
        ds = gdal.Rasterize("/vsimem/surf.tif", a.tlm, format="GTiff", outputBounds=[x0, y1 - h * r, x0 + w * r, y1],
                            width=w, height=h, burnValues=[1], outputType=gdal.GDT_Byte,
                            SQLDialect="SQLITE", SQLStatement=sql)
        out[ds.ReadAsArray().astype(bool)] = code
        ds = None
    return out, (x0, y1, r)


def split_by_surface(line, mask, dkm_cls, a):
    """Linie (LV95) verdichten, Stützpunkte nach Bodenbedeckung klassieren, in Abschnitte teilen.
    Abschnitte kürzer als a.min_run werden dem Nachbarn zugeschlagen (kein Flackern an Rändern)."""
    import numpy as np
    from osgeo import ogr
    arr, (x0, ytop, r) = mask
    g = line.Clone()
    g.Segmentize(a.surface_res)
    pts = np.array(g.GetPoints())[:, :2]
    ix = np.clip(((pts[:, 0] - x0) / r).astype(int), 0, arr.shape[1] - 1)
    iy = np.clip(((ytop - pts[:, 1]) / r).astype(int), 0, arr.shape[0] - 1)
    cls = arr[iy, ix].astype(int)
    if dkm_cls:  # Oberfläche aus DKM25 gilt, wo TLM nichts Besonderes meldet
        cls[cls == 0] = dkm_cls
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    # Läufe bilden und kurze Läufe glätten
    runs = []
    start = 0
    for i in range(1, len(cls) + 1):
        if i == len(cls) or cls[i] != cls[start]:
            runs.append([start, i - 1, cls[start]])
            start = i
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for k, (i0, i1, c) in enumerate(runs):
            if seg[i1] - seg[i0] < a.min_run:
                nb = runs[k - 1] if k > 0 else runs[k + 1]
                runs[k][2] = nb[2]
                changed = True
        merged = [runs[0]]
        for i0, i1, c in runs[1:]:
            if c == merged[-1][2]:
                merged[-1][1] = i1
            else:
                merged.append([i0, i1, c])
        if len(merged) == len(runs):
            break
        runs = merged
    out = []
    for k, (i0, i1, c) in enumerate(runs):
        j1 = min(i1 + 1, len(pts) - 1)  # Anschluss an den nächsten Abschnitt
        part = ogr.Geometry(ogr.wkbLineString)
        for x, y in pts[i0:j1 + 1]:
            part.AddPoint_2D(float(x), float(y))
        part = part.Simplify(a.simplify)  # Verdichtungspunkte wieder entfernen
        out.append((int(c), [p[:2] for p in part.GetPoints()]))
    return out

# ---------------------------------------------------------------- convert
def append_glacier_fill(a, opl, nid, wid, stats):
    """Gletscherkurven aus der eigenen swissALTI3D-Ableitung (build_dem.py/run_ch.py) anhängen.

    Die LK führt Gletscherkurven im Gletscher-Raster, nicht in T62_DKM25_HOEHENKURVE: landesweit
    liegen dort nur 132 km Kurven auf 876 km² Gletscher. Deshalb werden die SMV25-Stücke auf
    Gletschern verworfen und die abgeleiteten Gletscherkurven (contour_surface=glacier) übernommen.
    """
    # GDALs OSM-Treiber verwirft "ele" (osmconf ignore-Liste) → direkt mit osmium lesen:
    # Gletscherwege filtern und Knotenkoordinaten in die Wege schreiben (OPL mit Locations).
    import re
    filt = subprocess.run(["osmium", "tags-filter", a.glacier_fill, "w/contour_surface=glacier",
                           "-f", "pbf", "-o", "-"], check=True, capture_output=True).stdout
    loc = subprocess.run(["osmium", "add-locations-to-ways", "-F", "pbf", "-", "-f", "opl", "-o", "-"],
                         input=filt, check=True, capture_output=True).stdout.decode()
    w, s_, e, n = a.bbox
    count = 0
    with open(opl, "a") as f:
        for line in loc.splitlines():
            if not line.startswith("w"):
                continue
            m = re.search(r"(?:^| )T(\S*)", line)
            tagstr = m.group(1) if m else ""
            me = re.search(r"(?:^|,)ele=(-?\d+)", tagstr)
            if not me:
                continue
            ele = int(me.group(1))
            pts = [(float(x), float(y)) for x, y in re.findall(r"n\d+x(-?[\d.]+)y(-?[\d.]+)", line)]
            pts = [(x, y) for x, y in pts if w <= x <= e and s_ <= y <= n]
            if len(pts) < 2:
                continue
            ext = "elevation_major" if ele % 100 == 0 else "elevation_medium" if ele % 20 == 0 else "elevation_minor"
            tags = (f"contour=elevation,ele={ele},contour_ext={ext},source:contour=swissALTI3D,"
                    "contour_surface=glacier,swisstopo:untergrund=gletscher,swisstopo:kurve=gletscher")
            if "contour_aux=yes" in tagstr:
                tags += ",contour_aux=yes"
            refs = []
            for x, y in pts:
                nid += 1
                f.write(f"n{nid} v1 x{x:.7f} y{y:.7f}\n")
                refs.append(f"n{nid}")
            wid += 1
            f.write(f"w{wid} v1 T{tags} N{','.join(refs)}\n")
            count += 1
            key = f"{ext}|gletscher(alti3d)"
            stats[key] = stats.get(key, 0) + 1
    log(f"Gletscherkurven aus {a.glacier_fill}: {count} Linien angehängt")
    return nid, wid


def convert(a):
    from osgeo import ogr, osr
    from scipy.spatial import cKDTree
    import numpy as np
    ogr.UseExceptions()
    os.makedirs(a.work, exist_ok=True)
    gpkgs = sorted(glob.glob(os.path.join(a.src, "**", "*.gpkg"), recursive=True))
    if not gpkgs:
        raise SystemExit(f"keine GPKG unter {a.src}")
    wgs = osr.SpatialReference(); wgs.ImportFromEPSG(4326); wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    lv95 = osr.SpatialReference(); lv95.ImportFromEPSG(2056)
    to_lv95 = osr.CoordinateTransformation(wgs, lv95)
    to_wgs = osr.CoordinateTransformation(lv95, wgs)
    w, s, e, n = a.bbox
    clip = ogr.CreateGeometryFromWkt(f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))")
    clip_lv = clip.Clone(); clip_lv.Segmentize(0.01); clip_lv.Transform(to_lv95)
    env = clip_lv.GetEnvelope()

    # ---- Kurven (Kacheln überlappen nicht; Duplikate an Kachelrändern per UUID verhindern)
    # Jede Kurve wird entlang der swissTLM3D-Bodenbedeckung in Stücke geteilt: Fels, Geröll, Gletscher
    # (eigene Klasse swisstopo:kurve, damit der Style sie wie die LK als Fels-/Gletscherkurven zeigt).
    from osgeo import gdal
    gdal.UseExceptions()
    seen = set()
    opl = os.path.join(a.work, "contours.opl")
    nid = wid = a.contour_id_base
    stats = {}
    cls_tags = {
        0: "",
        1: ",contour_surface=rock,swisstopo:untergrund=fels,swisstopo:kurve=fels",
        2: ",contour_surface=rock,swisstopo:untergrund=fels,swisstopo:kurve=geroell",
        3: ",contour_surface=glacier,swisstopo:untergrund=gletscher,swisstopo:kurve=gletscher",
    }
    cls_name = {0: "boden", 1: "fels", 2: "geroell", 3: "gletscher"}
    with open(opl, "w") as f:
        for gp in gpkgs:
            ds = ogr.Open(gp)
            lyr = ds.GetLayerByName("T62_DKM25_HOEHENKURVE")
            if lyr is None:
                continue
            ex = lyr.GetExtent()  # (minx, maxx, miny, maxy)
            x0, x1 = max(ex[0], env[0]) - 500, min(ex[1], env[1]) + 500
            y0, y1 = max(ex[2], env[2]) - 500, min(ex[3], env[3]) + 500
            if x0 >= x1 or y0 >= y1:
                continue
            mask = surface_mask(a, x0, y0, x1, y1)
            lyr.SetSpatialFilterRect(env[0], env[2], env[1], env[3])
            for ft in lyr:
                uid = ft["DKM_UUID"]
                if uid in seen:
                    continue
                seen.add(uid)
                g = ft.GetGeometryRef().Clone()
                g.FlattenTo2D()
                g = g.Intersection(clip_lv)
                if g is None or g.IsEmpty():
                    continue
                ele = int(ft["HOEHE"])
                art = ft["OBJEKTART"] or ""
                ext = ("elevation_major" if art.startswith("Zaehl") else
                       "elevation_medium" if ele % 20 == 0 else "elevation_minor")
                base_tags = f"contour=elevation,ele={ele},contour_ext={ext},source:contour=SMV25"
                if art.startswith("Zwischen"):
                    base_tags += ",contour_aux=yes"
                ob = (ft["OBERFLAECH"] or "").lower()
                dkm_cls = 2 if ob == "geroell" else 1 if ob == "fels" else 3 if ("glet" in ob or "firn" in ob) else 0
                parts = [g] if g.GetGeometryType() in (ogr.wkbLineString, ogr.wkbLineString25D) else \
                    [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())]
                for p in parts:
                    if p.GetGeometryType() not in (ogr.wkbLineString, ogr.wkbLineString25D) or p.GetPointCount() < 2:
                        continue
                    for cls, coords in split_by_surface(p, mask, dkm_cls, a):
                        if len(coords) < 2 or (cls == 3 and a.glacier_fill):
                            continue  # Gletscher kommen aus --glacier-fill (SMV25 hat dort kaum Kurven)
                        refs = []
                        for x, y in coords:
                            lon, lat = to_wgs.TransformPoint(x, y)[:2]
                            nid += 1
                            f.write(f"n{nid} v1 x{lon:.7f} y{lat:.7f}\n")
                            refs.append(f"n{nid}")
                        wid += 1
                        f.write(f"w{wid} v1 T{base_tags}{cls_tags[cls]} N{','.join(refs)}\n")
                        key = f"{ext}|{cls_name[cls]}"
                        stats[key] = stats.get(key, 0) + 1
    if a.glacier_fill:
        nid, wid = append_glacier_fill(a, opl, nid, wid, stats)
    pbf = os.path.join(a.work, "contours.osm.pbf")
    subprocess.run(["osmium", "sort", "--overwrite", "-o", pbf, opl], check=True)
    os.remove(opl)
    log(f"{pbf}: {sum(stats.values())} Linien, {os.path.getsize(pbf) / 1e6:.1f} MB")
    for k, v in sorted(stats.items()):
        log(f"  {k}: {v}")

    # ---- Koten
    named = []
    if a.names and os.path.exists(a.names):
        nds = ogr.Open(a.names)
        nl = nds.GetLayerByName("swissnames3d_pkt")
        nl.SetAttributeFilter("objektart IN (" + ",".join(f"'{v}'" for v in NAMED) + ")")
        nl.SetSpatialFilterRect(env[0] - 200, env[2] - 200, env[1] + 200, env[3] + 200)
        named = [ft.GetGeometryRef().GetPoint_2D(0) for ft in nl]
    ntree = cKDTree(np.array(named)) if named else None
    pts, seen = [], set()
    for gp in gpkgs:
        ds = ogr.Open(gp)
        lyr = ds.GetLayerByName("T38_DKM25_HOEHENKOTE")
        if lyr is None:
            continue
        lyr.SetSpatialFilter(clip_lv)
        for ft in lyr:
            if ft["DKM_UUID"] in seen:
                continue
            seen.add(ft["DKM_UUID"])
            x, y = ft.GetGeometryRef().GetPoint_2D(0)
            pts.append((x, y, int(ft["HOEHE"]), (ft["OBJEKTART"] or "").lower()))
    land = [p for p in pts if p[3] != "seebodenkote"]
    dropped = 0
    if ntree is not None:
        keep = [p for p in land if not ntree.query_ball_point(p[:2], a.named_exclude)]
        dropped = len(land) - len(keep)
        land = keep
    # Rang für Zoomstufen: Dominanz unter den Koten (höher als alle Koten im Umkreis r),
    # danach gierige Ausdünnung mit Mindestabstand je Rang
    rank = {}
    if land:
        xy = np.array([p[:2] for p in land]); z = np.array([p[2] for p in land])
        tree = cKDTree(xy)
        dom = np.zeros(len(land))
        for r in (300, 700, 1500, 3000):
            for i, nb in enumerate(tree.query_ball_point(xy, r)):
                if z[i] >= z[nb].max():
                    dom[i] = r
        order = np.lexsort((-z, -dom))
        for rk, spacing in ((1, a.rank1_spacing), (2, a.rank2_spacing)):
            chosen = [i for i in rank if rank[i] <= rk]
            ct = cKDTree(xy[chosen]) if chosen else None
            added = []
            for i in order:
                if i in rank:
                    continue
                if ct is not None and ct.query_ball_point(xy[i], spacing):
                    continue
                if added and cKDTree(xy[added]).query_ball_point(xy[i], spacing):
                    continue
                rank[i] = rk; added.append(i)
        for i in range(len(land)):
            rank.setdefault(i, 3)
    opl = os.path.join(a.work, "spot_heights.opl")
    nid = a.spot_id_base
    rk_stats = {1: 0, 2: 0, 3: 0}
    with open(opl, "w") as f:
        for i, (x, y, ele, art) in enumerate(land):
            lon, lat = to_wgs.TransformPoint(x, y)[:2]
            nid += 1
            f.write(f"n{nid} v1 x{lon:.7f} y{lat:.7f} Tnatural=spot_height,ele={ele},swisstopo:kote=yes,"
                    f"swisstopo:kotenart={art},swisstopo:koten_rang={rank[i]},source:ele=SMV25\n")
            rk_stats[rank[i]] += 1
        for x, y, ele, art in (p for p in pts if p[3] == "seebodenkote"):
            lon, lat = to_wgs.TransformPoint(x, y)[:2]
            nid += 1
            f.write(f"n{nid} v1 x{lon:.7f} y{lat:.7f} Tele={ele},swisstopo:kote=seeboden,source:ele=SMV25\n")
    pbf = os.path.join(a.work, "spot_heights.osm.pbf")
    subprocess.run(["osmium", "cat", "--overwrite", "-o", pbf, opl], check=True)
    os.remove(opl)
    area = clip.Clone(); area.Transform(to_lv95)
    km2 = area.GetArea() / 1e6
    log(f"{pbf}: {len(land)} Koten ({len(land) / km2:.2f} je km²), Rang {rk_stats}, "
        f"{dropped} neben swissNAMES3D-Gipfeln weggelassen, "
        f"{sum(1 for p in pts if p[3] == 'seebodenkote')} Seebodenkoten")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download")
    d.add_argument("--bbox", nargs=4, type=float, default=[5.9, 45.8, 10.5, 47.85])
    d.add_argument("--out", default=str(paths.DOWNLOADS / "smv25-2026"))
    d.add_argument("--workers", type=int, default=3)
    c = sub.add_parser("convert")
    c.add_argument("--src", default=str(paths.DOWNLOADS / "smv25-2026"))
    c.add_argument("--bbox", nargs=4, type=float, default=[9.0, 47.2, 9.5, 47.5])
    c.add_argument("--work", default="work/dem/smv25")
    c.add_argument("--names", default=str(paths.DOWNLOADS / "swissnames3d/swissnames3d_2026_2056.gpkg"))
    c.add_argument("--named-exclude", type=float, default=100.0)
    c.add_argument("--tlm", default=str(paths.DOWNLOADS / "swisstlm3d/SWISSTLM3D_2026_LV95_LN02.gpkg"),
                   help="swissTLM3D für Fels/Geröll/Gletscher ('' = nur DKM25-Attribut)")
    c.add_argument("--glacier-fill", help="PBF der swissALTI3D-Kurven (build_dem.py/run_ch.py) für Gletscher")
    c.add_argument("--surface-res", type=float, default=5.0, help="Raster der Bodenbedeckung (m)")
    c.add_argument("--min-run", type=float, default=25.0, help="kürzere Fels-/Boden-Abschnitte zusammenlegen (m)")
    c.add_argument("--simplify", type=float, default=0.5, help="Toleranz nach dem Verdichten (m)")
    c.add_argument("--rank1-spacing", type=float, default=2500.0, help="Mindestabstand Rang 1 (m)")
    c.add_argument("--rank2-spacing", type=float, default=1000.0, help="Mindestabstand Rang 2 (m)")
    c.add_argument("--contour-id-base", type=int, default=7_703_000_000_000)
    c.add_argument("--spot-id-base", type=int, default=7_704_500_000_000)
    a = ap.parse_args()
    return download(a) if a.cmd == "download" else convert(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
