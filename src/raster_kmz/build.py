"""Baut eine Garmin-KMZ-Custom-Map aus Swiss Map Raster (SMR).

Ablauf:
  1. VRT-Mosaik der benötigten SMR-Blätter (EPSG:2056)
  2. gdalwarp nach EPSG:4326, Ausdehnung exakt = Zielgebiet, Pixel in Metern ≈ quadratisch
  3. Kacheln ≤ 1024 × 1024 px als Baseline-JPEG (nicht progressiv), leere Kacheln weglassen
  4. doc.kml mit GroundOverlay/LatLonBox/drawOrder, Quellenangabe ©swisstopo
  5. ZIP → .kmz (doc.kml zuerst)

Aufruf:
  python3 build.py --variant alpstein-smr25            # vordefinierte Variante (variants.py)
  python3 build.py --list                               # Varianten mit Kachelzahl anzeigen
  python3 build.py --variant x --scale 25 --bbox 9.3 47.2 9.4 47.3 --res 1.25
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import os
import pathlib
import shutil
import sys
import zipfile
from xml.sax.saxutils import escape

import numpy as np
from osgeo import gdal
from PIL import Image

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

import variants as V

gdal.UseExceptions()

SMR_DIR = paths.SMR_DIR
WORK = pathlib.Path(__file__).resolve().parents[2] / "work" / "raster_kmz"

ATTRIBUTION = "©swisstopo"
LICENSE_URL = "https://www.swisstopo.admin.ch/ogd-conditions"

# Ausgaben vor diesem Jahr gelten als „ältere Ausgabe“. Betrifft vier Grenz-/Seeblätter
# (SMR25 1035, 1056, 1282, 2220: 1984–2003), deren neueste frei verfügbare Ausgabe so alt ist.
OLD_YEAR = 2010


def years_text(years) -> str:
    """Ausgabejahre als Text; alte Ausgaben gekennzeichnet."""
    new = [str(y) for y in years if y >= OLD_YEAR]
    old = [str(y) for y in years if y < OLD_YEAR]
    text = ", ".join(new)
    if old:
        text += ("; " if new else "") + "ältere Ausgabe " + ", ".join(old) + (
            " (Grenz-/Seeblatt, neueste frei verfügbare Ausgabe dieses Blatts)")
    return text


# Mittlerer Erdradius für Meter→Grad (WGS84-Äquatorradius reicht für Kachelplanung).
M_PER_DEG_LAT = 111_195.0


def deg_per_px(res_m: float, lat: float) -> tuple[float, float]:
    """Pixelgrösse in Grad (lon, lat) für eine Bodenauflösung res_m bei Breite lat."""
    dlat = res_m / M_PER_DEG_LAT
    dlon = res_m / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    return dlon, dlat


def plan(bbox, res_m: float, tile: int) -> dict:
    w, s, e, n = bbox
    dlon, dlat = deg_per_px(res_m, (s + n) / 2)
    width = math.ceil((e - w) / dlon - 1e-9)
    height = math.ceil((n - s) / dlat - 1e-9)
    cols, rows = math.ceil(width / tile), math.ceil(height / tile)
    return {"dlon": dlon, "dlat": dlat, "width": width, "height": height,
            "cols": cols, "rows": rows, "tiles_max": cols * rows}


def sheets_for(scale: int, bbox) -> list[pathlib.Path]:
    manifest = json.loads((SMR_DIR / "manifest.json").read_text())
    w, s, e, n = bbox
    out = []
    for a in manifest:
        if a["scale"] != scale:
            continue
        bw, bs, be, bn = a["bbox"]
        if bw < e and be > w and bs < n and bn > s:
            p = SMR_DIR / f"pk{scale}" / a["name"]
            if not p.exists():
                sys.exit(f"Blatt fehlt: {p} (fetch_smr.py laufen lassen)")
            out.append(p)
    if not out:
        sys.exit("keine Blätter für das Gebiet gefunden")
    return out


def warp(sources, bbox, p, resampling: str, tmp: pathlib.Path) -> pathlib.Path:
    vrt = tmp / "mosaic.vrt"
    gdal.BuildVRT(str(vrt), [str(x) for x in sources])
    out = tmp / f"warped_{resampling}.tif"
    w, s, e, n = bbox
    # Ausdehnung auf ganze Pixel erweitern (Ost/Süd), damit die Pixelgrösse exakt bleibt.
    e2 = w + p["width"] * p["dlon"]
    s2 = n - p["height"] * p["dlat"]
    gdal.Warp(str(out), str(vrt), options=gdal.WarpOptions(
        dstSRS="EPSG:4326", outputBounds=(w, s2, e2, n),
        width=p["width"], height=p["height"],
        resampleAlg=resampling, dstAlpha=True, multithread=True,
        warpOptions=["NUM_THREADS=ALL_CPUS"],
        creationOptions=["TILED=YES", "COMPRESS=ZSTD", "BIGTIFF=IF_SAFER"],
        warpMemoryLimit=2048))
    return out


def jpeg_bytes(rgb: np.ndarray, quality: int, subsampling: str) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(rgb, "RGB").save(
        buf, "JPEG", quality=quality, progressive=False, optimize=True,
        subsampling={"444": 0, "422": 1, "420": 2}[subsampling])
    return buf.getvalue()


def make_tiles(warped: pathlib.Path, p: dict, bbox, tile: int, quality: int,
               subsampling: str, min_coverage: float, keep=None):
    """Kacheln schneiden. keep(row, col) → bool wählt Kacheln aus (z. B. Landesmaske)."""
    ds = gdal.Open(str(warped))
    gt = ds.GetGeoTransform()
    tiles = []
    for r in range(p["rows"]):
        for c in range(p["cols"]):
            if keep is not None and not keep(r, c):
                continue
            x0, y0 = c * tile, r * tile
            tw, th = min(tile, p["width"] - x0), min(tile, p["height"] - y0)
            arr = ds.ReadAsArray(x0, y0, tw, th)  # (4, th, tw)
            alpha = arr[3].astype(np.float32) / 255.0
            cover = float(alpha.mean())
            if cover <= min_coverage:
                continue
            rgb = arr[:3].astype(np.float32)
            rgb = rgb * alpha + 255.0 * (1 - alpha)  # Lücken weiss
            rgb = np.clip(rgb + 0.5, 0, 255).astype(np.uint8).transpose(1, 2, 0)
            data = jpeg_bytes(np.ascontiguousarray(rgb), quality, subsampling)
            west = gt[0] + x0 * gt[1]
            north = gt[3] + y0 * gt[5]
            east = west + tw * gt[1]
            south = north + th * gt[5]
            tiles.append({"row": r, "col": c, "w": tw, "h": th, "data": data,
                          "north": north, "south": south, "east": east, "west": west,
                          "coverage": cover})
    return tiles


def kml(title: str, description: str, tiles, draw_order: int) -> str:
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="http://www.opengis.net/kml/2.2">',
             "<Document>",
             f"<name>{escape(title)}</name>",
             f"<description>{escape(description)}</description>",
             "<Folder>",
             f"<name>{escape(title)}</name>"]
    for t in tiles:
        parts += [
            "<GroundOverlay>",
            f"<name>{escape(t['href'].split('/')[-1][:-4])}</name>",
            f"<drawOrder>{draw_order}</drawOrder>",
            f"<Icon><href>{t['href']}</href></Icon>",
            "<LatLonBox>",
            f"<north>{t['north']:.9f}</north>",
            f"<south>{t['south']:.9f}</south>",
            f"<east>{t['east']:.9f}</east>",
            f"<west>{t['west']:.9f}</west>",
            "<rotation>0</rotation>",
            "</LatLonBox>",
            "</GroundOverlay>"]
    parts += ["</Folder>", "</Document>", "</kml>", ""]
    return "\n".join(parts)


def write_kmz(path: pathlib.Path, kml_text: str, tiles) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("doc.kml", date_time=(2026, 1, 1, 0, 0, 0)),
                   kml_text.encode("utf-8"), compress_type=zipfile.ZIP_DEFLATED)
        for t in tiles:
            # JPEG ist schon komprimiert → speichern ohne Deflate
            z.writestr(zipfile.ZipInfo(t["href"], date_time=(2026, 1, 1, 0, 0, 0)),
                       t["data"], compress_type=zipfile.ZIP_STORED)


def write_readme(out_dir: pathlib.Path) -> pathlib.Path:
    """README.txt aus README-vorlage.txt und build.json erzeugen."""
    meta = json.loads((out_dir / "build.json").read_text())
    tpl = (pathlib.Path(__file__).with_name("README-vorlage.txt")).read_text(encoding="utf-8")
    w, s, e, n = meta["bbox"]
    text = tpl.format(
        title=meta["title"], underline="=" * len(meta["title"]), scale=meta["scale"],
        years=years_text(meta["years"]), kmz=meta["name"] + ".kmz",
        west=f"{w:.3f}", east=f"{e:.3f}", south=f"{s:.3f}", north=f"{n:.3f}",
        res=meta["res_m"], tiles=meta["tiles"], kmz_mb=meta["kmz_mb"],
        draw_order=meta["draw_order"])
    path = out_dir / "README.txt"
    path.write_text(text, encoding="utf-8")
    return path


def build(cfg: dict, keep_tmp: bool = False) -> dict:
    name = cfg["name"]
    bbox = tuple(cfg["bbox"])
    tile = cfg.get("tile", 1024)
    p = plan(bbox, cfg["res"], tile)
    out_dir = WORK / name
    tmp = WORK / "tmp" / name
    tmp.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    sources = sheets_for(cfg["scale"], bbox)
    print(f"[{name}] {len(sources)} Blätter, {p['width']}×{p['height']} px, "
          f"{p['cols']}×{p['rows']} Kacheln max.", flush=True)
    warped = warp(sources, bbox, p, cfg.get("resampling", "lanczos"), tmp)
    tiles = make_tiles(warped, p, bbox, tile, cfg.get("quality", 85),
                       cfg.get("subsampling", "420"), cfg.get("min_coverage", 0.0))
    for t in tiles:
        t["href"] = f"files/r{t['row']:02d}c{t['col']:02d}.jpg"

    manifest = json.loads((SMR_DIR / "manifest.json").read_text())
    names = {s.name for s in sources}
    years = sorted({a["year"] for a in manifest if a["name"] in names})
    title = f"{cfg['title']} {ATTRIBUTION}"
    description = (
        f"{cfg['title']}. Swiss Map Raster 1:{cfg['scale']}'000 "
        f"(Ausgabe {years_text(years)}), {cfg['res']} m/px. "
        f"Quelle: {ATTRIBUTION}, Open Government Data, Nutzungsbedingungen: {LICENSE_URL}. "
        "Keine offizielle Karte von swisstopo. Erzeugt vom Projekt Helvetopo "
        f"am {dt.date.today().isoformat()}.")
    kml_text = kml(title, description, tiles, cfg.get("draw_order", 51))

    kmz_path = out_dir / f"{name}.kmz"
    write_kmz(kmz_path, kml_text, tiles)
    (out_dir / "doc.kml").write_text(kml_text, encoding="utf-8")

    sizes = [len(t["data"]) for t in tiles]
    meta = {
        "name": name, "title": title, "scale": cfg["scale"], "bbox": bbox,
        "res_m": cfg["res"], "resampling": cfg.get("resampling", "lanczos"),
        "quality": cfg.get("quality", 85), "subsampling": cfg.get("subsampling", "420"),
        "draw_order": cfg.get("draw_order", 51), "tile": tile,
        "grid": [p["cols"], p["rows"]], "pixels": [p["width"], p["height"]],
        "tiles": len(tiles), "jpeg_max_kb": max(sizes) // 1024,
        "jpeg_mean_kb": sum(sizes) // len(sizes) // 1024,
        "kmz_mb": round(kmz_path.stat().st_size / 2**20, 1),
        "sheets": [s.name for s in sources], "years": years,
    }
    (out_dir / "build.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    write_readme(out_dir)
    if not keep_tmp:
        shutil.rmtree(tmp)
    print(f"[{name}] {meta['tiles']} Kacheln, KMZ {meta['kmz_mb']} MB, "
          f"JPEG ø {meta['jpeg_mean_kb']} KB / max {meta['jpeg_max_kb']} KB → {kmz_path}")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", nargs="*", help="Name(n) aus variants.py oder 'all'")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--scale", type=int)
    ap.add_argument("--bbox", nargs=4, type=float)
    ap.add_argument("--res", type=float)
    ap.add_argument("--title")
    ap.add_argument("--resampling")
    ap.add_argument("--quality", type=int)
    ap.add_argument("--subsampling", choices=["444", "422", "420"])
    ap.add_argument("--draw-order", type=int)
    ap.add_argument("--keep-tmp", action="store_true")
    ap.add_argument("--readme-only", action="store_true",
                    help="nur README.txt aus vorhandenem build.json neu erzeugen")
    a = ap.parse_args()

    if a.list:
        for v in V.VARIANTS.values():
            p = plan(v["bbox"], v["res"], v.get("tile", 1024))
            print(f"{v['name']:28s} SMR{v['scale']:<3d} {v['res']:5.2f} m/px "
                  f"{p['width']:6d}×{p['height']:<6d} px  {p['cols']:2d}×{p['rows']:<2d} "
                  f"= {p['tiles_max']:4d} Kacheln max.")
        return
    names = a.variant or []
    if names == ["all"]:
        names = list(V.VARIANTS)
    for n in names:
        cfg = dict(V.VARIANTS.get(n, {"name": n}))
        for k in ("scale", "bbox", "res", "title", "resampling", "quality", "subsampling"):
            if getattr(a, k) is not None:
                cfg[k] = getattr(a, k)
        if a.draw_order is not None:
            cfg["draw_order"] = a.draw_order
        cfg.setdefault("title", n)
        if a.readme_only:
            print(write_readme(WORK / n))
        else:
            build(cfg, a.keep_tmp)


if __name__ == "__main__":
    main()
