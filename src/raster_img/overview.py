"""Übersichts-GMP für Raster-IMGs (Pixel und Luftbild): grobe Zoomstufen unterhalb der Detailkacheln.

Gerätetest 3 (GPSMAP 67): Das Gerät zeigt eine Ebene nur im Bereich ihrer eigenen bits. Eine Detail-GMP hat
höchstens 8 Levels, lückenlos 24..18 plus die leere oberste Ebene 17. Gröber als bits 18 zeigt sie nichts.
Deshalb trägt eine zusätzliche GMP je IMG die groben Stufen für die ganze Fläche der IMG:

| bits    | 17     | 16     | 15     | 14      | 13      | oben |
|---------|--------|--------|--------|---------|---------|------|
| Faktor  | 128    | 256    | 512    | 1024    | 2048    | 12   |
| m/px    | ca. 160| 320    | 640    | 1300    | 2600    |      |

Faktor relativ zu DPP25 (1,15e-5 °/px). Zusammen mit den Detailkacheln sind die Ebenen 24..13 lückenlos.

- Ebenennummer = 24 − bits (GmpOptions.zoom_from_bits), wie bei den Detailkacheln (24 → 0 … 17 → 7).
- Map-ID <FID>8901 (Zellen nutzen <FID>0001…, die gmapi-Übersicht von mkgmap <FID>9000).
- Draw-Priority 28, eine Stufe unter den Detailkacheln (29): Falls ein Gerät die Übersicht auch bei feinem
  Zoom zeichnet, liegen die Detailkacheln oben.
- Die Bilder decken genau die Fläche der IMG (Vereinigung der Zellen). Ausserhalb der Quelle bleibt das Bild
  weiss, wie in den Detailkacheln.
"""
from __future__ import annotations

import dataclasses
import io
import math
import os
import subprocess
import tempfile

from PIL import Image

import regions as RG
from rasterimg import GmpOptions, Tile, build_gmp

TOP = 12
LEVELS = ((17, 128), (16, 256), (15, 512), (14, 1024), (13, 2048))   # (bits, Faktor zu DPP25), feinste zuerst
ID_SUFFIX = 8901
PRIORITY = 28
TILE_PX = 512


def map_id(fid: int) -> int:
    return fid * 10000 + ID_SUFFIX


def levels_table() -> list[tuple[int, int]]:
    return list(LEVELS)


def _cut(tif: str, w: float, n: float, dpp: float, width: int, height: int, quality: int, ov: int) -> list[Tile]:
    """Schneidet ein Bild von width × height px (plus ov px Überlappung nach Osten/Süden) in Kacheln ≤ 512 px.
    Die Kacheln sind rechteckig und decken genau die Fläche."""
    img = Image.open(tif).convert("RGB")
    cols, rows = math.ceil(width / TILE_PX), math.ceil(height / TILE_PX)
    xs = [round(i * width / cols) for i in range(cols + 1)]
    ys = [round(i * height / rows) for i in range(rows + 1)]
    tiles = []
    mid = cols // 2 if cols > 1 else cols
    order = [(c, r) for half in (range(0, mid), range(mid, cols)) for r in range(rows - 1, -1, -1) for c in half]
    for c, r in order:
        box = (xs[c], ys[r], xs[c + 1] + ov, ys[r + 1] + ov)
        buf = io.BytesIO()
        img.crop(box).save(buf, "JPEG", quality=quality, optimize=False, progressive=False, subsampling=2)
        tiles.append(Tile(buf.getvalue(), north=n - ys[r] * dpp, south=n - (ys[r + 1] + ov) * dpp,
                          west=w + xs[c] * dpp, east=w + (xs[c + 1] + ov) * dpp, col=c, row=r))
    return tiles


def build_overview(fid: int, area, vrt: str, base: GmpOptions, quality: int, workdir: str,
                   resampling: str = "average", overlap: int = 1) -> bytes:
    """area = (W, S, E, N) in Grad; vrt = Quelle (z. B. SMR1000 oder SWISSIMAGE 2 m)."""
    w, s, e, n = area
    level_tiles, all_tiles = {}, []
    tmp = tempfile.mkdtemp(dir=workdir)
    try:
        for bits, factor in LEVELS:
            dpp = RG.DPP25 * factor
            width, height = max(1, math.ceil((e - w) / dpp)), max(1, math.ceil((n - s) / dpp))
            tif = os.path.join(tmp, f"ov{bits}.tif")
            subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326",
                            "-te", repr(w), repr(n - (height + overlap) * dpp), repr(w + (width + overlap) * dpp),
                            repr(n), "-ts", str(width + overlap), str(height + overlap), "-r", resampling,
                            "-wo", "INIT_DEST=255", "-multi", "-co", "TILED=YES", vrt, tif], check=True)
            level_tiles[bits] = _cut(tif, w, n, dpp, width, height, quality, overlap)
            all_tiles += level_tiles[bits]
    finally:
        subprocess.run(["rm", "-rf", tmp], check=False)
    if len(all_tiles) > 255:
        raise ValueError(f"Übersicht: {len(all_tiles)} Bilder > 255 je GMP")
    opt = dataclasses.replace(base, levels=(TOP,) + tuple(sorted(b for b, _ in LEVELS)), zoom_from_bits=True,
                              draw_priority=PRIORITY)
    return build_gmp(map_id(fid), all_tiles, opt, level_tiles=level_tiles)


def write_overview(fid: int, area, vrt: str, base: GmpOptions, quality: int, out: str, workdir: str,
                   resampling: str = "average") -> str:
    """Baut die Übersichts-GMP und legt sie als <out>/<Map-ID>.gmp ab. Liefert den Pfad."""
    data = build_overview(fid, area, vrt, base, quality, workdir, resampling)
    os.makedirs(out, exist_ok=True)
    dest = os.path.join(out, f"{map_id(fid):08d}.gmp")
    with open(dest + ".part", "wb") as f:
        f.write(data)
    os.replace(dest + ".part", dest)
    return dest
