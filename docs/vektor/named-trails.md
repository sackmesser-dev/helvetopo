# Named Trail Database (`Garmin/SQL/*.db`)

Stand: 2026-11-04. Status: Analyse. Nicht umgesetzt.

Garmin-Topokarten können neben der IMG eine SQLite-Datei `Garmin/SQL/<Teilenummer>.db` enthalten.
Sie ordnet Routennamen den routingfähigen Linien der IMG zu. Damit funktionieren die Suche
„Wohin? > Trails“ auf dem Gerät und „Named Trails“ in BaseCamp. Eine Spezifikation gibt es nicht.
Das Format unten ist an Referenzdateien kommerzieller Garmin-Topokarten ermittelt (nur lesend).

## Format

### Tabellen

```sql
trails(id INTEGER PRIMARY KEY, name TEXT, description TEXT, difficult INTEGER, color INTEGER,
       icon BLOB, min_lat INTEGER, min_lon INTEGER, max_lat INTEGER, max_lon INTEGER)
trail_segs(dbg_line_id int, map_id int, link_id int, trail_id int, org_node_id int, dst_node_id int,
           org_pnt_lat int, org_pnt_lon int, dst_pnt_lat int, dst_pnt_lon int)
garmin_metadata(_id INTEGER PRIMARY KEY, part_number TEXT, database_class INTEGER, version INTEGER,
                description TEXT, copyright TEXT, schema_version INTEGER, create_timestamp TEXT ...)
```

Indizes: `trail_id_bbox`, `adj_index` (map_id, link_id, org_node_id, dst_node_id), `trails_bbox`.
`garmin_metadata`: `database_class = 13`, `description = "Named Trail Database"`, `schema_version = 1`.

| Feld | Bedeutung |
|---|---|
| `trails.name` | Routenname. `description`, `difficult` und `color` sind in den Referenzdateien leer. `icon` ist ein BLOB von 529 Byte. |
| Koordinaten | 32-Bit-Semicircles: `grad = wert * 180 / 2^31` |
| `map_id` | 8-stellige Kachelnummer der IMG, dezimal |
| `link_id` | Byte-Offset des Strassen-Datensatzes im NET-Block der Kachel (NT-NET-Header +0x43/+0x47) |
| `org_node_id`, `dst_node_id` | Byte-Offset des Routing-Knotens im NOD-Block (NT-NOD-Header +0x67/+0x6b). `-1` steht für ein Linienende ohne Routing-Knoten **(unsicher)**. |
| Segment | ein Eintrag je Teilstück zwischen zwei Knoten. Eine Strasse kann mehreren Routen angehören. |
| `dbg_line_id` | interne Kennung, für das Gerät ohne Bedeutung **(unsicher)** |

Belege aus allen Kacheln einer Referenzkarte:

- Der grösste `link_id` liegt bei 97,6–100 % der Länge des NET-Strassenblocks.
- Der grösste Knoten-Offset liegt bei 97,2–99,9 % des NOD-Blocks.

### Verknüpfung DB ↔ IMG

Der Dateiname der DB ist die Teilenummer. Sie steht im Header des IMG-Containers ab Offset `0x30`
in 9 Bytes. Kodierung:

- 12 Zeichen zu je 6 Bit, Zeichen = Wert + 0x20
- Das erste Zeichen steht in den höchsten Bits einer Little-Endian-Zahl. Dieselbe Kodierung beschreibt Oppmann für GCD-Firmwaredateien.

```python
def encode_part_number(pn: str) -> bytes:      # "006-D6603-01" -> 11d44c9065918d0541
    n = 0
    for ch in pn:                              # genau 12 Zeichen, ASCII 0x20–0x5F
        n = (n << 6) | (ord(ch) - 0x20)
    return n.to_bytes(9, "little")
```

- In allen Referenzkarten entspricht der dekodierte Header dem Dateinamen der DB.
- `garmin_metadata.part_number` kann vom Dateinamen abweichen. Massgebend ist der Dateiname.
- mkgmap schreibt an `0x30` Nullen und hat keine Option für eine Teilenummer.

### Ablage und Geräte (laut Foren, nicht geprüft)

- Die IMG liegt in `Garmin\`, die DB in `Garmin\SQL\`.
- Die DB dient nur der Suche. Die Hervorhebung der Routen kommt aus IMG und TYP.
- Montana, Monterra, GPSMAP 62/64, Oregon 6xx und Edge 810/1000 unterstützen die Funktion. Für
  GPSMAP 66/67 und Montana 7xx gibt es keine Angaben.
- BaseCamp zeigt „Named Trails“ nur mit einer DB auf dem Gerät bzw. der Speicherkarte.

## Umsetzung für Helvetopo (Plan)

1. Zielkarte ist die Basiskarte 7701. Nur sie hat NET und NOD. Die Zuordnung Route ↔ swissTLM3D-Kante
   liefert `src/routes/match_tlm.py` (siehe [routen.md](routen.md)).
2. Teilenummer nach dem Build in die 9 Bytes bei `0x30` schreiben. Die Nummer folgt Garmins Muster
   und kollidiert mit keinem Garmin-Produkt, z. B. `999-S7701-00`.
3. Offsets aus der fertigen IMG lesen: je Routensegment `map_id`, NET1-Offset der Strasse und
   NOD1-Offsets der beiden Knoten. mkgmap gibt diese Werte nicht aus. Das klassische Format
   (Nicht-NT) ist in mkgmap, `display` und imgdecode beschrieben.
4. DB mit `sqlite3` schreiben. Schema wie oben. Routennamen aus den SchweizMobil-Daten (als Attribut
   erlaubt). Generisches Icon ohne SchweizMobil-Logo.

Minimaltest vor dem Bau: eine Kachel des Testgebiets, einige Routen, DB von Hand, Teilenummer
gesetzt, zwei Varianten von `link_id` (roher Offset bzw. um `net-shift` verschoben). Zuerst auf dem Gerät.

## Offene Fragen

- Alle Referenzkarten sind NT-Karten (GMP). Ob die Firmware die Trail-Suche für Nicht-NT-Karten von
  mkgmap anbietet, ist unbekannt.
- Ob `link_id` im Nicht-NT-Format der rohe Byte-Offset oder der verschobene Wert ist, klärt nur
  der Gerätetest.
- Ob GPSMAP 66/67 und Montana 7xx die Funktion haben, ist unbekannt.
- Ob das Gerät eine frei gewählte Teilenummer annimmt, ist unbekannt.

## Quellen

- [pinns.co.uk – Active Routing On Garmin](https://www.pinns.co.uk/osm/activerouting.html)
- [GPSPower – ActiveRouting .db file, general discussion](https://www.gpspower.net/garmin-discussions/276556-activerouting-db-file-general-discussion-print.html)
- [GPSPower – Data in SQL (.db) files](https://www.gpspower.net/garmin-discussions/274319-data-sql-db-files.html)
- [Oppmann – Garmin GCD Format](https://www.memotech.franken.de/FileFormats/Garmin_GCD_Format.pdf)
- [Oppmann – Garmin IMG Subfiles Format](https://www.memotech.franken.de/FileFormats/Garmin_IMG_Subfiles_Format.pdf)
