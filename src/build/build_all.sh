#!/usr/bin/env bash
# Gesamt-Build: Basiskarte (mit DEM und Höhenkoten), Routen-Overlay, Höhenlinien.
#
#   src/build/build_all.sh                        # Standard aus src/build/config.sh
#   DEVICE_FAMILIES=split src/build/build_all.sh  # Gerät: 7701/7702/7703 als getrennte Karten
#   CONTOURS=embedded src/build/build_all.sh      # Höhenlinien in die Basis-Kacheln statt als Overlay
#
# BaseCamp zeigt nur EIN Kartenprodukt gleichzeitig. Deshalb liegt für BaseCamp alles in der
# Familie 7701: Basiskacheln 77010001…, transparente Routen-Kacheln 77011001…, transparente
# Höhenlinien-Kacheln 77012001…, gemeinsame Übersicht 77010000, gemeinsame TDB, eine TYP.
#
# Ergebnis in $OUT (work/build/):
#   dist/gmapsupp.img                Gerät (GPSMAP/Montana), je nach DEVICE_FAMILIES
#   dist/BaseCamp/<MAP_NAME>.gmap  BaseCamp (eine Familie 7701)
#   dist/README.txt, dist/LICENSE.txt
#   timings.tsv                      Laufzeit und Spitzen-RAM je Schritt
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
source "$REPO/src/build/config.sh"
cd "$REPO"

mkdir -p "$OUT"
# Veraltete Ausgabeordner entfernen, die dieser Lauf nicht neu schreibt (sonst misst jemand alte Kacheln)
stale=()
[[ "$CONTOURS" == overlay ]] || stale+=("7701-contours" "7703")
[[ "$ROUTES" == yes ]] || stale+=("7701-routes" "7702")
[[ "$DEVICE_FAMILIES" == split ]] || stale+=("7702" "7703" "split")
for d in "${stale[@]}"; do
  if [[ -d "${OUT:?}/$d" ]]; then echo "entferne veralteten Ordner $OUT/$d"; rm -rf "${OUT:?}/${d:?}"; fi
done
TIMINGS="$OUT/timings.tsv"
printf 'schritt\tsekunden\tmax_rss_mb\n' > "$TIMINGS"

# Schritt mit Zeit- und Speichermessung ausführen: step <name> <log> <befehl…>
step() {
  local name=$1 log=$2; shift 2
  local t0=$SECONDS tf
  tf=$(mktemp)
  echo "== $name"
  if ! /usr/bin/time -l "$@" > "$log" 2> >(tee -a "$log" > "$tf"); then
    tail -30 "$log"; echo "FEHLER in Schritt $name (Log: $log)"; exit 1
  fi
  wait
  local rss
  rss=$(awk '/maximum resident set size/ {printf "%.0f", $1/1048576}' "$tf")
  rm -f "$tf"
  printf '%s\t%d\t%s\n' "$name" $((SECONDS - t0)) "${rss:-?}" >> "$TIMINGS"
}

MKGMAP_VERSION=$(java -jar "$MKGMAP" --version 2>&1 | head -1 | tr -dc '0-9')
JOBS_OPT=(--max-jobs${MAX_JOBS:+=$MAX_JOBS})
MK=(java -Xmx"$JAVA_XMX" -jar "$MKGMAP")
COMMON=(--product-id=1 --code-page=1252 --lower-case --area-name="$AREA_NAME")

