# Stil und TYP nach Swiss Map Vector 25

Stand: 2026-11-04. Gilt für die Basiskarte 7701 (Codepage 1252) auf GPSMAP und Montana.

Ziel ist eine Karte möglichst nahe an der Landeskarte 1:25'000 (Swiss Map Vector 25). Farben,
Linienbreiten, Muster, Symbole und Zeichenreihenfolge sind gleich, soweit Garmin es zulässt. Jede
Abweichung ist je Objektart dokumentiert ([soll-ist.md](soll-ist.md), [Abweichungen](#abweichungen-vom-vorbild)).
Die Nähe wird gemessen ([messung.md](messung.md)).

Kennzeichnung **(unsicher)**: abgeleitet oder nur am Renderer geprüft, nicht in BaseCamp oder am Gerät.

## Dateien

| Pfad | Inhalt |
|---|---|
| `src/style/swisstopo/` | mkgmap-Stil (`version`, `info`, `options`, `points`, `lines`, `polygons`, `relations`, `inc/access`, `inc/address`, `inc/routing_pref`) |
| `src/style/typ/swisstopo.txt` | TYP-Quelltext, **erzeugt** von `make_typ.py` |
| `src/style/tools/make_typ.py` | TYP-Generator: Soll-Werte aus SMV25 (mm), Umrechnung in px, Muster, Symbole, Nachtfarben, Zeichenreihenfolge |
| `src/style/tools/typ_i18n.py` | TYP-Namen in Französisch, Italienisch, Englisch. Fehlt eine Übersetzung, bricht `make_typ.py` ab. |
| `src/style/tools/extract_qgs_symbology.py` | liest Farben und Linienarten aus der swisstopo-QGIS-Projektdatei |
| `src/style/tools/render_img.py` | Vorschau-Renderer für IMG und TYP-Text (TRE, RGN, LBL, NET) |
| `src/style/tools/netz_check.py` | prüft isolierte Netzstücke je Zoomstufe |
| `src/style/build_testgebiet.sh` | baut das Testgebiet aus einer Basis-PBF |
| `src/style/build_legend.sh`, `src/style/test/make_legend_osm.py` | Legenden-Testkarte |
| `src/style/build_shieldtest.sh` | Testkarte für die Garmin-Schilder |

Die TYP-Datei nicht von Hand ändern, sondern `make_typ.py`. Die Soll-Ist-Liste entsteht mit
`make_typ.py --soll-ist > docs/stil/soll-ist.md`.

## Quellen

| Quelle | Verwendet für | Lizenz |
|---|---|---|
| QGIS-Projekt `SMV25_CHLV95LN02.qgs` aus `SMV25-Hilfsdateien.zip` (Produktseite Swiss Map Vector 25) | alle RGB-Werte, Linienbreiten, Strichmuster | OGD-Hilfsmaterial |
| Produktdokumentation Swiss Map Vector | Layerstruktur, Schriften (Frutiger → Liberation Sans Narrow, Symbolschrift DKM_Symbole) | OGD |
| WMTS `ch.swisstopo.pixelkarte-farbe` (8 Kacheln) | nur Sichtvergleich | OGD |
| mkgmap r4924 Doku (`typ-compiler.txt`, `style-manual.pdf`) und Quellcode | TYP-Grenzen, Regelsemantik, IMG-Format | GPL v2 |

Downloads liegen in `downloads/style-swisstopo/`, die ausgelesene Tabelle in `symbology.tsv`.

Lizenz:
- Farben, Breiten und Strichmuster stammen aus der OGD-Hilfsdatei. Farbwerte und Linienarten sind
  keine schutzfähigen Werke.
- Die Schrift `DKM_Symbole-Medium` ist nicht eingebunden und nicht kopiert. Alle Punktsymbole und
  Flächenmuster sind eigene Pixelgrafiken in `make_typ.py`.
- Fels, Geröll und Gletscher sind in SMV25 Rasterbilder. Die TYP verwendet eigene 32×32-Muster.
- Keine Logos. Die TYP enthält nur die Quellenangabe `©swisstopo`.

## Umrechnung mm → px

Breiten, Strichmuster, Musterabstände und Symbolgrössen stehen im QGIS-Projekt in mm bei
1:25'000. `make_typ.py` rechnet `px = round(mm × K)`, mindestens 1 px.

| Konstante | Wert | gilt für | Herleitung |
|---|---|---|---|
| `K_DEV` | 6,25 px/mm | alle Linien ausser Strassen in Auflösung 24 | GPSMAP 66/67, 158 dpi: LK-Strich in Originalgrösse |
| `K_24` | 12,5 px/mm | Strassen-Routingtypen und Auflösung-24-Typen | Auflösung 24 entspricht am Gerät ca. 1:12'500 = 2 × `K_DEV` |
| `K_LINE` | 10,4 px/mm | Flächenmuster | Geländebreite bei 1 Einheit = 1 px |
| `K_SYM` | 6,25 px/mm | Punktsymbole | LK-Grösse auf dem GPSMAP 66/67 |

- Strassen: Gesamtbreite = round((innen + 2 × Rand) × K), Füllung = Gesamtbreite − 2 × Rand.
- Strichmuster: Strich und Lücke in mm × K, Periode gestreckt auf eine ganze Zahl von
  Wiederholungen in 32 px (`dash()`).
- Flächenmuster: Rasterabstände × K auf 32 × 32 px (`grid()`, `hatch()`). Fels: kurze 45°-Schraffen
  im Raster 1,0 mm (ca. 3 % Deckung). Geröll: Punkte im Raster 0,8 mm (ca. 1,5 %).
- Zählkurven sind mindestens 1 px breiter als Normalkurven.
- Bahn: Breiten × 0,7, Normalspur mindestens 2 px. Landes- und Kantonsband × 0,8.

Massstabsgleicher Vergleich mit der LK-Pixelkarte: WMTS z16 (ca. 1,6 m/px) gegen
`render_img.py --res 24 --scale 1.475`, WMTS z15 gegen `--res 23 --scale 1.475`.

## Zoomstufen

`options`: `levels = 0:24, 1:23, 2:22, 3:21, 4:20, 5:19, 6:18, 7:16`, Übersicht `8:14, 9:12`.
mkgmap erlaubt höchstens 8 Levels.

| Auflösung | BaseCamp-Zoom | etwa wie | Inhalt |
|---|---|---|---|
| 24 | < 300 m | 1:10'000 | Routingtypen in Geländebreite, Strassennamen, Einzelpunkte, Bahnhöfe, Treppen, Arealränder, City-Punkte |
| 23 | 300–500 m | LK 1:25'000 | alle Strassen und Wege, alle Gebäude, Flur- und Objektnamen |
| 22 | 700 m | LK 1:50'000 | LK50-Typen, Bäche, Gebäude ab ca. 50 m², Bahnhöfe, Ausfahrten, Fluss- und Strassennummern, Koten Rang 2 |
| 21 | 1–1,5 km | LK 1:100'000 | Gebäude ab ca. 150 m², Flüsse ohne Namen, Strassen ohne Nummer (ausser Autobahn), Koten Rang 1 |
| 20 | 2 km | LK 1:200'000 | Dörfer, Verbindungsstrassen, Seen, Kantonsgrenzen, Gebäude ab ca. 4000 m² |
| 19 | – | wie 18 | Inhalt wie 18 auf halb so grobem Raster (Kurven weniger eckig, +0,4 % Grösse), dazu Autobahn- und Autostrassennummern |
| 18 | – | LK 1:200'000 | Schmalspur, Seen ab ca. 35 000 m², Dörfer ab 2000 Einwohnern |
| 16 | 3–5 km | LK 1:500'000 | Autobahn, Durchgangsstrasse, Bahn, grosse Flüsse, Wald, Gletscher, Siedlungsfläche, Städte ab 30 000 Einwohnern |
| 14, 12 | Übersichtskarte | 1:1 Mio. | Autobahn ohne Nummer, Autostrasse, grosse Flüsse, Seen ohne Namen, Siedlungsfläche, Städte ab 100 000 Einwohnern |

- Die BaseCamp-Spalte ist in der VM gemessen (200 % DPI, Detail normal). Welche Gerätezoomstufe
  welcher Auflösung entspricht, hängt vom Gerät und von der Einstellung „Detail“ ab **(unsicher)**.
- BaseCamp in der VM zeichnet TYP-Pixel physisch. Linien wirken dort halb so breit wie am Gerät.
- `--polygon-size-limits="24:0,23:1,22:1,21:1,20:1,19:1,18:2,16:1,14:1,12:1"`. Höhere Werte
  verwerfen kleine Gebäude und in 16 den Wald.

## Typcodes

Routingfähig sind in mkgmap nur 0x01–0x13, 0x16, 0x1a, 0x1b. Erweiterte Typen 0x1TTSS (Untertyp
SS ≤ 0x1f) sind reine Darstellung. Die vollständige Zuordnung steht in `src/style/swisstopo/` und
in [soll-ist.md](soll-ist.md).

Eine TYP kennt nur eine Breite je Typ. mkgmap behält bei zwei Elementen gleichen Typs für dasselbe
Objekt nur eines. Jede Strasse hat deshalb eigene Typen je Zoombereich:

| Bereich | Typen | Auflösung | Zweck |
|---|---|---|---|
| Routingtypen | 0x01–0x16 | 24 | Geländebreite (`K_24`), Strassennamen, Routing, Adressindex |
| Übersichtstypen | 0x10a01–0x10a16 | 21–23 | LK-Strichbreite (`K_DEV`), nur Routennummer |
| LK50-Typen | 0x10b.. | 21–22 | generalisiert: 4-m- und 3-m-Hartbelagstrasse als feine Doppellinie (0x10b06), schmale Strassen 1 px, Wege fein gestrichelt |
| Grobstufen | 0x10901–0x10907 | 12–20 | Autobahn ab 12, Autostrasse ab 14, Durchgangsstrasse ab 16, Verbindungsstrasse ab 18, Kantonsstrassen 4–6 m 19–20. Tunnel durchgezogen |
| Auflösung-24-Typen | 0x10c.., 0x10d.., 0x111.. | 24 | Bahn, Seilbahn, Gewässer, Grenzen, Leitungen in Geländebreite |

Routing, NOD und Adressindex verwenden nur die Daten der Auflösung 24 **(unsicher, ob alle Geräte
das in allen Zoomstufen so tun)**.

Weitere Bereiche:

| Bereich | Inhalt |
|---|---|
| 0x10e.. | Bahn, Seilbahn, Gewässerlinien |
| 0x10f.. | Höhenkurven, Grenzen, Mauern, Böschungen, Arealränder |
| 0x110.. | Flächen |
| 0x113.. | Routen im Gesamtbuild (siehe [routen.md](../vektor/routen.md#einbau-in-die-gesamtkarte)) |
| 0x115.. | eigene Punkte (Ortsnamen, Koten, Einzelsymbole) |

### Routingklassen

Klasse und Geschwindigkeit hängen am `highway`-Tag, nicht an der Signatur. Der Stil setzt
`mkgmap:road-class` und `mkgmap:road-speed-class`.

| highway | Klasse | Geschwindigkeit |
|---|---|---|
| motorway | 4 | 7 |
| motorway_link | 4 | 4 |
| trunk | 4 | 6 |
| trunk_link, primary | 3 | 4, 5 |
| secondary | 2 | 4 |
| tertiary | 1 | 3 |
| unclassified, residential | 0 | 3, 2 |
| service, living_street, track, pedestrian, cycleway | 0 | 1 |
| path, footway, steps, via_ferrata, bridleway | 0 | 0 |

- `inc/access` folgt dem OSM-Zugangsbaum. Wegtyp-Vorgaben (z. B. `path` → `access=no`, `foot=yes`,
  `bicycle=yes`) stehen vor dem Ausrollen.
- Autobahn und Autostrasse ohne Velo und Fuss. Treppen und Klettersteige ohne Velo. 1-m-Wege und
  Spuren ohne Motorfahrzeuge.
- `motor_vehicle=destination` und `access=private` setzen `mkgmap:throughroute=no`.
- `mkgmap:unpaved=1` bei Naturbelag.
- Velo- und Wanderpräferenz: [routing.md](../vektor/routing.md).
- mkgmap kann „Einbahn ausgenommen Velo“ (`oneway:bicycle=no`) nicht abbilden.

## Farben (Tagfarben aus SMV25-QGIS)

Breiten in mm bei 1:25'000.

### Strassen und Wege (T45)

| Objektart | Füllung | Rand | Breite gesamt / innen | Strich |
|---|---|---|---|---|
| Autobahn | `#FBBF39` | `#000000` | 0,68 / 0,36 | durchgezogen |
| Autostrasse, Zufahrt, Ein- und Ausfahrt | `#FBBF39` | `#000000` | 0,70 / 0,46 | durchgezogen |
| Durchgangsstrasse | `#F5AE95` | `#000000` | 0,54–0,86 / 0,30–0,62 | durchgezogen |
| Verbindungsstrasse | `#FFF582` | `#000000` | 0,54–0,86 / 0,30–0,62 | durchgezogen |
| Strasse 10 / 8 / 6 / 4 / 3 / 2 m | `#FFFFFF` | `#000000` | 0,86 / 0,78 / 0,70 / 0,62 / 0,54 / 0,46 | durchgezogen |
| Strasse Naturbelag | `#FFFFFF` | Punkte `#000000` | wie oben | Rand punktiert |
| Weg 2 m | – | `#000000` | 0,18 | durchgezogen |
| Weg 2 m, nicht befahrbar | – | `#000000` | 0,18 | gestrichelt 3,0 / 0,3 |
| Weg 1 m | – | `#000000` | 0,18 | gestrichelt 1,2 / 0,3 |
| Markierte Spur | – | Punkte `#000000` | 0,27 | punktiert |
| Autofähre | – | `#000000` | 0,14 | gestrichelt 0,99 / 0,40 |

### Bahn, Seilbahn (T44, T42)

| Objektart | Farbe | Breite |
|---|---|---|
| Normalspur | `#DD1919` | 0,32 |
| Normalspur Mehrspur | `#DD1919`, Mitte `#FFFFFF` 0,22 | 0,76 |
| Schmalspur | `#DD1919` | 0,22 |
| Anschlussgleis | `#DD1919` | 0,10 |
| Luftseilbahn, Gondel- und Sesselbahn | `#DD1919` mit Symbolen | 0,18–0,20 |
| Skilift | `#D7963C` mit Symbolen | 0,15 |
| Transportseil, Förderband | `#000000`, `#333333` | 0,13–0,18 |

### Gewässer (T55–T57)

| Objektart | Farbe |
|---|---|
| Fliessgewässer (0,12–0,40 mm), Druckleitung | `#0088D0` |
| See, Wasserbecken | `#D2EEFF`, Rand `#0088D0` 0,14–0,18 |
| Fluss (Fläche) | `#9CD5F8`, Rand `#0088D0` 0,12 |
| Trockenrinne | Punkte `#000000` |
| Tiefenlinien | `#0088D0` 0,10 / 0,18 |

### Relief (T62)

| Objektart | Farbe |
|---|---|
| Höhenkurve braun: Normal / Zähl / Zwischen | `#D7963C` 0,10 / 0,18 / 0,18 gestrichelt |
| Höhenkurve schwarz (Fels, Geröll) | `#3E3E3E` 0,08 / 0,16 |
| Höhenkurve blau (Gletscher, See) | `#0088D0` 0,10 / 0,18 |
| Fels, Geröll (Raster) | `#3F3F3F` |
| Gletscher (Raster) | `#006BC7` |

### Bodenbedeckung und Areale (T61–T65)

| Objektart | Füllung | Rand |
|---|---|---|
| Wald | `#CDE6BE` | – |
| offener Wald, Gebüschwald, Gehölz | Punkte `#70B446` | – |
| Reben, Obstanlage, Baumschule | Muster `#70B446` | – |
| Feuchtgebiet | Symbole `#0088D0` | – |
| Friedhof, Park, Camping, Golf, Freizeit, Sportplatz | `#E7F3E1` | `#70B446` 0,12 |
| Deponie | `#F0DABC` | – |
| Spitalareal | `#F2F2F2` | – |
| Unterwerk, Parkplatz, Verkehrsfläche, Hartbelagpiste | `#FFFFFF` | `#262626` 0,12 |
| Staumauer, Staudamm | `#CCCCCC` | `#262626` |
| Gebäude, Mauer gross, Wehr | `#000000` | – |
| Flugdach, Treibhaus | `#FFFFFF` mit Schraffur | `#333333` |
| Kartenhintergrund | `#FFFFFF` | – |

### Grenzen (T53, T54)

| Objektart | Farbe |
|---|---|
| Landesgrenze | Linie `#C22976` 0,16 auf Band `#ECA8C8` 2,0 |
| Kantonsgrenze | Linie `#C22976` 0,16 auf Band `#ECA8C8` 1,0 |
| Bezirksgrenze | `#ECA8C8` 0,4 |
| Gemeindegrenze | `#ECA8C8` 0,4 gestrichelt 3,0 / 0,6 |
| Nationalpark | `#A0CF83` 0,16 mit Band |

### Bauten und Punkte (T29–T40)

| Objektart | Farbe |
|---|---|
| Hochspannungsleitung | `#0088D0` 0,14 Strich-Punkt |
| Mauer, Laufbahn | `#000000` 0,14–0,20 |
| Gewässerverbauung, Hafensteg | `#0088D0` |
| Durchfahrtssperre | `#DD1919` |
| Brunnen, Quelle, Wasserturm, Spital | `#0088D0` |
| Landesgrenzstein | `#C22976` |
| Gipfelkreuz, Kapelle, Turm, Antenne, Höhenkote | `#000000` |
| Schrift allgemein | `#000000` |

## Zeichenreihenfolge

Nach der Layerfolge im QGIS-Projekt (unten → oben). Die TYP verwendet folgende Stufen:

| Stufe | Inhalt |
|---|---|
| 1 | Kartenhintergrund 0x4b (allein) |
| 2 | Siedlung (Übersicht), Flugplatzareal |
| 3 | Wald |
| 4 | Nutzungs- und Freizeitareale |
| 5 | Verkehrsareale |
| 6 | Bauten-Flächen (Sportplatz, Pisten, Solar, Schwimmbecken, Staumauer) |
| 7 | Geröll, Fels |
| 8 | Gewässer |
| 9 | transparente Muster (offener Wald, Gebüschwald, Feuchtgebiet) |
| 10 | Gebäude, Flugdach, Gletscher |

- mkgmap legt je Kachel eine Hintergrundfläche 0x4b an. Bei gleicher Stufe entscheidet die
  Reihenfolge im RGN. Der Hintergrund liegt deshalb allein auf Stufe 1.
- Flächen ohne `[_drawOrder]`-Eintrag zeigt das Gerät nicht. `make_typ.py` prüft das.
- Linien liegen immer über allen Flächen. Die Reihenfolge der Linien untereinander bestimmt das
  Gerät über die Typnummer **(unsicher)**.

## Darstellungsregeln

### Gebäude und Siedlung

- Gebäude sind schwarz wie SMV25.
- Gebäude nach Grösse: ab Auflösung 20 ab ca. 4000 m², 21 ab ca. 150 m² (`area_size() > 38`),
  22 ab ca. 50 m², 23 alle.
- Grosse Mauern (`swisstopo:mauer=gross`) sind schwarz gefüllt ab 23. In Historischen Arealen
  fallen sie weg, dort steht nur das Ruinensymbol. Gedeckte Mauern sind Gebäude.
  `building=ruins` hat nur einen Umriss (0x10f0d).
- Generalisierte Siedlungsfläche (`swisstopo:generalisiert=siedlung`) 0x1100e `#BEBEBE` in 14–21,
  in 22 heller Siedlungston 0x1100f `#F0F0F0`. Beides gibt es in SMV25 nicht.

### Strassen und Netz

- Die Startstufe einer Strasse kommt aus `swisstopo:netz_res` (siehe Tag-Schema). So bleibt das
  Netz je Zoomstufe zusammenhängend. Ohne den Tag gilt die Startstufe der Klasse.
- Isolierte Stücke unter 1,5 km im Testgebiet: in 21 keines, in 22 223 (davon 207 Wegfragmente wie
  auf der LK und 8 Klettersteige).
- Strassennamen nur in Auflösung 24 (NormalFont). Routennummern von Durchgangs- und
  Verbindungsstrassen ab 22, Autobahn- und Autostrassennummern ab 18.
- Parallele Gleisachsen (`swisstopo:parallelachse=yes`) zeichnet der Stil nicht. Mehrspurstrecken
  haben eine Mehrspursignatur.
- TYP-Namen der Routingtypen sind neutral und feminin („Gasse“, „Naturstrasse“, „Pfadstrecke“).
  BaseCamp nennt sie bei unbenannten Abschnitten in der Wegbeschreibung und schreibt fest „auf die …“.

### Schilder

| Objekt | Schild | Quelle |
|---|---|---|
| Autobahn, Autostrasse | `box` | `swisstopo:shield_autobahn` („A1“) |
| Hauptstrasse | `hbox` | `swisstopo:shield_hauptstrasse` („7“, bei „8;16“ nur der erste Teil) |
| Hauptstrasse mit dreistelliger Nummer | `round` | `swisstopo:hauptstrasse_nr_intern` („447“), nur ohne signalisierte Nummer |
| SchweizMobil-Routen | `oval` | Routen-Overlay |

Die Schilder sind nach einer Testkarte am GPSMAP 67 gewählt. Die Schildfarbe legt die Firmware fest.
Das runde Schild für dreistellige Nummern ist ein Wunsch des Benutzers (Review 3). Diese Nummern der
Hauptstrassen B und C sind in der Schweiz nicht signalisiert.

Autobahn- und Autostrassennummern erscheinen ab 19. Das GPSMAP 67 setzt Schilder und Flussnamen vor
die Ortsnamen. Im Gerätetest 7794-klassen2 stand bei 3 km ein A1-Schild an der Stelle von
„St. Gallen“. Bei 8 km fehlten St. Gallen, Rorschach und Herisau.

Darum haben Strassen- und Flussstücke in der Nähe einer Stadt bis 21 keine Nummer und keinen Namen.
Das Mass ist `swisstopo:stadtabstand`: die Meter bis zum nächsten Stadtpunkt ab 10 000 Einwohnern
(0x1150d ab 18). Die Grenze folgt der Breite des Stadtnamens am Gerät:

| Auflösung | kein Label bei Abstand unter |
|---|---|
| bis 18 | 4 km |
| 19 | 3 km |
| 20 | 2 km |
| 21 | 1,5 km |

Ab 22 gilt die Grenze nicht mehr. Ohne das Tag haben alle Stücke ein Label.

### Gewässer

- Flüsse und Bäche nach Flussordnung: `swisstopo:gewaesserklasse` 6 ab 14, 5 ab 18.
  Nach `swisstopo:strahler`: ≥ 5 ab 21 (2 px), 3–4 ab 22 (1 px), 1–2 ab 23, in 24 eigener Typ 0x10c17.
  Bäche der Gewässerklasse 4 in 19–20 ohne Namen. Ohne die Tags gilt eine Namensliste grosser Flüsse.
- Flussnamen ab 22. In 21 haben nur Flüsse der Gewässerklasse 4 (z. B. Goldach, Steinach) einen Namen
  (0x10e1a), die übrigen Flüsse in 21 nicht.
- Bis 21 haben Flussstücke in der Nähe einer Stadt keinen Namen (`swisstopo:stadtabstand`, Grenzen wie
  bei den Schildern). Bei 3 km stand die Sitter sonst dreimal neben St. Gallen.
- Seen zerfallen in swissTLM3D in Teilflächen. In 12–20 haben sie eigene Typen ohne Namen
  (0x3d, 0x3f). Namen stehen ab 21 an 0x3c und 0x3e.
- Seenamen kommen als Punkt (`place=lake` aus swissNAMES3D, 0x650d) nach Namenklasse: 1 ab 16, 2 ab 18,
  3 ab 20, übrige ab 22, je bis 23. Eine Seefläche mit Namen bekommt keinen zweiten Namenpunkt.
- Gletschernamen (0x650a) nach Namenklasse: 1 ab 18, 2 ab 19, 3 ab 20, übrige ab 21. Gletscher ohne
  Namen haben keinen Punkt, sonst gäbe es leere Treffer in der Suche.

### Höhenkurven

- Eine Farbe je Untergrund: braun, Fels und Geröll schwarz, Gletscher und See blau.
- Ab Auflösung 22: 10- und 20-m-Kurven 1 px, aufgehellt (35 % Weiss). Die 100-m-Zählkurve 2 px in
  voller Farbe. In 21 nur 100-m-Kurven, 1 px in voller Farbe (0x10f15, 0x10f17, 0x10f19).
- Die Standardtypen 0x20–0x22 gelten ab 22. Garmin erkennt sie als Höhenlinien.
- Zahlen nur an den 100-m-Zählkurven. Zahlen an den 10- und 20-m-Kurven verdrängen sonst Objektnamen.
- 10-m-Kurven Fels und Gletscher: 0x10f12, 0x10f13.

### Fels und Gebirge

Review 3 (Säntis) verglich die Karte mit der swisstopo-App. Fels, Geröll und Schummerung wirkten
zu schwach. Die Höhenlinien bleiben unverändert (Entscheid des Benutzers). Umgesetzt ist:

- Fels 0x11001: gestreute steile Striche, ca. 10 % Deckung (vorher 3 %). Kein sichtbares Raster.
- Geröll 0x11002: gestreute Punkte, ca. 6 % Deckung.
- Felsschraffen 0x10f1a (Lichtseite, #7A7A7A) und 0x10f1b (Schattenseite, #3F3F3F) ab 23.
  `src/dem/rock_relief.py` erzeugt aus swissALTI3D Höhenlinien im swissTLM3D-Fels, alle 20 m.
  Der TYP zeichnet sie mit einer Kamm-Signatur. Die Striche stehen quer zur Linie, also in der
  Falllinie. Im steilen Fels rücken die Linien zusammen und die Fläche wird dunkler.
- Schattenflächen 0x11010 (mittel) und 0x11011 (stark) ab 21. `rock_relief.py` wählt Hänge ab 25°,
  die bei Licht von Nordwesten dunkel sind. Muster: geordnetes Raster in #50647D auf transparent,
  zusammen höchstens 25 %. Sie verstärken die graue Garmin-Schummerung.
- Wanderwege im Routen-Overlay 3 px statt 2 px (`src/routes/make_typ.py`).

Build: `RELIEF=yes` ist in beiden Profilen Standard. Fehlt `RELIEF_PBF`, rechnet der Build die
Datei neu. `rock_relief.py` rechnet in LV95-Kacheln zu 20 km mit 400 m Rechenpuffer. Jede Kachel
schneidet ihr Ergebnis auf das Kerngebiet zu. Danach führt `osmium merge` die Kacheln zusammen.

Fertige Kacheln in `<out>/tiles/` bleiben bei einem Neustart erhalten. `RELIEF_JOBS` (Standard 4)
legt die Zahl der parallelen Kacheln fest. Jede Kachel braucht höchstens 1,7 GB RAM.

Messung 2026-11-06 (14 Kerne, 6 parallel):

| Gebiet | Kacheln | Zeit | RAM je Kachel | PBF |
|---|---|---|---|---|
| Testgebiet | 9 | 9 s | max. 1,6 GB | 0,6 MB |
| Schweiz | 231, davon 145 mit Daten | 6 min | max. 1,7 GB | 58 MB |

Datenmenge Testgebiet (33,2 MB statt 32,7 MB):

| Teil | Objekte | IMG | Schweiz |
|---|---|---|---|
| Felsschraffen (Kamm) | 14 947 Linien, 54 255 Stützpunkte | 0,35 MB | 1,84 Mio. Linien, 7,6 Mio. Stützpunkte, ca. 50 MB IMG |
| Schattenflächen | 1705 Flächen | 0,09 MB | 67 402 Flächen, ca. 3 MB IMG |

Die IMG-Grösse der Schweiz ist aus den Stützpunkten hochgerechnet.
Einzelne Schraffen als eigene Linien (`--mode striche`) kosten 2,5 MB im Testgebiet, also rund
400 MB für die Schweiz. Diese Variante ist deshalb nur zum Vergleich da.

Grenzen:

- Garmin hat keine Rasterzeichnung. Die Felszeichnung ist eine Annäherung aus dem DEM, keine Kopie
  der LK. Grate und Wandfüsse zeichnet sie nicht eigens.
- Die Strichlänge der Kamm-Signatur ist fest in Pixeln. Sie wächst nicht mit dem Zoom.
- Die Garmin-Schummerung bleibt grau. Farbe und Stärke legt der Renderer fest.
- Das Schattenmuster ist ein Pixelraster. Je nach Bildschirm wirkt es körnig.
- An den Kachelrändern teilt `rock_relief.py` Linien und Flächen. Die Teile stossen genau aneinander.

### Ortsnamen

- Jeder Ort hat genau einen City-Punkt in Auflösung 24 (Suche, Adressen, MDR). mkgmap legt für jeden
  City-Punkt einen eigenen Städte-Eintrag an. Mehrere City-Punkte je Ort erzeugen doppelte Einträge.
- Die sichtbaren Ortsnamen sind eigene Beschriftungspunkte mit 4×4-Ortsring: 0x1150d (Städte,
  LargeFont), 0x1150e (Dörfer, NormalFont). Garmin zeichnet City-Typen in den Detailstufen nicht,
  und BaseCamp verwirft Punkte mit transparentem 1×1-Symbol.
- Städte nach Einwohnern (`population` aus swissBOUNDARIES3D). Ab Auflösung 12: über 100 000.
  Ab 16: über 30 000. Ab 18: über 10 000. Ab 20: übrige Städte.
- Dörfer nach swissNAMES3D-Einwohnerkategorie: 2000–9999 ab 18, 1000–1999 ab 19, übrige ab 20.
- Normale Schreibweise. BaseCamp setzt Titelschreibung.
- Quartiere mit Zentrumsnamen (Innenstadt, Altstadt, Zentrum, Dorf usw.) erst ab 23 als 0x2800.
  Sonst verdrängen sie das Ortslabel.
- Landschafts- und Gebietsnamen (0x6602) ab 21, Täler (0x6617) ab 22, Gebirge (0x6611) ab 20.
- Namen mit Namenklasse (`swisstopo:namenklasse` aus `src/vector/labelclass.py`: 1 = in SMV1000,
  2 = in SMV500, 3 = in swissTLMRegio) erscheinen früher: Klasse 1 ab 16, 2 ab 18, 3 ab 20. Das gilt
  für Gebiete, Täler, Grate und Gebirge, auch ohne LK25-Text.
- Massive mit Hauptgipfel (z. B. „Alpstein“ am Säntis, „Pilatus“ am Tomlishorn) sind 0x6612 nur in 24.
  Der Punkt hat kein Symbol und keine Schrift (`FontStyle=NoLabel`), die Suche findet ihn. Er liegt
  genau auf dem Gipfel. Als 0x6616 verdeckte er den Gipfelnamen in BaseCamp. Als 0x6612 in 20–21
  verdeckte er ihn auf dem GPSMAP 67 (Gerätetest 7794-klassen2). Massive ohne Gipfel bleiben 0x6611
  mit Schrift.
- Namen ohne LK-Beschriftung (`swisstopo:lk_text=no`) erscheinen erst ab 24. Die Suche findet sie in
  jeder Stufe.
- Objektnamen (SMV25-Annotationen, Areal- und Gebäudenamen) sind 0x2800 ab 23. Abwasserreinigungsareale
  heissen „ARA“ wie auf der LK.

### Gipfel und Koten

- Gipfel sind 0x6616 (Summit), Label nur `${name}`. mkgmap indexiert 0x64–0x66 im MDR unter
  „Geographic > Land Features“.
- Gipfel und Hügel haben eine Gipfelklasse (`swisstopo:gipfelklasse` aus `src/vector/peaks.py`):
  1 = Name in SMV1000, 2 = in SMV500, 3 = in swissTLMRegio, 4 = übrige.

| Klasse | Name 0x6616 ab | Kote im Label | Kote als eigener Punkt | Kotentyp |
|---|---|---|---|---|
| 1 (CH 66, z. B. Säntis) | 18 | 18–21 | ab 22 | 0x11510 (LargeFont) |
| 2 (CH 293, z. B. Altmann) | 20 | 20–21 | ab 22 | 0x11510 (LargeFont) |
| 3 (CH 1009, z. B. Schäfler) | 21 | 21 | ab 22 | 0x1150f (NormalFont) |
| 4 (übrige) | 22, Hügel 23 | – | ab 22, Hügel 23 | 0x1150f (NormalFont) |

- Bis 21 steht die Kote im Label des Gipfels („Säntis 2502“). So bleiben Name und Kote zusammen.
  Als eigener Punkt lag die Kote oft in einer anderen Unterteilung (Subdivision) als der Name. Das
  GPSMAP 67 zeichnete dann die Kote und verwarf den Namen (Säntis, Gerätetest 7794-klassen2).
- Die Suche liest nur die Punkte der Auflösung 24. Dort ist das Label nur der Name. Ein Label mit Kote
  im Suchindex fand BaseCamp nicht.
- Klasse 1 hat die Kote schon in 18. Ein Punkt nur mit Namen in 18 geht nicht: mkgmap legt ihn mit dem
  gleichen Punkt ab 22 zusammen (gleicher Typ, Name und Ort). Auflösung 18 bleibt dann leer.
- Ab 22 ist die Kote eines benannten Gipfels ein eigener Punkt je Auflösung r
  (`swisstopo:gipfelkote=r`). Er liegt 12 Karteneinheiten dieser Auflösung südlich des Gipfels.
  Der Stil zeichnet ihn nur in r (`resolution r-r`). Grund: Am selben Punkt zeigte das GPSMAP 67
  nur den Namen, die Höhe fehlte. Die Kotenpunkte 19–21 haben keine Regel.
- Pässe mit Namen nach Passklasse (`swisstopo:passklasse`): 0x660b Klasse 1 ab 19, 2 ab 20, 3 ab 21,
  übrige ab 22. Die Kote steht nur bei Pässen ohne Namen am Pass.
- Ein Pass darf einen Gipfel der Klasse 1 nicht verdrängen. Im Gerätetest 7794-klassen3 verdeckte
  „Schwägalp Passhöhe“ den Säntis (3 km entfernt). Das GPSMAP 67 zeichnet den Pass oft zuerst, und
  sein Label reicht weit nach rechts. Eine Stufe Abstand reicht darum nicht.
- `swisstopo:gipfelabstand` gibt die Meter bis zum nächsten Gipfel der Klasse 1 an. Ein Pass erscheint
  erst, wenn dieser Abstand grösser ist als die Labelbreite der Stufe: 19 18 km, 20 9 km, 21 4,5 km.
  Ab 22 gilt keine Grenze. Ohne das Tag gelten die Grundstufen.
- Gipfel ohne Gipfelklasse fallen auf die Stufen der Klasse 4 zurück und haben keine Kote.
- Unbenannte Gipfel und Hügel bekommen nur die Kote am Gipfelpunkt, 0x1150f ab 22.
- Höhenkoten (SMV25) sind 0x1150f mit Punktsymbol und Label in Metern, gestaffelt nach
  `swisstopo:koten_rang`: Rang 1 ab 21, Rang 2 ab 22, übrige ab 23. Wie auf der LK erscheinen bei
  1:50'000 wenige Koten und erst bei 1:25'000 alle. Garmin zeichnet 0x6300 mit Höhenfeld nicht.
- Nach `continue` übernimmt mkgmap das Label nicht in das nächste Element. Jede Regel setzt `name` selbst.

### POIs

- Bahnhöfe (`railway=station`, swissTLM3D „Haltestelle Bahn“): 0x2f08 nur in 24 (etwa 200 m), mit
  rotem Symbol 15×9. Früher verdrängten sie Ortsnamen (Gerätetest 7794-klassen3: „Appenzell
  Meistersrüte“ bei 3 km so früh wie Gais). Ab 22 waren sie im Gerätetest 7794-klassen4 noch zu früh.
- Die TYP gibt den Bahnhofsnamen die Schriftfarbe `#DD1919` (Rot der Bahnlinien). Das GPSMAP 67
  zeichnet Punktnamen trotzdem schwarz (siehe Garmin-Grenzen).
- Autobahnausfahrten (0x2000) ab 22.
- Haltestellen von Bus, Postauto, Schiff und Seilbahn stehen nur im Routen-Overlay (FID 7702), nicht
  in der Basiskarte. swissTLM3D trennt sie über die Objektart (Haltestelle Bahn, Bus, Schiff,
  Seilbahn, übrige Bahnen). Tramhalte sind in swissTLM3D „Haltestelle Bahn“. Mit
  `swisstopo:oev=tram` fehlen sie in der Basiskarte und stehen im Overlay.
- Die Basiskarte zeigt nur Punkte, die auch die LK 1:25'000 zeigt. Hotels (0x2b01), Parkplätze
  (0x2f0b), Toiletten (0x4e00) und die Haltestellen stehen im Routen-Overlay. Die Parkplatzflächen
  bleiben als Areal (0x05).
- Gastgewerbe nur mit `swisstopo:nutzung=Gasthof abgelegen` (LK-Fahne, 0x2a00 ab 23).
- Areale werden über `swisstopo:objektart` gezeichnet, nicht über POI-Tags.
- Nur POIs sind grösser als die SMV-Sollgrösse: Berghütte, Camping, Gastwirtschaft, Spital, Flugplatz,
  Heliport, Aussichtspunkt, Aussichtsturm, Burg und Ruine, Kirche, Kapelle, Höhle, Wasserfall. Symbole
  bis 7 px sind doppelt so gross, Symbole mit 8–10 px 1,5-mal so gross, ab 11 px bleiben sie. Am
  GPSMAP 67 waren sie sonst zu klein (Gerätetest 7794-klassen5). Der Bahnhof hat ein eigenes Symbol 15×9.
- Die Kartenzeichen der LK bleiben in SMV-Sollgrösse, z. B. Einzelbaum, Poller, Grenzstein, Brunnen,
  Quelle, Bildstock, Gipfelkreuz, Turm, Pass, Gipfel und Koten. Vergrössert wirkten sie zu gross.
- Wichtige POIs (Gastwirtschaft, Camping, Höhle, Burg, Aussicht, Kirche, Spital, Wasserfall) und
  Strassennamen haben NormalFont. Kleinobjekte SmallFont.
- Einzelbäume (`natural=tree`) als grüner Punkt 0x1150c (3 px) ab 23.

## TYP und Strings

- Flächenmuster: genau 32 × 32 px, 2 Farben plus 2 Nachtfarben.
- Linienmuster: 32 px breit, Höhe = Linienbreite, 2 Farben plus 2 Nachtfarben. Linien ohne Muster:
  `LineWidth` und `BorderWidth`.
- POI-Symbole: bis 255 Farben, beliebige Grösse.
- Schrift: nur `SmallFont`, `NormalFont`, `LargeFont`. Keine Schriftart, kein Kursiv.
- Strings je Typ: `0x02` Deutsch (zuerst), `0x01` Französisch, `0x05` Italienisch, `0x04` Englisch.
- Codepage 1252, FID 7701, Product 1.
- `src/build/merge_typ.py` schreibt `; -*- coding: utf-8 -*-` als erste Zeile. Ohne diese Zeile
  liest mkgmap die Quelle als Latin-1, und Umlaute gehen kaputt.

## Nachtfarben

`make_typ.py` leitet sie ab: Helle Flächen werden stark zum Nachtgrund (dunkles Blaugrau)
gemischt, Linien schwächer. Schwarz wird Hellgrau (Gebäude `#8C8C8C`, Wege `#C8C8C8`). Schriftfarben
werden aufgehellt. Ob Geräte für Linien mit Muster die Nachtfarben nutzen, ist offen **(unsicher)**.

## Build und Vorschau

```bash
sh src/style/build_legend.sh
bash src/style/build_testgebiet.sh <testgebiet.osm.pbf>
```

- `build_legend.sh` erzeugt TYP-Text und Legende und baut `work/style/legende/gmapsupp.img`
  (Map-ID 77019001, Übersicht 77019000).
- `build_testgebiet.sh` baut `work/style/testgebiet/gmapsupp.img` mit denselben Optionen wie
  `src/vector/build_img.sh`.
- Beide Skripte brechen ab, wenn `openstreetmap` oder `odbl` in einer Ausgabe steht. Ohne
  `--copyright-file` und `--overview-mapname` schreibt mkgmap diese Texte in IMG und TDB.
- `STYLE_DIR` und `TYP_FILE` wählen Stil- und TYP-Varianten.

Vorschau ohne BaseCamp:

```bash
python3 -I src/style/tools/render_img.py work/style/legende/77019001.img src/style/typ/swisstopo.txt out.png --res 24
```

Optionen: `--night`, `--res`, `--scale`, `--bbox lon,lat,lon,lat`, `--labels all|points|none`,
`--list` (Typzählung je Zoomstufe). Der Renderer liest eine einzelne Kachel. Er hat keine
Garmin-Schriftplatzierung und keine Kollisionsprüfung. Massgebend ist BaseCamp bzw. das Gerät.

## Garmin-Grenzen

- Eine Breite je TYP-Typ. Für jede Zoomstufe braucht es eigene Typen.
- Die IMG speichert Koordinaten höchstens im Raster der Auflösung 24: 1,6 m Ost–West und 2,4 m
  Nord–Süd. Jede Gebäudeecke wird für sich gerundet. Schräge Kanten bekommen dadurch Knicke, rechte
  Winkel weichen ab, und zwischen Gebäudeteilen entstehen Kerben. Messung Niederuzwil: Im TLM weichen
  die Ecken im Median 0,1° vom rechten Winkel ab, in der IMG 4,8°. mkgmap vereinfacht die Gebäude
  dabei nicht (`--simplify-polygons` 24:0).
- Abhilfe ist nur in den Daten möglich: Der Konverter dreht die Gebäude vor dem Runden leicht
  (höchstens 3°) und verschiebt sie um Bruchteile einer Einheit. So bleiben die gerundeten Ecken
  rechtwinklig. Gebäudeteile, die sich berühren, bekommen dieselbe Lage, sonst entstehen neue Kerben.
  Details: [Basiskarte](../vektor/basiskarte.md).
- Kein Puffer um die Gebäude (Gerätetest GPSMAP 67, 2026-11-08). Ein Puffer schliesst schmale Schlitze
  zwischen Gebäudeteilen, macht aber jedes Haus dicker. Mit 0,4 m gab es in Dörfern und Städten zu viel
  Schwarz. Im Testgebiet verglichen wir vier Varianten mit swissTLM3D (sichtbare Fläche):

  | Variante | Fläche | Eckwinkel Median | Schlitze unter 1 m |
  |---|---|---|---|
  | ohne Ausrichtung | +0,2 % | 5,9° | 12 277 m² |
  | ausgerichtet, ohne Puffer (Standard) | +0,5 % | 2,2° | 11 540 m² |
  | ausgerichtet, Puffer 0,15 m | +4,2 % | 2,2° | 8 823 m² |
  | ausgerichtet, Puffer 0,4 m | +10,4 % | 2,2° | 6 737 m² |

  swissTLM3D selbst hat 8676 m² Schlitze unter 1 m. Am Gerät sahen alle vier Varianten gut aus. Der
  Benutzer wählte die feinere Variante ohne Puffer. Ohne Puffer verschwindet kein Haus (keines unter
  1 m²). Ohne Ausrichtung fallen 224 Häuser unter 1 m².
- Keine Schriftart, kein Kursiv. BaseCamp wandelt reine Grossbuchstaben in Titelschreibung um.
- Die Labelplatzierung macht das Gerät. Konkurrierende Labels verdrängen Ortsnamen. Sie sind deshalb
  über die Zoomstufen gestaffelt.
- City-Typen zeichnet Garmin in den Detailstufen nicht.
- Punkte mit transparentem 1×1-Symbol verwirft BaseCamp.
- Punktnamen zeichnet das GPSMAP 67 immer schwarz. Der Farbtest (FID 7799) belegt das. Er hatte fünf
  Farben, mit und ohne Nachtfarbe, drei Schriftgrössen, erweiterte Typen und Standardtypen mit und
  ohne TYP-Eintrag. Alle Namen waren schwarz. Linien behalten ihre Schriftfarbe (Flussnamen blau).
- Flächen haben keinen Rand. Keine Maskierung an Kreuzungen.
- Wegpunkte in BaseCamp unterdrücken Kartenlabels in ihrer Nähe.
- Helligkeit und Lichtrichtung der Schummerung legt der Renderer fest (siehe [hoehen.md](../vektor/hoehen.md)).

## Abweichungen vom Vorbild

| Thema | SMV25/LK25 | Helvetopo | Grund |
|---|---|---|---|
| Linienbreiten | massstäblich in mm | ganze Pixel, eigene Typen je Zoombereich | TYP |
| Strassenränder an Kreuzungen | maskiert | Ränder je Typ | keine Maskierung in Garmin |
| Strassennamen | fast nur Nummern | Namen in Auflösung 24 | Orientierung und Suche |
| Tunnel, Galerie, Brücke | eigene Signaturen | ein Tunneltyp für alle Klassen, Brücken normal | Routingtypen sind knapp |
| Strasse in Bau | gestrichelt | nicht unterschieden | wenig Nutzen am Gerät |
| Fels, Geröll, Gletscher | Rasterzeichnung | 32×32-Muster, Felsschraffen aus dem DEM | TYP |
| Schummerung | Rasterschummerung | DEM und Schattenflächen | Garmin |
| Symbole | DKM-Symbolschrift | eigene Pixelsymbole | Symbolschrift nicht frei |
| Schrift | Frutiger, kursiv für Gewässer und Gelände | Geräteschrift, nur Grösse und Farbe | TYP |
| Städte | Grossbuchstaben | normale Schreibweise mit Ortsring | BaseCamp-Titelschreibung, Labels ohne Symbol werden nicht gezeichnet |
| Schriftplatzierung | handplatziert | automatisch | Gerät |
| Uferlinien, Arealränder | Rand an der Fläche | Uferlinie fehlt, Arealränder als eigene Linie ab 24 | Garmin-Flächen haben keinen Rand |
| Siedlungsfläche | – | grau in groben Stufen | geschlossene Ortswirkung |
| Flussbreite | 0,12–0,40 mm je Gewässer | Stufen nach Flussordnung | ganze Pixel |
| Koordinatennetz | schwarz | fehlt | Gerät hat eigenes Gitter |
| Kurvenbeschriftung | einzelne Zählkurven | Garmin beschriftet selbst | Gerät |

Abweichungen je Objekt: [soll-ist.md](soll-ist.md).

## Offene Punkte

- Gerätetest GPSMAP 66/67 und Montana: Breiten, Symbolgrössen, Zoomzuordnung, Nachtfarben.
- Liniendicken und Symbolgrössen für Montana 7xx (höhere Pixeldichte).
- Kloster, Stiftsbezirk und Spital in der St. Galler Altstadt fehlen bei 150 m. Ursache ist die
  Labeldichte **(unsicher)**.
- `Strasse in Bau`, Brücken und Galerien als eigene Signaturen.
- Blaue Tiefenlinien der Seen (`T55_DKM25_TIEFENLINIE`).
