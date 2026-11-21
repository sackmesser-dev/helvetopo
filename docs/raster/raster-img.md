# Raster-IMG: Swiss Map Raster als Garmin-IMG

Stand: 2026-11-08. Code: `src/raster_img/`. FIDs: 7704 (50-1000), 7705 (25-1000), 7706 (10-1000).
Die Luftbild-Karte (FID 7707) nutzt denselben Encoder, siehe [luftbild.md](luftbild.md).

Der Encoder baut aus Swiss Map Raster eine Garmin-IMG mit eingebetteten JPEG-Bildern. Vorbild ist
die kommerzielle Karte „Topo Schweiz v3 Rastermap“ (2015). Ihr Format wurde nur lesend mit eigenen
Werkzeugen (`imgread.py`, `inspect_img.py`) analysiert und mit den Decodern von GarminImg
(kiozen/GarminImg) und GPXSee gegengelesen. Aus der Referenzkarte steht nichts im Repo.

Die Raster-IMG läuft auf dem GPSMAP 67, in BaseCamp 4.7.5 (als gmapi) und in GPXSee.

## Format

Eine Raster-IMG ist eine normale NT-Karte. Jede Kachel ist eine GMP-Subdatei mit TRE, RGN und LBL.
- Die JPEG-Bilder liegen in LBL: LBL29 enthält alle JPEGs hintereinander, LBL28 die Offset-Tabelle
  (4 Byte je Bild).
- Ein erweitertes Polygon Typ 0x10613 in RGN2 referenziert je ein Bild. Seine Zusatzdaten enthalten
  den Bildindex, die Grenzen N/E/S/W und die JPEG-Grösse.
- Ein Abdeckungspolygon Typ 0x10d01 liegt je Subdivision.
- Keine NET, NOD, DEM, TYP, MDR. Kein Routing, keine Suche.

### Container (`DSKIMG`/`GARMIN`)

| Feld | Wert |
|---|---|
| XOR-Byte | 0 |
| Blockgrösse | 2^(9+7) = 64 KiB (Header 0x61/0x62 = 09 07) |
| FAT-Beginn | 0x1000 (Byte 0x40 = 08) |
| Subdateien | `GMAPPROM.MPS` und die GMP-Dateien |
| Partitionstabelle 0x1BE | Ende 0x55AA |

- FAT-Eintrag (512 Byte): Flag 01, Name 8 Zeichen, Erweiterung 3 Zeichen, Grösse u32 (0x0C), Teil u16
  (0x10), Blockliste ab 0x20 (240 × u16, 0xFFFF = leer). Eine GMP braucht keine Folgeeinträge.
- Die IMG ist auf 4 GiB begrenzt (65 535 Blöcke zu 64 KiB). Das ist auch die FAT32-Grenze am Gerät.
- Die Referenzkarte setzt im Kopf weitere Felder (0x0F, 0x24–0x27, 0x83–0x87, Blockzahl 0xFFFF,
  maximale CHS-Angabe). Ihre Bedeutung ist unbekannt. Der Encoder lässt sie auf 0. Das Gerät
  braucht sie nicht.

### `GMAPPROM.MPS`

- Ein `F`-Record: Produkt, Family, Serienname.
- Je Kachel ein `L`-Record (52 Byte): Produkt u16, Family u16, Kartennummer u32 = 0, Serienname\0,
  Beschreibung = GMP-Name\0, Gebietsname\0, Hex-Kartennummer u32 = TRE-Map-ID, 0 u32.
- Kein `P`-Record. mkgmap schreibt stattdessen `MAKEGMAP.MPS`. Das Gerät nimmt beide Namen an.

### GMP-Kachel

| Offset | Inhalt |
|---|---|
| 0x000 | GMP-Header 0x35 Byte: `GARMIN GMP`, 01, Sperr-Flag 0, Datum, Offsets TRE, RGN, LBL, NET=0, NOD=0, DEM=0 |
| 0x035 | Freitext (Copyright), nicht referenziert |
| 0x0E8 | TRE-Header 0x111 Byte |
| | Freitext |
| | RGN-Header 0x7D Byte |
| | LBL-Header 0x210 Byte |
| | Daten: TRE3, TRE2, TRE1, TRE8, TRE7, RGN2, RGN5, LBL12, LBL1, LBL16, LBL21, LBL28, LBL29, TRE9 |

Alle Offsets sind relativ zum GMP-Anfang.

### TRE

- Grenzen N/E/S/W als 24-Bit-Werte (Grad × 2^24 / 360).
- Die oberste Ebene ist vererbt und leer (Flag 0x80).
- Subdivisions: Breite und Höhe sind die halbe Ausdehnung in verschobenen Einheiten
  (`>> (24 − bits)`). Bit 15 der Breite markiert die letzte Subdivision einer Gruppe. Objekt-Flags 0,
  RGN-Offset 0. Nach TRE2 folgen 4 Byte 0. Die Breite ist auf 15 Bit begrenzt.
- Feinste Ebene (bits 24) mit zwei Subdivisions: Die erste hat Mitte und Halbbreite der linken
  Hälfte. Die letzte hat **Mitte und Ausdehnung der ganzen Kachel**. Mit nur der rechten Hälfte
  verschwindet das Raster am Gerät auf der feinsten Ebene.
- TRE7 (erweiterte Objekte, Record 4 Byte = Polygon-Offset, Flags bei 0x86 = 1): ein Eintrag je
  Subdivision **ohne** die vererbte oberste Ebene, plus ein Endeintrag.
