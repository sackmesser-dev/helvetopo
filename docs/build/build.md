# Gesamtbuild der Vektorkarte

Stand: 2026-11-06. Code: `src/build/build_all.sh`, Einstellungen `src/build/config.sh`, Ablage `src/build/store.sh`.

`build_all.sh` baut aus Basis-PBF, Höhen und Routen die Kartenfamilie 7701 für GPSMAP/Montana
(`gmapsupp.img`) und BaseCamp (gmapi-Ordner).

## Familie 7701

BaseCamp zeigt nur ein Kartenprodukt (FID) gleichzeitig. Getrennte Overlays erscheinen dort nicht
über der Basiskarte. Der Build legt deshalb alles in die Familie 7701:

| Teil | Map-IDs | Eigenschaften |
|---|---|---|
| Übersicht | 77010000 | aus den Basiskacheln, mit DEM (`--overview-dem-dist`) |
| Basiskacheln | 77010001 … | Stil `swisstopo`, Routing, Index, DEM, Höhenkoten, Höhenkurven (`CONTOURS=embedded`) |
| Routen-Kacheln | 77011001 … | Stil `routes` mit verschobenen Typen, transparent, draw-priority 30 |
| Höhenlinien-Kacheln | 77012001 … | nur `CONTOURS=overlay`: Stil `contours`, transparent, draw-priority 28 |

Ein gemeinsamer mkgmap-Lauf über alle Kacheln mit `--tdbfile --gmapi --index` und einer
zusammengeführten TYP (`meta/ch_7701.txt`) ergibt eine TDB, eine Übersicht, einen Suchindex und eine
TYP.

`DEVICE_FAMILIES` wählt die Gerätedatei:
- `single` (Standard): die Familie 7701 als `gmapsupp.img`.
- `split`: drei Familien 7701, 7702, 7703 in einer `gmapsupp.img`, am Gerät einzeln schaltbar.
  BaseCamp bekommt immer die gemeinsame Familie.

### TYP zusammenführen

`src/build/merge_typ.py` fasst `swisstopo.txt`, `routes.txt` und `contours.txt` zusammen und bricht
bei doppelten Typcodes ab. Erlaubt sind nur die Codes in `--shared`: 0x20–0x22 bedeuten in Basis und
Höhenlinien dasselbe, es gilt die Basis-Definition.

Die Routencodes `0x10exx` kollidieren mit Bahnlinien der Basis. `ROUTES_TYPE_REMAP=0x10e:0x113`
verschiebt sie in Stil- und TYP-Kopie (`meta/style_routes`, `meta/routes_7701.txt`) nach `0x113xx`.

## Aufruf

```bash
src/build/build_all.sh                                       # Testgebiet
PROFILE=ch BASE_PBF=work/vector/ch/ch.osm.pbf src/build/build_all.sh   # ganze Schweiz
```

| Variable | Standard | Bedeutung |
|---|---|---|
| `BASE_PBF` | `work/vector/testgebiet.osm.pbf` | Basis-PBF aus `src/vector/` |
| `ROUTES_PBF` | `work/routes/routes.osm.pbf` | fehlt sie, läuft `src/routes/build.sh` |
| `ROUTES` | `yes` | Routen einbauen |
| `DEM` | `yes` | Schummerung in der Basiskarte |
| `DEM_WORK`, `HGT_DIR` | `work/dem/…` | fehlen sie, entstehen sie aus swissALTI3D |
| `HEIGHTS` | `smv25` | Quelle für Höhenkurven und -koten: `smv25` oder `alti3d` |
| `SMV25_SRC`, `SMV25_WORK` | `$HELVETOPO_DATA/smv25-2026`, `<DEM_WORK>/smv25` | SMV25-GPKG und Ausgabe von `smv25_heights.py convert` |
| `GLACIER_FILL_PBF` | `<DEM_WORK>/contours.osm.pbf` | Gletscherkurven aus swissALTI3D |
| `CONTOURS` | `embedded` | `embedded` (in den Basiskacheln), `overlay` (eigene Kacheln) oder `none` |
| `SPOTS` | `yes` | Höhenkoten |
| `SPOTS_NAMED_RADIUS` | `300` | Koten näher an benannten Gipfeln entfallen |
| `HGT_ARCSEC` | `0.5` | HGT-Rasterweite |
| `HGT_SMOOTH` | `0` | Glättung im Hügelland (σ in m) |
| `DEM_DISTS` | `1656,6624,13248,26512,53024,106048,212096,424192` | genau ein Wert je Level (8), sonst Abbruch. Bei 1″ `3312,…` |
| `DEM_INTERPOLATION` | `bicubic` | `bicubic`, `auto`, `bilinear` |
| `OVERVIEW_DEM_DIST` | `55000` | DEM in der Übersichtskarte |
| `STYLE_OPTIONS` | `routing_pref=basis;velo_toll=stark` | siehe [routing.md](../vektor/routing.md) |
| `DEVICE_FAMILIES` | `single` | `single` oder `split` |
| `ROUTES_TYPE_REMAP` | `0x10e:0x113` | Routentypen verschieben |
| `BOUNDS` | leer | `--bounds`, optional |
| `JAVA_XMX`, `SPLITTER_MAX_NODES`, `MAX_JOBS` | `8g`, `1200000`, leer | Ressourcen |
| `VERSION` | | Version in Kartennamen, README und LICENSE |
| `OUT` | `work/build` | Ausgabeordner |
| `STORE_SUBDIR` | `vektor/<PROFILE>/<VERSION>` | Unterordner in der Ablage (nur mit `HELVETOPO_STORE`) |
| `STORE_CLEAN` | `no` | `yes`: `OUT` nach der geprüften Ablage entfernen |

