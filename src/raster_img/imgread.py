"""Lesender Zugriff auf Garmin-IMG-Container (DSKIMG/GARMIN) und NT-GMP-Subdateien.

Nur zur Analyse. Liest nie die ganze Datei, sondern gezielt Blöcke.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field


@dataclass
class FatEntry:
    name: str
    ext: str
    size: int
    part: int
    blocks: list[int]


@dataclass
class Subfile:
    name: str
    ext: str
    size: int
    blocks: list[int] = field(default_factory=list)


class ImgFile:
    def __init__(self, path: str):
        self.path = path
        self.f = open(path, "rb")
        hdr = self.f.read(0x600)
        self.xor = hdr[0]
        if self.xor:
            hdr = bytes(b ^ self.xor for b in hdr)
        self.hdr = hdr
        if hdr[0x10:0x16] != b"DSKIMG" or hdr[0x41:0x47] != b"GARMIN":
            raise ValueError("kein Garmin-IMG")
        e1, e2 = hdr[0x61], hdr[0x62]
        self.blocksize = 1 << (e1 + e2)
        self.fat_offset = hdr[0x40] * 0x200 if hdr[0x40] else 0x600
        self.subfiles: dict[str, Subfile] = {}
        self.fat: list[FatEntry] = []
        self._read_fat()

    def _read(self, off: int, n: int) -> bytes:
        self.f.seek(off)
        d = self.f.read(n)
        if self.xor:
            d = bytes(b ^ self.xor for b in d)
        return d

    def _read_fat(self):
        off = self.fat_offset
        # erster Eintrag (Header-Pseudodatei) bestimmt die Grösse des reservierten Bereichs
        first = self._read(off, 512)
        limit = struct.unpack_from("<I", first, 12)[0] if first[0] == 1 else 0x600 + 512 * 64
        while off + 512 <= limit:
            e = self._read(off, 512)
            off += 512
            if len(e) < 512:
                break
            if e[0] != 1:
                continue
            name = e[1:9].decode("latin1")
            ext = e[9:12].decode("latin1")
            size, part = struct.unpack_from("<IH", e, 12)
            blocks = [b for b in struct.unpack_from("<240H", e, 32) if b != 0xFFFF]
            fe = FatEntry(name, ext, size, part, blocks)
            self.fat.append(fe)
            if name.strip() == "" and ext.strip() == "":
                continue  # Header-Pseudodatei
            key = f"{name.strip()}.{ext.strip()}"
            sf = self.subfiles.get(key)
            if sf is None:
                sf = Subfile(name.strip(), ext.strip(), size)
                self.subfiles[key] = sf
            if part == 0:
                sf.size = size
            sf.blocks.extend(blocks)

    def read_subfile(self, key: str, off: int = 0, n: int | None = None) -> bytes:
        sf = self.subfiles[key]
        if n is None:
            n = sf.size - off
        n = min(n, sf.size - off)
        out = bytearray()
        bs = self.blocksize
        while n > 0:
            bi, bo = divmod(off, bs)
            take = min(n, bs - bo)
            out += self._read(sf.blocks[bi] * bs + bo, take)
            off += take
            n -= take
        return bytes(out)


def u24(b: bytes, o: int) -> int:
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16)


def s24(b: bytes, o: int) -> int:
    v = u24(b, o)
    return v - 0x1000000 if v & 0x800000 else v


def mu2deg(v: int) -> float:
    return v * 360.0 / (1 << 24)