- TRE8: Typliste, je Typ 3 Byte (Typ, höchste Ebene, Subtyp), z. B. `06 03 13` und `0d 05 01`.
- Map-ID bei 0x74, Kartennummer bei 0xCF, POI-Flags 0x3F = 01.
- Zeichenpriorität bei 0x40: Die Referenzkarte hat 31. Die Release-Dateien haben 29 (`release.RASTER_PRIORITY`),
  damit die Routen darüber liegen (siehe „Routen über Pixelkarte und Luftbild“).
- Schlüssel bei 0x9A (16 Byte) nach mkgmap `MapValues` aus Map-ID und Headerlänge. Bei Headerlänge
  ≥ 0x100 geht zusätzlich `len >> 8` in das zweite Nibble des zweiten Werts ein
  (`src/raster_img/keygen.py`).
- TRE9: 5 Byte am Dateiende. Ihre Bedeutung ist unbekannt. Man kann sie aus dem Schlüssel k
  ableiten (mod 16, `rasterimg.tre9_bytes`):
  - t9[0] = k[8] + (7, 3)
  - t9[1] = k[9] + (0, 5)
  - t9[2] = k[10] + (0, 1)
  - t9[3] = k[11]
  - t9[4] = k[8]

### RGN

- Header 0x7D: RGN1 leer, RGN2 = erweiterte Polygone, RGN3/RGN4 leer, RGN5 = Huffman-Tabelle.
  Info-Wert 0x79 = 0xE5 bei Huffman.
- Drei 20-Byte-Blöcke nach den Offsets (0x25, 0x41, 0x5D) sind Feldmasken.

Rasterpolygon (Typ 0x06, Subtyp-Byte 0xB3 = 0x13 | 0x20 Label | 0x80 Zusatzdaten):

| Feld | Byte |
|---|---|
| Typ, Subtyp mit Flags | 2 |
| Δlon, Δlat der SW-Ecke relativ zur Subdivision | 2 + 2 |
| Bitstream-Länge (variabel), Bitstream | 1 + n |
| Label (LBL1-Offset) | 3 |
| `E0`, Länge der Zusatzdaten | 2 |
| Bildindex, Breite = byteSize(Bildanzahl − 1) | 1 bei bis 256 Bildern |
| N, E, S, W als int32 (24-Bit-Wert << 8) | 16 |
| JPEG-Grösse u32 | 4 |

- Die Indexbreite muss byteSize(Bildanzahl − 1) sein. GarminImg schreibt immer 2 Byte. Leser lesen
  dann Index und Grenzen um ein Byte verschoben, und das Raster erscheint nicht.
- Die Referenzkarte gibt jedem Bild ein eigenes Label. Der Encoder schreibt ebenfalls je Bild ein
  eigenes Label („©swisstopo 1“ usw., Option `unique_tile_labels`).
- Das Abdeckungspolygon 0x10d01 (ohne Label und Zusatzdaten) liegt auf der feinsten Ebene nur in der
  letzten Subdivision (Option `coverage_bottom_last`).

### LBL

- Header 0x210 Byte, plus ein Abschnitt bei 0x200.
- Codierung 0x1E: 11 = Huffman (Tabelle in RGN5), 9 = 8 Bit. Codepage 1252.
- LBL12: „Western European Sort“.
- LBL21 (256 × 3 Byte): Wörterbuchtabelle der Huffman-Textkodierung. Ein Eintrag ≠ 0 ersetzt das
  Zeichen durch ein anderes Label. Der Encoder schreibt eine Nulltabelle.
- LBL28: Offset-Tabelle, rec 4, aufsteigend, danach 4 Byte 0.
- LBL29: alle JPEGs hintereinander.
- JPEG: JFIF 1.01, Baseline, RGB als YCbCr 4:2:0, Standard-Huffmantabellen.
- Projektion plate carrée: gleiche Grad je Pixel in Länge und Breite.

### Huffman (RGN5)

`src/raster_img/huffman.py`, Format nach GPXSee (`huffmantable.cpp`, `huffmanstream.h`).
- RGN5 ist eine Folge von Records. Record 0 = Texttabelle (8 Bit je Symbol), Record 1 =
  Koordinatentabelle (32 Bit je Symbol). Info 0xE5 → Koordinatentabelle ist Record
  ((0xE5 >> 1) & 0xF) − 1 = 1.
- Tabellenkopf: Byte 0 = ACL-Bits | 0x10, Byte 1 = längster Code, Byte 2 = Einträge der
  Suchtabelle, Byte 3 = Bits je Symbol, dann die Symbolanzahl (variabel).
- Kanonische Codes in Garmin-Anordnung: Die längsten Codes haben die kleinsten Werte. Null-Füllbits
  am Streamende bilden deshalb nie einen Code.
- Bitstreams MSB zuerst. Polygon: 1 Bit 0, dann je Delta |d| und bei d ≠ 0 ein Vorzeichenbit.
  Rasterpolygone: SW-Startpunkt plus drei Deltas (SE, NE, NW).

BaseCamp und GPXSee brauchen Huffman nicht. Der Encoder kann beides (`GmpOptions(huffman=True)`).

## Aufbau der Release-Dateien

`src/raster_img/release.py` baut die Release-Varianten.

Jede IMG enthält zwei Serien von GMPs, wie die Referenzkarte. Beide Serien haben dieselbe Level-Menge 17 (leer)
bis 24 und auf jeder Ebene mindestens ein Objekt.

