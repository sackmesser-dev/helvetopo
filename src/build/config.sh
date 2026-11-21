# Konfiguration für src/build/build_all.sh. Jede Variable lässt sich per Umgebung überschreiben,
# z. B.  CONTOURS=embedded src/build/build_all.sh

# Haupt-Checkout mit tools/ und .venv/ (src/paths.sh): MAIN bzw. HELVETOPO_ROOT; Rohdaten in HELVETOPO_DATA,
# sonst über git bestimmt (bei einem Worktree der Haupt-Checkout).
if [[ -n "${MAIN:-}" ]]; then export HELVETOPO_ROOT=$MAIN; fi
source "$REPO/src/paths.sh"
MAIN=$HELVETOPO_ROOT
TOOLS=${TOOLS:-$MAIN/tools}
MKGMAP=${MKGMAP:-$TOOLS/mkgmap-r4924/mkgmap.jar}
SPLITTER=${SPLITTER:-$TOOLS/splitter-r654/splitter.jar}
PYTHON=${PYTHON:-$MAIN/.venv/bin/python}

# Profil: test (Testgebiet) | ch (Schweiz + Liechtenstein). Setzt nur Standardwerte, die
# einzelnen Variablen lassen sich weiterhin überschreiben.
#   PROFILE=ch BASE_PBF=/pfad/ch.osm.pbf src/build/build_all.sh
PROFILE=${PROFILE:-test}
if [[ "$PROFILE" == ch ]]; then
  PERIMETER_DIR=${PERIMETER_DIR:-$REPO/work/perimeter}         # src/build/make_perimeter.py
  [[ -f "$PERIMETER_DIR/ch_fl.poly" ]] || "$PYTHON" "$REPO/src/build/make_perimeter.py" --out "$PERIMETER_DIR" >&2
  BBOX=${BBOX:-$(cat "$PERIMETER_DIR/bbox.txt")}
  AREA_NAME=${AREA_NAME:-Schweiz und Liechtenstein}
  DEM_WORK=${DEM_WORK:-$REPO/work/dem/ch}                      # src/dem/run_ch.py
  DEM_POLY=${DEM_POLY:-$PERIMETER_DIR/ch_fl.poly}
  # splitter --polygon-file: osmosis lehnt den Landesumriss als "self-intersecting" ab (gültige
  # Geometrie, auch vereinfacht); nicht nötig, weil alle Daten innerhalb CH+FL liegen.
  SPLITTER_POLY=${SPLITTER_POLY:-}
  ROUTES_PBF=${ROUTES_PBF:-$REPO/work/routes-ch/routes.osm.pbf}
  OUT=${OUT:-$REPO/work/build-ch}
  JAVA_XMX=${JAVA_XMX:-16g}
  : "${BASE_PBF:?PROFILE=ch braucht BASE_PBF (landesweite PBF von src/vector/convert.py)}"
fi

# Gebiet (nur für Beschriftung und für die Teil-Builds DEM/Routen)
BBOX=${BBOX:-9.0,47.2,9.5,47.5}
AREA_NAME=${AREA_NAME:-Testgebiet Wil-St.Gallen-Saentis}
VERSION=${VERSION:-$(date +%Y-%m-%d)}
# Kartenname auf Gerät und in BaseCamp (Release-Plan): "Helvetopo Vektor <Version>", beim Testgebiet mit Zusatz
if [[ "$PROFILE" == ch ]]; then MAP_NAME=${MAP_NAME:-Helvetopo Vektor $VERSION}
else MAP_NAME=${MAP_NAME:-Helvetopo Vektor $VERSION Testgebiet}; fi

