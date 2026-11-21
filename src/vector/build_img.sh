#!/usr/bin/env bash
# Basiskarte Vektor (FID 7701): PBF → splitter → mkgmap → gmapsupp.img und gmapi.
#
# Aufruf aus dem Repo-Wurzelverzeichnis:
#   src/vector/build_img.sh [eingabe.osm.pbf] [ausgabeordner] [style]
# Standard: work/vector/testgebiet.osm.pbf → work/vector/img, mkgmap-Default-Style.
# Weitere Umgebungsvariablen:
#   BOUNDS=<ordner>   eigene Grenzen (aus swissBOUNDARIES3D, siehe make_bounds.sh) für --bounds
#   TYP=<datei.typ>   TYP-Datei (src/style/typ/)
#   JAVA_XMX=4g       Java-Heap
#   MKGMAP_EXTRA="…"  zusätzliche mkgmap-Optionen (Leerzeichen-getrennt), z. B. für Vergleichsbuilds
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
TOOLS=${TOOLS:-$HELVETOPO_ROOT/tools}
MKGMAP="$TOOLS/mkgmap-r4924/mkgmap.jar"
SPLITTER="$TOOLS/splitter-r654/splitter.jar"

IN="${1:-$REPO/work/vector/testgebiet.osm.pbf}"
OUT="${2:-$REPO/work/vector/img}"
STYLE="${3:-}"
XMX="${JAVA_XMX:-6g}"

FID=7701
PID=1
MAPID_BASE=77010001          # Kacheln 77010001 …
OVERVIEW=77010000

rm -rf "$OUT"
mkdir -p "$OUT/tiles"
# absolute Pfade (mkgmap läuft im Ausgabeordner)
OUT="$(cd "$OUT" && pwd)"
IN="$(cd "$(dirname "$IN")" && pwd)/$(basename "$IN")"

echo "== splitter"
java -Xmx"$XMX" -jar "$SPLITTER" \
  --output-dir="$OUT/tiles" \
  --mapid=$MAPID_BASE \
  --max-nodes=1200000 \
  --keep-complete=true \
  --output=pbf \
  --description="CH Basiskarte" \
  "$IN" > "$OUT/splitter.log" 2>&1
tail -3 "$OUT/splitter.log"

# Quellenangabe: das Gerät zeigt nur die zweite Zeile, deshalb dieselbe Angabe in beiden Zeilen.
# Quellen aus <pbf>.sources (vom Konverter geschrieben), sonst nur ©swisstopo.
SOURCES="©swisstopo"
if [[ -f "$IN.sources" ]]; then
  SOURCES="$(paste -sd ';' "$IN.sources" | sed 's/;/; /g')"
fi
printf '%s\n%s\n' "$SOURCES" "$SOURCES" > "$OUT/copyright.txt"
DESCRIPTION="CH Basiskarte; $SOURCES"
cat > "$OUT/license.txt" <<EOF
Kartendaten: $SOURCES (Open Government Data bzw. Open Data BY, freie Nutzung mit Quellenangabe).
Datensätze: swissTLM3D, swissNAMES3D, swissBOUNDARIES3D, amtliches Gebäudeadressverzeichnis,
amtliches Strassenverzeichnis; falls angegeben Routenzugehörigkeit aus Veloland, Mountainbikeland,
Wanderland, Skatingland. Keine offizielle Karte von swisstopo oder SchweizMobil.
Routing: Schwerpunkt Fuss und Velo. Das Auto-Routing ist nur topografisch: swissTLM3D enthält
keine Einbahnen (ausser richtungsgetrennten Fahrbahnen und Kreiseln), keine Abbiegeverbote,
keine Fahrstreifen und keine Tempolimits. Nicht zur Fahrzeugnavigation verwenden.
Erzeugt mit mkgmap (GPL). Enthält ausschliesslich Daten der genannten Quellen.
EOF

STYLE_OPTS=()
if [[ -n "$STYLE" ]]; then
  STYLE_OPTS=(--style-file="$STYLE")
fi
BOUNDS_OPTS=()
if [[ -n "${BOUNDS:-}" ]]; then
  BOUNDS_OPTS=(--bounds="$BOUNDS")
fi
TYP_FILES=()
if [[ -n "${TYP:-}" ]]; then
  TYP_FILES=("$TYP")
fi

COMMON=(
  --code-page=1252
  --lower-case
  --family-id=$FID
  --product-id=$PID
  --family-name="Helvetopo Basiskarte"
  --series-name="Helvetopo Basiskarte"
  --area-name="Schweiz (Test)"
  --description="$DESCRIPTION"
  --overview-mapname=$OVERVIEW
  --overview-mapnumber=$OVERVIEW
  --copyright-file="$OUT/copyright.txt"
  --license-file="$OUT/license.txt"
  --route
  --drive-on=right
  --country-name=Schweiz
  --country-abbr=CHE
  --index
  --housenumbers
  --location-autofill=is_in,nearest
  --link-pois-to-ways
  --process-destination
  --process-exits
  --report-roundabout-issues=all
  --report-routing-islands
  --report-similar-arcs
  --report-dead-ends=1
  --max-jobs
  --tdbfile
)

echo "== check-styles"
java -jar "$MKGMAP" ${STYLE_OPTS[@]+"${STYLE_OPTS[@]}"} --check-styles > "$OUT/check-styles.log" 2>&1 || true
tail -5 "$OUT/check-styles.log"

echo "== mkgmap gmapsupp"
(cd "$OUT" && java -Xmx"$XMX" -Dlog.config="$REPO/src/vector/mkgmap-logging.properties" -jar "$MKGMAP" \
  "${COMMON[@]}" ${STYLE_OPTS[@]+"${STYLE_OPTS[@]}"} ${BOUNDS_OPTS[@]+"${BOUNDS_OPTS[@]}"} \
  ${MKGMAP_EXTRA:-} \
  --output-dir="$OUT" \
  --gmapsupp \
  --gmapi \
  -c "$OUT/tiles/template.args" \
  ${TYP_FILES[@]+"${TYP_FILES[@]}"} > "$OUT/mkgmap.log" 2>&1)
tail -5 "$OUT/mkgmap.log"
ls -la "$OUT"/*.img | head
du -sh "$OUT"/*.gmap 2>/dev/null || true