| Serie | Zelle | Bilder | übrige Ebenen | Map-IDs |
|---|---|---|---|---|
| fein | 10 × 10 Bilder des feinsten Massstabs (0,1176° bzw. 0,0588°) | 24 bis 21 | 20 bis 18: nur Abdeckungspolygon | `<FID>0001`–`<FID>7999` |
| grob | 0,2352° (`release.COARSE_CELL`) | 20 bis 18 | 24 bis 21: Raster-Polygone ohne Bild | `<FID>8001`– |

- Bei grobem Zoom liest das Gerät die Bilder nur aus wenigen grossen GMPs. Vorher trug jede kleine Zelle alle
  Stufen, und das Gerät dekodierte bei 2 bis 8 km viele winzige Bilder. Das war sehr träge (Gerätetest 5).
- Raster-Polygone ohne Bild: Typ 0x06, Subtyp 0x33 (0x13 mit Label, ohne Zusatzdaten), je ein Polygon pro Bild
  der Ebene 20 (`GmpOptions.placeholder_bits`). Die grobe Serie der Referenz hat sie ebenso.
- Jede Ebene unter der obersten trägt das Abdeckungspolygon 0x10d01 (`coverage_levels` = 7).
- Gröbere Massstäbe sind kleinere Bilder, deren Kante die Zellkante teilt. Alle Bilder einer GMP liegen in
  derselben LBL29-Tabelle. Der Index hat 1 Byte, also höchstens 255 Bilder je GMP.
- Jede GMP liegt zwischen 512 KiB und 16 MiB (`rasterimg.GMP_MIN`, `rasterimg.GMP_MAX`). `build_gmp` füllt
  kleinere GMPs am Ende mit Nullbytes auf. Die Füllung ist nicht referenziert. Eine GMP über der Grenze bricht
  den Build ab. `write_img` und `build_img` prüfen beide Grenzen für jede GMP.
- mkgmap und Garmin erlauben höchstens 8 Levels. Die Ebenen mit Raster liegen lückenlos von bits 24 bis 18.
  `release.check_levels` bricht sonst ab. Das gilt auch für `luftbild.py`.
- Jedes Bild reicht 1 px weiter nach Osten und Süden (`smr_tiles.cut_tiles(overlap=…)`,
  `release.OVERLAP_PX = 1`). Ohne Überlappung mischt BaseCamp die Randpixel mit dem Hintergrund, und
  ein feines Kachelraster wird sichtbar. Kosten: ca. 2 % Grösse.
- Die Bildgrenzen stehen in Karteneinheiten von bits 24 (360°/2²⁴ = 2,1·10⁻⁵°, `rasterimg.deg2mu`). Ist ein
  Pixel kleiner als eine Einheit, rundet 1 px Überlappung oft auf 0 Einheiten:

  | Stufe | Pixel in Einheiten | Kanten mit 0 Einheiten Überlappung |
  |---|---|---|
  | Pixel 25-1000 und 50-1000, bits 24 | 1,07 | keine |
  | Pixel 10-1000, bits 24 | 0,54 | ca. 46 % |
  | Luftbild detail, bits 24 / 23 | 0,27 / 0,54 | ca. 71 % / 42 % |

- `release.overlap_px` verlangt darum zusätzlich mindestens `OVERLAP_MU` Einheiten. Das Luftbild nimmt
  2 Einheiten (`luftbild.OVERLAP_MU`): detail überlappt auf bits 24 / 23 / 22 um 8 / 4 / 2 px. Die
  Pixelkarten bleiben bei 1 px. `release.py --overlap-mu 2` baut sie mit 2 px (ca. 0,4 % grösser).
- Befund 2026-11-07 (BaseCamp, Mac): Pixel 25-1000 zeigt bei St. Gallen bei ca. 200 m feine Haarlinien an den
  Bildgrenzen. Luftbild kompakt zeigt am gleichen Ort keine Linien. Beide haben dieselbe Zelle, dieselben
  Bildgrössen (513 px) und dieselbe Überlappung in Einheiten. Mögliche Ursache: BaseCamp mischt die Randpixel
  jedes Bildes mit dem Hintergrund, und auf den flachen Farben der Karte ist das sichtbar, im Foto nicht
  **(unsicher)**. Test: `H1_ov1px` gegen `H2_ov2px` in `work/screenshots/haarlinien/`.

| Variante | FID | 24 | 23 | 22 | 21 | 20 | 19 | 18 |
|---|---|---|---|---|---|---|---|---|
| 50-1000 | 7704 | SMR50 | SMR50 | SMR50 | SMR100 | SMR200 | SMR500 | SMR1000 |
| 25-1000 | 7705 | SMR25 ½ | SMR25 ½ | SMR50 ½ | SMR100 | SMR200 | SMR500 | SMR1000 |
| 10-1000 | 7706 | SMR10 ½ | SMR25 ½ | SMR50 ½ | SMR100 | SMR200 | SMR500 | SMR1000 |

„½“ heisst halbe Auflösung. Die oberste Ebene 17 ist leer.

- Alle Varianten zeigen auf derselben Ebene denselben Massstab. Nur die Ebene 24 trägt den feinsten Massstab der
  Variante. Bei 25-1000 und 50-1000 füllt er auch die Ebenen bis 23 bzw. 22, mit denselben Bildern.
- Der Massstabswechsel ist auf *Kartendetail* „Normal“ abgestimmt. Dann erscheinen bei „120 m“ SMR25, „300 m“
  SMR50, „800 m“ SMR100, „1,2 km“ SMR200 und „2–3 km“ SMR500. SMR10 erscheint dann nur beim stärksten Zoom.
