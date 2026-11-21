#!/usr/bin/env python3
"""Stellt ein Release aus fertigen Builds zusammen (Release-Plan, docs/build/release.md).

Eingaben (vorher bauen):
- Vektor:  OUT=<dir> VERSION=<version> src/build/build_all.sh  → <dir>/dist/{gmapsupp.img, BaseCamp/*.gmap}
- Pixel:   src/raster_img/release.py --variant <v> --region <gebiet> --version <version> --gmapi --out <dir>/<v>

Ausgaben:
- work/release/<version>/files/        Downloads mit sprechenden Namen, BaseCamp-ZIPs, SHA256SUMS
- work/release/<version>/manifest.json Portal-Manifest (Schema 2, docs/build/portal.md)
- releases/<version>/{vektor,pixel}/   README.md und QUELLSTAND.md (versioniert, vom Portal verlinkt)

Aufruf (Testgebiet):
  .venv/bin/python -I src/release/make_release.py --version 2026-11 --area testgebiet \
      --vector work/release-build/vektor --pixel work/release-build/pixel

Aufruf (Schweiz, Quellen aus der NAS-Ablage, docs/build/build.md „Rohdaten und Ablage“):
  .venv/bin/python -I src/release/make_release.py --version 2026-11 --area schweiz \
      --store <Ablage>/helvetopo/.build --out work/release/2026-11-ch [--dry-run]
  Erwartete Ablage: vektor/ch/<v>/{gmapsupp.img,README.txt,LICENSE.txt,BaseCamp/*.gmap},
  routen/ch/<v>/Helvetopo_Routen_Schweiz_<v>.img, pixel/<v>/ und luftbild/<v>/ (IMG, QUELLSTAND,
  BaseCamp/*.gmap). Die Downloads in <out>/files/ sind symbolische Links auf die Ablage. Nur die
  BaseCamp-ZIPs entstehen neu. --dry-run schreibt nur <out>/manifest.dry.json (ohne ZIPs und Prüfsummen).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src" / "raster_img"))
sys.path.insert(1, str(REPO / "src"))
import paths  # noqa: E402
import quellstand as Q  # noqa: E402

PREFIX = "Helvetopo"
PORTAL = REPO / "src" / "portal" / "prototype"
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/{c}/items?limit=100"
ATTR_ST = "©swisstopo"
ATTR_ASTRA = "Bundesamt für Strassen, Kanton, Stiftung SchweizMobil"
ATTR_SM = "Stiftung SchweizMobil"

# Gebiete: Dateinamen-Teil, Text, BBox WGS84 (W, S, E, N)
AREAS = {
    "testgebiet": ("Testgebiet", "Testgebiet Wil–St. Gallen–Säntis", (9.00, 47.20, 9.50, 47.50)),
    "schweiz": ("Schweiz", "Schweiz und Liechtenstein", (5.95, 45.81, 10.50, 47.81)),
}
BASE_URL = "https://dl.sackmesser.dev/helvetopo/{v}/"
# Schweiz: Variante -> Aufteilung der Gerätedateien (Portal-Manifest „area“, release.PARTITIONS)
# 10-1000: vier Teile aus ganzen Regionen (release.PARTITIONS["teile"]). Die Portal-IDs haben das Präfix
# „pixel10-“, weil „west“ und „ost“ schon die Hälften von 25-1000 sind (regions.json: eine Form je ID).
PIXEL_AREA = {"50-1000": "schweiz", "25-1000": "haelften", "10-1000": "teile"}
AREA_REGIONS = {"schweiz": [None], "haelften": ["west", "ost"],
                "teile": ["pixel10-west", "pixel10-sued", "pixel10-mitte", "pixel10-ost"],
                "regionen": ["genfersee", "bern", "nordwestschweiz", "wallis", "zuerich", "ostschweiz",
                             "graubuenden", "zentralschweiz", "tessin"]}
MANIFEST_AREA = {"teile": "regionen"}     # Portal: Auswahl je Gebiet wie bei Regionen
REGION_FILE = {"west": "West", "ost": "Ost", "pixel10-west": "West", "pixel10-sued": "Sued", "pixel10-mitte": "Mitte",
               "pixel10-ost": "Ost", "genfersee": "Genfersee", "bern": "Bern",
               "nordwestschweiz": "Nordwestschweiz", "wallis": "Wallis", "zuerich": "Zuerich",
               "ostschweiz": "Ostschweiz", "graubuenden": "Graubuenden", "zentralschweiz": "Zentralschweiz",
               "tessin": "Tessin"}
# Luftbild: Produkt -> (FID, Name im Build, Name im Release laut Portal-Manifest, Name der gmapi, Teilung).
# Teilung: GeoJSON der Teile in der Ablage (luftbild.py --split-max, Feature-id = Portal-Region), None = eine Datei.
LUFTBILD = {
    "luftbild-standard": (7708, "Luftbild-kompakt", "Luftbild_Standard", "Luftbild kompakt", None),
    "luftbild-detail": (7707, "Luftbild_Detail", "Luftbild_Detail", "Luftbild Detail", "regionen-detail.geojson"),
}
# Teile von Luftbild detail, deren ID schon eine Pixel-Region mit anderer Form bezeichnet: eigene Portal-ID
# (regions.json speichert eine Form je ID)
LUFTBILD_REGION_ID = {"ostschweiz": "luftbild-ostschweiz", "nordwestschweiz": "luftbild-nordwestschweiz"}
LUFTBILD_USED = {7708: "Asset 2 m je Kachel", 7707: "Übersicht 0,4 m des 10-cm-COG je Kachel"}
PIXEL = {  # Variante -> (FID, Massstäbe feinste zuerst)
    "50-1000": (7704, [50, 100, 200, 500, 1000]),
    "25-1000": (7705, [25, 50, 100, 200, 500, 1000]),
    "10-1000": (7706, [10, 25, 50, 100, 200, 500, 1000]),
}
# Vektor-Quellen: id -> (Titel, STAC-Collection, prominent)
VECTOR_SOURCES = {
    "swisstlm3d": ("swissTLM3D", "ch.swisstopo.swisstlm3d", True),
    "swissnames3d": ("swissNAMES3D", "ch.swisstopo.swissnames3d", True),
    "gebaeudeadressen": ("Amtliches Gebäudeadressverzeichnis", "ch.swisstopo.amtliches-gebaeudeadressverzeichnis", True),
    "strassenverzeichnis": ("Amtliches Strassenverzeichnis", "ch.swisstopo.amtliches-strassenverzeichnis", True),
    "swissalti3d": ("swissALTI3D", "ch.swisstopo.swissalti3d", False),
    "smv25": ("Swiss Map Vector 25 (Höhenlinien, Koten)", "ch.swisstopo.swiss-map-vector25", False),
    "swissboundaries3d": ("swissBOUNDARIES3D", "ch.swisstopo.swissboundaries3d", False),
    "wanderwege": ("swissTLM3D Wanderwege", "ch.swisstopo.swisstlm3d-wanderwege", False),
    "schweizmobil": ("SchweizMobil-Routen (Wanderland, Veloland, Mountainbikeland, Skatingland)", "ch.astra.wanderland", False),
    "kanuland": ("SchweizMobil Kanuland", None, False),
}


# ------------------------------------------------------------------ Quellstand
def _downloads() -> Path:
    return paths.DOWNLOADS


def _mtime(p: Path) -> str:
    return _dt.date.fromtimestamp(p.stat().st_mtime).isoformat()


def _stac_items(coll: str, cache: dict) -> list[dict]:
    if coll not in cache:
        with urllib.request.urlopen(STAC.format(c=coll), timeout=30) as r:
            cache[coll] = [dict(id=f["id"], datetime=(f["properties"].get("datetime") or "")[:10])
                           for f in json.load(r)["features"]]
    return cache[coll]


def vector_sources(bbox, cache: dict) -> list[dict]:
    """Ausgabe und Bezugsdatum je Vektor-Quelle, aus den lokalen Downloads und STAC."""
    dl = _downloads()
    out = []

    def item(coll, item_id):
        return next((i for i in _stac_items(coll, cache) if i["id"] == item_id), {})

    for sid, (title, coll, prom) in VECTOR_SOURCES.items():
        e = dict(id=sid, title=title, prominent=prom)
        if coll:
            e["stac"] = coll
        if sid == "swisstlm3d":
            z = next(dl.glob("swisstlm3d/swisstlm3d_*_2056_*.gpkg.zip"))
            ed = re.search(r"swisstlm3d_(\d{4}-\d{2})", z.name).group(1)
            e.update(edition=ed, date=item(coll, f"swisstlm3d_{ed}").get("datetime"))
        elif sid == "swissnames3d":
            ed = re.search(r"(\d{4})", next(dl.glob("swissnames3d/swissnames3d_*.gpkg")).name).group(1)
            e.update(edition=ed, date=item(coll, f"swissnames3d_{ed}").get("datetime"))
        elif sid == "swissboundaries3d":
            z = next(dl.glob("swissboundaries3d/swissboundaries3d_*.gpkg.zip"))
            ed = re.search(r"(\d{4}-\d{2})", z.name).group(1)
            e.update(edition=ed, date=item(coll, f"swissboundaries3d_{ed}").get("datetime"))
        elif sid in ("gebaeudeadressen", "strassenverzeichnis"):
            z = next(dl.glob(f"{sid}/*.csv.zip"))
            e.update(edition="täglich nachgeführt", date=_mtime(z))
        elif sid == "swissalti3d":
            years = _alti_years(dl / "swissalti3d" / "2m", bbox)
            e.update(edition=years)
        elif sid == "smv25":
            eds = sorted({p.name.split("_")[0] for p in (dl / "smv25-2026").glob("20*_*")})
            e.update(edition="–".join(dict.fromkeys([eds[0], eds[-1]])) if eds else "")
        elif sid == "wanderwege":
            e.update(date=item(coll, "swisstlm3d-wanderwege").get("datetime"))
        elif sid == "schweizmobil":
            e.update(date=item(coll, "wanderland").get("datetime"),
                     retrieved=_mtime(dl / "astra-wanderland" / "wanderland_2056.gpkg"))
        elif sid == "kanuland":
            e.update(retrieved=_mtime(dl / "schweizmobil-kanuland" / "kanu.gpkg"))
        out.append(e)
    return out


def _alti_years(d: Path, bbox) -> str:
    def lv95(lon, lat):  # Näherungsformel swisstopo (Genauigkeit ~1 m), reicht für die Kachelauswahl
        p, l = (lat * 3600 - 169028.66) / 10000, (lon * 3600 - 26782.5) / 10000
        e = 2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p - 44.54 * l ** 3
        n = 1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p - 194.56 * l * l * p + 119.79 * p ** 3
        return e, n
    w, s, e, n = bbox
    xs, ys = zip(*(lv95(x, y) for x in (w, e) for y in (s, n)))
    x0, x1, y0, y1 = int(min(xs) // 1000), int(max(xs) // 1000), int(min(ys) // 1000), int(max(ys) // 1000)
    years = set()
    for p in d.glob("swissalti3d_*_*-*_2_2056*.tif"):
        m = re.match(r"swissalti3d_(\d{4})_(\d{4})-(\d{4})_", p.name)
        if m and x0 <= int(m[2]) <= x1 and y0 <= int(m[3]) <= y1:
            years.add(int(m[1]))
    return f"{min(years)}–{max(years)}" if len(years) > 1 else (str(min(years)) if years else "")


def pixel_sources(bbox) -> list[dict]:
    src = Q.sources([10, 25, 50, 100, 200, 500, 1000], bbox)
    out = []
    for s, v in src.items():
        if not v["sheets"]:
            continue
        a, b = v["year_min"], v["year_max"]
        out.append(dict(id=f"smr{s}", title=v["name"], edition=str(a) if a == b else f"{a}–{b}",
                        sheets=v["sheets"], stac=v["collection"], prominent=True))
    return out


_QS_SMR = re.compile(r"^- Swiss Map Raster (\d+): (\d+) Bl\S+, Ausgaben? ([\d–]+), .*STAC-Collection (\S+)", re.M)
_QS_SI = re.compile(r"^- SWISSIMAGE 10 cm: (\d+) Kacheln .*?, Befliegung(?:en)? ([\d–]+), Stand der Items bis "
                    r"([\d-]+), .*STAC-Collection (\S+)", re.M)


def pixel_sources_qs(texts: list[str]) -> list[dict]:
    """SMR-Quellen aus QUELLSTAND-Dateien (release.py). Bei mehreren Dateien je Massstab die Datei mit
    den meisten Blättern (Schweiz-Datei bzw. grösste Region)."""
    best = {}
    for t in texts:
        for m in _QS_SMR.finditer(t):
            s, n = int(m[1]), int(m[2])
            if n > best.get(s, (0,))[0]:
                best[s] = (n, m[3], m[4])
    return [dict(id=f"smr{s}", title=f"Swiss Map Raster {s}", edition=ed, sheets=n, stac=coll, prominent=True)
            for s, (n, ed, coll) in sorted(best.items())]


def part_file(region: str) -> str:
    """Teil-ID (z. B. graubuenden-sued) -> Dateinamen-Teil (Graubuenden-Sued), wie luftbild.split_parts."""
    return "-".join(w.capitalize() for w in region.split("-"))


def merge_swissimage(srcs: list[dict]) -> dict:
    """SWISSIMAGE-Quellstand mehrerer Teile: Spanne der Befliegungsjahre, neuester Stand, grösste Kachelzahl
    (die Teile überlappen am Rand in den Quellkacheln, eine Summe wäre zu hoch)."""
    years = [int(y) for x in srcs for y in re.findall(r"\d{4}", x["edition"])]
    ed = f"{min(years)}–{max(years)}" if min(years) != max(years) else str(min(years))
    return dict(srcs[0], edition=ed, date=max(x["date"] for x in srcs), tiles=max(x["tiles"] for x in srcs))


def swissimage_source(text: str) -> dict:
    m = _QS_SI.search(text)
    if not m:
        raise SystemExit("QUELLSTAND Luftbild: SWISSIMAGE-Zeile fehlt")
    return dict(id="swissimage", title="SWISSIMAGE 10 cm", edition=m[2], date=m[3], tiles=int(m[1]),
                stac=m[4], prominent=True)


# ------------------------------------------------------------------ Dateien
def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def zip_dir(zpath: Path, gmap: Path, extra: dict[str, str]) -> None:
    """BaseCamp-ZIP: <name>.gmap/… plus README/LICENSE (Text) im Wurzelordner."""
    tmp = zpath.with_suffix(".zip.part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for f in sorted(gmap.rglob("*")):
            if f.is_file() and f.name != ".DS_Store" and not f.name.startswith("._"):  # keine macOS-Begleitdateien
                # GMP enthalten JPEG: Deflate spart nichts und kostet Zeit
                ct = zipfile.ZIP_STORED if f.suffix.upper() == ".GMP" else zipfile.ZIP_DEFLATED
                z.write(f, Path(gmap.name) / f.relative_to(gmap), compress_type=ct)
        for name, text in extra.items():
            z.writestr(name, text)
    tmp.replace(zpath)


def link_or_copy(src: Path, dst: Path, symlink: bool = False) -> None:
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if symlink:                     # Schweiz: Link auf die Ablage statt Kopie
        dst.symlink_to(src)
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


# ------------------------------------------------------------------ Grenzwerte
# Grenzwerte für Gerätefamilien (docs/test/teststufen.md, Abschnitt „Gerätekompatibilität“).
# - FAT32: Dateien bis 2^32 − 1 Byte (Microsoft, FAT32-Spezifikation). Garmin-Speicher und microSD
#   nutzen FAT32.
# - IMG-Container: Die FAT-Einträge zählen Blöcke mit 16 Bit, 0xFFFF ist das Endezeichen. Eine IMG hat
#   höchstens 0xFFFF Blöcke (mkgmap ImgFS, src/raster_img/imgread.py).
# - Kacheln je IMG: Ältere Geräte (GPSMAP 60/76 CSx, eTrex HCx, Colorado) zeigen höchstens 2025 Kacheln.
#   Neuere Geräte zeigen bis etwa 4000 Kacheln. Beide Werte stammen aus der mkgmap-Mailingliste und von
#   openmtbmap.org, nicht von Garmin (unsicher).
# - Erweiterte Typen (≥ 0x10000): Ältere Geräte zeigen sie nicht an (mkgmap style manual, „extended types“).
# - Referenz: „Topo Schweiz v3 Raster“ (Garmin) hat 516 GMP-Kacheln in einer IMG und läuft auf eTrex und
#   GPSMAP 6x. Mehr Raster-Kacheln sind nicht erprobt.
FAT32_MAX = (1 << 32) - 1
IMG_MAX_BLOCKS = 0xFFFF
TILES_CURRENT = 4000  # Zielgeräte GPSMAP 66/67, Montana 7xx: Fehler darüber
TILES_OLD = 2025      # ältere Geräte: Warnung darüber
RASTER_TILES_REF = 516
ZIP_SLACK = 1.10      # BaseCamp-ZIP höchstens IMG + 10 %


def img_stats(p: Path) -> dict:
    """Blockgrösse, Kacheln und Anzahl erweiterter TYP-Typen einer IMG (nur lesend)."""
    from imgread import ImgFile
    img = ImgFile(str(p))
    try:
        exts = [k.rsplit(".", 1) for k in img.subfiles]
        tiles = {n for n, e in exts if e in ("TRE", "GMP")}
        typ_ext = 0
        for k in (k for k in img.subfiles if k.endswith(".TYP")):
            d = img.read_subfile(k)
            for o in (0x33, 0x3D, 0x47):  # Index Punkte, Linien, Flächen: Offset, Satzlänge, Grösse
                off, rs, sz = struct.unpack_from("<IHI", d, o)
                for j in range(off, off + (sz if rs else 0), rs or 1):
                    # Bit 13 im Typfeld markiert einen erweiterten Typ (0x1ttss)
                    typ_ext += bool(int.from_bytes(d[j:j + 2], "little") & 0x2000)
        return dict(blocksize=img.blocksize, tiles=len(tiles), subfiles=len(img.subfiles),
                    raster=any(e == "GMP" for _, e in exts), typ_ext=typ_ext)
    finally:
        img.f.close()


def check_limits(pairs: list[tuple[Path, Path | None]], groups: list[tuple[list[Path], Path]] = ()) \
        -> tuple[list[str], list[str]]:
    """Prüft IMG und BaseCamp-ZIP gegen die Grenzwerte. → (Fehler, Warnungen).
    groups: (Gerätedateien, ZIP) für Varianten, deren gmapi mehrere Gerätedateien umfasst."""
    errs, warns = [], []
    for imgs, zp in groups:
        total = sum(i.stat().st_size for i in imgs)
        if zp.exists() and zp.stat().st_size > total * ZIP_SLACK:
            errs.append(f"{zp.name}: {zp.stat().st_size / 1e6:.1f} MB, grösser als die Gerätedateien + 10 %")
    for img, zp in pairs:
        n, size = img.name, img.stat().st_size
        st = img_stats(img)
        if size > FAT32_MAX:
            errs.append(f"{n}: {size / 2**30:.2f} GiB, FAT32 erlaubt höchstens 4 GiB − 1 Byte")
        if size > st["blocksize"] * IMG_MAX_BLOCKS:
            errs.append(f"{n}: mehr als {IMG_MAX_BLOCKS} Blöcke zu {st['blocksize']} B")
        if st["tiles"] > TILES_CURRENT:
            errs.append(f"{n}: {st['tiles']} Kacheln, Zielgeräte zeigen höchstens {TILES_CURRENT}")
        elif st["tiles"] > TILES_OLD:
            warns.append(f"{n}: {st['tiles']} Kacheln, ältere Geräte zeigen höchstens {TILES_OLD}")
        if st["raster"] and st["tiles"] > RASTER_TILES_REF:
            warns.append(f"{n}: {st['tiles']} Raster-Kacheln, mehr als die Referenz ({RASTER_TILES_REF})")
        if st["typ_ext"]:
            warns.append(f"{n}: TYP mit {st['typ_ext']} erweiterten Typen, ältere Geräte zeigen sie nicht")
        if zp is not None and zp.exists() and zp.stat().st_size > size * ZIP_SLACK:
            errs.append(f"{zp.name}: {zp.stat().st_size / 1e6:.1f} MB, grösser als IMG + 10 %")
        print(f"  Grenzwerte {n}: {size / 2**30:.2f} GiB, {st['tiles']} Kacheln, "
              f"{st['subfiles']} Subdateien, {st['typ_ext']} erweiterte TYP-Typen")
    return errs, warns


# ------------------------------------------------------------------ Texte
def md_sources(srcs: list[dict]) -> str:
    rows = ["| Datensatz | Ausgabe | Bezugsdatum | STAC-Collection |", "|---|---|---|---|"]
    for s in srcs:
        date = s.get("date") or (f"abgerufen {s['retrieved']}" if s.get("retrieved") else "")
        ed = s.get("edition", "")
        if s.get("sheets"):
            ed += f" ({s['sheets']} {'Blatt' if s['sheets'] == 1 else 'Blätter'})"
        rows.append(f"| {s['title']} | {ed} | {date} | {('`' + s['stac'] + '`') if s.get('stac') else '–'} |")
    return "\n".join(rows)


def write_docs(rel: Path, version: str, area_txt: str, vec: dict | None, pix: list[dict], vsrc, psrc,
               mkgmap: str) -> None:
    today = _dt.date.today().isoformat()
    if vec:
        d = rel / "vektor"
        d.mkdir(parents=True, exist_ok=True)
        (d / "QUELLSTAND.md").write_text(
            f"# Quellstand Helvetopo Vektor {version}\n\nGebiet: {area_txt}. Erstellt: {today}, "
            f"mkgmap {mkgmap}, Family-ID 7701.\n\n{md_sources(vsrc)}\n\n"
            f"Quellenangaben: `{ATTR_ST}`. Routen: `{ATTR_ASTRA}`. Kanuland: `{ATTR_SM}`. "
            "Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).\n", encoding="utf-8")
        (d / "README.md").write_text(VECTOR_README.format(version=version, area=area_txt, img=vec["img"],
                                                          zip=vec["zip"]), encoding="utf-8")
    if pix:
        d = rel / "pixel"
        d.mkdir(parents=True, exist_ok=True)
        lines = "\n".join(f"| {p['variant']} | `{p['img']}` | {p['fid']} | "
                          f"{', '.join('SMR' + str(s) for s in p['scales'])} |" for p in pix)
        (d / "QUELLSTAND.md").write_text(
            f"# Quellstand Helvetopo Pixel {version}\n\nGebiet: {area_txt}. Erstellt: {today}.\n\n"
            f"{md_sources(psrc)}\n\n| Variante | Datei | FID | Massstäbe |\n|---|---|---|---|\n{lines}\n\n"
            f"Quellenangabe: `{ATTR_ST}`. Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).\n",
            encoding="utf-8")
        files = "\n".join(f"- **{p['variant']}** (FID {p['fid']}): `{p['img']}`, BaseCamp `{p['zip']}`"
                          for p in pix)
        (d / "README.md").write_text(PIXEL_README.format(version=version, area=area_txt, files=files),
                                     encoding="utf-8")


def older_releases(public: Path, version: str, base_url: str) -> list[dict]:
    """Ältere Releases, die noch im öffentlichen Ordner auf dem NAS liegen (neueste zuerst).

    Das Portal verlinkt nur diese. Wer ein altes Release vom NAS löscht und das Manifest neu baut,
    entfernt damit auch die Links.
    """
    out = []
    for d in sorted((x for x in public.iterdir() if x.is_dir() and re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", x.name)),
                    key=lambda x: x.name, reverse=True):
        if d.name == version:
            continue
        files = sorted(f for f in d.iterdir() if f.is_file() and f.suffix.lower() in (".img", ".zip"))
        if not files:
            continue
        sums = next((f.name for f in d.glob("*SHA256SUMS*")), None)
        out.append(dict(release=d.name, baseUrl=base_url.format(v=d.name), checksums=sums,
                        files=[dict(name=f.name, size=f.stat().st_size) for f in files]))
    return out


def publish_docs(files: Path, version: str, products: list[dict], copy: bool = True) -> None:
    """README, QUELLSTAND und LICENSE-KARTEN.md je Release auf den Download-Server (files/info/).

    Endnutzer brauchen so kein GitHub. Die Pfade in products[].docs werden relativ zu baseUrl
    (info/<art>/README.md, info/LICENSE-KARTEN.md). Der Link auf die Lizenz wird an die neue Tiefe angepasst.
    """
    rel = f"releases/{version}/"
    done = set()
    for p in products:
        d = p.get("docs")
        if not d:
            continue
        for k, path in d.items():
            new = "info/" + (path[len(rel):] if path.startswith(rel) else path)
            if copy and path not in done:
                src, dst = REPO / path, files / new
                dst.parent.mkdir(parents=True, exist_ok=True)
                txt = src.read_text(encoding="utf-8").replace("](../../../LICENSE-KARTEN.md)", "](../LICENSE-KARTEN.md)")
                dst.write_text(txt, encoding="utf-8")
                done.add(path)
            d[k] = new


VECTOR_README = """# Helvetopo Vektor {version}

