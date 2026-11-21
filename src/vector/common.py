"""Gemeinsame Einstellungen und Hilfsfunktionen für den Konverter swissTLM3D → OSM-PBF."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pyogrio
import shapely
from pyproj import Transformer

from ..paths import DOWNLOADS, MAIN

log = logging.getLogger("vector")

MAIN_CHECKOUT = MAIN

TLM_GPKG = DOWNLOADS / "swisstlm3d" / "SWISSTLM3D_2026_LV95_LN02.gpkg"
NAMES_GPKG = DOWNLOADS / "swissnames3d" / "swissnames3d_2026_2056.gpkg"
BOUNDARIES_GPKG = DOWNLOADS / "swissboundaries3d" / "swissBOUNDARIES3D_1_5_LV95_LN02.gpkg"
ADDRESS_CSV = DOWNLOADS / "gebaeudeadressen" / "amtliches-gebaeudeadressverzeichnis_ch_2056.csv"
STREET_CSV = DOWNLOADS / "strassenverzeichnis" / "amtliches-strassenverzeichnis_ch_2056.csv"
# Kleinmassstäbliche Karten für die Gipfelklassen (src/vector/peaks.py)
SMV1000_GPKG = DOWNLOADS / "swiss-map-vector1000" / "SMV1000-4-ALLLAYERS-CHLV95_NONE-GPKG" / "SMV1000.gpkg"
SMV500_GPKG = DOWNLOADS / "swiss-map-vector500" / "SMV500-4-ALLLAYERS-CHLV95_NONE-GPKG" / "SMV500.gpkg"
TLMREGIO_GPKG = DOWNLOADS / "swisstlmregio" / "swissTLMRegio_Product_LV95.gpkg"

# "Kein Wert" in swissTLM3D
NO_VALUE = {"k_W", "", None}

# Dezimalstellen der OSM-Koordinaten (1e-7° ≈ 1 cm)
COORD_SCALE = 10_000_000


@dataclass(frozen=True)
class Area:
    """Bearbeitungsgebiet in WGS84 (lon/lat)."""

    west: float
    south: float
    east: float
    north: float
    margin_m: float = 600.0  # Leserand in LV95, damit Clip-Kanten sauber sind

    @property
    def wgs84_box(self) -> shapely.Polygon:
        return shapely.box(self.west, self.south, self.east, self.north)

    def lv95_bbox(self) -> tuple[float, float, float, float]:
        t = Transformer.from_crs(4326, 2056, always_xy=True)
        xs, ys = [], []
        # Rand mehrfach abtasten, weil das Rechteck in LV95 leicht schief ist
        for i in range(11):
            f = i / 10
            for lon, lat in (
                (self.west + f * (self.east - self.west), self.south),
                (self.west + f * (self.east - self.west), self.north),
                (self.west, self.south + f * (self.north - self.south)),
                (self.east, self.south + f * (self.north - self.south)),
            ):
                x, y = t.transform(lon, lat)
                xs.append(x)
                ys.append(y)
        m = self.margin_m
        return (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)


TEST_AREA = Area(9.00, 47.20, 9.50, 47.50)

_TO_WGS84 = Transformer.from_crs(2056, 4326, always_xy=True)


def to_wgs84(geoms: np.ndarray) -> np.ndarray:
    """LV95 → WGS84 (2D), vektorisiert."""
    geoms = shapely.force_2d(geoms)

    def _tf(coords: np.ndarray) -> np.ndarray:
        x, y = _TO_WGS84.transform(coords[:, 0], coords[:, 1])
        return np.column_stack([x, y])

    return shapely.transform(geoms, _tf)


def read_layer(path: Path, layer: str, area: Area | None, columns=None, where=None):
    """Liest einen Layer (optional auf das Gebiet gefiltert) als GeoDataFrame in LV95."""
    kwargs = {}
    if area is not None:
        kwargs["bbox"] = area.lv95_bbox()
    if columns is not None:
        kwargs["columns"] = columns
    if where:
        kwargs["where"] = where
    df = pyogrio.read_dataframe(path, layer=layer, **kwargs)
    log.info("gelesen %s: %d Objekte", layer, len(df))
    return df


def read_table(path: Path, layer: str, columns=None):
    return pyogrio.read_dataframe(path, layer=layer, read_geometry=False, columns=columns)


def clip_wgs84(geoms: np.ndarray, area: Area) -> np.ndarray:
    """Transformiert nach WGS84 und schneidet auf das Gebiet zu."""
    g = to_wgs84(geoms)
    box = area.wgs84_box
    inside = shapely.contains_properly(box, g)
    out = g.copy()
    todo = ~inside & ~shapely.is_empty(g)
    if todo.any():
        part = g[todo]
        part = shapely.make_valid(part)
        out[todo] = shapely.intersection(part, box)
    return out


def val(v):
    """Normalisiert einen Attributwert: k_W, NaN und leer → None."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, str):
        v = v.strip()
        if v in NO_VALUE:
            return None
    return v


def first_name(v):
    """swissTLM3D-Namen mehrsprachiger Objekte sind mit ' | ' getrennt: erster Teil = Hauptname."""
    v = val(v)
    if v is None:
        return None, None
    parts = [p.strip() for p in str(v).split("|") if p.strip()]
    if not parts:
        return None, None
    return parts[0], (";".join(parts[1:]) if len(parts) > 1 else None)


def int_str(v):
    v = val(v)
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f.is_integer():
        return str(int(f))
    return f"{f:g}"


CANTON_NAMES = {
    "ZH": "Zürich", "BE": "Bern", "LU": "Luzern", "UR": "Uri", "SZ": "Schwyz",
    "OW": "Obwalden", "NW": "Nidwalden", "GL": "Glarus", "ZG": "Zug", "FR": "Fribourg",
    "SO": "Solothurn", "BS": "Basel-Stadt", "BL": "Basel-Landschaft", "SH": "Schaffhausen",
    "AR": "Appenzell Ausserrhoden", "AI": "Appenzell Innerrhoden", "SG": "St. Gallen",
    "GR": "Graubünden", "AG": "Aargau", "TG": "Thurgau", "TI": "Ticino", "VD": "Vaud",
    "VS": "Valais", "NE": "Neuchâtel", "GE": "Genève", "JU": "Jura",
}
