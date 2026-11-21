"""Diagnosevariante T1: Original-GMP unverändert, nur die JPEG-Bilder durch SMR25 ersetzt.

Jedes Bild wird aus Swiss Map Raster 25 exakt auf die Grenzen des Originalbilds (aus den Zusatzdaten
der Rasterpolygone) gerechnet. Container, Polygone, Huffman, Labels bleiben Original. Damit lässt sich
die eigene JPEG-Erzeugung getrennt von unserem GMP-Aufbau testen. Nur lokal (Garmin-Material).

Aufruf: python3 -I make_transplant.py <Original.IMG> <GMP-Name> <Ausgabeordner>
"""
from __future__ import annotations

import glob
import io
import os
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402

import huffman as H  # noqa: E402
from imgread import ImgFile, mu2deg  # noqa: E402
from rasterimg import build_img, build_mps, byte_size  # noqa: E402

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

SMR25 = str(paths.SMR_DIR / "pk25" / "*.tif")


def raster_polys(g: bytes):
    """Liefert (Position des Grössenfelds in g, Bildindex, N, E, S, W) für alle Rasterpolygone."""
    tre, rgn, lbl = struct.unpack_from("<3I", g, 0x19)
    R, L = g[rgn:], g[lbl:]
    r2o, r2s = struct.unpack_from("<II", R, 0x1D)
    l28s, l28r = struct.unpack_from("<IH", L, 0x188)
    idsz = byte_size(l28s // l28r - 1)
    p, end, out = r2o, r2o + r2s, []
    while p < end:
        t, st = g[p], g[p + 1]
        p += 6
        bl, p = H.read_vuint(g, p)
        p += bl
        if st & 0x20:
            p += 3
        if st & 0x80:
            fl = g[p]; p += 1
            ln, p2 = H.read_vuint(g, p) if fl >> 5 == 7 else ({4: 1, 5: 2, 6: 3}[fl >> 5], p)
            if t == 0x06 and (st & 0x1F) == 0x13 and ln == idsz + 20:
                idx = int.from_bytes(g[p2:p2 + idsz], "little")
                n, e, s, w = (v >> 8 for v in struct.unpack_from("<iiii", g, p2 + idsz))
                out.append((p2 + idsz + 16, idx, mu2deg(n), mu2deg(e), mu2deg(s), mu2deg(w)))
            p = p2 + ln
    return out


def main():
    src, key, outdir = sys.argv[1:4]
    img = ImgFile(src)
    g = bytearray(img.read_subfile(key))
    name = key.split(".")[0]
    tre, rgn, lbl = struct.unpack_from("<3I", g, 0x19)
    L = lbl
    l28o, l28s, l28r = struct.unpack_from("<IIH", g, L + 0x184)
    l29o, l29s = struct.unpack_from("<II", g, L + 0x192)
    nimg = l28s // l28r
    polys = raster_polys(bytes(g))
    bounds = {}
    for _, idx, n, e, s, w in polys:
        bounds.setdefault(idx, (n, e, s, w))
    assert len(bounds) == nimg, (len(bounds), nimg)
    tmp = tempfile.mkdtemp(dir=outdir)
    vrt = os.path.join(tmp, "smr25.vrt")
    subprocess.run(["gdalbuildvrt", "-q", vrt, *sorted(glob.glob(SMR25))], check=True)
    jpegs = []
    for idx in range(nimg):
        n, e, s, w = bounds[idx]
        tif = os.path.join(tmp, f"{idx}.tif")
        subprocess.run(["gdalwarp", "-q", "-t_srs", "EPSG:4326", "-te", repr(w), repr(s), repr(e), repr(n),
                        "-ts", "512", "512", "-r", "cubic", "-wo", "INIT_DEST=255", vrt, tif], check=True)
        buf = io.BytesIO()
        Image.open(tif).convert("RGB").save(buf, "JPEG", quality=85, subsampling=2)
        jpegs.append(buf.getvalue())
        os.remove(tif)
    new29 = b"".join(jpegs)
    offs, o = [], 0
    for j in jpegs:
        offs.append(o)
        o += len(j)
    delta = len(new29) - l29s
    old_end29 = l29o + l29s
    # Grössenfelder in RGN2
    for pos, idx, *_ in polys:
        struct.pack_into("<I", g, pos, len(jpegs[idx]))
    for i, off in enumerate(offs):
        g[l28o + i * l28r:l28o + (i + 1) * l28r] = off.to_bytes(l28r, "little")
    struct.pack_into("<I", g, L + 0x196, len(new29))
    # Header-Offsets, die hinter LBL29 zeigen (TRE9 usw.), verschieben
    for base, hl in ((tre, struct.unpack_from("<H", g, tre)[0]), (rgn, 0x7D),
                     (lbl, struct.unpack_from("<H", g, lbl)[0])):
        for p in range(base + 0x15, base + hl - 3):
            v = struct.unpack_from("<I", g, p)[0]
            if v == old_end29:  # Offsetfelder, die auf TRE9 direkt hinter LBL29 zeigen
                struct.pack_into("<I", g, p, v + delta)
                print("  verschoben:", hex(p - base), "im Header bei", hex(base))
    g = g[:l29o] + new29 + g[old_end29:]
    tre_mapid = struct.unpack_from("<I", g, tre + 0x74)[0]
    mps = build_mps(7704, 1, "GST Diagnose T1", [(tre_mapid, name)])
    data = build_img([("GMAPPROM", "MPS", mps), (name, "GMP", bytes(g))], "Diagnose T1 Orig-GMP+SMR25")
    fn = os.path.join(outdir, "T1_orig_gmp_smr25_jpeg.img")
    open(fn, "wb").write(data)
    os.remove(vrt)
    os.rmdir(tmp)
    print(fn, len(data), "Bilder", nimg, "Delta", delta)


if __name__ == "__main__":
    main()
