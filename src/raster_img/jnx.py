"""Garmin JNX (BirdsEye-Rasterformat), unsigniert, aus Swiss Map Raster. Writer und Rückleser.

Formatbeschreibung: siehe docs/raster/jnx.md. Eigene Implementierung nach den offenen Readern/Writern
von QMapShack (qmt_map2jnx, CMapJNX) und ImageMagick (coders/jnx.c), kein fremder Code übernommen.

Aufruf: python3 -I jnx.py [<ausgabeordner>]       # baut J3, J4, J3b für den Raum St. Gallen
        python3 -I jnx.py --kseries [<ausgabeordner>]   # Halbierungsserie K1–K5
        python3 -I jnx.py --mseries [<ausgabeordner>]   # M1–M3: Metablock/UTF-8 wie SAS.Planet
        python3 -I jnx.py --check <datei.jnx>     # liest eine JNX zurück und prüft sie
"""
from __future__ import annotations

import dataclasses
import io
import math
import os
import struct
import subprocess
import sys
import uuid

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HEADER_BLOCK = 1024              # Kachel-Tabelle beginnt hier (wie qmt_map2jnx)
TILE_REC = 28                    # top, right, bottom, left (i32), width, height (u16), size, offset (u32)
DEG = 0x7FFFFFFF / 180.0
COPYRIGHT = "©swisstopo, Swiss Map Raster (OGD). Inoffizielle Karte, Helvetopo"


def d2j(v: float) -> int:
    return int(v * DEG)


def j2d(v: int) -> float:
    return v / DEG


def jnx_scale(m_per_px: float) -> int:
    """JNX-Massstabswert aus Metern je Pixel (Formel aus qmt_map2jnx, Stufen ×2 ab 76437)."""
    r = 2.000032708011
    return int(math.floor(0.5 + 76437 * math.exp(math.log(r) * math.floor(
        0.5 + math.log(m_per_px * 10 * 130.2084 / 76437) / math.log(r)))))


@dataclasses.dataclass
class JTile:
    north: float
    east: float
    south: float
    west: float
    width: int
    height: int
    jpeg: bytes          # vollständiges JPEG (mit SOI); beim Schreiben wird SOI entfernt


@dataclasses.dataclass
class JLevel:
    tiles: list[JTile]
    scale: int
    name: str = ""


def build_jnx(levels: list[JLevel], version: int, north: float, east: float, south: float, west: float,
              product_id: int = 0, zorder: int = 25, guid: str | None = None, product_name: str = "BirdsEye",
              map_name: str = "GST Raster", copyright: str = COPYRIGHT, info_block: bool | None = None,
              encoding: str = "cp1252", meta_tail: int = 0) -> bytes:
    """meta_tail > 0: wie SAS.Planet JNXlib – Metablock auch in v3, danach meta_tail Nullbytes, die
    Kacheltabelle folgt direkt dahinter (statt fest bei 1024). Strings dort in UTF-8 (encoding)."""
    enc = encoding
    cp = copyright.encode(enc) + b"\x00"
    if info_block is None:
        info_block = version >= 4
    hdr = struct.pack("<IIiiiiIIIIII", version, 0, d2j(north), d2j(east), d2j(south), d2j(west), len(levels),
                      0, product_id, 0, 0, 0)
    if version >= 4:
        hdr += struct.pack("<I", zorder)
    ntiles = sum(len(l.tiles) for l in levels)
    def level_table(table_off: int) -> bytes:
        lvl, t0 = b"", 0
        for l in levels:
            lvl += struct.pack("<III", len(l.tiles), table_off + t0 * TILE_REC, l.scale)
            if version >= 4:
                lvl += struct.pack("<I", 2) + cp
            t0 += len(l.tiles)
        return lvl
    info = b""
    if info_block:
        g = (guid or str(uuid.uuid4())).upper().encode("ascii")
        assert len(g) == 36
        info = (struct.pack("<I", 9) + g + b"\x00" + product_name.encode(enc) + b"\x00" + b"\x00"
                + struct.pack("<H", product_id & 0xFFFF) + map_name.encode(enc) + b"\x00"
                + struct.pack("<I", len(levels)))
        for i, l in enumerate(levels, 1):
            nm = (l.name or f"Level {i}").encode(enc) + b"\x00"
            info += nm + nm + cp + struct.pack("<I", i)
    info += bytes(meta_tail)
    if meta_tail:
        table_off = len(hdr) + len(level_table(0)) + len(info)
    else:
        table_off = HEADER_BLOCK
    data_off = table_off + ntiles * TILE_REC
    head = hdr + level_table(table_off) + info
    if len(head) > table_off:
        raise ValueError("Kopf > 1024 Byte")
    table = bytearray()
    data = bytearray()
    for l in levels:
        for t in l.tiles:
            assert t.jpeg[:2] == b"\xFF\xD8"
            body = t.jpeg[2:]
            table += struct.pack("<iiiiHHII", d2j(t.north), d2j(t.east), d2j(t.south), d2j(t.west), t.width,
                                 t.height, len(body), data_off + len(data))
            data += body
    return head + bytes(table_off - len(head)) + bytes(table) + bytes(data) + b"BirdsEye"


