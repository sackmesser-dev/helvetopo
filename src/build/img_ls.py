#!/usr/bin/env python3
"""Subdateien einer Garmin-IMG (gmapsupp) auflisten: Name, Typ, Grösse. Nur lesend."""
import struct
import sys
from collections import defaultdict

path = sys.argv[1]
with open(path, "rb") as f:
    hdr = f.read(0x200)
    e1, e2 = hdr[0x61], hdr[0x62]
    block = 1 << (e1 + e2)
    desc = (hdr[0x49:0x49 + 20] + hdr[0x65:0x65 + 31]).split(b"\0")[0].decode("cp1252", "replace").strip()
    fat_start = (hdr[0x40] if hdr[0x40] else 2) * 0x200
    f.seek(fat_start)
    files = defaultdict(int)
    while True:
        e = f.read(512)
        if len(e) < 512 or e[0] != 1:
            if len(e) < 512 or e[0] not in (0, 1):
                break
            continue
        name = e[1:9].decode("ascii", "replace").strip()
        ext = e[9:12].decode("ascii", "replace")
        size, part = struct.unpack("<IH", e[12:18])
        if part == 0 and name.strip():
            files[(name, ext)] = size
print(f"{path}: Beschreibung '{desc}', Block {block} B, {len(files)} Subdateien")
for (n, x), s in sorted(files.items()):
    print(f"  {n}.{x}  {s:>10}")
