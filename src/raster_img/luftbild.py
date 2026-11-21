"""Luftbild-Karte aus SWISSIMAGE 10 cm als Raster-IMG (FID 7707), auf Basis von release.py.

Gleicher Aufbau wie die Pixelkarte (release.py): eine GMP je Zelle des landesweiten Gitters, je Zoomstufe
eigene Bilder, 1 px Überlappung, oberste Ebene leer. Unterschiede:
- eine Quelle für alle Stufen: SWISSIMAGE. Die Stufen sind Resampling-Stufen derselben Bilder;
- feine Stufen aus der 0,4-m-Übersicht des 10-cm-COG, grobe Stufen aus dem fertigen 2-m-Asset
  (beides lädt swissimage.py);
- Verkleinern mit `-r average` statt `cubic` (Fotos rauschen sonst), JPEG q80 statt q85.

Zoomstufen (Zelle 0,0294° wie Pixel 10-1000, Faktor relativ zu DPP25 = 1,15e-5 °/px):

| bits   | 24   | 23   | 22   | 21  | 20  | 19  | 18  | oben |
|--------|------|------|------|-----|-----|-----|-----|------|
| Faktor | 0,5  | 1    | 2    | 4   | 8   | 16  | 64  | 17   |
| N-S    | 0,64 m | 1,3 m | 2,6 m | 5 m | 10 m | 20 m | 82 m |   |
| Quelle | 0,4 m | 0,4 m | 0,4 m | 2 m | 2 m | 2 m | 2 m |   |

Map-IDs: 77070001 … fortlaufend über die Zellen der Schweiz (wie release.id_table), 77079000 = gmapi-Übersicht.
Diese Tabelle gilt für `detail-voll` (bis Gerätetest 12). `detail` hat seit Gerätetest 12 (X3) nur die Ebenen
24..22 mit Bildern, Ebene 21 leer, und nur die feine Serie. Am Gerät liegt `detail` über `kompakt`.
Für die ganze Schweiz teilt `--split-max 4e9` die Zellen in Teile ohne Überlappung (split_parts).

Variante `kompakt` (FID 7708): die ganze Schweiz in einer Datei unter 4 GiB. Zelle 0,1176° wie Pixel 50-1000,
alle Stufen aus dem 2-m-Asset, Ebenen lückenlos 24..18 (Gerätetest 3, wie Pixel 50-1000):

| bits   | 24    | 23    | 22    | 21   | 20   | 19   | 18   | oben |
|--------|-------|-------|-------|------|------|------|------|------|
| Faktor | 2     | 2     | 4     | 8    | 16   | 32   | 64   | 17   |
| N-S    | 2,6 m | 2,6 m | 5 m   | 10 m | 20 m | 41 m | 82 m |      |

Aufruf:
  python3 -I luftbild.py --region testgebiet --download          # STAC-Kacheln für die Zellen laden
  python3 -I luftbild.py --region testgebiet --gmapi [--version 2026-11] [--quality 80] [--dry-run]
  # → work/raster_img/luftbild/Helvetopo_Luftbild_Testgebiet_2026-11.img, „Helvetopo Luftbild 2026-11 Testgebiet“
  python3 -I luftbild.py --variant kompakt --region schweiz --download     # nur 2-m-Assets
  python3 -I luftbild.py --variant kompakt --region schweiz --gmapi
  # → work/raster_img/luftbild-kompakt/Helvetopo_Luftbild-kompakt_Schweiz_2026-11.img
  python3 -I luftbild.py --variant detail --region schweiz --split-max 4e9 --gmapi --routes <PBF>
  # → work/raster_img/luftbild-detail/Helvetopo_Luftbild_Detail_<Teil>_2026-11.img, regionen.geojson
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quellstand as Q  # noqa: E402
import regions as RG  # noqa: E402
import release as R  # noqa: E402
import swissimage as SI  # noqa: E402
from rasterimg import GmpOptions, build_gmp, build_mps, patch_gmp_file, write_img  # noqa: E402
from smr_tiles import cut_tiles  # noqa: E402

FID = 7707
FINE_RES = 0.4                       # Übersicht aus dem 10-cm-COG (m)
TOP = 17
# (bits, Quelle, Faktor zu DPP25) – feinste zuerst, lückenlos 24..18 (release.check_levels, Gerätetest 3)
LEVELS = ((24, "fein", 0.5), (23, "fein", 1), (22, "fein", 2), (21, "2m", 4), (20, "2m", 8), (19, "2m", 16),
          (18, "2m", 64))
# detail: nur die feinen Ebenen 24..22, oberste Ebene 21 leer, nur feine Serie (Gerätetest 12, X3). Am Gerät
# liegt detail über kompakt (7708). kompakt zeigt die gröberen Stufen. Weniger GMPs im Bild beim Herauszoomen.
LEVELS_DETAIL = LEVELS[:3]
# 24 und 23 mit denselben Bildern (2-m-Asset in voller Auflösung, Überzoom auf 24)
LEVELS_KOMPAKT = ((24, "2m", 2), (23, "2m", 2), (22, "2m", 4), (21, "2m", 8), (20, "2m", 16), (19, "2m", 32),
                  (18, "2m", 64))
QUALITY = 80
# Bildüberlappung mindestens 2 Karteneinheiten (release.overlap_px). Bei detail misst ein Pixel auf bits 24 nur
# 0,27 Einheiten: 1 px Überlappung rundet dort an ca. 70 % der Bildkanten auf 0.
OVERLAP_MU = 2


@dataclasses.dataclass(frozen=True)
class Variant:
    fid: int
    top: int
    levels: tuple
    label: str                       # Kartenname „Helvetopo <label> <Version>“
    file: str                        # Dateiname „Helvetopo_<file>_<Gebiet>_<Version>“
    out: str                         # Ausgabeordner unter work/raster_img/
    quality: int = QUALITY
    series: str = "beide"            # "fein": nur feine Serie (alle Ebenen > release.COARSE_MAX_BITS)

    @property
    def fine_res(self) -> float | None:      # Übersicht aus dem 10-cm-COG oder None (nur 2-m-Asset)
        return FINE_RES if any(src == "fein" for _, src, _ in self.levels) else None


VARIANTS = {
    "detail": Variant(FID, 21, LEVELS_DETAIL, "Luftbild Detail", "Luftbild_Detail", "luftbild-detail",
                      series="fein"),
    "detail-voll": Variant(FID, TOP, LEVELS, "Luftbild", "Luftbild", "luftbild"),     # bis Gerätetest 12
    "kompakt": Variant(7708, 17, LEVELS_KOMPAKT, "Luftbild kompakt", "Luftbild-kompakt", "luftbild-kompakt"),
}


def plan(v: Variant = VARIANTS["detail"]) -> R.Plan:
    R.check_levels(f"luftbild-{v.fid}", v.top, v.levels)
    return R.Plan(f"luftbild-{v.fid}", v.top, v.levels)


def default_names(region: str, version: str, v: Variant = VARIANTS["detail"]) -> tuple[str, str]:
    area = R.REGION_FILE.get(region, region.capitalize())
    shown = R.REGION_NAME.get(region, area)
    name = f"{R.PREFIX} {v.label} {version}" + ("" if region == "schweiz" else f" {shown}")
    return name, f"{R.PREFIX}_{v.file}_{area}_{version}"


def source_dir(src: str) -> str:
    return SI.fine_dir(FINE_RES) if src == "fein" else os.path.join(SI.DL, "2m")


def vrt_for(src: str, workdir: str) -> str:
    os.makedirs(workdir, exist_ok=True)
    vrt = os.path.join(workdir, f"swissimage_{src}.vrt")
    if not os.path.exists(vrt):
        tifs = sorted(glob.glob(os.path.join(source_dir(src), "*.tif")))
        if not tifs:
            raise SystemExit(f"Quelle fehlt: {source_dir(src)} (zuerst --download)")
        tmp = f"{vrt}.{os.getpid()}.tmp.vrt"
        lst = f"{vrt}.{os.getpid()}.txt"         # Dateiliste: die ganze Schweiz hat über 40 000 Kacheln
        with open(lst, "w") as f:
            f.write("\n".join(tifs) + "\n")
        subprocess.run(["gdalbuildvrt", "-q", "-input_file_list", lst, tmp], check=True)
        os.remove(lst)
        os.replace(tmp, vrt)
    return vrt


def sources(area) -> dict:
    """Kacheln, Befliegungsjahre und Stand im Gebiet (aus downloads/swissimage/manifest.json)."""
    w, s, e, n = area
    man = [m for m in SI.load_manifest()
           if not (m["bbox"][2] < w or m["bbox"][0] > e or m["bbox"][3] < s or m["bbox"][1] > n)]
    years = sorted({m["year"] for m in man})
    return dict(tiles=len(man), years=years, updated=max((m.get("updated") or "" for m in man), default=""))


def _years(src) -> str:
    y = src["years"]
    return f"Befliegung {y[0]}" if len(y) == 1 else f"Befliegungen {y[0]}–{y[-1]}"


def copyright_lines(area, product: str) -> tuple[str, ...]:
    return ("©swisstopo", f"SWISSIMAGE 10 cm ({_years(sources(area))}), swisstopo OGD",
            f"{product}, inoffizielle Karte")


def quellstand_text(area, product: str, fid: int, fine_res: float | None = FINE_RES) -> str:
    src = sources(area)
    used = (f"Übersicht {str(fine_res).replace('.', ',')} m des 10-cm-COG und Asset 2 m" if fine_res
            else "Asset 2 m")
    t = [f"Quellstand {product}", f"Erstellt: {_dt.date.today().isoformat()}, Family-ID {fid}", "",
         f"- SWISSIMAGE 10 cm: {src['tiles']} Kacheln zu 1 km, {_years(src)}, Stand der Items bis "
         f"{src["updated"][:10]}, verwendet: {used}, "
         f"STAC-Collection {SI.COLLECTION} (data.geo.admin.ch)",
         "", "Lizenz: " + Q.LICENSE_LINE]
    return "\n".join(t) + "\n"


def gmp_options(p: R.Plan, cr: tuple[str, ...], product: str) -> GmpOptions:
    return dataclasses.replace(GmpOptions(), **R.R_STYLE,
                               levels=(p.top,) + tuple(sorted(b for b, _, _ in p.levels)),
                               copyright=cr,
                               hdr_comment1=("©swisstopo, Daten unter OGD (opendata.swiss).",
                                             f"{product}, inoffizielle Karte."),
                               hdr_comment2=("SWISSIMAGE", "©swisstopo"))


def render_aerial(src, factor, bounds, out: str, quality: int):
    """SWISSIMAGE-Bilder für eine Fläche: Pixelgrösse DPP25 × factor, Bildkante ≤ 512 px, 1 px Überlappung.
    Verkleinern mit `average` (Fotos rauschen sonst), Vergrössern (factor ≤ 0,5) mit `cubic`."""
    w, so, e, n = bounds
    px = round((e - w) / (RG.DPP25 * factor))
    k = R.split(px)
    dpp = (e - w) / px
    ov = R.overlap_px(dpp, OVERLAP_MU)
    tmp = tempfile.mkdtemp(dir=os.path.join(out, "_vrt"))
    try:
        tif = os.path.join(tmp, f"{src}_{factor}.tif")
        subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-te", repr(w),
                        repr(so - ov * dpp), repr(e + ov * dpp), repr(n), "-ts", str(px + ov), str(px + ov),
                        "-r", "cubic" if factor <= 0.5 else "average", "-wo", "INIT_DEST=255",
                        "-wo", "NUM_THREADS=2", "-multi", "-co", "TILED=YES",
                        vrt_for(src, os.path.join(out, "_vrt")), tif], check=True)
        return cut_tiles(tif, w, n, dpp, k, k, tile_px=px // k, quality=quality, overlap=ov)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_one(job):
    out, fid, product, cr, quality, p, kind, bounds, mid = job
    dest = os.path.join(out, R.gmp_dir(fid, p, quality, kind) + f"_ov{OVERLAP_MU}", f"{mid:08d}.gmp")
    if os.path.exists(dest):
        return mid, os.path.getsize(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    data = R.series_gmp(mid, bounds, kind, p.levels, gmp_options(p, cr, product), render_aerial, (out, quality))
    with open(dest + ".part", "wb") as f:
        f.write(data)
    os.replace(dest + ".part", dest)
    return mid, len(data)


def select_cells(p: R.Plan, region: str, bbox, out: str):
    mask_region = region
    if region in R.TEST_AREAS:
        mask_region, box = R.TEST_AREAS[region]
        bbox = bbox or list(box)
    cells = p.cells(RG.region_mask(mask_region, os.path.join(out, "_mask")))
    if bbox:
        bw, bs, be, bn = bbox
        cells = [(c, r) for c, r in cells if not (p.bounds(c, r)[2] < bw or p.bounds(c, r)[0] > be
                                                   or p.bounds(c, r)[3] < bs or p.bounds(c, r)[1] > bn)]
    bb = [p.bounds(c, r) for c, r in cells]
    area = (min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb))
    return cells, area


IMG_OVERHEAD = 64 * 1024                     # je Unterdatei (write_img: Blockgrösse 64 KiB)
# Namen der Streifen, wenn split_parts eine Region teilt: Achse x (West → Ost) bzw. y (Nord → Süd)
STRIPS = {"x": {2: ("West", "Ost"), 3: ("West", "Mitte", "Ost"), 4: ("West", "Mitte-West", "Mitte-Ost", "Ost")},
          "y": {2: ("Nord", "Süd"), 3: ("Nord", "Mitte", "Süd"), 4: ("Nord", "Mitte-Nord", "Mitte-Süd", "Süd")}}


def img_bytes(sizes) -> int:
    """Grösse der IMG aus den GMP-Grössen (Kopf und MPS je ein Block, jede GMP auf 64 KiB aufgerundet)."""
    return IMG_OVERHEAD * (1 + len(sizes)) + sum(-(-n // IMG_OVERHEAD) * IMG_OVERHEAD for n in sizes)


def split_parts(p: R.Plan, cells, size: dict, limit: float, workdir: str) -> list[dict]:
    """Teilt die Zellen der Schweiz in Teile ohne Überlappung, je IMG höchstens `limit` Bytes.

    Grundlage ist die Teilung "regionen" (release.PARTITIONS): Jede grobe Zelle gehört ganz zu einer Region.
    Ist eine Region zu gross, teilt sie sich in n Streifen entlang ihrer längeren Achse, mit Grenzen auf dem
    Gitter der groben Zellen und möglichst gleich grossen Teilen (`size` = GMP-Grösse je Zelle).
    Ergebnis: [{id, file, label, region, suffix, cells}], Reihenfolge wie PARTITIONS."""
    import math
    have = set(cells)
    parts = []
    for reg in R.PARTITIONS["regionen"]:
        rc = [c for c in R.partition_cells(p, "regionen", reg, workdir) if c in have]
        coarse = sorted({p.coarse_of(*c) for c in rc})
        xs, ys = [x for x, _ in coarse], [y for _, y in coarse]
        wide = (max(xs) - min(xs) + 1) * math.cos(math.radians(46.8)) >= (max(ys) - min(ys) + 1)
        axis, ax = ("x", 0) if wide else ("y", 1)
        keys = sorted({k[ax] for k in coarse})
        by = {k: [c for c in rc if p.coarse_of(*c)[ax] == k] for k in keys}
        n = max(1, math.ceil(img_bytes([size[c] for c in rc]) / limit))
        while True:
            groups = _balanced(keys, {k: sum(size[c] for c in by[k]) for k in keys}, n)
            gcells = [[c for k in g for c in by[k]] for g in groups]
            if all(img_bytes([size[c] for c in g]) <= limit for g in gcells):
                break
            n += 1
            if n > len(keys) or n not in STRIPS[axis]:
                raise SystemExit(f"{reg}: keine Teilung in Streifen unter {limit / 1e9:.2f} GB")
        base, shown = R.REGION_FILE[reg], R.REGION_NAME.get(reg, R.REGION_FILE[reg])
        for i, g in enumerate(gcells):
            suf = STRIPS[axis][n][i] if n > 1 else ""
            ascii_suf = suf.replace("ü", "ue")
            parts.append(dict(id=reg + (f"-{ascii_suf.lower()}" if suf else ""),
                              file=base + (f"-{ascii_suf}" if suf else ""),
                              label=shown + (f" {suf}" if suf else ""),
                              region=reg, suffix=suf, cells=sorted(g)))
    got = sorted(c for pt in parts for c in pt["cells"])
    if got != sorted(cells):
        raise SystemExit(f"Teilung unvollständig: {len(got)} von {len(cells)} Zellen")
    return parts


def _balanced(keys, weight: dict, n: int) -> list[list]:
    """Teilt die geordneten `keys` in n zusammenhängende Gruppen mit möglichst gleicher Summe von `weight`."""
    total = sum(weight.values())
    cum, acc = [], 0
    for k in keys:
        acc += weight[k]
        cum.append(acc)
    cuts, start = [], 0
    for i in range(1, n):
        target = total * i / n
        j = min(range(start, len(keys) - (n - i)), key=lambda x: abs(cum[x] - target))
        cuts.append(j + 1)
        start = j + 1
    bounds = [0] + cuts + [len(keys)]
    return [keys[bounds[i]:bounds[i + 1]] for i in range(n)]


def parts_geojson(p: R.Plan, parts: list[dict], sizes: dict, product: str, fn: str) -> None:
    """Umrisse der Teile (Vereinigung der Zellen) mit Zellzahl, Landfläche CH/FL und IMG-Grösse."""
    import json
    from osgeo import ogr, osr
    ogr.UseExceptions()
    ds = ogr.Open(RG.BOUNDARIES)
    lay = ds.GetLayerByName("tlm_landesgebiet")
    land = None
    for f in lay:
        if f.GetField("icc") in ("CH", "LI"):
            g = f.GetGeometryRef().Clone()
            g.FlattenTo2D()
            land = g if land is None else land.Union(g)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(wgs, lay.GetSpatialRef())
    feats = []
    for pt in parts:
        u = ogr.Geometry(ogr.wkbMultiPolygon)
        for c, r in pt["cells"]:
            w, s_, e, n = p.bounds(c, r)
            ring = ogr.Geometry(ogr.wkbLinearRing)
            for x, y in ((w, s_), (e, s_), (e, n), (w, n), (w, s_)):
                ring.AddPoint_2D(round(x, 6), round(y, 6))
            poly = ogr.Geometry(ogr.wkbPolygon)
            poly.AddGeometry(ring)
            u.AddGeometry(poly)
        g = u.UnionCascaded()
        g2 = g.Clone()
        g2.Transform(tr)
        name = RG.REGIONS[pt["region"]][0] + (f" {pt['suffix']}" if pt["suffix"] else "")
        props = dict(id=pt["id"], name=name, varianten=[product], zellen=len(pt["cells"]),
                     land_km2=round(g2.Intersection(land).GetArea() / 1e6), bytes=sizes[pt["id"]])
        feats.append({"type": "Feature", "properties": props, "geometry": json.loads(g.ExportToJson())})
    with open(fn, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)


def write_map(out: str, file: str, name: str, fid: int, mids, gmps, area, fine_res) -> str:
    """IMG mit MPS und GMPs plus <file>_QUELLSTAND.txt. Bricht über 4 GiB ab."""
    total = IMG_OVERHEAD * (1 + len(gmps)) + sum(os.path.getsize(g) for g in gmps)
    if total > 0xFFFF * IMG_OVERHEAD:
        raise SystemExit(f"{file}: {total / 2**30:.2f} GiB > 4 GiB: Gebiet teilen (--region, --split-max)")
    mps = build_mps(fid, 1, name, [(m, f"{m:08d}") for m in mids], orig_style=True)
    fn = os.path.join(out, file + ".img")
    write_img(fn, [("GMAPPROM", "MPS", mps)] + [(f"{m:08d}", "GMP", g) for m, g in zip(mids, gmps)],
              f"{name} ©swisstopo")
    with open(os.path.join(out, file + "_QUELLSTAND.txt"), "w", encoding="utf-8") as f:
        f.write(quellstand_text(area, name, fid, fine_res))
    return fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="detail", choices=list(VARIANTS),
                    help="detail: 0,64 m, FID 7707, je Region; kompakt: 2,6 m, FID 7708, ganze Schweiz")
    ap.add_argument("--region", default="testgebiet", choices=list(RG.REGIONS) + list(R.TEST_AREAS))
    ap.add_argument("--fid", type=int)
    ap.add_argument("--version", default=_dt.date.today().strftime("%Y-%m"))
    ap.add_argument("--name")
    ap.add_argument("--file")
    ap.add_argument("--out")
    ap.add_argument("--quality", type=int)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"))
    ap.add_argument("--download", action="store_true", help="STAC-Kacheln für die Zellen laden, dann Ende")
    ap.add_argument("--gmapi", action="store_true")
    ap.add_argument("--gmapi-only", action="store_true", help="nur die gmapi, keine Gerätedatei")
    ap.add_argument("--gmapi-fid", type=int)
    ap.add_argument("--routes", metavar="PBF", help="gmapi mit transparenten Routen-Kacheln (routen.py)")
    ap.add_argument("--overview", action="store_true",
                    help="Übersichts-GMP für die groben Stufen 17..13 (Versuch; Gerätetest 4: IMG wird nicht angeboten)")
    ap.add_argument("--split-max", type=float, metavar="BYTES",
                    help="nur --region schweiz: Teile ohne Überlappung je höchstens BYTES (z. B. 4e9), siehe split_parts")
    ap.add_argument("--series", choices=["beide", "fein", "grob", "eine"],
                    help="Diagnose: nur feine bzw. grobe Serie, oder eine Serie mit Bildern auf allen Ebenen")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    v = VARIANTS[a.variant]
    a.fid, a.quality, a.series = a.fid or v.fid, a.quality or v.quality, a.series or v.series
    if a.series == "fein" and any(b <= R.COARSE_MAX_BITS for b, _, _ in v.levels):
        raise SystemExit(f"--series fein: Ebenen ≤ {R.COARSE_MAX_BITS} hätten keine Bilder")
    if a.split_max and a.region != "schweiz":
        raise SystemExit("--split-max gilt nur für --region schweiz")
    dn, df = default_names(a.region, a.version, v)
    a.name, a.file = a.name or dn, a.file or df
    out = os.path.normpath(a.out or os.path.join(RG.OUT_DEFAULT, "..", v.out))
    os.makedirs(os.path.join(out, "_vrt"), exist_ok=True)
    p = plan(v)
    cells, area = select_cells(p, a.region, a.bbox, out)
    if a.download:
        tiles = SI.latest_per_tile(SI.stac_items(area))
        SI.save_manifest(tiles)
        print(f"{len(tiles)} Kacheln für {len(cells)} Zellen, Gebiet {', '.join(f'{x:.4f}' for x in area)}")
        if not a.dry_run:
            from multiprocessing.pool import ThreadPool
            done, nbytes = 0, 0
            with ThreadPool(8) as pool:
                for _, nb in pool.imap_unordered(SI.fetch, [(m, v.fine_res) for m in tiles]):
                    done, nbytes = done + 1, nbytes + nb
                    if done % 50 == 0 or done == len(tiles):
                        print(f"  {done}/{len(tiles)} Kacheln, {nbytes / 1e9:.2f} GB neu", flush=True)
        return
    ids = R.id_table(p, out)
    cr = copyright_lines(area, a.name)
    cids = R.coarse_id_table(p, ids)
    coarse = sorted({p.coarse_of(c, r) for c, r in cells})
    fk = "voll" if a.series == "eine" else "fein"
    jobs = [(out, a.fid, a.name, cr, a.quality, p, fk, p.bounds(c, r), a.fid * 10000 + ids[(c, r)])
            for c, r in cells] if a.series != "grob" else []
    jobs += [(out, a.fid, a.name, cr, a.quality, p, "grob", R.Plan.coarse_bounds(*x), a.fid * 10000 + cids[x])
             for x in coarse] if a.series in ("beide", "grob") else []
    print(f"{a.file}: FID {a.fid}, „{a.name}“, Region {a.region}, q{a.quality}")
    print(f"  Levels {[p.top] + sorted(b for b, _, _ in p.levels)}, {len(jobs)} GMP (Zelle {p.cell:.4f}°), "
          f"Map-IDs {min(j[8] for j in jobs)}–{max(j[8] for j in jobs)}, ganze Schweiz {len(ids)} Zellen")
    print("  " + " | ".join(cr))
    if a.dry_run:
        return
    for src in sorted({s_ for _, s_, _ in p.levels}):
        vrt_for(src, os.path.join(out, "_vrt"))
    t0, nbytes = time.time(), 0
    with Pool(a.jobs) as pool:
        for i, (_, size) in enumerate(pool.imap_unordered(build_one, jobs), 1):
            nbytes += size
            if i % 25 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} GMP, {nbytes / 1e9:.2f} GB, {(time.time() - t0) / 60:.1f} min", flush=True)
    mids = sorted(j[8] for j in jobs)
    kinds = {j[8]: j[6] for j in jobs}
    gmps = [os.path.join(out, R.gmp_dir(a.fid, p, a.quality, kinds[m]) + f"_ov{OVERLAP_MU}", f"{m:08d}.gmp")
            for m in mids]
    if a.overview:            # grobe Stufen 17..13 (overview.py), Detailkacheln enden bei 18
        import overview as OV  # noqa: E402
        R.check_overview(p.top)
        ov = OV.write_overview(a.fid, area, vrt_for("2m", os.path.join(out, "_vrt")), gmp_options(p, cr, a.name),
                               a.quality, os.path.join(out, "_overview"), os.path.join(out, "_vrt"))
        mids, gmps = mids + [OV.map_id(a.fid)], gmps + [ov]
        print(f"  Übersicht {OV.map_id(a.fid)}: Ebenen {[OV.TOP] + sorted(b for b, _ in OV.LEVELS)}, "
              f"{os.path.getsize(ov) / 1e6:.1f} MB")
    if a.gmapi_only:
        a.gmapi = True
    elif a.split_max:
        mid_of = {cr: a.fid * 10000 + ids[cr] for cr in cells}
        gmp_of = dict(zip(mids, gmps))
        size = {cr: os.path.getsize(gmp_of[mid_of[cr]]) for cr in cells}
        parts = split_parts(p, cells, size, a.split_max, os.path.join(out, "_mask"))
        stem = a.file[:-len("_Schweiz_" + a.version)] if a.file.endswith("_Schweiz_" + a.version) else a.file
        sizes = {}
        for pt in parts:
            pm = sorted(mid_of[cr] for cr in pt["cells"])
            bb = [p.bounds(*cr) for cr in pt["cells"]]
            parea = (min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb))
            fn = write_map(out, f"{stem}_{pt['file']}_{a.version}", f"{a.name} {pt['label']}", a.fid, pm,
                           [gmp_of[m] for m in pm], parea, v.fine_res)
            sizes[pt["id"]] = os.path.getsize(fn)
            print(f"{fn}: {len(pm)} GMP, {sizes[pt['id']] / 1e9:.3f} GB")
        gj = os.path.join(out, "regionen.geojson")
        parts_geojson(p, parts, sizes, f"luftbild-{a.variant}", gj)
        print(f"{len(parts)} Teile, {sum(sizes.values()) / 1e9:.2f} GB, {gj}, {(time.time() - t0) / 60:.1f} min")
    else:
        fn = write_map(out, a.file, a.name, a.fid, mids, gmps, area, v.fine_res)
        print(f"{fn}: {os.path.getsize(fn) / 1e9:.3f} GB, {(time.time() - t0) / 60:.1f} min")
    if a.gmapi:
        from make_gmapi import make_gmapi_files  # noqa: E402
        gf = a.gmapi_fid or a.fid
        if a.routes:
            from routen import gmapi_with_routes  # noqa: E402
            d = gmapi_with_routes(gmps, os.path.join(out, "gmapi"), a.name, gf, list(cr) + [Q.LICENSE_LINE],
                                  a.routes, R.REGION_NAME.get(a.region, a.region))
        else:
            d = make_gmapi_files(gmps, os.path.join(out, "gmapi"), a.name, gf, gf * 10000 + 9000,
                                 copyright_lines=list(cr) + [Q.LICENSE_LINE], draw_priority=R.RASTER_PRIORITY)
        print(f"gmapi: {d}")


if __name__ == "__main__":
    main()