# --------------------------------------------------------------------------- Rücklesen
def _dec(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1252") + " [kein gültiges UTF-8]"


def read_jnx(buf: bytes, decode: bool = True) -> dict:
    """Liest wie CMapJNX/ImageMagick; dekodiert jedes Bild (SOI wieder vorangestellt) zur Prüfung."""
    ver, dev, n, e, s, w, nlev, expire, pid, crc, sig, sigoff = struct.unpack_from("<IIiiiiIIIIII", buf, 0)
    p = 48
    zorder = None
    if ver > 3:
        zorder = struct.unpack_from("<I", buf, p)[0]
        p += 4
    out = dict(version=ver, devid=dev, bounds=(j2d(n), j2d(e), j2d(s), j2d(w)), levels=[], product_id=pid,
               expire=expire, crc=crc, signature=sig, sig_offset=sigoff, zorder=zorder, problems=[])
    for _ in range(nlev):
        cnt, off, scale = struct.unpack_from("<III", buf, p)
        p += 12
        cpr = None
        if ver > 3:
            p += 4
            end = buf.index(b"\x00", p)
            cpr = _dec(buf[p:end])
            p = end + 1
        out["levels"].append(dict(count=cnt, offset=off, scale=scale, copyright=cpr, tiles=[]))
    if struct.unpack_from("<I", buf, p)[0] == 9:
        q = p + 4
        guid = buf[q:q + 36].decode("ascii")
        q += 37
        end = buf.index(b"\x00", q)
        prod = _dec(buf[q:end])
        q = end + 2
        pid16 = struct.unpack_from("<H", buf, q)[0]
        q += 2
        end = buf.index(b"\x00", q)
        out["info"] = dict(guid=guid, product_name=prod, product_id=pid16, map_name=_dec(buf[q:end]))
    for li, lv in enumerate(out["levels"]):
        for k in range(lv["count"]):
            tn, te, ts, tw, wd, ht, size, off = struct.unpack_from("<iiiiHHII", buf, lv["offset"] + k * TILE_REC)
            t = dict(bounds=(j2d(tn), j2d(te), j2d(ts), j2d(tw)), w=wd, h=ht, size=size, offset=off)
            if off + size > len(buf):
                out["problems"].append(f"L{li} T{k}: Daten ausserhalb der Datei")
            elif decode:
                jp = b"\xFF\xD8" + buf[off:off + size]
                try:
                    im = Image.open(io.BytesIO(jp))
                    im.load()
                    if im.size != (wd, ht):
                        out["problems"].append(f"L{li} T{k}: Bildgrösse {im.size} ≠ {wd}x{ht}")
                except Exception as ex:  # noqa: BLE001
                    out["problems"].append(f"L{li} T{k}: JPEG nicht lesbar ({ex})")
            if not (ts < tn and tw < te):
                out["problems"].append(f"L{li} T{k}: Grenzen verdreht")
            lv["tiles"].append(t)
    if not buf.endswith(b"BirdsEye"):
        out["problems"].append("Endmarke 'BirdsEye' fehlt")
    return out


# --------------------------------------------------------------------------- Bauen aus SMR
def make_level(source: str, workdir: str, west: float, south: float, east: float, north: float, dpp: float,
               tile_px: int = 256, quality: int = 85, max_tiles: tuple[int, int] | None = None) -> list[JTile]:
    from regions import vrt_for  # noqa: E402
    vrt = vrt_for(source, os.path.join(workdir, "_vrt"))
    cols = math.ceil((east - west) / (dpp * tile_px) - 1e-9)
    rows = math.ceil((north - south) / (dpp * tile_px) - 1e-9)
    if max_tiles:
        cols, rows = min(cols, max_tiles[0]), min(rows, max_tiles[1])
    e2, s2 = west + cols * tile_px * dpp, north - rows * tile_px * dpp
    tif = os.path.join(workdir, f"_jnx_{source}_{dpp:.4e}_{cols}x{rows}.tif")
    subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-te", repr(west), repr(s2), repr(e2),
                    repr(north), "-ts", str(cols * tile_px), str(rows * tile_px), "-r", "cubic",
                    "-wo", "INIT_DEST=255", vrt, tif], check=True)
    img = Image.open(tif).convert("RGB")
    tiles = []
    step = tile_px * dpp
    for r in range(rows):
        for c in range(cols):
            b = io.BytesIO()
            img.crop((c * tile_px, r * tile_px, (c + 1) * tile_px, (r + 1) * tile_px)).save(
                b, "JPEG", quality=quality, subsampling=2, optimize=False, progressive=False)
            tiles.append(JTile(north - r * step, west + (c + 1) * step, north - (r + 1) * step, west + c * step,
                               tile_px, tile_px, b.getvalue()))
    os.remove(tif)
    return tiles


