"""Encoder für Garmin-IMG mit eingebetteten Rasterkacheln (NT/GMP-Format).

Aufbau nach der Analyse von „Topo Schweiz v3 Rastermap“ (siehe docs/raster/raster-img.md):
- Jede GMP-Subdatei enthält TRE, RGN und LBL.
- Die JPEG-Kacheln liegen hintereinander in LBL-Abschnitt 29, LBL28 ist die Offset-Tabelle.
- Jede Kachel ist ein erweitertes Polygon Typ 0x10613 in RGN2 mit Zusatzdaten
  (0xE0, Länge, Bildindex, N/E/S/W als 32-Bit-Koordinaten, JPEG-Grösse).
- Ein Abdeckungspolygon 0x10d01 je Subdivision (wie im Original).

Alle Optionen, die Hypothesen zum Gerätverhalten betreffen, sind im Dataclass `GmpOptions` schaltbar.
"""
from __future__ import annotations

import datetime as _dt
import math
import struct
from dataclasses import dataclass, field

import huffman as H
from keygen import tre_key

# Grössengrenzen einer GMP (GPSMAP 67). Liegt eine GMP ausserhalb, bietet das Gerät die ganze IMG nicht an.
# - GMP_MAX: Gerätetest 5, eine GMP mit 16,9 MB.
# - GMP_MIN: Gerätetest 8: jede IMG mit einer GMP unter 327 680 Byte fehlte (auch einzelne graue Kacheln),
#   jede IMG mit GMPs ab 479 075 Byte erschien. Die Referenzkarte hat keine GMP unter 700 KB.
#   build_gmp füllt kleinere GMPs am Ende mit Nullbytes auf (nicht referenziert).
GMP_MAX = 16 * 2**20
GMP_MIN = 512 * 2**10


def check_gmp_size(name: str, size: int) -> None:
    """Bricht ab, wenn eine GMP ausserhalb von GMP_MIN … GMP_MAX liegt."""
    if size < GMP_MIN:
        raise ValueError(f"{name}: GMP {size} Byte < {GMP_MIN} (Gerätetest 8: IMG wird dann nicht angeboten)")
    if size >= GMP_MAX:
        raise ValueError(f"{name}: GMP {size} Byte ≥ 16 MiB (Gerätetest 5: IMG wird dann nicht angeboten)")

# --------------------------------------------------------------------------- Hilfsfunktionen


def deg2mu(deg: float) -> int:
    """Grad -> 24-Bit-Karteneinheiten (gerundet)."""
    return int(math.floor(deg * (1 << 24) / 360.0 + 0.5))


def mu2deg(mu: int) -> float:
    return mu * 360.0 / (1 << 24)


def p24(v: int) -> bytes:
    return (v & 0xFFFFFF).to_bytes(3, "little")


def common_header(length: int, kind: str, when: _dt.datetime) -> bytes:
    """Gemeinsamer 21-Byte-Kopf aller Subdatei-Header (Länge, 'GARMIN XXX', 1, 0, Datum)."""
    return (struct.pack("<H", length) + f"GARMIN {kind}".encode("ascii")
            + bytes([1, 0]) + struct.pack("<HBBBBB", when.year, when.month, when.day,
                                          when.hour, when.minute, when.second))


class BitWriter:
    def __init__(self):
        self.bits: list[int] = []

    def put(self, val: int, n: int):
        for i in range(n):
            self.bits.append((val >> i) & 1)

    def bytes(self) -> bytes:
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            b = 0
            for j, bit in enumerate(self.bits[i:i + 8]):
                b |= bit << j
            out.append(b)
        return bytes(out)


def _base_for(nbits: int) -> int:
    """Kleinster Basiswert, dessen Bitbreite (ohne Vorzeichen) >= nbits ist."""
    for base in range(16):
        w = 2 + (base if base <= 9 else 2 * base - 9)
        if w >= nbits:
            return base
    raise ValueError("Delta zu gross")


def _width(base: int) -> int:
    return 2 + (base if base <= 9 else 2 * base - 9)


