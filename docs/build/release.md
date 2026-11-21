# Release: Pakete, Dateinamen, Quellstand, Lizenz

Stand: 2026-11-08. Code: `src/release/make_release.py`.

## Grundsätze

- Sprechende Dateinamen. Interne Testnamen (`R3`, `S1`, `gmapsupp.img`) erscheinen nicht im Download.
- Format: `<Präfix>_<Art>_<Massstabsbereich>_<Gebiet>_<Version>.<ext>`, nur ASCII, ohne Leerzeichen
  (FAT32 und Webserver). Präfix `Helvetopo`.
- Version = Release-Datum `JJJJ-MM`, bei mehreren Releases im Monat `JJJJ-MM-TT`. Release-Tag `v<Version>`.
- Kartennamen auf Gerät und in BaseCamp ohne Marke und Logo und ohne Anschein einer offiziellen
  Karte. `©swisstopo` steht in Copyright-Feld und Beschreibung.
- Jede Datei bleibt unter 4 GB (FAT32).
- Verschiedene Varianten haben eigene FIDs und kollidieren nicht. Die Regionen einer Variante teilen
  sich eine FID mit verschiedenen Map-IDs.

## Produkte

### Vektorkarte

| Download | Inhalt | Kartenname |
|---|---|---|
| `Helvetopo_Vektor_Schweiz_<v>.img` | Gerätedatei: Basis und Höhenlinien, ohne Routen (FID 7701) | „Helvetopo Vektor <v>“, Testgebiet „Helvetopo Vektor <v> Testgebiet“ |
| `Helvetopo_Vektor_Schweiz_<v>_BaseCamp.zip` | gmapi-Ordner für BaseCamp mit Routen und Installationshilfe | dito |
| `Helvetopo_Routen_Schweiz_<v>.img` | Routen-Overlay: Wanderwege und SchweizMobil-Routen (FID 7702), transparent | „Helvetopo Routen“ |

Das Routen-Overlay gilt für alle Karten: Vektor, Pixel und Luftbild. Am Gerät ist es einzeln
schaltbar. BaseCamp zeigt nur ein Kartenprodukt gleichzeitig. Deshalb enthält jede BaseCamp-gmapi die
Routen als eigene Kacheln. Erzeugt wird das Overlay mit `src/raster_img/routen.py overlay`, die
Gerätedatei ohne Routen mit `DEVICE_ROUTES=overlay` (Standard). `DEVICE_ROUTES=embedded` baut die
Routen wieder in die Gerätedatei ein.

Mit `DEVICE_FAMILIES=split` sind getrennte Dateien möglich: `…_Vektor-Basis_…img` (7701),
`…_Routen_…img` (7702), `…_Hoehenlinien_…img` (7703).

### Pixelkarte (Raster-IMG)

| Download | Massstäbe | Gebiet | FID |
|---|---|---|---|
| `Helvetopo_Pixel_50-1000_Schweiz_<v>.img` | SMR50 bis SMR1000 | ganze Schweiz in 1 Datei, 3,87 GB (3,60 GiB) | 7704 |
| `Helvetopo_Pixel_25-1000_West_<v>.img`, `…_Ost_<v>.img` | SMR25 bis SMR1000 | Hälften West 2,41 GB, Ost 3,24 GB | 7705 |
| `Helvetopo_Pixel_10-1000_West_<v>.img`, `…_Sued_…`, `…_Mitte_…`, `…_Ost_…` | SMR10 bis SMR1000 | vier Teile ohne Überlappung, 2,84 bis 4,00 GB (zusammen 14,1 GB) | 7706 |

- Jede Gerätedatei bleibt unter 4 GiB (IMG-Format und FAT32). 50-1000 passt mit JPEG q70 und optimierten
  Huffman-Tabellen in eine Datei. 25-1000 und 10-1000 brauchen Hälften bzw. Teile.