- Mit „Weniger“ wechselt das Gerät eine Stufe früher auf den gröberen Massstab, mit „Maximal“ eine Stufe später.
  Wer gröbere Bilder will, stellt *Kartendetail* niedriger.
- Bei 50-1000 liegt auf 22 dasselbe SMR50 wie auf 24. Eine eigene Fassung in halber Auflösung brachte eine GMP
  über 16 MiB.
- Der GMP-Zwischenspeicher trägt Level-Tabelle und Serie im Ordnernamen (`release.gmp_dir`). Eine geänderte
  Tabelle baut deshalb neu.

Die Varianten 25-1000 und 10-1000 speichern ihre feinen Massstäbe in halber Auflösung, wie die Referenzkarte „Topo
Schweiz v3 Raster“. Auf den Stufen 24 und 23 liegt SMR25 mit ca. 2,5 m/px, auf Stufe 22 SMR50 mit ca. 5 m/px.
Bei 10-1000 liegt SMR10 auf Stufe 24 mit ca. 1,3 m/px. Mit JPEG q75 sind die Dateien ca. 31 % (25-1000)
bzw. 34 % (10-1000) so gross wie mit voller Auflösung und q85. Die alten Fassungen bleiben als Varianten
`25-1000v` und `10-1000v` für Vergleiche erhalten.

Auflösung der Bilder:

| Ebene | Auflösung | Quelle |
|---|---|---|
| SMR10 | 0,6 m | 0,5 m |
| SMR25 | 1,15·10⁻⁵ °/px (ca. 1,25 m), volle Auflösung | |
| SMR1000 | 80 bzw. 160 m | |

Erkenntnisse aus den Gerätetests:
- GMPs mit Raster auf nur einer Ebene (eine Massstabsserie je GMP) bietet das GPSMAP 67 nicht als
  Karte an. Eine GMP mit eigenen Bildern je Ebene funktioniert über alle Zoomstufen.
- Die Zahl der Levels (7 oder 8) ändert in BaseCamp nichts.
- Fehlt zwischen bits 24 und der gröbsten Ebene mit Raster eine Ebene, zeigt das GPSMAP 67 bei diesem Zoom kein
  Bild. Beispiele: 10-1000 und Luftbild kompakt ohne Ebene 23 zeigen bei „200 m“ und „300 m“ nichts.
  50-1000 ohne Ebene 23 verschwand beim starken Zoom.
- 50-1000 mit lückenlosen Ebenen 24 bis 18 zeigt am Gerät diese Massstäbe:
  „≤ 300 m“ SMR50, „500–800 m“ SMR100, „1,2 km“ SMR200, „2–5 km“ SMR500. Ab „8 km“ kommt kein Bild mehr.
  SMR1000 auf Ebene 18 war bei keinem Zoom zu sehen.
- Eine IMG mit einer zusätzlichen Übersichts-GMP (Ebenen 17 bis 13, darüber leer 12) bot das GPSMAP 67 nicht
  als Karte an. Die Übersichts-GMPs waren nur 59 bis 140 KB gross. Wahrscheinliche Ursache ist deshalb die
  Mindestgrösse (siehe unten), nicht die Level-Menge. Ein Test mit aufgefüllter Übersichts-GMP fehlt.
- 50-1000 mit einer GMP von 16,9 MB bietet das GPSMAP 67 nicht an. Alle angebotenen Dateien haben GMPs unter
  16 MiB, die Referenzkarte höchstens 15,2 MB.
- Bei grobem Zoom wurde das Gerät sehr träge, solange jede kleine Zelle alle Stufen trug. Beispiele: Luftbild
  St. Gallen (Zelle 0,0294°) ca. 30 s bei „2 km“, Pixel 10-1000 ab „3 km“.
- Eine Ebene jenseits einer Lücke (Versuch mit SMR1000 auf 16 und Lücke 17–18) zeigt kein Bild.
- Die zwei Serien (Gerätetest 6) funktionieren bei den Pixelkarten. Die Karten sehen besser aus.
- Eine einzige GMP unter ca. 330 KB macht die ganze IMG ungültig. Das Gerät bietet sie dann nicht an. Details
  im nächsten Abschnitt.

### Mindestgrösse einer GMP

Das GPSMAP 67 bietet eine IMG nicht an, wenn eine ihrer GMPs zu klein ist. Die Grenze liegt zwischen 322 849
Byte (grösste abgelehnte GMP) und 479 075 Byte (kleinste angenommene GMP). Die Referenzkarte hat keine GMP unter
700 KB.

- Betroffen waren die Luftbild-IMGs aus Gerätetest 6. Ihre groben GMPs über Flächen mit wenig Bildinhalt
  (Bodensee, Rand des Kantons) hatten nur 65 bis 323 KB. Die Pixelkarten haben keine GMP unter 1,5 MB.
- Wahrscheinlich galt das auch für die Übersichts-GMP (59 bis 140 KB, Gerätetest 4).
- `build_gmp` füllt jede GMP unter 512 KiB (`rasterimg.GMP_MIN`) am Ende mit Nullbytes auf. Die Füllung ist
  nicht referenziert. Das Gerät bietet die aufgefüllte IMG an.
- `rasterimg.check_gmp_size` prüft jede GMP auf 512 KiB bis 16 MiB. `write_img`, `build_img` und
  `make_gmapi` brechen ausserhalb dieser Grenzen ab.

Testreihen (eine Datei je Variante, eigene FID, alle zusammen auf dem Gerät):