def encode_bitstream(deltas: list[tuple[int, int]]) -> bytes:
    """Klassischer (nicht Huffman-) Koordinaten-Bitstream für erweiterte Typen.

    Liefert Basisbyte + Bitdaten. Vorzeichen: 'same sign' wenn möglich, sonst mit Vorzeichenbit.
    Escape-Werte (nur Vorzeichenbit gesetzt) werden vermieden, indem die Breite gross genug gewählt wird.
    """
    xs = [d[0] for d in deltas]
    ys = [d[1] for d in deltas]

    def sign_info(vals):
        nz = [v for v in vals if v != 0]
        if all(v >= 0 for v in nz):
            return True, False
        if all(v <= 0 for v in nz):
            return True, True
        return False, False

    xsame, xneg = sign_info(xs)
    ysame, yneg = sign_info(ys)

    def need(vals, same):
        m = max(abs(v) for v in vals) if vals else 0
        if same:
            return max(1, m.bit_length())
        # mit Vorzeichen: Wert v in n Bits (Zweierkomplement), -2^(n-1) ist Escape -> meiden
        return max(1, m.bit_length()) + 1

    nx = need(xs, xsame)
    ny = need(ys, ysame)
    bx = _base_for(nx - (0 if xsame else 1))
    by = _base_for(ny - (0 if ysame else 1))
    wx = _width(bx) + (0 if xsame else 1)
    wy = _width(by) + (0 if ysame else 1)
    bw = BitWriter()
    bw.put(1 if xsame else 0, 1)
    if xsame:
        bw.put(1 if xneg else 0, 1)
    bw.put(1 if ysame else 0, 1)
    if ysame:
        bw.put(1 if yneg else 0, 1)
    bw.put(0, 1)  # Version-2-Extrabit: aus
    for dx, dy in deltas:
        bw.put(abs(dx) if xsame else dx & ((1 << wx) - 1), wx)
        bw.put(abs(dy) if ysame else dy & ((1 << wy) - 1), wy)
    return bytes([bx | (by << 4)]) + bw.bytes()


def varlen(n: int) -> bytes:
    """Variable Länge wie in GPXSee readVUInt32 (1 Byte für < 128)."""
    if n < 0x80:
        return bytes([(n << 1) | 1])
    if n < 0x4000:
        return struct.pack("<H", (n << 2) | 2)
    raise ValueError("zu lang")


def byte_size(v: int) -> int:
    n = 1
    while v >= (1 << (8 * n)):
        n += 1
    return n


# --------------------------------------------------------------------------- Datenmodell


@dataclass
class Tile:
    jpeg: bytes
    north: float
    east: float
    south: float
    west: float
    col: int = 0
    row: int = 0


@dataclass
class GmpOptions:
    levels: tuple[int, ...] = (18, 19, 20, 21, 22, 23, 24)  # oben -> unten; oberste = leer/vererbt
    raster_levels: int = 4            # Rasterpolygone in den untersten N Ebenen (Original: 4 = bits 21..24)
    raster_min_level: int = 0         # ... aber erst ab dieser Ebene (von unten gezählt); für grobe Serien
    coverage_polygon: bool = True     # 0x10d01 je Subdivision (Original: ja)
    coverage_levels: int = 6          # in den untersten N Ebenen (Original: bits 19..24)
    split_bottom: bool = True         # unterste Ebene in zwei Subdivisions (links/rechts), wie Original
    tile_labels: bool = True          # Label je Rasterpolygon (Original: ja)
    index_bytes: int | None = None    # None = byteSize(n-1) wie Original/GPXSee; 2 = GarminImg-Verhalten
    rgn_flag_blocks: str = "orig"     # "orig" (wie Original), "zero" (mkgmap-artig)
    draw_priority: int = 0x1F
    copyright: tuple[str, ...] = ("©swisstopo", "Swiss Map Raster 25, swisstopo OGD",
                                  "Helvetopo, inoffiziell")
    tile_label: str = "©swisstopo"
    hdr_comment1: tuple[str, ...] = ("©swisstopo, Daten unter OGD (opendata.swiss).",
                                     "Inoffizielle Karte, erstellt mit Helvetopo.")
    hdr_comment2: tuple[str, ...] = ("Swiss Map Raster 25", "©swisstopo")
    huffman: bool = False             # Labels (LBL-Codierung 11) und Koordinaten Huffman-kodiert wie Original
    orig_extras: bool = False         # TRE9 (aus dem Schlüssel abgeleitet) und LBL16 (2 Nullbytes) wie Original
    unique_tile_labels: bool = False  # eigenes Label je Bild (Original: 110 verschiedene Labels je GMP)
    coverage_bottom_last: bool = False  # unterste Ebene: 0x10d01 nur in der letzten Subdivision (wie Original)
    bottom_last_full: bool = False    # unterste Ebene: letzte Subdivision spannt die ganze GMP (wie Original)
    placeholder_bits: tuple[int, ...] = ()  # mit level_tiles: auf diesen Ebenen Raster-Polygone ohne Bild
                                            # (grobe Serie, siehe release.py „zwei Serien“)
    zoom_from_bits: bool = False      # Ebenennummer = 24 − bits statt Index (Übersichts-GMP passt dann zu den
                                      # Nummern der Detail-GMPs, siehe overview.py)
    overview_bits: tuple[int, ...] = ()  # mit level_tiles: Ebenen mit Übersichtsbildern (grosse Fläche); die
                                         # übrigen Ebenen nehmen nur die Ausdehnung der Nicht-Übersichtsbilder


