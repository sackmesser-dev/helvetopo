# Mitmachen bei Helvetopo

Danke für dein Interesse! Helvetopo ist ein Freizeitprojekt, das grösstenteils mit KI-Hilfe
(Claude) entsteht. Beiträge von Menschen sind willkommen, gerade beim Prüfen.

## Fehler melden (Issues)

Bitte für jeden Fehler ein [Issue](../../issues/new/choose) eröffnen. Hilfreich sind:

- **Ort:** Koordinaten (WGS84 oder LV95) oder ein Link auf map.geo.admin.ch
- **Karte und Version:** Dateiname bzw. Release (z. B. `Helvetopo_Vektor_Schweiz_2026-11.img`)
- **Gerät oder Programm:** Modell und Firmware bzw. BaseCamp-Version, Betriebssystem
- **Zoomstufe** und was du erwartet hättest (z. B. Ausschnitt der Landeskarte zum Vergleich)
- **Screenshot**

Fehler in den Quelldaten selbst (falscher Wegverlauf, falscher Name) meldest du am besten
direkt bei swisstopo bzw. SchweizMobil. Helvetopo übernimmt die Korrektur mit dem nächsten
Datenstand.

## Änderungen beitragen (Pull Requests)

- Verbesserungen bitte als **Pull Request** gegen `main`.
- Bei grösseren Änderungen (neue Kartenart, Umbau der Pipeline, Stilwechsel) zuerst ein Issue
  eröffnen, damit wir die Richtung abstimmen können.
- Ein PR pro Thema. Kurz beschreiben, was sich ändert und wie du es getestet hast
  (Build, BaseCamp, Gerät).
- **Stiländerungen:** Ziel ist die Nähe zur Landeskarte 1:25'000. Bitte begründen, und wenn
  möglich mit `src/style_qa/` messen ([docs/stil/messung.md](docs/stil/messung.md)).
- **Mit KI erzeugter Code ist willkommen.** Bitte im PR erwähnen und das Ergebnis selbst
  ausprobiert haben.

## Regeln

- **Sprache:** Doku, Issues und Commits auf Deutsch (Englisch geht auch). Code-Bezeichner auf
  Englisch.
- **Schreibregeln:** Alle Texte folgen ASD-STE100, übertragen auf Deutsch
  ([docs/schreibregeln.md](docs/schreibregeln.md)). Das gilt für Markdown-Dateien, PR- und
  Issue-Beschreibungen und Commit-Nachrichten. Kurze aktive Sätze, kein Semikolon, nur Fakten zum
  aktuellen Stand. Vor dem PR `python3 src/doc_lint/check_md.py` ausführen. Der Workflow prüft
  das bei jedem PR noch einmal.
- **Keine fremden Datenquellen.** Nur swisstopo-OGD und SchweizMobil-Routen (Open Data BY).
  Kein OpenStreetMap (ODbL), keine kantonalen Daten, keine Logos oder Marken. Wer eine neue
  Quelle vorschlägt, dokumentiert die Lizenzfolgen.
- **Keine grossen Dateien committen:** Geodaten, IMG, ZIP, TIFF gehören nach `downloads/` bzw.
  `work/` (gitignored).
- **Kein massives Scraping** von WMTS-Kacheln. Daten kommen über den STAC-Katalog
  `data.geo.admin.ch`.

## Lizenz deiner Beiträge

Mit einem Pull Request stellst du deinen Beitrag unter die Lizenz des Projekts
(Code: [GPL-3.0-or-later](LICENSE)). Übernimm keinen Code aus Quellen mit unverträglicher
Lizenz und nenne die Herkunft, wenn du dich an fremdem Code orientierst.
