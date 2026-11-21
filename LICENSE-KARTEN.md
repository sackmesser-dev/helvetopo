# Lizenz und Quellenangaben der Karten

Diese Datei gilt für die **Kartendateien** von Helvetopo (IMG, gmap/BaseCamp-Pakete). Für den
**Code** in diesem Repository gilt die [GPL-3.0-or-later](LICENSE).

Die Karten sind aus frei verfügbaren Geodaten abgeleitet. Nutzung und Weitergabe sind erlaubt,
auch kommerziell, sofern die folgenden Quellenangaben bei jeder Darstellung, Veröffentlichung
und Weitergabe erhalten bleiben. Das ergibt sich aus den Bedingungen der Datenquellen. Das
Projekt kann sie nicht einschränken.

## 1. swisstopo – Open Government Data

- **Quellenangabe:** `©swisstopo`
- **Daten:** swissTLM3D, swissTLM3D Wanderwege, swissNAMES3D, swissBOUNDARIES3D, swissALTI3D,
  Swiss Map Vector 25, Swiss Map Raster 10/25/50/100/200/500/1000, amtliches
  Gebäudeadressverzeichnis, amtliches Strassenverzeichnis
- **Bedingungen:** <https://www.swisstopo.admin.ch/ogd-conditions>

## 2. Bundesamt für Strassen ASTRA – SchweizMobil-Routen

Layer `ch.astra.wanderland`, `veloland`, `mountainbikeland`, `skatingland`.

- **Quellenangabe:** `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`
- **Bedingungen:** Opendata BY, <https://opendata.swiss/terms-of-use#terms_by>

## 3. Stiftung SchweizMobil (falls enthalten)

Kanuland, hindernisfreie Wege, Winterrouten.

- **Quellenangabe:** `Stiftung SchweizMobil`
- **Bedingungen:** Open Data BY, <https://schweizmobil.info/de/geodaten>

## Hinweise

- Die Karten enthalten keine Logos oder Marken von swisstopo oder SchweizMobil und sind keine
  offiziellen Produkte dieser Stellen. Sie enthalten keine Daten aus anderen Quellen
  (insbesondere keine OpenStreetMap-Daten). Jeder Build prüft das automatisch
  (`src/build/check_license.sh`).
- Welche Datensätze und Ausgaben in einem Release stecken, steht in dessen `QUELLSTAND.md`.
- **Haftungsausschluss:** Die Karten werden ohne Gewähr bereitgestellt. Das Auto-Routing ist
  nur topografisch und nicht zur Fahrzeugnavigation geeignet.
- Erstellt mit mkgmap und splitter (GPL), GDAL (MIT) und osmium (GPL-3.0). Diese Werkzeuge
  sind nicht Teil der Kartendateien.

Hintergrund zu den Lizenzen: [docs/daten/lizenzen.md](docs/daten/lizenzen.md).
