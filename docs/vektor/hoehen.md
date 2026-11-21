# Höhen: Schummerung, Höhenkurven, Höhenkoten

Stand: 2026-11-04. Code: `src/dem/`. Alle Höhendaten sind ©swisstopo (OGD). SRTM, Copernicus und
andere Höhenmodelle werden nicht beigemischt.

## Übersicht

| Teil | Quelle | Werkzeug | Build-Variable (Standard) |
|---|---|---|---|
| DEM für Schummerung und Profil | swissALTI3D 2 m | `build_dem.py hgt`, `run_ch.py` | `HGT_ARCSEC=0.5`, `DEM_INTERPOLATION=bicubic`, `HGT_SMOOTH=0` |
| Höhenkurven | Swiss Map Vector 25 (DKM25) | `smv25_heights.py convert` | `HEIGHTS=smv25`, `CONTOURS=embedded` |
| Gletscherkurven | swissALTI3D | `build_dem.py`, `run_ch.py` | `GLACIER_FILL_PBF` (Testgebiet: wird bei Bedarf erzeugt) |
| Höhenkoten | Swiss Map Vector 25 | `smv25_heights.py convert`, `filter_spots.py` | `SPOTS=yes`, `SPOTS_NAMED_RADIUS=300` |
| Ausweichweg Kurven und Koten | swissALTI3D | `build_dem.py contours`, `spot_heights.py` | `HEIGHTS=alti3d` |

Die Variablen stehen in `src/build/config.sh`.

## swissALTI3D

### Download (`download_swissalti3d.py`)

- STAC-Abfrage `items?bbox=…` mit Paging. Je 1-km-Kachel nimmt das Skript den jüngsten Stand und
  das Asset `*_2_2056_5728.tif` (2 m, COG).
- Das Skript prüft die SHA-256-Prüfsumme aus `checksum:multihash`. Ein zweiter Lauf lädt korrekte
  Dateien nicht neu.
- Ganze Schweiz mit Liechtenstein: 43 621 Kacheln, ca. 49 GB, ca. 70 min mit 8 Verbindungen.
  Testgebiet: 1331 Kacheln, 1,5 GB.
- `--estimate N` schätzt das Volumen aus N Kacheln (nur Listing und HEAD).
- swissALTI3D gibt es nur in 0,5 m und 2 m. 0,5 m ist ca. 16-mal grösser und bringt für
  Kurven und HGT nichts, weil beide stärker mitteln.
- Die COGs enthalten Übersichten (4, 8, 16 m). Ein Lesen der 4-m-Übersicht per HTTP-Range spart
  Volumen, braucht aber über 100 000 Einzelanfragen. Das Projekt lädt deshalb die vollen Kacheln.

### DEM für mkgmap (HGT)

- mkgmap liest für `--dem` nur HGT: 1°-Kacheln im SRTM-Schema (Name nach der Südwestecke, z. B.
  `N47E009.hgt`), Int16 Big Endian.
- 1″ = 3601 × 3601 Punkte (25,9 MB je Kachel, am 47. Breitengrad ca. 31 m × 21 m).
  0,5″ = 7201 × 7201 Punkte (104 MB). mkgmap akzeptiert jede quadratische Grösse.
- Umrechnung: `gdalwarp -t_srs EPSG:4326 -r average` aus dem 2-m-Mosaik (VRT). `average` wirkt als
  Antialiasing.
- Ganze Schweiz: 15 Kacheln N45E006–N47E010 (bei 1″ 371 MB, bei 0,5″ ca. 1,5 GB). N45E005 hat keine Daten.
- Punkte ausserhalb der Daten bekommen den Void-Wert −32768. `--dem-poly` (Perimeter CH + FL)
  verhindert, dass mkgmap Voids einrechnet. Ausserhalb des Perimeters gibt es keine Schummerung.
- Höhenbezug: swissALTI3D ist in LN02. HGT nimmt formal EGM96 an. Die Abweichung liegt bei
  Dezimetern bis ca. 1 m und ist für Schummerung und Profil unerheblich.
- Plausibilität: Maximum 4621 m in N45E007 (Dufourspitze 4634 m), Minimum 193 m (Lago Maggiore).

