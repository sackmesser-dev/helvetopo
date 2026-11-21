#!/bin/sh
# Baut die Legenden-Testkarte mit Style und TYP nach work/style/legende/.
# Aufruf aus dem Repo-Wurzelverzeichnis:  sh src/style/build_legend.sh
set -eu

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
MKGMAP=${MKGMAP:-$HELVETOPO_ROOT/tools/mkgmap-r4924/mkgmap.jar}
OUT="$ROOT/work/style/legende"
mkdir -p "$OUT"

# Erst in Temp-Dateien schreiben: ein Fehler im Generator darf die Quellen nicht leeren
python3 -I "$ROOT/src/style/tools/make_typ.py" > "$OUT/swisstopo.txt.tmp"
mv "$OUT/swisstopo.txt.tmp" "$ROOT/src/style/typ/swisstopo.txt"
python3 -I "$ROOT/src/style/test/make_legend_osm.py" > "$OUT/legende.osm.tmp"
mv "$OUT/legende.osm.tmp" "$ROOT/src/style/test/legende.osm"

# Quellenangabe: nur swisstopo. Ohne --copyright-file/--overview-mapname schreibt mkgmap
# "Map data (c) OpenStreetMap … ODbL" in Karte und TDB.
printf '%s\n%s\n' '©swisstopo' '©swisstopo' > "$OUT/copyright.txt"
cat > "$OUT/license.txt" <<'EOT'
Kartendaten: ©swisstopo (Open Government Data, freie Nutzung mit Quellenangabe).
Legenden-Testkarte von Helvetopo mit erfundener Geometrie. Keine offizielle Karte von swisstopo.
Erzeugt mit mkgmap (GPL).
EOT

java -jar "$MKGMAP" \
  --output-dir="$OUT" \
  --style-file="$ROOT/src/style/swisstopo" \
  --check-styles \
  --family-id=7701 --product-id=1 --family-name="Helvetopo Legende" \
  --series-name="Helvetopo" --area-name="Legende" \
  --code-page=1252 --lower-case \
  --mapname=77019001 --description="Helvetopo Legende ©swisstopo" \
  --copyright-file="$OUT/copyright.txt" --license-file="$OUT/license.txt" \
  --overview-mapname=77019000 --overview-mapnumber=77019000 \
  --country-name=Schweiz --country-abbr=CHE --location-autofill=is_in,nearest \
  --polygon-size-limits="24:0,23:1,22:1,21:1,20:1,19:1,18:2,16:1,14:1,12:1" \
  --route --index --housenumbers --add-pois-to-areas \
  --remove-short-arcs \
  --report-similar-arcs --report-dead-ends=1 \
  --gmapsupp --tdbfile \
  "$ROOT/src/style/test/legende.osm" \
  "$ROOT/src/style/typ/swisstopo.txt" 2>&1 | tee "$OUT/mkgmap.log"

# Kontrolle: keine OSM-/ODbL-Hinweise in den Ausgaben
if grep -l -a -i -E 'openstreetmap|odbl' "$OUT"/*.img "$OUT"/*.tdb 2>/dev/null; then
  echo "FEHLER: OSM/ODbL-Text in der Ausgabe" >&2; exit 1
fi

ls -la "$OUT"
