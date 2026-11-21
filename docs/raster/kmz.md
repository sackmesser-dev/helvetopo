# Pixelkarte als KMZ (Garmin Custom Maps)

Stand: 2026-11-04. Code: `src/raster_kmz/`. Status: für den Eigenbedarf. Das Portal bietet keine
KMZ an.

Aus Swiss Map Raster entstehen Garmin Custom Maps (KMZ) für GPSMAP 66/67 und Montana 7xx.
BaseCamp zeigt Custom Maps nicht an. Die Georeferenz lässt sich in Google Earth Pro, QGIS oder
GPXSee prüfen.

## Daten

- STAC-Kollektionen `ch.swisstopo.pixelkarte-farbe-pk{25,50,100,200}.noscale`, Variante **krel**
  (Farbe mit Relief), 508 dpi, GeoTIFF (COG, LZW, RGB, EPSG:2056).
- Auflösung: SMR25 1,25 m, SMR50 2,5 m, SMR100 5 m, SMR200 10 m je Pixel.
- Je Blatt nur die neueste Ausgabe.
- Ablage `downloads/smr/pk*/` mit `manifest.json` (Jahr, BBox, URL).
- Die Blätter enthalten angrenzendes Ausland. Das ist Teil des swisstopo-Produkts unter OGD.
- Vier SMR25-Blätter am Rand (1035 Bodensee, 1056 Vorarlberg, 1282 Genfersee, 2220 Vinschgau) haben
  als neueste Ausgabe 1984–2003. Pakete mit Teilen davon nennen sie in KML-Beschreibung, `README.txt`
  und `INDEX.md` als „ältere Ausgabe“ (`build.json`: `old_sheets`).

| Stufe | Blätter CH | Volumen |
|---|---|---|
| SMR25 | 260 | 83,3 GiB |
| SMR50 | 80 | 29,0 GiB |
| SMR100 | 25 | 10,0 GiB |
| SMR200 | 13 | 3,0 GiB |

## Pipeline

STAC-Download → VRT-Mosaik → `gdalwarp` nach EPSG:4326 (Lanczos) → Kacheln bis 1024 × 1024 px als
Baseline-JPEG (q85, 4:2:0) → `doc.kml` → KMZ.

| Datei | Zweck |
|---|---|
| `stac.py` | STAC-Abfrage, neueste Ausgabe und krel-Asset je Blatt |
| `fetch_smr.py` | Download nach `$HELVETOPO_DATA/smr/` (Testgebiet oder `--region ch`, SMR10 bis SMR200, fortsetzbar, `--dry-run`, `--max-gb`). SMR10 schreibt sein eigenes Manifest `manifest_pk10.json`. |
| `variants.py` | vordefinierte Varianten |
| `build.py` | Mosaik, Warp, Kacheln, KML, KMZ, `build.json`, `README.txt` |
| `check.py` | automatische Prüfung und Vorschau |
| `plan_ch.py` | Hochrechnung Schweiz |
| `quality_test.py` | Qualitätsvergleich Resampling und JPEG |
| `package.py` | regionale Pakete mit Landesmaske innerhalb der Kachellimits |
| `index.py` | `INDEX.md` über gebaute Pakete |
| `README-vorlage.txt` | README je Paket |

```bash
cd src/raster_kmz
python3 fetch_smr.py --region ch --scales 25 50 100 200
python3 package.py --scale 25 --region ch --out-root ../../work/raster_kmz/ch
python3 index.py ../../work/raster_kmz/ch
python3 check.py ../../work/raster_kmz/ch/*/*.kmz
```

Eigener Ausschnitt: `python3 build.py --variant name --scale 25 --res 1.25 --bbox W S E N --title "…"`.

### Technische Regeln

- **Zielgitter:** EPSG:4326. Die Pixelgrösse in Grad ist so gewählt, dass ein Pixel in der
  Gebietsmitte quadratisch ist (Δlon = Δlat / cos φ). Die Auflösung des Originals bleibt erhalten,
  die Kacheln stossen exakt aneinander. LatLonBox ohne Rotation.
- **Resampling Lanczos.** Wegen der Meridiankonvergenz (ca. 1,4° bei 9,3° O) muss neu abgetastet
  werden. `near` treppt Schrift. `bilinear` macht Schrift und Höhenlinien weich. `cubic` ist
  gleichwertig.
- **JPEG q85, 4:2:0, Baseline, optimierte Huffman-Tabellen.** Bis q75 verschmieren dünne Linien.
  Ab q85 ist bei 1:1 kein Unterschied zum PNG sichtbar. q90 kostet 21 % mehr ohne sichtbaren Gewinn.
  4:4:4 kostet 25 % mehr und hilft nur bei Vergrösserung. Mittel ca. 330 KB je Kachel.
- Leere Kacheln fallen weg. Lücken sind weiss.
- **drawOrder:** SMR25 53, SMR50 52, SMR100 und SMR200 51. Werte über 50 zeichnet Garmin über die
  Vektorkarten. Die feinere Stufe liegt oben.