Vektorkarte im Stil der Landeskarte 1:25'000 für Garmin-Geräte und BaseCamp. Gebiet: {area}.
Inoffizielle Karte: kein Produkt von swisstopo, ASTRA, SchweizMobil oder Garmin.

## Dateien
- `{img}`: Gerätedatei (Basiskarte mit Höhenlinien, FID 7701).
  In den Ordner `Garmin/` auf dem Gerät oder der microSD-Karte kopieren.
- `Helvetopo_Routen_…img`: Wanderwege und SchweizMobil-Routen als eigenes Overlay (FID 7702).
  Ebenfalls nach `Garmin/` kopieren. Am Gerät unter Karteninformationen einzeln schaltbar. Es passt
  auch über die Pixelkarte und das Luftbild.
- `{zip}`: BaseCamp-Paket. Entpacken und den `.gmap`-Ordner kopieren nach
  `C:\\ProgramData\\Garmin\\Maps\\` (Windows) bzw. `~/Library/Application Support/Garmin/Maps/` (macOS).
  BaseCamp zeigt nur eine Karte gleichzeitig. Deshalb sind die Routen im BaseCamp-Paket eingebaut.

Die Prüfsummen stehen in `Helvetopo_{version}_SHA256SUMS.txt`.

## Routing
- Fuss und Velo aus swissTLM3D und den SchweizMobil-Routen. Wanderwege werden bevorzugt.
- **Velo/MTB:** im Aktivitätsprofil „Mautstrassen vermeiden“ einschalten. Die Karte nutzt das
  Maut-Merkmal als Hinweis auf Haupt- und Kantonsstrassen ohne Veloroute. So folgt die Route
  bevorzugt Veloland.
