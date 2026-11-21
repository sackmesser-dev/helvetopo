# Helvetopo Pixel 2026-11 (experimentell)

Swiss Map Raster von swisstopo als Garmin-IMG. Jede Zoomstufe zeigt den passenden Massstab bis
1:1'000'000. Gebiet: Schweiz und Liechtenstein. Inoffizielle Karte: kein Produkt von swisstopo oder Garmin.

## Varianten

- **50-1000** (FID 7704): eine Datei für die ganze Schweiz. BaseCamp: `Helvetopo_Pixel_50-1000_Schweiz_2026-11_BaseCamp.zip`.
- **25-1000** (FID 7705): zwei Hälften: West und Ost. BaseCamp: `Helvetopo_Pixel_25-1000_Schweiz_2026-11_BaseCamp.zip`.
- **10-1000** (FID 7706): vier Teile: West, Süd, Mitte und Ost. BaseCamp: `Helvetopo_Pixel_10-1000_Schweiz_2026-11_BaseCamp.zip`.

Eine Gerätedatei bleibt unter 4 GiB (FAT32). Darum gibt es 25-1000 in zwei Hälften und 10-1000 in vier
Teilen. Die Hälften und Teile überlappen nicht. Die Karte im Portal zeigt die Grenzen.

## Installation

- Gerät: Jede IMG in den Ordner `Garmin/` auf dem Gerät oder der microSD-Karte kopieren. Die Karte unter
  Karteneinstellungen einblenden. Kartendetail „Normal“ wählen. Mit „Weniger“ wechselt das Gerät eine
  Stufe früher auf den gröberen Massstab.
- BaseCamp: Je Variante gibt es ein ZIP für die ganze Schweiz. Das ZIP entpacken und den `.gmap`-Ordner
  nach `C:\ProgramData\Garmin\Maps\` (Windows) bzw. `~/Library/Application Support/Garmin/Maps/`
  (macOS) kopieren. Die Wanderwege und SchweizMobil-Routen sind darin eingebaut.

Unterhalb des feinsten Massstabs vergrössert das Gerät das Bild. Die feinen Linien im Bild sind das
gedruckte Kilometernetz der Landeskarte. Prüfsummen: `Helvetopo_2026-11_SHA256SUMS.txt`.

## Quellen und Lizenz

Quellenangabe: `©swisstopo`. BaseCamp-Pakete mit Routen zusätzlich: `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`.
Datenstand: [QUELLSTAND.md](QUELLSTAND.md). Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).
Ohne Gewähr.