# --------------------------------------------------------------------------- GMP


def tre9_bytes(key: bytes) -> bytes:
    """TRE9 (5 Byte) wie im Original, nibbleweise aus Schlüsselbytes 8-11 (an allen 516 Kacheln geprüft)."""
    def nib(b, lo, hi):
        return (((b >> 4) + hi) & 0xF) << 4 | ((b & 0xF) + lo) & 0xF
    return bytes([nib(key[8], 3, 7), nib(key[9], 5, 0), nib(key[10], 1, 0), key[11], key[8]])


class _Subdiv:
    def __init__(self, level_idx: int, bits: int, tiles: list[Tile], west, south, east, north):
        self.level_idx = level_idx
        self.bits = bits
        self.shift = 24 - bits
        self.tiles = tiles
        w, s, e, n = deg2mu(west), deg2mu(south), deg2mu(east), deg2mu(north)
        self.clon = (w + e) // 2
        self.clat = (s + n) // 2
        self.hw = ((max(self.clon - w, e - self.clon) + (1 << self.shift) - 1) >> self.shift) + 1
        self.hh = ((max(self.clat - s, n - self.clat) + (1 << self.shift) - 1) >> self.shift) + 1
        self.bounds = (west, south, east, north)
        self.number = 0
        self.next = 0
        self.last_sibling = False
        self.rgn2 = b""

    def rel(self, lon_mu: int, lat_mu: int) -> tuple[int, int]:
        half = (1 << self.shift) >> 1
        return (lon_mu - self.clon + half) >> self.shift, (lat_mu - self.clat + half) >> self.shift


def _rect_poly(sd: _Subdiv, west, south, east, north) -> tuple[int, int, list]:
    """Rechteck SW -> SE -> NE -> NW (geschlossen implizit), relativ zur Subdivision."""
    pts = [sd.rel(deg2mu(west), deg2mu(south)), sd.rel(deg2mu(east), deg2mu(south)),
           sd.rel(deg2mu(east), deg2mu(north)), sd.rel(deg2mu(west), deg2mu(north))]
    for x, y in pts:
        if not (-0x8000 <= x <= 0x7FFF and -0x8000 <= y <= 0x7FFF):
            raise ValueError("Delta ausserhalb int16")
    deltas = [(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]) for i in range(1, len(pts))]
    return pts[0][0], pts[0][1], deltas


