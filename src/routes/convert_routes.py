#!/usr/bin/env python3
"""Wanderwege (swissTLM3D) und SchweizMobil-Routen (ASTRA/SchweizMobil) -> OSM-XML/PBF.

Liest die GeoPackages direkt mit sqlite3 (keine GDAL-Bindings nötig), rechnet
LV95 (EPSG:2056) mit PROJ (pyproj, falls vorhanden) oder mit den swisstopo-
Näherungsformeln nach WGS84, schneidet auf die Bounding Box zu und schreibt
Linien mit eigenen Tags (Schema: docs/vektor/routen.md). Dazu kommen die ÖV-Haltestellen aus
swissTLM3D als Punkte (Bahn, Tram, Bus, Schiff, übrige Bahnen).

Aufruf:
    python3 -I src/routes/convert_routes.py \
        --downloads $HELVETOPO_DATA \
        --bbox 9.00,47.20,9.50,47.50 --out work/routes/routes.osm
Danach (macht build.sh): osmium cat routes.osm -o routes.osm.pbf
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import struct
import sys
from pathlib import Path
from xml.sax.saxutils import quoteattr

# --------------------------------------------------------------------------
# Quellen
# --------------------------------------------------------------------------

TLM_WANDERWEGE = "swisstlm3d-wanderwege/SWISSTLM3D_WANDERWEGE.gpkg"

# (Schlüssel, Datei, OSM route=, Netzpräfix für network=)
ROUTE_SOURCES = [
    ("wanderland", "astra-wanderland/wanderland_2056.gpkg", "hiking", "wn"),
    ("veloland", "astra-veloland/veloland_2056.gpkg", "bicycle", "cn"),
    ("mountainbikeland", "astra-mountainbikeland/mountainbikeland_2056.gpkg", "mtb", "mtb"),
    ("skatingland", "astra-skatingland/skatingland_2056.gpkg", "inline_skates", "in"),
    ("kanuland", "schweizmobil-kanuland/kanu.gpkg", "canoe", "wn"),
]

WANDERWEG_CLASS = {
    "Wanderweg": "wanderweg",
    "Bergwanderweg": "bergwanderweg",
    "Alpinwanderweg": "alpinwanderweg",
}
# Entsprechung in OSM (nur als Zusatzinfo, die Darstellung nutzt ch:wanderweg)
SAC_SCALE = {
    "wanderweg": "hiking",
    "bergwanderweg": "mountain_hiking",
    "alpinwanderweg": "alpine_hiking",
}
# Alle ÖV-Haltestellen (swissTLM3D tlm_oev_haltestelle). Bahnhöfe kommen als „bahn“ mit, damit die
# Suche vollständig ist; ihren sichtbaren Namen zeigt die Basiskarte. Tramhalte sind in swissTLM3D
# ebenfalls „Haltestelle Bahn“; sie werden über das Gleis erkannt (tlm_oev_eisenbahn, verkehrsmittel=Tram).
TLM = "swisstlm3d/SWISSTLM3D_2026_LV95_LN02.gpkg"
OEV_KIND = {"Haltestelle Bus": "bus", "Haltestelle Schiff": "schiff", "Uebrige Bahnen": "uebrige_bahn"}
TRAM_RADIUS_M = 25.0
AERIAL_STATIONS = {"Luftseilbahn", "Gondelbahn", "Sesselbahn", "Skilift", "Standseilbahn"}
AERIAL_HALT_M = 80.0  # Linienende mit Haltestelle „Uebrige Bahnen“ in diesem Abstand: keine eigene Station
STOP_MERGE_M = 150.0  # Haltekanten mit gleichem Namen und Art in diesem Abstand = eine Haltestelle
NETWORK_LEVEL = {"national": "n", "regional": "r", "local": "l", "handicap": "l"}

# --------------------------------------------------------------------------
# Koordinaten
# --------------------------------------------------------------------------


def _make_transformer():
    try:
        from pyproj import Transformer  # type: ignore

        t = Transformer.from_crs(2056, 4326, always_xy=True)
        return (lambda e, n: t.transform(e, n)), "PROJ (pyproj)"
    except Exception:
        return lv95_to_wgs84_approx, "swisstopo-Näherungsformel (~1 m)"


def lv95_to_wgs84_approx(e: float, n: float) -> tuple[float, float]:
    """swisstopo-Näherungsformeln LV95 -> WGS84 (Genauigkeit ca. 1 m)."""
    y = (e - 2600000.0) / 1e6
    x = (n - 1200000.0) / 1e6
    lon = (2.6779094 + 4.728982 * y + 0.791484 * y * x + 0.1306 * y * x * x
           - 0.0436 * y ** 3)
    lat = (16.9023892 + 3.238272 * x - 0.270978 * y * y - 0.002528 * x * x
           - 0.0447 * y * y * x - 0.0140 * x ** 3)
    return lon * 100.0 / 36.0, lat * 100.0 / 36.0


def wgs84_to_lv95_approx(lon: float, lat: float) -> tuple[float, float]:
    """Für die Vorselektion per R-Tree (grosszügig gepuffert)."""
    p = (lat * 3600.0 - 169028.66) / 10000.0
    l = (lon * 3600.0 - 26782.5) / 10000.0
    e = (2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p
         - 44.54 * l ** 3)
    n = (1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p
         - 194.56 * l * l * p + 119.79 * p ** 3)
    return e, n


# --------------------------------------------------------------------------
# GeoPackage-Geometrie (GPKG-Header + WKB/ISO-WKB, 2D/3D)
# --------------------------------------------------------------------------


def parse_gpkg_geom(blob: bytes) -> list[list[tuple[float, float]]]:
    if blob is None or blob[:2] != b"GP":
        return []
    flags = blob[3]
    env = (flags >> 1) & 0x07
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    if flags & 0x10:  # leere Geometrie
        return []
    off = 8 + env_len
    parts: list[list[tuple[float, float]]] = []
    _parse_wkb(blob, off, parts)
    return parts


def _parse_wkb(b: bytes, off: int, parts: list) -> int:
    bo = "<" if b[off] == 1 else ">"
    (gtype,) = struct.unpack_from(bo + "I", b, off + 1)
    off += 5
    has_z = has_m = False
    if gtype & 0x80000000:
        has_z = True
    if gtype & 0x40000000:
        has_m = True
    gtype &= 0x0FFFFFFF
    if gtype >= 3000:
        has_z = has_m = True
        gtype -= 3000
    elif gtype >= 2000:
        has_m = True
        gtype -= 2000
    elif gtype >= 1000:
        has_z = True
        gtype -= 1000
    dim = 2 + has_z + has_m
    if gtype == 1:  # Point
        vals = struct.unpack_from(bo + "d" * dim, b, off)
        parts.append([(vals[0], vals[1])])
        return off + 8 * dim
    if gtype == 2:  # LineString
        (npts,) = struct.unpack_from(bo + "I", b, off)
        off += 4
        vals = struct.unpack_from(bo + "d" * (npts * dim), b, off)
        off += 8 * npts * dim
        parts.append([(vals[i], vals[i + 1]) for i in range(0, len(vals), dim)])
        return off
    if gtype in (4, 5, 7):  # MultiPoint, MultiLineString, GeometryCollection
        (ngeom,) = struct.unpack_from(bo + "I", b, off)
        off += 4
        for _ in range(ngeom):
            off = _parse_wkb(b, off, parts)
        return off
    raise ValueError(f"Geometrietyp {gtype} nicht unterstützt")


# --------------------------------------------------------------------------
# Clipping (Liang-Barsky je Segment, Linien werden an der Box aufgetrennt)
# --------------------------------------------------------------------------


def clip_line(pts, xmin, ymin, xmax, ymax):
    out: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0
        ok = True
        for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
            if p == 0:
                if q < 0:
                    ok = False
                    break
            else:
                r = q / p
                if p < 0:
                    if r > t1:
                        ok = False
                        break
                    t0 = max(t0, r)
                else:
                    if r < t0:
                        ok = False
                        break
                    t1 = min(t1, r)
        if not ok:
            if len(cur) > 1:
                out.append(cur)
            cur = []
            continue
        a = (x0 + t0 * dx, y0 + t0 * dy)
        c = (x0 + t1 * dx, y0 + t1 * dy)
        if not cur:
            cur = [a]
        elif cur[-1] != a:
            if len(cur) > 1:
                out.append(cur)
            cur = [a]
        cur.append(c)
        if t1 < 1.0:
            if len(cur) > 1:
                out.append(cur)
            cur = []
    if len(cur) > 1:
        out.append(cur)
    return out


# --------------------------------------------------------------------------
# OSM-Ausgabe
# --------------------------------------------------------------------------


class OsmWriter:
    """Sammelt Knoten (gemeinsam genutzt bei gleicher Koordinate) und Wege."""

    def __init__(self) -> None:
        self.nodes: dict[tuple[int, int], int] = {}
        self.ways: list[tuple[list[int], dict[str, str]]] = []
        self.pois: list[tuple[int, int, dict[str, str]]] = []

    def poi(self, lon: float, lat: float, tags) -> None:
        """Eigener Knoten mit Tags (nicht mit Wegknoten geteilt)."""
        self.pois.append((round(lon * 1e7), round(lat * 1e7), tags))

    def node(self, lon: float, lat: float) -> int:
        key = (round(lon * 1e7), round(lat * 1e7))
        nid = self.nodes.get(key)
        if nid is None:
            nid = len(self.nodes) + 1
            self.nodes[key] = nid
        return nid

    def way(self, coords, tags) -> None:
        refs = []
        for lon, lat in coords:
            nid = self.node(lon, lat)
            if not refs or refs[-1] != nid:
                refs.append(nid)
        if len(refs) > 1:
            self.ways.append((refs, tags))

    def write(self, path: Path, bbox) -> None:
        with path.open("w", encoding="utf-8") as f:
            f.write("<?xml version='1.0' encoding='UTF-8'?>\n")
            f.write("<osm version='0.6' generator='Helvetopo convert_routes.py'>\n")
            f.write(
                f"  <bounds minlon='{bbox[0]}' minlat='{bbox[1]}' maxlon='{bbox[2]}' maxlat='{bbox[3]}'/>\n"
            )
            for (lon7, lat7), nid in sorted(self.nodes.items(), key=lambda kv: kv[1]):
                f.write(
                    f"  <node id='{nid}' version='1' lat='{lat7 / 1e7:.7f}' lon='{lon7 / 1e7:.7f}'/>\n"
                )
            for j, (lon7, lat7, tags) in enumerate(self.pois, start=len(self.nodes) + 1):
                f.write(f"  <node id='{j}' version='1' lat='{lat7 / 1e7:.7f}' lon='{lon7 / 1e7:.7f}'>\n")
                for k, v in sorted(tags.items()):
                    f.write(f"    <tag k={quoteattr(k)} v={quoteattr(str(v))}/>\n")
                f.write("  </node>\n")
            for i, (refs, tags) in enumerate(self.ways, start=1):
                f.write(f"  <way id='{i}' version='1'>\n")
                for r in refs:
                    f.write(f"    <nd ref='{r}'/>\n")
                for k, v in sorted(tags.items()):
                    f.write(f"    <tag k={quoteattr(k)} v={quoteattr(str(v))}/>\n")
                f.write("  </way>\n")
            f.write("</osm>\n")


# --------------------------------------------------------------------------
# Konvertierung
# --------------------------------------------------------------------------


def rtree_ids(con, table, geomcol, lv95box):
    e0, n0, e1, n1 = lv95box
    rt = f"rtree_{table}_{geomcol}"
    return [
        r[0]
        for r in con.execute(
            f'SELECT id FROM "{rt}" WHERE maxx >= ? AND minx <= ? AND maxy >= ? AND miny <= ?',
            (e0, e1, n0, n1),
        )
    ]


def lv95_box(bbox, buffer_m=2000.0):
    corners = [wgs84_to_lv95_approx(x, y) for x in (bbox[0], bbox[2]) for y in (bbox[1], bbox[3])]
    es = [c[0] for c in corners]
    ns = [c[1] for c in corners]
    return (min(es) - buffer_m, min(ns) - buffer_m, max(es) + buffer_m, max(ns) + buffer_m)


def emit(writer, parts_lv95, tags, tf, bbox, stats, key):
    for part in parts_lv95:
        wgs = [tf(e, n) for e, n in part]
        for piece in clip_line(wgs, *bbox):
            writer.way(piece, dict(tags))
            stats[key] = stats.get(key, 0) + 1


def convert_wanderwege(path, writer, tf, bbox, stats):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    ids = rtree_ids(con, "tlm_strassen_strasse", "geom", lv95_box(bbox))
    q = (
        "SELECT geom, wanderwege, objektart, kunstbaute, uuid FROM tlm_strassen_strasse "
        "WHERE id = ?"
    )
    for fid in ids:
        geom, ww, objektart, kunstbaute, uuid = con.execute(q, (fid,)).fetchone()
        cls = WANDERWEG_CLASS.get(ww)
        if not cls:
            continue
        tags = {
            "ch:wanderweg": cls,
            "sac_scale": SAC_SCALE[cls],
            "ch:tlm_uuid": (uuid or "").strip("{}"),
            "source": "swisstopo swissTLM3D Wanderwege",
        }
        if objektart == "Markierte Spur":
            tags["ch:markierte_spur"] = "yes"
        if kunstbaute in ("Tunnel", "Unterfuehrung", "Unterfuehrung mit Treppe", "Galerie"):
            tags["tunnel"] = "yes"
        elif kunstbaute and kunstbaute.startswith(("Bruecke", "Gedeckte Bruecke", "Steg")):
            tags["bridge"] = "yes"
        emit(writer, parse_gpkg_geom(geom), tags, tf, bbox, stats, f"wanderweg/{cls}")
    con.close()


def _seg_dist(p, a, b):
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _is_tram_stop(con, e, n):
    """Tramhalt: im Umkreis von TRAM_RADIUS_M liegen nur Gleise mit verkehrsmittel=Tram."""
    r = TRAM_RADIUS_M
    kinds = set()
    for fid in rtree_ids(con, "tlm_oev_eisenbahn", "geom", (e - r, n - r, e + r, n + r)):
        geom, vm = con.execute("SELECT geom, verkehrsmittel FROM tlm_oev_eisenbahn WHERE id = ?", (fid,)).fetchone()
        for part in parse_gpkg_geom(geom):
            if any(_seg_dist((e, n), a, b) <= r for a, b in zip(part, part[1:])):
                kinds.add(vm)
                break
    return kinds == {"Tram"}


def _line_ends_z(blob):
    """Erster und letzter Punkt (E, N, Z oder None) einer (Multi-)LineString-Geometrie."""
    flags = blob[3]
    off = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(flags >> 1) & 0x07]
    pts = []

    def walk(off):
        bo = "<" if blob[off] == 1 else ">"
        (gt,) = struct.unpack_from(bo + "I", blob, off + 1)
        off += 5
        base = gt & 0x0FFFFFFF
        z = bool(gt & 0x80000000) or base // 1000 in (1, 3)
        m = bool(gt & 0x40000000) or base // 1000 in (2, 3)
        gt = base % 1000
        dim = 2 + z + m
        (cnt,) = struct.unpack_from(bo + "I", blob, off)
        off += 4
        if gt == 2:
            v = struct.unpack_from(bo + "d" * (cnt * dim), blob, off)
            pts.extend([v[i:i + dim] for i in (0, (cnt - 1) * dim)] if cnt else [])
            return off + 8 * cnt * dim
        for _ in range(cnt):
            off = walk(off)
        return off

    walk(off)
    if not pts:
        return []
    ends = [pts[0], pts[-1]]
    return [(p[0], p[1], p[2] if len(p) > 2 else None) for p in ends]


def convert_haltestellen(path, writer, tf, bbox, stats):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    ids = rtree_ids(con, "tlm_oev_haltestelle", "geom", lv95_box(bbox, buffer_m=0.0))
    q = "SELECT geom, objektart, name, dienststellen_nummer, uuid FROM tlm_oev_haltestelle WHERE id = ?"
    groups: dict[tuple, list] = {}  # (Art, Name) -> [[Summe E, Summe N, Anzahl, Tags], ...]
    for fid in ids:
        geom, oa, name, uic, uuid = con.execute(q, (fid,)).fetchone()
        parts = parse_gpkg_geom(geom)
        if not parts:
            continue
        e, n = parts[0][0]
        kind = OEV_KIND.get(oa)
        if oa == "Haltestelle Bahn":
            kind = "tram" if _is_tram_stop(con, e, n) else "bahn"
        if kind is None:
            continue
        lon, lat = tf(e, n)
        if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
            continue
        main = (name or "").split("|")[0].strip()
        # Haltekanten derselben Haltestelle (je Richtung ein Punkt) zu einem Punkt zusammenfassen
        cands = groups.setdefault((kind, main), [])
        for g in cands if main else ():
            if math.hypot(g[0] / g[2] - e, g[1] / g[2] - n) <= STOP_MERGE_M:
                g[0] += e
                g[1] += n
                g[2] += 1
                break
        else:
            tags = {"ch:oev": kind, "source": "swisstopo swissTLM3D", "ch:tlm_uuid": (uuid or "").strip("{}")}
            if main:
                tags["name"] = main
            if uic:
                tags["uic_ref"] = str(int(uic))
            cands.append([e, n, 1, tags])
    # Berg- und Talstationen von Seilbahnen und Skiliften (Linienenden, Höhe aus Z)
    halts = [(g[0] / g[2], g[1] / g[2]) for (k, _), cs in groups.items() if k == "uebrige_bahn" for g in cs]
    qa = "SELECT geom, objektart, name, ausser_betrieb, uuid FROM tlm_oev_uebrige_bahn WHERE id = ?"
    for fid in rtree_ids(con, "tlm_oev_uebrige_bahn", "geom", lv95_box(bbox, buffer_m=0.0)):
        geom, oa, name, ausser, uuid = con.execute(qa, (fid,)).fetchone()
        if oa not in AERIAL_STATIONS or ausser == "Wahr" or geom is None:
            continue
        ends = _line_ends_z(geom)
        if len(ends) != 2:
            continue
        lower = 0 if (ends[0][2] or 0) <= (ends[1][2] or 0) else 1
        main = (name or "").split("|")[0].strip()
        for k, (e, n, z) in enumerate(ends):
            if any(math.hypot(he - e, hn - n) <= AERIAL_HALT_M for he, hn in halts):
                continue
            lon, lat = tf(e, n)
            if not (bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]):
                continue
            role = "Talstation" if k == lower else "Bergstation"
            tags = {"ch:oev": "seilbahn", "aerialway": "station", "name": f"{main} {role}" if main else role,
                    "ch:objektart": oa, "source": "swisstopo swissTLM3D", "ch:tlm_uuid": (uuid or "").strip("{}")}
            if z is not None:
                tags["ele"] = str(int(round(z)))
            groups.setdefault(("seilbahn", tags["name"]), []).append([e, n, 1, tags])
    for (kind, _), cands in groups.items():
        for se, sn, cnt, tags in cands:
            writer.poi(*tf(se / cnt, sn / cnt), tags)
            stats[f"haltestelle/{kind}"] = stats.get(f"haltestelle/{kind}", 0) + 1


def _edge_keys(parts):
    keys = set()
    for part in parts:
        for a, b in zip(part, part[1:]):
            ka = (round(a[0], 1), round(a[1], 1))
            kb = (round(b[0], 1), round(b[1], 1))
            keys.add((ka, kb) if ka <= kb else (kb, ka))
    return keys


def _subtract_edges(parts, keys):
    """Teile von Rückweg-Geometrien, die nicht schon im Hinweg liegen."""
    out = []
    for part in parts:
        cur = []
        for a, b in zip(part, part[1:]):
            ka = (round(a[0], 1), round(a[1], 1))
            kb = (round(b[0], 1), round(b[1], 1))
            k = (ka, kb) if ka <= kb else (kb, ka)
            if k in keys:
                if len(cur) > 1:
                    out.append(cur)
                cur = []
            else:
                if not cur:
                    cur = [a]
                cur.append(b)
        if len(cur) > 1:
            out.append(cur)
    return out


def convert_routes(key, path, osm_route, net_suffix, writer, tf, bbox, stats):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    ids = rtree_ids(con, "Route", "geom", lv95_box(bbox))
    rows = []
    for fid in ids:
        rows.append(
            con.execute(
                "SELECT fid, geom, NrR, NameR, Typ_TR, Richtung, Abwicklung, LVRoute_ID "
                "FROM Route WHERE fid = ?",
                (fid,),
            ).fetchone()
        )
    con.close()
    # Hin- und Rückweg derselben Route: Rückweg nur, wo er abweicht.
    by_route: dict = {}
    for r in rows:
        by_route.setdefault((r[2], r[7]), []).append(r)
    for (_nr, _rid), group in sorted(by_route.items(), key=lambda kv: str(kv[0])):
        group.sort(key=lambda r: 0 if r[6] != "Rückweg" else 1)
        seen: set = set()
        for fid, geom, nr, name, typ, richtung, abwicklung, lvid in group:
            parts = parse_gpkg_geom(geom)
            if seen:
                parts = _subtract_edges(parts, seen)
            seen |= _edge_keys(parts)
            level = NETWORK_LEVEL.get(typ or "", "l")
            tags = {
                "ch:route": key,
                "ch:network": typ or "unknown",
                "route": osm_route,
                "network": level + net_suffix,
                "ref": nr or "",
                "name": name or "",
                "ch:lvroute_id": str(lvid or ""),
            }
            if abwicklung == "Rückweg":
                tags["ch:abwicklung"] = "rueckweg"
            if richtung and richtung.startswith("nur"):
                tags["ch:richtung"] = "einseitig"
            if typ == "handicap":
                tags["wheelchair"] = "yes"
            tags = {k: v for k, v in tags.items() if v != ""}
            emit(writer, parts, tags, tf, bbox, stats, f"{key}/{typ}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--downloads", required=True, type=Path)
    ap.add_argument("--bbox", default="9.00,47.20,9.50,47.50", help="minlon,minlat,maxlon,maxlat (WGS84)")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--skip", default="", help="kommagetrennt, z. B. kanuland,wanderwege,haltestellen")
    args = ap.parse_args(argv)

    bbox = tuple(float(v) for v in args.bbox.split(","))
    skip = {s for s in args.skip.split(",") if s}
    tf, tf_name = _make_transformer()
    print(f"Koordinatentransformation: {tf_name}", file=sys.stderr)

    writer = OsmWriter()
    stats: dict[str, int] = {}
    if "wanderwege" not in skip:
        convert_wanderwege(args.downloads / TLM_WANDERWEGE, writer, tf, bbox, stats)
    for key, rel, osm_route, suffix in ROUTE_SOURCES:
        if key in skip:
            continue
        p = args.downloads / rel
        if not p.exists():
            print(f"WARNUNG: {p} fehlt, {key} übersprungen", file=sys.stderr)
            continue
        convert_routes(key, p, osm_route, suffix, writer, tf, bbox, stats)

    if "haltestellen" not in skip:
        convert_haltestellen(args.downloads / TLM, writer, tf, bbox, stats)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer.write(args.out, bbox)
    for k in sorted(stats):
        print(f"{k:40s} {stats[k]:7d} {'Punkte' if k.startswith('haltestelle/') else 'Linien'}", file=sys.stderr)
    print(f"{len(writer.nodes) + len(writer.pois)} Knoten, {len(writer.ways)} Wege -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