| Reihe | Variante | GMP | Ergebnis |
|---|---|---|---|
| 8b/8c | nur feine Serie, eine Serie wie Gerätetest 5 | ab 734 KB | angeboten |
| 8b/8c | nur grobe Serie, beide Serien, Testgebiet, Bildgrössen wie Pixel | eine GMP 65–323 KB | nicht angeboten |
| 8c | Testgebiet mit Bildgrössen wie Pixel, dazu mit Texten der Pixelkarte | ab 1,1 MB | angeboten |
| 8c | Pixel nur grobe Serie | ab 1,5 MB | angeboten |
| 8c | je eine grobe Zelle (8016, 8017, 8030, 8031, 8032) | 479–663 KB | angeboten |
| 8c | grobe Zelle 8018 | 323 KB | nicht angeboten |
| 8d | Zelle 8018: q75, Bilder ganz oder teilweise grau, neue FID | 56–323 KB | nicht angeboten |
| 8e | Zelle 8017 mit grauen Bildern, 8018 ohne Überlappung, Zelle 8019 | 56–311 KB | nicht angeboten |
| 8e | Zelle 8018 mit JPEG q95, Zelle 8018 mit Bildgrössen wie Pixel | 647 KB, 1,1 MB | angeboten |
| 9 | Zelle 8018 auf 512 KiB aufgefüllt | 512 KiB | angeboten |

Daraus folgt: Bildinhalt, JPEG-Format, Koordinaten, Map-ID und die Zahl der Karten auf dem Gerät sind nicht die
Ursache. Dieselbe Zelle mit demselben Aufbau wird angeboten, sobald ihre GMP gross genug ist.

### Zoomstufen

- bits 24 ist die feinste Ebene, die Garmin kennt. Feiner als SMR25 bzw. SMR10 auf bits 24 geht nicht.
- GPXSee wählt die Ebene mit den grössten bits, die nicht feiner als die Ansicht ist. Das GPSMAP 67 zeigt bei
  einer Lücke dagegen nichts (siehe Erkenntnisse oben).
- Eine Detailkachel hat 8 Levels: Raster lückenlos auf 24 bis 18, darüber die leere Ebene 17.
- Gröber als 18 zeigt die IMG nichts. Dort übernimmt die Basemap des Geräts.
- `overview.py` baut eine Übersichts-GMP für die Stufen 17 bis 13 (Option `--overview`, Standard aus). Am Gerät
  macht sie die IMG ungültig (siehe Erkenntnisse oben).
- Am Gerät verschiebt *Einstellungen → Karte → Kartendetail* die Wechsel: „Maximal“ zeigt feinere
  Ebenen eine Stufe früher, „Normal“ eine Stufe später. In BaseCamp gilt *Optionen → Karte → Detailgrad*.
- In BaseCamp erscheint die feinste Stufe ab ca. 700 m. Darunter vergrössert BaseCamp die feinste Stufe.

### Map-IDs

Fortlaufend `<FID>0001`–`<FID>8999` über alle Gitterzellen der Schweiz und Liechtensteins, je Serie
von fein nach grob. Eine Zelle hat in jeder Region dieselbe ID und denselben Inhalt. Regionen
derselben Variante teilen sich die FID ohne Konflikt.

| Variante | Zellen CH | ganze Schweiz (Hochrechnung) | Bauzeit |
|---|---|---|---|
| 50-1000 | 450 | 3,87 GB (q70, optimierte Huffman-Tabellen) | ca. 4 min |
| 25-1000 | 450 | ca. 5,3 GB (q75, halbe Auflösung) | ca. 6 min |
| 10-1000 | 1648 | ca. 15,5 GB (q75, halbe Auflösung) | ca. 20 min |

Jede Datei bleibt unter 4 GB. Grössere Varianten werden geteilt. Die Teile bestehen aus Regionen. Die Regionen sind
Kantonsgruppen aus `regions.REGIONS`. Eine Region umfasst alle Zellen, die ihr um 1 km gepuffertes
Gebiet berühren (swissBOUNDARIES3D). Die Ostschweiz enthält Liechtenstein.

### Teilung ohne Überlappung

Jede Gerätedatei bleibt unter 4 GiB. 50-1000 passt in eine Datei (3,60 GiB). 25-1000 kommt in Hälften, 10-1000
in vier Teile. Die Kantonsmasken allein überlappen an den Rändern. Dann käme dieselbe Map-ID in zwei
Dateien derselben FID vor.

- `release.partition_cells` teilt nach dem Gitter der groben Zellen (0,2352°). Jede grobe Zelle gehört mit
  allen ihren feinen Zellen zu genau einem Teil, und zwar zum Teil mit dem grössten Anteil an Maskenfläche.
- Die Teilungen stehen in `release.PARTITIONS`. `--region west` bzw. `--region ost` bauen bei 25-1000 die
  Hälften, bei 10-1000 die Teile West und Ost (`release.PARTITION_FOR`). `--region <Region> --disjoint` baut eine
  der neun Regionen ohne Überlappung.
- Die Hälften: West = genfersee, bern, nordwestschweiz, wallis. Ost = zuerich, ostschweiz, graubuenden,
  zentralschweiz, tessin.

| Hälfte | Zellen fein + grob | Landfläche CH/FL | 25-1000 |
|---|---|---|---|
| West | 198 + 58 | 18 603 km² | 2,41 GB |
| Ost | 252 + 72 | 22 848 km² | 3,24 GB |

