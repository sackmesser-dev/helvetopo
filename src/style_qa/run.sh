#!/bin/bash
# Stil-QA: misst die aktuelle Stil-Version gegen das swisstopo-Layout (SMV25 + Swiss Map Raster).
#
#   bash src/style_qa/run.sh              # alles, Referenzen nur wenn noch nicht vorhanden
#   bash src/style_qa/run.sh --refs       # Referenzen neu rendern (nach Änderung der Ausschnitte)
#   bash src/style_qa/run.sh --gesamt     # Gesamt-Build in main (work/build: DEM, Koten, Höhenlinien)
#                                           → Ausgabe work/style_qa/gesamt/
#
# Umgebungsvariablen (Vorgaben in src/style_qa/config.py):
#   STYLE_ROOT  Checkout/Worktree mit src/style/… und work/style/testgebiet (Standard: Haupt-Checkout)
#   IMG_DIR     Ordner mit den Kacheln 7701xxxx.img     TYP_TXT  TYP-Quelltext
#   OVERLAYS    "name=imgordner:typ;…" (Standard: Höhenlinien 7703 aus work/dem/img7703, "" = keine)
#   STYLE_QA_OUT  Ausgabeordner (Standard: work/style_qa im Repo)
# Ausgabe: work/style_qa/report.md, vergleich/*.png, results.json, findings.json, history.json
set -euo pipefail
. "$(dirname "$0")/../paths.sh"   # HELVETOPO_ROOT: Haupt-Checkout mit tools/, .venv/; HELVETOPO_DATA: Rohdaten
cd "$(dirname "$0")/../.."
PY=${PY:-$HELVETOPO_ROOT/.venv/bin/python}
MAIN=${MAIN:-$HELVETOPO_ROOT}
FORCE_REFS=""
for a in "$@"; do
  case $a in
    --refs) FORCE_REFS="--force" ;;
    --gesamt) export QA_TARGET=gesamt ;;
    *) echo "unbekannte Option $a"; exit 2 ;;
  esac
done

if [[ ! -s $HELVETOPO_DATA/smv25/merged/SMV25_CHLV95LN02.gpkg ]]; then
  echo "SMV25 fehlt: Blätter 216/217/226/227 nach $HELVETOPO_DATA/smv25/ laden (STAC ch.swisstopo.swiss-map-vector25), dann:"
  echo "  bash src/style_qa/merge_smv25.sh"
  exit 1
fi
echo "== Referenzen (SMV25 über QGIS headless, SMR, Relief)"
"$PY" -I -B src/style_qa/refs.py $FORCE_REFS
echo "== Unsere Karte (render_img.py)"
"$PY" -I -B src/style_qa/render_ours.py --force | grep -c '^ok' | sed 's/^/Bilder: /'
echo "== Messen"
"$PY" -I -B src/style_qa/measure.py | tail -1
echo "== Bericht"
"$PY" -I -B src/style_qa/report.py
