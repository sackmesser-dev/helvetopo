# Gerätetest GPSMAP/Montana – Kurzanleitung

Das Paket liegt in `work/geraetetest/`. Es wird mit `src/build/geraetetest_paket.sh` erzeugt und enthält
die Release-Dateien von `src/release/make_release.py`. Getestet werden also genau die Dateien, die zum
Download kommen. Die Datei `*_SHA256SUMS.txt` im Paket enthält die Prüfsummen.

Vorher:
- Vorhandene Dateien in `\Garmin\` sichern.
- Die Dateinamen nicht ändern. Eine `gmapsupp.img` darf daneben liegen bleiben.
- GPSMAP 66/67 und Montana 7xx erscheinen als MTP-Gerät. Kopieren mit Android File Transfer, mit
  OpenMTP oder über die microSD-Karte im Kartenleser. Ziel ist `\Garmin\` im internen Speicher oder auf der SD-Karte.

## Test 1 – Vektorkarte

1. `1-vektor/Helvetopo_Vektor_<Gebiet>_<Version>.img` nach `\Garmin\` kopieren.
2. Gerät neu starten.
3. Einstellungen → Karte → Karteninformation:
   - „Helvetopo“ aktivieren.
   - Andere Topo-Karten für den Test ausblenden.
   - Kartendetail einmal auf „Normal“, einmal auf „Maximal“ stellen.
4. Prüfen:
   - **Darstellung:** St. Gallen, Herisau und Säntis in mehreren Zoomstufen. Wie gut ist die Karte draussen lesbar?
   - **Höhen:** Höhenlinien (100 m kräftig, 10 m und 20 m dünn), Koten, Schummerung (Relief einschalten).
   - **Routen:** Wanderwege und SchweizMobil-Routen mit Routenschildern.
   - **Routing:**
     - Wandern Wasserauen → Säntis
     - Velo St. Gallen → Wil, im Velo-Profil mit „Mautstrassen vermeiden“: Die Route soll Veloland folgen.
     - Auto St. Gallen → Appenzell, im Auto-Profil ohne „Mautstrassen vermeiden“.
   - **Bekannt beim Routing:**
     - Auto-Routen zu Zielen ohne Fahrweg enden auf Fusswegen. Das ist Garmin-Verhalten.
     - Einbahnen und Abbiegeverbote fehlen.
   - **Suche:**
     - Adresse „Marktgasse 20, St. Gallen“
     - Gipfel „Säntis“
     - Ort „Gossau SG“: Er darf nur einmal erscheinen.
   - **Höhenangabe** an einem bekannten Punkt (Säntis 2502 m) und das Höhenprofil einer Route.

## Test 2 – Pixelkarte (Raster-IMG, experimentell)

Die drei Varianten haben eigene Family-IDs (7704, 7705, 7706) und dürfen gleichzeitig auf dem Gerät
liegen. Für den Test immer nur **eine** Variante einblenden.

1. `2-pixel/Helvetopo_Pixel_50-1000_…img` nach `\Garmin\` kopieren. Bei genug Speicher auch 25-1000
   und 10-1000 kopieren (zusammen etwa 2,3 GB im Testgebiet).
2. In der Karteninformation die Variante einblenden und „Helvetopo“ (Vektor) ausblenden.
3. Prüfen:
   - Ist das Bild von 15 km bis 100 m durchgehend, ohne Lücken und ohne Säume?
   - Bei welchem Zoom wechselt der Massstab (1:1 Mio., 1:500'000, …, 1:25'000)?
   - Nur Variante 10-1000: Ab welchem Zoom erscheint die Landeskarte 1:10'000? Erwartet ist ab etwa 700 m.
   - Wie schnell zeichnet die Karte beim Zoomen und Verschieben?
   - Wie spielt die Pixelkarte mit der Vektorkarte zusammen, wenn beide eingeblendet sind?

Die feinen Linien im Bild sind das gedruckte Kilometernetz der Landeskarte.

## Rückmeldung

Am einfachsten Fotos oder Screenshots und Stichworte je Test in den Chat. Vor allem wichtig:
- Test 1: Lesbarkeit draussen und Routing.
- Test 2: Ist das Bild durchgehend? Bei welchen Zoomstufen wechselt der Massstab?
