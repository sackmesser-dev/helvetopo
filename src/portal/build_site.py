#!/usr/bin/env python3
"""Baut die Portal-Website für den Server aus dem Prototyp und dem Manifest eines Releases.

- kopiert src/portal/prototype/ (ohne manifest.json, data.js) nach --out
- legt das Release-Manifest als manifest.json daneben
- entfernt den Hinweis „Prototyp mit Beispieldaten“ (div.proto-note)
- hängt an jeden Bildverweis img/<datei> und an lang.js, app.css, app.js in index.html eine Version
  ?v=<sha256> an (geänderte Dateien umgehen den Browser-Cache)
- erzeugt data.js neu (build_data.py --site)

Die Kartendateien gehören nicht zur Website. Sie liegen auf dem Download-Server (baseUrl im Manifest).

Aufruf:
    python3 -I src/portal/build_site.py --manifest work/release/2026-11-ch/manifest.json [--out work/portal/deploy]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PROTO = HERE / "prototype"


IMG_REF = re.compile(r'img/([A-Za-z0-9._-]+\.(?:jpg|jpeg|png|svg|webp))(?![?\w])')


def version_images(out: Path) -> None:
    """Hängt an jeden Verweis img/<datei> den Anfang der SHA-256 an (img/<datei>?v=<hash>).

    Browser behalten Bilder im Cache. Mit dem Hash ändert sich die URL, sobald sich ein Bild ändert.
    Dann laden alle Browser das neue Bild sofort.
    """
    import hashlib
    ver = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()[:10] for p in (out / "img").iterdir() if p.is_file()}
    count = 0
    for f in (out / "index.html", out / "app.css", out / "app.js"):
        text = f.read_text(encoding="utf-8")

        def repl(m: re.Match) -> str:
            nonlocal count
            name = m.group(1)
            if name not in ver:
                sys.exit(f"{f.name}: Bild img/{name} fehlt")
            count += 1
            return f"img/{name}?v={ver[name]}"

        f.write_text(IMG_REF.sub(repl, text), encoding="utf-8")
    print(f"Bilder versioniert: {count} Verweise")

    # Danach dasselbe für Skripte und Stylesheet in index.html (ihr Inhalt enthält jetzt die Bild-Hashes).
    idx = out / "index.html"
    html = idx.read_text(encoding="utf-8")
    for name in ("lang.js", "app.css", "app.js"):
        h = hashlib.sha256((out / name).read_bytes()).hexdigest()[:10]
        html, n = re.subn(rf'((?:src|href)="){re.escape(name)}"', rf'\g<1>{name}?v={h}"', html)
        if n != 1:
            sys.exit(f"index.html: Verweis auf {name} nicht genau einmal gefunden ({n})")
    idx.write_text(html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=REPO / "work" / "portal" / "deploy")
    a = ap.parse_args()

    m = json.loads(a.manifest.read_text(encoding="utf-8"))
    if "_hinweis" in m:
        sys.exit(f"{a.manifest} ist das Prototyp-Manifest (Beispieldaten), kein Release-Manifest")
    if not m.get("baseUrl", "").startswith("https://"):
        sys.exit(f"baseUrl ist keine absolute https-URL: {m.get('baseUrl')!r}")

    out = a.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(PROTO, out, ignore=shutil.ignore_patterns("manifest.json", "data.js", ".DS_Store", "files"))
    shutil.copy2(a.manifest, out / "manifest.json")

    idx = out / "index.html"
    html = idx.read_text(encoding="utf-8")
    html, n = re.subn(r'<div class="proto-note"[^>]*>.*?</div>\n?', "", html, count=1, flags=re.S)
    if n != 1:
        sys.exit("Hinweis „Prototyp“ (div.proto-note) nicht gefunden")
    idx.write_text(html, encoding="utf-8")
    version_images(out)

    subprocess.run([sys.executable, "-I", str(HERE / "build_data.py"), "--site", str(out)], check=True)
    print(f"Website: {out} (Release {m['release']}, Dateien unter {m['baseUrl']})")


if __name__ == "__main__":
    main()