Hilfsdaten wie `tools/` und `.venv/` liegen im Haupt-Checkout. `src/paths.py` und `src/paths.sh`
finden ihn über `HELVETOPO_ROOT` oder über git. Rohdaten und Ablage beschreibt der Abschnitt
[Rohdaten und Ablage](#rohdaten-und-ablage).

### Profil ganze Schweiz (`PROFILE=ch`)

- Perimeter `work/perimeter/ch_fl.poly` (bei Bedarf erzeugt) als `--dem-poly`. splitter bekommt kein
  Polygon (siehe [hoehen.md](../vektor/hoehen.md#perimeter)).
- `BBOX` aus `bbox.txt`, `AREA_NAME` „Schweiz und Liechtenstein“.
- `DEM_WORK=work/dem/ch`, `ROUTES_PBF=work/routes-ch/routes.osm.pbf`, `OUT=work/build-ch`, `JAVA_XMX=16g`.
- `BASE_PBF` ist Pflicht.
- Fehlende Eingaben erzeugt `build_all.sh` selbst (HGT, SMV25-Import, Routen, Perimeter).

## Ablauf

1. Fehlende Eingaben erzeugen (DEM, Höhenkurven, Höhenkoten, Routen-PBF).
2. TYP: Routentypen verschieben, alle Quellen zu `meta/ch_7701.txt` zusammenführen, Kollisionen prüfen.
3. Basiskacheln: `osmium merge` der Basis-PBF mit Höhenkoten und Höhenkurven. `filter_spots.py`
   entfernt Koten neben benannten Gipfeln. splitter (`--max-nodes`, `--keep-complete`). mkgmap mit
   Stil `swisstopo`, Routing, Index, Hausnummern, `--country-name=Schweiz --country-abbr=CHE`, DEM
   (`--dem`, `--dem-dists`, `--dem-poly`, `--dem-interpolation`, `--show-profiles=1`),
   `--simplify-polygons=24:0,23:0,22:0,21:2.6`, `--polygon-size-limits`, `--style-option`.
4. Routen-Kacheln (und bei `overlay` Höhenlinien-Kacheln), transparent. splitter teilt die Routen-PBF
   (`ROUTES_MAX_NODES`, Standard 800 000). Als eine Kachel überschreitet die ganze Schweiz die RGN-Grenze von 16 MiB.
5. Familie 7701: ein mkgmap-Lauf über alle Kacheln mit `--tdbfile --gmapi --index`, Übersicht mit DEM,
   bei `single` auch `--gmapsupp`.
6. Nur bei `split`: Routen und Höhenlinien zusätzlich als FID 7702 und 7703 (Original-TYP) bauen und
   alle drei Familien in eine `gmapsupp.img` legen.
7. `dist/`: `gmapsupp.img`, `BaseCamp/Helvetopo.gmap`, `README.txt` und `LICENSE.txt` aus
   `src/build/templates/` (Platzhalter `@VERSION@`, `@AREA@`, `@MKGMAP@`, `@CONTOURS@`, `@DEVICE_FAMILIES@`).
8. Lizenzprüfung `src/build/check_license.sh`.
9. Nur mit `HELVETOPO_STORE`: `dist/` mit `src/build/store.sh` in die Ablage kopieren und prüfen.

`timings.tsv` im Ausgabeordner enthält Laufzeit und Spitzen-RAM je Schritt. `src/build/img_ls.py`
listet die Subdateien einer IMG.

### Lizenzprüfung

`check_license.sh` bricht den Build ab, wenn:
- in einer IMG, TDB oder TYP „OpenStreetMap“, „ODbL“, „DbCL“, „opendatacommons“ oder „osmmap“ steht,
- eine Datei `osmmap.*` existiert,
- in TDB oder gmapsupp `©swisstopo` fehlt,
- mit Routen die Angabe „Bundesamt für Strassen, Kanton, Stiftung SchweizMobil“ fehlt.

Ohne `--license-file`, `--copyright-file` und `--overview-mapname` schreibt mkgmap seine OSM-Texte in
die Karte.

## Rohdaten und Ablage

Die Rohdaten und die fertigen Karten können auf einem Netzlaufwerk (NAS) liegen. Der Mac braucht
dann nur Platz für die Zwischendateien eines Builds.

| Variable | Standard | Bedeutung |
|---|---|---|
| `HELVETOPO_DATA` | `<Haupt-Checkout>/downloads` | Ordner mit den Rohdaten (`swisstlm3d/`, `smr/`, `swissimage/` usw.) |
| `HELVETOPO_STORE` | leer | Ablage für fertige Ausgaben: lokaler Ordner oder rsync-Ziel `benutzer@host:pfad`. Leer = keine Ablage. |
| `HELVETOPO_STORE_RSH` | leer | Shell für rsync bei einem entfernten Ziel, z. B. `ssh -i <schlüssel>` |

`src/paths.py` (`DOWNLOADS`) und `src/paths.sh` lesen `HELVETOPO_DATA`. Alle Skripte finden die
Rohdaten über diese Variable. Die Download-Skripte (`fetch_smr.py`, `swissimage.py`,
`download_swissalti3d.py`) schreiben ebenfalls dorthin. Mit einem eingebundenen Netzlaufwerk landen
neue Downloads also direkt auf dem NAS. Beide Download-Skripte überspringen vorhandene Dateien und
setzen einen abgebrochenen Lauf fort.

Einrichtung:

1. Auf dem NAS einen Ordner für die Rohdaten und einen für die Ablage anlegen.
2. Die Rohdaten einmal kopieren: `rsync -rtp --partial --chmod=D2775,F664 <Haupt-Checkout>/downloads/ <ziel>/`.
   `--chmod` wirkt nur mit `-p`. Ohne Gruppen-Schreibrecht kann der SMB-Benutzer keine neuen Downloads ablegen.
3. Die Kopie prüfen: Grösse je Ordner und SHA-256 einer Stichprobe vergleichen.
4. Die Freigabe auf dem Mac einbinden (SMB) und `HELVETOPO_DATA` auf den Mount setzen.
5. `HELVETOPO_STORE` auf den Ablage-Ordner setzen.

Hinweise:

- Ein Upload-Zugang mit `rrsync` erlaubt nur eine Verbindung gleichzeitig. `store.sh` scheitert, solange
  eine andere Kopie auf denselben Zugang läuft.
- Die Builds lesen die Rohdaten über das Netz. Für rechenintensive Schritte mit vielen kleinen
  Lesezugriffen (z. B. GDAL auf vielen Kacheln) ist eine lokale Kopie des betroffenen Ordners schneller
  **(unsicher, nicht gemessen)**.

`src/build/store.sh [--clean <ordner>]... <unterordner> <datei|ordner>...`:

1. rsync kopiert die Quellen nach `$HELVETOPO_STORE/<unterordner>/` (fortsetzbar).
2. Ein zweiter rsync-Lauf vergleicht Grösse und Prüfsumme ohne Übertragung. Weicht eine Datei ab,
   endet das Skript mit Exit-Code 1 und löscht nichts.
3. Nach erfolgreicher Prüfung entfernt `--clean` die genannten Ordner. Erlaubt sind nur Ordner unter
   `work/`.

`build_all.sh` ruft `store.sh` am Ende für `dist/` auf. Die anderen Builds (Pixel, Luftbild) rufen es
noch nicht selbst auf. Ihre fertigen IMGs kopiert ein Aufruf von Hand, z. B.
`src/build/store.sh pixel/2026-11 work/raster_img/<ordner>/*.img`.

## Quellenangaben

Garmin zeigt am Gerät nur die zweite Copyright-Zeile. Die Pflichtangabe steht deshalb in beiden Zeilen.

| Karte | Copyright (beide Zeilen) | Lizenztext |
|---|---|---|
| Familie 7701 mit Routen | `©swisstopo; Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` | `templates/license_all.txt` |
| Familie 7701 ohne Routen, Höhenlinien-Kacheln | `©swisstopo` | `license_7701.txt`, `license_7703.txt` |
| Routen-Kacheln, Familie 7702 | `©swisstopo; Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` | `license_7702.txt` (mit Kanuland: Stiftung SchweizMobil) |

## Ergebnis ganze Schweiz

Mac mit 14 Kernen und 48 GB RAM, Java 26, mkgmap r4924, splitter r654. Eingaben unter `DEM_WORK`
vorhanden.

| Schritt | Laufzeit | max. RSS |
|---|---|---|
| osmium merge Basis, Kurven, Koten | 21 s | 0,6 GB |
| splitter Basis | 2 min 46 s | 4,2 GB |
| mkgmap Basis (Routing, Index, Hausnummern, DEM 0,5″, 14 Jobs) | 2 min 17 s | 15,3 GB |
| mkgmap Routen-Kacheln | 41 s | 3,7 GB |
| Familie 7701 | 10 s | 1,0 GB |
| **Gesamt** | **6 min 15 s** | **15,3 GB** |

Mit `JAVA_XMX=16g` nutzt mkgmap fast den ganzen Heap. Bei grösseren Daten `JAVA_XMX=20g` oder
`MAX_JOBS=10` setzen.

| Datei | Grösse | Inhalt |
|---|---|---|
| `work/build-ch/dist/gmapsupp.img` | 984 MB | 243 Basiskacheln, 1 Routen-Kachel, Übersicht, Blockgrösse 16 KiB |
| `work/build-ch/dist/BaseCamp/Helvetopo.gmap` | 939 MB | dieselbe Familie für BaseCamp |

| Subdatei | Grösse |
|---|---|
| RGN (Linien, Flächen, Punkte, Höhenkurven, Koten) | 767 MB |
| DEM (0,5″, 7 Stufen) | 95 MB |
| NET und NOD (Routing) | 78 MB |
| MDR (Suchindex) | 11 MB |
| LBL (Beschriftungen) | 10 MB |

Eingaben:

| Eingabe | Umfang | Werkzeug | Dauer |
|---|---|---|---|
| Basis-PBF | 1,33 GB, 169 Mio. Knoten, 8,27 Mio. Wege | `src/vector/build_ch.py` | ca. 20 min |
| Höhenkurven SMV25 mit Gletschern | 376 MB, 5,89 Mio. Stücke (81 868 Gletscherkurven aus swissALTI3D) | `smv25_heights.py convert --glacier-fill` | 33 min |
| Höhenkoten SMV25 | 158 255 Koten, 353 Seebodenkoten | dito | |
| HGT 0,5″ | 15 Kacheln, 1,5 GB | `run_ch.py --stages hgt --hgt-arcsec 0.5` | 2,7 min |
| Höhenlinien swissALTI3D (Gletscherquelle) | 203 MB | `run_ch.py` | 38 min |
| Routen-PBF | 53 MB | `src/routes/convert_routes.py` | ca. 6 min |
| Perimeter | CH + FL | `src/build/make_perimeter.py` | < 1 min |

In BaseCamp läuft die Karte stabil ohne Lücken. Programmstart 13 s, Zeichnen 2–4 s.

Sparmöglichkeiten:
- DEM 1″ (`HGT_ARCSEC=1`): ca. −55 MB.
- Höhenkurven in groben Zoomstufen weiter ausdünnen.
- Höhenlinien als eigenes Overlay (`CONTOURS=overlay`, `DEVICE_FAMILIES=split`).

### DEM in groben Stufen

mkgmap rechnet das DEM je Kartenkachel auf ein eigenes Punktraster (`DEMFile`, `DEMSection`,
`HGTConverter`). Punkte ausserhalb von `--dem-poly` sind unsichtbar. Gültige Punkte an der Grenze
erscheinen als ganze Zellen.

Grobe Abstände sind 212 096 bzw. 848 384 Einheiten (ca. 2 bzw. 8 km).
Mit ihnen zeigt die Grobstufe ein Kachelraster und Blöcke über die Landesgrenze hinaus. Die Standardwerte
enden bei 212 096. Die Zellen sind dadurch 4–8-mal kleiner.

## Testgebiet

| Variante | gmapsupp | Laufzeit |
|---|---|---|
| `single`, Höhenlinien `embedded` | ca. 30 MB | ca. 35 s |
| `single`, Höhenlinien `overlay` | ca. 20 MB | ca. 33 s |
| `split`, `overlay` | ca. 20 MB (3 Familien, 3 TYP, 3 MDR) | ca. 40 s |
