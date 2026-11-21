#!/usr/bin/env bash
# Baut die Basiskarte (FID 7701) aus einer PBF mit dem swisstopo-Style und der TYP-Datei.
# Optionen wie src/vector/build_img.sh, aber mit eigener Copyright-
# und Lizenzdatei, in der die Wörter "OpenStreetMap" und "ODbL" nicht vorkommen. So bleibt die
# Prüfung `strings -a … | grep -ciE 'openstreetmap|odbl'` eindeutig bei 0.
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   bash src/style/build_testgebiet.sh <eingabe.osm.pbf> [ausgabeordner]
# Standard-Ausgabe: work/style/testgebiet
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
TOOLS=${TOOLS:-$HELVETOPO_ROOT/tools}
MKGMAP="$TOOLS/mkgmap-r4924/mkgmap.jar"
SPLITTER="$TOOLS/splitter-r654/splitter.jar"
IN="${1:?PBF angeben}"
OUT="${2:-$ROOT/work/style/testgebiet}"
XMX="${JAVA_XMX:-6g}"
STYLE_DIR="${STYLE_DIR:-$ROOT/src/style/swisstopo}"   # für A/B-Varianten überschreibbar
POLY_LIMITS="${POLY_LIMITS:-24:0,23:1,22:1,21:1,20:1,19:1,18:2,16:1,14:1,12:1}"   # ebenso

rm -rf "$OUT"
mkdir -p "$OUT/tiles"

# TYP-Quelle frisch erzeugen (über Temp-Datei, damit ein Fehler sie nicht leert).
# TYP_FILE=<datei> nimmt stattdessen eine fertige TYP-Quelle (A/B-Varianten), src bleibt unberührt.
if [ -n "${TYP_FILE:-}" ]; then
  TYP_SRC="$TYP_FILE"
else
  python3 -I "$ROOT/src/style/tools/make_typ.py" > "$OUT/swisstopo.txt.tmp"
  mv "$OUT/swisstopo.txt.tmp" "$ROOT/src/style/typ/swisstopo.txt"
  TYP_SRC="$ROOT/src/style/typ/swisstopo.txt"
fi

java -Xmx"$XMX" -jar "$SPLITTER" --output-dir="$OUT/tiles" --mapid=77010001 \
  --max-nodes=1200000 --keep-complete=true --output=pbf --description="CH Basiskarte" \
  "$IN" > "$OUT/splitter.log" 2>&1

printf '%s\n%s\n' '©swisstopo' '©swisstopo' > "$OUT/copyright.txt"
cat > "$OUT/license.txt" <<'EOF'
Kartendaten: ©swisstopo (Open Government Data, freie Nutzung mit Quellenangabe).
Datensätze: swissTLM3D, swissNAMES3D, swissBOUNDARIES3D, amtliches Gebäudeadressverzeichnis,
amtliches Strassenverzeichnis. Nur swisstopo-Daten. Keine offizielle Karte von swisstopo.
Erzeugt mit mkgmap (GPL).
EOF

(cd "$OUT" && java -Xmx"$XMX" -jar "$MKGMAP" \
  --code-page=1252 --lower-case \
  --family-id=7701 --product-id=1 \
  --family-name="Helvetopo Basiskarte" --series-name="Helvetopo Basiskarte" --area-name="Schweiz (Test)" \
  --description="CH Basiskarte, Daten ©swisstopo" \
  --overview-mapname=77010000 --overview-mapnumber=77010000 \
  --country-name=Schweiz --country-abbr=CHE \
  --polygon-size-limits="$POLY_LIMITS" \
  --simplify-polygons="${SIMPLIFY_POLYGONS:-24:0,23:0,22:0,21:2.6}" \
  --copyright-file="$OUT/copyright.txt" --license-file="$OUT/license.txt" \
  --style-file="$STYLE_DIR" \
  --route --drive-on=right --index --housenumbers --location-autofill=is_in,nearest \
  --add-pois-to-areas --link-pois-to-ways --process-destination --process-exits \
  --max-jobs --tdbfile --gmapsupp --gmapi \
  --output-dir="$OUT" \
  -c "$OUT/tiles/template.args" \
  "$TYP_SRC" > "$OUT/mkgmap.log" 2>&1)
grep -E "MapFailedExceptions|ExitExceptions" "$OUT/mkgmap.log"

# Kontrolle: keine OSM-/ODbL-Hinweise
n=$(cat "$OUT"/*.img "$OUT"/*.tdb | strings -a | grep -ciE 'openstreetmap|odbl' || true)
echo "OSM/ODbL-Treffer: $n"
if [ "$n" != 0 ]; then echo "FEHLER: OSM/ODbL-Text in der Ausgabe" >&2; exit 1; fi
ls -la "$OUT/gmapsupp.img"
