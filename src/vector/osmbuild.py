"""Sammelt Knoten, Wege und Relationen und schreibt sie als OSM-PBF.

Gleiche (gerundete) Koordinaten ergeben denselben Knoten. Das ist die Grundlage für das Routing
in mkgmap: Strassen, die sich in swissTLM3D an einem Stützpunkt treffen, teilen sich danach einen
OSM-Knoten.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from pathlib import Path

import numpy as np
import osmium
import shapely

from .common import COORD_SCALE

log = logging.getLogger("vector")

MAX_WAY_NODES = 1800  # OSM erlaubt 2000; lange Linien werden geteilt


def _key(ix: int, iy: int) -> int:
    return (ix + 1_800_000_000) * 4_000_000_000 + (iy + 900_000_000)


# Kachelmodus (Landesbuild): global eindeutige IDs, damit Kacheln mit osmium merge zusammenpassen.
# Gemeinsame Knoten: ID aus der Koordinate (lon·1e7 < 2^28, lat·1e7 < 2^29 für die Schweiz).
# Eigene POI-Knoten, Wege, Relationen: Bereich je Kachel.
POI_NODE_BASE = 1 << 58
TILE_STRIDE = 1 << 32


def coord_node_id(ix: int, iy: int) -> int:
    return (ix << 29) | iy


class OsmBuilder:
    def __init__(self, tile: int | None = None) -> None:
        """tile=None: fortlaufende IDs ab 1 (Einzelbuild). tile=k: global eindeutige IDs (Kachel k)."""
        self.tile = tile
        self.node_shared: list[bool] = []
        self.node_lon: list[int] = []
        self.node_lat: list[int] = []
        self.node_tags: dict[int, dict[str, str]] = {}
        self.coord_index: dict[int, int] = {}
        self.ways: list[tuple[list[int], dict[str, str]]] = []
        self.relations: list[tuple[list[tuple[str, int, str]], dict[str, str]]] = []
        self.stats: Counter = Counter()

    # --- Knoten -----------------------------------------------------------------
    def _new_node(self, ix: int, iy: int, shared: bool = False) -> int:
        self.node_lon.append(ix)
        self.node_lat.append(iy)
        self.node_shared.append(shared)
        return len(self.node_lon)  # interne Indizes ab 1

    def shared_node(self, ix: int, iy: int) -> int:
        k = _key(ix, iy)
        nid = self.coord_index.get(k)
        if nid is None:
            nid = self._new_node(ix, iy, shared=True)
            self.coord_index[k] = nid
        return nid

    def has_shared_node(self, lon: float, lat: float) -> int | None:
        ix, iy = _round(lon), _round(lat)
        return self.coord_index.get(_key(ix, iy))

    def add_point(self, lon: float, lat: float, tags: dict, merge: bool = False) -> int:
        """Punktobjekt. merge=True: auf einen vorhandenen Linienknoten legen (z. B. Barriere)."""
        ix, iy = _round(lon), _round(lat)
        if merge:
            nid = self.shared_node(ix, iy)
            existing = self.node_tags.setdefault(nid, {})
            existing.update(_clean(tags))
        else:
            nid = self._new_node(ix, iy)
            self.node_tags[nid] = _clean(tags)
        self.stats["points"] += 1
        return nid

    # --- Linien und Flächen -------------------------------------------------------
    def _coords_to_nodes(self, coords: np.ndarray) -> list[int]:
        ixs = np.round(coords[:, 0] * COORD_SCALE).astype(np.int64)
        iys = np.round(coords[:, 1] * COORD_SCALE).astype(np.int64)
        refs: list[int] = []
        last = None
        for ix, iy in zip(ixs.tolist(), iys.tolist()):
            nid = self.shared_node(ix, iy)
            if nid != last:
                refs.append(nid)
                last = nid
        return refs

    def add_line(self, geom, tags: dict) -> int:
        """Linie oder MultiLinie; gibt die Anzahl geschriebener Wege zurück."""
        n = 0
        tags = _clean(tags)
        for part in _parts(geom, ("LineString",)):
            refs = self._coords_to_nodes(shapely.get_coordinates(part))
            if len(refs) < 2:
                continue
            for chunk in _chunks(refs):
                self.ways.append((chunk, dict(tags)))
                n += 1
        self.stats["ways"] += n
        return n

    def add_area(self, geom, tags: dict) -> int:
        """Polygon/MultiPolygon: einfacher Ring als geschlossener Weg, sonst Multipolygon."""
        tags = _clean(tags)
        polys = [p for p in _parts(geom, ("Polygon",)) if not p.is_empty and p.area > 0]
        if not polys:
            return 0
        rings: list[tuple[str, list[int]]] = []
        for p in polys:
            outer = self._ring(p.exterior)
            if outer is None:
                continue
            rings.append(("outer", outer))
            for hole in p.interiors:
                inner = self._ring(hole)
                if inner is not None:
                    rings.append(("inner", inner))
        if not rings:
            return 0
        if len(rings) == 1 and len(rings[0][1]) <= MAX_WAY_NODES:
            self.ways.append((rings[0][1], tags))
            self.stats["area_ways"] += 1
            return 1
        members = []
        for role, refs in rings:
            for chunk in _chunks(refs):
                self.ways.append((chunk, {}))
                members.append(("w", len(self.ways), role))
        rel_tags = {"type": "multipolygon", **tags}
        self.relations.append((members, rel_tags))
        self.stats["multipolygons"] += 1
        return 1

    def _ring(self, ring) -> list[int] | None:
        refs = self._coords_to_nodes(shapely.get_coordinates(ring))
        if len(refs) < 4:
            return None
        if refs[0] != refs[-1]:
            refs.append(refs[0])
        return refs

    # --- Ausgabe ------------------------------------------------------------------
    def _out_ids(self):
        """Interner Index (ab 1) → Ausgabe-ID."""
        n = len(self.node_lon)
        if self.tile is None:
            node_id = list(range(1, n + 1))
            way_base = rel_base = 0
        else:
            poi_base = POI_NODE_BASE + self.tile * TILE_STRIDE
            node_id = []
            k = 0
            for i in range(n):
                if self.node_shared[i]:
                    node_id.append(coord_node_id(self.node_lon[i], self.node_lat[i]))
                else:
                    k += 1
                    node_id.append(poi_base + k)
            way_base = rel_base = self.tile * TILE_STRIDE
        return node_id, way_base, rel_base

    def write(self, path: Path) -> None:
        path = Path(path)
        tmp = path.with_suffix(".tmp.pbf")
        if tmp.exists():
            tmp.unlink()
        log.info(
            "schreibe %s: %d Knoten, %d Wege, %d Relationen",
            path, len(self.node_lon), len(self.ways), len(self.relations),
        )
        node_id, way_base, rel_base = self._out_ids()
        # Knoten ohne Tags, die kein Weg braucht, nicht schreiben (z. B. alte Ecken gepufferter Gebäude)
        used = np.zeros(len(node_id) + 1, dtype=bool)
        for refs, _t in self.ways:
            used[refs] = True
        keep = [i for i in range(len(node_id)) if used[i + 1] or self.node_tags.get(i + 1)]
        order = sorted(keep, key=node_id.__getitem__)
        writer = osmium.SimpleWriter(str(tmp))
        try:
            lon = self.node_lon
            lat = self.node_lat
            tags = self.node_tags
            for i in order:
                writer.add_node(
                    osmium.osm.mutable.Node(
                        id=node_id[i],
                        version=1,
                        location=osmium.osm.Location(lon[i] / COORD_SCALE, lat[i] / COORD_SCALE),
                        tags=canton_form(tags.get(i + 1, {})),
                    )
                )
            for i, (refs, t) in enumerate(self.ways):
                writer.add_way(osmium.osm.mutable.Way(
                    id=way_base + i + 1, version=1, nodes=[node_id[r - 1] for r in refs], tags=canton_form(t)))
            for i, (members, t) in enumerate(self.relations):
                mem = [(typ, way_base + ref, role) for typ, ref, role in members]
                writer.add_relation(
                    osmium.osm.mutable.Relation(id=rel_base + i + 1, version=1, members=mem, tags=canton_form(t))
                )
        finally:
            writer.close()
        tmp.replace(path)


# Einheitliche Form des Kantonskürzels in Namen (Review BaseCamp: „Gossau (Sg)“ neben „Gossau Sg“).
# BFS-Gemeindenamen (swissBOUNDARIES3D, Adressverzeichnis COM_NAME) schreiben „Gossau (SG)“, die
# Ortschaften (PLZ-Verzeichnis), swissNAMES3D-Siedlungen und ÖV-Haltestellen „Gossau SG“. Gewählt ist
# die Form ohne Klammern, weil sie in den angezeigten Namen (Orte, Haltestellen) schon überwiegt.
_KT = "AG|AI|AR|BE|BL|BS|FR|GE|GL|GR|JU|LU|NE|NW|OW|SG|SH|SO|SZ|TG|TI|UR|VD|VS|ZG|ZH"
_RX_KT = re.compile(r" \((" + _KT + r")\)(?=$|[,\s])")
CANTON_FORM_KEYS = ("name", "alt_name", "official_name", "is_in:city", "addr:city", "addr:place",
                    "swisstopo:name", "swisstopo:amtlicher_name")


def canton_form(tags: dict) -> dict:
    out = None
    for k in CANTON_FORM_KEYS:
        v = tags.get(k)
        if v and "(" in v:
            w = _RX_KT.sub(r" \1", v)
            if w != v:
                if out is None:
                    out = dict(tags)
                out[k] = w
    return out if out is not None else tags


def _round(v: float) -> int:
    return int(round(v * COORD_SCALE))


def _clean(tags: dict) -> dict[str, str]:
    out = {}
    for k, v in tags.items():
        if v is None:
            continue
        s = str(v).strip()
        if s == "" or s == "k_W" or s == "nan":
            continue
        out[k] = s
    return out


def _parts(geom, kinds):
    if geom is None or geom.is_empty:
        return
    gt = geom.geom_type
    if gt in kinds:
        yield geom
    elif gt.startswith("Multi") or gt == "GeometryCollection":
        for g in geom.geoms:
            yield from _parts(g, kinds)


def _chunks(refs: list[int]):
    if len(refs) <= MAX_WAY_NODES:
        yield refs
        return
    start = 0
    while start < len(refs) - 1:
        end = min(start + MAX_WAY_NODES, len(refs))
        yield refs[start:end]
        start = end - 1
