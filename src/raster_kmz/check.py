"""Prüft KMZ-Custom-Maps auf Garmin-Tauglichkeit und erzeugt eine Vorschau.

Prüfungen:
  - ZIP lesbar, doc.kml vorhanden und erster Eintrag
  - KML wohlgeformt, Namespace KML 2.2, Document/name enthält ©swisstopo
  - jede GroundOverlay: Icon/href existiert im ZIP, LatLonBox N>S, O>W, rotation 0, drawOrder gesetzt
  - jede JPEG: Baseline (SOF0, nicht progressiv), ≤ 1024 × 1024 px, < 3 MB, RGB/YCbCr
  - Kachelraster lückenlos: benachbarte LatLonBoxen stossen exakt aneinander
  - Kachelzahl gegen Gerätelimits (100 / 500)
Vorschau: setzt alle Kacheln anhand ihrer LatLonBox zusammen (prüft so auch die Georeferenz),
verkleinert auf max. 2000 px, Kachelgrenzen rot.

Aufruf: python3 check.py work/raster_kmz/*/*.kmz
"""
from __future__ import annotations

import io
import json
import pathlib
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile

from PIL import Image, ImageDraw, ImageFont

NS = {"k": "http://www.opengis.net/kml/2.2"}
MAX_PX = 1024
MAX_BYTES = 3 * 1024 * 1024
try:
    FONT = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 18)
except OSError:
    FONT = ImageFont.load_default()
LIMITS = {"100er-Geräte": 100, "GPSMAP 66/67, Montana 7xx": 500}


