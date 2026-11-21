"""Baut Raster-IMG-Testvarianten aus Swiss Map Raster (FID 7704).

Detailstufe ist immer Swiss Map Raster 25 (1:25'000). Gröbere Zoomstufen dürfen aus SMR 50/100 kommen,
wie beim Vorbild (dort eine feine und eine grobe Kachelserie). SMR 10 wird nicht verwendet.

Aufruf: python3 -I build_smr.py <ausgabeordner> [variante ...]
Ohne Variantennamen werden alle Varianten gebaut. Siehe VARIANTS.
"""
from __future__ import annotations

import dataclasses
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rasterimg import GmpOptions, build_gmp, build_img, build_mps  # noqa: E402
from smr_tiles import cut_tiles, warp_area  # noqa: E402

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

DL = str(paths.SMR_DIR)
SRC = {"smr25": f"{DL}/pk25/*.tif", "smr50": f"{DL}/pk50/*.tif", "smr100": f"{DL}/pk100/*.tif",
       "smr200": f"{DL}/pk200/*.tif", "smr500": f"{DL}/pk500/*.tif", "smr1000": f"{DL}/pk1000/*.tif"}
COPYRIGHT = {"smr25": "Swiss Map Raster 25, swisstopo OGD", "smr50": "Swiss Map Raster 50, swisstopo OGD",
             "smr100": "Swiss Map Raster 100, swisstopo OGD", "smr200": "Swiss Map Raster 200, swisstopo OGD",
             "smr500": "Swiss Map Raster 500, swisstopo OGD", "smr1000": "Swiss Map Raster 1000, swisstopo OGD"}
FID = 7704
PRODUCT = 1
TILE_DEG = 0.01176          # Kachelkante im Original (feine Serie), ~2.3e-5 Grad/px
DPP_NATIVE25 = TILE_DEG / 1024   # ~1.15e-5 Grad/px ≈ 1.25 m N-S: volle SMR25-Auflösung
DPP_HALF25 = TILE_DEG / 512      # wie Original-Feinserie (~2.5 m), entspricht SMR50-Auflösung
BASE_W, BASE_N = 9.30, 47.4776   # St. Gallen und Umgebung


@dataclasses.dataclass
class Series:
    source: str                      # smr25 / smr50 / smr100
    dpp: float                       # Grad je Pixel
    grid: list[tuple[int, int]]      # GMP-Positionen (Spalte, Zeile) in GMP-Einheiten
    tiles: tuple[int, int] = (10, 10)
    opts: dict = dataclasses.field(default_factory=dict)
    base_w: float = BASE_W
    base_n: float = BASE_N


AREA = (9.00, 47.20, 9.50, 47.50)   # Testgebiet laut AGENTS.md (W, S, E, N)


def area_series(source: str, dpp: float, opts: dict, area=AREA, tiles=(10, 10)) -> Series:
    """Series, deren GMP-Gitter das Gebiet vollständig abdeckt (Ursprung NW-Ecke)."""
    w, s, e, n = area
    gw, gh = tiles[0] * 512 * dpp, tiles[1] * 512 * dpp
    nx, ny = math.ceil((e - w) / gw - 1e-9), math.ceil((n - s) / gh - 1e-9)
    return Series(source, dpp, [(x, y) for y in range(ny) for x in range(nx)], tiles, opts, w, n)


# Detailstufe SMR25 nur auf bits 21..24, grobe Serie SMR50 nur auf bits 19..20
FINE = {"raster_levels": 4, "raster_min_level": 0}
COARSE_ONLY_HIGH = {"raster_levels": 6, "raster_min_level": 4, "split_bottom": False}
COARSE_ALL = {"raster_levels": 6, "raster_min_level": 0}

