# Luftbild: SWISSIMAGE als Raster-IMG

Stand: 2026-11-07. Code: `src/raster_img/swissimage.py` (Download), `src/raster_img/luftbild.py` (Build).

Varianten (`luftbild.py --variant`):

| Variante | FID | feinste Stufe | Gebiet | Status |
|---|---|---|---|---|
| `detail` | 7707 | 0,64 m, nur bits 24 bis 22 | Schweiz in 18 Teilen, 1,35 bis 3,95 GB (zusammen 50,5 GB) | gebaut 2026-11-07, Gerätetest offen |
| `kompakt` | 7708 | 2,6 m | ganze Schweiz in einer Datei, 3,15 GB (2,94 GiB) | gebaut, Standard-Luftbild. Schweiz-Datei am Gerät nicht geprüft |
| `detail-voll` | 7707 | 0,64 m, bits 24 bis 18 | je Region | früherer Aufbau von detail mit grober Serie. St. Gallen lief in BaseCamp und am GPSMAP 67 |

- detail ergänzt kompakt. Am Gerät liegt detail über kompakt. Für die kleinen Massstäbe sorgt kompakt.
- BaseCamp (detail-voll): durchgehend von 15 km bis 70 m, ohne Säume, ab 300 m scharf.

Die Luftbild-Karte nutzt denselben Encoder und denselben Aufbau wie die Pixelkarte
([raster-img.md](raster-img.md)). Nur die Quelle und die Zoomstufen sind anders.

## Quelle

| Produkt | STAC-Collection | Auflösung | Format | Lizenz |
|---|---|---|---|---|
| SWISSIMAGE 10 cm | `ch.swisstopo.swissimage-dop10` | 10 cm (Alpen 25 cm), Asset 2 m | COG, LV95 | OGD |
| SWISSIMAGE Background | `ch.swisstopo.swissimage` | 0,5 m (WMTS-Stufe 18) | ein TAR mit JPEG-Kacheln, EPSG:3857 | OGD |

Die Luftbild-Karte verwendet nur SWISSIMAGE 10 cm.
- Kachelung: 1 × 1 km in LV95. Das Item heisst `swissimage-dop10_<Jahr>_<E>-<N>`.
- Jede Kachel gibt es je Befliegungsjahr als eigenes Item. Die Collection reicht von 2017 bis 2025.
  Der Nachführungszyklus ist 3 Jahre. Im Testgebiet gibt es je Kachel die Jahre 2019, 2022 und 2025.
- Jedes Item hat zwei Assets:
  - `…_0.1_2056.tif`: 10 000 × 10 000 px zu 10 cm, JPEG q95 im COG.
    Interne Übersichten: 0,2 / 0,4 / 0,8 / 1,6 / 3,2 m. Im Mittelland ca. 65 MB, im Hochgebirge ca. 35 MB (25 cm, auf 10 cm geliefert).
  - `…_2_2056.tif`: 500 × 500 px zu 2 m, ca. 0,15 MB. Das ist eine fertige Übersichtsstufe.
- Lizenz: Die Collection hat im STAC keinen Lizenz-Link (`license: proprietary`). SWISSIMAGE 10 cm gehört
  zu den swisstopo-OGD-Daten ([lizenzen.md](../daten/lizenzen.md)). Quellenangabe `©swisstopo`.
- SWISSIMAGE Background ist ein einziges TAR der ganzen Schweiz in Web Mercator. Es passt nicht zum
  Kachel-Download und wird nicht verwendet.

### Download (`swissimage.py`)

- Je Kachel nur das neueste Befliegungsjahr.
- Feine Quelle: die 0,4-m-Übersicht aus dem 10-cm-COG. GDAL liest sie per HTTP-Range-Abfrage
  (`/vsicurl/`, `gdal_translate -ovr 1`). Übertragen wird ca. 1/16 der vollen Datei.
- Grobe Quelle: das 2-m-Asset, unverändert.
- Ablage: `downloads/swissimage/fein_0.4m/<E>-<N>.tif`, `downloads/swissimage/2m/<E>-<N>.tif`,
  `downloads/swissimage/manifest.json` (Jahr, BBox, Item, Asset-URLs, Stand je Kachel).
