"""Swiss Map Raster (LV95-GeoTIFF) -> JPEG-Kacheln 512 x 512 in WGS84 (gleiche Grad pro Pixel in x und y).

Arbeitet mit GDAL-Kommandozeilenwerkzeugen (gdalbuildvrt, gdalwarp) und Pillow.
"""
from __future__ import annotations

import glob
import io
import os
import subprocess

from PIL import Image

from rasterimg import Tile

Image.MAX_IMAGE_PIXELS = None


def warp_area(src_glob: str, workdir: str, west: float, south: float, east: float, north: float,
              deg_per_px: float, name: str, resampling: str = "cubic") -> str:
    os.makedirs(workdir, exist_ok=True)
    srcs = sorted(glob.glob(src_glob))
    if not srcs:
        raise FileNotFoundError(src_glob)
    vrt = os.path.join(workdir, "smr_mosaic.vrt")
    if not os.path.exists(vrt):
        subprocess.run(["gdalbuildvrt", "-q", vrt, *srcs], check=True)
    out = os.path.join(workdir, f"{name}.tif")
    if not os.path.exists(out):
        subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-te", repr(west), repr(south),
                        repr(east), repr(north), "-tr", repr(deg_per_px), repr(deg_per_px), "-r", resampling,
                        "-co", "TILED=YES", "-co", "COMPRESS=DEFLATE", "-wo", "INIT_DEST=255", "-wo",
                        "NUM_THREADS=ALL_CPUS", "-multi", vrt, out], check=True)
    return out


def cut_tiles(geotiff: str, west: float, north: float, deg_per_px: float, cols: int, rows: int,
              tile_px: int = 512, quality: int = 85, overlap: int = 0, optimize: bool = False) -> list[Tile]:
    """Schneidet cols x rows Kacheln (Zeile 0 = Norden). Liefert Tiles mit exakten Grenzen.

    overlap > 0: jedes Bild reicht `overlap` Pixel weiter nach Osten und Süden (Bild und Grenzen), sodass
    Nachbarbilder sich überlappen und beim Skalieren keine hellen Säume an den Kachelkanten entstehen.
    Das Geotiff muss dann (cols * tile_px + overlap) Pixel breit und hoch sein."""
    img = Image.open(geotiff).convert("RGB")
    tiles = []
    step = tile_px * deg_per_px
    # Reihenfolge wie im Original: erst linke Hälfte, darin zeilenweise von Süd nach Nord, West nach Ost
    mid = cols // 2 if cols > 1 else cols
    order = [(c, r) for half in (range(0, mid), range(mid, cols)) for r in range(rows - 1, -1, -1)
             for c in half]
    for c, r in order:
        if True:
            box = (c * tile_px, r * tile_px, (c + 1) * tile_px + overlap, (r + 1) * tile_px + overlap)
            sub = img.crop(box)
            buf = io.BytesIO()
            sub.save(buf, "JPEG", quality=quality, optimize=optimize, progressive=False, subsampling=2)
            ov = overlap * deg_per_px
            tiles.append(Tile(buf.getvalue(), north=north - r * step, south=north - (r + 1) * step - ov,
                              west=west + c * step, east=west + (c + 1) * step + ov, col=c, row=r))
    return tiles