# ------------------------------------------------------------------ Eingaben prüfen/erzeugen
[[ -f "$BASE_PBF" ]] || { echo "Basis-PBF fehlt: $BASE_PBF"; exit 1; }
if [[ "$HEIGHTS" == smv25 && ( "$CONTOURS" != none || "$SPOTS" == yes ) ]] && \
   [[ ! -f "$CONTOURS_PBF" || ! -f "$SPOTS_PBF" ]]; then
  # Gletscherkurven: SMV25 hat auf Gletschern fast keine Kurven (LK: Gletscher-Raster). Ohne die
  # swissALTI3D-Kurven (GLACIER_FILL_PBF) fehlen sie, z. B. am Blauschnee (Gerätetest 2026-11-06).
  if [[ "$CONTOURS" != none && -n "$GLACIER_FILL_PBF" && ! -f "$GLACIER_FILL_PBF" ]]; then
    if [[ "$PROFILE" == test ]]; then
      GL_WORK=$(dirname "$GLACIER_FILL_PBF"); mkdir -p "$GL_WORK"
      GL_VRT="$DEM_WORK/alti3d_2m.vrt"; [[ -f "$GL_VRT" ]] || GL_VRT="$MAIN/work/dem/alti3d_2m.vrt"
      step glacier_contours "$OUT/glacier_contours.log" \
        "$PYTHON" src/dem/build_dem.py contours --bbox ${BBOX//,/ } --work "$GL_WORK" --vrt "$GL_VRT"
      step glacier_pbf "$OUT/glacier_pbf.log" "$PYTHON" src/dem/build_dem.py pbf --bbox ${BBOX//,/ } --work "$GL_WORK"
    else
      echo "WARNUNG: GLACIER_FILL_PBF fehlt ($GLACIER_FILL_PBF), Gletscher ohne Höhenkurven (src/dem/run_ch.py)"
    fi
  fi
  step smv25_heights "$OUT/smv25_heights.log" \
    "$PYTHON" src/dem/smv25_heights.py convert --src "$SMV25_SRC" --bbox ${BBOX//,/ } --work "$SMV25_WORK" \
    ${GLACIER_FILL_PBF:+$([[ -f "$GLACIER_FILL_PBF" ]] && echo "--glacier-fill $GLACIER_FILL_PBF")}
fi
if [[ "$HEIGHTS" == alti3d && "$CONTOURS" != none && ! -f "$CONTOURS_PBF" ]]; then
  step dem_contours "$OUT/build_dem.log" \
    "$PYTHON" src/dem/build_dem.py all --bbox ${BBOX//,/ } --work "$DEM_WORK"
fi
if [[ "$DEM" == yes && ! -f "$HGT_DIR/dem.poly" ]]; then
  [[ -f "$DEM_WORK/alti3d_2m.vrt" ]] || step dem_mosaic "$OUT/build_dem_mosaic.log" \
    "$PYTHON" src/dem/build_dem.py mosaic --work "$DEM_WORK"
  POLY_OPT=(); [[ "$DEM_POLY" != "$HGT_DIR/dem.poly" ]] && POLY_OPT=(--poly "$DEM_POLY")
  step dem_hgt "$OUT/build_dem_hgt.log" "$PYTHON" src/dem/build_dem.py hgt --bbox ${BBOX//,/ } \
    --work "$DEM_WORK" --hgt-arcsec "$HGT_ARCSEC" --hgt-smooth "$HGT_SMOOTH" --hgt-out "$HGT_DIR" ${POLY_OPT[@]+"${POLY_OPT[@]}"}
fi
if [[ "$SPOTS" == yes && ! -f "$SPOTS_PBF" ]]; then
  step spot_heights "$OUT/spot_heights.log" \
    "$PYTHON" src/dem/spot_heights.py --bbox ${BBOX//,/ } --work "$DEM_WORK"
fi
if [[ "$ROUTES" == yes && ! -f "$ROUTES_PBF" ]]; then
  # nur die Umwandlung aus src/routes/build.sh, aber mit eigenem Ziel (ROUTES_PBF) und BBOX
  mkdir -p "$(dirname "$ROUTES_PBF")"
  step routes_convert "$OUT/routes_build.log" python3 -I src/routes/convert_routes.py \
    --downloads "$HELVETOPO_DATA" --bbox "$BBOX" --out "${ROUTES_PBF%.pbf}"
  # POIs, die die Landeskarte nicht zeigt (wie src/routes/build.sh)
  step routes_pois "$OUT/routes_pois.log" "$PYTHON" -E -s -m src.routes.pois_overlay --bbox "$BBOX" \
    --out "${ROUTES_PBF%.pbf}.pois.osm"
  step routes_pbf "$OUT/routes_osmium.log" osmium merge -O "${ROUTES_PBF%.pbf}" "${ROUTES_PBF%.pbf}.pois.osm" \
    -o "$ROUTES_PBF"
fi

# ------------------------------------------------------------------ Quellenangaben
# Garmin zeigt am Gerät nur die zweite Copyright-Zeile → Pflichtangabe in beiden Zeilen.
SRC_ST="©swisstopo"
SRC_ALL="©swisstopo; Bundesamt für Strassen, Kanton, Stiftung SchweizMobil"
M="$OUT/meta"; mkdir -p "$M"
printf '%s\n%s\n' "$SRC_ST" "$SRC_ST" > "$M/copyright_swisstopo.txt"
printf '%s\n%s\n' "$SRC_ALL" "$SRC_ALL" > "$M/copyright_all.txt"
render_tpl() {
  sed -e "s|@VERSION@|$VERSION|g" -e "s|@AREA@|$AREA_NAME|g" -e "s|@MKGMAP@|r$MKGMAP_VERSION|g" \
      -e "s|@CONTOURS@|$CONTOURS|g" -e "s|@DEVICE_FAMILIES@|$DEVICE_FAMILIES|g" "$1"
}
for t in 7701 7702 7703 all; do render_tpl "src/build/templates/license_$t.txt" > "$M/license_$t.txt"; done
# Familie 7701 enthält bei Routen auch ASTRA-/SchweizMobil-Daten
if [[ "$ROUTES" == yes ]]; then COPY_7701="$M/copyright_all.txt"; LIC_7701="$M/license_all.txt"
else COPY_7701="$M/copyright_swisstopo.txt"; LIC_7701="$M/license_7701.txt"; fi

# ------------------------------------------------------------------ TYP: Routen-Typen verschieben, zusammenführen, prüfen
# Routen-Style und -TYP belegen dieselben Linientypen wie die Basis (0x10e00–0x10e02, 0x10e10–0x10e12).
# In der gemeinsamen Familie werden sie per ROUTES_TYPE_REMAP (Präfix alt:neu) verschoben.
RSTYLE="$M/style_routes"
rm -rf "$RSTYLE"; cp -R src/style/routes "$RSTYLE"
cp src/style/typ/routes.txt "$M/routes_7701.txt"
if [[ -n "$ROUTES_TYPE_REMAP" ]]; then
  from=${ROUTES_TYPE_REMAP%%:*}; to=${ROUTES_TYPE_REMAP##*:}
  for f in "$RSTYLE"/lines "$RSTYLE"/points "$RSTYLE"/polygons "$M/routes_7701.txt"; do
    [[ -f "$f" ]] && perl -pi -e "s/\\b${from}([0-9a-fA-F]{2})\\b/${to}\$1/g" "$f"
  done
fi
TYP_SRC=(src/style/typ/swisstopo.txt)
[[ "$ROUTES" == yes ]] && TYP_SRC+=("$M/routes_7701.txt")
[[ "$CONTOURS" == overlay ]] && TYP_SRC+=(src/style/typ/contours.txt)
# 0x20–0x22 sind in Basis und Höhenlinien dieselben Garmin-Höhenlinien: Basis-Definition gilt.
step typ_merge "$M/typ_merge.log" python3 -I src/build/merge_typ.py --fid 7701 \
  --out "$M/ch_7701.txt" --shared line:0x20,line:0x21,line:0x22 "${TYP_SRC[@]}"
grep -E 'TYP-Prüfung|Hinweis' "$M/typ_merge.log" || true
# einzelne Quellen auf interne Doppel prüfen
for t in src/style/typ/swisstopo.txt src/style/typ/routes.txt src/style/typ/contours.txt; do
  python3 -I src/build/merge_typ.py --check-only "$t" 2>/dev/null || { echo "FEHLER: Doppel in $t"; exit 1; }
done

# ------------------------------------------------------------------ 7701 Basiskacheln
B="$OUT/7701"
rm -rf "$B"; mkdir -p "$B/tiles"
BASE_IN="$BASE_PBF"
EXTRA=()
[[ "$CONTOURS" == embedded ]] && EXTRA+=("$CONTOURS_PBF")
if [[ "$SPOTS" == yes ]]; then
  # Koten neben benannten Gipfeln/Hügeln/Pässen der Basis-PBF entfernen (verdrängen sonst deren Namen)
  step spots_filter "$B/spots_filter.log" python3 -I src/dem/filter_spots.py \
    --spots "$SPOTS_PBF" --base "$BASE_PBF" --out "$B/spot_heights.filtered.osm.pbf" --radius "$SPOTS_NAMED_RADIUS"
  grep -E '^Koten:' "$B/spots_filter.log" || true
  EXTRA+=("$B/spot_heights.filtered.osm.pbf")
fi
# Felsschraffen und Schattenflächen aus swissALTI3D (src/dem/rock_relief.py, IDs ab 7710·10^12)
# Rechnet in 20-km-Kacheln (je ca. 1,5 GB RAM, RELIEF_JOBS parallel). Schweiz: ca. 2 min.
if [[ "$RELIEF" == yes ]]; then
  if [[ ! -f "$RELIEF_PBF" ]]; then
    RELIEF_VRT="$DEM_WORK/alti3d_2m.vrt"; [[ -f "$RELIEF_VRT" ]] || RELIEF_VRT="$MAIN/work/dem/alti3d_2m.vrt"
    step rock_relief "$OUT/rock_relief.log" "$PYTHON" src/dem/rock_relief.py --bbox ${BBOX//,/ } \
      --vrt "$RELIEF_VRT" --jobs "$RELIEF_JOBS" --out "$(dirname "$RELIEF_PBF")"
  fi
  EXTRA+=("$RELIEF_PBF")
fi
if (( ${#EXTRA[@]} )); then
  # ID-Bereiche: Basis ab 1, Höhenlinien ab 7703·10^12, Koten ab 77045·10^11 → keine Kollision
  BASE_IN="$B/base_merged.osm.pbf"
  step 7701_merge "$B/merge.log" osmium merge --overwrite -o "$BASE_IN" "$BASE_PBF" "${EXTRA[@]}"
fi
step 7701_splitter "$B/splitter.log" java -Xmx"$JAVA_XMX" -jar "$SPLITTER" \
  --output-dir="$B/tiles" --mapid=77010001 --max-nodes="$SPLITTER_MAX_NODES" \
  --keep-complete=true --output=pbf --description="Helvetopo" \
  ${SPLITTER_POLY:+--polygon-file="$SPLITTER_POLY"} "$BASE_IN"

DEM_OPTS=()
if [[ "$DEM" == yes ]]; then
  # Geräte brauchen einen DEM-Abstand pro Level (mkgmap-Doku --dem-dists), sonst fehlt Schummerung
  n_levels=$(grep -E '^levels *=' src/style/swisstopo/options | tr ',' '\n' | grep -c ':')
  n_dists=$(tr ',' '\n' <<< "$DEM_DISTS" | grep -c .)
  if (( n_levels != n_dists )) && [[ "${DEM_LEVEL_CHECK:-yes}" == yes ]]; then
    echo "DEM_DISTS hat $n_dists Werte, src/style/swisstopo/options aber $n_levels Levels"; exit 1
  fi
  DEM_OPTS=(--dem="$HGT_DIR" --dem-dists="$DEM_DISTS" --dem-interpolation="$DEM_INTERPOLATION"
            --dem-poly="$DEM_POLY" --show-profiles=1)
fi
BOUNDS_OPTS=()
[[ -n "$BOUNDS" ]] && BOUNDS_OPTS=(--bounds="$BOUNDS")

step 7701_mkgmap "$B/mkgmap.log" "${MK[@]}" "${COMMON[@]}" \
  --output-dir="$B" \
  --style-file=src/style/swisstopo ${STYLE_OPTIONS:+--style-option="$STYLE_OPTIONS"} \
  --family-id=7701 --family-name="$MAP_NAME" --series-name="$MAP_NAME" \
  --description="Helvetopo Vektor ©swisstopo" \
  --overview-mapname=77010000 --overview-mapnumber=77010000 \
  --copyright-file="$M/copyright_swisstopo.txt" --license-file="$M/license_7701.txt" \
  --route --drive-on=right --country-name=Schweiz --country-abbr=CHE \
  --index --housenumbers \
  --location-autofill=is_in,nearest --link-pois-to-ways \
  --process-destination --process-exits \
  --add-pois-to-areas --remove-short-arcs \
  --polygon-size-limits="24:0,23:1,22:1,21:1,20:1,19:1,18:2,16:1,14:1,12:1" \
  --simplify-polygons="24:0,23:0,22:0,21:2.6" \
  --report-routing-islands \
  ${DEM_OPTS[@]+"${DEM_OPTS[@]}"} ${BOUNDS_OPTS[@]+"${BOUNDS_OPTS[@]}"} \
  "${JOBS_OPT[@]}" \
  -c "$B/tiles/template.args"

# ------------------------------------------------------------------ Overlay-Kacheln
build_routes() {  # <fid> <mapid> <dir> <style>
  local fid=$1 mapid=$2 dir=$3 style=$4
  rm -rf "$dir"; mkdir -p "$dir/tiles"
  # Kacheln wie bei den Höhenlinien: Als eine Kachel überschreitet die ganze Schweiz die RGN-Grenze
  # von 16 MiB (Schweiz-Build 2026-11-06). Im Testgebiet entsteht weiterhin eine Kachel.
  step "${fid}_routes_splitter" "$dir/splitter.log" java -Xmx"$JAVA_XMX" -jar "$SPLITTER" \
    --output-dir="$dir/tiles" --mapid="$mapid" --max-nodes="${ROUTES_MAX_NODES:-800000}" \
    --keep-complete=true --output=pbf --description="Helvetopo Routen" "$ROUTES_PBF"
  step "${fid}_routes_mkgmap" "$dir/mkgmap.log" "${MK[@]}" "${COMMON[@]}" \
    --output-dir="$dir" --style-file="$style" \
    --family-id="$fid" --family-name="Helvetopo Routen" --series-name="Helvetopo Routen" \
    --description="Helvetopo Routen ©swisstopo ASTRA SchweizMobil" \
    --overview-mapname="${fid}0000" --overview-mapnumber="${fid}0000" \
    --copyright-file="$M/copyright_all.txt" --license-file="$M/license_7702.txt" \
    --transparent --draw-priority=30 --merge-lines --reduce-point-density=2 \
    "${JOBS_OPT[@]}" -c "$dir/tiles/template.args"
}
build_contours() {  # <fid> <mapid> <dir>
  local fid=$1 mapid=$2 dir=$3
  rm -rf "$dir"; mkdir -p "$dir/tiles"
  step "${fid}_contours_splitter" "$dir/splitter.log" java -Xmx"$JAVA_XMX" -jar "$SPLITTER" \
    --output-dir="$dir/tiles" --mapid="$mapid" --max-nodes=1600000 \
    --output=pbf --description="Helvetopo Hoehenlinien" "$CONTOURS_PBF"
  step "${fid}_contours_mkgmap" "$dir/mkgmap.log" "${MK[@]}" "${COMMON[@]}" \
    --output-dir="$dir" --style-file=src/style/contours \
    --family-id="$fid" --family-name="Helvetopo Hoehenlinien" --series-name="Helvetopo Hoehenlinien" \
    --description="Helvetopo Hoehenlinien ©swisstopo" \
    --overview-mapname="${fid}0000" --overview-mapnumber="${fid}0000" \
    --copyright-file="$M/copyright_swisstopo.txt" --license-file="$M/license_7703.txt" \
    --transparent --draw-priority=28 --reduce-point-density=2 \
    "${JOBS_OPT[@]}" -c "$dir/tiles/template.args"
}
tiles() { ls "$1"/[0-9]*.img | grep -vE '/[0-9]{4}0000\.img$'; }

# Gemeinsame Familie 7701 (immer, für BaseCamp)
[[ "$ROUTES" == yes ]] && build_routes 7701 77011001 "$OUT/7701-routes" "$RSTYLE"
[[ "$CONTOURS" == overlay ]] && build_contours 7701 77012001 "$OUT/7701-contours"

# ------------------------------------------------------------------ Familie 7701 zusammenstellen
S="$OUT/single"; rm -rf "$S"; mkdir -p "$S"
SINGLE_TILES=($(tiles "$B"))
[[ "$ROUTES" == yes ]] && SINGLE_TILES+=($(tiles "$OUT/7701-routes"))
[[ "$CONTOURS" == overlay ]] && SINGLE_TILES+=($(tiles "$OUT/7701-contours"))
GMAPSUPP_SINGLE=()
[[ "$DEVICE_FAMILIES" == single && ( "$DEVICE_ROUTES" == embedded || "$ROUTES" != yes ) ]] && GMAPSUPP_SINGLE=(--gmapsupp)
OVDEM=()
[[ "$DEM" == yes ]] && OVDEM=(--dem="$HGT_DIR" --dem-poly="$DEM_POLY" --overview-dem-dist="$OVERVIEW_DEM_DIST")
step 7701_family "$S/mkgmap.log" "${MK[@]}" "${COMMON[@]}" \
  --output-dir="$S" \
  --family-id=7701 --family-name="$MAP_NAME" --series-name="$MAP_NAME" \
  --description="Helvetopo Vektor ©swisstopo $VERSION" \
  --overview-mapname=77010000 --overview-mapnumber=77010000 \
  --copyright-file="$COPY_7701" --license-file="$LIC_7701" \
  ${OVDEM[@]+"${OVDEM[@]}"} \
  --index --tdbfile --gmapi ${GMAPSUPP_SINGLE[@]+"${GMAPSUPP_SINGLE[@]}"} \
  "${SINGLE_TILES[@]}" "$M/ch_7701.txt"

# ------------------------------------------------------------------ Gerätedatei ohne Routen (Routen als Overlay 7702)
if [[ "$DEVICE_FAMILIES" == single && "$DEVICE_ROUTES" == overlay && "$ROUTES" == yes ]]; then
  V="$OUT/device"; rm -rf "$V"; mkdir -p "$V"
  DEV_TILES=($(tiles "$B"))
  [[ "$CONTOURS" == overlay ]] && DEV_TILES+=($(tiles "$OUT/7701-contours"))
  step 7701_device "$V/mkgmap.log" "${MK[@]}" "${COMMON[@]}" \
    --output-dir="$V" \
    --family-id=7701 --family-name="$MAP_NAME" --series-name="$MAP_NAME" \
    --description="Helvetopo Vektor ©swisstopo $VERSION" \
    --overview-mapname=77010000 --overview-mapnumber=77010000 \
    --copyright-file="$M/copyright_swisstopo.txt" --license-file="$M/license_7701.txt" \
    ${OVDEM[@]+"${OVDEM[@]}"} \
    --index --gmapsupp "${DEV_TILES[@]}" src/style/typ/swisstopo.txt
fi

# ------------------------------------------------------------------ Geräte-Variante mit getrennten Familien
if [[ "$DEVICE_FAMILIES" == split ]]; then
  [[ "$ROUTES" == yes ]] && build_routes 7702 77020001 "$OUT/7702" src/style/routes
  [[ "$CONTOURS" == overlay ]] && build_contours 7703 77030001 "$OUT/7703"
  P="$OUT/split"; rm -rf "$P"; mkdir -p "$P"
  GM=(--family-id=7701 --family-name="$MAP_NAME" --series-name="$MAP_NAME" $(tiles "$B") src/style/typ/swisstopo.txt)
  [[ "$ROUTES" == yes ]] && GM+=(--family-id=7702 --family-name="Helvetopo Routen" --series-name="Helvetopo Routen"
                                $(tiles "$OUT/7702") src/style/typ/routes.txt)
  [[ "$CONTOURS" == overlay ]] && GM+=(--family-id=7703 --family-name="Helvetopo Hoehenlinien" --series-name="Helvetopo Hoehenlinien"
                                      $(tiles "$OUT/7703") src/style/typ/contours.txt)
  step gmapsupp_split "$P/mkgmap.log" "${MK[@]}" --output-dir="$P" --gmapsupp --index --code-page=1252 \
    --product-id=1 --description="Helvetopo Vektor ©swisstopo $VERSION" "${GM[@]}"
  rm -f "$P"/osmmap.* 2>/dev/null || true
fi

# ------------------------------------------------------------------ dist
D="$OUT/dist"; rm -rf "$D"; mkdir -p "$D/BaseCamp"
if [[ "$DEVICE_FAMILIES" == split ]]; then cp "$OUT/split/gmapsupp.img" "$D/"
elif [[ -f "$OUT/device/gmapsupp.img" && "$DEVICE_ROUTES" == overlay && "$ROUTES" == yes ]]; then cp "$OUT/device/gmapsupp.img" "$D/"
else cp "$S/gmapsupp.img" "$D/"; fi
cp -R "$S"/*.gmap "$D/BaseCamp/"
render_tpl src/build/templates/README.txt > "$D/README.txt"
render_tpl src/build/templates/LICENSE.txt > "$D/LICENSE.txt"

echo
column -t "$TIMINGS"
ls -la "$D"; du -sh "$D"/BaseCamp/*

# ------------------------------------------------------------------ automatische Prüfungen
# Lizenz: keine OSM/ODbL-Texte, überall ©swisstopo; mit Routen zusätzlich die ASTRA-Angabe
CHECK_DIRS=("$D" "$S")
[[ "$DEVICE_FAMILIES" == split ]] && CHECK_DIRS+=("$OUT/split")
if [[ -d "$OUT/device" && "$DEVICE_ROUTES" == overlay && "$ROUTES" == yes ]]; then
  # Gerätedatei ohne Routen: nur ©swisstopo; BaseCamp-gmapi mit Routen: zusätzlich ASTRA
  REQUIRE_ASTRA=no src/build/check_license.sh "$D/gmapsupp.img" "$OUT/device"
  CHECK_DIRS=("$D/BaseCamp" "$S")
fi
REQUIRE_ASTRA=$([[ "$ROUTES" == yes ]] && echo yes || echo no) src/build/check_license.sh "${CHECK_DIRS[@]}"

# ------------------------------------------------------------------ Ablage (nur mit HELVETOPO_STORE)
# Kopiert dist/ nach $HELVETOPO_STORE/$STORE_SUBDIR/ und prüft die Kopie (src/build/store.sh).
# STORE_CLEAN=yes entfernt danach $OUT (nur unter work/).
if [[ -n "${HELVETOPO_STORE:-}" ]]; then
  STORE_ARGS=()
  [[ "$STORE_CLEAN" == yes ]] && STORE_ARGS+=(--clean "$OUT")
  src/build/store.sh ${STORE_ARGS[@]+"${STORE_ARGS[@]}"} "$STORE_SUBDIR" "$D/"
fi