- **Auto und Wandern:** „Mautstrassen vermeiden“ ausschalten. Die Karte kennt keine Mautgebühren.
- Auto-Routing ist nur topografisch (keine Einbahnen, Abbiegeverbote, Tempolimits) und nicht zur
  Fahrzeugnavigation geeignet.

## Quellen und Lizenz
Quellenangaben: `©swisstopo`. Routen: `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`.
Kanuland: `Stiftung SchweizMobil`. Datenstand: [QUELLSTAND.md](QUELLSTAND.md).
Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md). Ohne Gewähr.
"""

PIXEL_README = """# Helvetopo Pixel {version} (experimentell)

Swiss Map Raster von swisstopo als Garmin-IMG, je Zoomstufe der passende Massstab bis 1:1'000'000.
Gebiet: {area}. Inoffizielle Karte: kein Produkt von swisstopo oder Garmin.

## Varianten
{files}

Unterhalb des feinsten Massstabs wird das Bild vergrössert. Jede IMG in den Ordner `Garmin/` auf
dem Gerät oder der microSD-Karte kopieren und unter Karteneinstellungen einblenden. Für BaseCamp das
ZIP entpacken und den `.gmap`-Ordner nach `C:\\ProgramData\\Garmin\\Maps\\` bzw.
`~/Library/Application Support/Garmin/Maps/` kopieren. Detailgrad „Normal“ oder höher wählen.