def m_per_px(dpp: float, lat: float) -> float:
    return dpp * math.pi / 180 * 6371010 * math.cos(math.radians(lat))


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--check":
        for fn in sys.argv[2:]:
            r = read_jnx(open(fn, "rb").read())
            print(f"{os.path.basename(fn)}: Version {r['version']}, Gerät {r['devid']}, Produkt {r['product_id']}, "
                  f"zorder {r['zorder']}, Grenzen N/E/S/W {', '.join(f'{v:.5f}' for v in r['bounds'])}, "
                  f"Signatur {r['signature']}/{r['sig_offset']}")
            if "info" in r:
                print(f"  Info: {r['info']}")
            for i, lv in enumerate(r["levels"]):
                ts = lv["tiles"]
                print(f"  Level {i}: {lv['count']} Kacheln, Massstab {lv['scale']}, Tabelle @{lv['offset']}, "
                      f"N {max(t['bounds'][0] for t in ts):.5f} S {min(t['bounds'][2] for t in ts):.5f} "
                      f"O {max(t['bounds'][1] for t in ts):.5f} W {min(t['bounds'][3] for t in ts):.5f}")
            print(f"  Probleme: {len(r['problems'])}", *r["problems"][:10], sep="\n    ")
        return
    from regions import DPP25  # noqa: E402
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../work/raster_img/jnx"))
    os.makedirs(out, exist_ok=True)
    W, S, E, N = 9.33, 47.40, 9.41, 47.45
    lat = (N + S) / 2
    fine = make_level("pk25", out, W, S, E, N, DPP25)
    coarse = make_level("pk50", out, W, S, E, N, 2 * DPP25)
    lv_fine = JLevel(fine, jnx_scale(m_per_px(DPP25, lat)), "SMR25 1,25 m")
    lv_coarse = JLevel(coarse, jnx_scale(m_per_px(2 * DPP25, lat)), "SMR50 2,5 m")

    def bounds(levels):
        ts = [t for l in levels for t in l.tiles]
        return (max(t.north for t in ts), max(t.east for t in ts), min(t.south for t in ts), min(t.west for t in ts))

    variants = {
        "J3": dict(levels=[lv_coarse, lv_fine], version=3),
        "J4": dict(levels=[lv_coarse, lv_fine], version=4, product_id=7704,
                   guid=str(uuid.uuid5(uuid.NAMESPACE_URL, "garminswisstopo/jnx/J4-stgallen")),
                   map_name="GST Raster St. Gallen (J4)"),
    }
    mini = make_level("pk25", out, 9.365, 47.42, E, 47.43, DPP25, max_tiles=(2, 2))
    variants["J3b"] = dict(levels=[JLevel(mini, lv_fine.scale, "SMR25")], version=3)
    for name, kw in variants.items():
        n, e, s, w = bounds(kw["levels"])
        data = build_jnx(north=n, east=e, south=s, west=w, **kw)
        fn = os.path.join(out, f"TEST_{name}_StGallen.jnx")
        open(fn, "wb").write(data)
        print(f"{fn}: {len(data) / 1e6:.2f} MB, Level " +
              ", ".join(f"{len(l.tiles)} Kacheln/Massstab {l.scale}" for l in kw["levels"]))


