"""Wanderwege und SchweizMobil-Routen über Pixelkarte und Luftbild.

Zwei Wege, je nach Programm:

1. Gerät (GPSMAP/Montana): eigenes Kartenprodukt „Helvetopo Routen“ (FID 7702), transparent, Draw-Priority 31.
   Es liegt als eigene IMG neben der Raster-IMG auf der Karte und ist am Gerät einzeln ein- und ausschaltbar.
   Die Raster-IMG hat Priority 29 (release.RASTER_PRIORITY), die Routen liegen also oben.
     python3 -I routen.py overlay --pbf work/raster_img/routen/routes.osm.pbf --region testgebiet
     → Helvetopo_Routen_Testgebiet_2026-11.img + _QUELLSTAND.txt

2. BaseCamp zeigt nur ein Kartenprodukt gleichzeitig. Deshalb kommen transparente Routen-Kacheln mit der FID
   der Rasterkarte in deren gmapi (wie die Familie 7701 der Vektorkarte mit 77011001…). Map-IDs der
   Routen-Kacheln: <FID>9001 … <FID>9999 (<FID>9000 ist die Übersicht, <FID>0001–8999 sind Rasterzellen).
     python3 -I routen.py gmapi --img <raster.img> --fid 7705 --name "…" --pbf routes.osm.pbf
   Dasselbe als Option der Raster-Builds: release.py/luftbild.py --gmapi --routes routes.osm.pbf.

Quellenangaben: mit Routen gehört „Bundesamt für Strassen, Kanton, Stiftung SchweizMobil“ ins Copyright
(AGENTS.md); Prüfung: REQUIRE_ASTRA=yes src/build/check_license.sh <ordner>.

Routen-PBF: src/routes/convert_routes.py (Tag-Schema docs/vektor/routen.md). Style: src/style/routes unverändert,
also dieselben Stufen wie in der Vektorkarte (Quelle src/routes/make_style.py).
TYP-Quelltext src/style/typ/routes.txt (die FID wird je Familie ersetzt).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.dirname(HERE))
import paths  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
MKGMAP = str(paths.MKGMAP)
SPLITTER = str(paths.SPLITTER)
STYLE = os.path.join(REPO, "src", "style", "routes")
TYP = os.path.join(REPO, "src", "style", "typ", "routes.txt")
OUT_DEFAULT = os.path.join(REPO, "work", "raster_img", "routen")

FID_OVERLAY = 7702
ROUTES_PRIORITY = 31          # über Raster (29) und Vektor (25); 31 = höchster Wert, den das Original nutzt
ASTRA = "Bundesamt für Strassen, Kanton, Stiftung SchweizMobil"
# Garmin zeigt am Gerät nur die zweite Copyright-Zeile → Pflichtangaben in beiden Zeilen (wie build_all.sh)
COPYRIGHT = f"©swisstopo; {ASTRA}"
LICENSE = ("Helvetopo Routen (inoffiziell, keine Karte von swisstopo oder SchweizMobil). "
           "Wanderwege: ©swisstopo, swissTLM3D Wanderwege (OGD, https://www.swisstopo.admin.ch/ogd-conditions). "
           f"Wanderland, Veloland, Mountainbikeland, Skatingland: {ASTRA} "
           "(Opendata BY, https://opendata.swiss/terms-of-use#terms_by). "
           "Kanuland (falls enthalten): Stiftung SchweizMobil (Open Data BY). Erstellt mit mkgmap (GPL).")
AREA_NAMES = {"testgebiet": "Testgebiet", "schweiz": "Schweiz"}


def typ_for(fid: int, workdir: str) -> str:
    """TYP-Quelltext der Routen mit der FID der Zielfamilie."""
    with open(TYP, encoding="utf-8") as f:
        txt = f.read()
    txt, n = re.subn(r"(?m)^FID=\d+", f"FID={fid}", txt)
    assert n == 1, "FID-Zeile im Routen-TYP fehlt"
    dest = os.path.join(workdir, f"routes_{fid}.txt")
    with open(dest, "w", encoding="utf-8") as f:
        f.write(txt)
    return dest


def build_tiles(pbf: str, fid: int, first_id: int, workdir: str, area_name: str,
                priority: int = ROUTES_PRIORITY, max_nodes: int = 1600000) -> list[str]:
    """Transparente Routen-Kacheln (*.img) für die Familie fid; grosse PBF werden mit splitter geteilt."""
    os.makedirs(workdir, exist_ok=True)
    for f in glob.glob(os.path.join(workdir, "[0-9]*.img")) + glob.glob(os.path.join(workdir, "*.tdb")):
        os.remove(f)
    cf, lf = os.path.join(workdir, "copyright.txt"), os.path.join(workdir, "license.txt")
    with open(cf, "w", encoding="utf-8") as f:
        f.write(f"{COPYRIGHT}\n{COPYRIGHT}\n")
    with open(lf, "w", encoding="utf-8") as f:
        f.write(LICENSE + "\n")
    desc = "Helvetopo Routen ©swisstopo ASTRA SchweizMobil"
    if os.path.getsize(pbf) > 20e6:
        sd = os.path.join(workdir, "split")
        shutil.rmtree(sd, ignore_errors=True)
        subprocess.run(["java", "-Xmx4g", "-jar", SPLITTER, f"--mapid={first_id}", f"--max-nodes={max_nodes}",
                        "--output=pbf", f"--output-dir={sd}", f"--description={desc}", pbf],
                       check=True, capture_output=True)
        inputs = ["-c", os.path.join(sd, "template.args")]
    else:
        inputs = [f"--description={desc}", f"--mapname={first_id}", pbf]
    args = ["java", "-Xmx4g", "-jar", MKGMAP, f"--output-dir={workdir}", f"--style-file={STYLE}",
            f"--family-id={fid}", "--product-id=1", "--family-name=Helvetopo Routen",
            "--series-name=Helvetopo Routen", f"--area-name={area_name}",
            f"--overview-mapname={fid}0000", f"--overview-mapnumber={fid}0000",
            "--code-page=1252", "--lower-case", "--transparent", f"--draw-priority={priority}",
            "--merge-lines", "--reduce-point-density=2", f"--copyright-file={cf}", f"--license-file={lf}",
            *inputs]
    r = subprocess.run(args, capture_output=True, text=True)
    with open(os.path.join(workdir, "mkgmap.log"), "w") as f:
        f.write(r.stdout + r.stderr)
    if r.returncode:
        raise RuntimeError(r.stdout + r.stderr)
    tiles = sorted(p for p in glob.glob(os.path.join(workdir, "[0-9]*.img"))
                   if not os.path.basename(p).endswith("0000.img"))
    if not tiles or int(os.path.basename(tiles[-1])[:8]) > fid * 10000 + 9999:
        raise RuntimeError(f"Routen-Kacheln ausserhalb von {fid}9001–{fid}9999: {tiles}")
    return tiles


def quellstand_text(product: str, fid: int, pbf: str) -> str:
    log = os.path.join(os.path.dirname(pbf), "convert.log")
    t = [f"Quellstand {product}", f"Erstellt: {_dt.date.today().isoformat()}, Family-ID {fid}", "",
         "- Wanderwege: swissTLM3D Wanderwege, ©swisstopo (OGD), Collection ch.swisstopo.swisstlm3d-wanderwege",
         f"- Wanderland, Veloland, Mountainbikeland, Skatingland (ch.astra.*): {ASTRA} (Opendata BY)"]
    if os.path.exists(log) and re.search(r"(?m)^kanuland/", open(log, encoding="utf-8").read()):
        t.append("- Kanuland: Stiftung SchweizMobil (Open Data BY)")
    t += ["", "Lizenz: " + LICENSE]
    return "\n".join(t) + "\n"


def build_overlay(pbf: str, out: str, region: str, version: str) -> str:
    """Eigenes Kartenprodukt FID 7702 als IMG fürs Gerät (gmapsupp-Aufbau, mit TYP)."""
    area = AREA_NAMES.get(region, region.capitalize())
    name = f"Helvetopo Routen {version}" + ("" if region == "schweiz" else f" {area}")
    fn = os.path.join(out, f"Helvetopo_Routen_{area}_{version}.img")
    work = os.path.join(out, f"_tiles_{FID_OVERLAY}")
    tiles = build_tiles(pbf, FID_OVERLAY, FID_OVERLAY * 10000 + 1, work, area)
    tmp = tempfile.mkdtemp(dir=out)
    try:
        r = subprocess.run(["java", "-Xmx4g", "-jar", MKGMAP, f"--output-dir={tmp}", "--gmapsupp",
                            f"--family-id={FID_OVERLAY}", "--product-id=1", f"--family-name={name}",
                            f"--series-name={name}", f"--description={name} ©swisstopo"[:50],
                            f"--overview-mapname={FID_OVERLAY}0000", "--code-page=1252",
                            f"--copyright-file={os.path.join(work, 'copyright.txt')}",
                            f"--license-file={os.path.join(work, 'license.txt')}",
                            *tiles, typ_for(FID_OVERLAY, tmp)], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stdout + r.stderr)
        shutil.move(os.path.join(tmp, "gmapsupp.img"), fn)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    with open(fn[:-4] + "_QUELLSTAND.txt", "w", encoding="utf-8") as f:
        f.write(quellstand_text(name, FID_OVERLAY, pbf))
    return fn


def gmapi_inputs(pbf: str, fid: int, workdir: str, area_name: str) -> list[str]:
    """mkgmap-Eingaben für make_gmapi(extra_inputs=…): Routen-Kacheln der Familie fid und ihr TYP."""
    tiles = build_tiles(pbf, fid, fid * 10000 + 9001, workdir, area_name)
    return tiles + [typ_for(fid, workdir)]


def gmapi_with_routes(gmps, outdir: str, name: str, fid: int, copyright_lines: list[str], pbf: str,
                      area_name: str, from_img: bool = False) -> str:
    """gmapi einer Rasterkarte mit Routen-Kacheln (gmps: GMP-Dateien oder, mit from_img, eine Raster-IMG)."""
    from make_gmapi import make_gmapi, make_gmapi_files  # noqa: E402
    import release as R  # noqa: E402
    lines = list(copyright_lines)
    if ASTRA not in " ".join(lines):
        lines.insert(1, COPYRIGHT)        # zweite Zeile: ©swisstopo; ASTRA (wie build_all.sh)
    work = os.path.join(os.path.dirname(os.path.normpath(outdir)), f"_routes_{fid}")   # nicht in den gmapi-Ordner
    extra = gmapi_inputs(pbf, fid, work, area_name)
    lic = ("Kartendaten: ©swisstopo, Nutzungsbedingungen für frei verfügbare Geodaten (OGD), "
           "https://www.swisstopo.admin.ch/ogd-conditions. " + LICENSE)
    fn = make_gmapi if from_img else make_gmapi_files
    return fn(gmps, outdir, name, fid, fid * 10000 + 9000, copyright_lines=lines, extra_inputs=extra,
              license_text=lic, draw_priority=R.RASTER_PRIORITY)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("overlay", help="Routen-Overlay FID 7702 als eigene IMG (Gerät)")
    o.add_argument("--pbf", default=os.path.join(OUT_DEFAULT, "routes.osm.pbf"))
    o.add_argument("--region", default="testgebiet")
    o.add_argument("--version", default=_dt.date.today().strftime("%Y-%m"))
    o.add_argument("--out", default=OUT_DEFAULT)
    g = sub.add_parser("gmapi", help="gmapi einer vorhandenen Raster-IMG mit Routen-Kacheln (BaseCamp)")
    g.add_argument("--img", required=True)
    g.add_argument("--fid", type=int, required=True)
    g.add_argument("--name", required=True)
    g.add_argument("--copyright", action="append", default=[], help="Copyright-Zeile (mehrfach)")
    g.add_argument("--pbf", default=os.path.join(OUT_DEFAULT, "routes.osm.pbf"))
    g.add_argument("--area-name", default="Testgebiet")
    g.add_argument("--out", default=os.path.join(OUT_DEFAULT, "gmapi"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    if a.cmd == "overlay":
        print(build_overlay(a.pbf, a.out, a.region, a.version))
    else:
        import quellstand as Q  # noqa: E402
        lines = a.copyright or ["©swisstopo"]
        lines = lines + [Q.LICENSE_LINE]
        print(gmapi_with_routes(a.img, a.out, a.name, a.fid, lines, a.pbf, a.area_name, from_img=True))


if __name__ == "__main__":
    main()