# Eingaben
# Basis-PBF von src/vector/convert.py (siehe docs/vektor/basiskarte.md):
#   .venv/bin/python -m src.vector.convert --out work/vector/testgebiet.osm.pbf --routes-csv work/routes/tlm_routes.csv
BASE_PBF=${BASE_PBF:-$REPO/work/vector/testgebiet.osm.pbf}
# Routen-PBF (src/routes/build.sh). Fehlt sie, baut build_all.sh sie nach work/routes/.
ROUTES_PBF=${ROUTES_PBF:-$REPO/work/routes/routes.osm.pbf}
# Höhen (src/dem/build_dem.py). Fehlen sie, baut build_all.sh sie nach work/dem/.
DEM_WORK=${DEM_WORK:-$REPO/work/dem}
# HGT-Rasterweite: 0.5 (7201², Standard, schärfere Schummerung) oder 1 (3601²), siehe docs/vektor/hoehen.md
HGT_ARCSEC=${HGT_ARCSEC:-0.5}
# Glättung nur im Hügelland (Relief < 400 m je km), Gauss σ in m; 0 = aus. Gebirge bleibt unverändert.
HGT_SMOOTH=${HGT_SMOOTH:-0}
if [[ "$HGT_SMOOTH" != 0 ]]; then HGT_DIR=${HGT_DIR:-$DEM_WORK/hgt$HGT_ARCSEC-s$HGT_SMOOTH}
else HGT_DIR=${HGT_DIR:-$DEM_WORK/hgt$HGT_ARCSEC}; fi
DEM_POLY=${DEM_POLY:-$HGT_DIR/dem.poly}
# Quelle für Höhenkurven und Höhenkoten:
#   smv25  = Landeskarte selbst (Swiss Map Vector 25, DKM25-Kurven und -Koten, src/dem/smv25_heights.py)
#   alti3d = eigene Ableitung aus swissALTI3D (src/dem/build_dem.py, spot_heights.py)
# DEM/Schummerung kommt immer aus swissALTI3D (HGT).
HEIGHTS=${HEIGHTS:-smv25}
SMV25_SRC=${SMV25_SRC:-$HELVETOPO_DATA/smv25-2026}
SMV25_WORK=${SMV25_WORK:-$DEM_WORK/smv25}
# Gletscherkurven fehlen in SMV25 (LK: Gletscher-Raster) → aus der eigenen swissALTI3D-Ableitung
GLACIER_FILL_PBF=${GLACIER_FILL_PBF:-$DEM_WORK/contours.osm.pbf}
if [[ "$HEIGHTS" == smv25 ]]; then
  CONTOURS_PBF=${CONTOURS_PBF:-$SMV25_WORK/contours.osm.pbf}
  SPOTS_PBF=${SPOTS_PBF:-$SMV25_WORK/spot_heights.osm.pbf}
else
  CONTOURS_PBF=${CONTOURS_PBF:-$DEM_WORK/contours.osm.pbf}
  SPOTS_PBF=${SPOTS_PBF:-$DEM_WORK/spot_heights.osm.pbf}
fi
# Felsschraffen und Schattenflächen aus swissALTI3D (src/dem/rock_relief.py, Review 3). Fehlt die
# Datei, baut build_all.sh sie (nur mit RELIEF=yes).
RELIEF_PBF=${RELIEF_PBF:-$DEM_WORK/relief/rock_relief.osm.pbf}
# Eigene Grenzen für --bounds (Adress-/Ortssuche), optional (siehe vector-convert make_bounds.sh)
BOUNDS=${BOUNDS:-}

# Schalter
CONTOURS=${CONTOURS:-embedded}  # embedded = in den Basiskacheln (Standard: Kurven unter Strassen wie LK) | overlay = transparente Kacheln | none
ROUTES=${ROUTES:-yes}           # yes = Overlay 7702 | no
# Felsschraffen und Schattenflächen (src/dem/rock_relief.py, Review 3), in beiden Profilen.
RELIEF=${RELIEF:-yes}
RELIEF_JOBS=${RELIEF_JOBS:-4}   # parallele 20-km-Kacheln, je ca. 1,5 GB RAM
DEM=${DEM:-yes}                 # Schummerung in der Basiskarte
SPOTS=${SPOTS:-yes}             # Höhenkoten (SMV25 bzw. swissALTI3D) in der Basiskarte
SPOTS_NAMED_RADIUS=${SPOTS_NAMED_RADIUS:-300}   # Koten näher an benannten Gipfeln/Pässen entfallen (m)