def build_gmp(map_number: int, tiles: list[Tile], opt: GmpOptions | None = None,
              when: _dt.datetime | None = None, level_tiles: dict[int, list[Tile]] | None = None) -> bytes:
    """level_tiles (optional): je Ebene (bits) eigene Bilder, z. B. SMR25 auf 24 und SMR50 auf 23 in einer
    GMP. Dann ist `tiles` die Gesamtliste aller Bilder; raster_levels/raster_min_level werden ignoriert."""
    opt = opt or GmpOptions()
    when = when or _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    if not tiles:
        raise ValueError("keine Kacheln")
    west = min(t.west for t in tiles)
    east = max(t.east for t in tiles)
    south = min(t.south for t in tiles)
    north = max(t.north for t in tiles)
    # Ausdehnung der Detail-Ebenen (ohne Übersichtsbilder), sonst wie die ganze GMP
    main = [t for b, lst in (level_tiles or {}).items() if b not in opt.overview_bits for t in lst] \
        if (level_tiles and opt.overview_bits) else tiles
    mw, ms, me, mn = (min(t.west for t in main), min(t.south for t in main), max(t.east for t in main),
                      max(t.north for t in main))

    # ---- LBL1 (Codierung 9, cp1252; oder 11 = Huffman)
    def tile_text(i: int) -> str:
        return f"{opt.tile_label} {i + 1}" if opt.unique_tile_labels else opt.tile_label

    label_strings = [""] + list(opt.copyright) + (
        [tile_text(i) for i in range(len(tiles))] if opt.tile_labels else [])
    text_codes = None
    if opt.huffman:
        f: dict[int, int] = {}
        for st_ in label_strings:
            for sym in H.text_symbols(st_.encode("cp1252"), 8):
                f[sym] = f.get(sym, 0) + 1
        text_codes = H.canonical_codes(H.pad_freq(f, range(1, 256)))
    lbl1 = bytearray()
    label_cache: dict[str, int] = {}

    def label(s: str) -> int:
        if s in label_cache:
            return label_cache[s]
        off = len(lbl1)
        raw = s.encode("cp1252")
        lbl1.extend(H.encode_text(text_codes, 8, raw) if opt.huffman else raw + b"\x00")
        label_cache[s] = off
        return off

    label("")

    copyright_offs = [label(s) for s in opt.copyright]
    tile_lbl = label(opt.tile_label) if opt.tile_labels else 0

    # ---- LBL28/29
    lbl28 = bytearray()
    lbl29 = bytearray()
    for t in tiles:
        lbl28 += struct.pack("<I", len(lbl29))
        lbl29 += t.jpeg
    idx_bytes = opt.index_bytes or byte_size(len(tiles) - 1)

    # ---- Ebenen und Subdivisions
    nlev = len(opt.levels)
    subdivs_per_level: list[list[_Subdiv]] = []
    for li, bits in enumerate(opt.levels):
        level_from_bottom = nlev - 1 - li
        lt = level_tiles.get(bits, []) if level_tiles is not None else tiles
        if li == 0:
            sds = [_Subdiv(li, bits, [], west, south, east, north)]
        elif li == nlev - 1 and opt.split_bottom and len({t.col for t in lt}) > 1:
            cols = sorted({t.col for t in lt})
            mid = cols[len(cols) // 2]
            left = [t for t in lt if t.col < mid]
            right = [t for t in lt if t.col >= mid]
            sds = []
            for pi, part in enumerate((left, right)):
                if opt.bottom_last_full and pi == 1:
                    # Original: rechte Subdivision mit Mitte und Ausdehnung der ganzen Kachel
                    sds.append(_Subdiv(li, bits, part, mw, ms, me, mn))
                    continue
                sds.append(_Subdiv(li, bits, part, min(t.west for t in part), min(t.south for t in part),
                                   max(t.east for t in part), max(t.north for t in part)))
        else:
            if bits in opt.overview_bits:
                sds = [_Subdiv(li, bits, list(lt), west, south, east, north)]
            else:
                sds = [_Subdiv(li, bits, list(lt), mw, ms, me, mn)]
        for sd in sds:
            if level_tiles is not None:
                sd.has_raster = li > 0 and bool(sd.tiles)
            else:
                sd.has_raster = li > 0 and opt.raster_min_level <= level_from_bottom < opt.raster_levels
            sd.has_cov = li > 0 and opt.coverage_polygon and level_from_bottom < opt.coverage_levels
        if opt.coverage_bottom_last and li == nlev - 1:
            for sd in sds[:-1]:
                sd.has_cov = False
        sds[-1].last_sibling = True
        subdivs_per_level.append(sds)
    n = 1
    for sds in subdivs_per_level:
        for sd in sds:
            sd.number = n
            n += 1
    for li in range(nlev - 1):
        first_child = subdivs_per_level[li + 1][0].number
        for sd in subdivs_per_level[li]:
            sd.next = first_child  # alle Ebenen haben je 1 Subdivision ausser der untersten

    # ---- RGN2-Inhalte je Subdivision (erst sammeln, dann kodieren)
    type_maxlevel: dict[int, int] = {}
    polys: list = []  # (sd, Typ/Subtyp, dx, dy, Deltas, Rest)
    for li, sds in enumerate(subdivs_per_level):
        if li == 0:
            continue
        level_from_bottom = nlev - 1 - li
        for sd in sds:
            if sd.has_cov:
                w, s, e, nn = sd.bounds
                dx, dy, dl = _rect_poly(sd, w, s, e, nn)
                polys.append((sd, bytes([0x0D, 0x01]), dx, dy, dl, b""))
                type_maxlevel[0x10D01] = max(type_maxlevel.get(0x10D01, 0), level_from_bottom)
            if sd.has_raster:
                for t in sd.tiles:
                    idx = tiles.index(t)
                    dx, dy, dl = _rect_poly(sd, t.west, t.south, t.east, t.north)
                    rest = p24(label(tile_text(idx))) if opt.tile_labels else b""
                    if sd.bits in opt.placeholder_bits:
                        # Raster-Polygon ohne Bild (ohne Zusatzdaten), wie die grobe Serie der Referenzkarte
                        # auf ihren feinen Ebenen
                        polys.append((sd, bytes([0x06, 0x13 | (0x20 if opt.tile_labels else 0)]), dx, dy, dl, rest))
                        continue
                    st = 0x13 | 0x80 | (0x20 if opt.tile_labels else 0)
                    extra = (idx.to_bytes(idx_bytes, "little")
                             + struct.pack("<iiiiI", deg2mu(t.north) << 8, deg2mu(t.east) << 8,
                                           deg2mu(t.south) << 8, deg2mu(t.west) << 8, len(t.jpeg)))
                    rest += bytes([0xE0]) + varlen(len(extra)) + extra
                    polys.append((sd, bytes([0x06, st]), dx, dy, dl, rest))
                type_maxlevel[0x10613] = max(type_maxlevel.get(0x10613, 0), level_from_bottom)

    coord_codes = None
    rgn5 = b""
    if opt.huffman:
        f = {}
        for _, _, _, _, dl, _ in polys:
            for d in dl:
                for v in d:
                    f[abs(v)] = f.get(abs(v), 0) + 1
        coord_codes = H.canonical_codes(H.pad_freq(f, range(1, 256)))
        t_text = H.build_table(text_codes, 8, 6)
        t_coord = H.build_table(coord_codes, 32, 4)
        rgn5 = H.write_vuint(len(t_text)) + t_text + H.write_vuint(len(t_coord)) + t_coord
    out_by_sd: dict[int, bytearray] = {}
    for sd, ts, dx, dy, dl, rest in polys:
        bs = H.encode_deltas(coord_codes, dl) if opt.huffman else encode_bitstream(dl)
        out_by_sd.setdefault(id(sd), bytearray()).extend(
            ts + struct.pack("<hh", dx, dy) + varlen(len(bs)) + bs + rest)
    for sds in subdivs_per_level:
        for sd in sds:
            sd.rgn2 = bytes(out_by_sd.get(id(sd), b""))

    rgn2 = bytearray()
    tre7 = bytearray()
    for li, sds in enumerate(subdivs_per_level):
        for sd in sds:
            if li == 0:
                continue  # vererbte oberste Ebene hat keinen TRE7-Eintrag
            tre7 += struct.pack("<I", len(rgn2))
            rgn2 += sd.rgn2
    tre7 += struct.pack("<I", len(rgn2))  # Endeintrag

    # ---- TRE1/TRE2/TRE3/TRE8
    tre1 = bytearray()
    for li, sds in enumerate(subdivs_per_level):
        zoom = 24 - opt.levels[li] if opt.zoom_from_bits else nlev - 1 - li
        tre1 += bytes([zoom | (0x80 if li == 0 else 0), opt.levels[li]]) + struct.pack("<H", len(sds))
    tre2 = bytearray()
    for li, sds in enumerate(subdivs_per_level):
        for sd in sds:
            rec = p24(0) + bytes([0]) + p24(sd.clon) + p24(sd.clat)
            rec += struct.pack("<HH", (sd.hw & 0x7FFF) | (0x8000 if sd.last_sibling else 0), sd.hh & 0x7FFF)
            if li < nlev - 1:
                rec += struct.pack("<H", sd.next)
            tre2 += rec
    tre2 += struct.pack("<I", 0)
    tre3 = b"".join(p24(o) for o in copyright_offs)
    tre8 = bytearray()
    for t in sorted(type_maxlevel):
        tre8 += bytes([(t >> 8) & 0xFF, type_maxlevel[t], t & 0xFF])

    lbl12 = b"Western European Sort\x00"
    lbl21 = bytes(0x300) if opt.huffman else b""
    lbl16 = bytes(2) if opt.orig_extras else b""
    tre9 = tre9_bytes(tre_key(map_number, 0x111)) if opt.orig_extras else b""

    # ---- Layout
    GMP_HL, TRE_HL, RGN_HL, LBL_HL = 0x35, 0x111, 0x7D, 0x210
    c1 = b"".join(s.encode("cp1252") + b"\x00" for s in opt.hdr_comment1)
    c2 = b"".join(s.encode("cp1252") + b"\x00" for s in opt.hdr_comment2)
    tre_off = GMP_HL + len(c1)
    rgn_off = tre_off + TRE_HL + len(c2)
    lbl_off = rgn_off + RGN_HL
    pos = lbl_off + LBL_HL
    sec = {}
    for name, data in (("tre3", tre3), ("tre2", tre2), ("tre1", tre1), ("tre8", tre8), ("tre7", tre7),
                       ("rgn2", rgn2), ("rgn5", rgn5), ("lbl12", lbl12), ("lbl1", lbl1), ("lbl16", lbl16),
                       ("lbl21", lbl21), ("lbl28", lbl28),
                       ("lbl29", lbl29), ("tre9", tre9)):
        sec[name] = (pos, len(data), data)
        pos += len(data)
    end = pos

    # ---- GMP-Header
    gmp = bytearray(common_header(GMP_HL, "GMP", when))
    gmp += b"\x00" * 4 + struct.pack("<6I", tre_off, rgn_off, lbl_off, 0, 0, 0) + b"\x00" * 4
    assert len(gmp) == GMP_HL

    # ---- TRE-Header
    t = bytearray(TRE_HL)
    t[0:21] = common_header(TRE_HL, "TRE", when)
    t[0x15:0x18] = p24(deg2mu(north)); t[0x18:0x1B] = p24(deg2mu(east))
    t[0x1B:0x1E] = p24(deg2mu(south)); t[0x1E:0x21] = p24(deg2mu(west))
    struct.pack_into("<II", t, 0x21, sec["tre1"][0], sec["tre1"][1])
    struct.pack_into("<II", t, 0x29, sec["tre2"][0], sec["tre2"][1])
    struct.pack_into("<IIH", t, 0x31, sec["tre3"][0], sec["tre3"][1], 3)
    t[0x3F] = 0x01
    t[0x40:0x43] = p24(opt.draw_priority)
    t[0x43:0x4A] = bytes([0x01, 0x08, 0x24, 0x00, 0x01, 0x00, 0x00])
    after_tre8 = sec["tre8"][0] + sec["tre8"][1]
    struct.pack_into("<IIH", t, 0x4A, after_tre8, 0, 2)
    struct.pack_into("<IIH", t, 0x58, after_tre8, 0, 2)
    struct.pack_into("<IIH", t, 0x66, after_tre8, 0, 3)
    struct.pack_into("<I", t, 0x74, map_number)
    struct.pack_into("<IIHI", t, 0x7C, sec["tre7"][0], sec["tre7"][1], 4, 1)
    struct.pack_into("<IIHHHH", t, 0x8A, sec["tre8"][0], sec["tre8"][1], 3, 0, len(type_maxlevel), 0)
    t[0x9A:0xAA] = tre_key(map_number, TRE_HL)
    if opt.orig_extras:
        struct.pack_into("<IIH", t, 0xAE, sec["tre9"][0], 5, 5)
    else:
        struct.pack_into("<IIH", t, 0xAE, end, 0, 0)
    struct.pack_into("<IIH", t, 0xBC, sec["rgn2"][0], 0, 1)
    struct.pack_into("<I", t, 0xCF, map_number)
    struct.pack_into("<I", t, 0xD5, sec["rgn2"][0])
    struct.pack_into("<I", t, 0xE3, sec["rgn2"][0])

    # ---- RGN-Header
    r = bytearray(RGN_HL)
    r[0:21] = common_header(RGN_HL, "RGN", when)
    r2o, r2s = sec["rgn2"][0], sec["rgn2"][1]
    after_rgn2 = r2o + r2s
    struct.pack_into("<IIII", r, 0x15, r2o, 0, r2o, r2s)
    if opt.rgn_flag_blocks == "orig":
        r[0x25:0x39] = bytes.fromhex("0200000000000000ff000020fdfc030000000000")
        r[0x41:0x55] = bytes.fromhex("00000000000000003f000020fd0f000000000000")
        r[0x5D:0x71] = bytes.fromhex("0000000000000000ff0f00203ff7ff0000000000")
    struct.pack_into("<II", r, 0x39, after_rgn2, 0)
    struct.pack_into("<II", r, 0x55, after_rgn2, 0)
    struct.pack_into("<III", r, 0x71, sec["rgn5"][0], sec["rgn5"][1], 0xE5 if opt.huffman else 0)

    # ---- LBL-Header (Feldlage wie Original, 0x210 Byte)
    L = bytearray(LBL_HL)
    L[0:21] = common_header(LBL_HL, "LBL", when)
    l1o, l1s = sec["lbl1"][0], sec["lbl1"][1]
    empty = l1o + l1s
    struct.pack_into("<IIBB", L, 0x15, l1o, l1s, 0, 11 if opt.huffman else 9)
    recs = {  # Abschnitt: (Position, Recordgrösse, Füllbytes nach rec)
        2: (0x1F, 0, b""), 3: (0x2D, 6, b"\x01\x00\x00\x00"), 4: (0x3B, 7, b"\x01\x00\x00\x80"),
        5: (0x49, 0, b""), 7: (0x64, 0, b""), 8: (0x72, 3, b""), 9: (0x80, 6, b""),
        10: (0x8E, 4, b"\x02\x00\x00\x00"), 11: (0x9C, 3, b""), 13: (0xB8, 0, b""), 14: (0xC4, 0, b""),
        15: (0xD0, 0x2E, b"\x01\x00\x00\x00"), 16: (0xDE, 0, b""), 17: (0xEC, 0, b""), 18: (0xFA, 0, b""),
        19: (0x108, 0xC, b""), 20: (0x116, 3, b""), 21: (0x124, 3, b""), 22: (0x132, 0, b""),
        23: (0x140, 0, b""), 24: (0x14E, 0, b""), 25: (0x15A, 0, b""), 26: (0x168, 0, b""),
        27: (0x176, 0, b""), 30: (0x19A, 0, b""), 31: (0x1A6, 0, b""), 32: (0x1B2, 0, b""),
        33: (0x1BE, 0, b""), 34: (0x1CA, 0, b""), 35: (0x1D8, 0, b""), 36: (0x1E6, 0, b""),
        37: (0x1F2, 0, b""), 38: (0x200, 0x15, b""),
    }
    for k, (p, rs, pad) in recs.items():
        struct.pack_into("<IIH", L, p, empty, 0, rs)
        L[p + 10:p + 10 + len(pad)] = pad
    struct.pack_into("<II", L, 0x57, empty, 0)  # LBL6 (ohne rec)
    L[0x5F] = 0
    struct.pack_into("<H", L, 0xAA, 1252)
    L[0xAC:0xB0] = bytes.fromhex("07000280")
    struct.pack_into("<II", L, 0xB0, sec["lbl12"][0], sec["lbl12"][1])
    if opt.huffman:
        struct.pack_into("<IIH", L, 0x124, sec["lbl21"][0], sec["lbl21"][1], 3)
    if opt.orig_extras:
        struct.pack_into("<II", L, 0xDE, sec["lbl16"][0], 2)
        for pos in (0x1B2, 0x1BE, 0x200):
            struct.pack_into("<I", L, pos, sec["tre9"][0])
    struct.pack_into("<IIH", L, 0x184, sec["lbl28"][0], sec["lbl28"][1], 4)
    struct.pack_into("<II", L, 0x192, sec["lbl29"][0], sec["lbl29"][1])

    out = bytearray(gmp + c1 + t + c2 + r + L)
    assert len(out) == sec["tre3"][0], (len(out), sec["tre3"][0])
    for name in ("tre3", "tre2", "tre1", "tre8", "tre7", "rgn2", "rgn5", "lbl12", "lbl1", "lbl16", "lbl21",
                 "lbl28", "lbl29", "tre9"):
        out += sec[name][2]
    assert len(out) == end
    if len(out) < GMP_MIN:                  # Auffüllen, siehe GMP_MIN
        out += bytes(GMP_MIN - len(out))
    return bytes(out)


def gmp_draw_priority(data: bytes) -> int:
    """Draw-Priority (TRE-Header 0x40) einer GMP."""
    tre = struct.unpack_from("<I", data, 0x19)[0]
    return data[tre + 0x40] | data[tre + 0x41] << 8 | data[tre + 0x42] << 16


def set_gmp_draw_priority(data: bytes, prio: int) -> bytes:
    """GMP mit geänderter Draw-Priority (nur das Headerfeld, sonst bytegleich)."""
    tre = struct.unpack_from("<I", data, 0x19)[0]
    if gmp_draw_priority(data) == prio:
        return data
    b = bytearray(data)
    b[tre + 0x40:tre + 0x43] = p24(prio)
    return bytes(b)


def patch_gmp_file(path: str, prio: int) -> bool:
    """Draw-Priority einer GMP-Datei an Ort und Stelle setzen; True, wenn geändert."""
    with open(path, "r+b") as f:
        head = f.read(0x40)
        tre = struct.unpack_from("<I", head, 0x19)[0]
        f.seek(tre + 0x40)
        if f.read(3) == p24(prio):
            return False
        f.seek(tre + 0x40)
        f.write(p24(prio))
    return True


# --------------------------------------------------------------------------- IMG-Container und MPS


def build_mps(family: int, product: int, series: str, maps: list[tuple[int, str]], orig_style: bool = False) -> bytes:
    """GMAPPROM.MPS wie im Original: ein F-Record, je Karte ein L-Record."""
    def rec(t: str, body: bytes) -> bytes:
        return t.encode() + struct.pack("<H", len(body)) + body

    s = series.encode("cp1252") + b"\x00"
    out = rec("F", struct.pack("<HH", product, family) + s)
    for number, desc in maps:
        body = (struct.pack("<HHI", product, family, 0 if orig_style else number) + s + desc.encode("cp1252") + b"\x00"
                + b"\x00" + struct.pack("<II", number, 0))
        out += rec("L", body)
    return out


def img_header(subfiles: list[tuple[str, str, int]], description: str,
               when: _dt.datetime | None = None, block_exp: tuple[int, int] = (9, 7)) -> tuple[bytes, int]:
    """Kopf (Header + FAT, auf Blockgrenze aufgefüllt) eines IMG-Containers.

    subfiles: (Name 8 Zeichen, Erweiterung 3 Zeichen, Grösse). Die Daten folgen in dieser Reihenfolge,
    jede Subdatei auf die Blockgrösse aufgefüllt. Liefert (Kopf, Blockgrösse).
    """
    when = when or _dt.datetime.now()
    bs = 1 << (block_exp[0] + block_exp[1])
    fat_start = 0x1000
    # FAT-Einträge zählen (pro 240 Blöcke ein Eintrag)
    nentries = 1 + sum(max(1, math.ceil(math.ceil(d / bs) / 240)) for _, _, d in subfiles)
    hdr_bytes = fat_start + nentries * 512
    hdr_blocks = math.ceil(hdr_bytes / bs)
    total_blocks = hdr_blocks + sum(math.ceil(d / bs) for _, _, d in subfiles)
    if total_blocks > 0xFFFF:
        raise ValueError("zu viele Blöcke")

    h = bytearray(0x200)
    h[0x0A] = when.month
    h[0x0B] = when.year - 1900
    h[0x10:0x17] = b"DSKIMG\x00"
    h[0x17] = 0x02
    end_sector = (total_blocks * bs + 511) // 512
    heads, sectors, cyls = 0x100, 0x20, 0x400
    struct.pack_into("<HHH", h, 0x18, sectors, heads, cyls)
    struct.pack_into("<HBBBBB", h, 0x39, when.year, when.month, when.day, when.hour, when.minute,
                     when.second)
    h[0x40] = fat_start // 0x200
    h[0x41:0x48] = b"GARMIN\x00"
    d = description.encode("cp1252")[:50].ljust(50, b" ")
    h[0x49:0x5D] = d[:20]
    struct.pack_into("<HH", h, 0x5D, heads, sectors)
    h[0x61], h[0x62] = block_exp
    struct.pack_into("<H", h, 0x63, min(total_blocks, 0xFFFF))
    h[0x65:0x83] = d[20:50]
    # Partitionstabelle (wie mkgmap)
    lba = end_sector - 1
    hh = (lba // sectors) % heads
    ss = (lba % sectors) + 1
    cc = lba // (sectors * heads)
    h[0x1BE:0x1CE] = bytes([0, 0, 1, 0, 0, hh, (ss | ((cc >> 2) & 0xC0)) & 0xFF, cc & 0xFF]) + struct.pack(
        "<II", 0, end_sector)
    h[0x1FE:0x200] = b"\x55\xAA"

    out = bytearray(h) + bytearray(fat_start - 0x200)

    def fat_entry(name: bytes, ext: bytes, size: int, part: int, blocks: list[int]) -> bytes:
        e = bytearray(512)
        e[0] = 1
        e[1:9] = name.ljust(8, b" ")[:8]
        e[9:12] = ext.ljust(3, b" ")[:3]
        struct.pack_into("<IH", e, 12, size, part)
        bl = blocks + [0xFFFF] * (240 - len(blocks))
        struct.pack_into("<240H", e, 32, *bl)
        return bytes(e)

    out += fat_entry(b"", b"", hdr_blocks * bs, 3, list(range(hdr_blocks)))
    nb = hdr_blocks
    for name, ext, size in subfiles:
        cnt = math.ceil(size / bs)
        blocks = list(range(nb, nb + cnt))
        nb += cnt
        for part, i in enumerate(range(0, max(cnt, 1), 240)):
            out += fat_entry(name.encode(), ext.encode(), size if part == 0 else 0, part,
                             blocks[i:i + 240])
    out += b"\x00" * (hdr_blocks * bs - len(out))
    return bytes(out), bs


def build_img(subfiles: list[tuple[str, str, bytes]], description: str,
              when: _dt.datetime | None = None, block_exp: tuple[int, int] = (9, 7)) -> bytes:
    """Garmin-IMG-Container (DSKIMG) im Speicher. subfiles: (Name 8 Zeichen, Erweiterung 3 Zeichen, Daten)."""
    for n, e, d in subfiles:
        if e == "GMP":
            check_gmp_size(f"{n}.{e}", len(d))
    hdr, bs = img_header([(n, e, len(d)) for n, e, d in subfiles], description, when, block_exp)
    out = bytearray(hdr)
    for _, _, data in subfiles:
        out += data
        out += b"\x00" * ((-len(data)) % bs)
    return bytes(out)


def write_img(path: str, subfiles: list[tuple[str, str, str | bytes]], description: str,
              when: _dt.datetime | None = None, block_exp: tuple[int, int] = (9, 7)) -> int:
    """Wie build_img, aber streamend auf Platte. Daten als bytes oder als Pfad einer Datei."""
    import os
    sizes = [(n, e, len(d) if isinstance(d, (bytes, bytearray)) else os.path.getsize(d)) for n, e, d in subfiles]
    for n, e, size in sizes:
        if e == "GMP":
            check_gmp_size(f"{n}.{e}", size)
    hdr, bs = img_header(sizes, description, when, block_exp)
    with open(path + ".part", "wb") as f:
        f.write(hdr)
        for (_, _, d), (_, _, size) in zip(subfiles, sizes):
            if isinstance(d, (bytes, bytearray)):
                f.write(d)
            else:
                with open(d, "rb") as g:
                    while chunk := g.read(1 << 22):
                        f.write(chunk)
            f.write(b"\x00" * ((-size) % bs))
        total = f.tell()
    os.replace(path + ".part", path)
    return total