- Der Download ist fortsetzbar. Vorhandene Dateien werden übersprungen.

| Gebiet | Kacheln | 10 cm voll | genutzter Download (0,4 m + 2 m) |
|---|---|---|---|
| Testgebiet (Zellen 8,99–9,52° O / 47,18–47,51° N) | 1518 | ca. 95 GB | 2,55 GB |
| Schweiz (Hochrechnung) | ca. 43 000 | ca. 2–2,5 TB | ca. 70 GB |
| Schweiz, nur 2 m (kompakt) | ca. 43 000 | – | ca. 6,5 GB |

Die Variante `kompakt` lädt nur das 2-m-Asset (0,154 MB je Kachel).

## Aufbau der IMG (detail)

Seit 2026-11-07 hat detail nur die feine Serie (Aufbau „X3“):

| bits | 24 | 23 | 22 | 21 |
|---|---|---|---|---|
| Pixel N-S | 0,64 m | 1,3 m | 2,6 m | leer |
| Quelle | 0,4 m | 0,4 m | 0,4 m | – |
| Bilder je Zelle | 10 × 10 zu 520 px | 5 × 5 zu 516 px | 4 × 4 zu 322 px | – |

- Zelle 0,0294°, 6252 Zellen für die Schweiz, Map-IDs `77070001`–`77076252`.
- Bits 21 ist die leere oberste Ebene. Alle GMPs haben denselben Satz von Ebenen (21 bis 24), ohne Lücke.
- Gröber als 2,6 m zeigt detail nichts. Dort übernimmt kompakt (7708) bzw. die Basemap.
- Warum 24 bis 22: Der Gerätetest der Testdateien X3 und X3b (Gerätetest 12) ist noch offen. 24 bis 22 ist der
  Vorgabewert. Mit bits 22 überlappt detail mit kompakt auf einer Stufe (2,6 m). Beim Hineinzoomen
  wechselt das Bild deshalb nicht abrupt von 2,6 m auf 1,3 m.
- Die Bilder überlappen um mindestens 2 Karteneinheiten (`luftbild.OVERLAP_MU`, siehe
  [raster-img.md](raster-img.md)). Deshalb sind die Bilder 520, 516 und 322 px breit. Mit 1 px Überlappung wären es 513, 513 und 321 px.

Früherer Aufbau (`--variant detail-voll`):

- Zwei Serien wie bei der Pixelkarte (siehe [raster-img.md](raster-img.md)):
  - feine Serie: Zelle 0,0294°, 10 × 10 Bilder zu 512 px auf der feinsten Stufe, Bilder auf 24 bis 21
  - grobe Serie: Zelle 0,2352° (8 × 8 feine Zellen), Bilder auf 20 bis 18, auf 24 bis 21 Raster-Polygone ohne Bild.
- Die Stufen sind Resampling-Stufen derselben Fotos.
- Die Pyramide entsteht beim Build mit `gdalwarp` direkt aus den Quellkacheln.

| bits | 24 | 23 | 22 | 21 | 20 | 19 | 18 | 17 |
|---|---|---|---|---|---|---|---|---|
| Pixel N-S | 0,64 m | 1,3 m | 2,6 m | 5 m | 10 m | 20 m | 82 m | leer |
| Quelle | 0,4 m | 0,4 m | 0,4 m | 2 m | 2 m | 2 m | 2 m | – |
| Resampling | cubic | average | average | average | average | average | average | – |

- Die Ebenen mit Bild liegen lückenlos von bits 24 bis 18 (`release.check_levels`). Fehlt eine Ebene, zeigt
  das GPSMAP 67 bei diesem Zoom kein Bild (siehe [raster-img.md](raster-img.md)).
- Ein Pixel misst in West-Ost-Richtung ca. 2/3 der N-S-Länge (Grad-Raster bei 47° N).
- Feiner als bits 24 geht nicht. Darunter vergrössern Gerät und BaseCamp die feinste Stufe.
  0,64 m entspricht der feinsten Stufe der Pixelkarte 10-1000.
