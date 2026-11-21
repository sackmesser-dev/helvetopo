# Helvetopo Luftbild 2026-11 (experimentell)

Orthofotos SWISSIMAGE von swisstopo als Garmin-IMG. Gebiet: Schweiz und Liechtenstein.
Inoffizielle Karte: kein Produkt von swisstopo oder Garmin.

## Dateien

- `Helvetopo_Luftbild_Standard_Schweiz_2026-11.img`: Gerätedatei (FID 7708).
- `Helvetopo_Luftbild_Standard_Schweiz_2026-11_BaseCamp.zip`: BaseCamp-Paket für die ganze Schweiz.
- 18 Gerätedateien, je Teilgebiet eine, ohne Überlappung: `Helvetopo_Luftbild_Detail_Genfersee-West_2026-11.img`, `Helvetopo_Luftbild_Detail_Genfersee-Ost_2026-11.img`, `Helvetopo_Luftbild_Detail_Bern-West_2026-11.img`, `Helvetopo_Luftbild_Detail_Bern-Mitte_2026-11.img`, `Helvetopo_Luftbild_Detail_Bern-Ost_2026-11.img`, `Helvetopo_Luftbild_Detail_Nordwestschweiz_2026-11.img`, `Helvetopo_Luftbild_Detail_Wallis-West_2026-11.img`, `Helvetopo_Luftbild_Detail_Wallis-Ost_2026-11.img`, `Helvetopo_Luftbild_Detail_Zuerich-West_2026-11.img`, `Helvetopo_Luftbild_Detail_Zuerich-Ost_2026-11.img`, `Helvetopo_Luftbild_Detail_Ostschweiz_2026-11.img`, `Helvetopo_Luftbild_Detail_Graubuenden-Nord_2026-11.img`, `Helvetopo_Luftbild_Detail_Graubuenden-Mitte_2026-11.img`, `Helvetopo_Luftbild_Detail_Graubuenden-Sued_2026-11.img`, `Helvetopo_Luftbild_Detail_Zentralschweiz-West_2026-11.img`, `Helvetopo_Luftbild_Detail_Zentralschweiz-Ost_2026-11.img`, `Helvetopo_Luftbild_Detail_Tessin-Nord_2026-11.img`, `Helvetopo_Luftbild_Detail_Tessin-Sued_2026-11.img` (FID 7707).
- `Helvetopo_Luftbild_Detail_Schweiz_2026-11_BaseCamp.zip`: BaseCamp-Paket für die ganze Schweiz.

- Luftbild Standard (FID 7708): ganze Schweiz in einer Datei, ca. 2,6 m bis 82 m je Pixel.
- Luftbild Detail (FID 7707): Gerätedateien je Teilgebiet, ca. 0,64 m bis 2,6 m je Pixel. Detail ergänzt
  Standard für die grossen Massstäbe. Am Gerät beide Karten einblenden. Detail liegt über Standard.
  Das BaseCamp-Paket von Detail zeigt nur die grossen Massstäbe.

## Installation

- Gerät: Die IMG in den Ordner `Garmin/` auf dem Gerät oder der microSD-Karte kopieren. Die Karte unter
  Karteneinstellungen einblenden. Kartendetail „Normal“ wählen.
- BaseCamp: Das ZIP entpacken und den `.gmap`-Ordner nach `C:\ProgramData\Garmin\Maps\` (Windows)
  bzw. `~/Library/Application Support/Garmin/Maps/` (macOS) kopieren. Die Wanderwege und
  SchweizMobil-Routen sind darin eingebaut.

Prüfsummen: `Helvetopo_2026-11_SHA256SUMS.txt`.

## Quellen und Lizenz

Quellenangabe: `©swisstopo`. BaseCamp-Paket mit Routen zusätzlich: `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`.
Datenstand: [QUELLSTAND.md](QUELLSTAND.md). Bedingungen: [LICENSE-KARTEN.md](../../../LICENSE-KARTEN.md).
Ohne Gewähr.
