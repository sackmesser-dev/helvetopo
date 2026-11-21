"""Raster-IMG (gmapsupp-artig, NT/GMP) -> gmapi-Ordner für BaseCamp (<Name>.gmap).

Ablauf:
1. GMP-Kacheln aus der IMG lesen (Map-ID und Grenzen aus dem TRE-Header).
2. mkgmap mit Dummy-Kacheln gleicher Nummer und Grenzen laufen lassen (--gmapi --tdbfile). Das liefert
   Info.xml, Übersichtskarte (BaseMap) und ein gültiges TDB.
3. Dummy-Kacheln durch die GMP-Dateien ersetzen (Product1/<nr>/<nr>.GMP), die Detailblöcke im TDB
   auf eine Subdatei <nr>.GMP umschreiben und die TDB-Prüfsumme (CRC32, T-Block) neu berechnen.

Aufruf: python3 -I make_gmapi.py <eingabe.img> <ausgabeordner> <Name> <Family-ID>
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imgread import ImgFile, mu2deg, s24  # noqa: E402
from rasterimg import check_gmp_size, patch_gmp_file, set_gmp_draw_priority  # noqa: E402

OVERVIEW_SUFFIX = 8901        # overview.ID_SUFFIX (ohne Import, overview.py braucht PIL)

sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths  # noqa: E402

MKGMAP = str(paths.MKGMAP)
COPYRIGHT = "©swisstopo (Swiss Map Raster, OGD). Inoffizielle Karte, erstellt mit Helvetopo."
# Ersetzt den mkgmap-Standardtext (OpenStreetMap/ODbL), der sonst ins TDB käme. Die Karten enthalten keine OSM-Daten.
LICENSE = ("Kartendaten: ©swisstopo, Nutzungsbedingungen für frei verfügbare Geodaten (OGD), "
           "https://www.swisstopo.admin.ch/ogd-conditions. Inoffizielle Karte, kein Produkt von swisstopo "
           "oder Garmin. Erstellt mit mkgmap (GPL) und eigenem Raster-Encoder.")


def read_gmps(path: str):
    img = ImgFile(path)
    out = []
    for k, sf in img.subfiles.items():
        if not k.endswith(".GMP"):
            continue
        g = img.read_subfile(k)
        check_gmp_size(k, len(g))          # GMP_MIN/GMP_MAX wie in der IMG (Gerätetest 5 und 8)
        out.append(dict(gmp_info(k, g), data=g))
    return out


def gmp_info(name: str, g: bytes) -> dict:
    tre = struct.unpack_from("<I", g, 0x19)[0]
    map_id = struct.unpack_from("<I", g, tre + 0x74)[0]
    n, e, s, w = (mu2deg(s24(g, tre + o)) for o in (0x15, 0x18, 0x1B, 0x1E))
    return dict(name=name, map_id=map_id, n=n, e=e, s=s, w=w)


def read_gmp_files(paths: list[str]):
    """Wie read_gmps, aber aus einzelnen GMP-Dateien; die Daten werden erst beim Kopieren gelesen."""
    out = []
    for p in paths:
        check_gmp_size(os.path.basename(p), os.path.getsize(p))
        with open(p, "rb") as f:
            g = f.read(0x400)
        out.append(dict(gmp_info(os.path.basename(p), g), path=p))
    return out


def dummy_osm(t, fn):
    n, e, s, w = t["n"], t["e"], t["s"], t["w"]
    pts = [(s, w), (s, e), (n, e), (n, w)]
    nodes = "".join(f'<node id="{i+1}" lat="{la:.7f}" lon="{lo:.7f}" version="1"/>' for i, (la, lo) in enumerate(pts))
    way = ('<way id="1" version="1">' + "".join(f'<nd ref="{i}"/>' for i in (1, 2, 3, 4, 1))
           + '<tag k="natural" v="water"/></way>')
    open(fn, "w").write(f'<?xml version="1.0" encoding="UTF-8"?><osm version="0.6" generator="gst">'
                        f'<bounds minlat="{s:.7f}" minlon="{w:.7f}" maxlat="{n:.7f}" maxlon="{e:.7f}"/>'
                        f'{nodes}{way}</osm>')


def blocks(d: bytes):
    o = 0
    while o < len(d):
        t = d[o]
        ln = struct.unpack_from("<H", d, o + 1)[0]
        yield t, d[o + 3:o + 3 + ln]
        o += 3 + ln


def rewrite_tdb(path: str, tiles: dict[int, tuple[str, int]]):
    """Detailblöcke (0x4C) auf genau eine Subdatei <nr>.GMP umstellen, T-Block-CRC neu berechnen."""
    d = open(path, "rb").read()
    out = bytearray()
    for t, body in blocks(d):
        if t == 0x4C:
            num = struct.unpack_from("<I", body, 0)[0]
            if num in tiles:
                # Kopf (Nr., Eltern, N, E, S, W) + Beschreibung bis \0 übernehmen
                desc_end = body.index(b"\x00", 24) + 1
                fname, size = tiles[num]
                body = (body[:desc_end] + struct.pack("<HH", 2, 1) + struct.pack("<I", size)
                        + struct.pack("<I", 0xFF00C301) + bytes(3) + fname.encode("ascii") + b"\x00")
        if t == 0x54:
            crc = zlib.crc32(bytes(out))
            body = bytes([0, 0, (crc >> 24) & 0xFF, 0, 0, 0, 0, 0, 0, (crc >> 16) & 0xFF, 0, 0,
                          (crc >> 8) & 0xFF, 0, 0, 0, 0, crc & 0xFF, 0, 0])
        out += bytes([t]) + struct.pack("<H", len(body)) + body
    open(path, "wb").write(bytes(out))


def make_gmapi(img_path: str, outdir: str, name: str, fid: int, overview: int, **kw) -> str:
    return make_gmapi_tiles(read_gmps(img_path), outdir, name, fid, overview, **kw)


def make_gmapi_files(paths: list[str], outdir: str, name: str, fid: int, overview: int, **kw) -> str:
    return make_gmapi_tiles(read_gmp_files(paths), outdir, name, fid, overview, **kw)


def make_gmapi_tiles(tiles: list[dict], outdir: str, name: str, fid: int, overview: int,
                     copyright_lines: list[str] | None = None, description: str | None = None,
                     extra_inputs: list[str] | None = None, license_text: str | None = None,
                     draw_priority: int | None = None) -> str:
    """copyright_lines: Zeilen für den Copyright-Block des TDB (mkgmap --copyright-file);
    description: Beschreibung der Kacheln (Standard: Name + Map-ID);
    extra_inputs: weitere mkgmap-Eingaben derselben Familie, die unverändert in die gmapi kommen, z. B.
    transparente Routen-Kacheln (*.img) und deren TYP-Quelltext (routen.py);
    license_text: Lizenztext statt LICENSE; draw_priority: Raster-GMPs beim Kopieren auf diese Priority setzen."""
    os.makedirs(outdir, exist_ok=True)
    work = tempfile.mkdtemp(dir=outdir)
    try:
        args = ["java", "-Xmx4g", "-jar", MKGMAP, f"--output-dir={work}", f"--family-id={fid}",
                "--product-id=1", f"--family-name={name}", f"--series-name={name}",
                f"--overview-mapname={overview}", f"--overview-mapnumber={overview}", "--code-page=1252",
                "--tdbfile", "--gmapi", "--lower-case"]
        lf = os.path.join(work, "license.txt")
        with open(lf, "w", encoding="utf-8") as f:
            f.write((license_text or LICENSE) + "\n")
        args.append(f"--license-file={lf}")
        if copyright_lines:
            cf = os.path.join(work, "copyright.txt")
            with open(cf, "w", encoding="utf-8") as f:
                f.write("\n".join(copyright_lines) + "\n")
            args.append(f"--copyright-file={cf}")
        else:
            args.append(f"--copyright-message={COPYRIGHT}")
        # Kacheln über eine Befehlsdatei (-c): mit Tausenden Kacheln wird die Argumentliste sonst zu lang
        cmd = os.path.join(work, "tiles.args")
        with open(cmd, "w", encoding="utf-8") as f:
            for t in tiles:
                fn = os.path.join(work, f"{t['map_id']:08d}.osm")
                dummy_osm(t, fn)
                f.write(f"mapname={t['map_id']:08d}\n"
                        f"description={(description or name)[:40]} {t['map_id']:08d}\n"
                        f"input-file={fn}\n")
            for x in extra_inputs or []:
                f.write(f"input-file={x}\n")
        args += ["-c", cmd]
        r = subprocess.run(args, capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stdout + r.stderr)
        gmap = os.path.join(work, f"{name}.gmap")
        prod = os.path.join(gmap, "Product1")
        info = {}
        for t in tiles:
            nr = f"{t['map_id']:08d}"
            tdir = os.path.join(prod, nr)
            # Übersichts-GMP (overview.py, <FID>8901) behält ihre eigene, tiefere Priority
            prio = None if t["map_id"] % 10000 == OVERVIEW_SUFFIX else draw_priority
            shutil.rmtree(tdir)
            os.makedirs(tdir)
            if "path" in t:
                shutil.copyfile(t["path"], os.path.join(tdir, f"{nr}.GMP"))
                if prio is not None:
                    patch_gmp_file(os.path.join(tdir, f"{nr}.GMP"), prio)
                info[t["map_id"]] = (f"{nr}.GMP", os.path.getsize(t["path"]))
            else:
                data = t["data"] if prio is None else set_gmp_draw_priority(t["data"], prio)
                open(os.path.join(tdir, f"{nr}.GMP"), "wb").write(data)
                info[t["map_id"]] = (f"{nr}.GMP", len(t["data"]))
        tdb = [f for f in os.listdir(prod) if f.lower().endswith(".tdb")][0]
        rewrite_tdb(os.path.join(prod, tdb), info)
        dest = os.path.join(outdir, f"{name}.gmap")
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.move(gmap, dest)
        return dest
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    src, outdir, name, fid = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
    print(make_gmapi(src, outdir, name, fid, fid * 10000 + 9000))
