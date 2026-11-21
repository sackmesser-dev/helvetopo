"""Regionale KMZ-Pakete für die Schweiz (oder einen Ausschnitt) innerhalb der Garmin-Kachellimits.

Prinzip
- Ein **globales Kachelraster** je Massstab (Ursprung 5,80° O / 47,95° N, Pixelgrösse aus der
  Auflösung bei 46,8° N): Alle Pakete einer Stufe teilen sich dasselbe Raster, Kacheln benachbarter
  Pakete stossen exakt aneinander und überlappen nicht.
- **Landesmaske:** Nur Kacheln, die das Gebiet Schweiz + Liechtenstein (swissBOUNDARIES3D, OGD)
  inkl. Puffer berühren, kommen in Pakete. Kacheln über reinem Ausland fallen weg.
- **Schema `grid`:** Blöcke von k × k Kacheln (Standard k = 22 → ≤ 484). Kleine Randpakete werden
  mit Nachbarn zusammengelegt, solange das Limit hält.
- **Schema `canton`:** ein Paket je Kanton (Kacheln, die den Kanton berühren); grosse Kantone
  werden nach demselben k × k-Raster geteilt. Kacheln an Kantonsgrenzen liegen in beiden Paketen.
- Quellen: SMR-Blätter per STAC (neueste Ausgabe, krel). Liegen sie unter downloads/smr/, werden
  die lokalen Dateien benutzt, sonst wird das COG per /vsicurl/ gelesen (nur benötigte Bereiche).

Aufrufe
  python3 package.py --scale 25 --region ch --dry-run              # Plan Schweiz, ohne Bauen
  python3 package.py --scale 25 --region testgebiet                # Pakete im Testgebiet bauen
  python3 package.py --scale 50 --scheme canton --region ch --dry-run
  python3 package.py --scale 25 --region bbox 9.2 47.2 9.5 47.46
Ausgabe: work/raster_kmz/pakete/<schema>-smr<massstab>-<region>/
  plan.json, uebersicht.png, LIESMICH.txt, <paket>/<paket>.kmz + README.txt + build.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pathlib
import re
import shutil
import string
import sys
import time

import numpy as np
from osgeo import gdal, ogr, osr
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

import build as B
import stac
import variants as V

gdal.UseExceptions()
ogr.UseExceptions()

GPKG = paths.BOUNDARIES_GPKG
ORIGIN = (5.80, 47.95)          # NW-Ecke des globalen Rasters
REF_LAT = 46.8                  # Breite für die Pixelgrösse
GRID_EXTENT = (5.80, 45.70, 10.70, 47.95)
RES = {25: 1.25, 50: 2.5, 100: 5.0, 200: 10.0}
DRAW_ORDER = {25: 53, 50: 52, 100: 51, 200: 51}
TILE = 1024
try:
    FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
except OSError:
    FONT = ImageFont.load_default()


class Grid:
    def __init__(self, scale: int):
        self.scale = scale
        self.res = RES[scale]
        self.dlon, self.dlat = B.deg_per_px(self.res, REF_LAT)
        self.tlon, self.tlat = self.dlon * TILE, self.dlat * TILE
        w, s, e, n = GRID_EXTENT
        self.cols = math.ceil((e - w) / self.tlon)
        self.rows = math.ceil((n - s) / self.tlat)

    def tile_bbox(self, r, c):
        w = ORIGIN[0] + c * self.tlon
        n = ORIGIN[1] - r * self.tlat
        return (w, n - self.tlat, w + self.tlon, n)

    def index_range(self, bbox):
        """Kachelindizes (r0, r1, c0, c1), die eine bbox berühren (r1, c1 exklusiv)."""
        w, s, e, n = bbox
        c0 = math.floor((w - ORIGIN[0]) / self.tlon)
        c1 = math.ceil((e - ORIGIN[0]) / self.tlon)
        r0 = math.floor((ORIGIN[1] - n) / self.tlat)
        r1 = math.ceil((ORIGIN[1] - s) / self.tlat)
        return r0, r1, c0, c1

    def rasterize(self, layer) -> np.ndarray:
        ds = gdal.GetDriverByName("MEM").Create("", self.cols, self.rows, 1, gdal.GDT_Byte)
        ds.SetGeoTransform((ORIGIN[0], self.tlon, 0, ORIGIN[1], 0, -self.tlat))
        srs = osr.SpatialReference(); srs.ImportFromEPSG(4326)
        ds.SetProjection(srs.ExportToWkt())
        gdal.RasterizeLayer(ds, [1], layer, burn_values=[1], options=["ALL_TOUCHED=TRUE"])
        return ds.ReadAsArray().astype(bool)


def boundary_layers(buffer_m: float, where: str, layer_name: str):
    """Polygone (LV95) puffern, nach EPSG:4326 transformieren; je Feature ein Memory-Layer."""
    src = ogr.Open(str(GPKG))
    lyr = src.GetLayerByName(layer_name)
    lyr.SetAttributeFilter(where)
    dst = osr.SpatialReference(); dst.ImportFromEPSG(4326)
    dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(lyr.GetSpatialRef(), dst)
    geoms: dict[str, ogr.Geometry] = {}
    for f in lyr:
        g = f.GetGeometryRef().Clone()
        g.FlattenTo2D()
        g = g.SimplifyPreserveTopology(20)
        if buffer_m:
            g = g.Buffer(buffer_m, 4)
        name = f.GetField("name")
        geoms[name] = geoms[name].Union(g) if name in geoms else g  # mehrteilige Kantone
    out = {}
    for name, g in geoms.items():
        g.Transform(ct)
        mem = ogr.GetDriverByName("MEM").CreateDataSource(name)
        l = mem.CreateLayer("l", dst, ogr.wkbMultiPolygon)
        nf = ogr.Feature(l.GetLayerDefn()); nf.SetGeometry(g); l.CreateFeature(nf)
        out[name] = (mem, l)
    return out


def region_mask(grid: Grid, region: list[str]) -> tuple[np.ndarray, str, tuple | None]:
    m = np.zeros((grid.rows, grid.cols), bool)
    if region[0] == "ch":
        m[:] = True
        return m, "ch", None
    if region[0] == "testgebiet":
        bbox, label = V.TESTGEBIET, "testgebiet"
    elif region[0] == "bbox":
        bbox = tuple(float(x) for x in region[1:5])
        label = "bbox-" + "-".join(f"{x:.2f}" for x in bbox)
    else:
        raise SystemExit("Region: ch | testgebiet | bbox W S E N")
    r0, r1, c0, c1 = grid.index_range(bbox)
    m[r0:r1, c0:c1] = True
    return m, label, bbox


def blocks(tiles: np.ndarray, k: int) -> dict[tuple[int, int], set]:
    out = {}
    for r, c in zip(*np.nonzero(tiles)):
        out.setdefault((r // k, c // k), set()).add((int(r), int(c)))
    return out


def merge_small(pk: dict, limit: int, small: int) -> list[dict]:
    """Kleine Blöcke (< small Kacheln) mit dem kleinsten Nachbarblock zusammenlegen."""
    groups = {key: {"keys": [key], "tiles": set(t)} for key, t in pk.items()}
    owner = {key: key for key in pk}
    changed = True
    while changed:
        changed = False
        for gk in sorted(groups, key=lambda g: len(groups[g]["tiles"])):
            g = groups.get(gk)
            if g is None or len(g["tiles"]) >= small:
                continue
            neigh = set()
            for (br, bc) in g["keys"]:
                for d in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                    nb = (br + d[0], bc + d[1])
                    if nb in owner and owner[nb] != gk:
                        neigh.add(owner[nb])
            cand = [n for n in neigh if len(groups[n]["tiles"]) + len(g["tiles"]) <= limit]
            if not cand:
                continue
            tgt = min(cand, key=lambda n: len(groups[n]["tiles"]))
            groups[tgt]["keys"] += g["keys"]
            groups[tgt]["tiles"] |= g["tiles"]
            for key in g["keys"]:
                owner[key] = tgt
            del groups[gk]
            changed = True
            break
    return [{"keys": sorted(g["keys"]), "tiles": g["tiles"]} for g in groups.values()]


def block_label(key):
    r, c = key
    return f"{string.ascii_uppercase[r]}{c + 1:02d}"


def plan(args) -> dict:
    grid = Grid(args.scale)
    k = args.block or int(math.isqrt(args.limit))
    land = boundary_layers(args.buffer, "icc IN ('CH','LI')", "tlm_landesgebiet")
    land_mask = np.zeros((grid.rows, grid.cols), bool)
    for _n, (_m, l) in land.items():
        land_mask |= grid.rasterize(l)
    reg_mask, label, reg_bbox = region_mask(grid, args.region)
    base = land_mask & reg_mask
    cantons = boundary_layers(0, None, "tlm_kantonsgebiet")
    cmask = {n: grid.rasterize(l) for n, (_m, l) in cantons.items()}

    packages = []
    if args.scheme == "grid":
        for g in merge_small(blocks(base, k), args.limit, args.merge_below):
            packages.append({"id": "-".join(block_label(x) for x in g["keys"][:3])
                             + ("+" if len(g["keys"]) > 3 else ""), "tiles": g["tiles"]})
    else:
        for name, cm in sorted(cmask.items()):
            t = cm & base
            if not t.any():
                continue
            if t.sum() <= args.limit:
                packages.append({"id": slug(name), "tiles": set(map(tuple, np.argwhere(t)))})
            else:
                for g in merge_small(blocks(t, k), args.limit, args.merge_below):
                    packages.append({"id": slug(name) + "-" + block_label(g["keys"][0]),
                                     "tiles": g["tiles"]})
    for p in packages:
        p["tiles"] = sorted((int(r), int(c)) for r, c in p["tiles"])
        cnt = {n: sum(cm[r, c] for r, c in p["tiles"]) for n, cm in cmask.items()}
        p["cantons"] = [n for n, v in sorted(cnt.items(), key=lambda x: -x[1]) if v][:4]
        rs = [r for r, _ in p["tiles"]]; cs = [c for _, c in p["tiles"]]
        w, _, _, n = grid.tile_bbox(min(rs), min(cs))
        _, s, e, _ = grid.tile_bbox(max(rs), max(cs))
        p["bbox"] = [round(w, 6), round(s, 6), round(e, 6), round(n, 6)]
        p["n"] = len(p["tiles"])
    packages.sort(key=lambda p: (-p["bbox"][3], p["bbox"][0]))
    return {"grid": grid, "k": k, "label": label, "region_bbox": reg_bbox,
            "base": base, "packages": packages}


def slug(name: str) -> str:
    tr = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "è": "e", "é": "e", "â": "a",
                        "ê": "e", " ": "-", ".": "", "'": ""})
    return name.lower().translate(tr)


def sources(scale: int, bbox) -> tuple[list[str], list[int]]:
    """Blätter für bbox: lokal, wenn vollständig geladen (im manifest), sonst /vsicurl/."""
    man_path = B.SMR_DIR / "manifest.json"
    man = {a["name"]: a for a in json.loads(man_path.read_text())} if man_path.exists() else {}
    assets = stac.latest_assets(scale, bbox)
    paths = []
    for a in assets:
        local = B.SMR_DIR / f"pk{scale}" / a["name"]
        ok = (a["name"] in man and local.exists()
              and local.stat().st_size == man[a["name"]].get("size", -1))
        paths.append(str(local) if ok else "/vsicurl/" + a["href"])
    return paths, sorted({a["year"] for a in assets})


def build_package(pl: dict, p: dict, out: pathlib.Path, args) -> dict:
    """Baut ein Paket. Gewarpt wird je k×k-Block (nur das Rechteck der Paketkacheln darin),
    damit zusammengelegte, L-förmige Pakete nicht als grosses Rechteck gerechnet werden."""
    t_start = time.time()
    grid: Grid = pl["grid"]
    k = pl["k"]
    name = f"smr{args.scale}-{p['id']}"
    d = out / name
    tmp = out / "_tmp"
    d.mkdir(parents=True, exist_ok=True); tmp.mkdir(exist_ok=True)
    groups: dict[tuple, list] = {}
    for r, c in p["tiles"]:
        groups.setdefault((r // k, c // k), []).append((r, c))
    tiles, all_srcs, years = [], set(), set()
    for key in sorted(groups):
        part = groups[key]
        rs = [r for r, _ in part]; cs = [c for _, c in part]
        r0, c0 = min(rs), min(cs)
        rows, cols = max(rs) - r0 + 1, max(cs) - c0 + 1
        w, _, _, n = grid.tile_bbox(r0, c0)
        _, s, e, _ = grid.tile_bbox(r0 + rows - 1, c0 + cols - 1)
        bbox = (w, s, e, n)
        pinfo = {"dlon": grid.dlon, "dlat": grid.dlat, "width": cols * TILE,
                 "height": rows * TILE, "rows": rows, "cols": cols}
        srcs, yrs = sources(args.scale, bbox)
        all_srcs |= set(srcs); years |= set(yrs)
        keep_set = {(r - r0, c - c0) for r, c in part}
        warped = B.warp(srcs, bbox, pinfo, args.resampling, tmp)
        part_tiles = B.make_tiles(warped, pinfo, bbox, TILE, args.quality, args.subsampling,
                                  0.0, keep=lambda r, c: (r, c) in keep_set)
        warped.unlink()
        for t in part_tiles:  # globale Kachelnummer: eindeutig über alle Pakete
            t["href"] = f"files/r{t['row'] + r0:03d}c{t['col'] + c0:03d}.jpg"
        tiles += part_tiles
    years = sorted(years)
    bbox = tuple(p["bbox"])
    region = ", ".join(p["cantons"]) if p["cantons"] else p["id"]
    title = f"SMR{args.scale} {p['id']} ({region}) {B.ATTRIBUTION}"
    desc = (f"Swiss Map Raster 1:{args.scale}'000 (Ausgabe {B.years_text(years)}), "
            f"{grid.res} m/px, Paket {p['id']}: {region}. Quelle: {B.ATTRIBUTION}, "
            f"Open Government Data, Nutzungsbedingungen: {B.LICENSE_URL}. Keine offizielle "
            "Karte von swisstopo. Erzeugt vom Projekt Helvetopo.")
    kml_text = B.kml(title, desc, tiles, DRAW_ORDER[args.scale])
    kmz = d / f"{name}.kmz"
    B.write_kmz(kmz, kml_text, tiles)
    sizes = [len(t["data"]) for t in tiles]
    remote = sum(1 for x in all_srcs if x.startswith("/vsicurl/"))
    meta = {"name": name, "id": p["id"], "title": title, "scale": args.scale, "bbox": bbox,
            "res_m": grid.res, "resampling": args.resampling, "quality": args.quality,
            "subsampling": args.subsampling, "draw_order": DRAW_ORDER[args.scale],
            "tile": TILE, "tiles": len(tiles), "tiles_planned": p["n"],
            "jpeg_mean_kb": sum(sizes) // max(len(sizes), 1) // 1024,
            "jpeg_max_kb": max(sizes) // 1024 if sizes else 0,
            "kmz_mb": round(kmz.stat().st_size / 2**20, 1), "years": years,
            "cantons": p["cantons"], "sources": sorted(pathlib.Path(x).name for x in all_srcs),
            "sources_remote": remote, "seconds": round(time.time() - t_start, 1),
            "old_sheets": sorted(pathlib.Path(x).name for x in all_srcs
                                 if int(re.search(r"_(\d{4})_", pathlib.Path(x).name).group(1))
                                 < B.OLD_YEAR)}
    (d / "build.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    B.write_readme(d)
    print(f"  {name}: {len(tiles)} Kacheln, {meta['kmz_mb']} MB, {meta['seconds']} s"
          + (f", {remote} Blätter per /vsicurl/" if remote else ""), flush=True)
    return meta


def overview(pl: dict, path: pathlib.Path, title: str) -> None:
    grid: Grid = pl["grid"]
    base = pl["base"]
    rr, cc = np.nonzero(base)
    if not len(rr):
        return
    r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
    px = max(3, min(40, 1400 // max(c1 - c0, 1)))
    W, H = (c1 - c0) * px, (r1 - r0) * px + 30
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    rng = np.random.default_rng(7)
    for p in pl["packages"]:
        col = tuple(int(x) for x in rng.integers(90, 230, 3))
        for r, c in p["tiles"]:
            x, y = (c - c0) * px, (r - r0) * px + 30
            d.rectangle([x, y, x + px - 1, y + px - 1], fill=col)
    for p in pl["packages"]:
        rs = [r for r, _ in p["tiles"]]; cs = [c for _, c in p["tiles"]]
        x = (np.mean(cs) - c0) * px; y = (np.mean(rs) - r0) * px + 30
        d.text((x - 20, y - 8), f"{p['id']}\n{p['n']}", fill="black", font=FONT)
    d.text((6, 6), title, fill="black", font=FONT)
    im.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scale", type=int, choices=sorted(RES), default=25)
    ap.add_argument("--scheme", choices=["grid", "canton"], default="grid")
    ap.add_argument("--region", nargs="+", default=["testgebiet"],
                    help="ch | testgebiet | bbox W S E N")
    ap.add_argument("--limit", type=int, default=484, help="max. Kacheln je Paket")
    ap.add_argument("--block", type=int, help="Blockkante k (Standard: √limit)")
    ap.add_argument("--merge-below", type=int, default=150,
                    help="Pakete mit weniger Kacheln mit Nachbarn zusammenlegen")
    ap.add_argument("--buffer", type=float, default=500, help="Puffer um CH/LI in m")
    ap.add_argument("--resampling", default="lanczos")
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--subsampling", default="420", choices=["420", "422", "444"])
    ap.add_argument("--dry-run", action="store_true", help="nur planen, nichts bauen")
    ap.add_argument("--only", nargs="*", help="nur diese Paket-IDs bauen")
    ap.add_argument("--out-root", type=pathlib.Path, default=B.WORK / "pakete",
                    help="Oberordner der Ausgabe (Standard work/raster_kmz/pakete)")
    ap.add_argument("--force", action="store_true",
                    help="auch Pakete neu bauen, deren build.json schon existiert")
    args = ap.parse_args()

    pl = plan(args)
    suffix = "" if args.limit == 484 and not args.block else f"-l{args.limit}b{pl['k']}"
    out = args.out_root / f"{args.scheme}-smr{args.scale}-{pl['label']}{suffix}"
    out.mkdir(parents=True, exist_ok=True)
    pk = pl["packages"]
    total = sum(p["n"] for p in pk)
    head = (f"{args.scheme} SMR{args.scale} {pl['label']}: {len(pk)} Pakete, {total} Kacheln, "
            f"Limit {args.limit}, Block {pl['k']}×{pl['k']}")
    print(head)
    for p in pk:
        print(f"  {p['id']:14s} {p['n']:4d} Kacheln  {', '.join(p['cantons'])}")
    overview(pl, out / "uebersicht.png", head)
    plan_json = {"scale": args.scale, "scheme": args.scheme, "region": pl["label"],
                 "limit": args.limit, "block": pl["k"], "res_m": pl["grid"].res,
                 "tiles_total": total, "est_gb": round(total * 340 / 2**20, 2),
                 "packages": [{k: v for k, v in p.items() if k != "tiles"} for p in pk]}
    (out / "plan.json").write_text(json.dumps(plan_json, indent=1, ensure_ascii=False))
    if args.dry_run:
        return
    metas = []
    for p in pk:
        if args.only and p["id"] not in args.only:
            continue
        bj = out / f"smr{args.scale}-{p['id']}" / "build.json"
        if bj.exists() and not args.force:
            m = json.loads(bj.read_text())
            if m.get("tiles_planned") == p["n"] and m.get("sources_remote", 0) == 0:
                print(f"  {m['name']}: vorhanden, übersprungen", flush=True)
                metas.append(m)
                continue
        metas.append(build_package(pl, p, out, args))
    shutil.rmtree(out / "_tmp", ignore_errors=True)
    lines = [f"Swiss Map Raster 1:{args.scale}'000 als Garmin Custom Maps (KMZ) – {pl['label']}",
             "", "Kartendaten: ©swisstopo (Open Government Data, "
             f"{B.LICENSE_URL}). Keine offizielle Karte von swisstopo.", "",
             f"Garmin zählt die Kacheln aller Custom Maps auf dem Gerät zusammen "
             f"(GPSMAP 66/67, Montana 7xx: 500; ältere Geräte: 100). Jedes Paket hat höchstens "
             f"{args.limit} Kacheln: auf 500er-Geräten also ein Paket gleichzeitig "
             "(plus ggf. eine kleine Übersicht).", "", "Pakete:"]
    for m in metas:
        lines.append(f"  {m['name']}.kmz  {m['tiles']:4d} Kacheln  {m['kmz_mb']:6.1f} MB  "
                     f"{', '.join(m['cantons'])}")
    (out / "LIESMICH.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
