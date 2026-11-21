# Teststufen und Werkzeuge

Stand: 2026-11-05.

Garmin bietet keinen Simulator für eigene IMG-Karten. Die Prüfung läuft in Stufen: CLI, Viewer,
BaseCamp, Gerät.

## Stufen

| Stufe | Ziel | Werkzeug | automatisierbar |
|---|---|---|---|
| 0 | Stil und TYP-Quelle korrekt | `mkgmap --style-file=… --check-styles`, TYP mit mkgmap kompilieren | ja |
| 1 | Topologie für das Routing | mkgmap mit `--route --index --report-routing-islands --report-roundabout-issues --report-similar-arcs --report-dead-ends=1`, Meldungen zählen | ja |
| 2 | Struktur der IMG | `src/build/img_ls.py`, `src/raster_img/inspect_img.py`, mkgmap display (`ImgDisplay`, `TreDisplay`, `NetDisplay`, `NodDisplay`, `DemDisplay`, `MdrCheck`, `TypDisplay`) | ja |
| 3 | Inhalt und Regression | `src/style/tools/render_img.py`, `src/style_qa/` (Messung gegen SMV25 und SMR) | ja |
| 4 | Sichtprüfung Stil, TYP, DEM | GPXSee, QMapShack | nein |
| 5 | Routing, Suche, Metadaten wie Garmin | BaseCamp (macOS oder Windows) | nein |
| 6 | Integration | Gerät (GPSMAP 67): Darstellung, Routing, Suche, Höhenschattierung, Ladezeit | nein |

- Die Stufen 0–3 laufen auf jedem System mit Java und Python.
- Die Lizenzprüfung (`src/build/check_license.sh`) läuft in jedem Build.
- BaseCamp und das Gerät ignorieren eine TYP mit anderer Family-ID oder Product-ID als die Karte.
  GPXSee und QMapShack zeigen sie trotzdem an.

## Werkzeuge

| Werkzeug | Plattform | Darstellung | TYP | Routing | Suche | DEM aus IMG |
|---|---|---|---|---|---|---|
| mkgmap `--check-styles`, `--report-*` | Java | nein | kompiliert | Berichte | nein | nein |
| mkgmap display (`test.display.*`) | Java | Text-Dump | ja | Struktur | `MdrCheck` | ja |
| `render_img.py` (eigen) | Python | PNG | ja | nein | nein | nein |
| GPXSee | macOS, Windows, Linux | ja (auch NT) | ja | nein | nein | ja |
| QMapShack | macOS arm64 (Fork), Linux, Windows | ja (ohne NT) | ja | nein | ? | nein |
| BaseCamp 4.8 | Windows. macOS nur Intel (Rosetta) | ja | ja | ja | ja | ja |
| GPSMapEdit, TYPViewer | Windows | ja bzw. TYP-Vorschau | ja | MP-Ebene | teilweise | ? |

- BaseCamp ist das einzige Programm, das Routing (NET/NOD) und Adresssuche (MDR) so liest wie Garmin.
- BaseCamp für macOS ist eine reine x86_64-App. macOS 27 ist laut Apple die letzte Version mit vollem
  Rosetta 2. Danach bleibt BaseCamp für Windows.
- GPXSee liest IMG, GMAP-Ordner und JNX und wertet das DEM aus. Ein Routing-Test ist nicht möglich.
  Der Homebrew-Cask ist seit 2026-09-01 deaktiviert.
- QMapShack lehnt NT-Karten ab und wertet das DEM in der IMG nicht aus. Es gibt kein Homebrew-Paket.
- GDAL hat keinen Treiber für Garmin-IMG.
- Parser-Bibliotheken: `garmin_img` (Dart, MIT), `garmin-img-parser` (Python, MIT), `typconv` (Go, MIT,
  TYP binär ↔ Text).

## BaseCamp