Zusammen ergeben die Hälften genau die 41 451 km² von CH und FL. Acht Kantone liegen in beiden Hälften.
Am meisten Fläche in der anderen Hälfte haben Bern (620 km² in Ost) und Basel-Landschaft (173 km² in Ost).
Das Portal zeigt die Hälften deshalb als Karte und nicht nur als Kantonsliste.

10-1000 kommt seit 2026-11-08 in vier Teilen statt in neun Regionen. Ein Teil besteht aus ganzen Regionen
(`PARTITIONS["teile"]`, `PARTITION_BASE`). Jede grobe Zelle gehört zum Teil ihrer Region. Darum enthalten die Teile
genau dieselben Zellen und Map-IDs wie die Regionen. Neue Überlappungen gibt es nicht.

| Teil | Regionen | Zellen fein + grob | Landfläche CH/FL | Datei |
|---|---|---|---|---|
| West | genfersee, bern, nordwestschweiz | 542 + 41 | 13 968 km² | 3,996 GB (3,72 GiB) |
| Süd | wallis, tessin | 353 + 29 | 8488 km² | 3,518 GB (3,28 GiB) |
| Mitte | zuerich, zentralschweiz | 335 + 23 | 9011 km² | 2,836 GB (2,64 GiB) |
| Ost | ostschweiz, graubuenden | 417 + 37 | 9982 km² | 3,701 GB (3,45 GiB) |

- West liegt 299 MB unter der Grenze von 4 GiB (65 535 Blöcke zu 64 KiB). Alle GMPs liegen zwischen 1,23 und
  12,85 MiB, also innerhalb von 512 KiB bis 16 MiB.
- Die vier Dateien enthalten zusammen 1777 GMPs ohne doppelte Map-ID, gleich wie die neun Regionen.
- Die Kartennamen haben den Teil als Gebietsnamen, z. B. „Helvetopo Pixel 10-1000 2026-11 Süd“. Der Name steht
  auch im Kopf jeder GMP. Darum kann man die GMPs der Regionen nicht unverändert in die Teile übernehmen.
- Bau über die Netzfreigabe: ca. 2 h 45 min mit `--jobs 12` (Engpass Lesen der SMR-Blätter).
- Im Portal heissen die Teile `pixel10-west`, `pixel10-sued`, `pixel10-mitte` und `pixel10-ost`, weil `west` und
  `ost` schon die Hälften von 25-1000 sind.

Die neun Regionen ohne Überlappung (Bausteine der Teile):

| Region | Zellen fein | Landfläche CH/FL |
|---|---|---|
| genfersee | 156 | 3672 km² |
| bern | 278 | 7893 km² |
| nordwestschweiz | 108 | 2403 km² |
| wallis | 212 | 5100 km² |
| zuerich | 175 | 4329 km² |
| ostschweiz | 138 | 3442 km² |
| graubuenden | 279 | 6540 km² |
| zentralschweiz | 160 | 4682 km² |
| tessin | 141 | 3388 km² |

BaseCamp bekommt je Variante eine gmapi für die ganze Schweiz (`--region schweiz --gmapi-only`). Eine gmapi
hat keine 4-GiB-Grenze, und BaseCamp zeigt nur ein Produkt gleichzeitig.

### Aufruf

```bash
python3 -I src/raster_img/release.py --variant 25-1000 --region testgebiet --version 2026-11 --gmapi
```

Weitere Optionen: `--fid`, `--name`, `--file`, `--quality`, `--dry-run`. Ohne Angaben setzt
`release.py` FID, Kartennamen („Helvetopo Pixel 25-1000 2026-11“, bei Regionen mit Gebietsname) und
Dateinamen (`Helvetopo_Pixel_25-1000_Schweiz_2026-11`) nach dem Release-Plan. Die alten
Variantennamen (…-500) gelten als Alias. Fehlt für eine Zelle mit Land CH/FL das SMR10-Blatt, bricht
10-1000 ab. Eine Zelle nur im 1-km-Puffer ausserhalb der Grenze hat kein SMR10-Blatt und keinen Inhalt.
`release.py` lässt sie weg (Schweiz: eine Zelle bei 9,78° O / 46,27° N in Italien).

Die Region `testgebiet` ist die Kantonsmaske Ostschweiz, beschnitten auf 9,00–9,50° O / 47,20–47,50° N.

| Testgebiet | FID | GMP | IMG |
|---|---|---|---|
| `Helvetopo_Pixel_50-1000_Testgebiet_2026-11.img` | 7704 | 15 | 229 MB |
| `Helvetopo_Pixel_25-1000_Testgebiet_2026-11.img` | 7705 | 15 | 193 MB |
| `Helvetopo_Pixel_10-1000_Testgebiet_2026-11.img` | 7706 | 60 | 504 MB |

### Lizenz und Quellstand in der Datei

- TRE-Copyright je GMP: `©swisstopo`, je Massstab „Swiss Map Raster NN (Ausgaben JJJJ–JJJJ),
  swisstopo OGD“ und „<Kartenname>, inoffizielle Karte“.
- IMG-Beschreibung: Kartenname und `©swisstopo`. MPS-Serienname: Kartenname.
- `<Datei>_QUELLSTAND.txt`: je Massstab Blattzahl, Ausgabejahre im Gebiet, Auflösung,
  STAC-Collection, Lizenzzeile (`quellstand.py`).
- Datenquellen für den Quellstand: `downloads/smr/manifest.json` (STAC-`datetime` je Blatt),
  `downloads/smr/manifest_pk10.json`, `downloads/smr/manifest_stac_items.json` (SMR500, SMR1000).
