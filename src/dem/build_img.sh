#!/usr/bin/env bash
# Höhenlinien-Overlay (FID 7703) aus work/dem/contours.osm.pbf bauen.
#   src/dem/build_img.sh            → work/dem/img7703/      (nur Höhenlinien, transparent)
#   WITH_DEM=1 src/dem/build_img.sh → work/dem/img7703-dem/  (zusätzlich DEM/Schummerung, Testvariante)
set -euo pipefail
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
cd "$(dirname "$0")/../.."
ROOT=$HELVETOPO_ROOT
MKGMAP=$ROOT/tools/mkgmap-r4924/mkgmap.jar
SPLITTER=$ROOT/tools/splitter-r654/splitter.jar
WORK=work/dem
OUT=$WORK/img7703${WITH_DEM:+-dem}
JAVA_MEM=${JAVA_MEM:--Xmx4g}
DEM_DISTS=${DEM_DISTS:-3312,13248,26512}   # passend zu levels 0:24,1:22,2:20 (Overlay-Style)

rm -rf "$OUT" "$WORK/split"; mkdir -p "$OUT" "$WORK/split"

# Quellenangaben: Garmin zeigt am Gerät nur die zweite Zeile → in beiden Zeilen. Ohne
# --license-file setzt mkgmap seinen OSM/ODbL-Standardtext ein, deshalb immer beide Dateien.
printf '%s\n%s\n' "©swisstopo" "©swisstopo" > "$OUT/copyright.txt"
sed -e "s|@VERSION@|$(date +%Y-%m-%d)|g" -e "s|@MKGMAP@|r4924|g" src/build/templates/license_7703.txt > "$OUT/license.txt"

t0=$(date +%s)
java $JAVA_MEM -jar "$SPLITTER" --output-dir="$WORK/split" --mapid=77030001 \
  --max-nodes=1600000 --resolution=13 --output=pbf "$WORK/contours.osm.pbf" > "$WORK/split/splitter.log"
t1=$(date +%s)

DEM_OPTS=()
if [[ -n "${WITH_DEM:-}" ]]; then
  DEM_OPTS=(--dem="$WORK/hgt1" --dem-dists="$DEM_DISTS" --dem-interpolation=auto
            --dem-poly="$WORK/hgt1/dem.poly" --show-profiles=1)
fi

java $JAVA_MEM -jar "$MKGMAP" \
  --output-dir="$OUT" \
  --family-id=7703 --product-id=1 \
  --family-name="Helvetopo Hoehenlinien" \
  --series-name="Helvetopo Hoehenlinien" \
  --area-name="Testgebiet Wil-St.Gallen-Saentis" \
  --description="Helvetopo Hoehenlinien ©swisstopo" \
  --overview-mapname=77030000 --overview-mapnumber=77030000 \
  --copyright-file="$OUT/copyright.txt" --license-file="$OUT/license.txt" \
  --code-page=1252 --lower-case \
  --transparent --draw-priority=28 \
  --style-file=src/style/contours \
  --reduce-point-density=2 \
  --tdbfile --gmapsupp --gmapi \
  --max-jobs \
  ${DEM_OPTS[@]+"${DEM_OPTS[@]}"} \
  -c "$WORK/split/template.args" \
  src/style/typ/contours.txt > "$OUT/mkgmap.log" 2>&1 || { tail -30 "$OUT/mkgmap.log"; exit 1; }
t2=$(date +%s)
echo "splitter $((t1-t0)) s, mkgmap $((t2-t1)) s"
ls -la "$OUT"/*.img "$OUT"/*.typ 2>/dev/null
grep -iE 'error|severe' "$OUT/mkgmap.log" | head || true
src/build/check_license.sh "$OUT"
