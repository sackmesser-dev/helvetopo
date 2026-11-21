# shellcheck shell=sh
# Gemeinsame Pfade von Helvetopo für Shell-Skripte (POSIX sh und bash), Gegenstück zu src/paths.py.
# Einbinden aus einem Skript unter src/<modul>/:
#   . "$(dirname "$0")/../paths.sh"
#
# Setzt (sofern nicht schon gesetzt); exportiert werden HELVETOPO_ROOT und HELVETOPO_DATA, nicht
# HELVETOPO_REPO, damit Kindprozesse aus anderen Worktrees ihren eigenen HELVETOPO_REPO bestimmen:
#   HELVETOPO_REPO  Checkout/Worktree, in dem das aufrufende Skript liegt (Quellen, work/)
#   HELVETOPO_ROOT  Haupt-Checkout mit downloads/, tools/ und .venv/ (gitignored, nur dort).
#                   Bestimmung: Umgebung, sonst Elternordner von `git rev-parse --git-common-dir`
#                   (bei einem Worktree der Haupt-Checkout), sonst HELVETOPO_REPO.
#   HELVETOPO_DATA  Rohdaten, Standard $HELVETOPO_ROOT/downloads (z. B. eine eingebundene Netzfreigabe).
#   HELVETOPO_STORE Ziel für fertige Ausgaben (src/build/store.sh): Ordner oder rsync-Ziel, leer = keine Ablage.

if [ -z "${HELVETOPO_REPO:-}" ]; then
  _hp_dir=$(cd "$(dirname "$0")" && pwd)
  while [ "$_hp_dir" != / ] && [ ! -f "$_hp_dir/src/paths.sh" ]; do
    _hp_dir=$(dirname "$_hp_dir")
  done
  HELVETOPO_REPO=$_hp_dir
  unset _hp_dir
fi

if [ -z "${HELVETOPO_ROOT:-}" ]; then
  _hp_common=$(git -C "$HELVETOPO_REPO" rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || _hp_common=
  if [ -n "$_hp_common" ] && [ "$(basename "$_hp_common")" = .git ]; then
    HELVETOPO_ROOT=$(dirname "$_hp_common")
  else
    HELVETOPO_ROOT=$HELVETOPO_REPO
  fi
  unset _hp_common
fi

export HELVETOPO_ROOT
HELVETOPO_DATA=${HELVETOPO_DATA:-$HELVETOPO_ROOT/downloads}
export HELVETOPO_DATA