- Die Release-Prüfung sucht nach den exakten Texten „OpenStreetMap“, „ODbL“ und „Open Database“.
  Eine Suche nach „odbl“ ohne Gross- und Kleinschreibung trifft Zufallsbytes in JPEG-Daten.

## gmapi für BaseCamp (`make_gmapi.py`)

BaseCamp erkennt eine IMG auf einem festen Laufwerk nicht als Gerät. Für BaseCamp entsteht deshalb
ein installierbarer Kartenordner:

```
<Name>.gmap/Info.xml                     MapProduct: Name, ID = Family-ID, BaseMap, TDB, Directory
<Name>.gmap/Product1/<FID>9000.tdb       TDB (Version 4.07)
<Name>.gmap/Product1/<FID>9000/…         Übersichtskarte (TRE/RGN/LBL, von mkgmap)
<Name>.gmap/Product1/<nr>/<nr>.GMP       je Kachel die unveränderte GMP
```

- `<nr>` ist die Map-ID aus TRE+0x74 (8-stellig dezimal).
- mkgmap erzeugt das TDB für Platzhalterkacheln mit gleicher Nummer und gleichen Grenzen. Danach wird
  jeder Detailblock (0x4C) auf eine Subdatei umgeschrieben: `u16 2, u16 1, u32 Grösse, u32 0xFF00C301,
  3 × 0, "<nr>.GMP\0"`. Der T-Block (0x54) enthält einen CRC32 über alle vorherigen TDB-Bytes, verteilt
  auf die Bytes 2, 9, 12 und 17. `make_gmapi.py` berechnet ihn neu.
- `--license-file` und `--copyright-file` sind Pflicht. Sonst schreibt mkgmap seinen OSM/ODbL-Text in
  TDB und Übersichtskarte, weil die Platzhalterkacheln aus OSM-XML entstehen.
- `--lower-case` erhält Gross- und Kleinschreibung.
- Ein eigenes TDB-Flag für Raster gibt es nicht.

## Routen über Pixelkarte und Luftbild (`routen.py`)

Die Pixelkarte und das Luftbild haben keine POIs und keine eigene Beschriftung. Wanderwege und
SchweizMobil-Routen kommen als transparente Vektorkacheln dazu. Quelle ist die Routen-PBF aus
`src/routes/convert_routes.py`.

- TYP: `src/style/typ/routes.txt` wie in der Vektorkarte, nur mit der FID der Zielfamilie. Die
  Linienbreiten sind deshalb gleich: 3 px für Wanderwege und Routen.
- Style: `src/style/routes` unverändert, wie in der Vektorkarte. Alle Routen und Wanderwege erscheinen
  ab Auflösung 21. Die einzige Quelle für die Stufen ist `src/routes/make_style.py` (`START_RES`).
- Damit verhalten sich Vektorkarte, Overlay 7702 und Pixel- bzw. Luftbild-gmapi gleich.

Zeichenreihenfolge (TRE 0x40, höhere Zahl liegt oben):

| Karte | Priorität |
|---|---|
| Vektor 7701 | 25 |
| Höhenlinien 7703 | 28 |
| Pixelkarte 7704–7706, Luftbild 7707 | 29 |
| Routen-Kacheln in der Vektor-Familie 7701 | 30 |
| Routen 7702 und Routen-Kacheln in Raster-Familien | 31 |

Die Referenzkarte nutzt 31 für das Raster. Höhere Werte als 31 sind nicht getestet. Deshalb liegt
das Raster bei 29 und die Routen bei 31. `release.py` und `luftbild.py` setzen 29 auch in GMPs aus
dem Zwischenspeicher.

### Gerät: eigenes Produkt „Helvetopo Routen“ (FID 7702)

- Datei: `Helvetopo_Routen_<Gebiet>_<Version>.img`, Kartenname „Helvetopo Routen 2026-11 Testgebiet“.
- Inhalt: gmapsupp-Aufbau mit Routen-Kacheln `77020001…`, TYP (FID 7702) und MPS. Transparent, Priorität 31.
- Die Datei liegt neben der Raster-IMG im Ordner `Garmin` des Geräts.
- Am Gerät erscheint sie als eigene Karte. Man schaltet sie deshalb unabhängig von der Pixelkarte ein und aus **(unsicher, Gerätetest offen)**.
- Testgebiet: 1 Kachel, 0,6 MB.

```bash
python3 -I src/raster_img/routen.py overlay --pbf work/raster_img/routen/routes.osm.pbf --region testgebiet --version 2026-11
```

### BaseCamp: Routen-Kacheln in der gmapi der Rasterkarte

BaseCamp zeigt nur ein Kartenprodukt gleichzeitig. Die Routen-Kacheln bekommen deshalb die FID der
Rasterkarte und kommen in deren gmapi. Die Vektor-Familie 7701 nutzt dasselbe Verfahren mit `77011001…`.

- Map-IDs der Routen-Kacheln: `<FID>9001`–`<FID>9999`. `<FID>9000` ist die Übersicht.
- Ein Routen-PBF über 20 MB teilt `routen.build_tiles` mit splitter (`--max-nodes=1600000`). Als eine
  Kachel wäre die RGN der Schweiz grösser als 16 MiB. Die Schweiz ergibt 7 Kacheln, die grösste RGN hat 3,0 MB.
  Das gilt für die gmapi und für das Overlay 7702.
- mkgmap baut TDB und Übersicht aus Platzhaltern und Routen-Kacheln. Danach ersetzt
  `make_gmapi.py` nur die Raster-Platzhalter durch die GMPs.
