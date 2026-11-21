#!/usr/bin/env bash
# Baut das Routen-Overlay (FID 7702).
#   bash src/routes/build.sh          # Testgebiet (Default) -> work/routes/
#   AREA=ch bash src/routes/build.sh  # ganze Schweiz mit splitter -> work/routes-ch/
# Voraussetzungen: Downloads in $DOWNLOADS (siehe docs/vektor/routen.md), osmium, Java.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
MAIN=${MAIN:-$HELVETOPO_ROOT}
DOWNLOADS="${DOWNLOADS:-$HELVETOPO_DATA}"
MKGMAP="${MKGMAP:-$MAIN/tools/mkgmap-r4924/mkgmap.jar}"
SPLITTER="${SPLITTER:-$MAIN/tools/splitter-r654/splitter.jar}"
AREA="${AREA:-test}"
POIS="${POIS:-yes}"   # no: ohne POIs aus src/routes/pois_overlay.py
PYTHON="${PYTHON:-$MAIN/.venv/bin/python}"
FID=7702

case "$AREA" in
  test)
    BBOX="${BBOX:-9.00,47.20,9.50,47.50}"
    OUT="$ROOT/work/routes"
    AREA_NAME="Testgebiet Wil-St.Gallen-Alpstein"
    SPLIT=0 ;;
  ch)
    # Schweiz und Liechtenstein; Routenstücke im Ausland (informativ) werden abgeschnitten
    BBOX="${BBOX:-5.95,45.81,10.50,47.81}"
    OUT="$ROOT/work/routes-ch"
    AREA_NAME="Schweiz"
    SPLIT=1 ;;
  *) echo "AREA muss test oder ch sein" >&2; exit 2 ;;
esac

mkdir -p "$OUT"
cd "$OUT"

# 1. Daten -> OSM -> PBF (das grosse XML wird danach gelöscht)
python3 -I "$ROOT/src/routes/convert_routes.py" --downloads "$DOWNLOADS" --bbox "$BBOX" \
  --out "$OUT/routes.osm" 2> >(tee "$OUT/convert.log" >&2)
# POIs, die die Landeskarte nicht zeigt (Logik der Basis, src/vector/pois.py; braucht das venv)
if [ "$POIS" = yes ]; then
  (cd "$ROOT" && HELVETOPO_DATA="$DOWNLOADS" "$PYTHON" -E -s -m src.routes.pois_overlay --bbox "$BBOX" \
    --out "$OUT/pois.osm") 2> >(tee "$OUT/pois.log" >&2)
  osmium merge -O "$OUT/routes.osm" "$OUT/pois.osm" -o "$OUT/routes.osm.pbf"
else
  osmium cat -O "$OUT/routes.osm" -o "$OUT/routes.osm.pbf"
fi
[ "$AREA" = test ] || rm -f "$OUT/routes.osm" "$OUT/pois.osm"

# 2. TYP-Quelltext und Style-Regeln erzeugen
python3 -I "$ROOT/src/routes/make_typ.py" > "$ROOT/src/style/typ/routes.txt"
python3 -I "$ROOT/src/routes/make_style.py" > "$ROOT/src/style/routes/lines"

# 3. Pflicht-Quellenangaben (je nach enthaltenen Daten)
{
  echo "©swisstopo; Routen: Bundesamt für Strassen, Kanton, Stiftung SchweizMobil"
  echo "Kartendaten ©swisstopo (swissTLM3D Wanderwege, Haltestellen und POIs, OGD)"
  echo "Routen: Bundesamt für Strassen, Kanton, Stiftung SchweizMobil (Opendata BY)"
  if grep -q "^kanuland/" "$OUT/convert.log"; then
    echo "Kanuland: Stiftung SchweizMobil (Open Data BY)"
  fi
} > "$OUT/copyright.txt"

cat > "$OUT/license.txt" <<'EOF'
Helvetopo Routen-Overlay (inoffiziell, keine Karte von swisstopo oder SchweizMobil).
Wanderwege, Haltestellen und POIs: ©swisstopo, swissTLM3D, Open Government Data (https://www.swisstopo.admin.ch/ogd-conditions).
Routen Wanderland, Veloland, Mountainbikeland, Skatingland: Bundesamt für Strassen, Kanton, Stiftung SchweizMobil, Opendata BY (https://opendata.swiss/terms-of-use#terms_by).
Kanuland (falls enthalten): Stiftung SchweizMobil, Open Data BY.
Erstellt mit mkgmap $MKGMAP_VERSION$ am $LONGDATE$.
EOF

# 4. Kacheln: Testgebiet eine Kachel, Schweiz mit splitter
rm -rf "$OUT"/7702*.img "$OUT"/gmapsupp.img "$OUT"/*.tdb "$OUT"/*.typ "$OUT"/*.gmap "$OUT/split"
if [ "$SPLIT" = 1 ]; then
  java -Xmx4g -jar "$SPLITTER" --mapid=77020001 --max-nodes=1600000 --output=pbf \
    --output-dir="$OUT/split" --description="Helvetopo Routen ©swisstopo ASTRA SchweizMobil" "$OUT/routes.osm.pbf" > "$OUT/splitter.log" 2>&1
  INPUT=(-c "$OUT/split/template.args")
  cd "$OUT/split"
else
  INPUT=(--description="Helvetopo Routen ©swisstopo ASTRA SchweizMobil" --mapname=77020001 "$OUT/routes.osm.pbf")
fi

# 5. mkgmap
java -Xmx4g -jar "$MKGMAP" \
  --output-dir="$OUT" \
  --style-file="$ROOT/src/style/routes" \
  --family-id=$FID --product-id=1 \
  --family-name="Helvetopo Routen" \
  --series-name="Helvetopo Routen (©swisstopo, ASTRA/SchweizMobil)" \
  --area-name="$AREA_NAME" \
  --overview-mapname=77020000 \
  --code-page=1252 --lower-case \
  --transparent --draw-priority=30 \
  --merge-lines \
  --reduce-point-density=2 \
  --copyright-file="$OUT/copyright.txt" \
  --license-file="$OUT/license.txt" \
  --tdbfile --gmapsupp --gmapi \
  --check-styles \
  "${INPUT[@]}" \
  "$ROOT/src/style/typ/routes.txt" 2>&1 | tee "$OUT/mkgmap.log"

# 6. Zuordnung Route <-> TLM-Kante für vector-convert (CSV über uuid)
python3 -I "$ROOT/src/routes/match_tlm.py" --downloads "$DOWNLOADS" --bbox "$BBOX" \
  --out "$OUT/tlm_routes.csv" 2> "$OUT/match.log"

ls -la "$OUT"
