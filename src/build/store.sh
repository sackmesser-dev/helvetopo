#!/usr/bin/env bash
# Fertige Ausgaben in die Ablage kopieren (HELVETOPO_STORE), danach prüfen und auf Wunsch
# lokale Zwischendateien entfernen.
#
#   src/build/store.sh [--clean <ordner>]... <unterordner> <datei|ordner>...
#
# Beispiele:
#   src/build/store.sh vektor/2026-11-06 work/build-ch/dist/
#   src/build/store.sh --clean work/raster_img/ch pixel/2026-11 work/raster_img/ch/out/*.img
#
# Umgebung:
#   HELVETOPO_STORE      Ziel: lokaler Ordner (z. B. eingebundene Netzfreigabe) oder rsync-Ziel
#                        wie "benutzer@host:pfad". Leer = keine Ablage, das Skript endet ohne Fehler.
#   HELVETOPO_STORE_RSH  Shell für rsync bei einem entfernten Ziel, z. B. "ssh -i ~/.ssh/schluessel".
#
# Ablauf:
#   1. rsync kopiert die Quellen nach $HELVETOPO_STORE/<unterordner>/ (fortsetzbar, --partial).
#   2. Ein zweiter rsync-Lauf vergleicht Grösse und Prüfsumme (-c, ohne Änderung). Meldet er eine
#      Datei, gilt die Ablage als fehlerhaft (Exit 1), und es wird nichts gelöscht.
#   3. Nur nach erfolgreicher Prüfung entfernt --clean die genannten Ordner. Erlaubt sind nur
#      Ordner unter work/ des Checkouts.
set -euo pipefail

. "$(dirname "$0")/../paths.sh"

clean=()
while [[ $# -gt 0 && $1 == --clean ]]; do
  clean+=("$2"); shift 2
done
if [[ $# -lt 2 ]]; then
  sed -n '2,10p' "$0" >&2
  exit 2
fi
sub=${1%/}; shift

if [[ -z "${HELVETOPO_STORE:-}" ]]; then
  echo "store.sh: HELVETOPO_STORE ist leer, keine Ablage."
  exit 0
fi

dest="${HELVETOPO_STORE%/}/$sub/"
opts=(-rtp --partial --chmod=D2775,F664 --exclude .DS_Store)
[[ -n "${HELVETOPO_STORE_RSH:-}" ]] && opts+=(-e "$HELVETOPO_STORE_RSH")

# Zielordner anlegen (rsync legt nur die letzte Ebene an)
if [[ "$HELVETOPO_STORE" == *:* ]]; then
  rsync "${opts[@]}" --mkpath "$@" "$dest"
else
  mkdir -p "$dest"
  rsync "${opts[@]}" "$@" "$dest"
fi

# Prüfung: Prüfsummenvergleich ohne Übertragung. Jede gemeldete Datei weicht ab.
diff=$(rsync "${opts[@]}" -c -n --out-format='%n' "$@" "$dest" | grep -v '/$' || true)
if [[ -n "$diff" ]]; then
  echo "store.sh: Abweichung nach dem Kopieren:" >&2
  echo "$diff" >&2
  exit 1
fi
echo "store.sh: abgelegt und geprüft: $dest"

for d in ${clean[@]+"${clean[@]}"}; do
  abs=$(cd "$d" && pwd -P)
  case "$abs/" in
    "$(cd "$HELVETOPO_REPO/work" && pwd -P)"/?*) ;;
    *) echo "store.sh: --clean nur unter work/, übersprungen: $d" >&2; continue ;;
  esac
  echo "store.sh: entferne Zwischendateien $abs"
  rm -rf "${abs:?}"
done