Die feinen Linien im Bild sind das gedruckte Kilometernetz der Landeskarte.
Prüfsummen: `Helvetopo_{version}_SHA256SUMS.txt`.

## Quellen und Lizenz
Quellenangabe: `©swisstopo`. Datenstand: [QUELLSTAND.md](QUELLSTAND.md).
Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md). Ohne Gewähr.
"""


# ------------------------------------------------------------------ Hauptteil
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--area", default="testgebiet", choices=list(AREAS))
    ap.add_argument("--vector", type=Path, help="OUT-Ordner von build_all.sh")
    ap.add_argument("--pixel", type=Path, help="Ordner mit Unterordnern je Variante (release.py --out)")
    ap.add_argument("--routes", type=Path,
                    help="Ordner mit dem Routen-Overlay (routen.py overlay): Helvetopo_Routen_<Gebiet>_<v>.img")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--repo-url", default="https://github.com/sackmesser-dev/helvetopo")
    ap.add_argument("--no-zip", action="store_true", help="BaseCamp-ZIPs nicht neu packen, falls vorhanden")
    ap.add_argument("--store", type=Path, help="Schweiz: Ablage der fertigen Builds (HELVETOPO_STORE), "
                    "z. B. <Ablage>/helvetopo/.build")
    ap.add_argument("--base-url", help=f"baseUrl im Manifest (Schweiz: {BASE_URL.format(v='<v>')})")
    ap.add_argument("--dry-run", action="store_true", help="Schweiz: nur Manifest-Entwurf, keine Links, ZIPs, Prüfsummen")
    ap.add_argument("--site", action="store_true",
                    help="Portal mit diesem Manifest nach work/portal/site/ legen (Vorschau, Dateien verlinkt)")
    a = ap.parse_args()
    if a.area == "schweiz":
        if not a.store:
            sys.exit("--area schweiz braucht --store (Ablage der Builds)")
        main_schweiz(a)
        if a.site and not a.dry_run:
            make_site(a.out or REPO / "work" / "release" / f"{a.version}-ch", a.version)
        return

    ftag, area_txt, bbox = AREAS[a.area]
    out = a.out or REPO / "work" / "release" / a.version
    files = out / "files"
    files.mkdir(parents=True, exist_ok=True)
    rel = REPO / "releases" / a.version
    cache_p = out / "stac_cache.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    license_txt = (REPO / "LICENSE-KARTEN.md").read_text(encoding="utf-8")
    products, vec, pix = [], None, []
    mkgmap = "r4924"

    vsrc = vector_sources(bbox, cache) if a.vector else []
    psrc = pixel_sources(bbox) if a.pixel else []
    cache_p.write_text(json.dumps(cache, indent=1, ensure_ascii=False))

    def fentry(p: Path, target: str, **kw) -> dict:
        print(f"  {p.name}: {p.stat().st_size / 1e6:.1f} MB")
        return dict(target=target, format=p.suffix[1:], name=p.name, size=p.stat().st_size, sha256=sha256(p), **kw)

    if a.vector:
        dist = a.vector / "dist"
        base = f"{PREFIX}_Vektor_{ftag}_{a.version}"
        img, zp = files / f"{base}.img", files / f"{base}_BaseCamp.zip"
        link_or_copy(dist / "gmapsupp.img", img)
        gmap = next((dist / "BaseCamp").glob("*.gmap"))
        if not (a.no_zip and zp.exists()):
            zip_dir(zp, gmap, {"README.txt": (dist / "README.txt").read_text(encoding="utf-8"),
                               "LICENSE.txt": (dist / "LICENSE.txt").read_text(encoding="utf-8"),
                               "LICENSE-KARTEN.md": license_txt})
        vec = dict(img=img.name, zip=zp.name)
        products.append(dict(
            id="vektor", group="vektor", kind="vektor", fid=7701, area=a.area,
            sources=[s["id"] for s in vsrc],
            docs=dict(readme=f"releases/{a.version}/vektor/README.md", license="LICENSE-KARTEN.md",
                      sources=f"releases/{a.version}/vektor/QUELLSTAND.md"),
            files=[fentry(img, "device", primary=True), fentry(zp, "basecamp", os=["windows", "macos"])]))

    if a.pixel:
        for v, (fid, scales) in PIXEL.items():
            d = a.pixel / v
            base = f"{PREFIX}_Pixel_{v}_{ftag}_{a.version}"
            src_img = d / f"{base}.img"
            if not src_img.exists():
                print(f"  (fehlt: {src_img}, Variante übersprungen)")
                continue
            img, zp = files / f"{base}.img", files / f"{base}_BaseCamp.zip"
            link_or_copy(src_img, img)
            qs = (d / f"{base}_QUELLSTAND.txt").read_text(encoding="utf-8")
            gmap = next((d / "gmapi").glob("*.gmap"))
            if not (a.no_zip and zp.exists()):
                zip_dir(zp, gmap, {"QUELLSTAND.txt": qs, "LICENSE-KARTEN.md": license_txt,
                                   "README.txt": PIXEL_README.format(version=a.version, area=area_txt,
                                                                     files=f"- {v} (FID {fid})")})
            pix.append(dict(variant=v, fid=fid, scales=scales, img=img.name, zip=zp.name))
            products.append(dict(
                id=f"pixel-{v}", group="pixel", kind="pixel", fid=fid,
                scale=dict(min=scales[0] * 1000, max=scales[-1] * 1000), area=a.area, experimental=True,
                sources=[f"smr{s}" for s in scales],
                docs=dict(readme=f"releases/{a.version}/pixel/README.md", license="LICENSE-KARTEN.md",
                          sources=f"releases/{a.version}/pixel/QUELLSTAND.md"),
                files=[fentry(img, "device", primary=True), fentry(zp, "basecamp", os=["windows", "macos"])]))

    if a.routes:
        base = f"{PREFIX}_Routen_{ftag}_{a.version}"
        src_img = a.routes / f"{base}.img"
        img = files / f"{base}.img"
        link_or_copy(src_img, img)
        products.append(dict(
            id="routen", group="vektor", kind="overlay", fid=7702, area=a.area,
            sources=["schweizmobil", "wanderwege"],
            docs=dict(readme=f"releases/{a.version}/vektor/README.md", license="LICENSE-KARTEN.md",
                      sources=f"releases/{a.version}/vektor/QUELLSTAND.md"),
            files=[fentry(img, "device", primary=True)]))

    errs, warns = check_limits([(files / p["files"][0]["name"],
                                 files / p["files"][1]["name"] if len(p["files"]) > 1 else None)
                                for p in products])
    for w in warns:
        print(f"  Warnung: {w}")
    if errs:
        for e in errs:
            print(f"  FEHLER: {e}", file=sys.stderr)
        sys.exit(f"Grenzwertprüfung: {len(errs)} Fehler, kein Manifest geschrieben")

    sums = files / f"{PREFIX}_{a.version}_SHA256SUMS.txt"
    sums.write_text("".join(f"{f['sha256']}  {f['name']}\n" for p in products for f in p["files"]))
    write_docs(rel, a.version, area_txt, vec, pix, vsrc, psrc, mkgmap)
    publish_docs(files, a.version, products)

    manifest = dict(
        schema=2, release=a.version, date=_dt.date.today().isoformat(), prefix=PREFIX,
        baseUrl=f"files/{a.version}/",
        repo=dict(url=a.repo_url, ref=f"v{a.version}"), checksums=sums.name,
        attribution=dict(swisstopo=ATTR_ST, astra=ATTR_ASTRA, schweizmobil=ATTR_SM),
        area=a.area, sources=vsrc + psrc,
        regions=[], groups=json.loads((PORTAL / "manifest.json").read_text(encoding="utf-8"))["groups"],
        products=products)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifest: {out / 'manifest.json'}\nPrüfsummen: {sums}\nDoku: {rel}")
    if a.site:
        make_site(out, a.version)


# ------------------------------------------------------------------ Schweiz (Ablage auf dem NAS)
PIXEL_README_CH = """# Helvetopo Pixel {version} (experimentell)

