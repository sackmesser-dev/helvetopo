# Vektor-Basiskarte (FID 7701)

Stand: 2026-11-04. Code: `src/vector/`. Tags: [tag-schema.md](../daten/tag-schema.md).

Der Konverter liest swisstopo-Daten und schreibt eine OSM-PBF. OSM dient nur als Dateiformat.
splitter und mkgmap bauen daraus die IMG.

## Inhalt

- Strassen und Wege mit Routing-Attributen, Bahn und Seilbahn, Gewässer, Bodenbedeckung, Areale
- Gebäude und Bauten, generalisierte Siedlungsflächen, Einzelbäume in LK-Dichte
- Grenzen, Adressen (amtliches Gebäudeadressverzeichnis), Namen (swissNAMES3D), POIs
- Platz-Namenpunkte, LK-Objektnamen (Annotationen aus Swiss Map Vector 25), Einwohnerzahlen
- Zugehörigkeit zu Veloland, Mountainbikeland und Wanderland

Die PBF enthält keine OSM-Daten, keine OSM-`bounds` und keine `sea`-Daten. Die Quellenangabe steht
in `ch.osm.pbf.sources`: `©swisstopo` und `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`
(wegen der Routenattribute).

## Eingabedaten

Alle Daten kommen aus dem STAC-Katalog `data.geo.admin.ch` und liegen unter `downloads/`.

| Datensatz | Stand | Datei | Grösse |
|---|---|---|---|
| swissTLM3D | 2026-02 | `downloads/swisstlm3d/SWISSTLM3D_2026_LV95_LN02.gpkg` | 4,8 GB ZIP, 10,8 GB entpackt |
| swissNAMES3D | 2026 | `downloads/swissnames3d/swissnames3d_2026_2056.gpkg` | 460 MB |
| swissBOUNDARIES3D | 2026-01 | `downloads/swissboundaries3d/swissBOUNDARIES3D_1_5_LV95_LN02.gpkg` | 74 MB |
| Gebäudeadressverzeichnis | Download 2026-11-03 | `downloads/gebaeudeadressen/amtliches-gebaeudeadressverzeichnis_ch_2056.csv` | 470 MB |
| Strassenverzeichnis | Download 2026-11-03 | `downloads/strassenverzeichnis/amtliches-strassenverzeichnis_ch_2056.csv` | 25 MB |
| Swiss Map Vector 25 (nur Annotationen) | 2026 | `downloads/` | |
| SchweizMobil-Routen (Zuordnung) | Download 2026-11-03 | CSV aus `src/routes/` | |

swissTLM3D gibt es im STAC nur für die ganze Schweiz. Der Konverter liest per Bounding-Box direkt
aus dem GPKG (räumlicher Index). Ein Zwischen-Clip ist nicht nötig.

## Module

| Datei | Inhalt |
|---|---|
| `common.py` | Pfade, Gebiet, LV95 → WGS84, Lesen und Zuschneiden |
| `osmbuild.py` | Knoten, Wege, Relationen, gemeinsame Knoten, PBF schreiben, Kachel-IDs |
| `roads.py` | Strassen und Wege, Routing, Verbindungen, Rampen, Barrieren, Fähren |
| `features.py` | Bahn, Gewässer, Bodenbedeckung, Areale, Gebäude, Bauten, Bäume, Siedlungsflächen |
| `names.py`, `pois.py`, `extras.py`, `anno.py`, `population.py` | Namenpunkte, POIs, Platznamen, LK-Annotationen, Einwohnerzahlen |
| `addresses.py`, `admin.py` | Adressen, Zuordnung zu Gemeinde und Kanton, Grenzlinien |
| `routes_attr.py` | Attribute von Veloland, Mountainbikeland, Wanderland aus der Routen-CSV |
| `netz.py` | Netzkonnektivität je Zoomstufe (`swisstopo:netz_res`), je Kachel |
| `rivers.py` | Flussordnung (Strahler, Länge oberhalb, Gewässerklasse), landesweit mit Cache `work/vector/cache/` |
| `convert.py` | Konverter für ein Gebiet oder eine Kachel |
| `build_ch.py` | Landesbuild in Kacheln |
| `build_img.sh` | Prüf-IMG mit dem mkgmap-Default-Stil |
| `check_routing.py` | Routing-Prüfung direkt auf der PBF |

