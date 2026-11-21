#!/bin/bash
# Führt die SMV25-Blätter (STAC ch.swisstopo.swiss-map-vector25) des Testgebiets zu einem
# GeoPackage zusammen, wie es das offizielle QGIS-Projekt SMV25_CHLV95LN02.qgs erwartet
# (./SMV25_CHLV95LN02.gpkg und ./SMV25_CHLV95LN02_RASTER/*.tif als VRT).
set -euo pipefail
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
SRC=${1:-$HELVETOPO_DATA/smv25}
OUT=${2:-$SRC/merged}
mkdir -p "$OUT/SMV25_CHLV95LN02_RASTER"
G=$OUT/SMV25_CHLV95LN02.gpkg
T=$OUT/_merge_tmp.gpkg
SHEETS=(216/SMV25_CHLV95LN02.gpkg 217/SMV25_CHLV95LN02_217.gpkg 226/SMV25_CHLV95LN02.gpkg 227/SMV25_CHLV95LN02_227.gpkg)
if [ ! -s "$G" ]; then
  rm -f "$T"
  for s in "${SHEETS[@]}"; do
    for l in $(ogrinfo -q "$SRC/$s" | sed -E 's/^[0-9]+: ([^ ]+).*/\1/'); do
      if [ -e "$T" ]; then upd=(-update -append); else upd=(-f GPKG); fi
      ogr2ogr "${upd[@]}" -gt 65536 "$T" "$SRC/$s" "$l" -nln "$l" || echo "WARN $s $l"
    done
  done
  mv "$T" "$G"
fi
for r in KOMB FELS GEROELL GLET; do
  gdalbuildvrt -q -overwrite "$OUT/SMV25_CHLV95LN02_RASTER/$r.vrt" \
    "$SRC"/216/SMV25_CHLV95LN02_RASTER/$r.tif "$SRC"/217/SMV25_CHLV95LN02_217_RASTER/$r.tif \
    "$SRC"/226/SMV25_CHLV95LN02_RASTER/$r.tif "$SRC"/227/SMV25_CHLV95LN02_227_RASTER/$r.tif
done
ls -la "$OUT" "$OUT/SMV25_CHLV95LN02_RASTER"
