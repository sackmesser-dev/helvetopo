"""Prüfwerkzeug: liest eine (Raster-)IMG wie GPXSee/Garmin und prüft die Konsistenz.

Aufruf: python3 -I inspect_img.py <datei.img> [--extract DIR] [--max-gmp N]
Prüft je GMP: Ebenen, Subdivisions, TRE7-Zuordnung (oberste Ebene ohne Eintrag + Endeintrag),
Rasterpolygone (Bildindexbreite = byteSize(n-1)), Lage der Polygone gegen die Zusatzdaten,
JPEG-Signatur und -Grösse.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bitstream import decode_deltas  # noqa: E402
import huffman as H  # noqa: E402
from imgread import ImgFile, mu2deg, s24, u24  # noqa: E402


def byte_size(v):
    n = 1
    while v >= (1 << (8 * n)):
        n += 1
    return n


def check_gmp(img: ImgFile, key: str, extract: str | None, verbose: bool) -> list[str]:
    probs = []
    g = img.read_subfile(key, 0, min(img.subfiles[key].size, 0x400000))
    tre, rgn, lbl = struct.unpack_from("<3I", g, 0x19)
    T, R, L = g[tre:], g[rgn:], g[lbl:]
    t1o, t1s, t2o, t2s = struct.unpack_from("<IIII", T, 0x21)
    levels = [(g[t1o + i], g[t1o + i + 1], struct.unpack_from("<H", g, t1o + i + 2)[0]) for i in range(0, t1s, 4)]
    huff = struct.unpack_from("<I", R, 0x79)[0] & 0x1E if struct.unpack_from("<H", R, 0)[0] >= 0x7D else 0
    ctab = ttab = None
    r5o, r5s, r5info = struct.unpack_from("<III", R, 0x71)
    if huff and r5s:
        recs5 = H.split_records(g[r5o:r5o + r5s])
        ctab = H.Table(recs5[((r5info >> 1) & 0xF) - 1])
        ttab = H.Table(recs5[0])
    l1o, l1s = struct.unpack_from("<II", L, 0x15)
    coding = L[0x1E]
    lbl1 = g[l1o:l1o + l1s]

    def label_text(off):
        if coding == 11 and ttab:
            return H.decode_text(ttab, lbl1[off:])
        return lbl1[off:lbl1.index(b"\x00", off) + 1]

    t3o, t3s = struct.unpack_from("<II", T, 0x31)
    copyrights = [label_text(u24(g, t3o + i)) for i in range(0, t3s, 3)]
    l28o, l28s, l28r = struct.unpack_from("<IIH", L, 0x184)
    l29o, l29s = struct.unpack_from("<II", L, 0x192)
    nimg = l28s // l28r if l28r else 0
    idsz = byte_size(nimg - 1) if nimg else 0
    offs = [int.from_bytes(g[l28o + i * l28r:l28o + (i + 1) * l28r], "little") for i in range(nimg)]
    t7o, t7s, t7r, t7f = struct.unpack_from("<IIHI", T, 0x7C)
    r2o, r2s = struct.unpack_from("<II", R, 0x1D)
    sds = []
    o = t2o
    for li, (z, bits, n) in enumerate(levels):
        for _ in range(n):
            last = li == len(levels) - 1
            clon, clat = s24(g, o + 4), s24(g, o + 7)
            w, h = struct.unpack_from("<HH", g, o + 10)
            sds.append(dict(level=li, bits=bits, inherited=bool(z & 0x80), clon=clon, clat=clat,
                            hw=(w & 0x7FFF) << (24 - bits), hh=(h & 0x7FFF) << (24 - bits)))
            o += 14 if last else 16
    nrec = t7s // t7r if t7r else 0
    diff = len(sds) - nrec + 1
    if verbose:
        print(f"  {key}: levels(bits)={[b for _, b, _ in levels]} subdivs={len(sds)} tre7recs={nrec} "
              f"(erste mit Eintrag: Subdiv {diff + 1}) bilder={nimg} idbytes={idsz} huffman={bool(huff)} "
              f"lbl-codierung={coding}")
        print(f"    Copyright: {[c.decode('cp1252', 'replace') for c in copyrights]}")
    recs = [struct.unpack_from("<I", g, t7o + i * t7r)[0] for i in range(nrec)]
    stats = {}
    for si, sd in enumerate(sds):
        k = si - diff
        if k < 0:
            continue
        start = recs[k]
        end = recs[k + 1] if k + 1 < len(recs) else r2s
        P = g[r2o + start:r2o + end]
        p = 0
        shift = 24 - sd["bits"]
        while p < len(P):
            t, st = P[p], P[p + 1]
            dlon, dlat = struct.unpack_from("<hh", P, p + 2)
            p += 6
            if P[p] & 1:
                bl = P[p] >> 1; p += 1
            else:
                bl = struct.unpack_from("<H", P, p)[0] >> 2; p += 2
            bs = P[p:p + bl]; p += bl
            lab = None
            if st & 0x20:
                lab = u24(P, p); p += 3
            info = None
            if st & 0x80:
                fl = P[p]; p += 1
                if fl >> 5 == 7:
                    vb = P[p]
                    if vb & 1:
                        rs = vb >> 1; p += 1
                    else:
                        rs = struct.unpack_from("<H", P, p)[0] >> 2; p += 2
                else:
                    rs = {4: 1, 5: 2, 6: 3}.get(fl >> 5, 0)
                info = P[p:p + rs]; p += rs
            x0 = sd["clon"] + (dlon << shift)
            y0 = sd["clat"] + (dlat << shift)
            typ = 0x10000 | (t << 8) | (st & 0x1F)
            stats[(si + 1, typ)] = stats.get((si + 1, typ), 0) + 1
            pts = [(x0, y0)]
            if not huff:
                _, d = decode_deltas(bs[0], bs[1:])
            elif ctab:
                try:
                    d = H.decode_deltas(ctab, bs)
                except Exception as ex:  # noqa: BLE001
                    probs.append(f"{key} sd{si+1}: Huffman-Bitstream fehlerhaft: {ex}")
                    d = []
            else:
                d = []
            for dx, dy in d:
                pts.append((pts[-1][0] + (dx << shift), pts[-1][1] + (dy << shift)))
            if lab:
                try:
                    label_text(lab)
                except Exception as ex:  # noqa: BLE001
                    probs.append(f"{key} sd{si+1}: Label {lab} nicht lesbar: {ex}")
            if typ == 0x10613 and info is None:
                stats[(si + 1, "0x10613 ohne Zusatzdaten")] = stats.get((si + 1, "0x10613 ohne Zusatzdaten"), 0) + 1
                if verbose and stats[(si + 1, "0x10613 ohne Zusatzdaten")] <= 2:
                    print(f"    sd{si+1}: 0x10613 ohne Zusatzdaten st={st:#x} d=({dlon},{dlat}) lab={lab} "
                          f"bs={bs.hex()}")
                continue
            if typ == 0x10613:
                if len(info) != idsz + 20:
                    probs.append(f"{key} sd{si+1}: Zusatzdaten {len(info)} B, erwartet {idsz + 20}")
                    continue
                idx = int.from_bytes(info[:idsz], "little")
                n_, e_, s_, w_, size = struct.unpack_from("<iiiiI", info, idsz)
                n_, e_, s_, w_ = n_ >> 8, e_ >> 8, s_ >> 8, w_ >> 8
                if idx >= nimg:
                    probs.append(f"{key} sd{si+1}: Bildindex {idx} >= {nimg}")
                    continue
                isz = (offs[idx + 1] if idx + 1 < nimg else l29s) - offs[idx]
                if isz != size:
                    probs.append(f"{key} sd{si+1}: Grösse {size} != LBL28-Differenz {isz}")
                tol = 2 << shift
                if abs(x0 - w_) > tol or abs(y0 - s_) > tol:
                    probs.append(f"{key} sd{si+1} img{idx}: Startpunkt ({x0},{y0}) weicht von SW ({w_},{s_}) ab")
                if len(pts) >= 4:
                    xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
                    if abs(min(xs) - w_) > tol or abs(max(xs) - e_) > tol or abs(min(ys) - s_) > tol \
                            or abs(max(ys) - n_) > tol:
                        probs.append(f"{key} sd{si+1} img{idx}: Polygon passt nicht zu N/E/S/W")
                if not (sd["clon"] - sd["hw"] - tol <= w_ and e_ <= sd["clon"] + sd["hw"] + tol
                        and sd["clat"] - sd["hh"] - tol <= s_ and n_ <= sd["clat"] + sd["hh"] + tol):
                    probs.append(f"{key} sd{si+1} img{idx}: Kachel ausserhalb der Subdivision")
                if extract and sd["level"] == len(levels) - 1:
                    jpg = img.read_subfile(key, l29o + offs[idx], size)
                    if jpg[:2] != b"\xff\xd8":
                        probs.append(f"{key} img{idx}: keine JPEG-Signatur")
                    os.makedirs(extract, exist_ok=True)
                    fn = f"{key}_{idx:03d}_{mu2deg(s_):.5f}_{mu2deg(w_):.5f}.jpg"
                    open(os.path.join(extract, fn), "wb").write(jpg)
    if verbose:
        for (sdn, typ), c in sorted(stats.items(), key=str):
            print(f"    sd{sdn} bits{sds[sdn-1]['bits']}: Typ {typ if isinstance(typ, str) else hex(typ)} x {c}")
    return probs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img")
    ap.add_argument("--extract")
    ap.add_argument("--max-gmp", type=int, default=3)
    a = ap.parse_args()
    img = ImgFile(a.img)
    print(f"{a.img}: Blockgrösse {img.blocksize}, {len(img.subfiles)} Subdateien")
    if "GMAPPROM.MPS" in img.subfiles or any(k.endswith(".MPS") for k in img.subfiles):
        for k in img.subfiles:
            if k.endswith(".MPS"):
                m = img.read_subfile(k)
                o = 0
                while o < len(m):
                    t = chr(m[o]); ln = struct.unpack_from("<H", m, o + 1)[0]
                    body = m[o + 3:o + 3 + ln]
                    if t in "FL":
                        prod, fam = struct.unpack_from("<HH", body, 0)
                        print(f"  {k} {t}: product {prod} family {fam} {body[4:].hex(' ')[:120]}")
                    o += 3 + ln
                    if o > 2000:
                        break
    probs = []
    gmps = [k for k in img.subfiles if k.endswith(".GMP")]
    for i, k in enumerate(gmps):
        probs += check_gmp(img, k, a.extract, i < a.max_gmp)
    print(f"{len(gmps)} GMP geprüft, {len(probs)} Probleme")
    for p in probs[:40]:
        print("  !", p)
    sys.exit(1 if probs else 0)


if __name__ == "__main__":
    main()
