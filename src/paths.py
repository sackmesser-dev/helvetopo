"""Gemeinsame Pfade von Helvetopo.

Zwei Wurzeln:

* ``REPO``: der Checkout bzw. Worktree, in dem dieser Code liegt (Quellen, ``work/``).
* ``MAIN``: der Haupt-Checkout mit ``downloads/``, ``tools/`` und ``.venv/``. Diese Ordner
  sind gitignored und liegen nur dort, Worktrees zeigen deshalb auf den Haupt-Checkout.

``MAIN`` wird so bestimmt:

1. Umgebungsvariable ``HELVETOPO_ROOT``, falls gesetzt.
2. Sonst über ``git rev-parse --git-common-dir``: der Elternordner des gemeinsamen
   ``.git``-Ordners (bei einem Worktree ist das der Haupt-Checkout).
3. Sonst ``REPO`` (z. B. ein entpacktes Archiv ohne Git).

Rohdaten (``DOWNLOADS``) liegen standardmässig in ``MAIN/downloads``. Die Umgebungsvariable
``HELVETOPO_DATA`` setzt einen anderen Ordner, z. B. eine eingebundene Netzfreigabe.
``HELVETOPO_STORE`` ist das Ziel für fertige Ausgaben (``src/build/store.sh``), leer = keine Ablage.

Einbinden aus einem Skript unter ``src/<modul>/``::

    sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import paths

Aus dem Paket ``src.vector`` (Aufruf mit ``-m``): ``from ..paths import DOWNLOADS``.
Das Gegenstück für Shell-Skripte ist ``src/paths.sh``.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _main_checkout() -> Path:
    env = os.environ.get("HELVETOPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        out = ""
    if out:
        common = Path(out)
        if common.name == ".git":
            return common.parent
    return REPO


MAIN = _main_checkout()
DOWNLOADS = Path(os.environ.get("HELVETOPO_DATA") or MAIN / "downloads").expanduser()
STORE = os.environ.get("HELVETOPO_STORE", "")
TOOLS = MAIN / "tools"
VENV_PYTHON = MAIN / ".venv" / "bin" / "python"
MKGMAP = TOOLS / "mkgmap-r4924" / "mkgmap.jar"
SPLITTER = TOOLS / "splitter-r654" / "splitter.jar"

# Häufig gebrauchte Rohdaten
TLM_GPKG = DOWNLOADS / "swisstlm3d" / "SWISSTLM3D_2026_LV95_LN02.gpkg"
NAMES_GPKG = DOWNLOADS / "swissnames3d" / "swissnames3d_2026_2056.gpkg"
BOUNDARIES_GPKG = DOWNLOADS / "swissboundaries3d" / "swissBOUNDARIES3D_1_5_LV95_LN02.gpkg"
SMR_DIR = DOWNLOADS / "smr"
SWISSALTI3D_2M = DOWNLOADS / "swissalti3d" / "2m"


if __name__ == "__main__":
    for k in ("REPO", "MAIN", "DOWNLOADS", "TOOLS", "STORE"):
        print(f"{k}={globals()[k]}")
