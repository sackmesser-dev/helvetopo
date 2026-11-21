#!/usr/bin/env bash
# Stellt das Paket für den Gerätetest (GPSMAP/Montana) unter work/geraetetest/ zusammen.
# Quelle sind die Release-Dateien von src/release/make_release.py (work/release/<version>/files/),
# also genau die Dateien, die auch zum Download kommen:
#   1-vektor/     Helvetopo_Vektor_<Gebiet>_<Version>.img und Routen-Overlay Helvetopo_Routen_<Gebiet>_<Version>.img
#   2-pixel/      Helvetopo_Pixel_{50,25,10}-1000_<Gebiet>_<Version>.img (sofern gebaut)
#   ANLEITUNG.md  Kurzanleitung (aus docs/test/geraetetest.md)
#   QUELLSTAND-*.md, LICENSE-KARTEN.md, *_SHA256SUMS.txt
#
#   src/build/geraetetest_paket.sh            # neueste Version in work/release/
#   VERSION=2026-11 src/build/geraetetest_paket.sh
set -euo pipefail

. "$(dirname "$0")/../paths.sh"   # HELVETOPO_REPO: dieser Checkout
REPO=$HELVETOPO_REPO
OUT=${OUT:-$REPO/work/geraetetest}
if [[ -z "${VERSION:-}" ]]; then
  VERSION=$(ls -1 "$REPO/work/release" 2>/dev/null | sort | tail -1)
fi
FILES=$REPO/work/release/$VERSION/files
[[ -n "$VERSION" && -d "$FILES" ]] || { echo "keine Release-Dateien in work/release/ (zuerst make_release.py)"; exit 1; }

rm -rf "$OUT"
mkdir -p "$OUT/1-vektor" "$OUT/2-pixel"
link() { ln "$1" "$2" 2>/dev/null || cp "$1" "$2"; }   # Hardlink spart Platz, sonst Kopie

shopt -s nullglob
vec=("$FILES"/Helvetopo_Vektor_*.img)
pix=("$FILES"/Helvetopo_Pixel_*.img)
(( ${#vec[@]} )) || { echo "keine Vektor-IMG in $FILES"; exit 1; }
for f in "${vec[@]}" "$FILES"/Helvetopo_Routen_*.img; do link "$f" "$OUT/1-vektor/$(basename "$f")"; done
for f in "${pix[@]}"; do link "$f" "$OUT/2-pixel/$(basename "$f")"; done

cp "$REPO/docs/test/geraetetest.md" "$OUT/ANLEITUNG.md"
cp "$REPO/LICENSE-KARTEN.md" "$FILES"/*_SHA256SUMS.txt "$OUT/"
for k in vektor pixel; do
  [[ -f "$REPO/releases/$VERSION/$k/QUELLSTAND.md" ]] && cp "$REPO/releases/$VERSION/$k/QUELLSTAND.md" "$OUT/QUELLSTAND-$k.md"
done

# Prüfsummen der Paketdateien gegen die Release-Liste
( cd "$OUT"; for f in 1-vektor/*.img 2-pixel/*.img; do
    want=$(awk -v n="$(basename "$f")" '$2 == n {print $1}' ./*_SHA256SUMS.txt)
    have=$(shasum -a 256 "$f" | cut -d' ' -f1)
    [[ "$want" == "$have" ]] || { echo "FEHLER Prüfsumme $f"; exit 1; }
  done )
# Lizenz: keine OSM/ODbL-Texte, überall ©swisstopo
REQUIRE_ASTRA=no "$REPO/src/build/check_license.sh" "$OUT"

du -sh "$OUT"/1-vektor/* "$OUT"/2-pixel/* 2>/dev/null
echo "Paket $VERSION: $OUT"