- Die Hälften und Teile überlappen nicht. Jede Kachel liegt in genau einer Datei, siehe
  [raster-img.md](../raster/raster-img.md#teilung-ohne-überlappung).
- Zu jeder Variante gibt es eine gmapi für die ganze Schweiz (`…_BaseCamp.zip`), auch wenn die Gerätedatei
  geteilt ist. Eine gmapi hat keine 4-GiB-Grenze. `release.py --region schweiz --gmapi-only` baut sie ohne
  Gerätedatei.
- Das Portal kennzeichnet die Pixelkarte als experimentell.
- Aufbau und Grössen: [raster-img.md](../raster/raster-img.md).

### Luftbild (Raster-IMG, Prototyp)

| Download | Quelle | Gebiet | FID |
|---|---|---|---|
| `Helvetopo_Luftbild-kompakt_Schweiz_<v>.img` | SWISSIMAGE (2,6 m bis 82 m) | ganze Schweiz, 3,15 GB | 7708 |
| `Helvetopo_Luftbild_Detail_<Teil>_<v>.img` | SWISSIMAGE 10 cm (0,64 m bis 2,6 m) | Schweiz in 18 Teilen ohne Überlappung, 1,35 bis 3,95 GB (zusammen 50,5 GB) | 7707 |

- Standard ist kompakt. detail ergänzt kompakt für die grossen Massstäbe und liegt am Gerät darüber.
- detail ist für 2026-11 gebaut und liegt in der Ablage unter `luftbild/<v>/`, mit `regionen-detail.geojson` und
  der gmapi in `BaseCamp/`. Der Gerätetest steht noch aus.
- Das BaseCamp-Paket von detail ist ca. 50 GB gross. Es zeigt nur die Stufen 24 bis 22.
- Aufbau und Grössen: [luftbild.md](../raster/luftbild.md).

KMZ (Custom Maps) sind kein Release-Produkt.

## Ablauf

1. Vektorkarte bauen:
   ```bash
   OUT=work/release-build/vektor VERSION=<v> src/build/build_all.sh
   ```
2. Pixelkarten bauen, je Variante und Region:
   ```bash
   python3 -I src/raster_img/release.py --variant <variante> --region <region> --version <v> --gmapi
   ```
3. Release zusammenstellen:
   ```bash
   .venv/bin/python -I src/release/make_release.py --version <v> --area <gebiet> \
       --vector work/release-build/vektor --pixel work/release-build/pixel [--site]
   ```

Ausgabe von `make_release.py`:
- `work/release/<v>/files/`: IMG, BaseCamp-ZIP und `Helvetopo_<v>_SHA256SUMS.txt`
- `work/release/<v>/manifest.json` für das Portal
- `releases/<v>/vektor/`, `releases/<v>/pixel/` und `releases/<v>/luftbild/` mit `README.md` und
  `QUELLSTAND.md` (versioniert)
- mit `--site` die Portal-Vorschau in `work/portal/site/`

Schweiz: Die Builds liegen in der Ablage auf dem NAS (`HELVETOPO_STORE`, siehe
[build.md](build.md#rohdaten-und-ablage)). `make_release.py` liest sie dort:

```bash
.venv/bin/python -I src/release/make_release.py --version <v> --area schweiz \
    --store <Ablage>/helvetopo/.build --out work/release/<v>-ch [--dry-run]
```

- Erwartete Ablage: `vektor/ch/<v>/`, `routen/ch/<v>/`, `pixel/<v>/` und `luftbild/<v>/`, je mit
  `BaseCamp/*.gmap`.
- Die Gerätedateien in `files/` sind symbolische Links auf die Ablage. Neu entstehen nur die
  BaseCamp-ZIPs (eines je Variante, ganze Schweiz). GMP-Dateien kommen unkomprimiert ins ZIP.
- Produkte und Aufteilung folgen dem Portal-Manifest: 25-1000 mit `region` west/ost, 10-1000 mit den
  vier Teilen `pixel10-west`, `pixel10-sued`, `pixel10-mitte` und `pixel10-ost`. Die IDs haben ein Präfix,
  weil `west` und `ost` die Hälften von 25-1000 sind. Im Manifest hat 10-1000 `area` `regionen`.
  Geplante Produkte (`planned`) übernimmt das Skript von dort.
- `--dry-run` schreibt nur `manifest.dry.json`, ohne Links, ZIPs und Prüfsummen.
- `baseUrl` ist `https://dl.sackmesser.dev/helvetopo/<v>/`. Das Skript schreibt nicht in den öffentlichen
  Ordner der Ablage. Die Veröffentlichung gibt der Benutzer frei.
- Das Luftbild „kompakt“ heisst im Release `Helvetopo_Luftbild_Standard_Schweiz_<v>.img` (Produkt
  `luftbild-standard`).
- Luftbild detail (Produkt `luftbild-detail`, `area` `regionen`): Die Teile liest das Skript aus
  `luftbild/<v>/regionen-detail.geojson`. Die Feature-`id` ist die Region im Manifest, z. B.
  `graubuenden-sued` für `Helvetopo_Luftbild_Detail_Graubuenden-Sued_<v>.img`. Ausnahme: Ostschweiz und
  Nordwestschweiz haben eine andere Form als bei Pixel 10-1000. Sie heissen im Manifest `luftbild-ostschweiz` und
  `luftbild-nordwestschweiz` (`LUFTBILD_REGION_ID`). Dazu kommt ein BaseCamp-ZIP für die ganze Schweiz.

## Dateien

- Die IMG wird direkt heruntergeladen, ohne ZIP-Hülle. Dazu gibt es eine SHA-256-Prüfsumme.
- README und Quellstand liegen je Release unter `releases/<v>/<vektor|pixel>/`. Die Kartenlizenz steht
  in `LICENSE-KARTEN.md`, die Codelizenz in `LICENSE`. Das Portal verlinkt sie im GitHub-Repo auf den
  Release-Tag.
- Die BaseCamp-ZIPs enthalten README und LICENSE.
- BaseCamp-Ziel: `C:\ProgramData\Garmin\Maps\` (Windows) bzw.
  `~/Library/Application Support/Garmin/Maps/` (macOS). Kein unsignierter Installer, weil
  SmartScreen sonst warnt.

## Quellstand

- Je Datensatz: Name, Ausgabe und Bezugsdatum aus den STAC-Metadaten.
- Gross auf Website und in der README:
  - Vektorkarte: swissTLM3D, swissNAMES3D, amtliches Gebäudeadress- und Strassenverzeichnis.
  - Pixelkarte: Swiss Map Raster je Massstab (Ausgabe bzw. Spanne der Ausgabejahre).
- Im Kleingedruckten: swissALTI3D, SMV25-Höhenkurven und -Koten, swissBOUNDARIES3D, SchweizMobil-Routen.
- Die Pipeline schreibt den Quellstand nach `QUELLSTAND`, in die README, in die Kartenbeschreibung und
  als `sources` in `manifest.json`.

## Lizenzangaben in jeder Datei

- **Vektor-IMG:** `--copyright-file` mit `©swisstopo` und `Bundesamt für Strassen, Kanton, Stiftung
  SchweizMobil` (mit Kanuland zusätzlich `Stiftung SchweizMobil`). `--license-file` mit dem vollen
  Lizenztext und dem Hinweis „inoffiziell“. Die Beschreibung enthält `©swisstopo`.
- **Raster-IMG:** TRE-Copyright mit `©swisstopo` und dem Kartenwerk, Kartenname und Beschreibung mit
  `©swisstopo`, volle Lizenzzeile in TDB bzw. gmapi und in der README.

Prüfungen vor jedem Release:
- Copyright-Strings vorhanden, kein OSM/ODbL-Text, Umlaute korrekt (cp1252).
- `manifest.json` vollständig.
- `python3 -I src/portal/build_data.py --check`.
- Lizenzvorgaben: [lizenzen.md](../daten/lizenzen.md).

## Offen

- Gerätetest der Schweiz-Dateien: Pixel 50-1000 (optimierte Huffman-Tabellen), 25-1000 (GMPs bis 16,4 MB),
  10-1000 und Luftbild kompakt.
- Luftbild detail: Gerätetest (Ladezeit, Stufen 24 bis 22 über kompakt).