## Aufruf

Python 3.13 im venv `.venv/` (Python 3.15 hat nicht für alle Pakete Wheels):

```bash
python3.13 -m venv .venv && .venv/bin/pip install pyogrio shapely pyproj numpy pandas geopandas osmium
```

Testgebiet (9.00–9.50° O / 47.20–47.50° N):

```bash
.venv/bin/python -m src.vector.convert --out work/vector/testgebiet.osm.pbf \
    --routes-csv work/routes/tlm_routes.csv
src/vector/build_img.sh work/vector/testgebiet.osm.pbf work/vector/img
.venv/bin/python -m src.vector.check_routing work/vector/testgebiet.osm.pbf
```

Ganze Schweiz:

```bash
.venv/bin/python -m src.vector.build_ch --out work/vector/ch --jobs 4 \
    --routes-csv work/routes-ch/tlm_routes.csv
```

`build_img.sh` baut nur eine Prüfkarte mit dem Default-Stil. Die ausgelieferte Karte baut
`src/build/build_all.sh` mit dem Stil `src/style/swisstopo/` (siehe [build.md](../build/build.md)).

## Laufzeiten

Mac mit Apple Silicon, 14 Kerne, 48 GB RAM.

| Schritt | Zeit | Speicher |
|---|---|---|
| Testgebiet `convert.py` | ca. 2 min | ca. 3 GB |
| Testgebiet splitter und mkgmap (Default-Stil) | ca. 15 s | |
| Landes-PBF `build_ch.py`, 62 Kacheln, 4 parallel | 14–17 min | ca. 3 GB je Kachel |
| `osmium merge` und `osmium renumber` | 1,5–2,5 min | 3,6 GB |
| splitter ganze Schweiz (160 Kacheln) | 4 min | 11,3 GB (Heap 16 GB) |
| mkgmap ganze Schweiz (Default-Stil) | 3 min | |

Landes-PBF: 1,33 GB, ca. 169 Mio. Knoten, 8,27 Mio. Wege, 31 600 Relationen.

## Konvertierungsregeln

### Koordinaten und Topologie

- PROJ wählt für EPSG:2056 → EPSG:4326 die Transformation „CH1903+ to WGS 84 (1)“ (Helmert, ca.
  1 m Genauigkeit). Das Garmin-Raster ist ca. 2,4 m. Die Koordinaten werden auf 1e-7° gerundet.
- swissTLM3D ist an Kreuzungen sauber genodet. Im Testgebiet trifft kein Linienende auf einen
  Zwischenpunkt einer anderen Strasse (0 von 90 954 Endpunkten). Gleiche Koordinaten ergeben
  deshalb denselben Knoten. Ein Snapping mit Toleranz ist nicht nötig.
- Richtungsgetrennte Fahrbahnen, Autobahnen, Ein- und Ausfahrten und Kreisel sind in Fahrrichtung
  digitalisiert (Stichprobe: Autobahn 214 von 214, Kreisel 415 von 418). Sie bekommen
  `oneway=yes` ohne Umkehrung. 5 Rampenstücke liegen entgegen der Fahrrichtung. Der Konverter dreht sie um.

### Strassen, Wege, Zugang

- Die Zuordnung Breitenklasse → `highway` ist eine Annahme (z. B. `4m Strasse` → `residential`,
  `3m Strasse` mit Hartbelag → `service`). Die Darstellung verwendet `swisstopo:objektart`.
- `Allgemeine Verkehrsbeschraenkung` bedeutet in der Regel Fahrverbot mit Zubringerdienst. Strassen
  ab 4 m bekommen `motor_vehicle=destination`, schmalere `motor_vehicle=no`.