### mkgmap-Optionen für das DEM

- `--dem-dists` braucht einen Wert je Level von `--levels`, für Geräte zwingend (mkgmap-Doku:
  BaseCamp kommt mit einem aus). Die Einheit ist der Garmin-Abstand (3314 ≈ 1″). Werte unter ca.
  50 % der HGT-Auflösung bringen nichts. `build_all.sh` bricht ab, wenn die Anzahl nicht zu den
  Levels in `src/style/swisstopo/options` passt (`DEM_LEVEL_CHECK=no` nur für Tests).
- Standard bei 0,5″ (8 Levels 24…16): `DEM_DISTS=1656,6624,13248,26512,53024,106048,212096,424192`.
  Bei 1″: `3312,6624,…,424192`.
- `--overview-dem-dist=55000` für die Übersichtskarte. `--show-profiles=1`.
- `--dem-interpolation=bicubic`. `auto` wählt bei 1″ meist ohnehin bikubisch.
- Helligkeit, Lichtrichtung und Stärke der Schummerung legt der Renderer fest (BaseCamp, Gerät).
  mkgmap hat dafür keine Option. Steuerbar ist nur die Feinheit des DEM.
- Laut mkgmap-dev zeigen Geräte die Schummerung etwa im Zoombereich 5–30 km.

Vergleich im Testgebiet (Gesamtbuild, nur DEM variiert):

| HGT | Interpolation | Stufe 0 | gmapsupp | DEM-Anteil |
|---|---|---|---|---|
| 1″ | auto | 3312 | 25,7 MB | 1,19 MB |
| 1″ | bicubic | 1648 | 27,0 MB | 2,50 MB |
| **0,5″** | **bicubic** | **1656** | **27,3 MB** | **2,80 MB** |

- 0,5″ bringt echte Details (Grate, Felsbänder, Runsen). 1648 aus 1″-Daten verdoppelt nur
  interpolierte Stützstellen.
- Feinere Daten machen die Schattierung schärfer, nicht dunkler (Standardabweichung der
  Schattierung 73,6 bzw. 73,9).
- Hochgerechnet auf die Schweiz: DEM ca. 95 MB statt 40 MB.

### Schummerung am Gerät (GPSMAP 66/67, Befund 2026-11-06)

Am GPSMAP 67 fehlte die Schummerung der Release-Datei „Helvetopo Vektor 2026-11 Testgebiet“.

Befund in der Datei (`work/release-build/vektor/dist/gmapsupp.img`):
- Alle Basiskacheln haben eine DEM-Subdatei. Dass die Übersicht 77010000 kein DEM hat, ist normal:
  mkgmap legt die Übersicht nicht in die gmapsupp, und auch Garmins Gerätekarten haben keine.
- Ein „DEM vorhanden“-Flag im TRE gibt es nicht. Das Gerät findet das DEM über den Kachelnamen.
- **Fehler:** Die Karte hat 8 Levels (24, 23, 22, 21, 20, 19, 18, 16), `DEM_DISTS` hatte nur 7
  Werte. Level 16 hatte kein DEM. Stand seit der Zwischenstufe 19 (Review 1), `config.sh` wurde
  damals nicht nachgeführt.
- **Abweichung von Garmin:** feinste DEM-Stufe 1664 (0,5″).

Kommerzielle Garmin-Karten zum Vergleich (DEM-Header gelesen, nicht im Repo):

- Garmin selbst hat weniger DEM-Stufen als Levels. Die Stufenzahl allein erklärt das Fehlen also
  nicht sicher. mkgmap verlangt sie für Geräte trotzdem, deshalb ist sie jetzt Pflicht.
- Garmin geht nie unter 3312 (1″). Ob das GPSMAP 0,5″ verarbeitet, ist offen.
- Meter statt Fuss (DEM-Flag 0) ist mkgmap-Standard und auf Geräten bewährt.
- Das Feld nach dem Zoom-Index im DEM-Abschnitt (Garmin CH: 0, 1, 2, 4, 6, 8, 10) ist bei TOPO
  Österreich überall 0, also nicht nötig.