- JPEG q80. Fotos haben keine scharfen Kanten wie die Kartengrafik. In Stichproben zeigt q80 keine
  Blockartefakte. q85 ist ca. 19 % grösser.
- Map-IDs: feine Serie `77070001`–, grobe Serie `77078001`–, fortlaufend über die Zellen der Schweiz.
  `77079000` ist die gmapi-Übersicht.
- Ausserhalb der Schweiz liefert SWISSIMAGE keine Daten. Dort bleibt das Bild weiss.

## Variante kompakt (FID 7708)

Ziel: die ganze Schweiz in einer Datei unter 4 GiB (FAT32). Feine Serie mit Zelle 0,1176° wie Pixel 50-1000,
Bilder auf 24 bis 21. Grobe Serie mit Zelle 0,2352°, Bilder auf 20 bis 18.

| bits | 24 | 23 | 22 | 21 | 20 | 19 | 18 | 17 |
|---|---|---|---|---|---|---|---|---|
| Pixel N-S | 2,6 m | 2,6 m | 5 m | 10 m | 20 m | 41 m | 82 m | leer |
| Quelle | 2 m | 2 m | 2 m | 2 m | 2 m | 2 m | 2 m | – |

- Alle Stufen kommen aus dem 2-m-Asset. Die feinste Stufe misst 2,6 m N-S und 1,7 m W-O.
- Die feinste Stufe liegt auf bits 24 und 23 mit denselben Bildern. Gerät und BaseCamp vergrössern sie bis zum
  stärksten Zoom.
- Die Ebenen liegen lückenlos von 24 bis 18. Ohne Ebene 23 zeigte das GPSMAP 67 bei „200 m“ und „300 m“ kein Bild.
- Die gröbste Stufe liegt auf bits 18. Weiter heraus zeigt die IMG nichts. Dort übernimmt die Basemap des Geräts.
  Eine Übersichts-GMP (`--overview`) machte die IMG am Gerät ungültig. Mögliche Ursache: ihre Grösse **(unsicher)** (siehe
  [raster-img.md](raster-img.md)).
- 450 feine Zellen für die Schweiz, Map-IDs `77080001`–`77080450`. Grobe Serie ab `77088001`,
  gmapi-Übersicht `77089000`.

Grösse aus der Probe St. Gallen (42 Zellen, 4315 km² mit Daten):

| JPEG | Probe | je km² | Schweiz (41 285 km² + 3 % Rand) | je Zelle × 450 |
|---|---|---|---|---|
| q75 | 251 MB | 58 kB | ca. 2,5 GB | ca. 2,7 GB |
| q80 | 286 MB | 66 kB | ca. 2,8 GB | ca. 3,05 GB |
| q85 | 335 MB | 77 kB | ca. 3,3 GB | ca. 3,6 GB |

- Standard ist q80. Die Reserve zur Grenze von 4,29 GB beträgt ca. 30 %.
- Eine feinere Stufe passt nicht. Mit 1,9 m (Faktor 1,5) wird die Schweiz ca. 4,6 GB gross.
- Die Spalte „je Zelle“ ist zu hoch, weil Randzellen ausserhalb der Schweiz weiss sind. Die Spalte
  „je km²“ ist die bessere Schätzung. Für das Hochgebirge ist die Schätzung **(unsicher)**.

## Unterschiede zur Pixelkarte

| Punkt | Pixelkarte | Luftbild |
|---|---|---|
| Quelle je Stufe | eigener Massstab (SMR10 bis SMR1000) | eine Quelle, Pyramide per Resampling |
| Bildinhalt | Grafik mit Schrift | Foto ohne Beschriftung |
| Verkleinern | cubic | average |
| JPEG | q85 | q80 |
| Säume | keine (Blattschnitt der Karte) | möglich zwischen Befliegungsjahren |
| Wiederverwendet | – | `release.Plan`, `split`, `id_table`, `rasterimg`, `smr_tiles.cut_tiles`, `make_gmapi`, Regionen |