- Durchfahrtssperre → `barrier=bollard` (Motorfahrzeuge gesperrt, Fuss und Velo frei).
- `2m Weg` → `motor_vehicle=no`. `1m Weg` mit Naturbelag → `bicycle=no`.
- Wanderweg → `sac_scale=hiking`, Bergwanderweg → `mountain_hiking`, Alpinwanderweg →
  `alpine_hiking`. Feinere T-Stufen gibt es in swissTLM3D nicht.
- Flüsse: `waterway=river`, wenn das Gewässer (gleiche `gewiss_nr`) eine Wasserfläche
  „Fliessgewaesser“ der Bodenbedeckung schneidet, sonst `stream`.

### Flächen und POIs

- Regel „Fläche plus genau ein POI“: Gebäude-Footprints tragen nur `building=*`, Areale nur
  Flächen-Tags (`landuse` usw.). Der Name steht an der Fläche in `swisstopo:name`. POI-Tags und
  `name` stehen nur am POI-Knoten aus `pois.py`.
- POIs gleicher Art und gleichen Namens im Umkreis von 100 m werden zusammengelegt.
- LK-Annotationen werden mit einem POI derselben Klasse im Umkreis von 150 m zusammengelegt, wenn
  der Text passt (`anno.text_matches`). Ist der LK-Text nur die Gattung des POI-Namens (z. B.
  „Burgruine“, `anno.is_generic_of`), gilt ein Radius von 300 m. Der POI-Name wird dann das Label,
  der LK-Text `alt_name`.
- Historische Areale bekommen die Art aus dem Namen (`historic=ruins`, `castle` usw.).
- Bewusst nicht übernommen: Einzelobjekte `Wasserversorgung` ohne Name (7393) und `Antenne klein`
  (6544). `Landesgrenzstein` kommt nur über swissNAMES3D. `Reservoir` gibt es nur als Fläche.
- WC: Das Attribut `toiletten` in swissTLM3D ist landesweit leer. swissNAMES3D hat keine WCs. Die
  Karte hat deshalb keine WCs.

### Gebäude

- Der Konverter vereinfacht Footprints in LV95 mit 0,2 m (`features.BUILDING_SIMPLIFY_M`). Nur
  kollineare Zwischenpunkte fallen weg. swissTLM3D zerlegt gerade Wände in Stücke von 3–5 m.
  mkgmap rundet jeden Punkt auf das Garmin-Raster (1,6 × 2,4 m). Ohne Vereinfachung entsteht ein
  Zickzack. Mittel: 12,7 → 5,9 Punkte je Gebäude.