def jpeg_sof(data: bytes) -> tuple[int, int, int, int]:
    """Gibt (SOF-Marker, Breite, Höhe, Komponenten) zurück."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("kein JPEG (SOI fehlt)")
    i = 2
    while i < len(data):
        if data[i] != 0xFF:
            raise ValueError(f"Marker erwartet bei {i}")
        m = data[i + 1]
        if m in (0xD8, 0x01) or 0xD0 <= m <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= m <= 0xCF and m not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return m, w, h, data[i + 9]
        i += 2 + seg
    raise ValueError("kein SOF gefunden")


def check(path: pathlib.Path, preview_px: int = 2000) -> dict:
    errors, warnings = [], []
    z = zipfile.ZipFile(path)
    names = z.namelist()
    if names[0] != "doc.kml":
        warnings.append(f"erster ZIP-Eintrag ist {names[0]}, nicht doc.kml")
    root = ET.fromstring(z.read("doc.kml"))
    if root.tag != "{%s}kml" % NS["k"]:
        errors.append(f"Wurzel {root.tag} statt KML-2.2-kml")
    doc_name = root.findtext("k:Document/k:name", namespaces=NS) or ""
    desc = root.findtext("k:Document/k:description", namespaces=NS) or ""
    if "©swisstopo" not in doc_name or "©swisstopo" not in desc:
        errors.append("Quellenangabe ©swisstopo fehlt in name/description")

    overlays = root.findall(".//k:GroundOverlay", NS)
    tiles = []
    max_bytes = 0
    for go in overlays:
        href = go.findtext("k:Icon/k:href", namespaces=NS)
        box = {k: float(go.findtext(f"k:LatLonBox/k:{k}", namespaces=NS))
               for k in ("north", "south", "east", "west")}
        rot = float(go.findtext("k:LatLonBox/k:rotation", "0", namespaces=NS))
        if go.findtext("k:drawOrder", namespaces=NS) is None:
            warnings.append(f"{href}: kein drawOrder")
        if not (box["north"] > box["south"] and box["east"] > box["west"]):
            errors.append(f"{href}: LatLonBox ungültig {box}")
        if rot != 0:
            errors.append(f"{href}: rotation {rot}")
        if href not in names:
            errors.append(f"{href}: fehlt im ZIP")
            continue
        data = z.read(href)
        max_bytes = max(max_bytes, len(data))
        sof, w, h, comps = jpeg_sof(data)
        if sof != 0xC0:
            errors.append(f"{href}: SOF{sof - 0xC0} (nicht Baseline)")
        if w > MAX_PX or h > MAX_PX:
            errors.append(f"{href}: {w}×{h} px > {MAX_PX}")
        if len(data) >= MAX_BYTES:
            errors.append(f"{href}: {len(data)} Bytes ≥ 3 MB")
        if comps != 3:
            warnings.append(f"{href}: {comps} Farbkomponenten")
        tiles.append({"href": href, "w": w, "h": h, **box})

    # Lückenlosigkeit: horizontal/vertikal Nachbarn suchen (Toleranz 1e-9°)
    eps = 1e-9
    gaps = 0
    by_west = {}
    for t in tiles:
        by_west.setdefault(round(t["west"], 8), []).append(t)
    for t in tiles:
        right = [u for u in by_west.get(round(t["east"], 8), [])
                 if abs(u["north"] - t["north"]) < eps]
        if right and abs(right[0]["south"] - t["south"]) > eps:
            gaps += 1
    if gaps:
        errors.append(f"{gaps} Kachelnachbarn passen nicht exakt")

    # Pixelgrösse konsistent?
    psx = [(t["east"] - t["west"]) / t["w"] for t in tiles]
    psy = [(t["north"] - t["south"]) / t["h"] for t in tiles]
    if max(psx) / min(psx) - 1 > 1e-6 or max(psy) / min(psy) - 1 > 1e-6:
        warnings.append(f"uneinheitliche Pixelgrösse: {psx} {psy}")

    n = len(tiles)
    limits = {k: ("ok" if n <= v else f"ZU VIEL ({n} > {v})") for k, v in LIMITS.items()}

    # Vorschau aus den Kacheln
    W = min(t["west"] for t in tiles); E = max(t["east"] for t in tiles)
    N = max(t["north"] for t in tiles); S = min(t["south"] for t in tiles)
    # Seitenverhältnis in Quellpixeln (Pixel sind im Boden ≈ quadratisch)
    px_w = (E - W) / min(psx)
    px_h = (N - S) / min(psy)
    pw = preview_px
    ph = int(round(preview_px * px_h / px_w))
    prev = Image.new("RGB", (pw, ph), "white")
    draw = ImageDraw.Draw(prev)
    for t in tiles:
        x0 = (t["west"] - W) / (E - W) * pw
        x1 = (t["east"] - W) / (E - W) * pw
        y0 = (N - t["north"]) / (N - S) * ph
        y1 = (N - t["south"]) / (N - S) * ph
        im = Image.open(io.BytesIO(z.read(t["href"]))).convert("RGB")
        im = im.resize((max(1, round(x1 - x0)), max(1, round(y1 - y0))), Image.LANCZOS)
        prev.paste(im, (round(x0), round(y0)))
    for t in tiles:
        x0 = (t["west"] - W) / (E - W) * pw; x1 = (t["east"] - W) / (E - W) * pw
        y0 = (N - t["north"]) / (N - S) * ph; y1 = (N - t["south"]) / (N - S) * ph
        draw.rectangle([x0, y0, x1, y1], outline=(220, 0, 0))
    draw.rectangle([0, 0, pw, 26], fill="white")
    draw.text((6, 4), f"{doc_name} | {n} Kacheln | {W:.3f}–{E:.3f} O, {S:.3f}–{N:.3f} N",
              fill="black", font=FONT)
    prev_path = path.with_name(path.stem + "_preview.jpg")
    prev.save(prev_path, quality=88)

    result = {"kmz": str(path), "name": doc_name, "tiles": n, "kmz_mb":
              round(path.stat().st_size / 2**20, 1), "max_jpeg_kb": max_bytes // 1024,
              "bbox": [round(W, 5), round(S, 5), round(E, 5), round(N, 5)],
              "limits": limits, "errors": errors, "warnings": warnings[:20],
              "preview": str(prev_path), "ok": not errors}
    path.with_name(path.stem + "_check.json").write_text(
        json.dumps(result, indent=1, ensure_ascii=False))
    return result


def main() -> None:
    bad = 0
    for p in sys.argv[1:]:
        r = check(pathlib.Path(p))
        status = "OK " if r["ok"] else "FEHLER"
        print(f"{status} {pathlib.Path(p).name}: {r['tiles']} Kacheln, {r['kmz_mb']} MB, "
              f"max. JPEG {r['max_jpeg_kb']} KB, Limits {r['limits']}")
        for e in r["errors"]:
            print("   !", e)
        for w in r["warnings"]:
            print("   ?", w)
        bad += not r["ok"]
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
