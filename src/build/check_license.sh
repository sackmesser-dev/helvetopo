#!/usr/bin/env bash
# Prüft, dass in keiner IMG/TDB/TYP fremde Lizenztexte stehen (mkgmap-Standardtext zu
# OpenStreetMap/ODbL/DbCL) und dass jede Karte die Pflichtangabe ©swisstopo trägt.
#   src/build/check_license.sh <ordner|datei>...
# Mit REQUIRE_ASTRA=yes muss jede TDB/gmapsupp/Release-IMG (Helvetopo_*.img) zusätzlich "Bundesamt für Strassen, Kanton,
# Stiftung SchweizMobil" enthalten (Karten mit Routen). Exit 1 bei Treffern. Läuft automatisch am Ende von build_all.sh und src/dem/build_img.sh.
set -uo pipefail
# Genaue Textstellen des mkgmap-Standardtexts, mit Gross-/Kleinschreibung: in grossen IMG kommen
# kurze Folgen wie "odbl" sonst zufällig in komprimierten Binärdaten vor (Fehlalarm).
FORBIDDEN='OpenStreetMap|openstreetmap\.org|opendatacommons|licenses/odbl|licenses/dbcl|Open Database License|osmmap|OSM street map'
fail=0; n=0
while IFS= read -r -d '' f; do
  n=$((n+1))
  hits=$(strings -n 4 "$f" | grep -E "$FORBIDDEN" | sort -u)
  if [[ -n "$hits" ]]; then
    echo "FEHLER Fremdlizenz in $f:"; echo "$hits" | sed 's/^/    /'; fail=1
  fi
  case "$f" in
    *.tdb|*gmapsupp.img|*/Helvetopo_*.img|Helvetopo_*.img)
      # ©swisstopo steht als "(c)swisstopo" (TDB, Beschreibung) oder 0xA9 + swisstopo
      if ! LC_ALL=C grep -qaE $'(\xa9|\\(c\\) ?)swisstopo' "$f"; then
        echo "FEHLER keine Quellenangabe ©swisstopo in $f"; fail=1
      fi
      if [[ "${REQUIRE_ASTRA:-no}" == yes ]] && ! LC_ALL=C grep -qaE 'Bundesamt f.{1,2}r Strassen, Kanton, Stiftung SchweizMobil' "$f"; then
        echo "FEHLER keine Quellenangabe ASTRA/SchweizMobil in $f"; fail=1
      fi;;
  esac
done < <(find "$@" -type f \( -iname '*.img' -o -iname '*.tdb' -o -iname '*.typ' \) -print0)
# ovm_-Zwischendateien und osmmap-Namen gelten ebenfalls als Fehler (Dateiname)
if find "$@" -iname 'osmmap*' | grep -q .; then echo "FEHLER Datei osmmap.* vorhanden (fehlendes --overview-mapname)"; fail=1; fi
echo "Lizenz-Check: $n Dateien geprüft, $([[ $fail == 0 ]] && echo ok || echo FEHLER)"
exit $fail
