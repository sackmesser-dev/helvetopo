"""Garmin-Huffman-Tabellen (RGN5) für Labels (LBL-Codierung 11) und Koordinaten-Bitstreams.

Tabellenformat und Dekodierung nach GPXSee (src/map/IMG/huffmantable.cpp, huffmanstream.h).
Ein RGN5-Abschnitt ist eine Folge von Records: variable Länge (wie GPXSee readVUInt32) + Tabelle.
Record 0 = Texttabelle, Record (info>>1 & 0xF) - 1 = Koordinatentabelle (Info-Feld RGN+0x79).

Tabelle:
  Byte 0: aclBits (Bit 0-3), 0x10 = kanonisches Huffman mit Symboltabelle
  Byte 1: symBits (längster Code), Byte 2: Anzahl Suchtabellen-Einträge, Byte 3: Bits je Symbol
  Byte 4..: Feld variabler Länge (vs(Byte 4)), dessen Länge = Indexbreite
  Suchtabelle: je Eintrag erster Code (linksbündig auf symBits, symBytes) + Codelänge (1) + Basisindex
  ACL-Tabelle: 2^aclBits Einträge à (symbolBytes + 1): direkt (Bit 0 = 1: Länge, Symbol) oder Bereich
  Symboltabelle: Symbole à symbolBits, LSB-zuerst gepackt
Bitstreams werden MSB-zuerst gelesen.
"""
from __future__ import annotations

import heapq
import struct


def bs(v: int) -> int:
    return (v + 7) >> 3


def vs(b0: int) -> int:
    return (4, 1, 2, 1, 3, 1, 2, 1)[b0 & 7]


def read_vuint(buf: bytes, pos: int) -> tuple[int, int]:
    """Variable Länge wie GPXSee SubFile::readVUInt32 (Länge in Bits 0-2 des ersten Bytes)."""
    b0 = buf[pos]
    if b0 & 1:
        return b0 >> 1, pos + 1
    if b0 & 2:
        return struct.unpack_from("<H", buf, pos)[0] >> 2, pos + 2
    if b0 & 4:
        return int.from_bytes(buf[pos:pos + 3], "little") >> 3, pos + 3
    return struct.unpack_from("<I", buf, pos)[0] >> 3, pos + 4


def write_vuint(v: int) -> bytes:
    if v < 0x80:
        return bytes([(v << 1) | 1])
    if v < 0x4000:
        return struct.pack("<H", (v << 2) | 2)
    if v < 0x200000:
        return ((v << 3) | 4).to_bytes(3, "little")
    return struct.pack("<I", v << 3)


def split_records(rgn5: bytes) -> list[bytes]:
    out, p = [], 0
    while p < len(rgn5):
        n, p = read_vuint(rgn5, p)
        out.append(rgn5[p:p + n])
        p += n
    return out


class Table:
    def __init__(self, buf: bytes):
        self.buf = buf
        self.acl_bits = buf[0] & 0x0F
        self.huffman = bool(buf[0] & 0x10)
        self.sym_bits = buf[1]
        self.sym_bytes = bs(self.sym_bits)
        self.bsrch_entries = buf[2]
        self.symbol_bits = buf[3]
        self.symbol_bytes = bs(self.symbol_bits)
        self.acl_entry_bytes = self.symbol_bytes + 1
        self.index_bytes = vs(buf[4])
        self.bsrch_entry_bytes = self.sym_bytes + self.index_bytes + 1
        self.bsrch = 4 + self.index_bytes
        self.acl = self.bsrch + self.bsrch_entry_bytes * self.bsrch_entries
        self.htab = self.acl + (self.acl_entry_bytes << self.acl_bits)

    def _rv(self, p: int, n: int) -> int:
        return int.from_bytes(self.buf[p:p + n], "little")

    def symbol(self, data: int) -> tuple[int, int]:
        """data = nächste 32 Bit (MSB-bündig). Liefert (Symbol, Codelänge)."""
        b = self.buf
        if not self.acl_bits:
            lo, hi = 0, self.bsrch_entries - 1
        else:
            tp = self.acl + self.acl_entry_bytes * (data >> (32 - self.acl_bits))
            if b[tp] & 1:
                return self._rv(tp + 1, self.symbol_bytes), b[tp] >> 1
            lo, hi = b[tp] >> 1, b[tp + 1]
        tp = self.bsrch + lo * self.bsrch_entry_bytes
        d = data >> (32 - self.sym_bits)
        while lo < hi:
            prev = tp
            m = (lo + 1 + hi) >> 1
            tp = self.bsrch + m * self.bsrch_entry_bytes
            nd = self._rv(tp, self.sym_bytes)
            if d < nd:
                tp = prev
                hi = m - 1
            elif d > nd:
                lo = m
            else:
                lo = hi = m
        i = self._rv(tp, self.sym_bytes)
        size = b[tp + self.sym_bytes]
        if not self.huffman:
            return self._rv(tp + self.sym_bytes + 1, self.symbol_bytes), size
        bi = self._rv(tp + self.sym_bytes + 1, self.index_bytes)
        ci = (d - i) >> (self.sym_bits - size)
        si = (ci + bi) * self.symbol_bits
        v = int.from_bytes(b[self.htab + (si >> 3):self.htab + (si >> 3) + 5], "little") >> (si & 7)
        return v & ((1 << self.symbol_bits) - 1), size