VARIANTS: dict[str, tuple[str, list[Series]]] = {
    "S1": ("Strukturtest: 1 GMP 10x10, SMR25 auf halbe Auflösung (wie Original-Feinserie)",
           [Series("smr25", DPP_HALF25, [(0, 0)])]),
    "S2": ("wie S1, ohne Abdeckungspolygon 0x10d01",
           [Series("smr25", DPP_HALF25, [(0, 0)], opts={"coverage_polygon": False})]),
    "S3": ("wie S1, RGN-Flagblöcke genullt (mkgmap-artig)",
           [Series("smr25", DPP_HALF25, [(0, 0)], opts={"rgn_flag_blocks": "zero"})]),
    "S4": ("2x2 GMP je 10x10, SMR25 halbe Auflösung",
           [Series("smr25", DPP_HALF25, [(0, 0), (1, 0), (0, 1), (1, 1)])]),
    "S5": ("1 GMP 10x10, SMR25 volle Auflösung (1,25 m)",
           [Series("smr25", DPP_NATIVE25, [(0, 0)])]),
    "M1": ("Zielaufbau: SMR25 voll (2x2 GMP, bits 21-24) + SMR50 (1 GMP, nur bits 19-20)",
           [Series("smr25", DPP_NATIVE25, [(0, 0), (1, 0), (0, 1), (1, 1)], opts=FINE),
            Series("smr50", DPP_HALF25, [(0, 0)], opts=COARSE_ONLY_HIGH)]),
    "M2": ("wie M1, aber SMR50 auf allen Ebenen bits 19-24 (wie Original-Grobserie, Überlagerung)",
           [Series("smr25", DPP_NATIVE25, [(0, 0), (1, 0), (0, 1), (1, 1)], opts=FINE),
            Series("smr50", DPP_HALF25, [(0, 0)], opts=COARSE_ALL)]),
    "G1": ("Ganzes Testgebiet 9.00-9.50 O / 47.20-47.50 N, Aufbau M1 (SMR25 voll + SMR50 grob)",
           [area_series("smr25", DPP_NATIVE25, FINE), area_series("smr50", DPP_HALF25, COARSE_ONLY_HIGH)]),
    "H1": ("wie S1, aber Labels und Koordinaten Huffman-kodiert wie das Original (RGN5, LBL-Codierung 11)",
           [Series("smr25", DPP_HALF25, [(0, 0)], opts={"huffman": True})]),
    "N1": ("Negativkontrolle: wie S1, Bildindex 2 Byte wie GarminImg",
           [Series("smr25", DPP_HALF25, [(0, 0)], opts={"index_bytes": 2})]),
}


# Varianten werden nur angehängt, damit die Map-IDs bestehender Testdateien gleich bleiben.
VARIANTS["X1"] = ("so nah wie möglich am Original: wie H1 + TRE9/LBL16 + MPS-L-Record mit Kartennummer 0",
                  [Series("smr25", DPP_HALF25, [(0, 0)], opts={"huffman": True, "orig_extras": True})])
MPS_ORIG_STYLE = {"X1"}
AREA_SG = (9.25, 47.336, 9.485, 47.51)   # St. Gallen mit Umgebung (Teufen, Gossau-Ost, Rorschach-West)
VARIANTS["G0"] = ("Ausschnitt St. Gallen ~0.24 x 0.18 Grad, Aufbau M1/G1 (SMR25 voll + SMR50 grob), für VHD <= 150 MB",
                  [area_series("smr25", DPP_NATIVE25, FINE, AREA_SG),
                   area_series("smr50", DPP_HALF25, COARSE_ONLY_HIGH, AREA_SG)])

VARIANTS["R1"] = ("Korrekturkandidat nach Strukturvergleich mit dem Original: wie X1 (Huffman, TRE9, LBL16, "
                  "MPS-Kartennummer 0) + eigenes Label je Bild + Abdeckungspolygon unten nur einmal",
                  [Series("smr25", DPP_HALF25, [(0, 0)],
                          opts={"huffman": True, "orig_extras": True, "unique_tile_labels": True,
                                "coverage_bottom_last": True})])
MPS_ORIG_STYLE.add("R1")
VARIANTS["R2"] = ("wie R1, aber unterste Ebene wie Original: rechte Subdivision spannt die ganze GMP "
                  "(Mitte und Breite der Kachel)",
                  [Series("smr25", DPP_HALF25, [(0, 0)],
                          opts={"huffman": True, "orig_extras": True, "unique_tile_labels": True,
                                "coverage_bottom_last": True, "bottom_last_full": True})])
