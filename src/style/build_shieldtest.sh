#!/usr/bin/env bash
# Shield-Testkarte für den Gerätetest (Map-ID 77019101, FID 7701) nach work/style/shieldtest/.
# Aufruf aus dem Repo-Wurzelverzeichnis:  bash src/style/build_shieldtest.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
MKGMAP=${MKGMAP:-$HELVETOPO_ROOT/tools/mkgmap-r4924/mkgmap.jar}
OUT="$ROOT/work/style/shieldtest"
rm -rf "$OUT"; mkdir -p "$OUT"
python3 -I "$ROOT/src/style/tools/make_typ.py" > "$OUT/base_typ.txt"
python3 -I "$ROOT/src/style/tools/make_shieldtest.py" "$OUT" "$OUT/base_typ.txt"
printf '%s\n%s\n' '©swisstopo' '©swisstopo' > "$OUT/copyright.txt"
echo 'Shield-Testkarte Helvetopo (synthetische Linien, keine Kartendaten). Keine offizielle Karte von swisstopo.' > "$OUT/license.txt"
(cd "$OUT" && java -jar "$MKGMAP" \
  --style-file="$OUT/style" --check-styles \
  --family-id=7701 --product-id=1 --family-name="Helvetopo Shieldtest" \
  --series-name="Helvetopo" --area-name="Shieldtest" \
  --code-page=1252 --lower-case \
  --mapname=77019101 --description="Helvetopo Shieldtest" \
  --copyright-file="$OUT/copyright.txt" --license-file="$OUT/license.txt" \
  --overview-mapname=77019100 --overview-mapnumber=77019100 \
  --gmapsupp --tdbfile \
  "$OUT/shieldtest.osm" "$OUT/shieldtest_typ.txt" > "$OUT/mkgmap.log" 2>&1)
grep -E "MapFailedExceptions|ExitExceptions|SCHWER|SEVERE" "$OUT/mkgmap.log" || true

# BaseCamp-Variante: eigene Test-FID 7749, damit sie neben der CH-Karte (7701) wählbar ist.
G="$OUT/gmapi"; mkdir -p "$G"
sed 's/^FID=7701$/FID=7749/' "$OUT/shieldtest_typ.txt" > "$G/shieldtest_7749.txt"
(cd "$G" && java -jar "$MKGMAP" \
  --style-file="$OUT/style" \
  --family-id=7749 --product-id=1 --family-name="CH Shieldtest" \
  --series-name="CH Shieldtest" --area-name="Shieldtest" \
  --code-page=1252 --lower-case \
  --mapname=77019101 --description="CH Shieldtest" \
  --copyright-file="$OUT/copyright.txt" --license-file="$OUT/license.txt" \
  --overview-mapname=77019100 --overview-mapnumber=77019100 \
  --tdbfile --gmapi \
  "$OUT/shieldtest.osm" "$G/shieldtest_7749.txt" > "$G/mkgmap.log" 2>&1)
grep -E "MapFailedExceptions|ExitExceptions|SCHWER|SEVERE" "$G/mkgmap.log" || true
n=$(cat "$OUT"/*.img "$OUT"/gmapi/*.img | strings -a | grep -ciE 'openstreetmap|odbl' || true)
echo "OSM/ODbL-Treffer: $n"; [ "$n" = 0 ]
ls -la "$OUT/gmapsupp.img"