- Die gmapi bekommt den Routen-TYP mit der FID der Rasterkarte (`routes_<FID>.typ`).
- In BaseCamp sind die Routen fest eingeschaltet. Wer sie nicht will, installiert die gmapi ohne `--routes`.
- Beide Fassungen haben dieselbe FID. Sie lassen sich deshalb nicht gleichzeitig installieren.

```bash
python3 -I src/raster_img/release.py --variant 25-1000 --region testgebiet --version 2026-11 --gmapi --routes work/raster_img/routen/routes.osm.pbf
python3 -I src/raster_img/release.py --variant 25-1000 --region schweiz --version 2026-11 --gmapi-only --routes work/routes-ch/routes.osm.pbf
python3 -I src/raster_img/luftbild.py --region testgebiet --version 2026-11 --gmapi --routes work/raster_img/routen/routes.osm.pbf
python3 -I src/raster_img/routen.py gmapi --img <raster.img> --fid 7705 --name "<Kartenname>" --copyright "©swisstopo"
```

### Lizenz bei Routen

- Copyright der Routen-Kacheln, beide Zeilen: „©swisstopo“ und „Bundesamt für Strassen, Kanton, Stiftung SchweizMobil“.
- TDB der Raster-gmapi mit Routen: Zeile 1 `©swisstopo`, Zeile 2 mit derselben Doppelangabe, danach die Raster-Zeilen.
- Der Lizenztext nennt swissTLM3D Wanderwege (OGD) und die ASTRA-Layer (Opendata BY).
- `<Datei>_QUELLSTAND.txt` des Overlays nennt beide Quellen. Kanuland erscheint nur, wenn es in der PBF steckt.
- Prüfung: `REQUIRE_ASTRA=yes src/build/check_license.sh <Ordner>`. Das Skript prüft auch Release-IMGs (`Helvetopo_*.img`).

## Prüfwerkzeuge

- `inspect_img.py` liest wie GPXSee und meldet Inkonsistenzen.
- `imgread.py` liest IMG-Container und GMP-Strukturen.
- `estimate_ch.py` rechnet Grössen für die ganze Schweiz hoch.

## Unterschiede zur Referenzkarte

| Punkt | Referenzkarte | Encoder |
|---|---|---|
| Massstäbe | zwei Kachelserien (fein halbe SMR25-Auflösung, grob halbe davon) | eine GMP je Zelle mit allen Massstäben |
| Bilder je GMP | 35–203 | bis 255 |
| JPEG-Qualität | ca. q75 | q75 (25-1000, 10-1000), q70 mit optimierten Huffman-Tabellen (50-1000) |
| Huffman, TRE9, LBL16 | ja | optional |
| Freitexte | Garmin-Copyright | ©swisstopo, Hinweis „inoffiziell“ |

Das heutige SMR mit Relief und feiner Grafik komprimiert schlechter als die Landeskarte von 2015.

## Unterschiede zu GarminImg

GarminImg (2021–2024) erzeugt Dateien, die das Gerät listet, aber ohne Raster zeigt. Die Ursachen:
1. Bildindex immer 2 Byte.
2. TRE7 mit Eintrag für die vererbte oberste Ebene und ohne Endeintrag. Die Polygone landen in der
   nie gezeichneten Ebene.
3. Volle statt halbe Subdivision-Ausdehnung, nicht verschoben.
4. Ebenen bits 22–24, kein Abdeckungspolygon, keine 4 Endbytes nach TRE2.

## Bildinhalt

- Feine Linien im Kilometerabstand sind das km-Netz der Landeskarte, keine Kachelnaht.
- SMR10 setzt Ortsnamen gross und fett. Im ländlichen Raum wirkt die Karte deshalb ähnlich wie SMR25.

## Offene Punkte

- Ob das Gerät die Hälften West und Ost derselben FID zusammen und ohne Lücke an der Grenze zeigt.
- Ob das Gerät GMPs zwischen 15,2 und 16,4 MB annimmt (Schweiz-Build 25-1000: 22 GMPs). Getestet sind
  GMPs bis ca. 13,8 MB, abgelehnt wurde eine mit 16,89 MB.
- JPEG mit optimierten Huffman-Tabellen (50-1000) am Gerät. Die Referenz nutzt die Standardtabellen.
- Ladezeit beim Herauszoomen bei vielen GMP und Anzeige der Copyright-Zeilen am Gerät.
- SMR10 für die ganze Schweiz: ca. 400–470 GB Download.
- Routen-Overlay 7702 über der Raster-IMG am Gerät: Zeichenreihenfolge und einzelnes Ein- und Ausschalten.
- Routen-Kacheln in der Raster-gmapi: Darstellung in BaseCamp über Raster und Routen-TYP.
- Zwei Serien am Gerät: Ist der grobe Zoom schneller? Erscheint SMR1000 auf 18?
- Ob BaseCamp aufgefüllte GMPs liest.
- Ob die Übersichts-GMP mit Auffüllung am Gerät gültig ist.

## Quellen

- kiozen/GarminImg (GPL-3.0): <https://github.com/kiozen/GarminImg>
- GPXSee (GPL-3.0), `src/map/IMG/`: <https://github.com/tumic0/GPXSee>
- mkgmap-dev, „Embedding raster maps“:
  <https://lists.mkgmap.org.uk/archives/list/mkgmap-dev@lists.mkgmap.org.uk/thread/RMWNOYR7ZOUYQWC7C3E7N6DX3DVQCYMI>