**Geräteeinstellung (GPSMAP 66/67):**
- Menüpfad: mit PAGE zur Kartenseite, dann MENU → „Karte einrichten“ → „Erweiterte Einrichtung“ →
  „Reliefschattierung“. Die Option steht nicht im Hauptmenü „Einrichten“.
- Quelle ist das Benutzerhandbuch (frz. Ausgabe, „Paramètres de carte avancés“). Die deutschen
  Menünamen sind übersetzt, nicht am Gerät abgelesen.
- Im Nachtmodus zeigt das Gerät kein Relief. Mit „Auto“ erscheint es erst ab etwa 5 km Zoom
  (OpenMTBMap, DEM-Karten aus mkgmap).
- Sind mehrere Karten mit DEM aktiv, die anderen ausblenden.

Testdateien `work/dem/geraet2/<v>/dist/gmapsupp.img` (Testgebiet, je einzeln aufs Gerät, alle FID 7701):

| Variante | HGT | `DEM_DISTS` | prüft |
|---|---|---|---|
| a | 1″ | 3312, 6624, 13248, 26512, 53024, 106048, 212096, 424192 | Garmin-nahe Auflösung und ein Wert je Level |
| b | 0,5″ | 1656, 6624, …, 424192 (8 Werte, neuer Standard) | nur die Stufenzahl |
| c | 1″ | 3312, 6624, …, 212096 (7 Werte) | nur die Auflösung |

### Glättung im Hügelland (`HGT_SMOOTH`)

`build_dem.py hgt --hgt-smooth <σ in m>` glättet nur, wo das Relief im 1-km-Fenster unter 400 m
liegt (voll unter 150 m, dazwischen gemischt). Das Gebirge bleibt unverändert. Standard ist `0`.

| | 0,5″ | 0,5″, σ 15 m | 0,5″, σ 30 m |
|---|---|---|---|
| Kontrast Hügelland (Std.-Abw. Schattierung) | 36,0 | 34,0 | 31,3 |
| Kontrast Säntis | 80,3 | 80,3 | 80,3 |
| Höhenänderung p99 / max | – | 2,9 / 14,9 m | 6,3 / 23,6 m |

## Höhenkurven aus Swiss Map Vector 25

Swiss Map Vector 25 (`ch.swisstopo.swiss-map-vector25`) enthält die kartografischen Daten der
Landeskarte 1:25'000:
- `T62_DKM25_HOEHENKURVE`: Normal-, Zähl- und Zwischenkurven mit `HOEHE` und `OBERFLAECH`
  (Uebriges_Gebiet, Geroell, Fels). Die Kurven sind generalisiert und im steilen Fels und in
  dichten Siedlungen unterbrochen wie auf der LK.
- `T38_DKM25_HOEHENKOTE`: Höhenkoten, Geländekoten, Seebodenkoten.

Eigene Ableitungen aus swissALTI3D erreichen die LK nicht: 0,4 statt 4,6 Koten je km², und bei
1:50'000 nur 10 % der LK-Kurven.

### `smv25_heights.py`

- `download`: jüngste Ausgabe je Kachel über STAC. Landesweit 58 Kacheln, Ausgabe 2026, ca. 23 GB
  ZIP, 7,6 GB GPKG in `downloads/smv25-2026/`. Prüfsumme wird kontrolliert. Fortsetzbar.
- `convert`: schneidet auf die BBox zu und schreibt eine PBF.

Tags der Kurven:

| Tag | Wert |
|---|---|
| `contour` | `elevation` |
| `ele` | Höhe in m |
| `contour_ext` | `elevation_major` (Zählkurve), `elevation_medium` (Vielfache von 20 m), sonst `elevation_minor` |
| `contour_aux` | `yes` bei Zwischenkurven |
| `swisstopo:kurve` | `fels`, `geroell`, `gletscher` |
| `swisstopo:untergrund` | `fels` (Fels und Geröll), `gletscher` |
| `contour_surface` | `rock`, `glacier` |
| `source:contour` | `SMV25` oder `swissALTI3D` |