- **KMZ:** `doc.kml` als erster Eintrag (deflate), Kacheln unter `files/rRRRcCCC.jpg` (stored). Feste
  ZIP-Zeitstempel für reproduzierbare Builds.
- **Quellenangabe:** `©swisstopo` in `Document/name` (sichtbar in der Kartenliste), in der
  `description` mit Ausgabejahr, OGD-Link und „Keine offizielle Karte von swisstopo“, ausserdem in
  `README.txt`. Keine Logos.

### Pakete (`package.py`)

- Globales Kachelraster je Massstab (Ursprung 5,80° O / 47,95° N). Kacheln benachbarter Pakete
  stossen exakt aneinander und kommen nicht doppelt vor.
- Landesmaske: nur Kacheln, die CH oder FL (swissBOUNDARIES3D) mit 500 m Puffer berühren.
- Schema `grid` (Standard): Blöcke von 22 × 22 Kacheln (bis 484). Pakete unter 150 Kacheln werden mit
  dem kleinsten Nachbarn zusammengelegt. Paket-ID = Blockname, z. B. `smr25-C10`.
- Schema `canton`: ein Paket je Kanton, grosse Kantone geteilt. Kacheln an Kantonsgrenzen liegen in
  beiden Paketen.
- Je Paket: `<paket>.kmz`, `README.txt`, `build.json`. Je Lauf: `plan.json`, `uebersicht.png`,
  `LIESMICH.txt`.
- Fehlende Blätter liest `package.py` per `/vsicurl/` aus dem COG (nur benötigte Bereiche).

Gebaut für die ganze Schweiz (`work/raster_kmz/ch/`, Schema grid):

| Stufe | Pakete | Kacheln | Grösse | Rechenzeit |
|---|---|---|---|---|
| SMR25 | 65 | 26 612 | 8,3 GB | 66 min |
| SMR50 | 17 | 6842 | 2,6 GB | 21 min |
| SMR100 | 5 | 1794 | 0,7 GB | 5 min |
| SMR200 (`--limit 500 --block 40`) | 1 | 484 | 0,2 GB | 2 min |

Alle 88 KMZ bestehen `check.py`.

## Limits der Zielgeräte

| Gerät | Kacheln gesamt (alle KMZ) | Beleg |
|---|---|---|
| GPSMAP 66 | 500 | Garmin-Forum, Nutzerbericht |
| GPSMAP 67 | 500 | Händlerangaben aus dem Datenblatt |
| Montana 700/700i/750i | 500 | Datenblatt Montana 700 |
| Montana 710 | 500 (angenommen) | nicht separat belegt |
| ältere Geräte (eTrex, GPSMAP 62/78, Edge) | 100 | Garmin-Forum |

- Kachel höchstens 1 Megapixel. Grössere Bilder werden verkleinert dargestellt.
- JPEG unter 3 MB je Kachel, nur Baseline. Progressive JPEG zeigt das Gerät nicht.
- Das Limit gilt für die Summe aller KMZ in `Garmin/CustomMaps/`. Ob ausgeschaltete Karten
  mitzählen, ist nicht belegt.
- Für die KMZ-Grösse gibt es keine dokumentierte Grenze ausser FAT32 (4 GB).
- Die Kachelzahl ist die knappe Ressource, nicht die Dateigrösse.

Ein 22 × 22-Detailpaket (484 Kacheln) lässt neben sich nur 16 Kacheln frei. Wer Detail und
Übersicht zugleich will, baut Detailpakete mit `--limit 400` und eine regionale SMR200-Übersicht mit
bis 100 Kacheln.

## Prüfung (`check.py`)

Das Skript prüft:

- je KMZ: ZIP lesbar, `doc.kml` als erster Eintrag, KML 2.2 wohlgeformt, `©swisstopo` in `name` und
  `description`
- je GroundOverlay: `href`, LatLonBox (N > S, O > W), `rotation` 0, `drawOrder`
- je JPEG: Baseline (SOF0), bis 1024 px, unter 3 MB, 3 Komponenten
- Kachelsatz: Nachbarkacheln stossen exakt aneinander, einheitliche Pixelgrösse, Kachelzahl gegen
  100 und 500

Die Vorschau setzt die Kacheln anhand ihrer LatLonBox zusammen. Ein Georeferenzfehler erscheint dort
als Versatz.

## Offene Punkte

- Gerätetest: Ladezeit, Herauszoomen, Zählung ausgeschalteter KMZ, drawOrder gegenüber Vektorkarten.
- Validierung gegen das OGC-KML-XSD.

## Quellen

- [Garmin-Forum GPSMAP 66 „100 Kachel Limit“](https://forums.garmin.com/de/outdoor/wandern-und-handgerate/f/gpsmap-66/34055/100-kachel-limit-bei-custom-maps/214039)
- [Montana 700 Datenblatt (GPS Central)](https://www.gpscentral.ca/wp-content/uploads/Garmin_Montana700_Specs.pdf)
- [GarminCustomMaps (NINA)](https://github.com/NINAnor/GarminCustomMaps)
- [OkMap: Garmin Custom Maps](https://www.okmap.org/en/en_articles/en_garminCustomMaps.aspx)