- Installation: `.gmap`-Ordner nach `C:\ProgramData\Garmin\Maps\` bzw.
  `~/Library/Application Support/Garmin/Maps/`. mkgmap erzeugt ihn mit `--gmapi`.
- Vor jedem Kartenwechsel TileCache und ProductDataCache leeren. Sonst zeigt BaseCamp alte Kacheln.
- BaseCamp zeigt nur ein Kartenprodukt gleichzeitig. Gleiche FIDs nacheinander installieren.
- Wegpunkte unterdrücken Kartenlabels in ihrer Nähe. Testpunkte nicht auf Ortszentren setzen.
- Die VM läuft mit 200 % DPI. BaseCamp zeichnet TYP-Pixel physisch. Linien wirken dort halb so breit
  wie am Gerät.
- Orte sucht man über Suchen → „Points of Interest suchen“ → „Städte“, nicht über das obere Suchfeld.
- BaseCamp zeigt in der POI-Suche ab der zweiten Abfrage einer Sitzung jeden Treffer doppelt, mit
  gleicher Distanz. Das gilt auch für „Städte“. Die erste Abfrage nach dem Start zeigt jeden Treffer
  einmal. Die Karte ist nicht die Ursache: Eine Testkarte mit POIs in einer, zwei und drei Ebenen
  verhält sich in allen Varianten gleich. Doppelte Treffer deshalb nur in der ersten Abfrage zählen.
- BaseCamp zeigt keine KMZ Custom Maps.
- Für Routing-Vergleiche Routen als GPX exportieren und mit `src/routing/gpx_match.py` auswerten.

## Gerät

- GPSMAP 66/67 und Montana 7xx erscheinen am Mac als MTP-Gerät. Kopieren mit OpenMTP bzw. Android File
  Transfer oder über die microSD-Karte.
- Vektor- und Raster-IMG gehören nach `\Garmin\`, KMZ nach `\Garmin\CustomMaps\`.
- Gleiche FID nur einmal gleichzeitig im Ordner.
- Nach dem Kopieren neu starten. Unter Einstellungen → Karte → Karteninformation die Karte aktivieren
  und andere Topo-Karten für den Test ausblenden.
- *Kartendetail* verschiebt die Zoomwechsel: „Maximal“ zeigt feinere Ebenen eine Stufe früher.
- Kurzanleitung für ein Testpaket: [geraetetest.md](geraetetest.md).

## Gerätekompatibilität

Das Projekt testet am Gerät nur mit einem GPSMAP 67. Für andere Geräte gibt es keinen Emulator. Der Connect-IQ-Simulator simuliert nur Apps und liest keine `gmapsupp.img`.
Die Kompatibilität mit anderen Geräten sichern vier Mittel: Firmware-Familien, Grenzwerte, eine Referenzkarte und ein Betatest.

### Firmware-Familien

Geräte einer Familie nutzen dieselbe Kartendarstellung. Ein Test an einem Gerät gilt deshalb für seine Familie. Die Zuordnung der Modelle stammt aus Foren und ist nicht von Garmin bestätigt **(unsicher)**.

| Familie | Geräte (Beispiele) | Status |
|---|---|---|
| Handhelds ab 2018 | GPSMAP 65/66/67, Montana 7xx, eTrex 22x/32x, eTrex SE/Solar | Zielgeräte, getestet mit GPSMAP 67 |
| Handhelds 2011–2017 | GPSMAP 62/64/78, eTrex 10/20/30, Oregon 6xx/7xx, Montana 6xx | nicht getestet |
| alte Handhelds | GPSMAP 60/76 CSx, eTrex HCx, Colorado | nicht unterstützt: höchstens 2025 Kacheln, keine erweiterten Typen |
| Uhren und Velocomputer | fēnix, epix, Edge mit Karte | nicht getestet: wenig Speicher, TYP nur teilweise |
| Autonavis | Drive, zūmo | kein Ziel |

### Grenzwerte

An den Grenzwerten scheitert eine Karte auf einem anderen Gerät am häufigsten. Die Darstellung selbst unterscheidet sich weniger. `src/release/make_release.py` prüft die Grenzwerte in `check_limits()`, bevor es das Manifest schreibt.

| Grenzwert | Wert | Art | Quelle |
|---|---|---|---|
| Dateigrösse | höchstens 4 GiB − 1 Byte | Fehler | FAT32 |
| Blöcke je IMG | höchstens 65 535 | Fehler | IMG-Format: Blocknummern mit 16 Bit |
| Kacheln je IMG | höchstens 4000 | Fehler | mkgmap-Mailingliste, openmtbmap.org **(unsicher)** |
| Kacheln je IMG für alte Geräte | höchstens 2025 | Warnung | mkgmap-Mailingliste, openmtbmap.org **(unsicher)** |
| Raster-Kacheln | höchstens 516 wie die Referenzkarte | Warnung | Referenzkarte, siehe unten |
| erweiterte Typen in der TYP (ab `0x10000`) | keine | Warnung | mkgmap style manual |
| BaseCamp-ZIP | höchstens IMG + 10 % | Fehler | Plausibilität |

- Fehler brechen das Release ab. Das Skript schreibt dann kein Manifest.
- Warnungen erscheinen in der Ausgabe. Die Vektorkarte nutzt erweiterte Typen bewusst. Alte Geräte zeigen diese Objekte nicht an.
- Für Subdateien je IMG ist kein Grenzwert der Geräte bekannt. Das Skript zählt sie nur.
- Tag- und Nachtfarben, Schriftstile und Bilder in der TYP prüft das Skript nicht. Ältere Geräte ignorieren einen Teil davon **(unsicher)**.
- Für KMZ gelten eigene Grenzwerte: Kachelzahl 100 bzw. 500, JPEG bis 1024 px und unter 3 MB. Sie stehen in [kmz.md](../raster/kmz.md). Das Skript `check.py` prüft sie.

### Was die Programme prüfen

| Programm | prüft | prüft nicht |
|---|---|---|
| mkgmap display, `inspect_img.py`, `img_ls.py` | Aufbau der IMG, Subdateien, Kacheln, TYP, Copyright | Darstellung auf einem Gerät |
| GPXSee, QMapShack | Darstellung, TYP, DEM (nur GPXSee) | Routing, Suche, Grenzwerte der Geräte |
| BaseCamp | Darstellung, Routing, Suche, Family-ID und TYP wie Garmin | Darstellung der Gerätefirmware, Speicher- und Kachelgrenzen |
| Gerät (GPSMAP 67) | alles für die eigene Familie | andere Familien |

Die Programme zeigen, ob eine IMG gültig ist und die Daten stimmen. Wie eine bestimmte Firmware die Karte zeichnet, zeigen sie nicht.

### Referenzkarte „Topo Schweiz v3 Raster“

„Topo Schweiz v3 Raster“ ist eine Raster-IMG von Garmin. Sie hat 516 GMP-Kacheln in einer Datei mit 3,4 GB und 64-KiB-Blöcken. Garmin nennt im Produktblatt die kompatiblen Geräte.

Die Raster-IMG von Helvetopo folgt dem Aufbau dieser Karte. Je enger der Aufbau übereinstimmt, desto eher gilt die Geräteliste von Garmin auch für Helvetopo. Vergleich:

1. Beide Dateien mit `src/raster_img/inspect_img.py` lesen.
2. Blockgrösse, Ebenen, Kachelgrösse, Anzahl Bilder je Kachel und JPEG-Grösse vergleichen.
3. Abweichungen in [raster-img.md](../raster/raster-img.md) je Merkmal festhalten.

Die Referenzkarte liegt nicht im Repo. Sie ist nicht frei und darf nur zum Vergleich gelesen werden.

### Betatest

Ein Betatest mit anderen Personen deckt die Familien ab, für die das Projekt kein Gerät hat.

1. Beta-Dateien auf der Downloadseite als „Beta“ kennzeichnen.
2. Auf das Rückmeldeformular verlinken: [.github/ISSUE_TEMPLATE/geraet.yml](../../.github/ISSUE_TEMPLATE/geraet.yml).
3. Den Betatest in Foren mit Garmin-Nutzern bekannt machen, zum Beispiel naviboard.de.
4. Rückmeldungen in einer Tabelle sammeln: Gerät, Firmware, Karte, Ergebnis je Prüfpunkt.
5. Die Tabelle der Firmware-Familien oben nachführen.

Das Formular fragt nach Gerät, Firmware, Karte, Speicherort und je einem Ergebnis für Darstellung, Zoomstufen, Routing, Suche und Ladezeit.

### Altgerät (optional)

Ein gebrauchtes Gerät der Familie „Handhelds 2011–2017“ deckt die ältere Firmware ab. Beispiele sind eTrex 20/30 oder GPSMAP 64. Läuft eine Karte dort, läuft sie mit hoher Wahrscheinlichkeit auch auf neueren Geräten. Uhren und Velocomputer lohnen sich nur, wenn das Projekt diese Geräte ausdrücklich unterstützt.

## Offene Punkte

- Aufruf und Build von mkgmap display sind nicht dokumentiert und müssen aus den Quellen abgeleitet werden.
- Ob die Geräte die Schummerung gleich darstellen wie BaseCamp.

## Quellen

- mkgmap Optionen: <https://www.mkgmap.org.uk/doc/options>
- mkgmap display: `svn.mkgmap.org.uk/mkgmap/display/trunk`
- GPXSee: <https://github.com/tumic0/GPXSee>
- QMapShack: <https://github.com/Maproom/qmapshack>