Befliegungsjahre: Benachbarte Kacheln können aus verschiedenen Jahren stammen. Dann entstehen Säume
mit anderer Vegetation und Beleuchtung. Der Build gleicht die Farben nicht ab. Im Testgebiet stammen alle
Kacheln aus 2025.

## Grösse

| Datei | FID | GMP | IMG |
|---|---|---|---|
| `Helvetopo_Luftbild_Testgebiet_2026-11.img` (detail-voll) | 7707 | 198 | 1,61 GB |
| `Helvetopo_Luftbild-kompakt_Schweiz_2026-11.img` | 7708 | 450 + 130 | 3,15 GB |
| `Helvetopo_Luftbild_Detail_<Teil>_2026-11.img`, 18 Teile | 7707 | 6252 | 50,5 GB |

- kompakt Schweiz: GMPs 0,52 bis 10,3 MB, davon 54 auf 512 KiB aufgefüllt. gmapi mit Routen 2,9 GB.
  Bauzeit ca. 9 min aus der lokalen Kopie von SWISSIMAGE (42 691 Kacheln zu 2 m).
- detail Schweiz: GMPs 0,64 bis 11,9 MiB, im Mittel 8,1 MB. Keine GMP liegt unter 512 KiB.
  gmapi mit Routen 47 GB. Bauzeit 79 min (10 Prozesse) aus der lokalen Kopie (42 691 Kacheln zu 0,4 m, 65 GB).
- detail-voll, Testgebiet: Eine GMP misst im Mittel 8,1 MB. Die Stufe bits 24 macht ca. 3/4 davon aus.
  gmapi 1,5 GB, Bauzeit ca. 3 min (6 Prozesse).

### Teile von detail

`luftbild.py --split-max 4e9` teilt die Schweiz ohne Überlappung (`split_parts`):

- Ausgangspunkt sind die neun Regionen der Pixelkarte 10-1000. Jede grobe Zelle (0,2352°) gehört genau einer
  Region. Die feinen Zellen folgen ihrer groben Zelle.
- Eine Region über der Grenze wird in 2 bis 4 Streifen entlang der längeren Achse geteilt. Die Schnitte liegen auf
  dem Raster der groben Zellen. Die Grösse kommt aus den gebauten GMPs.
- `regionen.geojson` (in der Ablage `regionen-detail.geojson`) enthält je Teil Umriss, Zellen, Landfläche und Bytes.

| Teil (Datei) | Zellen | Land km² | IMG |
|---|---|---|---|
| Genfersee-West | 322 | 1795 | 2,22 GB |
| Genfersee-Ost | 256 | 1877 | 2,07 GB |
| Bern-West | 264 | 1790 | 2,00 GB |
| Bern-Mitte | 448 | 3282 | 3,69 GB |
| Bern-Ost | 384 | 2821 | 3,17 GB |
| Nordwestschweiz | 395 | 2403 | 3,07 GB |
| Wallis-West | 350 | 2192 | 2,90 GB |
| Wallis-Ost | 433 | 2909 | 3,95 GB |
| Zuerich-West | 328 | 2098 | 2,55 GB |
| Zuerich-Ost | 342 | 2232 | 2,51 GB |
| Ostschweiz | 522 | 3442 | 3,86 GB |
| Graubuenden-Nord | 480 | 3151 | 3,93 GB |
| Graubuenden-Mitte | 374 | 2478 | 3,15 GB |
| Graubuenden-Sued | 186 | 912 | 1,44 GB |
| Zentralschweiz-West | 320 | 2341 | 2,55 GB |
| Zentralschweiz-Ost | 320 | 2341 | 2,76 GB |
| Tessin-Nord | 352 | 2464 | 3,35 GB |
| Tessin-Sued | 176 | 924 | 1,35 GB |

- Der Kartenname ist „Helvetopo Luftbild Detail 2026-11 <Teil>“, z. B. „… Graubünden Nord“.
- Alle Teile teilen sich FID 7707. Jede Map-ID kommt in genau einem Teil vor.
- Das grösste Teil (Wallis-Ost) hat eine Reserve von ca. 8 % zur Grenze von 4 GiB.

