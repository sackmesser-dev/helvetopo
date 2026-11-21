#!/usr/bin/env python3
"""Bündelt manifest.json, regions.json und i18n/*.json des Portals in data.js.

data.js braucht man nur, wenn index.html direkt als Datei (file://) geöffnet wird:
Dort darf der Browser keine JSON-Dateien nachladen. Über einen Webserver liest die
Seite weiterhin die JSON-Dateien selbst; sie bleiben die Quelle.

Aufruf:
    python3 -I src/portal/build_data.py            # data.js neu schreiben
    python3 -I src/portal/build_data.py --check    # Fehler, wenn data.js veraltet ist
"""
import argparse
import json
import sys
from pathlib import Path

LANGS = ["de", "fr", "it", "en"]


def build(site: Path) -> str:
    manifest = json.loads((site / "manifest.json").read_text(encoding="utf-8"))
    i18n = {l: json.loads((site / "i18n" / f"{l}.json").read_text(encoding="utf-8")) for l in LANGS}
    base = set(i18n["de"])
    for l in LANGS[1:]:
        missing, extra = base - set(i18n[l]), set(i18n[l]) - base
        if missing or extra:
            sys.exit(f"i18n/{l}.json passt nicht zu de.json: fehlt {sorted(missing)}, zu viel {sorted(extra)}")
    regions_path = site / "regions.json"
    regions = json.loads(regions_path.read_text(encoding="utf-8")) if regions_path.exists() else None
    data = json.dumps({"manifest": manifest, "i18n": i18n, "regions": regions}, ensure_ascii=False, separators=(",", ":"))
    return (
        "// Erzeugt von src/portal/build_data.py aus manifest.json und i18n/*.json. Nicht von Hand ändern.\n"
        f"window.PORTAL_DATA = {data};\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", type=Path, default=Path(__file__).resolve().parent / "prototype")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    out = args.site / "data.js"
    content = build(args.site)
    if args.check:
        if not out.exists() or out.read_text(encoding="utf-8") != content:
            sys.exit(f"{out} ist veraltet: build_data.py ausführen")
        print(f"{out} ist aktuell")
        return
    out.write_text(content, encoding="utf-8")
    print(f"{out} geschrieben ({len(content) // 1024} KB)")


if __name__ == "__main__":
    main()
