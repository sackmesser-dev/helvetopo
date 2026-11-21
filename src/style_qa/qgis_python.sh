#!/bin/bash
# Startet ein Skript mit dem Python des QGIS-App-Bundles (headless, keine GUI).
# QGIS_APP setzen, sonst das neueste /Applications/QGIS*.app.
A=${QGIS_APP:-$(ls -d /Applications/QGIS*.app/Contents 2>/dev/null | sort | tail -n 1)}
[[ -d "$A" ]] || { echo "QGIS nicht gefunden. QGIS_APP auf <QGIS.app>/Contents setzen." >&2; exit 1; }
export PYTHONHOME=$A/Frameworks
export PYTHONPATH=$A/Resources/python3.12/site-packages:$A/Resources/python3.12
export QT_QPA_PLATFORM=offscreen
exec "$A/MacOS/python3.12" "$@"