class BitReader:
    """MSB-zuerst."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def avail(self) -> int:
        return len(self.data) * 8 - self.pos

    def read(self, n: int) -> int:
        v = 0
        for _ in range(n):
            v = (v << 1) | ((self.data[self.pos >> 3] >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return v

    def peek32(self) -> int:
        v = 0
        for i in range(32):
            p = self.pos + i
            bit = (self.data[p >> 3] >> (7 - (p & 7))) & 1 if p < len(self.data) * 8 else 0
            v = (v << 1) | bit
        return v

    def symbol(self, t: Table) -> int:
        if self.avail() <= 0:
            raise EOFError
        s, n = t.symbol(self.peek32())
        if n > self.avail():
            raise EOFError
        self.pos += n
        return s


def decode_text(t: Table, data: bytes) -> bytes:
    r = BitReader(data)
    out = bytearray()
    while True:
        s = r.symbol(t)
        for _ in range(t.symbol_bits >> 3):
            out.append(s & 0xFF)
            if s & 0xFF == 0:
                return bytes(out)
            s >>= 8


def decode_deltas(t: Table, data: bytes, line: bool = False) -> list[tuple[int, int]]:
    r = BitReader(data)

    def sign():
        if r.read(1):
            return -1 if r.read(1) else 1
        return 0

    lon_s, lat_s = (sign(), sign()) if line else (0, 0)
    if r.read(1):
        raise ValueError("Extrabit gesetzt")

    def delta(sg):
        s = r.symbol(t)
        if s and not sg:
            sg = -1 if r.read(1) else 1
        return sg * s

    out = []
    try:
        while True:
            dx = delta(lon_s)
            dy = delta(lat_s)
            if not (dx | dy):
                break
            out.append((dx, dy))
    except EOFError:
        pass
    if r.avail() >= t.sym_bits:
        raise ValueError(f"Restbits {r.avail()}")
    return out


# --------------------------------------------------------------------------- Encoder


def canonical_codes(freq: dict[int, int], max_len: int = 16) -> dict[int, tuple[int, int]]:
    """Kanonische Huffman-Codes: Symbol -> (Code, Länge). Codelängen begrenzt auf max_len.

    Damit Füllbits (0) am Streamende nie einen ganzen Code bilden, sollte der längste Code >= 8 Bit
    sein; dafür sorgt pad_freq()."""
    syms = sorted(freq)
    if len(syms) == 1:
        lengths = {syms[0]: 1}
    else:
        heap = [(freq[s], i, [s]) for i, s in enumerate(syms)]
        heapq.heapify(heap)
        depth = {s: 0 for s in syms}
        cnt = len(syms)
        while len(heap) > 1:
            f1, _, a = heapq.heappop(heap)
            f2, _, b = heapq.heappop(heap)
            for s in a + b:
                depth[s] += 1
            heapq.heappush(heap, (f1 + f2, cnt, a + b))
            cnt += 1
        lengths = depth
        # einfache Längenbegrenzung
        while max(lengths.values()) > max_len:
            for s in lengths:
                if lengths[s] > max_len:
                    lengths[s] = max_len
            # Kraft-Ungleichung reparieren
            while sum(2 ** -l for l in lengths.values()) > 1:
                s = max((s for s in lengths if lengths[s] < max_len), key=lambda s: lengths[s])
                lengths[s] += 1
    # Garmin-Anordnung: längste Codes zuerst, Code 0...0 ist der längste (Nullbits als Füllung sicher)
    S = max(lengths.values())
    order = sorted(syms, key=lambda s: (-lengths[s], s))
    codes = {}
    val = 0
    for s in order:
        L = lengths[s]
        step = 1 << (S - L)
        val = (val + step - 1) // step * step
        codes[s] = (val >> (S - L), L)
        val += step
    assert val <= (1 << S)
    return codes


def pad_freq(freq: dict[int, int], dummies) -> dict[int, int]:
    """Ergänzt seltene Platzhaltersymbole, bis der Baum mindestens 8 Bit tief ist."""
    f = dict(freq)
    for d in dummies:
        if len(f) >= 300:
            break
        f.setdefault(d, 1)
    return f


def build_table(codes: dict[int, tuple[int, int]], symbol_bits: int, acl_bits: int = 0) -> bytes:
    """Serialisiert kanonische Codes im Garmin-Tabellenformat (huffman=1)."""
    sym_bits = max(L for _, L in codes.values())
    order = sorted(codes, key=lambda s: codes[s][0] << (sym_bits - codes[s][1]))
    # Suchtabelle: ein Eintrag je Codelänge (erster Code, linksbündig auf sym_bits)
    entries = []
    for i, s in enumerate(order):
        code, L = codes[s]
        if not entries or entries[-1][1] != L:
            entries.append((code << (sym_bits - L), L, i))
    n_sym = len(order)
    index_bytes = 1 if n_sym < 0x80 else (2 if n_sym < 0x4000 else 3)
    # Feld variabler Länge mit Anzahl Symbole, Codierung wie write_vuint
    if index_bytes == 1:
        idx_field = bytes([(n_sym << 1) | 1])
    elif index_bytes == 2:
        idx_field = struct.pack("<H", (n_sym << 2) | 2)
    else:
        idx_field = ((n_sym << 3) | 4).to_bytes(3, "little")
    sym_bytes = bs(sym_bits)
    symbol_bytes = bs(symbol_bits)
    out = bytearray([0x10 | acl_bits, sym_bits, len(entries), symbol_bits]) + idx_field
    for first, L, bi in entries:
        out += first.to_bytes(sym_bytes, "little") + bytes([L]) + bi.to_bytes(index_bytes, "little")
    # ACL-Tabelle
    nacl = 1 << acl_bits
    if acl_bits == 0:
        out += bytes(symbol_bytes + 1)  # Platzhalter (wird von GPXSee übersprungen)
    else:
        for a in range(nacl):
            prefix_lo = a << (sym_bits - acl_bits)
            prefix_hi = ((a + 1) << (sym_bits - acl_bits)) - 1
            # direkter Treffer: ein Code mit Länge <= acl_bits deckt den ganzen Präfix ab
            hit = None
            for s in order:
                code, L = codes[s]
                if L <= acl_bits and (code << (sym_bits - L)) <= prefix_lo and \
                        ((code + 1) << (sym_bits - L)) - 1 >= prefix_hi:
                    hit = s
                    break
            if hit is not None:
                out += bytes([(codes[hit][1] << 1) | 1]) + hit.to_bytes(symbol_bytes, "little")
            else:
                lo = max(i for i, e in enumerate(entries) if e[0] <= prefix_lo)
                hi = max(i for i, e in enumerate(entries) if e[0] <= prefix_hi)
                out += bytes([lo << 1, hi]) + bytes(symbol_bytes - 1)
    # Symboltabelle, LSB-zuerst gepackt
    acc, nbits, packed = 0, 0, bytearray()
    for s in order:
        acc |= s << nbits
        nbits += symbol_bits
        while nbits >= 8:
            packed.append(acc & 0xFF)
            acc >>= 8
            nbits -= 8
    if nbits:
        packed.append(acc & 0xFF)
    out += packed + bytes(4)  # Reserve, damit Leser 4-5 Byte lesen dürfen
    return bytes(out)


class BitWriter:
    def __init__(self):
        self.bits: list[int] = []

    def put(self, v: int, n: int):
        for i in range(n - 1, -1, -1):
            self.bits.append((v >> i) & 1)

    def bytes(self) -> bytes:
        out = bytearray()
        for i in range(0, len(self.bits), 8):
            chunk = self.bits[i:i + 8] + [0] * (8 - len(self.bits[i:i + 8]))
            v = 0
            for bit in chunk:
                v = (v << 1) | bit
            out.append(v)
        return bytes(out)


def encode_text(codes, symbol_bits: int, s: bytes) -> bytes:
    """s ohne Nullbyte; Symbole sind Gruppen von symbol_bits/8 Zeichen (Little Endian)."""
    k = symbol_bits >> 3
    data = s + b"\x00"
    bw = BitWriter()
    for i in range(0, len(data), k):
        chunk = data[i:i + k]
        sym = int.from_bytes(chunk.ljust(k, b"\x00"), "little")
        code, L = codes[sym]
        bw.put(code, L)
    return bw.bytes()


def text_symbols(s: bytes, symbol_bits: int) -> list[int]:
    k = symbol_bits >> 3
    data = s + b"\x00"
    return [int.from_bytes(data[i:i + k].ljust(k, b"\x00"), "little") for i in range(0, len(data), k)]


def encode_deltas(codes, deltas: list[tuple[int, int]]) -> bytes:
    """Polygon-Bitstream (ohne globale Vorzeichen): Extrabit 0, je Delta Symbol |d| + Vorzeichenbit."""
    bw = BitWriter()
    bw.put(0, 1)
    for dx, dy in deltas:
        for d in (dx, dy):
            code, L = codes[abs(d)]
            bw.put(code, L)
            if d:
                bw.put(1 if d < 0 else 0, 1)
    return bw.bytes()