Swiss Map Raster von swisstopo als Garmin-IMG. Jede Zoomstufe zeigt den passenden Massstab bis
1:1'000'000. Gebiet: Schweiz und Liechtenstein. Inoffizielle Karte: kein Produkt von swisstopo oder Garmin.

## Varianten

{files}

Eine Gerätedatei bleibt unter 4 GiB (FAT32). Darum gibt es 25-1000 in zwei Hälften und 10-1000 in vier
Teilen. Die Hälften und Teile überlappen nicht. Die Karte im Portal zeigt die Grenzen.

## Installation

- Gerät: Jede IMG in den Ordner `Garmin/` auf dem Gerät oder der microSD-Karte kopieren. Die Karte unter
  Karteneinstellungen einblenden. Kartendetail „Normal“ wählen. Mit „Weniger“ wechselt das Gerät eine
  Stufe früher auf den gröberen Massstab.
- BaseCamp: Je Variante gibt es ein ZIP für die ganze Schweiz. Das ZIP entpacken und den `.gmap`-Ordner
  nach `C:\\ProgramData\\Garmin\\Maps\\` (Windows) bzw. `~/Library/Application Support/Garmin/Maps/`
  (macOS) kopieren. Die Wanderwege und SchweizMobil-Routen sind darin eingebaut.

