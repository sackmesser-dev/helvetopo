"""Release-Build der Pixelkarte als Raster-IMG (Swiss Map Raster), parametrisiert nach Release-Plan.

Parameter:
- Variante (Massstabsbereich 50-1000, 25-1000, 10-1000), Family-ID;
- Kartenname und Dateiname: ohne Angabe nach Release-Plan aus Variante, Gebiet und Version
  („Helvetopo Pixel 25-1000 2026-11“, `Helvetopo_Pixel_25-1000_Schweiz_2026-11`);
- Gebiet (Region aus regions.REGIONS);

Copyright-Zeilen und QUELLSTAND.txt kommen aus den STAC-Metadaten (quellstand.py).

Aufbau nach Gerätetest 5 (GPSMAP 67), wie die Referenzkarte „Topo Schweiz v3 Raster“: zwei Serien von GMPs
mit derselben Level-Menge (oberste Ebene 17 leer).
- Feine Serie: eine GMP je Zelle des landesweiten Gitters (10 × 10 Bilder zu 512 px des feinsten Massstabs).
  Bilder auf 24 bis 21, auf 20 bis 18 nur das Abdeckungspolygon.
- Grobe Serie: eine GMP je grosser Zelle (COARSE_CELL = 0,2352°). Bilder auf 20 bis 18, auf 24 bis 21
  Raster-Polygone ohne Bild.
Jede GMP liegt zwischen 512 KiB und 16 MiB (rasterimg.GMP_MIN/GMP_MAX). Kleinere GMPs füllt build_gmp auf, eine grössere bricht ab.

Zoomstufen (höchstens 8 Levels inkl. der obersten, leeren Ebene 17), nach Gerätetest 5:

| Variante | 24     | 23     | 22     | 21     | 20     | 19     | 18      | oben |
|----------|--------|--------|--------|--------|--------|--------|---------|------|
| 25-1000  | SMR25  | SMR25  | SMR50  | SMR100 | SMR200 | SMR500 | SMR1000 | 17   |
| 50-1000  | SMR50  | SMR50  | SMR50  | SMR100 | SMR200 | SMR500 | SMR1000 | 17   |
| 10-1000  | SMR10  | SMR25  | SMR50  | SMR100 | SMR200 | SMR500 | SMR1000 | 17   |
| Serie    | fein   | fein   | fein   | fein   | grob   | grob   | grob    |      |

Je Ebene zeigen alle Varianten denselben Massstab, nur die feinsten Ebenen unterscheiden sich. Die Bildebenen
liegen lückenlos von 24 abwärts (check_levels bricht sonst ab). Am Gerät: Kartendetail „Normal“.

Map-IDs: feine Serie <FID>0001 … <FID>7999, grobe Serie <FID>8001 …, fortlaufend über die Zellen, die die Schweiz (inkl. FL, 1 km Puffer)
berühren. Sie sind in allen Regionen einer Variante gleich und kollidieren nicht. <FID>9000 bleibt der
gmapi-Übersichtskarte vorbehalten.

Aufruf:
  python3 -I release.py --variant 25-1000 --region schweiz [--version 2026-11] [--gmapi] [--dry-run]
  # → Helvetopo_Pixel_25-1000_Schweiz_2026-11.img, Kartenname „Helvetopo Pixel 25-1000 2026-11“, FID 7705
  python3 -I release.py --variant 25-1000 --region west --gmapi      # Hälfte ohne Überlappung (PARTITIONS)
  python3 -I release.py --variant 10-1000 --region west --gmapi      # Teil ohne Überlappung (PARTITIONS['teile'])
  python3 -I release.py --variant 10-1000 --region bern --disjoint   # Region ohne Überlappung
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as _dt
import math
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
import rasterimg as RI  # noqa: E402
from rasterimg import GmpOptions, build_gmp, build_mps, patch_gmp_file, write_img  # noqa: E402
from smr_tiles import cut_tiles  # noqa: E402

# Gerätetest 3 (GPSMAP 67): Fehlt eine Bits-Stufe zwischen 24 und der gröbsten Bildebene, zeigt das Gerät dort
# kein Bild (10-1000 und Luftbild kompakt ohne 23: Loch bei „200 m“/„300 m“, 50-1000 ohne 23). Deshalb gilt:
# Bildebenen lückenlos von 24 abwärts (check_levels). Mit 8 Levels inkl. der leeren obersten reicht das bis 18.
# Weniger Massstäbe als Stufen: derselbe Massstab auf mehreren Stufen (gleiche Bilder, keine Zusatzkosten).
FINEST, MAX_LEVELS = 24, 8

# Variante -> (oberste Ebene, [(bits, Massstab, Faktor zu DPP25)]) – feinste zuerst
VARIANTS = {
    # Alle Varianten: je Ebene derselbe Massstab (Entscheid des Benutzers 2026-11-06, Gerätetest 5):
    # 23 SMR25, 22 SMR50, 21 SMR100, 20 SMR200, 19 SMR500, 18 SMR1000. Auf 24 der feinste Massstab der Variante.
    # Empfohlen am Gerät: Kartendetail „Normal“ (Wechsel eine Stufe später als „Maximal“).
    # Die Stufen 20..18 kommen aus der groben Serie (COARSE_MAX_BITS).
    # SMR25 in halber Auflösung (2,5 m/px) wie die Referenzkarte „Topo Schweiz v3 Raster“, JPEG q75.
    "25-1000": (17, [(24, 25, 2), (23, 25, 2), (22, 50, 4), (21, 100, 4), (20, 200, 8), (19, 500, 16),
                     (18, 1000, 64)]),
    # Fassung mit voller SMR25-Auflösung (zum Vergleich)
    "25-1000v": (17, [(24, 25, 1), (23, 25, 1), (22, 50, 2), (21, 100, 4), (20, 200, 8), (19, 500, 16),
                      (18, 1000, 64)]),
    # SMR50 auf 24, 23 und 22 mit denselben Bildern (volle Auflösung): GMP bleibt unter 16 MiB (GMP_MAX)
    "50-1000": (17, [(24, 50, 2), (23, 50, 2), (22, 50, 2), (21, 100, 4), (20, 200, 8), (19, 500, 16),
                     (18, 1000, 64)]),
    # SMR10, SMR25 und SMR50 in halber Auflösung, JPEG q75. SMR10 nur auf 24.
    "10-1000": (17, [(24, 10, 1), (23, 25, 2), (22, 50, 4), (21, 100, 4), (20, 200, 8), (19, 500, 16),
                     (18, 1000, 64)]),
    # Fassung mit voller Auflösung (zum Vergleich), gleiche Ebenen
    "10-1000v": (17, [(24, 10, 0.5), (23, 25, 1), (22, 50, 2), (21, 100, 4), (20, 200, 8), (19, 500, 16),
                      (18, 1000, 64)]),
}
CELL_PX = RG.GMP_TILES * RG.TILE_PX     # 5120 px des feinsten Massstabs je Zelle
# Draw-Priority der Rasterkarten (Pixel, Luftbild). Das Original hat 31. Helvetopo nimmt 29: über der
# Vektorkarte (25) und unter den Routen (Overlay 7702: 31, Routen-Kacheln in der Raster-gmapi: 31).
RASTER_PRIORITY = 29
R_STYLE = {"huffman": True, "orig_extras": True, "unique_tile_labels": True, "coverage_bottom_last": True,
           "bottom_last_full": True, "draw_priority": RASTER_PRIORITY,
           "coverage_levels": 7}         # Abdeckungspolygon auf allen 7 Ebenen unter der obersten (keine leere Ebene)
ID_MAX = 7999                  # feine Serie; <FID>8001… grobe Serie, <FID>9000 gmapi-Übersicht
OVERLAP_PX = 1      # Bilder überlappen 1 px nach Osten/Süden: keine Säume an Kachelkanten (BaseCamp-Befund 50-1000)
# Die Bildgrenzen stehen in Karteneinheiten von bits 24 (360°/2^24 = 2,1e-5°, rasterimg.deg2mu). Ist ein Pixel
# kleiner als eine Einheit, rundet 1 px Überlappung oft auf 0 Einheiten. overlap_px() verlangt deshalb
# zusätzlich mindestens OVERLAP_MU Einheiten (0 = nur OVERLAP_PX, Stand der Pixelkarten 2026-11).
OVERLAP_MU = float(os.environ.get("HELVETOPO_OVERLAP_MU", "0"))   # --overlap-mu, auch für die Worker-Prozesse
MU_DEG = 360.0 / (1 << 24)


def overlap_px(dpp: float, min_mu: float | None = None) -> int:
    """Überlappung in Pixeln: mindestens OVERLAP_PX und mindestens min_mu Karteneinheiten."""
    mu = OVERLAP_MU if min_mu is None else min_mu
    return max(OVERLAP_PX, math.ceil(mu * MU_DEG / dpp - 1e-9))
PREFIX = "Helvetopo"
VARIANT_OPTS: dict = {}
GAP_BELOW: dict = {}            # Versuch: Lücken erst unterhalb dieser bits erlaubt (Versuch 25-1000x verworfen)

# Zwei Serien wie die Referenzkarte (Gerätetest 5: grobe Stufen aus vielen kleinen Zellen sind sehr träge):
# - feine Serie: Zellen wie bisher, Bilder auf den Ebenen > COARSE_MAX_BITS, darunter nur das Abdeckungspolygon;
# - grobe Serie: Zellen mit Kante COARSE_CELL, Bilder auf den Ebenen ≤ COARSE_MAX_BITS, auf den feineren Ebenen
#   Raster-Polygone ohne Bild (GmpOptions.placeholder_bits).
# Beide Serien haben dieselbe Level-Menge (oberste leer). Map-IDs grob: <FID>8001 … (COARSE_ID_BASE).
COARSE_MAX_BITS = 20
COARSE_CELL = 4 * CELL_PX * RG.DPP25     # 0,2352° = 2 × 2 Zellen von 25-1000/50-1000, wie die Referenz
COARSE_ID_BASE = 8000
GMP_MAX = RI.GMP_MAX                      # Gerätetest 5, siehe rasterimg.GMP_MAX
# 50-1000: q70 mit optimierten Huffman-Tabellen, damit die ganze Schweiz in eine Datei unter 4 GiB passt
# (Schweiz-Build 3,60 GiB; mit q85 ohne Optimierung 5,24 GiB). Optimierte Tabellen sparen ca. 3 % bei gleichem Bild.
QUALITY_DEFAULT = {"25-1000": 75, "10-1000": 75, "50-1000": 70}   # sonst 85
JPEG_OPTIMIZE = {"50-1000"}                                         # Varianten mit optimierten Huffman-Tabellen
FID_DEFAULT = {"25-1000v": 7705, "10-1000v": 7706, "50-1000": 7704, "25-1000": 7705, "10-1000": 7706}     # Release-Plan
ALIASES = {"50-500": "50-1000", "25-500": "25-1000", "10-500": "10-1000"}  # alte Namen
# Testgebiete: Kantonsmaske + Rechteck (AGENTS.md: Wil bis St. Gallen plus Säntis/Alpstein)
TEST_AREAS = {"testgebiet": ("ostschweiz", (9.00, 47.20, 9.50, 47.50))}
REGION_FILE = {"testgebiet": "Testgebiet", "schweiz": "Schweiz", "ostschweiz": "Ostschweiz", "graubuenden": "Graubuenden",
               "stgallen": "StGallen", "zentralschweiz": "Zentralschweiz", "zuerich": "Zuerich",
               "nordwestschweiz": "Nordwestschweiz", "bern": "Bern", "genfersee": "Genfersee",
               "wallis": "Wallis", "tessin": "Tessin", "west": "West", "ost": "Ost", "sued": "Sued",
               "mitte": "Mitte"}


# Teilungen ohne Überlappung: Jede grobe Zelle (COARSE_CELL) gehört mit allen ihren feinen Zellen genau zu
# einem Teil, und zwar zu dem Teil mit dem grössten Anteil an Maskenfläche in der Zelle. Die Grenze folgt dem
# Gitter der groben Zellen. So kommt keine Map-ID in zwei Dateien derselben FID vor.
# - "haelften": west/ost (Pseudo-Regionen, je eine Datei für 50-1000 und 25-1000);
# - "regionen": die neun Regionen mit --disjoint;
# - "teile": vier Teile für 10-1000 (Release ab 2026-11). Ein Teil besteht aus ganzen Teilen von "regionen"
#   (PARTITION_BASE): Die groben Zellen gehören zum Teil ihrer Region. So bleiben Zellen und Map-IDs gleich wie
#   bei den neun Regionen.
PARTITIONS = {
    "haelften": {"west": ["genfersee", "bern", "nordwestschweiz", "wallis"],
                 "ost": ["zuerich", "ostschweiz", "graubuenden", "zentralschweiz", "tessin"]},
    "regionen": {r: [r] for r in ("genfersee", "bern", "nordwestschweiz", "wallis", "zuerich", "ostschweiz",
                                  "graubuenden", "zentralschweiz", "tessin")},
    "teile": {"west": ["genfersee", "bern", "nordwestschweiz"], "sued": ["wallis", "tessin"],
              "mitte": ["zuerich", "zentralschweiz"], "ost": ["ostschweiz", "graubuenden"]},
}
PARTITION_BASE = {"teile": "regionen"}       # Teilung aus ganzen Teilen einer anderen Teilung
PARTITION_FOR = {"10-1000": "teile"}         # Teilung für --region west/ost/… je Variante, sonst "haelften"
HALVES = PARTITIONS["haelften"]
REGION_NAME = {"testgebiet": "Testgebiet", "schweiz": "Schweiz", "graubuenden": "Graubünden", "stgallen": "St. Gallen",
               "zuerich": "Zürich", "sued": "Süd"}


def default_names(variant: str, region: str, version: str) -> tuple[str, str]:
    """(Kartenname, Dateiname ohne Endung) nach Release-Plan, nur ASCII im Dateinamen."""
    area = REGION_FILE.get(region, region.capitalize())
    shown = REGION_NAME.get(region, area)
    name = f"{PREFIX} Pixel {variant} {version}" + ("" if region == "schweiz" else f" {shown}")
    return name, f"{PREFIX}_Pixel_{variant}_{area}_{version}"


def partition_cells(plan: "Plan", group: str, part: str, workdir: str) -> list[tuple[int, int]]:
    """Feine Zellen des Teils `part` einer Teilung ohne Überlappung (PARTITIONS[group]), siehe dort.
    Grundlage sind die Zellen der ganzen Schweiz. Bricht ab, wenn eine grobe Zelle keinem Teil zufällt."""
    import numpy as np
    parts = PARTITIONS[group]
    if group in PARTITION_BASE:          # ganze Teile der Grundteilung zusammenfassen
        base = PARTITION_BASE[group]
        cells = set()
        for sub in next(v for k, v in parts.items() if k == part):
            cells.update(partition_cells(plan, base, sub, workdir))
        return [cr for cr in plan.cells(RG.region_mask("schweiz", workdir)) if cr in cells]
    allcells = plan.cells(RG.region_mask("schweiz", workdir))
    masks = {k: sum(np.asarray(RG.region_mask(r, workdir), dtype=np.int64) for r in regs) for k, regs in parts.items()}
    b = plan.blk * plan.ratio            # Maskenzellen je Kante einer groben Zelle
    owner = {}
    for cc, rr in sorted({plan.coarse_of(c, r) for c, r in allcells}):
        share = {k: int(m[rr * b:(rr + 1) * b, cc * b:(cc + 1) * b].astype(bool).sum()) for k, m in masks.items()}
        best = max(share, key=lambda k: share[k])     # bei Gleichstand der erste Teil in PARTITIONS
        if share[best] == 0:
            raise ValueError(f"grobe Zelle {(cc, rr)} liegt in keinem Teil von {group}")
        owner[(cc, rr)] = best
    return [cr for cr in allcells if owner[plan.coarse_of(*cr)] == part]


def uncovered_cells(plan: "Plan", cells) -> list:
    """Zellen ohne geladenes SMR10-Blatt (SMR10 wird nur bei Bedarf geladen, siehe manifest_pk10.json)."""
    if 10 not in plan.scales:
        return []
    boxes = [m["bbox"] for m in Q._manifest() if m["scale"] == 10]
    out = []
    for c, r in cells:
        w, s_, e, n = plan.bounds(c, r)
        if not any(
                b[0] < e and b[2] > w and b[1] < n and b[3] > s_ for b in boxes):
            out.append((c, r))
    return out


def cells_with_land(plan: "Plan", cells) -> list:
    """Zellen, die Land von CH oder FL enthalten (swissBOUNDARIES3D, ohne Puffer)."""
    from osgeo import ogr, osr
    ogr.UseExceptions()
    ds = ogr.Open(RG.BOUNDARIES)          # Referenz halten, sonst gibt GDAL den Layer frei
    lay = ds.GetLayerByName("tlm_landesgebiet")
    land = [f.GetGeometryRef().Clone() for f in lay if f.GetField("icc") in ("CH", "LI")]
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    tr = osr.CoordinateTransformation(wgs, lay.GetSpatialRef())
    out = []
    for c, r in cells:
        w, s_, e, n = plan.bounds(c, r)
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for x, y in ((w, s_), (e, s_), (e, n), (w, n), (w, s_)):
            ring.AddPoint_2D(x, y)
        g = ogr.Geometry(ogr.wkbPolygon)
        g.AddGeometry(ring)
        g.Transform(tr)
        if any(g.Intersects(x) for x in land):
            out.append((c, r))
    return out


@dataclasses.dataclass(frozen=True)
class Plan:
    variant: str
    top: int
    levels: tuple[tuple[int, int, float], ...]

    @property
    def fine_factor(self) -> float:
        return self.levels[0][2]

    @property
    def cell(self) -> float:            # Zellkante in Grad
        return CELL_PX * RG.DPP25 * self.fine_factor

    @property
    def blk(self) -> int:               # Zellkante in Maskenzellen (Feinkacheln SMR25 zu 512 px)
        return max(1, round(RG.GMP_TILES * self.fine_factor))

    @property
    def scales(self) -> list[int]:
        return sorted({s for _, s, _ in self.levels})

    def cells(self, mask) -> list[tuple[int, int]]:
        rows, cols = mask.shape
        b = self.blk
        return [(c, r) for r in range(math.ceil(rows / b)) for c in range(math.ceil(cols / b))
                if mask[r * b:(r + 1) * b, c * b:(c + 1) * b].any()]

    def bounds(self, c: int, r: int):
        w = RG.GRID_W + c * self.cell
        n = RG.GRID_N - r * self.cell
        return w, n - self.cell, w + self.cell, n

    @property
    def ratio(self) -> int:             # feine Zellen je Kante einer groben Zelle
        q = COARSE_CELL / self.cell
        if abs(q - round(q)) > 1e-6 or round(q) < 1:
            raise ValueError(f"grobe Zelle {COARSE_CELL}° ist kein Vielfaches der Zelle {self.cell}°")
        return round(q)

    def coarse_of(self, c: int, r: int) -> tuple[int, int]:
        return c // self.ratio, r // self.ratio

    @staticmethod
    def coarse_bounds(cc: int, rr: int):
        w = RG.GRID_W + cc * COARSE_CELL
        n = RG.GRID_N - rr * COARSE_CELL
        return w, n - COARSE_CELL, w + COARSE_CELL, n


def split(px: int) -> int:
    """Kleinste Bildzahl je Kante, sodass die Bildkante ganzzahlig und ≤ 512 px ist."""
    n = math.ceil(px / RG.TILE_PX)
    while px % n:
        n += 1
    return n


def check_levels(name: str, top: int, levels, finest: int = FINEST, gap_below: int | None = None) -> None:
    """Bricht ab, wenn die Bildebenen nicht lückenlos von `finest` (Detail: 24) abwärts liegen (Gerätetest 3)
    oder mehr als 8 Levels inkl. der leeren obersten Ebene entstehen."""
    bits = [b for b, *_ in levels]
    if len(levels) + 1 > MAX_LEVELS:
        raise ValueError(f"{name}: {len(levels) + 1} Levels, höchstens {MAX_LEVELS} (inkl. oberster Ebene)")
    want = list(range(finest, finest - len(bits), -1))
    if gap_below is not None:        # Versuch: lückenlos nur bis gap_below, darunter beliebig (absteigend)
        fine = [b for b in bits if b >= gap_below]
        want = list(range(finest, finest - len(fine), -1)) + [b for b in bits if b < gap_below]
        if fine != want[:len(fine)] or sorted(bits, reverse=True) != bits:
            want = None
    if bits != want:
        miss = sorted(set(range(min(bits), finest + 1)) - set(bits), reverse=True)
        raise ValueError(f"{name}: Bildebenen {bits} nicht lückenlos ab {finest} (fehlt: {miss or 'Reihenfolge'})")
    if top >= min(bits):
        raise ValueError(f"{name}: oberste Ebene {top} muss gröber als {min(bits)} sein")


def check_overview(top: int) -> None:
    """Detailkacheln (24..top+1) und Übersicht (overview.LEVELS) zusammen lückenlos bis zur gröbsten Stufe."""
    import overview as OV  # noqa: E402
    check_levels("Übersicht", OV.TOP, [(b, f) for b, f in OV.LEVELS], finest=top)


def plan_for(variant: str) -> Plan:
    top, levels = VARIANTS[variant]
    check_levels(variant, top, levels, gap_below=GAP_BELOW.get(variant))
    return Plan(variant, top, tuple(levels))


def id_table(plan: Plan, out: str) -> dict[tuple[int, int], int]:
    ch = RG.region_mask("schweiz", os.path.join(out, "_mask"))
    tab = {cr: i + 1 for i, cr in enumerate(plan.cells(ch))}
    if len(tab) > ID_MAX:
        raise ValueError(f"{len(tab)} Zellen > {ID_MAX} Map-IDs je FID")
    return tab


def coarse_id_table(plan: Plan, fine_ids: dict) -> dict[tuple[int, int], int]:
    """Map-ID-Suffix je grober Zelle (alle groben Zellen der Schweiz, gleich in allen Regionen)."""
    cc = sorted({plan.coarse_of(c, r) for c, r in fine_ids}, key=lambda x: (x[1], x[0]))
    if len(cc) > 9000 - COARSE_ID_BASE - 1:
        raise ValueError(f"{len(cc)} grobe Zellen, zu viele Map-IDs")
    return {x: COARSE_ID_BASE + 1 + i for i, x in enumerate(cc)}


def series_gmp(mid: int, bounds, kind: str, levels, opts: GmpOptions, render, render_args) -> bytes:
    """GMP einer Serie. kind = "fein" (Ebenen > COARSE_MAX_BITS), "grob" (≤ COARSE_MAX_BITS, darüber
    Raster-Polygone ohne Bild) oder "voll" (eine Serie mit Bildern auf allen Ebenen, Aufbau bis Gerätetest 5). levels = [(bits, Quelle, Faktor)]; render(Quelle, Faktor, bounds, *render_args)
    liefert die Bilder. Gleiche (Quelle, Faktor) auf mehreren Ebenen nutzen dieselben Bilder."""
    mine = list(levels) if kind == "voll" else [lv for lv in levels if (lv[0] > COARSE_MAX_BITS) == (kind == "fein")]
    ph = tuple(b for b, *_ in levels if b > COARSE_MAX_BITS) if kind == "grob" else ()
    cache, level_tiles = {}, {}
    for bits, src, factor in mine:
        if (src, factor) not in cache:
            cache[(src, factor)] = render(src, factor, bounds, *render_args)
        level_tiles[bits] = cache[(src, factor)]
    if ph:                                  # Platzhalter: Umrisse der Bilder der feinsten groben Ebene
        first = level_tiles[max(b for b, *_ in mine)]
        for b in ph:
            level_tiles[b] = first
    all_tiles = [t for v in cache.values() for t in v]
    data = build_gmp(mid, all_tiles, dataclasses.replace(opts, placeholder_bits=ph), level_tiles=level_tiles)
    RI.check_gmp_size(f"GMP {mid}", len(data))
    return data


def render_smr(scale, factor, bounds, out: str, quality: int, optimize: bool = False):
    """SMR-Bilder für eine Fläche: Pixelgrösse DPP25 × factor, Bildkante ≤ 512 px, 1 px Überlappung."""
    w, so, e, n = bounds
    px = round((e - w) / (RG.DPP25 * factor))
    k = split(px)
    dpp = (e - w) / px
    ov = overlap_px(dpp)
    tmp = tempfile.mkdtemp(dir=os.path.join(out, "_vrt"))
    try:
        tif = os.path.join(tmp, f"{scale}_{factor}.tif")
        subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-te", repr(w),
                        repr(so - ov * dpp), repr(e + ov * dpp), repr(n), "-ts", str(px + ov), str(px + ov),
                        "-r", "cubic", "-wo", "INIT_DEST=255",
                        "-wo", "NUM_THREADS=2", "-multi", "-co", "TILED=YES",
                        RG.vrt_for(f"pk{scale}", os.path.join(out, "_vrt")), tif], check=True)
        return cut_tiles(tif, w, n, dpp, k, k, tile_px=px // k, quality=quality, overlap=ov, optimize=optimize)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def gmp_dir(fid: int, plan: Plan, quality: int, kind: str = "fein") -> str:
    """Zwischenspeicher der GMPs je Serie, mit Level-Signatur: Eine geänderte Level-Tabelle baut neu."""
    sig = "-".join(f"{b}x{s}f{f:g}" for b, s, f in plan.levels)
    opt = "o" if plan.variant in JPEG_OPTIMIZE else ""
    ovs = f"_ov{OVERLAP_MU:g}" if OVERLAP_MU else ""
    return f"_gmp_{fid}_{plan.variant}_q{quality}{opt}_t{plan.top}_{sig}_{kind}{COARSE_MAX_BITS}{ovs}"


def gmp_options(plan: Plan, product: str) -> GmpOptions:
    src = Q.sources(plan.scales)
    cr = ["©swisstopo"] + [f"{v['name']} ({Q._years(v)}), swisstopo OGD" for v in src.values()]
    cr.append(f"{product}, inoffizielle Karte")
    return dataclasses.replace(GmpOptions(), **R_STYLE,
                               levels=(plan.top,) + tuple(sorted(b for b, _, _ in plan.levels)),
                               copyright=tuple(cr),
                               hdr_comment1=("©swisstopo, Daten unter OGD (opendata.swiss).",
                                             f"{product}, inoffizielle Karte."),
                               hdr_comment2=("Swiss Map Raster", "©swisstopo"),
                               **VARIANT_OPTS.get(plan.variant, {}))


def build_one(job):
    out, fid, product, quality, plan, kind, bounds, mid = job
    dest = os.path.join(out, gmp_dir(fid, plan, quality, kind), f"{mid:08d}.gmp")
    if os.path.exists(dest):
        return mid, os.path.getsize(dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    data = series_gmp(mid, bounds, kind, plan.levels, gmp_options(plan, product), render_smr,
                      (out, quality, plan.variant in JPEG_OPTIMIZE))
    with open(dest + ".part", "wb") as f:
        f.write(data)
    os.replace(dest + ".part", dest)
    return mid, len(data)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", required=True, choices=list(VARIANTS) + list(ALIASES))
    ap.add_argument("--fid", type=int, help="Standard nach Release-Plan: 50-1000 → 7704, 25-1000 → 7705, "
                                            "10-1000 → 7706")
    ap.add_argument("--version", default=_dt.date.today().strftime("%Y-%m"), help="Release-Version JJJJ-MM")
    ap.add_argument("--name", help="Kartenname auf Gerät/BaseCamp (Standard: Helvetopo Pixel <Variante> <Version>)")
    ap.add_argument("--region", default="schweiz", choices=sorted(set(RG.REGIONS) | set(TEST_AREAS) |
                                                              {p for g in PARTITIONS.values() for p in g}))
    ap.add_argument("--disjoint", action="store_true",
                    help="Region ohne Überlappung mit den Nachbarregionen (PARTITIONS['regionen']); Teile wie west/ost immer")
    ap.add_argument("--file", help="Dateiname ohne Endung (Standard: Helvetopo_Pixel_<Variante>_<Gebiet>_<Version>)")
    ap.add_argument("--out", default=os.path.join(RG.OUT_DEFAULT, "..", "release"))
    ap.add_argument("--quality", type=int, help="JPEG-Qualität (Standard 85; 25-1000 und 10-1000: 75; 50-1000: 70)")
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--gmapi", action="store_true")
    ap.add_argument("--gmapi-only", action="store_true",
                    help="nur die gmapi bauen, ohne Geräte-IMG (BaseCamp: eine gmapi für die ganze Schweiz, "
                         "ohne 4-GiB-Grenze)")
    ap.add_argument("--gmapi-fid", type=int, help="abweichende FID für die gmapi (Test in BaseCamp)")
    ap.add_argument("--routes", metavar="PBF", help="gmapi mit transparenten Routen-Kacheln (routen.py), "
                    "z. B. work/raster_img/routen/routes.osm.pbf")
    ap.add_argument("--overview", action="store_true",
                    help="Übersichts-GMP für die groben Stufen 17..13 (Versuch; Gerätetest 4: IMG wird nicht angeboten)")
    ap.add_argument("--overlap-mu", type=float, default=0,
                    help="Bildüberlappung mindestens N Karteneinheiten (bits 24), siehe OVERLAP_MU; Standard 0")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"),
                    help="nur Zellen, die diese Box berühren (Stichprobe)")
    a = ap.parse_args()
    a.variant = ALIASES.get(a.variant, a.variant)
    global OVERLAP_MU
    OVERLAP_MU = a.overlap_mu
    os.environ["HELVETOPO_OVERLAP_MU"] = repr(a.overlap_mu)     # Pool-Worker importieren das Modul neu
    a.gmapi = a.gmapi or a.gmapi_only
    a.fid = a.fid or FID_DEFAULT[a.variant]
    a.quality = a.quality or QUALITY_DEFAULT.get(a.variant, 85)
    dn, df = default_names(a.variant, a.region, a.version)
    a.name, a.file = a.name or dn, a.file or df
    out = os.path.normpath(a.out)
    os.makedirs(os.path.join(out, "_vrt"), exist_ok=True)
    plan = plan_for(a.variant)
    for s in plan.scales:
        if not os.path.isdir(os.path.join(RG.DL, f"pk{s}")):
            raise SystemExit(f"Quelle fehlt: {RG.DL}/pk{s} (SMR{s} laden)")
    ids = id_table(plan, out)
    mask_region = a.region
    if a.region in TEST_AREAS:
        mask_region, box = TEST_AREAS[a.region]
        a.bbox = a.bbox or list(box)
    group = PARTITION_FOR.get(a.variant, "haelften")
    if a.region in PARTITIONS[group] and a.region not in RG.REGIONS:
        cells = partition_cells(plan, group, a.region, os.path.join(out, "_mask"))
    elif a.region not in RG.REGIONS and a.region not in TEST_AREAS:
        raise SystemExit(f"--region {a.region} gibt es für {a.variant} nicht (Teilung {group}: "
                         f"{', '.join(PARTITIONS[group])})")
    elif a.disjoint:
        if a.region not in PARTITIONS["regionen"]:
            raise SystemExit(f"--disjoint gilt nur für {', '.join(PARTITIONS['regionen'])}")
        cells = partition_cells(plan, "regionen", a.region, os.path.join(out, "_mask"))
    else:
        cells = plan.cells(RG.region_mask(mask_region, os.path.join(out, "_mask")))
    if a.bbox:
        bw, bs, be, bn = a.bbox
        cells = [(c, r) for c, r in cells if not (plan.bounds(c, r)[2] < bw or plan.bounds(c, r)[0] > be
                                                   or plan.bounds(c, r)[3] < bs or plan.bounds(c, r)[1] > bn)]
    miss = uncovered_cells(plan, cells)
    if miss:            # Zellen nur im 1-km-Puffer ausserhalb der Grenze: kein SMR10-Blatt, kein Inhalt
        drop = set(miss) - set(cells_with_land(plan, miss))
        if drop:
            print(f"  {len(drop)} Zelle(n) ohne SMR10-Blatt und ohne Land CH/FL weggelassen: {sorted(drop)}")
            cells = [cr for cr in cells if cr not in drop]
            miss = [cr for cr in miss if cr not in drop]
    if miss:
        raise SystemExit(f"{len(miss)} von {len(cells)} Zellen ohne geladenes SMR10-Blatt: zuerst SMR10 laden "
                         "(downloads/smr/pk10, manifest_pk10.json) oder mit --bbox auf das geladene Gebiet begrenzen")
    cids = coarse_id_table(plan, ids)
    jobs = [(out, a.fid, a.name, a.quality, plan, "fein", plan.bounds(c, r), a.fid * 10000 + ids[(c, r)])
            for c, r in cells]
    coarse = sorted({plan.coarse_of(c, r) for c, r in cells})
    jobs += [(out, a.fid, a.name, a.quality, plan, "grob", Plan.coarse_bounds(*x), a.fid * 10000 + cids[x])
             for x in coarse]
    print(f"{a.file}: Variante {a.variant}, FID {a.fid}, „{a.name}“, Region {a.region}")
    print(f"  Levels {[plan.top] + sorted(b for b, _, _ in plan.levels)}: " +
          ", ".join(f"{b}=SMR{s}" for b, s, _ in plan.levels))
    print(f"  {len(cells)} GMP fein (Zelle {plan.cell:.4f}°, Bilder auf {COARSE_MAX_BITS + 1}–24), "
          f"{len(coarse)} GMP grob (Zelle {COARSE_CELL:.4f}°, Bilder auf {COARSE_MAX_BITS} und gröber)")
    print(f"  {len(jobs)} GMP, Map-IDs {min(j[7] for j in jobs)}–{max(j[7] for j in jobs)}, "
          f"ganze Schweiz {len(ids)} Zellen")
    if a.dry_run:
        return
    for s in plan.scales:                # VRTs vorab, nicht parallel in den Workern
        RG.vrt_for(f"pk{s}", os.path.join(out, "_vrt"))
    t0, nbytes = time.time(), 0
    with Pool(a.jobs) as pool:
        for i, (_, size) in enumerate(pool.imap_unordered(build_one, jobs), 1):
            nbytes += size
            if i % 25 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} GMP, {nbytes / 1e9:.2f} GB, {(time.time() - t0) / 60:.1f} min", flush=True)
    mids = sorted(j[7] for j in jobs)
    kinds = {j[7]: j[5] for j in jobs}
    paths = [os.path.join(out, gmp_dir(a.fid, plan, a.quality, kinds[m]), f"{m:08d}.gmp") for m in mids]
    bb = [plan.bounds(c, r) for c, r in cells]
    area = (min(b[0] for b in bb), min(b[1] for b in bb), max(b[2] for b in bb), max(b[3] for b in bb))
    if a.overview:            # grobe Stufen 17..13 (overview.py), Detailkacheln enden bei 18
        import overview as OV  # noqa: E402
        check_overview(plan.top)
        ov = OV.write_overview(a.fid, area, RG.vrt_for("pk1000", os.path.join(out, "_vrt")),
                               gmp_options(plan, a.name), a.quality, os.path.join(out, "_overview"),
                               os.path.join(out, "_vrt"))
        mids, paths = mids + [OV.map_id(a.fid)], paths + [ov]
        print(f"  Übersicht {OV.map_id(a.fid)}: Ebenen {[OV.TOP] + sorted(b for b, _ in OV.LEVELS)}, "
              f"{os.path.getsize(ov) / 1e6:.1f} MB")
    total = 64 * 1024 * (1 + len(paths)) + sum(os.path.getsize(p) for p in paths)
    if not a.gmapi_only and total > 0xFFFF * 64 * 1024:
        raise SystemExit(f"{total / 2**30:.2f} GiB > 4 GiB: Gebiet teilen (--region)")
    with open(os.path.join(out, a.file + "_QUELLSTAND.txt"), "w", encoding="utf-8") as f:
        f.write(Q.quellstand_text(plan.scales, area, a.name, a.fid))
    if not a.gmapi_only:
        mps = build_mps(a.fid, 1, a.name, [(m, f"{m:08d}") for m in mids], orig_style=True)
        fn = os.path.join(out, a.file + ".img")
        write_img(fn, [("GMAPPROM", "MPS", mps)] + [(f"{m:08d}", "GMP", p) for m, p in zip(mids, paths)],
                  f"{a.name} ©swisstopo")
        print(f"{fn}: {os.path.getsize(fn) / 1e9:.3f} GB, {(time.time() - t0) / 60:.1f} min")
    if a.gmapi:
        from make_gmapi import make_gmapi_files  # noqa: E402
        gf = a.gmapi_fid or a.fid
        lines = list(Q.copyright_lines(plan.scales, area, a.name)) + [Q.LICENSE_LINE]
        if a.routes:
            from routen import gmapi_with_routes  # noqa: E402
            d = gmapi_with_routes(paths, os.path.join(out, "gmapi"), a.name, gf, lines, a.routes,
                                  REGION_NAME.get(a.region, a.region))
        else:
            d = make_gmapi_files(paths, os.path.join(out, "gmapi"), a.name, gf, gf * 10000 + 9000,
                                 copyright_lines=lines, draw_priority=RASTER_PRIORITY)
        print(f"gmapi: {d}")


if __name__ == "__main__":
    main()