- Das Runden auf das Raster der Auflösung 24 macht rechte Winkel schief. Die TLM-Grundrisse weichen im
  Median 0,1° vom rechten Winkel ab. Gerundet weichen die Eckwinkel im Median 4,7° vom Original ab, 6 %
  um mehr als 22° (Befund Niederuzwil, Friedeckstrasse/Bahnhofstrasse). Der Konverter richtet die
  Gebäude deshalb vor dem Schreiben aus (`src/vector/gebaeude_raster.py`):
  - Kein Puffer (`BUFFER_M = 0`, Gerätetest GPSMAP 67, 2026-11-08). Mit `BUFFER_M > 0` wächst jeder
    Grundriss (geschlossener Weg) zuerst nach aussen, mit spitzen Ecken. Multipolygone bleiben ohne
    Puffer. Schlitze unter 2 × `BUFFER_M` zwischen Nachbarteilen schliessen sich dann beim Runden, aber
    die Häuser werden dicker. Mit 0,4 m wächst die sichtbare Gebäudefläche im Testgebiet um 10,4 %, mit
    0,15 m um 4,2 %, ohne Puffer um 0,5 %. Am Gerät gab es mit 0,4 m in Dörfern und Städten zu viel
    Schwarz. Der Benutzer wählte die Variante ohne Puffer. Vergleich: [Stil](../stil/stil.md#garmin-grenzen).
  - Gruppe: alle `building=*` (auch Dächer und Multipolygone), deren Flächen sich überlappen, ineinander
    liegen oder weniger als 0,05 m voneinander entfernt sind. Eine Gruppe bekommt eine gemeinsame Lage.
  - Lage: Drehung um den Schwerpunkt bis ±3° und Verschiebung bis ±0,5 Rastereinheiten. Die Suche ist
    zuerst grob (Schritte 0,5° und 0,25 Einheiten), danach fein (0,25° und 0,125 Einheiten).
  - Ziel: Die gerundeten Eckwinkel gleichen den Originalwinkeln möglichst. Ecken, die beim Runden
    zusammenfallen, kosten sehr viel. Jede Ecke kostet 4 je m² Bewegung durch Drehung und Verschiebung.
    Keine Ecke bewegt sich mehr als 2 m. Ohne diese Grenze dreht sich eine grosse Gruppe
    (Industrieareal) um den Schwerpunkt, und ihre äusseren Ecken wandern bis 8 m.
  - Verworfen: gemeinsame Knoten an T-Stellen (Ecke auf der Wand eines Nachbarn). Gerundet liegen sie
    fast nie auf der gerundeten Wand. Die Wände bekommen Knicke, im Test 716 statt 231.
  - Ergebnis Niederuzwil mit Puffer 0,4 m (9,130–9,160° O, 47,437–47,452° N, 2806 Gebäude,
    1317 Gruppen): Abweichung der Eckwinkel im Median 4,7° → 1,8°, P90 18,7° → 13,5°. Lücken zwischen
    gerundeten Nachbarteilen (Schliessen mit 0,6 m): 239 → 99 m². Laufzeit: 0,3 s.
  - Ergebnis Testgebiet ohne Puffer (204 771 Gebäude, 104 851 Gruppen): Abweichung der Eckwinkel im
    Median 5,9° → 2,2°, P90 21,7° → 16,4°.
  - Knoten, die ein Gebäude mit einer Netzlinie teilt (Strasse, Bahn, Gewässer, Mauer), bleiben an ihrem
    Ort. Gepufferte Grundrisse (nur mit `BUFFER_M > 0`) haben immer eigene Knoten. Mit Flächen
    (Areale, Landnutzung) geteilte Knoten verschieben sich mit. Im Kachelbuild bekommen verschobene
    Knoten eine Kachel-ID. Knoten ohne Tags, die kein Weg mehr braucht, schreibt der Builder nicht.
  - Der Schalter `--ohne-gebaeude-raster` von `convert.py` lässt die Ausrichtung weg (Vergleich).
- mkgmap vereinfacht Polygone mit Douglas-Peucker (Standard 2,6 Einheiten, doppelt je Stufe). Ohne
  Anpassung werden kleine Gebäude in Auflösung 23 und 22 zu Dreiecken oder fehlen. Der Build setzt
  deshalb `--simplify-polygons=24:0,23:0,22:0,21:2.6`. Danach bleiben in Auflösung 23 79 von 1722
  Gebäuden Dreiecke (Kleinstbauten unter dem 4,8-m-Raster). Die Kacheln werden dadurch 16 % grösser.
- Mauern (`Mauer gross`, `Mauer gross gedeckt`, landesweit 11 422) sind keine Gebäude. Sie bekommen
  `barrier=wall`, `area=yes`, `swisstopo:mauer=gross`, im Historischen Areal zusätzlich
  `swisstopo:historisches_areal` und bei Ruinen `ruins=yes`. `Historische Baute` → `building=ruins`.

### Bahn

swissTLM3D hat bei Mehrspurstrecken eine DKM-Achse (`achse_dkm=Wahr`, `anzahl_spuren=2`) und
daneben jedes Gleis als eigene Achse. Der Konverter setzt `swisstopo:achse_dkm` an allen Bahnachsen
und `swisstopo:parallelachse=yes` an Gleisachsen, die zu mindestens 80 % höchstens 8 m neben einer
Mehrspurachse gleicher Spurweite liegen (`features.parallel_axes`). Landesweit betrifft das 9784
von 19 372 Nicht-DKM-Achsen. Der Stil zeichnet Parallelachsen nicht.

### Generalisierung

- Generalisierte Siedlungsflächen und `swisstopo:netz_res` steuern, was in groben Zoomstufen
  erscheint (siehe Tag-Schema).
- Routbare Strassen werden nicht vereinfacht. Eine Vereinfachung ändert Routing und Längen.
- Für die Stufen 16–21 sind eigene, nicht routbare Darstellungslinien möglich
  (`swisstopo:generalisiert=strasse`). Sie sind nicht umgesetzt.

## Adresssuche

mkgmap braucht für den Suchindex Land, Region und Ort je Objekt. Die üblichen `bounds` von
mkgmap.org.uk stammen aus OSM (ODbL). Helvetopo verwendet sie nicht.

- Der Konverter setzt `is_in:country=CH`, `is_in:county=<Kanton>` und `is_in:city=<Gemeinde>` an
  jedem Objekt (Punkt-in-Polygon mit swissBOUNDARIES3D). `inc/address` im Stil macht daraus
  `mkgmap:country`, `mkgmap:region` und `mkgmap:city`.
- Build-Optionen: `--location-autofill=is_in,nearest`, `--country-name=Schweiz`, `--country-abbr=CHE`.
- Benannte Punkte ausserhalb jeder Gemeinde (z. B. Gipfel auf der Landesgrenze wie Matterhorn und
  Dufourspitze) bekommen die nächste Gemeinde im Umkreis von 1 km.
- Die Reihenfolge „Marktgasse 20“ statt „20 Marktgasse“ kommt aus `LocatorConfig.xml` von mkgmap
  (`streetBeforeHousenumber="true"` für CHE). Sie wirkt nur, wenn das Objekt `mkgmap:country`
  trägt. Die Werte aus `--country-name` und `--country-abbr` gleicht mkgmap nicht mit
  `LocatorConfig.xml` ab. Darum braucht jedes Objekt `is_in:country`.
- Kantonskürzel in Gemeindenamen stehen ohne Klammern („Gossau SG“). Das GPSMAP 67 zeigt das Kürzel
  gross. BaseCamp setzt Titelschreibung („Gossau Sg“).
- Ergebnis: Die Suche Ort → Strasse → Hausnummer funktioniert in BaseCamp („Marktgasse 20,
  St. Gallen“, „Bahnhofstrasse 1, Zürich“).
- Möglich, aber nicht umgesetzt: eigene `bounds` aus swissBOUNDARIES3D mit dem
  `BoundaryPreprocessor` von mkgmap.

### Adressdaten

- Nur `ADR_STATUS=real`. `addr:city` ist die Gemeinde. Die Postortschaft steht in
  `swisstopo:ortschaft`, die PLZ in `addr:postcode`.
- Vierstellige Hausnummern an Strassen mit sonst normalen Nummern sind ein amtliches Muster
  (landesweit 9566, vor allem Toggenburg und Appenzell Ausserrhoden, z. B. „Sonnenwiese 1492,
  Nesslau“). Sie bleiben in der Karte.
- „Durchgangsstrasse“ (Herisau) ist ein amtlicher Strassenname (ESID 10211934). Er bleibt.
- 0,5 % der Hausnummern finden keine Strasse (Höfe ohne Strasse im Umkreis von 150 m oder
  abweichende Namen).

## Landesbuild in Kacheln

Ein einzelner Konverterlauf für die ganze Schweiz braucht 55–75 GB RAM, weil alle Knoten in einem
Python-Dict liegen (ca. 270 Byte je Knoten). `build_ch.py` konvertiert deshalb in Kacheln.

- Raster 0,4° × 0,3° über 5.95–10.50° O / 45.81–47.81° N. Nur Kacheln, die Schweiz oder
  Liechtenstein schneiden (swissBOUNDARIES3D `tlm_landesgebiet` plus 1 km), werden gebaut.
- Jede Kachel ist ein eigener Prozess (`convert.py --tile k --bbox …`). Danach folgt `osmium merge`.
- IDs im Kachelmodus: Gemeinsame Knoten bekommen die ID `(lon·1e7 << 29) | lat·1e7`. Die ID ist
  also in allen Kacheln gleich. Eigene POI-Knoten beginnen bei 2^58 + k·2^32, Wege und Relationen
  bei k·2^32. `osmium merge` schreibt gleiche Objekte nur einmal.
- Nach dem Merge vergibt `osmium renumber` dichte IDs ab 1. splitter r654 bricht mit den grossen
  Kachel-IDs auch mit 16 GB Heap ab (OutOfMemoryError).
- Der Build ist fortsetzbar: Fertige Kacheln (`tiles/tNNN.osm.pbf`) werden übersprungen. Jede Kachel
  wird zuerst als `.tmp.pbf` geschrieben. Logs je Kachel liegen in `logs/`.
- Prüfung: Wil ↔ St. Gallen über eine Kachelgrenze ergibt 28,3 km wie im Einzelbuild.

## Prüfungen

- `src/vector/check_routing.py`: Wil, Gossau, St. Gallen, Herisau, Appenzell, Schwägalp und
  Säntisgipfel sind für Auto und Fuss gegenseitig erreichbar. Distanzen: Wil → St. Gallen 28,3 km
  Auto, Schwägalp → Säntis 4,7 km zu Fuss. Von der Schwägalp führt keine erlaubte Auto- oder
  Veloroute auf den Säntisgipfel.
- mkgmap `--check-styles` meldet keine Fehler.
- Routing-Inseln: Das Strassennetz im Testgebiet hat 381 Komponenten. Die grösste umfasst
  11 279 km. Die übrigen 380 sind echte Inseln in swissTLM3D, vor allem `1m/2m Wegfragment` (309).
  Keine liegt näher als 0,5 m am Hauptnetz. Ein Snapping bringt deshalb nichts.
  `--max-routing-island-len` ist nicht gesetzt. Die Inseln bleiben routbar.

mkgmap-Meldungen im Testgebiet:

| Meldung | Anzahl | Bewertung |
|---|---|---|
| HousenumberRoad „found no plausible road“ | 681 von 146 991 | Höfe ohne Strasse oder abweichende Namen |
| Routing island | 472 | echte Inseln, durch Kachelgrenzen vervielfacht |
| LinkDestinationHook „not oneway“ | 34 | Autostrassen ohne Richtungstrennung als Rampenziel, harmlos |
| HighwayHooks „motorway exit … without ref“ | 8 | kosmetisch |
| HousenumberGroup | 15 | harmlos |
| ShapeMergeFilter | 52 | überlappende Flächen, harmlos |

## Garmin-Verhalten

- **Zielausnahme:** Garmin behandelt Zugangssperren als sehr hohe Kosten, nicht als Verbot. Ist ein
  Ziel für das Verkehrsmittel nicht erreichbar (z. B. Säntisgipfel mit Auto oder Velo), führt die
  Route am Ende über gesperrte Fusswege. Die Daten sperren korrekt (`mkgmap:car=no`,
  `mkgmap:bicycle=no`). Liegt das Ziel an einer erlaubten Strasse, meidet die Autoroute Wege
  vollständig.
- **Nur ein Label je POI:** mkgmap schreibt für POIs nur das erste Label. `mkgmap:label:2` und
  `mkgmap:label:3` wirken nur bei Linien. `alt_name` (z. B. „Mont Cervin“) ist deshalb nicht suchbar.
- **Gipfel-Labels:** Ein Label mit angehängtem Höhencode (`Matterhorn\x1f14692`) findet die
  BaseCamp-Suche nicht. Der Stil schreibt deshalb nur `${name}` als Label.
- **Massive:** swissNAMES3D führt z. B. „Pilatus“ als Massiv, nicht als Gipfel. Der Konverter setzt
  den Massivnamen an den höchsten Gipfel der Massivfläche (`natural=peak`, `name=Pilatus`,
  `swisstopo:hauptgipfel=Tomlishorn`, `swisstopo:hauptgipfel_ele=2128`, ohne `ele`). Das gilt für
  68 Massive.
- **Gleiche Labels am Gipfel:** Gleichnamige Punkte nahe beim Gipfel verdrängen sich in BaseCamp,
  auf dem GPSMAP 67 stehen sie doppelt. Am Säntis liegen der Gipfel, der Aussichtspunkt (10 m) und die
  Bergstation (87 m), alle mit dem Namen „Säntis“. Darum verliert ein Aussichtspunkt den Namen,
  wenn ein gleichnamiger Gipfel näher als 50 m liegt. Bei einer Station gilt 150 m
  (`names.drop_names_at_peaks`, CH: 29 Aussichtspunkte, 37 Stationen). Der Massivpunkt hat einen eigenen
  Typ ohne Zeichnung und ohne Label (0x6612).
- **Gipfelklassen:** Der Name eines Gipfels erscheint je nach Klasse ab Auflösung 18, 20, 21 oder 22
  (`swisstopo:gipfelklasse`, Herkunft siehe [Tag-Schema](../daten/tag-schema.md)). Säntis, Matterhorn
  und Rigi Kulm stehen so früher als Nebengipfel. Vorher war nur die Objektart massgebend.
- **Weitere Namenklassen:** Pässe (`swisstopo:passklasse`) sowie Seen, Gletscher, Gebiets- und
  Talnamen (`swisstopo:namenklasse`) folgen demselben Prinzip: Name in SMV1000, SMV500 oder
  swissTLMRegio. Flüsse sind schon nach Gewässerklasse abgestuft (`src/vector/rivers.py`).
- **Gipfelkote unter dem Namen:** Liegen Name und Kote auf demselben Punkt, zeigt das GPSMAP 67 nur den
  Namen (Gerätetest 7794-klassen: „2502“ am Säntis fehlte). Der Konverter setzt die Kote darum als eigenen
  Punkt unter den Gipfel, je Auflösung r einen Punkt 12 Karteneinheiten (12 · 360°/2^r) weiter südlich.
  Der Stil zeichnet ihn nur in seiner Auflösung. So bleibt der Abstand auf dem Bildschirm etwa gleich.
- **Typname als Wegname:** BaseCamp nennt in der Wegbeschreibung für unbenannte Kanten den Typnamen
  aus der TYP-Datei.
- **Ortssuche in BaseCamp:** Orte findet man über Suchen → „Points of Interest suchen“ → „Städte“.

## Bekannte Grenzen

1. **Auto-Routing nur topografisch.** swissTLM3D hat keine Einbahnen auf normalen Strassen (nur
   richtungsgetrennte Fahrbahnen und Kreisel), keine Abbiegeverbote, keine Fahrstreifen und keine
   Tempolimits. Das steht in Kartenbeschreibung, LICENSE und README.
2. **Velo-Bevorzugung begrenzt.** Siehe [routing.md](routing.md).
3. **Strassenklassen sind abgeleitet** aus Breitenklasse, Route und Verkehrsbedeutung.
4. **Kachelgrenzen im Landesbuild:** Eine Barriere genau auf einer Kachelgrenze kann ihren Tag
   verlieren. Die POI-Zusammenlegung (100 m) wirkt nur innerhalb einer Kachel.
5. **Darstellungslücken bei Siedlungsflächen:** Die generalisierten Flächen sind in PBF und IMG
   vollständig. Lücken in der Darstellung entstehen im Stil (gleiche drawOrder von `0x4b` und
   `0x1100e`, weiss gefüllte Nebenstrassen in Auflösung 21).