Unterhalb des feinsten Massstabs vergrössert das Gerät das Bild. Die feinen Linien im Bild sind das
gedruckte Kilometernetz der Landeskarte. Prüfsummen: `Helvetopo_{version}_SHA256SUMS.txt`.

## Quellen und Lizenz

Quellenangabe: `©swisstopo`. BaseCamp-Pakete mit Routen zusätzlich: `{astra}`.
Datenstand: [QUELLSTAND.md](QUELLSTAND.md). Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).
Ohne Gewähr.
"""

LUFTBILD_README = """# Helvetopo Luftbild {version} (experimentell)

Orthofotos SWISSIMAGE von swisstopo als Garmin-IMG. Gebiet: Schweiz und Liechtenstein.
Inoffizielle Karte: kein Produkt von swisstopo oder Garmin.

## Dateien

{files}

- Luftbild Standard (FID 7708): ganze Schweiz in einer Datei, ca. 2,6 m bis 82 m je Pixel.
- Luftbild Detail (FID 7707): Gerätedateien je Teilgebiet, ca. 0,64 m bis 2,6 m je Pixel. Detail ergänzt
  Standard für die grossen Massstäbe. Am Gerät beide Karten einblenden. Detail liegt über Standard.
  Das BaseCamp-Paket von Detail zeigt nur die grossen Massstäbe.

## Installation

- Gerät: Die IMG in den Ordner `Garmin/` auf dem Gerät oder der microSD-Karte kopieren. Die Karte unter
  Karteneinstellungen einblenden. Kartendetail „Normal“ wählen.
- BaseCamp: Das ZIP entpacken und den `.gmap`-Ordner nach `C:\\ProgramData\\Garmin\\Maps\\` (Windows)
  bzw. `~/Library/Application Support/Garmin/Maps/` (macOS) kopieren. Die Wanderwege und
  SchweizMobil-Routen sind darin eingebaut.

Prüfsummen: `Helvetopo_{version}_SHA256SUMS.txt`.

## Quellen und Lizenz