MPS_ORIG_STYLE.add("R2")

# R3: eine Kartenserie je Zoomstufe, Bildauflösung verdoppelt sich je Stufe (Massstab etwa 1:1 bis 1:2)
AREA_WG = (9.03, 47.40, 9.26, 47.48)   # Wil – Gossau
R_STYLE = {"huffman": True, "orig_extras": True, "unique_tile_labels": True, "coverage_bottom_last": True,
           "bottom_last_full": True}


def single_level_series(source: str, factor: int, level_from_bottom: int, area=AREA_WG) -> Series:
    dpp = TILE_DEG / 1024 * factor
    w, s, e, n = area
    side = 512 * dpp
    nx, ny = math.ceil((e - w) / side - 1e-9), math.ceil((n - s) / side - 1e-9)
    opts = dict(R_STYLE, raster_min_level=level_from_bottom, raster_levels=level_from_bottom + 1,
                split_bottom=level_from_bottom == 0)
    if nx <= 10 and ny <= 10:     # eine GMP genügt
        return Series(source, dpp, [(0, 0)], (nx, ny), opts, w, n)
    return area_series(source, dpp, opts, area)


VARIANTS["R3"] = ("Wil–Gossau, eine Serie je Zoomstufe: bits 24 SMR25 (1,25 m), 23 SMR50 (2,5 m), 22 SMR100 (5 m), "
                  "21 SMR200 (10 m), 20 SMR500 (20 m), 19 SMR1000 (40 m); Aufbau wie R2",
                  [single_level_series("smr25", 1, 0), single_level_series("smr50", 2, 1),
                   single_level_series("smr100", 4, 2), single_level_series("smr200", 8, 3),
                   single_level_series("smr500", 16, 4), single_level_series("smr1000", 32, 5)])
MPS_ORIG_STYLE.add("R3")

# Halbierung R3 (Gerät listet R3 nicht, R1 lief)
VARIANTS["R3a"] = ("1 GMP mit allen Massstäben: je Ebene eigene Bilder (bits 24 SMR25 10x10, 23 SMR50, 22 SMR100, "
                   "21 SMR200, 20 SMR500, 19 SMR1000), Aufbau wie R2", [])   # Sonderbau, siehe build_multiscale
VARIANTS["R3b"] = ("2 GMP SMR25 nebeneinander (Wil), Aufbau wie R2 (Raster bits 21-24 wie R1)",
                   [Series("smr25", DPP_HALF25, [(0, 0), (1, 0)], opts=dict(R_STYLE), base_w=9.03, base_n=47.48)])
VARIANTS["R3d"] = ("1 GMP SMR25 voll wie eine R3-Feinkachel: Raster nur auf bits 24",
                   [Series("smr25", DPP_NATIVE25, [(0, 0)], opts=dict(R_STYLE, raster_min_level=0, raster_levels=1),
                           base_w=9.03, base_n=47.48)])
MPS_ORIG_STYLE.update({"R3a", "R3b", "R3d"})
MULTISCALE = {"R3a": [("smr25", 1, 24), ("smr50", 2, 23), ("smr100", 4, 22), ("smr200", 8, 21),
                      ("smr500", 16, 20), ("smr1000", 32, 19)]}
# R4: wie R3a, SMR1000 zusätzlich als Übersicht der ganzen Schweiz auf bits 18 und 16 (8 Levels, oberste 14 leer)
AREA_CH = (5.90, 45.75, 10.55, 47.85)
VARIANTS["R4"] = ("wie R3a (24 SMR25 … 20 SMR500), dazu SMR1000 ganze Schweiz auf bits 18 (80 m) und 16 (160 m); "
                  "Levels 14 (leer), 16, 18, 20, 21, 22, 23, 24", [])
MPS_ORIG_STYLE.add("R4")
MULTISCALE["R4"] = [("smr25", 1, 24), ("smr50", 2, 23), ("smr100", 4, 22), ("smr200", 8, 21), ("smr500", 16, 20),
                    ("smr1000", 64, 18, AREA_CH), ("smr1000", 128, 16, AREA_CH)]