# DEM-Auflösung je Level der Basiskarte: GENAU EIN Wert pro Level in src/style/swisstopo/options
# (levels = 0:24,1:23,2:22,3:21,4:20,5:19,6:18,7:16 → 8 Werte). mkgmap-Doku: BaseCamp kommt mit einem
# Wert aus, GPS-Geräte brauchen einen pro Level. build_all.sh bricht bei abweichender Anzahl ab.
# Bis 2026-11-06 standen hier nur 7 Werte (Stand vor der Zwischenstufe 19) → Level 16 ohne DEM.
# Stufe 0 = halbe bzw. ganze HGT-Rasterweite (1656 ≈ 0,5", 3312 ≈ 1"), danach ×2 je Auflösungsstufe.
# Grobstufen (Auflösung 19/18/16) mit 106048/212096/424192 (≈ 1/2/4 km) statt bis 848384 (≈ 8 km):
# mkgmap rechnet das DEM je Kachel auf eigenem Raster; 8-km-Zellen ergaben im CH-Build ein
# Kachelraster und graue Treppen über die Landesgrenze (BaseCamp-Test 18). Kostet < 0,1 MB.
# Kommerzielle Garmin-Karten gehen nie unter 3312 (1").
if [[ "$HGT_ARCSEC" == 0.5 ]]; then
  DEM_DISTS=${DEM_DISTS:-1656,6624,13248,26512,53024,106048,212096,424192}
else
  DEM_DISTS=${DEM_DISTS:-3312,6624,13248,26512,53024,106048,212096,424192}
fi
OVERVIEW_DEM_DIST=${OVERVIEW_DEM_DIST:-55000}
DEM_INTERPOLATION=${DEM_INTERPOLATION:-bicubic}   # bicubic | auto | bilinear

# mkgmap --style-option für den Basis-Style, z. B. routing_pref=off (Vergleichsbuild ohne
# Routing-Präferenz) oder routing_pref=velo (Velo-Variante), siehe docs/vektor/routing.md
STYLE_OPTIONS=${STYLE_OPTIONS:-routing_pref=basis;velo_toll=stark}

# Ressourcen
JAVA_XMX=${JAVA_XMX:-8g}
SPLITTER_MAX_NODES=${SPLITTER_MAX_NODES:-1200000}
MAX_JOBS=${MAX_JOBS:-}          # leer = mkgmap wählt nach CPU-Zahl

# Ausgabe
OUT=${OUT:-$REPO/work/build}

# Gerät (gmapsupp): single = alles in Familie 7701 (wie BaseCamp) | split = 7701/7702/7703 getrennt
DEVICE_FAMILIES=${DEVICE_FAMILIES:-single}
# Routen auf dem Gerät: overlay = Gerätedatei ohne Routen, dazu das gemeinsame Routen-Overlay 7702
# (src/raster_img/routen.py, auch für Pixelkarte und Luftbild, am Gerät einzeln schaltbar) |
# embedded = Routen in der Gerätedatei. BaseCamp-gmapi enthält die Routen immer (nur ein Produkt sichtbar).
DEVICE_ROUTES=${DEVICE_ROUTES:-overlay}
# Routen-Typen in der gemeinsamen Familie verschieben (Präfix alt:neu), weil Basis- und Routen-TYP
# dieselben Codes belegen. Leer lassen, sobald der Routen-TYP eigene Codes vergibt.
ROUTES_TYPE_REMAP=${ROUTES_TYPE_REMAP:-0x10e:0x113}

# Ablage fertiger Ausgaben (src/build/store.sh, nur wenn HELVETOPO_STORE gesetzt ist)
STORE_SUBDIR=${STORE_SUBDIR:-vektor/$PROFILE/$VERSION}
STORE_CLEAN=${STORE_CLEAN:-no}  # yes = $OUT nach geprüfter Ablage entfernen