Quellenangabe: `©swisstopo`. BaseCamp-Paket mit Routen zusätzlich: `{astra}`.
Datenstand: [QUELLSTAND.md](QUELLSTAND.md). Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).
Ohne Gewähr.
"""


def write_docs_ch(rel: Path, version: str, area_txt: str, pix: list[dict], luft: list[dict], psrc, lsrc) -> None:
    """README und QUELLSTAND für Pixel und Luftbild (Schweiz)."""
    today = _dt.date.today().isoformat()
    d = rel / "pixel"
    d.mkdir(parents=True, exist_ok=True)
    rows, items = [], []
    for p in pix:
        n = len(p["imgs"])
        dev = f"`{p['imgs'][0]}`" if n == 1 else f"{n} Dateien `Helvetopo_Pixel_{p['variant']}_<Gebiet>_{version}.img`"
        rows.append(f"| {p['variant']} | {dev} | {p['fid']} | {', '.join('SMR' + str(s) for s in p['scales'])} |")
        where = {"schweiz": "eine Datei für die ganze Schweiz", "haelften": "zwei Hälften: West und Ost",
                 "teile": "vier Teile: West, Süd, Mitte und Ost", "regionen": "neun Regionen"}[p["area"]]
        items.append(f"- **{p['variant']}** (FID {p['fid']}): {where}. BaseCamp: `{p['zip']}`.")
    (d / "QUELLSTAND.md").write_text(
        f"# Quellstand Helvetopo Pixel {version}\n\nGebiet: {area_txt}. Erstellt: {today}.\n\n{md_sources(psrc)}\n\n"
        "| Variante | Gerätedateien | FID | Massstäbe |\n|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        f"Quellenangabe: `{ATTR_ST}`. Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).\n",
        encoding="utf-8")
    (d / "README.md").write_text(PIXEL_README_CH.format(version=version, files="\n".join(items), astra=ATTR_ASTRA),
                                 encoding="utf-8")
    if luft:
        d = rel / "luftbild"
        d.mkdir(parents=True, exist_ok=True)
        items, rows = [], []
        for x in luft:
            n = len(x["imgs"])
            dev = f"`{x['imgs'][0]}`: Gerätedatei" if n == 1 else \
                f"{n} Gerätedateien, je Teilgebiet eine, ohne Überlappung: " + ", ".join(f"`{i}`" for i in x["imgs"])
            items.append(f"- {dev} (FID {x['fid']}).\n- `{x['zip']}`: BaseCamp-Paket für die ganze Schweiz.")
            src = x["source"]
            rows.append(f"| {x['fid']} | {n} | {LUFTBILD_USED[x['fid']]} | {src['tiles']} | {src['edition']} |")
        items = "\n".join(items)
        (d / "QUELLSTAND.md").write_text(
            f"# Quellstand Helvetopo Luftbild {version}\n\nGebiet: {area_txt}. Erstellt: {today}.\n\n"
            f"{md_sources(lsrc)}\n\n| FID | Gerätedateien | verwendet | Kacheln zu 1 km | Befliegungen |\n"
            "|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
            f"Quellenangabe: `{ATTR_ST}`. Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).\n",
            encoding="utf-8")
        (d / "README.md").write_text(LUFTBILD_README.format(version=version, files=items, astra=ATTR_ASTRA),
                                     encoding="utf-8")


def main_schweiz(a) -> None:
    """Release Schweiz aus der Ablage (--store). Downloads als Links, BaseCamp-ZIPs neu."""
    v, store = a.version, a.store
    ftag, area_txt, bbox = AREAS["schweiz"]
    out = (a.out or REPO / "work" / "release" / f"{v}-ch").resolve()
    public = store.resolve().parent
    if out == public or public in out.parents:
        sys.exit(f"{out} liegt im öffentlichen Bereich ({public}). Die Veröffentlichung gibt der Benutzer frei.")
    files = out / "files"
    files.mkdir(parents=True, exist_ok=True)
    dirs = dict(vektor=store / "vektor" / "ch" / v, routen=store / "routen" / "ch" / v,
                pixel=store / "pixel" / v, luftbild=store / "luftbild" / v)
    for k, d in dirs.items():
        if not d.is_dir():
            sys.exit(f"Ablage fehlt: {d} ({k})")
    portal = json.loads((PORTAL / "manifest.json").read_text(encoding="utf-8"))
    license_txt = (REPO / "LICENSE-KARTEN.md").read_text(encoding="utf-8")
    cache_p = out / "stac_cache.json"
    cache = json.loads(cache_p.read_text()) if cache_p.exists() else {}
    vsrc = vector_sources(bbox, cache)
    cache_p.write_text(json.dumps(cache, indent=1, ensure_ascii=False))
    products, pairs, groups, zips, pix, luft = [], [], [], [], [], []
    pixel_qs = []

    def dev(src: Path, name: str, region: str | None = None) -> dict:
        if not src.is_file():
            sys.exit(f"fehlt: {src}")
        dst = files / name
        if not a.dry_run:
            link_or_copy(src, dst, symlink=True)
        pairs.append((src if a.dry_run else dst, None))
        e = dict(target="device", format="img")
        if region:
            e["region"] = region
        e.update(name=name, size=src.stat().st_size, _src=src, primary=True)
        return e

    def bc(gmap: Path, name: str, extra: dict) -> dict:
        if not gmap.is_dir():
            sys.exit(f"fehlt: {gmap}")
        zips.append((files / name, gmap, extra))
        est = sum(f.stat().st_size for f in gmap.rglob("*") if f.is_file())
        return dict(target="basecamp", format="zip", os=["windows", "macos"], name=name, size=est,
                    _zip=files / name)

    def docs(kind):
        return dict(readme=f"releases/{v}/{kind}/README.md", license="LICENSE-KARTEN.md",
                    sources=f"releases/{v}/{kind}/QUELLSTAND.md")

    # Vektor und Routen
    vd = dirs["vektor"]
    vimg = f"{PREFIX}_Vektor_{ftag}_{v}.img"
    vzip = f"{PREFIX}_Vektor_{ftag}_{v}_BaseCamp.zip"
    vfiles = [dev(vd / "gmapsupp.img", vimg),
              bc(next((vd / "BaseCamp").glob("*.gmap")), vzip,
                 {"README.txt": (vd / "README.txt").read_text(encoding="utf-8"),
                  "LICENSE.txt": (vd / "LICENSE.txt").read_text(encoding="utf-8"), "LICENSE-KARTEN.md": license_txt})]
    pairs[-1] = (pairs[-1][0], files / vzip)
    products.append(dict(id="vektor", group="vektor", kind="vektor", fid=7701, area="schweiz",
                         sources=[s["id"] for s in vsrc if s["id"] not in ("wanderwege", "kanuland")],
                         docs=docs("vektor"), files=vfiles))
    rimg = f"{PREFIX}_Routen_{ftag}_{v}.img"
    products.append(dict(id="routen", group="routen", kind="overlay", fid=7702, area="schweiz",
                         sources=["schweizmobil", "wanderwege"], docs=docs("vektor"),
                         files=[dev(dirs["routen"] / rimg, rimg)]))

    # Pixel
    pd = dirs["pixel"]
    for var, area in PIXEL_AREA.items():
        fid, scales = PIXEL[var]
        fl, imgs, qs = [], [], []
        for r in AREA_REGIONS[area]:
            tag = REGION_FILE[r] if r else ftag
            name = f"{PREFIX}_Pixel_{var}_{tag}_{v}.img"
            fl.append(dev(pd / name, name, r))
            imgs.append(pd / name)
            q = pd / f"{PREFIX}_Pixel_{var}_{tag}_{v}_QUELLSTAND.txt"
            if q.exists():
                qs.append(q.read_text(encoding="utf-8"))
        qch = pd / f"{PREFIX}_Pixel_{var}_{ftag}_{v}_QUELLSTAND.txt"
        qtext = qch.read_text(encoding="utf-8") if qch.exists() else "\n".join(qs)
        pixel_qs += qs + ([qtext] if qch.exists() else [])
        zname = f"{PREFIX}_Pixel_{var}_{ftag}_{v}_BaseCamp.zip"
        fl.append(bc(pd / "BaseCamp" / f"{PREFIX} Pixel {var} {v}.gmap", zname,
                     {"QUELLSTAND.txt": qtext, "LICENSE-KARTEN.md": license_txt,
                      "README.txt": PIXEL_README_CH.format(version=v, astra=ATTR_ASTRA,
                                                           files=f"- {var} (FID {fid})")}))
        groups.append((imgs, files / zname))
        pix.append(dict(variant=var, fid=fid, scales=scales, area=area, imgs=[f["name"] for f in fl[:-1]], zip=zname))
        products.append(dict(id=f"pixel-{var}", group="pixel", kind="pixel", fid=fid,
                             scale=dict(min=scales[0] * 1000, max=scales[-1] * 1000),
                             area=MANIFEST_AREA.get(area, area), experimental=True,
                             sources=[f"smr{s}" for s in scales] + ["swissboundaries3d"], docs=docs("pixel"),
                             files=fl))
    psrc = pixel_sources_qs(pixel_qs)

    # Luftbild
    ld = dirs["luftbild"]
    lsrc = []
    lsi = []
    for pid, (fid, bname, rname, gname, parts_f) in LUFTBILD.items():
        if parts_f:
            pf = ld / parts_f
            if not pf.is_file():
                sys.exit(f"fehlt: {pf}")
            tags = [(LUFTBILD_REGION_ID.get(f["properties"]["id"], f["properties"]["id"]), part_file(f["properties"]["id"]))
                    for f in json.loads(pf.read_text(encoding="utf-8"))["features"]]
        else:
            tags = [(None, ftag)]
        fl, srcs, qts, isrc = [], [], [], []
        for r, tag in tags:
            src = ld / f"{PREFIX}_{bname}_{tag}_{v}.img"
            qt = (ld / f"{PREFIX}_{bname}_{tag}_{v}_QUELLSTAND.txt").read_text(encoding="utf-8")
            qts.append(qt)
            isrc.append(swissimage_source(qt))
            srcs.append(src)
            fl.append(dev(src, f"{PREFIX}_{rname}_{tag}_{v}.img", r))
        lsi += isrc
        zname = f"{PREFIX}_{rname}_{ftag}_{v}_BaseCamp.zip"
        gmap = ld / "BaseCamp" / f"{PREFIX} {gname} {v}.gmap"
        names = [f["name"] for f in fl]
        flist = f"- {names[0]} (FID {fid})" if len(names) == 1 else \
            f"- {len(names)} Gerätedateien {PREFIX}_{rname}_<Teil>_{v}.img (FID {fid})"
        fl.append(bc(gmap, zname, {"QUELLSTAND.txt": "\n".join(qts), "LICENSE-KARTEN.md": license_txt,
                                   "README.txt": LUFTBILD_README.format(version=v, astra=ATTR_ASTRA, files=flist)}))
        groups.append((srcs, files / zname))
        luft.append(dict(fid=fid, imgs=names, zip=zname, source=merge_swissimage(isrc)))
        products.append(dict(id=pid, group="luftbild", kind="luftbild", fid=fid,
                             area="regionen" if parts_f else "schweiz",
                             experimental=True, sources=["swissimage", "swissboundaries3d"], docs=docs("luftbild"),
                             files=fl))
    lsrc = [merge_swissimage(lsi)]

    # Geplante Produkte aus dem Portal-Manifest
    known = {p["id"] for p in products}
    planned = [{k: x for k, x in p.items() if k != "files"} for p in portal["products"]
               if p.get("planned") and p["id"] not in known]

    # BaseCamp-ZIPs, Prüfsummen
    if not a.dry_run:
        for zp, gmap, extra in zips:
            if a.no_zip and zp.exists():
                continue
            print(f"  ZIP {zp.name} …", flush=True)
            zip_dir(zp, gmap, extra)
    errs, warns = check_limits(pairs if not a.dry_run else [(i, None) for i, _ in pairs],
                               groups if not a.dry_run else [])
    for w in warns:
        print(f"  Warnung: {w}")
    if errs:
        for e in errs:
            print(f"  FEHLER: {e}", file=sys.stderr)
        sys.exit(f"Grenzwertprüfung: {len(errs)} Fehler, kein Manifest geschrieben")
    for p in products:
        for f in p["files"]:
            src = f.pop("_src", None) or f.pop("_zip", None)
            if not a.dry_run:
                f["size"] = src.stat().st_size
                print(f"  sha256 {f['name']} …", flush=True)
                f["sha256"] = sha256(src)
            else:
                f["sha256"] = None
    sums = files / f"{PREFIX}_{v}_SHA256SUMS.txt"
    if not a.dry_run:
        sums.write_text("".join(f"{f['sha256']}  {f['name']}\n" for p in products for f in p["files"]))
        rel = REPO / "releases" / v
        write_docs(rel, v, area_txt, dict(img=vimg, zip=vzip), [], vsrc, [], "r4924")
        write_docs_ch(rel, v, area_txt, pix, luft, psrc, lsrc)
    publish_docs(files, v, products, copy=not a.dry_run)
    seen, sources = set(), []
    for x in vsrc + psrc + lsrc:
        if x["id"] not in seen:
            seen.add(x["id"])
            sources.append(x)
    manifest = dict(
        schema=2, release=v, date=_dt.date.today().isoformat(), prefix=PREFIX,
        baseUrl=a.base_url or BASE_URL.format(v=v),
        repo=dict(url=a.repo_url, ref=f"v{v}"), checksums=sums.name,
        attribution=dict(swisstopo=ATTR_ST, astra=ATTR_ASTRA, schweizmobil=ATTR_SM),
        area="schweiz", sources=sources, regions=portal["regions"], groups=portal["groups"],
        products=products + planned,
        older=older_releases(public, v, BASE_URL) if not a.base_url else [])
    mf = out / ("manifest.dry.json" if a.dry_run else "manifest.json")
    mf.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifest: {mf}" + ("" if a.dry_run else f"\nPrüfsummen: {sums}\nDoku: {REPO / 'releases' / v}"))


def make_site(out: Path, version: str) -> None:
    """Vorschau des Portals mit echtem Manifest: work/portal/site/ (Dateien per Symlink)."""
    import subprocess
    site = REPO / "work" / "portal" / "site"
    if site.exists():
        shutil.rmtree(site)
    shutil.copytree(PORTAL, site, ignore=shutil.ignore_patterns("manifest.json", "data.js", ".DS_Store"))
    shutil.copy2(out / "manifest.json", site / "manifest.json")
    (site / "files").mkdir()
    (site / "files" / version).symlink_to(out / "files")
    subprocess.run([sys.executable, "-I", str(REPO / "src" / "portal" / "build_data.py"), "--site", str(site)],
                   check=True)
    print(f"Portal-Vorschau: python3 -m http.server 8765 --directory {site.relative_to(REPO)}")


if __name__ == "__main__":
    main()