Im Testgebiet liegen 88 % der LK-Kurven auf Vielfachen von 20 m. `elevation_medium` liegt im Stil
auf Auflösung 22 (ca. 1:50'000). Dort erscheinen alle 20-m-Kurven wie auf der LK50.

### Fels, Geröll, Gletscher

`convert` teilt jede Kurve entlang der swissTLM3D-Bodenbedeckung:
1. Die Bodenbedeckung wird je Kachel auf 5 m gerastert. Fels: `Fels`, `Fels locker`,
   `Felsbloecke`, `Felsbloecke locker`. Geröll: `Lockergestein`. Gletscher: `Gletscher`,
   `Schneefeld Toteis`.
2. Die Kurve wird auf 5 m verdichtet. Jeder Stützpunkt wird klassiert. An jedem Wechsel beginnt
   ein neues Stück.
3. Stücke unter 25 m gehen an den Nachbarn. Danach wird mit 0,5 m vereinfacht.
4. Wo swissTLM3D nichts meldet, gilt `OBERFLAECH` aus DKM25.

Auf der LK sind Fels- und Geröllkurven schwarz.

### Gletscherkurven

Die LK zeichnet Gletscherkurven im Gletscher-Raster, nicht in `T62_DKM25_HOEHENKURVE`. Auf 876 km²
Gletscher liegen nur 132 km SMV25-Kurven. `convert --glacier-fill <PBF>` verwirft deshalb die
SMV25-Stücke auf Gletschern und übernimmt die Gletscherkurven aus swissALTI3D (23 152 km).

`build_all.sh` übergibt `GLACIER_FILL_PBF`. Fehlt die Datei im Testgebiet, rechnet der Build sie mit
`build_dem.py contours` und `pbf` (ca. 70 s). Landesweit liefert sie `run_ch.py`. Fehlt sie dort,
schreibt der Build eine Warnung. Ohne die Datei fehlen die Gletscherkurven, zum Beispiel am
Blauschnee (Gerätetest 2026-11-06).

Die PBF wird mit osmium gelesen. Der OSM-Treiber von GDAL verwirft den Tag `ele`.

### Höhenkoten

- Tags: `natural=spot_height`, `ele`, `swisstopo:kote=yes`, `swisstopo:kotenart`
  (`hoehenkote`, `gelaendekote`), `swisstopo:koten_rang=1|2|3`.
- Seebodenkoten bekommen nur `swisstopo:kote=seeboden`, ohne `natural=spot_height`.
- Rang für grobe Zoomstufen: Dominanz unter den Koten (höher als alle Koten im Umkreis 300, 700,
  1500, 3000 m), danach gierige Ausdünnung. Rang 1 hat mindestens 2,5 km Abstand, Rang 2 mindestens
  1 km. Der Stil zeigt Rang 1 ab Auflösung 21, Rang 2 ab 22, Rang 3 ab 23.
- `filter_spots.py` entfernt im Build jede Kote näher als `SPOTS_NAMED_RADIUS` (300 m) an einem
  benannten Gipfel, Hügel oder Pass der Basis-PBF. Sonst verdrängt die Kote in BaseCamp Name und Höhe
  des Gipfels (Beispiel: Geländekote 2453 an der Säntis-Bergstation, 196 m neben dem Gipfel 2502).
  Schweiz: 7810 von 158 608 Koten entfallen.
- Testgebiet: 6068 Koten (4,8 je km²), davon Rang 1 146, Rang 2 622, Rang 3 5300.

## Ausweichweg: Kurven und Koten aus swissALTI3D

`HEIGHTS=alti3d` verwendet eigene Ableitungen. Die Gletscherkurven entstehen immer so.

### Höhenkurven (`build_dem.py contours`)

1. 2-m-Mosaik auf ein 5-m-Raster in LV95 mitteln, mit 500 m Rand.
2. Gauss-Filter σ = 12 m (nodata-sicher). Mikrorelief, Böschungen und Gebäudereste verschwinden.
3. Gebirgszone mit 20-m-Äquidistanz: regionale Neigung (σ = 150 m) ≥ 22° und Höhe ≥ 1000 m.
   Parameter: `--alpine-slope`, `--alpine-min-ele`, `--alpine-sigma`. Ausserhalb gilt 10 m.
4. Zwischenkurven: In der Gebirgszone erscheinen die ungeraden 10-m-Stufen dort, wo die lokale
   Neigung (σ = 25 m) unter 12° liegt (`--aux-slope`).
5. Fels und Gletscher aus `tlm_bb_bodenbedeckung`. Flächen unter 5000 m² bleiben braun
   (`--min-surface-area`).
6. Konturieren mit `gdal.ContourGenerateEx`, je Oberfläche und Stufe auf einem maskierten DEM.
   Die Masken sind um 1 Pixel erweitert. Die Linien überlappen an den Grenzen um ca. 5 m.
7. Douglas-Peucker 1,5 m. Geschlossene Kurven unter 80 m und offene Stücke unter 15 m entfallen.
8. Zuschnitt auf die WGS84-BBox, OPL, `osmium sort` → PBF.

### Höhenkoten (`spot_heights.py`)

1. 2-m-Mosaik auf 10 m mitteln, glätten (σ = 15 m). Wasserflächen und Datenränder ausschliessen.
2. Kuppen: lokale Maxima im Umkreis von 150 m, mindestens 8 m über dem Mittel im Umkreis von 250 m.
   Rang nach Dominanz (Radius 150–2400 m) und Überhöhung.
3. Füllkoten: je Rasterzelle die flachste und tiefste Stelle mit Neigung unter 4°.
4. Auswahl: zuerst Kuppen nach Rang, dann Füllkoten. Mindestabstand 1000 m im Mittelland, 550 m im
   Gebirge. Benannte Gipfel und Pässe aus swissNAMES3D zählen als vorhandene Koten.
5. Höhe aus dem 2-m-Modell, bei Kuppen das Maximum im 20-m-Umkreis.

Tags: `natural=spot_height`, `ele`, `swisstopo:kote=yes`, `swisstopo:kotenart=kuppe|flach`.
Grenzen: keine Koten an Kreuzungen und Brücken, keine Koten in Mulden.

### Landesweite Berechnung (`run_ch.py`)

```bash
.venv/bin/python src/dem/run_ch.py --work work/dem/ch --jobs 4 --hgt-arcsec 0.5
```

- `mosaic`: VRT über alle 2-m-Kacheln.
- `hgt`: 1°-Kacheln. Kacheln ohne Daten werden nicht geschrieben. Fertige Kacheln werden übersprungen.
- `blocks`: 55 Blöcke zu 0,5° × 0,3°, die den Perimeter schneiden. Je Block laufen
  `build_dem.py contours`, `pbf` und `spot_heights.py`. 4 Blöcke laufen parallel. Ein Block ist fertig,
  wenn die Datei `DONE` existiert.
- `merge`: `osmium merge` → `contours.osm.pbf`, `spot_heights.osm.pbf`.
- Neustart mit demselben Befehl setzt die Berechnung fort.
- Blockränder: Die Glättung nutzt 500 m Rand. Die Linien enden an der Blockgrenze. Koten können
  dort etwas dichter liegen als der Mindestabstand.

| Schritt | Laufzeit | max. RAM |
|---|---|---|
| Mosaik (VRT) | 1 min | |
| HGT 1″ | 1,5 min | ca. 2 GB |
| 55 Blöcke, 4 parallel | 25 min | ca. 6 GB |
| Zusammenführen | < 1 min | |

Ergebnis: `contours.osm.pbf` 203 MB (44,1 Mio. Knoten, 2,86 Mio. Wege), 18 128 eigene Koten.

## ID-Bereiche

| Daten | Startwert | je Block k |
|---|---|---|
| Höhenkurven (Knoten und Wege) | 7 703 000 000 000 | + k·2·10⁹ |
| Höhenkoten | 7 704 500 000 000 | + k·10⁷ |

Die Bereiche überschneiden sich nicht mit der Basiskarte.

## Perimeter

`src/build/make_perimeter.py` schreibt `work/perimeter/ch_fl.poly` (osmosis-Format, WGS84),
`ch_fl.geojson` und `bbox.txt`. Grundlage ist die Vereinigung von CH und LI aus swissBOUNDARIES3D
`tlm_landesgebiet`, gepuffert um 300 m und vereinfacht um 25 m. Büsingen und Campione bleiben
Löcher. BBox: 5,952–10,496° O / 45,815–47,811° N.

Der Perimeter dient als `--dem-poly`. splitter lehnt ihn als `--polygon-file` ab („Invalid
polygon ring, possibly self-intersecting“), obwohl GEOS ihn als gültig meldet. Ein Rechteck nimmt
splitter an. Weil alle Daten in CH + FL liegen, braucht splitter kein Polygon.

## Einbau in die Karte

- Standard ist `CONTOURS=embedded`: `osmium merge` von Basis-PBF und Kurven-PBF vor dem splitter.
  Der Stil `src/style/swisstopo` zeichnet die Kurven unter Strassen und Text wie auf der LK.
- `CONTOURS=overlay` baut eine eigene transparente Karte (FID 7703) mit `src/dem/build_img.sh`,
  Stil `src/style/contours/` und TYP `src/style/typ/contours.txt`. Optionen:
  `--family-id=7703 --product-id=1 --code-page=1252 --lower-case --transparent --draw-priority=28`.
  Das Overlay hat kein DEM. Das DEM gehört in genau eine Karte.
- Eingebaut ist die gmapsupp im Testgebiet 20,7 MB gross, mit Overlay 19,6 MB.

Garmin-Typen im Overlay:

| Typ | Bedeutung | Auflösung | Farbe, Breite |
|---|---|---|---|
| 0x20 | Normalkurve braun | 24 | #D7963C, 1 px |
| 0x21 | 50-m-Kurve braun | 22 | #D7963C, 1 px |
| 0x22 | Zählkurve braun | 20 | #D7963C, 2 px |
| 0x11005 | Zwischenkurve braun | 24 | #D7963C gestrichelt |
| 0x11001 | Normalkurve Fels | 24 | #3E3E3E, 1 px |
| 0x11002 | Zählkurve Fels | 20 | #3E3E3E, 2 px |
| 0x11006 | Zwischenkurve Fels | 24 | #3E3E3E gestrichelt |
| 0x11003 | Normalkurve Gletscher | 24 | #0088D0, 1 px |
| 0x11004 | Zählkurve Gletscher | 20 | #0088D0, 2 px |

- Garmin erkennt 0x20–0x22 als Höhenlinien. Ihr Name steht deshalb in Fuss (`conv:m=>ft`). Das
  Gerät rechnet in die eingestellte Einheit um. Die Zusatztypen tragen Meter.
- Ohne `--license-file` schreibt mkgmap „Map data (c) OpenStreetMap…/ODbL“ in die TDB. Ohne
  `--overview-mapname` heisst die Übersicht `osmmap`. `src/build/check_license.sh` prüft das nach
  jedem Build.

## Vorbild Landeskarte

- Äquidistanz 10 m im Mittelland und Jura, 20 m in den Alpen. In flachen Teilen der Alpen ergänzen
  gestrichelte 10-m-Zwischenkurven. Jede 100-m-Kurve ist eine Zählkurve.
- Farben aus der SMV25-Symbolik: braun `#D7963C` (0,10 mm, Zählkurve 0,18 mm), schwarz `#3E3E3E`
  für Fels und Geröll, blau `#0088D0` für Gletscher.
- Garmin setzt die Kurvenbeschriftung selbst. Die LK-Regel „nur einzelne Zählkurven beschriften“
  lässt sich nicht nachbilden.

## Quellen

- mkgmap r4924 `--help=options`, Abschnitt „Hill Shading (DEM) options“
- mkgmap-dev: [DEM-Optionen](https://lists.mkgmap.org.uk/archives/list/mkgmap-dev@lists.mkgmap.org.uk/thread/UUGUBVJDKPA62TIXZ5HUULDTXEV3ZJL3),
  [--x-overview-dem-dist](https://mkgmap.org.uk/pipermail/mkgmap-dev/2017q4/027461.html)
- Äquidistanz LK25: [youngstarswiki.org](https://youngstarswiki.org/en/print/pdf/node/126),
  [talk-de 2009](https://lists.openstreetmap.org/pipermail/talk-de/2009-March/039237.html)