MULTISCALE_LEVELS = {"R4": (14, 16, 18, 20, 21, 22, 23, 24)}


def build_multiscale(outdir: str, name: str, number: int) -> bytes:
    """Eine GMP, je Ebene eigene Bilder; alle Serien decken die SMR25-Kachelfläche (NW-Ecke AREA_WG) ab."""
    w0, n0 = AREA_WG[0], AREA_WG[3]
    fine_side = 10 * 512 * TILE_DEG / 1024
    level_tiles, all_tiles = {}, []
    overview = []
    for source, factor, bits, *area in MULTISCALE[name]:
        dpp = TILE_DEG / 1024 * factor
        if area:   # Übersicht über ein grosses Gebiet
            aw, as_, ae, an = area[0]
            kx, ky = math.ceil((ae - aw) / (512 * dpp)), math.ceil((an - as_) / (512 * dpp))
            ow, on = aw, an
            overview.append(bits)
        else:
            kx = ky = max(1, math.ceil(fine_side / (512 * dpp) - 1e-9))
            ow, on = w0, n0
        east, south = ow + kx * 512 * dpp, on - ky * 512 * dpp
        tif = warp_area(SRC[source], os.path.join(outdir, "_warp", source), ow, south, east, on, dpp,
                        f"{source}_{dpp:.4e}_{ow:.5f}_{on:.5f}_{kx}x{ky}")
        tiles = cut_tiles(tif, ow, on, dpp, kx, ky)
        level_tiles[bits] = tiles
        all_tiles += tiles
    extra = {"levels": MULTISCALE_LEVELS[name], "overview_bits": tuple(overview)} if name in MULTISCALE_LEVELS else {}
    opt = dataclasses.replace(GmpOptions(), **R_STYLE, **extra,
                              copyright=("©swisstopo", "Swiss Map Raster 25-1000, swisstopo OGD",
                                         "Helvetopo, inoffiziell"))
    return build_gmp(number, all_tiles, opt, level_tiles=level_tiles)


def build_variant(outdir: str, name: str) -> str:
    desc, series = VARIANTS[name]
    gmps = []
    vno = list(VARIANTS).index(name) + 1
    if name in MULTISCALE:
        number = FID * 10000 + vno * 100 + 1
        gmps.append((f"{number:08d}", build_multiscale(outdir, name, number)))
    for s in series:
        opt = dataclasses.replace(GmpOptions(), **s.opts)
        opt = dataclasses.replace(opt, copyright=("©swisstopo", COPYRIGHT[s.source],
                                                  "Helvetopo, inoffiziell"))
        cols, rows = s.tiles
        step = 512 * s.dpp
        for gx, gy in s.grid:
            west = s.base_w + gx * cols * step
            north = s.base_n - gy * rows * step
            east, south = west + cols * step, north - rows * step
            tif = warp_area(SRC[s.source], os.path.join(outdir, "_warp", s.source), west, south, east, north,
                            s.dpp, f"{s.source}_{s.dpp:.4e}_{west:.5f}_{north:.5f}")
            tiles = cut_tiles(tif, west, north, s.dpp, cols, rows)
            number = FID * 10000 + vno * 100 + len(gmps) + 1
            gmps.append((f"{number:08d}", build_gmp(number, tiles, opt)))
    mps = build_mps(FID, PRODUCT, f"GST Raster {name}", [(int(n), n) for n, _ in gmps],
                    orig_style=name in MPS_ORIG_STYLE)
    img = build_img([("GMAPPROM", "MPS", mps)] + [(n, "GMP", d) for n, d in gmps],
                    f"GST Raster {name} (c)swisstopo")
    fn = os.path.join(outdir, f"{name}_gst_raster.img")
    open(fn, "wb").write(img)
    print(f"{name}: {fn} ({len(img)/1e6:.1f} MB, {len(gmps)} GMP) – {desc}")
    return fn


def main():
    outdir = sys.argv[1]
    names = sys.argv[2:] or list(VARIANTS)
    os.makedirs(outdir, exist_ok=True)
    for n in names:
        build_variant(outdir, n)


if __name__ == "__main__":
    main()
