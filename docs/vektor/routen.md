# Routen: Wanderwege und SchweizMobil (FID 7702)

Stand: 2026-11-07. Code: `src/routes/`. Stil: `src/style/routes/`. TYP: `src/style/typ/routes.txt`.

Die Routen sind ein transparentes, nicht routendes Overlay. Es enthält das signalisierte
Wanderwegnetz aus swissTLM3D, die SchweizMobil-Routen, alle ÖV-Haltestellen und die POIs, die die
Landeskarte nicht zeigt. Im Gesamtbuild liegen sie in der Familie 7701 (siehe
[Einbau in die Gesamtkarte](#einbau-in-die-gesamtkarte)). Zusätzlich liefert `src/routes/` die
Zuordnung Route ↔ swissTLM3D-Kante für die Basiskarte.

## Eingabedaten

Alle Dateien liegen unter `downloads/`. Es gibt nur landesweite Dateien. Der Konverter schneidet
auf die BBox zu.

| Ordner | Datei | Quelle | Quellenangabe |
|---|---|---|---|
| `swisstlm3d-wanderwege/` | `SWISSTLM3D_WANDERWEGE.gpkg` (Tabelle `tlm_strassen_strasse`) | STAC `ch.swisstopo.swisstlm3d-wanderwege` | `©swisstopo` |
| `astra-wanderland/` | `wanderland_2056.gpkg`, `wanderland.zip` (Doku) | STAC `ch.astra.wanderland` | `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` |
| `astra-veloland/` | `veloland_2056.gpkg` | STAC `ch.astra.veloland` | wie oben |
| `astra-mountainbikeland/` | `mountainbikeland_2056.gpkg` | STAC `ch.astra.mountainbikeland` | wie oben |
| `astra-skatingland/` | `skatingland_2056.gpkg` | STAC `ch.astra.skatingland` | wie oben |
| `schweizmobil-kanuland/` | `kanu.gpkg` | `data.schweizmobil.ch/gpkg_export/kanu.gpkg` | `Stiftung SchweizMobil` |
| `swisstlm3d/` | `SWISSTLM3D_2026_LV95_LN02.gpkg` (Tabellen `tlm_oev_haltestelle`, `tlm_oev_eisenbahn`, `tlm_oev_uebrige_bahn`) | STAC `ch.swisstopo.swisstlm3d` | `©swisstopo` |

Felder:
- swissTLM3D Wanderwege: `wanderwege` als Text (`Wanderweg`, `Bergwanderweg`, `Alpinwanderweg`).
  Den Wert „andere“ gibt es im Download nicht. Weitere Felder: `objektart` (u. a. `Markierte Spur`),
  `kunstbaute`, `uuid`.
- SchweizMobil (MGDM Langsamverkehr): Tabelle `Route` (MultiLineString je Route und Richtung) mit
  `NrR`, `NameR`, `Typ_TR` (`national`, `regional`, `local`, bei Wanderland zusätzlich `handicap`),
  `LvArt`, `Richtung`, `Abwicklung`, `LVRoute_ID`. Die Tabelle `Weg` hat keine `TLM_ID` und keinen
  Routenbezug.
- swissTLM3D Haltestellen: `objektart` mit den Werten `Haltestelle Bahn`, `Haltestelle Bus`,
  `Haltestelle Schiff` und `Uebrige Bahnen` (Seil-, Stand- und Zahnradbahnen). Weitere Felder:
  `name`, `dienststellen_nummer`, `uuid`. Tramhalte haben die Objektart `Haltestelle Bahn`.
  Das Gleis in `tlm_oev_eisenbahn` hat dort `verkehrsmittel = Tram`.
- Die Routengeometrien folgen swissTLM3D, aber nicht stützpunktgenau (Median 0,4 m, 90 %-Quantil
  0,6 m Abstand). Ein Join über gleiche Koordinaten findet nichts.

## Aufruf

```bash
bash src/routes/build.sh            # Testgebiet → work/routes/
AREA=ch bash src/routes/build.sh    # ganze Schweiz → work/routes-ch/
```

`POIS=no` baut ohne POIs. Der POI-Schritt braucht das venv (`PYTHON`, Standard `.venv/bin/python` im
Haupt-Checkout).

Ausgabe: `77020001.img` usw. (Kacheln), `77020000.img` und `77020000.tdb` (Übersicht),
`gmapsupp.img` mit TYP, `routes.typ`, gmapi-Ordner, `tlm_routes.csv`.

| Schritt (ganze Schweiz) | Zeit | Speicher, Grösse |
|---|---|---|
| `convert_routes.py` (GPKG → OSM-XML) | 74 s | 3,4 GB RAM, 11,0 Mio. Knoten, 699 000 Wege |
| `osmium cat` → PBF | 11 s | 53 MB |
| splitter (`--max-nodes=1600000`) | ca. 10 s | 7 Kacheln |
| mkgmap (TYP, gmapsupp, gmapi) | 25 s | `gmapsupp.img` 17 MB |
| `match_tlm.py` | 78–114 s | 2,1 GB RAM, CSV 16 MB |

Inhalt landesweit: 318 573 Wanderweg-, 88 008 Bergwanderweg-, 2695 Alpinwanderweg-Linien.
Wanderland 97 327, Veloland 114 363, Mountainbikeland 71 729, Skatingland 6196, Kanuland 19
Linienstücke. Enthält die Karte Kanuland, ergänzt `build.sh` die Quellenangabe
`Stiftung SchweizMobil`.

## Konverter (`convert_routes.py`)

- Nur Python-Standardbibliothek: GPKG über `sqlite3`, eigener WKB-Parser, Vorselektion über den
  R-Tree der GPKG.
- LV95 → WGS84 mit `pyproj`. Ohne `pyproj` gelten die swisstopo-Näherungsformeln (ca. 1 m).
- Clipping je Segment auf die BBox (Liang-Barsky). Linien werden an der Box aufgetrennt.
  Informative Routenstücke im Ausland fallen weg.
- Bei getrenntem Hin- und Rückweg übernimmt der Konverter den Rückweg nur dort, wo er vom Hinweg
  abweicht (Kantenvergleich auf 0,1 m).
- Knoten mit gleicher Koordinate werden geteilt. So kann `--merge-lines` Stücke zusammenfügen.
- Haltestellen: Der Konverter übernimmt alle Objektarten. `Haltestelle Bahn` teilt er in Bahnhof
  und Tramhalt. Ein Halt ist ein Tramhalt, wenn im Umkreis von 25 m nur Gleise mit
  `verkehrsmittel = Tram` liegen (`TRAM_RADIUS_M`).
- Haltekanten mit gleicher Art und gleichem Namen im Abstand bis 150 m fasst der Konverter zu einem
  Punkt zusammen (`STOP_MERGE_M`).
- Seilbahnstationen: Für Luftseil-, Gondel-, Sessel- und Standseilbahnen und Skilifte aus
  `tlm_oev_uebrige_bahn` setzt der Konverter je eine Tal- und Bergstation an die Linienenden. Die
  tiefere Station ist die Talstation. Er lässt Bahnen ausser Betrieb weg. Er lässt ein Ende weg,
  wenn im Umkreis von 80 m eine Haltestelle `Uebrige Bahnen` liegt (`AERIAL_HALT_M`). Mit `--skip haltestellen` fallen die Haltestellen weg.

Jede Route ist eine eigene Linie mit Routentags, keine `type=route`-Relation:
1. Die SchweizMobil-Daten liefern die Route als fertige Geometrie.
2. mkgmap zeichnet Relationen nur über die Mitgliedswege. Mehrere Routen auf einem Weg bräuchten
   Kopien im Stil.
3. Jede Route braucht einen eigenen Linientyp im IMG.

### Tags

| Tag | Werte | Herkunft |
|---|---|---|
| `ch:wanderweg` | `wanderweg`, `bergwanderweg`, `alpinwanderweg` | TLM `wanderwege` |
| `sac_scale` | `hiking`, `mountain_hiking`, `alpine_hiking` | abgeleitet |
| `ch:markierte_spur` | `yes` | TLM `objektart` |
| `tunnel`, `bridge` | `yes` | TLM `kunstbaute` |
| `ch:tlm_uuid` | UUID ohne Klammern | TLM `uuid` |
| `ch:route` | `wanderland`, `veloland`, `mountainbikeland`, `skatingland`, `kanuland` | Datensatz |
| `ch:network` | `national`, `regional`, `local`, `handicap` | `Typ_TR` |
| `route` | `hiking`, `bicycle`, `mtb`, `inline_skates`, `canoe` | Datensatz |
| `network` | `nwn`/`rwn`/`lwn`, `ncn`/`rcn`/`lcn` usw. | `Typ_TR` |
| `ref`, `name` | Routennummer, Routenname | `NrR`, `NameR` |
| `ch:lvroute_id` | Zahl | `LVRoute_ID` |
| `ch:abwicklung` | `rueckweg` | abweichende Rückweg-Stücke |
| `ch:richtung` | `einseitig` | `Richtung` |
| `wheelchair` | `yes` | `Typ_TR = handicap` |
| `ch:oev` | `bahn`, `tram`, `bus`, `schiff`, `uebrige_bahn`, `seilbahn` (nur Punkte) | TLM `objektart`, Tram über das Gleis |
| `name`, `uic_ref` | Name der Haltestelle (erster Teil vor „\|“), Dienststellennummer | TLM `name`, `dienststellen_nummer` |
| `name`, `ele`, `ch:objektart` | Seilbahnstation: „<Bahn> Talstation“ bzw. „Bergstation“, Höhe, Bahnart | TLM `name`, Z, `objektart` |

## Darstellung

Grundsatz: Die Karte soll wie die Landeskarte aussehen. Die Routen sind ein Zusatz. Sie erscheinen
als feine Linie und sind in groben Stufen stärker aufgehellt. Jede Linie hat ab ihrer ersten Stufe
auf allen Stufen dieselbe Breite: 3 px für Wanderwege und Routen (Wunsch des Benutzers). Das gilt für
die Vektorkarte, das Overlay 7702 und die Routen in den Pixel- und Luftbild-gmapi, denn alle nutzen
denselben TYP und denselben Style.

Alle Routen (jedes Land, jedes Netz, auch hindernisfreie Wege) und alle Wanderwege erscheinen ab
Auflösung 21 (≈ 1:100 000). In 21 und 22 zeichnen die Übersichtstypen, ab 23 die Routentypen. Die
Routennummer im Schild kommt ab 22, der Routenname ab 24. Die Stufen stehen nur in
`src/routes/make_style.py` (`START_RES`, `COARSE_MAX`, `SHIELD_RES`, `NAME_RES`).

Warum 21: Velo, MTB, Skating und Kanu sollen nicht später einsetzen als Wanderland.
In 21 ist das Wanderwegnetz im Flachland dicht, aber die Routen heben sich noch klar ab. In 20 würde
das Netz die Karte zudecken.

Zoomstufen wie die Basiskarte: `levels = 0:24, 1:23, 2:22, 3:21, 4:20, 5:18`. Auflösung 24 und 23
≈ 1:25 000, 22 ≈ 1:50 000, 21 ≈ 1:100 000, 20 ≈ 1:200 000.

| Typ | Objekt | Darstellung | Auflösung |
|---|---|---|---|
| `0x10e00` | Wanderweg | 3 px, kurze Striche `#F2A900` auf Weiss (4/4 px) | ab 21 |
| `0x10e01` | Bergwanderweg | 3 px, kurze Striche `#C83C32` auf Weiss (4/4 px) | ab 21 |
| `0x10e02` | Alpinwanderweg | 3 px, kurze Striche `#2E6FC0` auf Weiss (4/4 px) | ab 21 |
| `0x10e18` | Wanderland und hindernisfreie Wege, Übersicht | 3 px, leicht aufgehellt `#268E4D` | 21–22 |
| `0x10e1a` | Veloland, Übersicht | 3 px `#415CA8` | 21–22 |
| `0x10e1b` | Mountainbikeland, Übersicht | 3 px gestrichelt `#D47D26` | 21–22 |
| `0x10e1c` | Skatingland, Übersicht | 3 px gepunktet `#A826D4` | 21–22 |
| `0x10e1d` | Kanuland, Übersicht | 3 px `#73CCCE` | 21–22 |
| `0x10e10` | Wanderland-Route | 3 px `#007A2E` | ab 23 |
| `0x10e11` | hindernisfreier Weg | 3 px `#007A2E` gestrichelt | ab 23 |
| `0x10e12` | Veloland-Route | 3 px `#1F3F99` | ab 23 |
| `0x10e13` | Mountainbikeland-Route | 3 px `#CC6600` gestrichelt | ab 23 |
| `0x10e14` | Skatingland-Route | 3 px `#9900CC` gepunktet | ab 23 |
| `0x10e15` | Kanuland-Route | 3 px `#33B5B8` | ab 23 |

Regeln:
- Die Farben stammen aus den Legenden der Bundes-Geodienste
  (`api3.geo.admin.ch/static/images/legends/<layer>_de.png`). Die Kanuland-Farbe ist eine Annahme,
  weil es keinen Bundes-Layer gibt. Die Wanderwegfarben sind gedämpft, damit sie nicht dominieren.
- Wanderland ist dunkelgrün `#007A2E`, nicht im Bundesgrün `#00A800` (Wunsch des Benutzers). Es hebt
  sich so vom Wald `#CDE6BE` ab (Kontrast 4,1 statt 1,9). Wanderland ist nah nicht und in der Übersicht
  nur zu 15 % aufgehellt.
- Veloland ist marineblau, nicht im Bundesblau `#0099FF`. Helles Blau sieht wie Gewässer aus
  (`#0088D0`). Velo, MTB und Skating sind nah nicht und in der Übersicht nur zu 15 % aufgehellt.
  Sonst ähneln sie Gewässern, Höhenkurven (`#D7963C`) und Grenzen (`#ECA8C8`).
- Übersichtslinien von Wanderland und Kanuland sind zu 45 % mit Weiss gemischt. Die TYP kennt keine
  Transparenz.
- Die feine Linie liegt mittig auf dem Weg. Eine seitlich versetzte Linie geht mit TYP-Bitmaps
  nicht: Der Versatz hängt von der Digitalisierrichtung ab.
- Liegen zwei Routen auf demselben Weg, ist nur die obere sichtbar. Das Strichmuster hilft bei der
  Unterscheidung.
- Eine TYP-Bitmap-Linie hat höchstens zwei Farben (eine darf transparent sein) und keinen Rand.
- Erweiterte Linientypen dürfen den Subtyp 0x1f nicht überschreiten.

### ÖV-Haltestellen

Punkttypen haben einen eigenen Nummernraum. `0x10e00` als Punkt kollidiert nicht mit der Linie
`0x10e00`. Auch bei Punkten darf der Subtyp 0x1f nicht überschreiten.

| Punkttyp | Objekt | Darstellung | Auflösung |
|---|---|---|---|
| `0x10e00` | Bushaltestelle | blauer Punkt `#1F66CC` mit weissem Rand, 13 px | ab 21 |
| `0x10e01` | Tramhaltestelle | wie Bus | ab 21 |
| `0x10e02` | Schiffstation | wie Bus | ab 21 |
| `0x10e03` | Seilbahn- oder Bergbahnstation, Skilift-Station | wie Bus | ab 21 |
| `0x10e04` | Bahnhof, Haltestelle Bahn | wie Bus, ohne sichtbares Label | ab 21 |

- Das Symbol ist 13 × 13 px gross mit 2 px weissem Rand (`SYMBOL_SIZE`, `RING_PX`). 7 px waren
  auf dem GPSMAP 67 kaum sichtbar.
- Der Name ist rot `#DD1919` wie bei den Bahnhöfen der Basiskarte (`NormalFont`, nachts `#FF6A6A`).
  Für Bushaltestellen gibt es keine swisstopo-Vorgabe. Rot ist eine Wahl.
- Name und Punkt stehen ab Auflösung 21 in der IMG. BaseCamp zeigt sie ab dieser Stufe. Das GPSMAP 67
  zeigt sie erst ab ca. 80 m, mit Namen. Bei 80 m ist genug Platz für die Namen. Gründe siehe
  [Punkttypen am GPSMAP 67](#punkttypen-am-gpsmap-67).
- Das GPSMAP 67 zeichnet die Schriftfarbe von Punkten nicht. Die Namen erscheinen dort schwarz,
  nur der blaue Punkt ist farbig. Die Farbe bleibt in der TYP für BaseCamp.
- Regeln in `src/style/routes/points` (von Hand gepflegt). Symbole und Farben in `make_typ.py`
  (`STOPS`, `STOP_DOT`, `STOP_LABEL_DAY`).
- Die Basiskarte zeigt nur die Bahnhöfe (Typ `0x2f08`, Name `#DD1919`, nur in Auflösung 24), wie die
  Landeskarte. Alle anderen Haltestellen und alle Seilbahnstationen zeigt nur das Overlay.
- Bahnhöfe stehen im Overlay mit `FontStyle=NoLabel`. Sonst stünde der Name am Bahnhof zweimal.
  Der Name bleibt im Suchindex, so findet die Suche alle Haltestellen.

### Punkttypen am GPSMAP 67

Das GPSMAP 67 hat für jeden Punkttyp eine eigene Zoomgrenze. Die Auflösung in der IMG legt nur fest,
ab welcher Stufe der Punkt in der Karte steht. Früher als seine Grenze zeigt das Gerät den Punkt nicht.

Gerätetests vom 2026-11-08, Kartendetail „Normal“, Region Wil:

| Karte | Punkttyp | Auflösung | erscheint ab |
|---|---|---|---|
| Tests 7795, 7783–7788 | erweitert (`0x10e00`, `0x10e1f`), mit und ohne Name | 18, 20, 21 oder 24 | 80 m |
| Test 7796 | `0x2f17`–`0x2f1b` | 21 | 80 m |
| Test 7790, Testgebiet | `0x2f08`, `0x2800`, `0x6400`, `0x0e00` | 21 | 1,2 km |
| Test 7791, Testgebiet | `0x2f08` | 22 | 80 m |
| Overlay Schweiz 7702 (nicht freigegeben) | `0x2f08` ohne sichtbaren Namen | 21 | 80 m |
| Basiskarte 7701 | `0x2f08` | 24 | ca. 200 m |

- Erweiterte Typen und `0x2f17` ff. erscheinen erst bei 80 m, unabhängig von der Auflösung.
- Kein Einfluss hatten: Level-Kopf wie die Basis, Punkte zusätzlich auf Auflösung 20 und 18,
  Zeichenpriorität 25 statt 31, nicht transparente Karte, Name oder kein Name.
- In der IMG liegen die Punkte jeweils auf den erwarteten Levels (geprüft mit dem `MapReader` von
  mkgmap und der Typübersicht im TRE-Kopf).
- Standardtypen erschienen nur im Test 7790 früh. Mit demselben Typ und derselben Auflösung erschien das
  Overlay Schweiz erst bei 80 m. Die Ursache für diesen Unterschied ist offen.
- Entscheid: Die Haltestellen bleiben erweiterte Typen mit Namen und erscheinen am Gerät ab ca. 80 m.
  Standardtypen bringen keinen zuverlässigen Nutzen. Im Gesamtbuild brauchen sie eine eigene
  Umlenkung, weil die Basis `0x2f08` und `0x2a00` auch nutzt.
- Aus demselben Grund bleiben die POIs erweiterte Typen.
- Die Basis nutzt viele erweiterte Punkttypen (`0x115xx`). Für diese ist am Gerät dasselbe zu erwarten.

### POIs, die die Landeskarte nicht zeigt

`src/routes/pois_overlay.py` ruft die POI-Erzeugung der Basiskarte (`src/vector/pois.py`) unverändert
auf. Tags und Namen sind deshalb gleich wie in der Basis. Haltestellen und Seilbahnstationen lässt
das Skript weg, die liefert `convert_routes.py`. Welche POIs das Overlay zeigt, legen die Regeln in
`src/style/routes/points` fest. Die Basiskarte zeichnet diese Arten nicht.

| Punkttyp | Objekt | Tags | Symbol |
|---|---|---|---|
| `0x10e05` | Parkplatz | `amenity=parking` (ohne `access=private`, `access=no`) | blaues Quadrat, weisses „P“ |
| `0x10e06` | Restaurant | `amenity=restaurant`, `cafe`, `pub`, ohne `swisstopo:nutzung=Gasthof abgelegen` | brauner Kreis `#8B4A1C`, Besteck |
| `0x10e07` | Rastplatz | `highway=rest_area` | grüner Kreis `#2E7D32`, Tisch |
| `0x10e08` | Raststätte | `highway=services` | oranger Kreis `#C05A00`, Besteck |
| `0x10e09` | Toilette | `amenity=toilets` | graues Quadrat `#555555`, „WC“ |
| `0x10e0a` | Hotel, Gasthaus | `tourism=hotel`, `guest_house`, `hostel` | violettes Quadrat `#8E2A6B`, „H“ |

- Abgelegene Gasthöfe (`swisstopo:nutzung=Gasthof abgelegen`) zeigt die Basis mit der Fahne der LK
  (`0x2a00`). Das Overlay lässt sie weg, sonst stünden zwei Symbole an derselben Stelle.
- Die Parkplatzfläche bleibt als Areal in der Basis. Nur der Parkplatz-Punkt ist im Overlay.
- Alle Symbole sind 13 × 13 px mit weissem Rand. Die Farbe steckt nur im Symbol.
- Name und Symbol erscheinen ab Auflösung 24. Der Name ist im Suchindex. Das GPSMAP 67 zeigt erweiterte
  Punkttypen erst ab ca. 80 m (siehe [Punkttypen am GPSMAP 67](#punkttypen-am-gpsmap-67)).
- Das Gerät zeichnet Punktnamen schwarz, auch mit Schriftfarbe in der TYP.
- swissTLM3D hat keine eigenen Objekte für Toiletten und Infopunkte. Restaurants stammen aus der
  Gebäudenutzung (`Gasthof abgelegen`) und aus Gebäudenamen.
- Im Testgebiet gibt es keine Toiletten und keine Hotels.
- Symbole und Farben in `make_typ.py` (`POIS`, `GLYPH_*`, `symbol_xpm`).

### Labels und Routennummern

- Unter Auflösung 22 kein Label. In 22 und 23 nur die Nummer im Schild. In 24 Schild und Name
  („[V4] ViaJacobi“).
- Alle SchweizMobil-Routen haben das Schild `oval` (Code 0x06) mit einem Präfix je Land. Die Basis
  belegt `interstate`, `shield` und `box`. Frei sind `hbox` und `round`.

| Objekt | Schild | Code | Label |
|---|---|---|---|
| Autobahn (Basis) | `interstate` | 0x01 | A1 |
| Autostrasse (Basis) | `shield` | 0x02 | 13 |
| Haupt- und Durchgangsstrasse (Basis) | `box` | 0x05 | 7 |
| Wanderland | `oval` | 0x06 | W24 |
| Veloland | `oval` | 0x06 | V7 |
| Mountainbikeland | `oval` | 0x06 | M95 |
| Skatingland | `oval` | 0x06 | S3 |
| Kanuland | `oval` | 0x06 | K1 |

- Die Netzebene ergibt sich wie auf den Wegweisern aus der Stellenzahl: national 1-, regional
  2-, lokal 3-stellig.
- Stilregel: `{ set ch:rref='V${ref}'; name '${ch:rref|highway-symbol:oval}' }`.
- Die Schildfarbe legt die Firmware fest. Wo das Gerät die Nummer entlang der Linie setzt, legt
  die Firmware fest.
- Nahe Linien haben `NormalFont`, Übersichtslinien `SmallFont`.
- TYP-Namen in vier Sprachen: `String1=0x02` Deutsch, `0x01` Französisch, `0x05` Italienisch,
  `0x04` Englisch.

### Erzeugte Dateien

- `src/routes/make_style.py` erzeugt `src/style/routes/lines`. Die Datei nicht von Hand ändern.
- `src/routes/make_typ.py` erzeugt `src/style/typ/routes.txt`. Farben in `make_typ.py` ändern
  (`LIGHTEN`, `LIGHTEN_FINE`, `LIGHTEN_BY_TYPE`).
- Vorschau ohne BaseCamp (ohne Schilder und ohne Garmin-Labelplatzierung):

```bash
.venv/bin/python -I src/style/tools/render_img.py work/routes/77020001.img src/style/typ/routes.txt out.png --res 23 --bbox 9.32,47.23,9.38,47.27
```

### Legende

| Signatur | Bedeutung |
|---|---|
| gelb-weiss gestrichelt | Wanderweg |
| rot-weiss gestrichelt | Bergwanderweg |
| blau-weiss gestrichelt | Alpinwanderweg |
| dunkelgrüne Linie, leicht aufgehellt | Wanderland, Übersicht |
| marineblaue bzw. orange gestrichelte Linie | Veloland bzw. Mountainbikeland, Übersicht |
| dunkelgrüne Linie | Wanderland-Route |
| dunkelgrüne Linie gestrichelt | hindernisfreier Weg |
| blaue Linie | Veloland-Route |
| orange Linie gestrichelt | Mountainbikeland-Route |
| violette Linie gepunktet | Skatingland-Route |
| türkise Linie | Kanuland-Route |
| blauer Punkt, Name rot | ÖV-Haltestelle (Bus, Postauto, Tram, Schiff, Seilbahn) |
| blauer Punkt ohne Name | Bahnhof (Name aus der Basiskarte) |
| blaues Quadrat mit „P“ | Parkplatz |
| brauner bzw. oranger Kreis mit Besteck | Restaurant bzw. Raststätte |
| grüner Kreis mit Tisch | Rastplatz |
| graues Quadrat mit „WC“ | Toilette |
| violettes Quadrat mit „H“ | Hotel, Gasthaus |

## Ein- und Ausschalten

- **Gerät:** Jede Familie in `gmapsupp.img` erscheint unter „Karte einrichten →
  Karteninformationen“ einzeln. Ein Overlay ist nur schaltbar, wenn es eine eigene Familie hat
  (`DEVICE_FAMILIES=split`). Innerhalb einer Familie gibt es keinen Schalter je Linientyp.
- **BaseCamp:** zeigt nur ein Kartenprodukt gleichzeitig. Ein transparentes Overlay einer anderen
  Familie legt BaseCamp nicht über die Basiskarte. Der Gesamtbuild fasst deshalb alles in der
  Familie 7701 zusammen.

| Variante | Gerät | BaseCamp |
|---|---|---|
| A: alles in 7701 (`DEVICE_FAMILIES=single`) | nicht schaltbar | sichtbar |
| B: `split`, Routen-Overlay 7702 | 7702 schaltbar | wie A |
| C: `split`, 7702 geteilt in SchweizMobil und Wanderwegnetz | beide getrennt schaltbar | wie A |

Für C erzeugt `make_style.py --part trails` bzw. `--part routes` je einen Stil aus derselben PBF.
Für den Wanderweg-Teil gibt es noch keine FID.

## Einbau in die Gesamtkarte

Im Gesamtbuild (`src/build/build_all.sh`) teilen sich Basis und Routen die Familie 7701. Die
Routencodes `0x10exx` kollidieren dort mit Bahnlinien der Basis. `ROUTES_TYPE_REMAP=0x10e:0x113`
(`src/build/config.sh`) verschiebt sie in Stil und TYP nach `0x113xx`.
- Die Ersetzung verlangt Typcodes kleingeschrieben im Format `0x10exx`. `make_typ.py` und
  `make_style.py` schreiben sie so.
- `merge_typ.py --fid 7701` findet mit `swisstopo.txt`, `routes.txt` und `contours.txt` keine
  Kollision.

## Quellenangaben im IMG

`build.sh` schreibt `copyright.txt` je nach Inhalt:

```
Kartendaten ©swisstopo (swissTLM3D Wanderwege, Haltestellen und POIs, OGD)
Routen: Bundesamt für Strassen, Kanton, Stiftung SchweizMobil (Opendata BY)
Kanuland: Stiftung SchweizMobil (Open Data BY)       ← nur mit Kanuland-Linien
```

Dazu kommen `--description` und `--series-name` mit „©swisstopo, ASTRA/SchweizMobil“ und eine
`license.txt` mit dem Hinweis „inoffiziell, keine Karte von swisstopo oder SchweizMobil“. Die Texte
stehen in CP1252 mit Umlauten im IMG. Codepage 1252 braucht `--lower-case`, sonst stehen nur
Grossbuchstaben ohne Umlaute im IMG.

## Zuordnung zur Basiskarte (`match_tlm.py`)

Die SchweizMobil-Daten haben keine `TLM_ID`. `match_tlm.py` ordnet die Routen den
swissTLM3D-Kanten zu:
- Eine Kante gehört zu einer Route, wenn mindestens 80 % ihrer Länge (Stichproben alle 5 m) näher
  als 3 m an der Routengeometrie liegen.
- Landesweit: 201 011 Kanten. Testgebiet: 9959 Kanten. Abgedeckt sind 527 von 528 km Wanderland
  und 434 von 437 km Veloland. Der Rest sind provisorisch erfasste Stücke ohne TLM-Kante und
  Grenzfälle an Kreuzungen.
- Ausgabe `tlm_routes.csv` mit den Spalten
  `uuid,objektart,wanderwege,belagsart,wanderland,veloland,mountainbikeland,skatingland`.
  Routenfelder als `netz:nummer`, mehrere mit `;` (z. B. `national:9;regional:99`). `uuid` ohne
  geschweifte Klammern entspricht `swisstopo:uuid`.

`src/vector/routes_attr.py` setzt daraus an den Basiskanten nur die Zugehörigkeit, keine Namen und
keine Nummern:

| Bedingung | Tags |
|---|---|
| Veloland | `ch:veloland=<netz:nr;…>`, nach bestem Netz `ncn=yes`, `rcn=yes` oder `lcn=yes` |
| Mountainbikeland | `ch:mountainbikeland=<…>`, `mtb=designated` |
| Skatingland | `ch:skatingland=<…>`, `inline_skates=designated` |
| Wanderland | `ch:wanderland=<…>` |
| Veloland oder Mountainbikeland | `bicycle=designated` |

`bicycle=designated` überschreibt das `bicycle=no` der Wegbreiten-Regel. Sonst führt das
Velorouting nie über eine signalisierte MTB-Route: Landesweit liegen 631 km Mountainbikeland auf
`1m Weg` als Bergwanderweg und 6 km auf `Markierte Spur`. Eine gesetzliche Sperre
(`verkehrsbeschraenkung`) hat Vorrang. Wie die Basiskarte die Zugehörigkeit im Routing nutzt, steht
in [routing.md](routing.md).

Die Basiskarte enthält damit Attribute aus den ASTRA-Daten. Ihre Quellenangabe nennt deshalb
zusätzlich `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`.

## Nicht umgesetzt

- Routennummer als Punkt an Routenknoten statt entlang der Linie. Wegweiserstandorte gibt es nicht
  als freien Datensatz.
- Winterwandern und Schneeschuh (`ch.astra.winterwanderwege`, `ch.astra.schneeschuhwanderwege`).
- Etappen mit Start- und Zielnamen.
- Velo und MTB nach Belag (Asphalt durchgezogen, Naturbelag gestrichelt).
