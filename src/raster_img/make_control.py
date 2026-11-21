"""Kontrollvarianten: eine Original-GMP-Kachel unverändert in einen neuen IMG-Container packen.

Nur für lokale Tests (urheberrechtlich geschütztes Garmin-Material), Ausgabe nach work/raster_img/.
Aufruf: python3 -I make_control.py <Original.IMG> <GMP-Name> <Ausgabeordner>
"""
from __future__ import annotations

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imgread import ImgFile  # noqa: E402
from rasterimg import build_img, build_mps  # noqa: E402


def main():
    src, gmp_key, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(outdir, exist_ok=True)
    img = ImgFile(src)
    gmp = img.read_subfile(gmp_key)
    name = gmp_key.split(".")[0]
    mps = img.read_subfile("GMAPPROM.MPS")
    # Original-MPS: F-Record + L-Record genau dieser Kachel
    o = 0
    f_rec = l_rec = None
    while o < len(mps):
        ln = struct.unpack_from("<H", mps, o + 1)[0]
        rec = mps[o:o + 3 + ln]
        if rec[0:1] == b"F":
            f_rec = rec
        elif rec[0:1] == b"L" and name.encode() + b"\x00" in rec:
            l_rec = rec
        o += 3 + ln
    assert f_rec and l_rec
    # C1: Original-GMP + Original-MPS-Records (Family 1395)
    data = build_img([("GMAPPROM", "MPS", f_rec + l_rec), (name, "GMP", gmp)],
                     "Kontrolle C1 Original-GMP")
    open(os.path.join(outdir, "C1_orig_gmp_orig_mps.img"), "wb").write(data)
    # C2: Original-GMP + eigene MPS (Family 7704, Produkt 1)
    tre = struct.unpack_from("<I", gmp, 0x19)[0]
    map_id = struct.unpack_from("<I", gmp, tre + 0x74)[0]
    mps2 = build_mps(7704, 1, "GST Kontrolle C2", [(map_id, name)])
    data = build_img([("GMAPPROM", "MPS", mps2), (name, "GMP", gmp)], "Kontrolle C2 Original-GMP FID7704")
    open(os.path.join(outdir, "C2_orig_gmp_fid7704.img"), "wb").write(data)
    print("ok", name, hex(map_id), len(gmp))


if __name__ == "__main__":
    main()