def build_kseries(out: str):
    """Halbierungsserie K1–K5: jede Variante ändert gegenüber J3b genau einen Faktor."""
    from regions import DPP25  # noqa: E402
    W, S, E, N = 9.33, 47.40, 9.41, 47.45
    lat = (N + S) / 2
    sc25, sc50 = jnx_scale(m_per_px(DPP25, lat)), jnx_scale(m_per_px(2 * DPP25, lat))
    # J3b-Ausschnitt: NW-Ecke 9.365 / 47.43, 2 × 2 Kacheln
    j3b = make_level("pk25", out, 9.365, 47.42, E, 47.43, DPP25, max_tiles=(2, 2))
    variants = {
        "K1": dict(levels=[JLevel(make_level("pk25", out, W, S, E, N, DPP25), sc25)], version=3),
        "K2": dict(levels=[JLevel(make_level("pk50", out, W, S, E, N, 2 * DPP25), sc50)], version=3),
        "K3": dict(levels=[JLevel(make_level("pk50", out, 9.365, 47.40, E, 47.43, 2 * DPP25, max_tiles=(2, 2)), sc50),
                           JLevel(j3b, sc25)], version=3),
        "K4": dict(levels=[JLevel(j3b, sc25, "SMR25")], version=4, product_id=7704,
                   guid=str(uuid.uuid5(uuid.NAMESPACE_URL, "garminswisstopo/jnx/K4-stgallen")),
                   map_name="GST Raster St. Gallen (K4)"),
        "K5": dict(levels=[JLevel(make_level("pk25", out, 9.35, 47.40, E, 47.45, DPP25, max_tiles=(10, 10)), sc25)],
                   version=3),
    }
    for name, kw in variants.items():
        ts = [t for l in kw["levels"] for t in l.tiles]
        data = build_jnx(north=max(t.north for t in ts), east=max(t.east for t in ts),
                         south=min(t.south for t in ts), west=min(t.west for t in ts), **kw)
        fn = os.path.join(out, f"TEST_{name}_StGallen.jnx")
        open(fn, "wb").write(data)
        print(f"{fn}: {len(data) / 1e6:.2f} MB, Level " +
              ", ".join(f"{len(l.tiles)} Kacheln/Massstab {l.scale}" for l in kw["levels"]))


def build_mseries(out: str):
    """M1–M3: Metablock und UTF-8 wie SAS.Planet JNXlib (v3) bzw. qmt_map2jnx (v4)."""
    from regions import DPP25  # noqa: E402
    W, S, E, N = 9.33, 47.40, 9.41, 47.45
    lat = (N + S) / 2
    sc25, sc50 = jnx_scale(m_per_px(DPP25, lat)), jnx_scale(m_per_px(2 * DPP25, lat))
    full25 = JLevel(make_level("pk25", out, W, S, E, N, DPP25), sc25, "SMR25 1,25 m")
    full50 = JLevel(make_level("pk50", out, W, S, E, N, 2 * DPP25), sc50, "SMR50 2,5 m")
    k3_50 = JLevel(make_level("pk50", out, 9.365, 47.40, E, 47.43, 2 * DPP25, max_tiles=(2, 2)), sc50, "SMR50")
    k3_25 = JLevel(make_level("pk25", out, 9.365, 47.42, E, 47.43, DPP25, max_tiles=(2, 2)), sc25, "SMR25")
    sas = dict(version=3, info_block=True, encoding="utf-8", meta_tail=1024)
    variants = {
        "M1": dict(levels=[full50, full25], guid=str(uuid.uuid5(uuid.NAMESPACE_URL, "garminswisstopo/jnx/M1")),
                   map_name="GST Raster St. Gallen (M1)", **sas),
        "M2": dict(levels=[k3_50, k3_25], guid=str(uuid.uuid5(uuid.NAMESPACE_URL, "garminswisstopo/jnx/M2")),
                   map_name="GST Raster St. Gallen (M2)", **sas),
        "M3": dict(levels=[full50, full25], version=4, product_id=7704, encoding="utf-8",
                   guid=str(uuid.uuid5(uuid.NAMESPACE_URL, "garminswisstopo/jnx/M3")),
                   map_name="GST Raster St. Gallen (M3)"),
    }
    for name, kw in variants.items():
        ts = [t for l in kw["levels"] for t in l.tiles]
        data = build_jnx(north=max(t.north for t in ts), east=max(t.east for t in ts),
                         south=min(t.south for t in ts), west=min(t.west for t in ts), **kw)
        fn = os.path.join(out, f"TEST_{name}_StGallen.jnx")
        open(fn, "wb").write(data)
        print(f"{fn}: {len(data) / 1e6:.2f} MB")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mseries":
        build_mseries(sys.argv[2] if len(sys.argv) > 2 else os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../work/raster_img/jnx")))
    elif len(sys.argv) > 1 and sys.argv[1] == "--kseries":
        build_kseries(sys.argv[2] if len(sys.argv) > 2 else os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../work/raster_img/jnx")))
    else:
        main()
