# JNX (BirdsEye-Raster)

Stand: 2026-11-04. Status: **verworfen**. Code: `src/raster_img/jnx.py` (Writer und Rückleser, als
Dokumentation erhalten).

Unsignierte JNX behandelt die Garmin-Firmware als Demo-Karte. Eine Demo-Karte darf höchstens
ca. 1 km² abdecken. Eine öffentliche Karte ist damit nicht möglich. Helvetopo baut keine
JNX-Dateien. Der Signaturmechanismus wird weder nachgebaut noch umgangen.

## Befund am GPSMAP 67

| Datei | Fläche | Ergebnis |
|---|---|---|
| Version 3, 1 Level, 2 × 2 Kacheln SMR25 | 0,29 km² | angezeigt |
| Version 3, 2 Levels, 126 + 504 Kacheln | 36,5 km² | „Ungültige Satellitendaten“, auch als einzige Datei |

- „Ungültige Satellitendaten“ ist laut Global Mapper eine Lizenzmeldung, kein Formatfehler.
- Version 3 mit Seriennummer 0 und ohne Signatur wird angenommen, solange die Fläche unter der
  Demo-Grenze liegt.
- Weitere Grenzen laut Recherche: 5 Levels, 50 000 Kacheln je Level, 250 JNX-Dateien je Gerät.
  Auch die Zahl gleichzeitig angezeigter Demo-Karten ist begrenzt.

## Format

Keine offizielle Spezifikation. Grundlage sind offene Implementierungen (kein Code übernommen):
QMapShack (`qmt_map2jnx/main.cpp`, `map/CMapJNX.cpp`), ImageMagick (`coders/jnx.c`), SAS.Planet
(`Includes/JNXlib.pas`).

Alle Zahlen Little Endian. Koordinaten int32 in Grad × 0x7FFFFFFF / 180.

| Offset | Typ | Feld |
|---|---|---|
| 0x00 | u32 | Version (3 oder 4) |
| 0x04 | u32 | Geräte-ID (0 = Demo) |
| 0x08 | i32 × 4 | Grenzen N, E, S, W |
| 0x18 | u32 | Anzahl Levels |
| 0x1C | u32 | Ablaufdatum |
| 0x20 | u32 | Produkt-ID |
| 0x24 | u32 | CRC |
| 0x28 | u32 | Signaturversion |
| 0x2C | u32 | Signatur-Offset |
| 0x30 | u32 | Z-Order (nur Version 4) |

- Je Level: Kachelzahl (u32), Offset der Kacheltabelle (u32), Massstab (u32). Version 4 zusätzlich
  ein u32 und ein Copyright-String.
- Metablock: u32 9, GUID, Produktname „BirdsEye“, 0x00 und u16 Produkt-ID, Kartenname, Levelzahl, je
  Level Name, Beschreibung, Copyright (UTF-8) und Zoom. Die Zoomwerte je Level müssen verschieden sein.
- Kacheltabelle: je Kachel 28 Byte (N, E, S, W als i32, Breite und Höhe u16, Grösse und Offset u32).
- Bilder: Baseline-JPEG ohne die ersten zwei Bytes (FF D8).
- Endmarke `BirdsEye` direkt nach dem letzten Bild. Keine Prüfsumme.
- Massstab je Level wie qmt_map2jnx: 76437 · 2^round(log2(m/px · 1302,084 / 76437)). SMR25 ergibt 1194,
  SMR50 2388.

Eine signierte BirdsEye-Datei hat zusätzlich Seriennummer, Ablaufdatum, CRC, eine Signaturversion und
einen Signaturblock hinter der Kacheltabelle.

## Werkzeug

```bash
python3 -I src/raster_img/jnx.py --check <datei.jnx>
```

Liest Kopf, Levels, Metablock und jede Kachel (SOI voranstellen, JPEG dekodieren, Grösse prüfen,
Grenzen, Endmarke).

## Quellen

- Whiter, „JNX Raster Maps“: <http://web.archive.org/web/2015/http://whiter.brinkster.net/en/JNX.shtml>
- Global-Mapper-Forum, Diskussion 6241: <https://www.globalmapperforum.com/discussion/6241/jnx-file-format/p2>
- QMapShack: <https://github.com/Maproom/qmapshack>
- SAS.Planet: <https://github.com/sasgis/sas.planet.src>
