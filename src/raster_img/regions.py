"""Regionale Raster-IMG-Pakete aus Swiss Map Raster (FID 7704), fortsetzbar.

Aufbau wie beim Vorbild, aber mit drei Serien:

| Serie  | Quelle | Auflösung            | GMP-Kante | Raster auf | Map-IDs           |
|--------|--------|----------------------|-----------|------------|-------------------|
| smr25  | SMR25  | 1,15e-5 °/px (1,25 m) | 0,0588°   | bits 21–24 | 77042000–77044879 |
| smr50  | SMR50  | 2,30e-5 °/px (2,5 m)  | 0,1176°   | bits 19–20 | 77045000–77045719 |
| smr100 | SMR100 | 4,59e-5 °/px (5 m)    | 0,2352°   | bits 17–18 | 77046000–77046179 |
| smr25h | SMR25  | 2,30e-5 °/px (halb)   | 0,1176°   | bits 21–24 | 77047000–77047719 |

Alle Serien liegen auf einem landesweiten Gitter (Ursprung 5,90° O / 47,86° N). Jede GMP hat 10 × 10
JPEG-Kacheln zu 512 px. Die Map-ID ergibt sich aus Serie, Zeile und Spalte. Dieselbe Kachel hat daher
in jeder Region dieselbe ID und denselben Inhalt; IDs verschiedener Kacheln kollidieren nie.
`smr25h` ist die Alternative mit halber SMR25-Auflösung (wie die Feinserie des Originals).

Eine Region wählt alle GMP, die das um 1 km gepufferte Gebiet ihrer Kantone (swissBOUNDARIES3D) berühren.
Jede GMP wird einzeln gebaut und unter `<out>/_gmp/<Map-ID>.gmp` zwischengespeichert. Ein Abbruch
verliert daher höchstens die GMP, die gerade in Arbeit sind. Erst am Schluss entsteht die IMG.

Aufruf:
  python3 -I regions.py list                                   # Regionen und GMP-Zahlen
  python3 -I regions.py build <region> [--jobs N] [--fine smr25|smr25h] [--quality Q] [--out DIR]
  python3 -I regions.py assemble <region> [...]                # nur IMG aus dem Zwischenspeicher
  python3 -I regions.py gmapi <region> [--gmapi-fid F] [...]   # gmapi-Ordner für BaseCamp (Test-FID)
Standard-Ausgabe: work/raster_img/regionen/ (Zwischenspeicher _gmp/, Masken _mask/, Log <region>.log).
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import glob
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rasterimg import GmpOptions, build_gmp, build_mps, write_img  # noqa: E402
from smr_tiles import cut_tiles  # noqa: E402

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

DL = str(paths.SMR_DIR)
BOUNDARIES = str(paths.BOUNDARIES_GPKG)
FID, PRODUCT = 7704, 1
TILE_PX, GMP_TILES = 512, 10
GRID_W, GRID_N = 5.90, 47.86
DPP25 = 0.01176 / 1024            # volle SMR25-Auflösung
FINE_CELL = TILE_PX * DPP25       # Kante einer JPEG-Kachel der Feinserie (Maskenraster)
BUFFER_M = 1000
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../work/raster_img/regionen"))

LEVELS_DEFAULT = (18, 19, 20, 21, 22, 23, 24)
LEVELS_SMR100 = (16, 17, 18, 19, 20, 21, 22, 23, 24)


@dataclasses.dataclass(frozen=True)
class SeriesDef:
    key: str
    source: str            # Ordner unter downloads/smr
    factor: int            # Pixelgrösse in Vielfachen von DPP25
    id_base: int           # Map-ID = FID*10000 + id_base + Zeile*Spalten + Spalte
    copyright: str
    opts: dict

    @property
    def dpp(self) -> float:
        return DPP25 * self.factor

    @property
    def gmp_side(self) -> float:
        return GMP_TILES * TILE_PX * self.dpp

    @property
    def cols(self) -> int:
        return math.ceil(80 / self.factor)   # 80 Feinserien-GMP = 4,70° → bis 10,60° O

    @property
    def rows(self) -> int:
        return math.ceil(36 / self.factor)   # 36 × 0,0588° = 2,12° → bis 45,74° N

    def map_id(self, col: int, row: int) -> int:
        return FID * 10000 + self.id_base + row * self.cols + col

    def bounds(self, col: int, row: int) -> tuple[float, float, float, float]:
        """(West, Süd, Ost, Nord) der GMP."""
        w = GRID_W + col * self.gmp_side
        n = GRID_N - row * self.gmp_side
        return w, n - self.gmp_side, w + self.gmp_side, n


SERIES = {
    "smr25": SeriesDef("smr25", "pk25", 1, 2000, "Swiss Map Raster 25, swisstopo OGD",
                       {"raster_levels": 4, "raster_min_level": 0}),
    "smr50": SeriesDef("smr50", "pk50", 2, 5000, "Swiss Map Raster 50, swisstopo OGD",
                       {"raster_levels": 6, "raster_min_level": 4, "split_bottom": False}),
    "smr100": SeriesDef("smr100", "pk100", 4, 6000, "Swiss Map Raster 100, swisstopo OGD",
                        {"levels": LEVELS_SMR100, "raster_levels": 8, "raster_min_level": 6,
                         "coverage_levels": 8, "split_bottom": False}),
    "smr25h": SeriesDef("smr25h", "pk25", 2, 7000, "Swiss Map Raster 25, swisstopo OGD",
                        {"raster_levels": 4, "raster_min_level": 0}),
}

# Regionen: Kantonsnummern (swissBOUNDARIES3D) und zusätzliche Landesgebiete (icc)
REGIONS: dict[str, tuple[str, list[int], list[str]]] = {
    "ostschweiz": ("Ostschweiz (SG, AR, AI, TG, FL)", [17, 15, 16, 20], ["LI"]),
    "graubuenden": ("Graubünden", [18], []),
    "stgallen": ("St. Gallen (Probe-Kanton)", [17], []),
    "zentralschweiz": ("Zentralschweiz (LU, UR, SZ, OW, NW, ZG, GL)", [3, 4, 5, 6, 7, 9, 8], []),
    "zuerich": ("Zürich, Schaffhausen, Aargau", [1, 14, 19], []),
    "nordwestschweiz": ("Nordwestschweiz (BS, BL, SO, JU)", [12, 13, 11, 26], []),
    "bern": ("Bern, Freiburg, Neuenburg", [2, 10, 24], []),
    "genfersee": ("Waadt und Genf", [22, 25], []),
    "wallis": ("Wallis", [23], []),
    "tessin": ("Tessin", [21], []),
    "schweiz": ("ganze Schweiz mit FL", list(range(1, 27)), ["LI"]),
}


# --------------------------------------------------------------------------- Auswahl
def region_mask(region: str, workdir: str):
    """Maske auf dem Raster der Feinserie (eine Zelle = eine JPEG-Kachel smr25). Liefert Liste von Zeilen."""
    from osgeo import gdal  # noqa: E402
    gdal.UseExceptions()
    _, cantons, iccs = REGIONS[region]
    os.makedirs(workdir, exist_ok=True)
    tif = os.path.join(workdir, f"mask_{region}.tif")
    if not os.path.exists(tif):
        where = [f"(src='k' AND nr IN ({','.join(map(str, cantons))}))"]
        if iccs:
            where.append(f"(src='l' AND icc IN ({','.join(repr(i) for i in iccs)}))")
        sql = ("SELECT ST_Buffer(ST_Union(geom), %d) AS geom FROM ("
               "SELECT 'k' AS src, kantonsnummer AS nr, NULL AS icc, geom FROM tlm_kantonsgebiet "
               "UNION ALL SELECT 'l', NULL, icc, geom FROM tlm_landesgebiet) WHERE %s"
               % (BUFFER_M, " OR ".join(where)))
        gpkg = os.path.join(workdir, f"mask_{region}.gpkg")
        subprocess.run(["ogr2ogr", "-q", "-overwrite", "-f", "GPKG", "-dialect", "SQLite", "-sql", sql,
                        "-s_srs", "EPSG:2056", "-t_srs", "EPSG:4326", "-dim", "XY", gpkg, BOUNDARIES], check=True)
        ncol, nrow = 80 * GMP_TILES, 36 * GMP_TILES
        subprocess.run(["gdal_rasterize", "-q", "-burn", "1", "-at", "-ot", "Byte", "-init", "0",
                        "-te", repr(GRID_W), repr(GRID_N - nrow * FINE_CELL), repr(GRID_W + ncol * FINE_CELL),
                        repr(GRID_N), "-ts", str(ncol), str(nrow), gpkg, tif], check=True)
    ds = gdal.Open(tif)
    arr = ds.GetRasterBand(1).ReadAsArray()
    return arr


def select_gmps(region: str, series: str, workdir: str) -> list[tuple[int, int]]:
    s = SERIES[series]
    m = region_mask(region, workdir)
    blk = GMP_TILES * s.factor
    out = []
    for r in range(s.rows):
        for c in range(s.cols):
            if m[r * blk:(r + 1) * blk, c * blk:(c + 1) * blk].any():
                out.append((c, r))
    return out


# --------------------------------------------------------------------------- Bau einer GMP
def vrt_for(source: str, workdir: str) -> str:
    os.makedirs(workdir, exist_ok=True)
    vrt = os.path.join(workdir, f"{source}.vrt")
    if not os.path.exists(vrt):
        srcs = sorted(glob.glob(f"{DL}/{source}/*.tif"))
        if not srcs:
            raise FileNotFoundError(f"{DL}/{source}")
        tmp = f"{vrt}.{os.getpid()}.tmp.vrt"   # eindeutig je Prozess (parallele Aufrufe)
        subprocess.run(["gdalbuildvrt", "-q", tmp, *srcs], check=True)
        os.replace(tmp, vrt)
    return vrt


def gmp_options(s: SeriesDef, quality: int) -> GmpOptions:
    opt = dataclasses.replace(GmpOptions(), **s.opts)
    return dataclasses.replace(opt, copyright=("©swisstopo", s.copyright, "Helvetopo, inoffiziell"),
                               hdr_comment2=(s.copyright.split(",")[0], "©swisstopo"))


def cache_path(out: str, map_id: int, quality: int) -> str:
    sub = "_gmp" if quality == 85 else f"_gmp_q{quality}"
    return os.path.join(out, sub, f"{map_id:08d}.gmp")


def build_one(job) -> tuple[int, int, float]:
    out, series, col, row, quality, threads = job
    s = SERIES[series]
    mid = s.map_id(col, row)
    dest = cache_path(out, mid, quality)
    if os.path.exists(dest):
        return mid, os.path.getsize(dest), 0.0
    t0 = time.time()
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    vrt = vrt_for(s.source, os.path.join(out, "_vrt"))
    w, so, e, n = s.bounds(col, row)
    px = GMP_TILES * TILE_PX
    tmpdir = tempfile.mkdtemp(dir=os.path.join(out, "_vrt"))
    try:
        tif = os.path.join(tmpdir, "w.tif")
        subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-te", repr(w), repr(so), repr(e),
                        repr(n), "-ts", str(px), str(px), "-r", "cubic", "-wo", "INIT_DEST=255",
                        "-wo", f"NUM_THREADS={threads}", "-multi", "-co", "TILED=YES", vrt, tif], check=True,
                       env={**os.environ, "GDAL_CACHEMAX": "512"})
        tiles = cut_tiles(tif, w, n, s.dpp, GMP_TILES, GMP_TILES, quality=quality)
        data = build_gmp(mid, tiles, gmp_options(s, quality))
        with open(dest + ".part", "wb") as f:
            f.write(data)
        os.replace(dest + ".part", dest)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    return mid, len(data), time.time() - t0


def region_jobs(out: str, region: str, fine: str, quality: int, threads: int):
    jobs = []
    for series in (fine, "smr50", "smr100"):
        for c, r in select_gmps(region, series, os.path.join(out, "_mask")):
            jobs.append((out, series, c, r, quality, threads))
    return jobs


def build_region(out: str, region: str, fine: str = "smr25", quality: int = 85, jobs: int = 6,
                 threads: int = 2, log=print) -> str:
    js = region_jobs(out, region, fine, quality, threads)
    todo = [j for j in js if not os.path.exists(cache_path(out, SERIES[j[1]].map_id(j[2], j[3]), quality))]
    log(f"{region}: {len(js)} GMP ({sum(1 for j in js if j[1] == fine)} {fine}, "
        f"{sum(1 for j in js if j[1] == 'smr50')} smr50, {sum(1 for j in js if j[1] == 'smr100')} smr100), "
        f"davon {len(todo)} zu bauen")
    # Wichtigste zuerst: grobe Serien, dann fein (kurze Rückmeldung, ob alles läuft)
    todo.sort(key=lambda j: (j[1] == fine, j[3], j[2]))
    t0, done, nbytes = time.time(), 0, 0
    with Pool(jobs) as pool:
        for mid, size, dt in pool.imap_unordered(build_one, todo):
            done += 1
            nbytes += size
            if done % 10 == 0 or done == len(todo):
                el = time.time() - t0
                eta = el / done * (len(todo) - done)
                log(f"  {done}/{len(todo)} GMP, {nbytes / 1e9:.2f} GB, {el / 60:.1f} min, Rest ~{eta / 60:.0f} min")
    return assemble(out, region, fine, quality, js, log)


def img_name(region: str, fine: str, quality: int) -> str:
    sfx = ("" if fine == "smr25" else "_halb") + ("" if quality == 85 else f"_q{quality}")
    return f"gst_raster_{region}{sfx}"


def assemble(out: str, region: str, fine: str, quality: int, js, log=print) -> str:
    title = REGIONS[region][0]
    mids = sorted(SERIES[j[1]].map_id(j[2], j[3]) for j in js)
    paths = [cache_path(out, m, quality) for m in mids]
    missing = [p for p in paths if not os.path.exists(p)]
    if missing:
        raise RuntimeError(f"{len(missing)} GMP fehlen, z. B. {missing[0]}")
    series = f"GST Raster {title}"[:60]
    mps = build_mps(FID, PRODUCT, series, [(m, f"{m:08d}") for m in mids])
    total = 64 * 1024 * (1 + len(paths)) + sum(os.path.getsize(p) for p in paths)
    if total > 0xFFFF * 64 * 1024:
        raise RuntimeError(f"{total / 2**30:.2f} GiB > 4 GiB, Region teilen oder --fine smr25h")
    fn = os.path.join(out, img_name(region, fine, quality) + ".img")
    size = write_img(fn, [("GMAPPROM", "MPS", mps)] + [(f"{m:08d}", "GMP", p) for m, p in zip(mids, paths)],
                     f"GST Raster {region} (c)swisstopo")
    log(f"{fn}: {size / 1e9:.2f} GB, {len(mids)} GMP")
    return fn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "build", "assemble", "gmapi"])
    ap.add_argument("region", nargs="?")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--fine", default="smr25", choices=["smr25", "smr25h"])
    ap.add_argument("--quality", type=int, default=85)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--gmapi-fid", type=int, default=7748)
    a = ap.parse_args()

    def log(msg):
        line = f"{_dt.datetime.now():%H:%M:%S} {msg}"
        print(line, flush=True)
        if a.region:
            with open(os.path.join(a.out, f"{a.region}.log"), "a") as f:
                f.write(line + "\n")

    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "list":
        for r in REGIONS:
            n = {s: len(select_gmps(r, s, os.path.join(a.out, "_mask"))) for s in SERIES}
            print(f"{r:16s} {n}")
    elif a.cmd == "build":
        build_region(a.out, a.region, a.fine, a.quality, a.jobs, a.threads, log)
    elif a.cmd == "assemble":
        assemble(a.out, a.region, a.fine, a.quality, region_jobs(a.out, a.region, a.fine, a.quality, 1), log)
    elif a.cmd == "gmapi":
        from make_gmapi import make_gmapi_files  # noqa: E402
        js = region_jobs(a.out, a.region, a.fine, a.quality, 1)
        paths = sorted(cache_path(a.out, SERIES[j[1]].map_id(j[2], j[3]), a.quality) for j in js)
        dest = make_gmapi_files(paths, os.path.join(a.out, "gmapi"), f"GST Raster {a.region}", a.gmapi_fid,
                                a.gmapi_fid * 10000 + 9000)
        log(f"gmapi: {dest}")


if __name__ == "__main__":
    main()