## Aufruf

```bash
python3 -I src/raster_img/luftbild.py --region testgebiet --download
python3 -I src/raster_img/luftbild.py --region testgebiet --version 2026-11 --gmapi
python3 -I src/raster_img/luftbild.py --variant kompakt --region schweiz --download
python3 -I src/raster_img/luftbild.py --variant kompakt --region schweiz --version 2026-11 --gmapi
python3 -I src/raster_img/luftbild.py --variant detail --region schweiz --version 2026-11 \
    --split-max 4e9 --gmapi --routes <PBF>
```

- `--variant detail` (Standard), `kompakt` oder `detail-voll`. Die Variante setzt FID, Ebenen, Kartenname
  („Helvetopo Luftbild kompakt 2026-11“), Dateiname (`Helvetopo_Luftbild-kompakt_Schweiz_2026-11`) und
  Ausgabeordner.

- `--download` lädt die Kacheln für alle Zellen der Region und endet.
- `--split-max BYTES` teilt die Schweiz in Teile unter dieser Grösse (nur mit `--region schweiz`).
- `--gmapi-only` baut nur die gmapi aus den GMPs im Cache, ohne Gerätedatei.
- Weitere Optionen: `--quality`, `--fid`, `--name`, `--file`, `--bbox`, `--jobs`, `--dry-run`.
- Ausgabe: `work/raster_img/luftbild/` bzw. `work/raster_img/luftbild-kompakt/` mit IMG, `<Datei>_QUELLSTAND.txt` und `gmapi/`.
- `--routes <PBF>` nimmt Wanderwege und SchweizMobil-Routen in die gmapi auf, siehe [raster-img.md](raster-img.md).

## Lizenz und Quellstand in der Datei

- TRE-Copyright je GMP: `©swisstopo`, „SWISSIMAGE 10 cm (Befliegung JJJJ), swisstopo OGD“,
  „<Kartenname>, inoffizielle Karte“.
- IMG-Beschreibung: Kartenname und `©swisstopo`. MPS-Serienname: Kartenname.
- `<Datei>_QUELLSTAND.txt`: Kachelzahl, Befliegungsjahre, Stand der Items, genutzte Auflösungen,
  STAC-Collection, Lizenzzeile.
- Prüfung: `src/build/check_license.sh work/raster_img/luftbild` bzw. `…/luftbild-kompakt`.

## Offene Punkte

- Gerätetest von detail (24 bis 22) über kompakt: Ladezeit, Wechsel der Stufen, Anzeige mehrerer Teile.
- BaseCamp zeigt in der gmapi von detail nur bits 24 bis 22. Weiter heraus bleibt das Bild weiss, weil BaseCamp
  nur ein Kartenprodukt gleichzeitig zeigt. Möglicher Ausweg: kompakt-Stufen in die gmapi von detail aufnehmen
  **(nicht geprüft)**.
- Das BaseCamp-ZIP von detail ist ca. 50 GB gross.
- Darstellung der Variante kompakt in BaseCamp und am GPSMAP 67.
- In Gerätetest 6 bot das GPSMAP 67 beide Luftbild-IMGs mit zwei Serien nicht an. Ursache: grobe GMPs unter
  ca. 330 KB über Flächen mit wenig Bildinhalt (Bodensee, Kantonsrand). Seit Gerätetest 9 füllt der Build jede
  GMP auf 512 KiB auf, siehe [raster-img.md](raster-img.md). Das Gerät bietet eine aufgefüllte Testdatei an, K und L sind noch nicht geprüft.
- Grösse der Variante kompakt im Hochgebirge.
- Säume und Farbabgleich in Regionen mit mehreren Befliegungsjahren.
- Ob 0,64 m auf bits 24 am Gerät sichtbar schärfer ist als 1,3 m.
- Kombination mit der Vektorkarte als Overlay (Transparenz, Zeichenreihenfolge).
- Routen über dem Luftbild am Gerät (Overlay 7702) und in BaseCamp (gmapi mit `--routes`).
