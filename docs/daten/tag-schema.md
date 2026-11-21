# Tag-Schema swissTLM3D → OSM-PBF

Stand: 2026-11-04 (Landes-PBF `ch-final4`). Das Tag-Schema ist die Schnittstelle zwischen dem
Konverter (`src/vector/`) und dem mkgmap-Stil bzw. der TYP-Datei (`src/style/`). Jede Änderung am
Schema gehört in diese Datei.

Grundsätze:

- Die PBF enthält **nur** swisstopo-Daten (OGD). OSM dient nur als Dateiformat.
- Standard-OSM-Tags, damit der mkgmap-Default-Style schon brauchbar ist (Routing, Index).
- Jedes Objekt behält seine Herkunft in `swisstopo:*`-Tags. Der Stil soll für die Darstellung
  primär `swisstopo:objektart` verwenden, weil das die Klassen der Landeskarte sind
  (z. B. „4m Strasse“). `highway=*` ist vor allem für Routing und Suche da.
- Werte `k_W` („kein Wert“) aus swissTLM3D werden nicht übernommen.
- Koordinaten: LV95 (EPSG:2056) → WGS84 mit PROJ (Transformation „CH1903+ to WGS 84 (1)“),
  Z verworfen, auf 1e-7° gerundet (OSM-Auflösung). Gleiche Koordinaten = gleicher Knoten.

Datenstand: swissTLM3D 2026-02, swissNAMES3D 2026, swissBOUNDARIES3D 2026-01, Swiss Map Vector 25
(2026, nur Annotationen), amtliches Gebäudeadressverzeichnis und Strassenverzeichnis vom Download
2026-11-03. Optional Veloland/Mountainbikeland/Wanderland/Skatingland (ASTRA/SchweizMobil, über die
CSV aus `src/routes/`).

Übersicht der Objektgruppen (Details in den Abschnitten unten):

| Gruppe | Merkmal-Tag | Abschnitt |
|---|---|---|
| Strassen/Wege mit Routing | `highway`, `swisstopo:objektart` | Strassen und Wege |
| Routenzugehörigkeit | `route_bicycle`, `mtb`, `ch:*land` | Routenzugehörigkeit |
| Adressen | `addr:*` | Adressen |
| Siedlungsflächen (grob) | `swisstopo:generalisiert=siedlung` | Generalisierte Siedlungsflächen |
| Platz-Namenpunkte | `swisstopo:namenpunkt=platz` | Platz-Namenpunkte |
| LK-Objektnamen | `swisstopo:anno` | SMV25-Annotationen |
| Einzelbäume | `natural=tree` | Einzelbäume |
| POIs | `swisstopo:poi` | POIs |
| Ortsnamen mit Einwohnerzahl | `place`, `population` | Namen und Punkte |
| Lagezuordnung | `is_in:country/county/city` (an allen Strassen, Adressen und benannten Punkten) | Adresszuordnung |

Nicht (mehr) enthalten: Waldrandlinien (Entscheid: SMV25 zeichnet Wald ohne Rand),
POI-Tags und Namen an Gebäude- und Arealflächen (stehen an den POI-Knoten).

## Kantonskürzel in Namen

Einheitlich „Ort KT“ ohne Klammern („Gossau SG“, „Stein AR“), Kürzel gross. Quellen: BFS-Gemeindenamen
(swissBOUNDARIES3D, Adressverzeichnis `COM_NAME` → `is_in:city`, `addr:city`) schreiben „Gossau (SG)“.
Die Ortschaften (PLZ-Verzeichnis), swissNAMES3D-Siedlungen (`place=*`) und ÖV-Haltestellen schreiben „Gossau SG“.
Beim Schreiben der PBF (`osmbuild.canton_form`) wird „ (KT)“ in `name`, `alt_name`, `is_in:city`,
`addr:city`, `swisstopo:name`, `swisstopo:amtlicher_name` zu „ KT“. BaseCamp zeigt Wörter aus lauter
Grossbuchstaben in der Suche als „Sg“ (Darstellung, nicht Daten, Test `work/vector/schreibtest/`).

## Gemeinsame swisstopo-Tags

| Tag | Inhalt |
|---|---|
| `swisstopo:layer` | Quell-Layer, z. B. `tlm_strassen_strasse` |
| `swisstopo:objektart` | Originalwert `objektart`, z. B. `4m Strasse`, `Wald` |
| `swisstopo:uuid` | UUID des TLM-Objekts (zur Rückverfolgung) |
| `source` | `swisstopo` |

## Strassen und Wege (`tlm_strassen_strasse`)

### Klasse

Reihenfolge der Regeln: die erste passende gilt.

| Bedingung | `highway` | Zusätze |
|---|---|---|
| objektart `Autobahn` | `motorway` | `oneway=yes` |
| objektart `Ausfahrt`, `Einfahrt` | `motorway_link` | `oneway=yes` |
| objektart `Autostrasse` | `trunk` | `motorroad=yes` |
| objektart `Raststaette`, `Zufahrt` | `service` | |
| objektart `Dienstzufahrt` | `service` | `access=no`, `service=emergency_access` |
| Breitenklasse (`10m`/`8m`/`6m`/`4m`/`3m Strasse`) auf einer Strassenroute `HLS Bund`/`HLS Kanton`/`Nationalstrasse` | `trunk` | |
| Breitenklasse auf Route `Hauptstrasse A` oder `verkehrsbedeutung=Hochleistungsstrasse` | `primary` | |
| Breitenklasse auf Route `Hauptstrasse B/C` oder `verkehrsbedeutung=Durchgangsstrasse` | `secondary` | |
| Breitenklasse mit `verkehrsbedeutung=Verbindungsstrasse` oder `eigentuemer=Kanton/Bund` | `tertiary` | |
| `10m Strasse`, `8m Strasse` | `tertiary` | |
| `6m Strasse` | `unclassified` | |
| `4m Strasse` | `residential` | |
| `3m Strasse` mit `belagsart=Hart` | `service` | |
| `3m Strasse` mit `belagsart=Natur` | `track` | `tracktype=grade2` |
| `2m Weg` mit `befahrbarkeit=Wahr` | `track` | `tracktype=grade1` (Hart) / `grade3` (Natur) |
| `2m Weg` sonst | `path` | |
| `1m Weg` | `path` | |
| `1m Wegfragment`, `2m Wegfragment` | `path` | `trail_visibility=intermediate` |
| `Markierte Spur` | `path` | `trail_visibility=bad` |
| `Platz` mit Verkehrsbeschränkung | `pedestrian` | |
| `Platz` sonst | `service` | |
| `Faehre` | – | `route=ferry` (siehe Fähren) |
| `Verbindung` | geerbt | siehe unten |

`Verbindung` (kurze Netz-Verbinder, Median 5 m, z. B. Autobahn ↔ Ausfahrt oder Weg ↔ Strasse)
erbt die **niedrigere** der beiden besten Klassen an den Enden. Verbindet sie Einbahnstrecken
(Autobahn, Rampen), wird sie `oneway=yes`. Ihre Digitalisierrichtung ist nicht verlässlich. Der
Konverter dreht deshalb ein Stück um, wenn alle drei Bedingungen gelten:

- Am Anfang kommt keine Einbahn an.
- Am Anfang beginnt eine Einbahn.
- Am Ende endet eine Einbahn.

Im Testgebiet betrifft das 5 Stücke an Autobahnanschlüssen.

Ein-/Ausfahrten: topologisch geprüft. 54 von 79 Ausfahrten sind über Verbindungen von der Autobahn
erreichbar und führen ins übrige Netz. 16 hängen an Autostrassen (`trunk`), 7 liegen am Rand
des Testgebiets, 1 hängt an einer Dienstzufahrt, 1 führt nicht ins übrige Netz. Einfahrten
entsprechend (59 vollständig, 22 an Autostrassen bzw. am Rand).

Kunstbauten mit Treppe (`kunstbaute=Treppe`, `Bruecke mit Treppe`, `Unterfuehrung mit Treppe`)
auf Weg-Klassen (`path`, `footway`, `track`, `pedestrian`) werden `highway=steps`.

### Routing-Attribute

| Quelle | OSM-Tags |
|---|---|
| `richtungsgetrennt=Wahr` | `oneway=yes` in Digitalisierrichtung. Geprüft: Fahrbahnen der A1 zeigen in Fahrrichtung, die Gegenfahrbahn liegt bei 126 von 126 auswertbaren Abschnitten links (Rechtsverkehr). Übrige richtungsgetrennte Strassen: 94 links, 6 rechts (Kurven/Verzweigungen). Anschlüsse Ende→Anfang 961 von 983 |
| `kreisel=Wahr` | `junction=roundabout` (Einbahn implizit). Geprüft: 415 von 418 Kreiselstücken gegen den Uhrzeigersinn, mkgmap `--report-roundabout-issues=all` meldet keine Richtungsfehler. Keine Umorientierung |
| `belagsart=Hart` / `Natur` | `surface=paved` / `surface=unpaved` |
| `kunstbaute=Bruecke`, `Steg` | `bridge=yes`, `layer=<stufe>` (mind. 1) |
| `kunstbaute=Gedeckte Bruecke` | `bridge=covered`, `layer` |
| `kunstbaute=Bruecke mit Galerie` | `bridge=yes`, `covered=yes`, `layer` |
| `kunstbaute=Tunnel`, `Unterfuehrung` | `tunnel=yes`, `layer=<stufe>` (max. −1) |
| `kunstbaute=Galerie` | `tunnel=avalanche_protector`, `layer` |
| `kunstbaute=in/auf Gebaeude` | `covered=yes` |
| `kunstbaute=Furt` | `ford=yes` |
| `stufe≠0` (ohne Kunstbaute) | `layer=<stufe>` |
| `verkehrsbeschraenkung=Allgemeine Verkehrsbeschraenkung` | Strassen ab 4 m: `motor_vehicle=destination` (**Annahme**: Fahrverbot mit Zubringerdienst). Schmaler: `motor_vehicle=no` |
| `verkehrsbeschraenkung=Allgemeines Fahrverbot`, `Gesperrt` | `motor_vehicle=no` |
| `verkehrsbeschraenkung=Zeitlich geregelt` | `motor_vehicle=destination` |
| `verkehrsbeschraenkung=Militaerstrasse`, `Panzerpiste`, `Rennstrecke`, `Teststrecke` | `access=private` (**Annahme**) |
| `verkehrsbeschraenkung=Gesicherte Kletterpartie` | `via_ferrata=yes`, `bicycle=no`, auf Wegen `sac_scale` mindestens `alpine_hiking` |
| `befahrbarkeit=Falsch` | `motor_vehicle=no` |
| `path`, `steps`, `pedestrian` | `motor_vehicle=no` |
| `track` aus `2m Weg` (auch mit `befahrbarkeit=Wahr`) | `motor_vehicle=no`, `agricultural=yes`, `forestry=yes` (**Annahme**: Feld-/Waldwege) |
| `track` aus `3m Strasse` (Natur) | befahrbar, ausser `befahrbarkeit=Falsch` oder Verkehrsbeschränkung |
| `motorway`, `motorway_link`, `trunk` mit `motorroad` | `bicycle=no`, `foot=no` |

Velo auf Wegen (**Annahme**, nach Breite, Belag und Schwierigkeit):

| Weg | `bicycle` |
|---|---|
| `track`, `2m Weg` | `yes` |
| `1m Weg` mit Hartbelag (Wanderweg oder ohne) | `yes` |
| `1m Weg` mit Naturbelag | `no` |
| `1m Weg` als Berg- oder Alpinwanderweg | `no` |
| `1m/2m Wegfragment`, `Markierte Spur` | `no` |
| `steps` | `no` |

Was swissTLM3D **nicht** enthält: Einbahnen auf normalen Strassen, Abbiegeverbote, Fahrstreifen,
Tempolimits. Das Auto-Routing ist deshalb nur topografisch (siehe Kartenbeschreibung und
`docs/vektor/basiskarte.md`). Schwerpunkt ist das Fuss- und Velorouting.

Alle Originalwerte bleiben erhalten: `swisstopo:kunstbaute`, `swisstopo:belagsart`,
`swisstopo:befahrbarkeit`, `swisstopo:verkehrsbeschraenkung`, `swisstopo:verkehrsbedeutung`,
`swisstopo:eigentuemer`, `swisstopo:stufe`, `swisstopo:richtungsgetrennt`.

### Netzkonnektivität je Zoomstufe (`swisstopo:netz_res`, `src/vector/netz.py`)

`swisstopo:netz_res=19|20|21|22|23`: tiefste Auflösung, ab der der Abschnitt gezeichnet werden soll,
damit keine Strassenstücke in der Luft hängen. Der Stil nimmt den Wert statt der Klassen-Startstufe.
Kein Tag an Ankern (Autobahn, Autostrasse, Aus-/Einfahrt, Zufahrt, Raststätte, Verbindung, alles mit
Verkehrsbedeutung ausser 2m Weg) und an Treppen, Klettersteigen, Fähren, Autozug.

| Basisstufe | Klassen |
|---|---|
| 19 | Kantonsstrassen 4m–10m (`eigentuemer=Kanton`) ohne Verkehrsbedeutung |
| 21 | 6m/8m/10m Strasse, 4m und 3m Strasse mit Hartbelag |
| 22 | Platz, Dienstzufahrt, Naturbelag, 2m/1m Weg, Wegfragmente, Markierte Spur |

Ablauf je Stufe r = 19 … 22:

1. Sichtbar sind Anker, Abschnitte mit Basis ≤ r und alles, was in r−1 sichtbar war.
2. Eine Komponente ist verankert, wenn eine Bedingung gilt: Sie enthält einen Anker. Sie liegt am
   Rand des Rechengebiets. Sie ist länger als A_r (19/20: 5 km, 21: 2 km, 22: 1 km).
3. Eine nicht verankerte Komponente bekommt den kürzesten Pfad ≤ P_r aus noch unsichtbaren
   Abschnitten (19/20: 800 m, 21: 400 m, 22: 250 m). In 19–21 nur über Strassen, in 22 auch über
   Wege, Treppen und Klettersteige. Die Abschnitte des Pfads werden hochgestuft.
4. Gibt es keinen solchen Pfad, bleibt die Komponente in r versteckt. Reine Wegfragment-Stücke
   bleiben in 22 immer versteckt.

Als Verbindung gelten gemeinsame Endpunkte und T-Anschlüsse (Endpunkt ≤ 0,5 m neben einem anderen
Abschnitt). Was bis 22 nie sichtbar ist, bekommt 23.

### Wanderwege

| `wanderwege` | Weg-Klassen (`path`, `track`, `steps`, `footway`, `pedestrian`) | alle Klassen |
|---|---|---|
| `Wanderweg` | `sac_scale=hiking` (T1) | `swisstopo:wanderweg=Wanderweg`, `hiking=yes` |
| `Bergwanderweg` | `sac_scale=mountain_hiking` (T2–T3) | `swisstopo:wanderweg=Bergwanderweg`, `hiking=yes` |
| `Alpinwanderweg` | `sac_scale=alpine_hiking` (T4+) | `swisstopo:wanderweg=Alpinwanderweg`, `hiking=yes` |

Auf befahrbaren Strassen wird kein `sac_scale` gesetzt. Die feinere Unterscheidung T2/T3 bzw.
T4/T5/T6 ist in swissTLM3D nicht enthalten (Annahme: jeweils untere Stufe).

### Routenzugehörigkeit Velo/MTB/Skating/Wandern (optional, `--routes-csv`)

Quelle: `tlm_routes.csv` aus routes-overlay (`src/routes/match_tlm.py`, Zuordnung ASTRA-Route ↔
TLM-Kante über `uuid`, siehe `docs/vektor/routen.md`). Werte `netz:nummer;…`.

| Bedingung (CSV) | Tags |
|---|---|
| `veloland` | `ch:veloland=<…>`, bestes Netz als `ncn=yes` / `rcn=yes` / `lcn=yes` und `route_bicycle=national\|regional\|local` |
| `mountainbikeland` | `ch:mountainbikeland=<…>`, `mtb=designated`, `route_mtb=national\|regional\|local` |
| `skatingland` | `ch:skatingland=<…>`, `inline_skates=designated` |
| `wanderland` | `ch:wanderland=<…>` |
| Veloland oder Mountainbikeland | `bicycle=designated` (hebt `bicycle=no` der Wegbreiten-Regel auf). **Nicht** bei Sperren (`verkehrsbeschraenkung` Gesperrt, Militaerstrasse, Panzerpiste, Renn-/Teststrecke, Gesicherte Kletterpartie, `access=no/private`) und nicht auf Autobahnen. Solche Fälle zählt das Log als Konflikt |

Für das Velo-Profil kann der Stil `route_bicycle`/`route_mtb` in eine höhere
`mkgmap:road-speed-class` übersetzen (nur auf Kanten mit `motor_vehicle=no`, siehe Regelvorschlag in
`docs/vektor/routen.md`). Routennamen kommen nicht in die Basiskarte.

**Lizenzfolge:** Mit diesen Attributen schreibt der Konverter `<pbf>.sources`, und `build_img.sh`
setzt „©swisstopo. Bundesamt für Strassen, Kanton, Stiftung SchweizMobil“ in beide Copyright-Zeilen,
in die Beschreibung und die Lizenzdatei.

Testgebiet: 9 959 Kanten mit Routenattribut, davon 4 474 `route_bicycle`, 1 934 `mtb=designated`,
5 914 `bicycle=designated` (37-mal `bicycle=no` aufgehoben), keine Konflikte mit Sperren.

### Namen und Nummern

| Quelle | Tag |
|---|---|
| `strassenname` (aus amtlichem Strassenverzeichnis) | `name` (unverändert, auch ungewöhnliche Namen wie „Durchgangsstrasse“ in Herisau: amtlicher Eintrag ESID 10211934, `STR_TYPE=Street`, `STR_OFFICIAL=true`) |
| `name` (Kunstbaute, z. B. „Sitterviadukt“) | `bridge:name` bzw. `tunnel:name`, ohne `strassenname` auch `name` |
| Strassenroute `routennummer` (via `tlm_strassen_strassenroute_strasse`) | `ref` (z. B. `A1`, `7`, mehrere mit `;`), Nationalstrassen-Nummer (`N1`) in `nat_ref` (nur ohne andere Nummer auch in `ref`), Europastrassen in `int_ref` |
| Strassenname-ESID (via `tlm_strassen_strassenname_strasse`) | `swisstopo:esid` |

**Nummern für Garmin-Shields**. `ref` bleibt unverändert, enthält aber auch
nicht signalisierte Nummern. Für Shields deshalb diese Tags verwenden (gekürzt auf die
signalisierte Nummer: `A1H`/`A1L`/`A1R` → `A1`, `112.1` → `112`):

| Tag | Inhalt | Schild in der Schweiz |
|---|---|---|
| `swisstopo:shield_autobahn` | Autobahn/Autostrasse aus `HLS Bund`/`HLS Kanton` mit A-Nummer: `A1`, `A13` | rot, weisse Zahl |
| `swisstopo:shield_hauptstrasse` | nur `Hauptstrasse A` (1–30, 2a, 2b): `7`, `13` | blau, weisse Zahl |
| `swisstopo:shield_europa` | `E60`, `E43` | grün |
| `swisstopo:shield` | führende Schildart: `autobahn` > `hauptstrasse` > `europa` | – |
| `swisstopo:hauptstrasse_nr_intern` | Nummern der Hauptstrassen B/C (100–599), Verwaltungsnummern, nicht signalisiert, **kein Shield** | – |

Mehrere Nummern mit `;`, kürzere zuerst. Nationalstrassen-Nummern (`N1`) bleiben nur in `nat_ref`.
Autobahnanschlüsse tragen ihre Nummer in `ref` (OSM-Standard) und zusätzlich in
`swisstopo:ausfahrt_nr`, damit der Stil sie nicht mit Strassennummern verwechselt.

### Adresszuordnung (für `--index`/`--housenumbers`)

Ohne OSM-`bounds` setzt der Konverter die Lage direkt (Punkt-in-Polygon mit swissBOUNDARIES3D):

| Tag | Inhalt |
|---|---|
| `is_in:country` | `CH` an **jedem** Objekt (Strassen, Adressen, alle benannten Punkte). Im Ausland `<icc>`, z. B. `LI`. mkgmap gleicht das mit `LocatorConfig.xml` ab (Schweiz/CHE, `streetBeforeHousenumber` → „Marktgasse 20“) |
| `is_in:county` | Kantonsname (mkgmap → `mkgmap:region`) |
| `is_in:city` | Gemeindename (mkgmap → `mkgmap:city`) |

Gilt für alle Strassen, Adresspunkte, Orte und alle übrigen benannten Punkte (POIs, Gipfel,
Flurnamen, Anschlüsse. Nachträglich per Punkt-in-Polygon ergänzt). Liegt ein Punkt in keiner
Gemeinde (z. B. Gipfel genau auf der Landesgrenze wie Matterhorn, Dufourspitze), gilt die nächste
Gemeinde im Umkreis von 1 km.

Adressen mit Gebiets- statt Strassennamen (Strassenverzeichnis `STR_TYPE=Area/Place`,
z. B. „Rüti 1“): Gibt es im Umkreis von 150 m keine Strasse mit diesem Namen, bekommt die
nächste **unbenannte** Strasse (ohne Autobahn/Autostrasse/Treppe) den Tag
`addr:street=<Gebietsname>`. Je Strassenstück nur ein Gebietsname, häufigste zuerst. Der
mkgmap-Default-Style macht daraus `mkgmap:street` (Hausnummernzuordnung), die Beschriftung
bleibt leer. Ein eigener Stil kann `addr:street` auf `highway=*` ohne `name` auswerten.

Autobahnstücke ohne eigene Strassenroute übernehmen `ref`/`nat_ref`/`int_ref` vom angrenzenden
Autobahnstück.

### Fähren

`tlm_oev_schifffahrt` und objektart `Faehre`: `route=ferry`, `name`, `foot=yes`,
`bicycle=yes`, `motor_vehicle=yes` nur bei `Autofaehre`.

## Durchfahrtssperren (`tlm_strassen_strasseninfo`)

`objektart=Durchfahrtssperre` → Knoten mit `barrier=bollard` (sperrt Motorfahrzeuge, Fuss und
Velo frei). Die Punkte liegen in swissTLM3D exakt auf Stützpunkten der Strasse und werden mit
diesem Knoten verschmolzen.

## Adressen (amtliches Gebäudeadressverzeichnis)

Ein Knoten pro Adresse mit `ADR_STATUS=real`:

| CSV-Feld | Tag |
|---|---|
| `STN_LABEL` | `addr:street` |
| `ADR_NUMBER` | `addr:housenumber` |
| `ZIP_LABEL` (z. B. „9000 St. Gallen“) | `addr:postcode` (`9000`), `addr:place`/`swisstopo:ortschaft` (`St. Gallen`) |
| `COM_NAME` | `addr:city`, `is_in:city` |
| `COM_CANTON` | `is_in:county` (voller Kantonsname) |
| `BDG_NAME` | `name` (falls vorhanden) |
| `ADR_EGAID` | `swisstopo:egaid` |

`addr:city` ist die **Gemeinde**, nicht die Postortschaft. So passen Strassen und Hausnummern
in mkgmap zusammen (beide über `is_in:city`). Die Postortschaft steht in `swisstopo:ortschaft`.

## Bahn und Seilbahn

| Quelle | OSM-Tags |
|---|---|
| `tlm_oev_eisenbahn` `Normalspur` | `railway=rail`, `gauge=1435` |
| `tlm_oev_eisenbahn` `Schmalspur` | `railway=narrow_gauge`, `gauge=1000` |
| `Schmalspur mit Normalspur` | `railway=rail`, `gauge=1000;1435` |
| `Kleinbahn` | `railway=miniature` |
| `anzahl_spuren` | `tracks` (1 oder 2) |
| objektart (Normalspur/Schmalspur …) | zusätzlich `swisstopo:spurweite` |
| `achse_dkm` | `swisstopo:achse_dkm=yes\|no` (kartografische Achse, auf Doppelspur trägt sie `tracks=2`) |
| Gleisachse neben Mehrspurachse | `swisstopo:parallelachse=yes`: ohne DKM-Flag, kein Anschlussgleis, zu ≥ 80 % der Länge ≤ 8 m neben einer DKM-Achse gleicher Spurweite mit `tracks≥2`. Der Stil zeichnet sie nicht (LK: eine Mehrspur-Signatur). Bahnhofs- und Weichengleise bleiben unmarkiert. Landesweit 9784 Achsen (2499 km), Testgebiet 332 |
| `zahnradbahn=Wahr` | `rack=yes` |
| `standseilbahn=Wahr` | `railway=funicular` |
| `anschlussgleis=Wahr` | `service=siding` |
| `museumsbahn=Wahr` | `usage=tourism` |
| `ausser_betrieb=Wahr` | `railway=disused` |
| `auf_strasse=Wahr` | `embedded=yes` (Tram/Strassenbahnabschnitt) |
| `kunstbaute` | `bridge`/`tunnel`/`layer` wie Strassen |
| `tlm_oev_uebrige_bahn` `Luftseilbahn` | `aerialway=cable_car` |
| `Gondelbahn` | `aerialway=gondola` |
| `Sesselbahn` | `aerialway=chair_lift` |
| `Skilift` | `aerialway=drag_lift` |
| `Lift` | `aerialway=platter` |
| `Transportseil` | `aerialway=goods` |
| `Foerderband` | `man_made=goods_conveyor` |

## Gewässer

| Quelle | OSM-Tags |
|---|---|
| `tlm_gewaesser_fliessgewaesser` `Fliessgewaesser` | `waterway=stream` bzw. `waterway=river` (siehe unten) |
| `verlauf=Unterirdisch bestimmt`/`unbestimmt` | `tunnel=culvert`, `layer=-1` |
| `verlauf=Wasserfall` | `waterway=waterfall` am Linienstück (zusätzlich zu `waterway`) |
| `verlauf=Bruecke` | `bridge=aqueduct` |
| `Trockenrinne` | `waterway=ditch`, `intermittent=yes` |
| `Druckleitung einfach` | `man_made=pipeline`, `substance=water` |
| `Seeachse` | nicht übernommen (Hilfslinie durch Seen) |
| `name` | `name` |

**Flussordnung** (`src/vector/rivers.py`, landesweit aus dem TLM-Netz, keine
Fremdquelle) an allen Fliessgewässer-Linien (`Fliessgewaesser`, `Trockenrinne`):

| Tag | Inhalt |
|---|---|
| `swisstopo:strahler` | Strahler-Ordnung 1–10 (Quellbach 1). Arme desselben Gewässers (gleiche GEWISS-Nr.), die sich wieder vereinigen, erhöhen sie nicht. Thur 7, Sitter 7, Glatt 5, Steinach 4 |
| `swisstopo:laenge_oberhalb_km` | Gewässerlänge oberhalb inkl. Abschnitt (km, eine Nachkommastelle), Ersatz für das Einzugsgebiet |
| `swisstopo:gewaesserklasse` | 1–6 aus der Länge oberhalb: < 3 / 15 / 60 / 300 / 1500 km / darüber (≈ 1 / 6 / 25 / 120 / 600 km² Einzugsgebiet). An der Mündung: 4 Steinach, Goldach. 5 Glatt, Necker, Urnäsch, Sitter. 6 Thur, Reuss |

Empfehlung für den Stil: Dicke und Zoomstufe nach `swisstopo:gewaesserklasse`. Beispiel: Klasse 1
ab Auflösung 23, 2 ab 22, 3 ab 21, 4 ab 20, 5–6 ab 18. Die Werte gelten je Abschnitt, ein Bach
wird also flussabwärts breiter. Zuflüsse aus dem Ausland fehlen im Netz (dort ist die Ordnung zu tief).
Druckleitungen/-stollen und Bisses/Suonen bekommen keine Ordnung.

Fliessgewässer mit Name auf Flüssen (`gwl_nr` gesetzt) bekommen `waterway=river`, alle anderen
`waterway=stream`. Die Uferlinien stehender Gewässer (`tlm_gewaesser_stehendes_gewaesser`) werden
nicht als Linien übernommen, die Wasserflächen kommen aus der Bodenbedeckung.

## Abstand zur nächsten Stadt (`swisstopo:stadtabstand`)

Flussnamen und Autobahnschilder können auf dem Gerät den Stadtnamen verdrängen. Beispiel: Im
Gerätetest 7794-klassen2 fehlte „St. Gallen“ bei 3 km und 8 km. Der Stil zeigt diese Labels deshalb
nahe einer Stadt erst bei grösserem Zoom. Dafür liefert `src/vector/stadtabstand.py` dieses Tag:

| Punkt | Regel |
|---|---|
| Stadt | Knoten `place=city` oder `place=town` mit `population>=10000` |
| Wege | `waterway=river\|stream\|canal\|ditch\|drain`, `highway=motorway\|trunk\|motorway_link\|trunk_link` und Wege mit `swisstopo:shield_autobahn` |
| Wert | Kleinster Abstand eines Wegknotens zur nächsten Stadt, in ganzen Metern |
| Bedingung | Nur unter 5000 m |
| Teilung | An den Grenzen 1500, 2000, 3000, 4000 und 5000 m, am ersten Knoten jenseits der Grenze |

Ohne Teilung verliert ein langer Weg sein Label überall, auch wenn er nur kurz nahe an einer Stadt
liegt. Die Teilstücke behalten alle Tags. Das erste Teilstück behält die Weg-ID. Die anderen bekommen
neue IDs über der grössten Weg-ID der Datei.

Der Schritt läuft auf der fertigen PBF: im Einzelbuild am Ende von `convert.py`, im Landesbuild in
`build_ch.py` nach dem Merge der Kacheln. So zählen auch Städte jenseits einer Kachelgrenze.
Testgebiet Klassen-Test (9.25–9.65° O): 3 Städte (St. Gallen, Herisau, Rorschach), 5740 Wege mit
Tag, 473 Wege aus der Teilung.

## Bodenbedeckung (`tlm_bb_bodenbedeckung`)

| objektart | OSM-Tags |
|---|---|
| `Wald` | `natural=wood` |
| `Wald offen` | `natural=wood`, `wood=open` |
| `Gebueschwald` | `natural=scrub` |
| `Gehoelzflaeche` | `natural=wood`, `wood=copse` |
| `Fels` | `natural=bare_rock` |
| `Fels locker` | `natural=bare_rock`, `density=sparse` |
| `Felsbloecke` | `natural=scree`, `scree=boulders` |
| `Felsbloecke locker` | `natural=scree`, `scree=boulders`, `density=sparse` |
| `Lockergestein` | `natural=scree` |
| `Lockergestein locker` | `natural=scree`, `density=sparse` |
| `Gletscher` | `natural=glacier` |
| `Schneefeld Toteis` | `natural=glacier`, `glacier:type=dead_ice` |
| `Feuchtgebiet` | `natural=wetland` |
| `Stehende Gewaesser` | `natural=water`, `water=lake` |
| `Fliessgewaesser` | `natural=water`, `water=river` |

Seenamen (swissNAMES3D `See`) werden per räumlicher Zuordnung als `name` auf die Wasserfläche
gesetzt. Für die Beschriftung gibt es zusätzlich einen Seepunkt `place=lake` (siehe Namen von Flächen). Flächen mit Löchern oder mehreren Teilen werden Multipolygon-Relationen.

## Generalisierte Siedlungsflächen (für grobe Zoomstufen)

Quelle sind die Gebäude-Footprints ohne unterirdische Gebäude, Schächte und grosse Mauern. Ablauf:

1. Puffer +30 m, vereinigen, Puffer −20 m.
2. Auf 10 m vereinfachen.
3. Löcher < 1 ha füllen, Flächen < 3 ha weglassen.

Tags: `landuse=residential`, `swisstopo:generalisiert=siedlung`, `swisstopo:layer=tlm_bauten_gebaeude_footprint`.

Testgebiet: 231 Flächen (Rechenzeit ca. 70 s). Der Landesbuild rechnet je Kachel und schneidet an
den Kachelgrenzen. Beide Seiten entstehen aus denselben Gebäuden im Leserand und sind deshalb
deckungsgleich.

## Platz-Namenpunkte (Plätze, Tore, benannte Kreisel)

Ein Punkt je benanntem Platz: `place=square`, `name`, `swisstopo:namenpunkt=platz`,
`swisstopo:quelle=tlm|strassenverzeichnis`, `is_in:*`.

1. **TLM:** Strassenkanten mit `objektart=Platz` oder `kreisel=Wahr` und `strassenname`, Punkt am
   Schwerpunkt der zusammenhängenden Kanten gleichen Namens. Nur echte Platznamen zählen:
   - Der Name steht im Strassenverzeichnis als `STR_TYPE=Place` oder endet auf -platz, -tor, -markt.
   - Der Name endet nicht auf eine Strassenendung (-strasse, -weg, -gasse, -rain, -allee, -ring …).

   Grund: Kreisel tragen fast immer nur den Namen der durchgehenden Strasse (Testgebiet: 162 von
   163). Platzkanten tragen oft Gebietsnamen.
2. **Strassenverzeichnis:** Einträge `STR_TYPE=Place` (Plätze, Tore, Pärke) an der Koordinate des
   Verzeichnisses.
3. **Dubletten:** kein Punkt, wenn ein Punkt gleichen Namens (swissNAMES3D, POI oder schon
   erzeugter Platzpunkt) näher als 100 m liegt. TLM-Schwerpunkt hat Vorrang.

Testgebiet: 56 Punkte (8 TLM, z. B. Spisertor, Obstmarkt, Bahnhofplatz, 48 Strassenverzeichnis,
z. B. Marktplatz, Multertor, Schibenertor), 15 Dubletten verworfen.

Eine Waldrandlinie gibt es nicht (Entscheid: SMV25 zeichnet Wald ohne Rand).

## Objektnamen wie auf der LK (SMV25-Annotationen)

**Namen an der LK-Textposition (`anno.move_names_to_anno`):** Das betrifft swissNAMES3D-Flurnamen
(Punkte) und Gelände-/Gebietsnamen (Flächen-Labelpunkte, ausser Massiven am Hauptgipfel). Sie wandern
an die Textmitte einer SMV25-Beschriftung mit gleichem Text (T14/T12/T13) im Umkreis von 600 m. Dort
tragen sie `swisstopo:lk_text=yes`. Ohne Gegenstück bleiben sie am Referenzpunkt mit `swisstopo:lk_text=no`
(die LK25 zeigt sie nicht). Testgebiet: 2242 verschoben (Median 69 m), 5656 ohne Gegenstück.

Quelle: Swiss Map Vector 25 (swisstopo, OGD), blattweise GPKG in `downloads/smv25-2026/`, Layer
`T07_DKM25_GEBAEUDE_ANNO`, `T08_…BAUTE_PKT_ANNO`, `T10_…BAUTE_PLY_ANNO`, `T25_…FREIZEITAREAL_ANNO`,
`T26_…NUTZUNGSAREAL_ANNO`, `T27_…VERKEHRSAREAL_ANNO`.

| Tag | Inhalt |
|---|---|
| `name` | `TEXTSTRING`. Mehrzeilige Texte (gleiche `DKM_UUID`, Zeilen von oben nach unten, links nach rechts) zusammengesetzt: Zeilenende „-“ + Kleinbuchstabe → ohne Bindestrich („Kantons-“ + „spital“ → „Kantonsspital“), + Grossbuchstabe → mit Bindestrich („Gross-“ + „Hütten“), sonst Leerzeichen |
| `swisstopo:anno` | `gebaeude`, `baute`, `freizeitareal`, `nutzungsareal`, `verkehrsareal` |
| `swisstopo:layer` | `smv25:<Layer>` |
| `swisstopo:dkm_uuid` | `DKM_UUID` |
| `alt_name`, `swisstopo:amtlicher_name` | Name des zusammengelegten Areal-/Gebäude-POIs, falls abweichend |
| `amenity`, `tourism`, `leisure`, `historic` … | vom zusammengelegten POI übernommen |

Position: Mittelpunkt der Beschriftung, bei zusammengelegten POIs die Objektposition (siehe unten).
Doppel aus überlappenden Blättern fallen weg.

**Zusammenlegen:** Die `DKM_UUID` entspricht nicht der TLM-UUID (0 Treffer). Deshalb gilt eine
räumliche Regel. Liegt ein POI derselben Klasse (Areal-Layer bzw. Gebäude/Einzelobjekt) näher als
150 m, entfällt er. Sein Name wird `alt_name` des Anno-Knotens, seine POI-Tags gehen über.
Testgebiet: 257 Anno-Knoten, 156 zusammengelegt.

Der zusammengelegte Knoten liegt an der Position des POI, also im Areal (`point_on_surface`), am
Gebäude bzw. am TLM-Punkt. Er liegt nicht an der LK-Textposition, denn die LK stellt Texte oft neben
das Objekt. Beispiel: Den Text „Burgruine“ für Helfenberg stellt die LK 151 m neben das Areal auf die
Wiese. Im Testgebiet liegen 150 der 156 Knoten mehr als 30 m von der Textposition entfernt.

**Einschränkung:** mkgmap schreibt für POIs nur das erste Label. Mehrere Labels wirken nur bei
Linien. Ein Test mit `mkgmap:label:2` bzw. `mkgmap:label:3` = `alt_name` an POIs (Kopie
Default-Style, `--index`) zeigt: Der zweite Name steht weder in der Kachel noch im MDR. `alt_name`
kommt also nicht in den Suchindex. Die Suche findet den LK-Text (z. B. „Spital“, „Bad“, „ARA“),
nicht den amtlichen Namen („Spital Wil“).

## Einzelbäume (`tlm_bb_einzelbaum`)

`natural=tree`, nur ausserhalb von `Wald`, `Wald offen`, `Gebueschwald`, `Gehoelzflaeche` (TLM hat
dort ohnehin keine). Ausgedünnt auf etwa die LK25-Dichte: ein Baum je Rasterzelle, **20 m**
ausserhalb und **80 m** innerhalb der Siedlungskerne (generalisierte Siedlungsflächen, Aussenring).
Baumreihen und Obstgärten werden damit nicht vollständig aufgelöst.

Eichung an den LK-Referenzzählungen der Stil-QA (Ausschnitte 1:25 000):

| Ausschnitt | LK-Referenz | TLM ausgedünnt (20/80 m) |
|---|---|---|
| St. Gallen Zentrum | 1 692 | 1 526 |
| Herisau | 1 795 | 1 825 |
| Wil SG | 1 411 | 1 149 |
| Oberbüren–Niederuzwil | 1 621 | 1 652 |
| Säntis/Alpstein | 59 | 112 |
| **Summe** | **6 578** | **6 264 (95 %)** |

Testgebiet: 443 307 TLM-Bäume → 203 262 übernommen.

## Areale

**Regel „Fläche plus genau ein POI“:** Die Arealfläche trägt nur Flächen-Tags ohne POI-Wirkung
(Tabelle unten, `landuse`/`area:highway`/`access`), `swisstopo:objektart` und den Namen in
`swisstopo:name`. Die POI-Tags der folgenden Tabelle (`amenity`, `tourism`, `leisure`,
`aeroway` …) und `name` stehen nur am POI-Knoten (siehe POIs). Für die Darstellung nutzt der
Stil `swisstopo:objektart`. Alle Arealflächen tragen `area=yes` (`Privates Parkplatzareal`
hat sonst nur `access=private` und ist für OSM-Werkzeuge eine Linie).

**Hinweis für den Stil:** Viele Polygonregeln des Stils `swisstopo` greifen
auf POI-Tags (`amenity=parking`, `tourism=camp_site|zoo`, `highway=rest_area`,
`aeroway=aerodrome`, `amenity=hospital`), die an der Fläche bewusst fehlen. Diese Areale werden
konvertiert, aber nicht gezeichnet. Beispiel: Privates Parkplatzareal bei LV95 2728380/1255480
(Uzwil, 2,1 ha).

Diese Areale brauchen eine Regel über `swisstopo:objektart`: `Oeffentliches
Parkplatzareal`, `Privates Parkplatzareal`, `Rastplatzareal`, `Campingplatzareal`,
`Standplatzareal`, `Zooareal`, `Flugfeldareal`, `Flugplatzareal`, `Flughafenareal`, `Heliport`,
`Spitalareal` (`landuse=healthcare`), `Schul- und Hochschulareal` (`landuse=education`),
`Historisches Areal`, `Klosterareal`, `Truppenuebungsplatz`, `Messeareal`, Industrieareale (ARA,
KVA, Kraftwerk, Unterwerk), `Gleisareal`, `Pferderennbahnareal`, `Massnahmenvollzugsanstaltsareal`,
`Antennenareal`.

Neu: `tlm_areale_schutzgebiet` (nur der Nationalpark) → `boundary=national_park`,
`protect_class=2`, Name in `swisstopo:name`.

| objektart | Flächen-Tags |
|---|---|
| Schul- und Hochschulareal | `landuse=education` |
| Spitalareal | `landuse=healthcare` |
| Friedhof | `landuse=cemetery` |
| Obstanlage, Reben, Baumschule, Schrebergartenareal | `landuse=orchard/vineyard/plant_nursery/allotments` |
| Wald nicht bestockt | `landuse=forest` |
| Abbau-, Deponieareal | `landuse=quarry/landfill` |
| ARA, KVA, Kraftwerk, Unterwerk | `landuse=industrial` |
| Klosterareal | `landuse=religious` |
| Truppenübungsplatz | `landuse=military` |
| Messeareal | `landuse=commercial` |
| Sport-, Schwimmbad-, Golfplatz-, Freizeitanlagenareal, öffentliches Parkareal | `landuse=recreation_ground` |
| Gleisareal | `landuse=railway` |
| Verkehrsfläche, privates Fahrareal | `area:highway=yes` (privat: `access=private`) |
| Privates Parkplatzareal | `access=private` |
| übrige (Camping, Zoo, Parkplatz, Rastplatz, Flugplatz, Heliport, historisches Areal …) | nur `swisstopo:objektart` |

Bedeutung der Objektarten (diese Tags stehen nur am POI-Knoten, nicht an der Fläche):

| Layer / objektart | OSM-Tags |
|---|---|
| Nutzungsareal `Schul- und Hochschulareal` | `amenity=school` |
| `Spitalareal` | `amenity=hospital` |
| `Friedhof` | `landuse=cemetery` |
| `Obstanlage` | `landuse=orchard` |
| `Reben` | `landuse=vineyard` |
| `Baumschule` | `landuse=plant_nursery` |
| `Schrebergartenareal` | `landuse=allotments` |
| `Wald nicht bestockt` | `landuse=forest`, `swisstopo:objektart` (Schlagflächen) |
| `Abbauareal` | `landuse=quarry` |
| `Deponieareal` | `landuse=landfill` |
| `Abwasserreinigungsareal` | `man_made=wastewater_plant` |
| `Kehrichtverbrennungsareal` | `landuse=industrial`, `industrial=waste_incineration` |
| `Kraftwerkareal` | `power=plant` |
| `Unterwerkareal` | `power=substation` |
| `Historisches Areal` | `historic=yes` |
| `Klosterareal` | `amenity=monastery` |
| `Oeffentliches Parkareal` | `leisure=park` |
| `Truppenuebungsplatz` | `landuse=military` |
| `Massnahmenvollzugsanstaltsareal` | `amenity=prison` |
| `Messeareal` | `landuse=commercial` |
| Freizeitareal `Sportplatzareal` | `leisure=sports_centre` |
| `Schwimmbadareal` | `leisure=water_park` |
| `Campingplatzareal` | `tourism=camp_site` |
| `Standplatzareal` | `tourism=caravan_site` |
| `Golfplatzareal` | `leisure=golf_course` |
| `Freizeitanlagenareal` | `leisure=park` |
| `Zooareal` | `tourism=zoo` |
| `Pferderennbahnareal` | `leisure=track`, `sport=horse_racing` |
| Verkehrsareal `Oeffentliches Parkplatzareal` | `amenity=parking` |
| `Privates Parkplatzareal` | `amenity=parking`, `access=private` |
| `Rastplatzareal` | `highway=rest_area` |
| `Flugfeldareal`, `Flugplatzareal`, `Flughafenareal` | `aeroway=aerodrome` |
| `Heliport` | `aeroway=heliport` |
| `Gleisareal` | `landuse=railway` |
| `Verkehrsflaeche`, `Privates Fahrareal` | `area:highway=yes` |

`name` wird übernommen. Areale sind Flächen ohne Routing.

## Gebäude und Bauten

**Geometrie:** Footprints werden vor der Umrechnung in LV95 mit 0,2 m vereinfacht (nur kollineare
Zwischenpunkte fallen weg, alle Ecken bleiben). swissTLM3D zerlegt gerade Wände in Stücke von
3–5 m. Mkgmap rundet jeden Punkt auf das Garmin-Raster, ohne Vereinfachung entsteht daraus ein Zickzack.

**Ausrichtung auf das Raster:** Vor dem Schreiben dreht und verschiebt `src/vector/gebaeude_raster.py` jede
Gruppe sich berührender Gebäude leicht und rundet die Ecken auf das Raster der Auflösung 24. Die Ecken
behalten so ihre Winkel. Die Grundrisse wachsen dabei nicht (kein Puffer, Gerätetest 2026-11-08). Die Tags
ändern sich nicht. Details: [Basiskarte](../vektor/basiskarte.md).

**Mauern sind keine Gebäude:** Footprints der Objektart `Mauer gross` (10 847) und
`Mauer gross gedeckt` (575) bekommen kein `building=*`. Mit `building=wall` erscheinen sie schwarz wie Häuser
(Beispiel Burgruine Helfenberg: zwei Mauerstücke, 10 und 22 m²). 3804 davon liegen in einem Historischen
Areal: 1972 Burg/Schloss, 1099 Ruine, 266 Kloster, 195 archäologische Stätte, 14 Stadtmauer,
258 ohne Namensmuster. Der Stil soll `swisstopo:mauer=gross` als Mauer zeichnen (Umriss oder
dunkelgraue Fläche), nicht als Gebäude. Die Regel `barrier=wall & area!=no → 0x13` in `polygons`
macht sie sonst wieder schwarz.

Gebäude-Footprints tragen **nur** `building=*` (z. B. `yes`, `roof`, `church`, `chapel`,
`greenhouse`, `storage_tank`, `tower`, `chimney`) plus `swisstopo:*`, keine POI-Tags (`amenity`,
`tourism`, `leisure`, `man_made` …) und keinen `name`, der Name steht in `swisstopo:name`. Die
Tabelle unten beschreibt die Bedeutung. `man_made`/`amenity` stehen nur an POI-Knoten. Sonst entstünden mit
`--add-pois-to-areas` aus jedem Footprint eines Gebäudekomplexes eigene POIs (Beispiel:
„Berggasthaus Alter Säntis“ mit 6 Footprints). POIs liefert `pois.py` als Knoten.

| Quelle / objektart | OSM-Tags |
|---|---|
| Gebäude `Gebaeude` | `building=yes` |
| `Offenes Gebaeude`, `Flugdach` | `building=roof` |
| `Lagertank` | `man_made=storage_tank` |
| `Im Bau` | `building=construction` |
| `Sakrales Gebaeude` | `building=church`, `amenity=place_of_worship` |
| `Kapelle` | `building=chapel`, `amenity=place_of_worship` |
| `Sakraler Turm` | `building=church`, `man_made=tower`, `tower:type=bell_tower` |
| `Hochhaus` | `building=yes`, `building:levels` nicht bekannt |
| `Treibhaus` | `building=greenhouse` |
| `Turm` | `man_made=tower` |
| `Hochkamin` | `man_made=chimney` |
| `Mauer gross`, `Mauer gross gedeckt` | **kein** `building`: `barrier=wall`, `area=yes`, `swisstopo:mauer=gross`. Gedeckt zusätzlich `covered=yes`. Im Historischen Areal `swisstopo:historisches_areal=<castle\|ruins\|archaeological_site\|monastery\|citywalls\|yes>`, bei `ruins`/`archaeological_site` zusätzlich `ruins=yes` |
| `Historische Baute` | `building=ruins`, `ruins=yes` (22 Objekte, Mauerreste, z. B. Amphitheater Lentia) |
| `Verbindungsbruecke` | `building=bridge` |
| `Unterirdisches Gebaeude`, `Lueftungsschacht` | `building=yes`, `location=underground`, `layer=-1` |
| Gebäude in einem Historischen Areal | zusätzlich `swisstopo:historisches_areal` (wie oben) |
| `nutzung` | `swisstopo:nutzung` (POI-Tags wie `amenity=restaurant` stehen nur am POI-Knoten, siehe POIs) |
| `tlm_bauten_mauer` | `barrier=wall` |
| `tlm_bauten_verbauung` `Trockenmauer` | `barrier=wall`, `wall=dry_stone` |
| `Schutzverbauung` | `man_made=avalanche_protection` (siehe Hinweis) |
| `Gewaesserverbauung` | `man_made=embankment` |
| `tlm_bauten_leitung` `Stromleitung` | `power=line` |
| `tlm_bauten_staubaute` `Staumauer` | `waterway=dam`, `area=yes` |
| `Staudamm` | `waterway=dam`, `area=yes` |
| `Wehr` | `waterway=weir`, `area=yes` |
| `Schutzdamm` | `man_made=dyke`, `area=yes` |
| `Wasserbecken` | `natural=water`, `water=basin` |
| `tlm_bauten_sportbaute_ply` `Sportplatz` | `leisure=pitch` |
| `tlm_bauten_sportbaute_lin` `Laufbahn` | `leisure=track` |
| `Scheibenstand` | `swisstopo:objektart=Scheibenstand`, `man_made=yes` |
| `Skisprungschanze` | `piste:type=ski_jump` |
| `Rodelbahn`, `Bobbahn` | `piste:type=sled` |
| `tlm_bauten_verkehrsbaute_ply` `Perron` | `railway=platform`, `area=yes` |
| `Rollfeld Hartbelag`/`Gras`, `Graspiste`, `Hartbelagpiste` | `aeroway=runway`, `area=yes`, `surface` |
| `Schleuse` (Verkehrsbaute Fläche) | `waterway=lock_gate`, `lock=yes`, `area=yes` |
| `tlm_bauten_verkehrsbaute_lin` `Hafensteg` | `man_made=pier` |
| `tlm_bauten_versorgungsbaute_pkt` `Antenne gross` | `man_made=mast` |
| `Antenne klein` | nicht übernommen |
| `Windturbine` | `power=generator`, `generator:source=wind` |

Hinweis: `Schutzverbauung` (Lawinen-/Steinschlagverbauungen) → `man_made=avalanche_protection`
(kein etablierter OSM-Wert, Stil entscheidet über `swisstopo:objektart`).

## Namen und Punkte (swissNAMES3D, Punkte)

Einige Klassen kommen **nicht** aus swissNAMES3D, sondern direkt aus swissTLM3D (siehe POIs). So
erscheint nichts doppelt. Das gilt für:

- Haltestellen (`TLM_HALTESTELLE`)
- benannte Gebäude (`TLM_GEBAEUDE`)
- die Einzelobjekte Bildstock, Brunnen, Quelle, Wasserfall, Denkmal, Grotte/Höhle, Gipfelkreuz und
  Triangulationspyramide

Für diese Klassen gelten die Zeilen der folgenden Tabelle nicht.

Ein Objekt (`uuid`) kann mehrere Namen haben. Der Hauptname ist der offizielle mit `namen_typ`
„einfacher Name“ oder „Endonym“, weitere Namen landen in `alt_name` (mit `;`).

| objektklasse_tlm / objektart | OSM-Tags |
|---|---|
| `TLM_NAME_PKT` `Hauptgipfel`, `Gipfel`, `Alpiner Gipfel` | `natural=peak`, `ele` |
| `Haupthuegel`, `Huegel` | `natural=hill`, `ele` |
| `Felskopf` | `natural=peak`, `ele`, `swisstopo:objektart=Felskopf` |
| `Pass` | `natural=saddle`, `mountain_pass=yes`, `ele` |
| `Strassenpass` | `mountain_pass=yes`, `ele` |
| `TLM_SIEDLUNGSNAME_ZENTRUM` `Ort` | `place=city` (> 100 000 Einw.), `town` (≥ 10 000), `village` (≥ 100), `hamlet` (< 100) |
| `Ortsteil`, `Quartier` | `place=suburb` |
| `Quartierteil` | `place=neighbourhood` |
| `TLM_FLURNAME` `Flurname swisstopo`, `Lokalname swisstopo` | `place=locality` |
| `TLM_EINZELOBJEKT` `Aussichtspunkt` | `tourism=viewpoint`. Liegt ein gleichnamiger Gipfel oder Hügel näher als 50 m, steht der Name in `swisstopo:aussicht_name` statt in `name` (Symbol ohne Label, sonst verdrängen sich die Labels, z. B. Säntis, Rigi Kulm. CH: 29 von 240) |
| `Bildstock` | `historic=wayside_shrine` |
| `Brunnen` | `amenity=fountain` |
| `Denkmal` | `historic=memorial` |
| `Grotte, Hoehle` | `natural=cave_entrance` |
| `Quelle` | `natural=spring` |
| `Wasserfall` | `waterway=waterfall` |
| `Landesgrenzstein` | `historic=boundary_stone` |
| `TLM_GEBAEUDE` `Gebaeude` | `building=yes` (Namenspunkt) |
| `Offenes Gebaeude` | `building=roof` |
| `Kapelle` | `amenity=place_of_worship`, `building=chapel` |
| `Sakrales Gebaeude` | `amenity=place_of_worship` |
| `Turm` | `man_made=tower` |
| `TLM_HALTESTELLE` `Haltestelle Bahn` | `railway=station`, `public_transport=station` |
| `Haltestelle Bus` | `highway=bus_stop` |
| `Haltestelle Schiff` | `amenity=ferry_terminal` |
| `Uebrige Bahnen` | `aerialway=station`. Wie beim Aussichtspunkt: Liegt ein gleichnamiger Gipfel näher als 150 m, steht der Name in `swisstopo:station_name` (gilt auch für Haltestellen aus swissTLM3D, CH: 37) |
| `TLM_MORPH_KLEINFORM_PKT` `Erratischer Block`, `Felsblock` | `natural=stone` |
| `TLM_AUS_EINFAHRT` `Ausfahrt`, `Ein- und Ausfahrt`, `Verzweigung` | `highway=motorway_junction` (aus `tlm_strassen_aus_einfahrt`, `ref` = Nummer) |
| `TLM_STRASSENINFO` `Zollamt …` | `barrier=border_control` |

Gipfel und Hügel tragen zusätzlich `swisstopo:gipfelklasse` (`src/vector/peaks.py`). Die Klasse folgt den
Landeskarten-Massstäben. Massgebend ist die kleinste Karte, in der der Gipfel als Namenpunkt vorkommt:

| Klasse | Quelle | Gipfel CH | Beispiele Alpstein |
|---|---|---|---|
| 1 | Swiss Map Vector 1000 (`T14_DKM1M_NAME_PKT`, Gipfel) | 66 | Säntis |
| 2 | Swiss Map Vector 500 (`T15_DKM500_NAME_PKT`, Gipfel und Hügel) | 293 | Altmann, Hoher Kasten, Kronberg |
| 3 | swissTLMRegio (`tlmregio_names_namedlocation`, HGipfel, GGipfel, KGipfel, Huegel) | 1009 | Öhrlikopf, Schäfler |
| 4 | alle übrigen | 8728 | Girenspitz, Chalbersäntis |

Zuordnung: gleicher Name im Umkreis von 1500 m (SMV1000), 800 m (SMV500) oder 400 m (swissTLMRegio).
Ein Doppelname wie „Rheinwaldhorn Adula“ gilt als gleicher Name. Ohne Namenstreffer gilt die gleiche
Höhe (± 3 m) im selben Umkreis. Die Zahlen gelten für Gipfel und Hügel in der Schweiz (Stand 2026-11).

Ein benannter Gipfel mit Höhe bekommt zusätzlich Kotenpunkte: `ele`, `swisstopo:gipfelkote=<r>`,
`swisstopo:gipfelklasse`. Je Auflösung r gibt es einen Punkt, 12 · 360°/2^r südlich des Gipfels. Die
erste Auflösung ist 19, 20, 21 oder 22 je Klasse 1–4 (Hügel der Klasse 4: 23), die letzte 24.

Pässe (`Pass`, `Strassenpass`) tragen ebenso `swisstopo:passklasse` 1–4. Quellen: SMV1000 (Pass), SMV500
(Pass, Strassenpass), swissTLMRegio (Strassenpass, Fusspass). Schweiz: 30, 49, 175 und 2179 Pässe, z. B.
Gotthard, Grimsel und Schwägalp in Klasse 1. Benannte Pässe bekommen Kotenpunkte wie die Gipfel
(`swisstopo:gipfelkote`, `swisstopo:gipfelklasse` mit dem Wert der Passklasse). swissNAMES3D führt
manche Pässe zweimal, als `Pass` und als `Strassenpass` mit gleichem Namen am gleichen Ort. Davon bleibt
ein Punkt (gleicher Name im Umkreis von 50 m) mit der besten Klasse und `natural=saddle`.

Ein Pass darf einen Gipfel der Klasse 1 nie verdrängen (Entscheid des Benutzers). Beispiel: Das Label
„Schwägalp Passhöhe“ verdrängte den Säntis. Dafür trägt jeder benannte Pass `swisstopo:gipfelabstand`:
den Abstand in ganzen Metern zum nächsten benannten `natural=peak|hill` mit `swisstopo:gipfelklasse=1`.
Pass heisst hier: `name=*` und `mountain_pass=yes` oder `natural=saddle`, nicht `natural=peak|hill`. Das
Tag steht nur unter 20 000 m.

Der Stil zeigt einen nahen Pass erst bei grösserem Zoom. Testgebiet:
Schwägalp Passhöhe 3042 m, Windenpass 6248 m. Berechnung und Ablauf wie bei `swisstopo:stadtabstand`
(siehe Abschnitt „Abstand zur nächsten Stadt“), im Landesbuild also nach dem Merge.

### Einwohnerzahl (`population`)

Am Hauptort jeder Gemeinde: `population=<einwohnerzahl>` aus swissBOUNDARIES3D
(`tlm_hoheitsgebiet`, Gemeindegebiet), dazu `swisstopo:population_quelle=swissBOUNDARIES3D Gemeinde <Name>`.
Den Hauptort bestimmt diese Regel:

1. Der `place`-Knoten (Objektart `Ort`) in der Gemeindefläche mit dem Gemeindenamen.
   Kantonszusätze „(SG)“ bzw. „ SG“ zählen nicht.
2. Gibt es keinen solchen Knoten, gilt der grösste Ort der Gemeinde nach
   swissNAMES3D-Einwohnerkategorie (Beispiel Gaiserwald → Engelburg).

Im Kachelmodus wendet nur die Kachel mit dem Gemeinde-Mittelpunkt Regel 2 an. Sie tut das nur, wenn
es in der ganzen Gemeinde (swissNAMES3D, kachelübergreifend) keinen Ort mit dem Gemeindenamen gibt.
Sonst bekämen Gemeinden über eine Kachelgrenze zwei Einträge.

Testgebiet: 63 Gemeinden (53 über den Namen, 10 über den grössten Ort). Die Einwohnerzahl gilt für
die ganze Gemeinde, nicht für die Ortschaft.

## Namen von Flächen (swissNAMES3D, Polygone) als Beschriftungspunkte

Ein Knoten am inneren Punkt (`point_on_surface`) der Fläche:

| objektart | OSM-Tags |
|---|---|
| `Tal`, `Haupttal`, `Graben` | `natural=valley` |
| `Grat` | `natural=ridge` |
| `Massiv` | am höchsten Gipfel (swissNAMES3D `TLM_NAME_PKT`) in der Massivfläche: `natural=peak` (ohne `ele`, damit das Label ohne Höhencode suchbar bleibt), `swisstopo:hauptgipfel=<Gipfelname>`, `swisstopo:hauptgipfel_ele` (z. B. „Pilatus“ am Tomlishorn). Ohne Gipfel `natural=mountain_range` in der Fläche. Ein Massiv der Namenklasse 1–3 bekommt zusätzlich einen sichtbaren Punkt `natural=mountain_range` in der Fläche (z. B. „Rigi“), weil der Suchpunkt am Gipfel unsichtbar ist |
| `Huegelzug` | `natural=mountain_range` |
| `Gletscher` | `natural=glacier` (nur Punkt) |
| `Gebiet`, `Landschaftsname`, `Grossregion` | `place=region` |
| `Seeteil` | `place=locality` |
| `See` | `place=lake` (Seename als Punkt). Der Name steht ausserdem auf der Wasserfläche |

Seen, Gletscher sowie Gebiets-, Tal-, Grat- und Bergnamen tragen `swisstopo:namenklasse` 1–4
(`src/vector/labelclass.py`), nach demselben Prinzip wie die Gipfelklassen:

| Klasse | Quelle | Seen CH | Gletscher CH | Gebiete, Täler CH |
|---|---|---|---|---|
| 1 | Anno-Text in SMV1000 (Seen: `T07_DKM1M_GEWAESSER_PLY_ANNO`, sonst `T05_DKM1M_GELAENDENAME_ANNO`) | 9 | 0 | 16 |
| 2 | Anno-Text in SMV500 (`T07`, `T05`, Gebiete auch `T04_DKM500_GEBIETSNAME_ANNO`) | 25 | 7 | 98 |
| 3 | gleichnamige Fläche in swissTLMRegio (`tlmregio_names_namedlocation_ply`) | 57 | 50 | 492 |
| 4 | alle übrigen | 1396 | 697 | 18 486 |

Beispiele: Bodensee und Zürichsee (1), Walensee (2), Grosser Aletschgletscher (2), Toggenburg und Goms
(1), Werdenberg (2), Fürstenland (3). Ein Anno-Text liegt höchstens 5 km (SMV1000) bzw. 3 km (SMV500)
neben der Fläche. Er muss Wort für Wort dem Namen entsprechen. Abkürzungen mit Punkt gelten als Anfang
eines Worts („Gr. Aletschgletscher“, „Gouwligl.“). Ein über die Zeile getrenntes Wort („Vierwald-“)
gilt, wenn der Name damit beginnt oder endet.

Die Areal-Namen (`TLM_NUTZUNGSAREAL`, `TLM_FREIZEITAREAL`, `TLM_VERKEHRSAREAL`) kommen direkt aus
den TLM-Arealen, die Siedlungsnamen-Polygone werden nicht übernommen (Punkte reichen).

## Grenzen (swissBOUNDARIES3D)

`tlm_hoheitsgrenze` als Linien:

| objektart | OSM-Tags |
|---|---|
| 1 (Landesgrenze) | `boundary=administrative`, `admin_level=2` |
| 2 (Kantonsgrenze) | `boundary=administrative`, `admin_level=4` |
| 3 (Bezirksgrenze) | `boundary=administrative`, `admin_level=6` |
| 4 (Gemeindegrenze) | `boundary=administrative`, `admin_level=8` |

Die Gemeinde- und Kantonsflächen dienen nur zur Zuordnung (`is_in:*`), sie werden nicht als
Flächen geschrieben.

## POIs (`src/vector/pois.py`)

Alle POIs sind eigene Knoten mit Namen (wo vorhanden) und `swisstopo:poi=<herkunft>`. POIs gleicher
Herkunft und Objektart mit gleichem Namen im Umkreis von 100 m werden nur einmal geschrieben
(z. B. mehrere Haltekanten eines Bahnhofs). Flächen-POIs
liegen am inneren Punkt der Fläche. mkgmap läuft **ohne** `--add-pois-to-areas`, sonst entstünden
doppelte POIs.

| Quelle | OSM-Tags | `swisstopo:poi` |
|---|---|---|
| `tlm_eo_einzelobjekt` `Gipfelkreuz` | `man_made=cross`, `summit:cross=yes` | `einzelobjekt` |
| `Bildstock` | `historic=wayside_shrine` | |
| `Brunnen` | `amenity=fountain` (ob Trinkwasser, ist nicht bekannt) | |
| `Quelle` | `natural=spring` | |
| `Wasserfall` | `waterway=waterfall` | |
| `Denkmal` | `historic=memorial` | |
| `Grotte, Hoehle` | `natural=cave_entrance` | |
| `Triangulationspyramide` | `man_made=survey_point`, `survey_point:structure=pyramid` | |
| `Wasserversorgung` (nur mit Name) | `man_made=water_works` | |
| `tlm_oev_haltestelle` `Haltestelle Bahn` | `railway=station`, `public_transport=station`, `train=yes` | `haltestelle` |
| `Haltestelle Bus` | `highway=bus_stop`, `public_transport=platform`, `bus=yes` | |
| `Haltestelle Schiff` | `amenity=ferry_terminal`, `public_transport=station` | |
| `Uebrige Bahnen` | `aerialway=station`, `public_transport=station` | |
| `dienststellen_nummer` | `uic_ref` | |
| alle Haltestellen | `swisstopo:oev` = `bahn`/`tram`/`bus`/`schiff`/`seilbahn` (Regeln unter der Tabelle). `swisstopo:oev_rang` = 1 Bahn-Umsteigeknoten (Bus/Schiff ≤ 150 m), 2 Bahn, 3 Schiff und übrige Bahnen, 4 Bus (für prominentere Darstellung) | |
| `Haltestelle Bahn` | `swisstopo:bahnhof_rang` aus swissTLM3D allein (kein Fahrplan): 1 Grossbahnhof (Perronfläche im Umkreis 200 m ≥ 5000 m²: St. Gallen, Wil, Rorschach), 2 Knoten (≥ 3000 m²: Gossau, Herisau, Wattwil), 3 Bahnhof (≥ 1500 m² oder ≥ 4 Gleise auf einem Kreis von 100 m: Uzwil, Flawil, Appenzell, St. Fiden), 4 übrige Halte (Bettwiesen). Dazu `swisstopo:perronflaeche_m2`. Näherung für Fernverkehrs- bzw. Knotenbahnhöfe | |
| `tlm_oev_uebrige_bahn` Linienenden (Luftseil-, Gondel-, Sesselbahn, Skilift) | `aerialway=station`, `name=<Bahn> Talstation/Bergstation` (tiefer/höher nach Z), `ele`, `swisstopo:oev` = `skilift` (Skilift) bzw. `seilbahn`, `swisstopo:oev_art` | `seilbahnstation` (nur, wenn keine Haltestelle „Uebrige Bahnen“ im Umkreis von 80 m) |
| Freizeitareal `Campingplatzareal` | `tourism=camp_site` | `areal` |
| `Schwimmbadareal` | `leisure=water_park` | |
| `Golfplatzareal` | `leisure=golf_course` | |
| `Zooareal` | `tourism=zoo` | |
| `Sportplatzareal` | `leisure=sports_centre` | |
| `Standplatzareal` | `tourism=caravan_site` | |
| Nutzungsareal `Spitalareal` | `amenity=hospital` | |
| `Friedhof` | `amenity=grave_yard` | |
| `Klosterareal` | `amenity=monastery` | |
| `Schul- und Hochschulareal` | `amenity=school` | |
| `Historisches Areal` | `historic=yes`, `tourism=attraction`. Art aus dem Namen (`swisstopo:poi_heuristik=name`, de/fr/it): Ruine/Burgstelle/Ruderi/Sito castrale → `historic=ruins`, `ruins=castle`. Prähistorisch/römisch/Kastell/Wehranlage → `historic=archaeological_site`. Kloster/Kartause/Propstei → `historic=monastery`. Burg/Schloss/Schlössli/Château/Castello/Wohnturm → `historic=castle`. Letzi/Schanze → `historic=citywalls`. Landesweit 1312 Areale, 179 bleiben `historic=yes` | |
| weitere Nutzungsareale (Park, ARA, Kraftwerk, KVA, Deponie, Abbau, Messe, Waffenplatz, Strafanstalt) | wie Flächen, siehe Areale | |
| Verkehrsareal `Oeffentliches Parkplatzareal` | `amenity=parking` | |
| `Rastplatzareal` | `highway=rest_area` | |
| `Flugfeld-/Flugplatz-/Flughafenareal` | `aeroway=aerodrome` | |
| `Heliport` | `aeroway=heliport` | |
| `tlm_strassen_strasseninfo` `Raststaette` | `highway=services` | `strasseninfo` |
| `Verladestation` (Autoverlad) | `railway=station`, `service=car_shuttle`, `motorcar=yes` | |
| `Zahlstelle` | `barrier=toll_booth` | |
| `Zollamt …` | `amenity=customs` (zusätzlich `barrier=border_control` auf dem Strassenknoten) | |
| Gebäude `Kapelle` | `amenity=place_of_worship`, `building=chapel` | `gebaeude` |
| `Sakrales Gebaeude`, `Sakraler Turm` | `amenity=place_of_worship` | |
| `Turm` | `man_made=tower` | |
| `nutzung=Aussichtsturm` | `man_made=tower`, `tower:type=observation`, `tourism=viewpoint` | |
| `nutzung=Gasthof abgelegen` | `amenity=restaurant` | |
| `nutzung=Observatorium`, `Stadion`, `Schiessstand`, `Parkhaus`, `Sporthalle` | `man_made=observatory`, `leisure=stadium`, `sport=shooting`, `parking=multi-storey`, `leisure=sports_hall` | |
| `nutzung=Schutzhuette`, `Wasserturm`, `Leuchtturm` (neu) | `tourism=wilderness_hut`, `man_made=water_tower`, `man_made=lighthouse`. Kombinierte Nutzungen („Aussichtsturm, Wasserturm“) bekommen die Tags aller Teile | |
| benanntes Gebäude ohne Klasse | `building=yes` + `name` (Stil entscheidet) | |
| `tlm_bauten_versorgungsbaute_pkt` `Antenne gross`, `Windturbine` | `man_made=mast`, `power=generator` (siehe Bauten) | – |

Regeln für `swisstopo:oev` (die Basiskarte lässt Tramhalte weg, das Overlay zeigt sie als ÖV-Halt):

- `tram`: `Haltestelle Bahn` mit Tramgleis (`tlm_oev_eisenbahn`, `verkehrsmittel=Tram`) im Umkreis von 20 m und
  ohne anderes Gleis dort. Anschlussgleise zählen nicht. Dazu `tram=yes` statt `train=yes`. Schweiz: ca. 1100 von
  3157 Bahnhalten, z. B. in Bern, Basel, Zürich und Genf.
- `bahn`: übrige Halte der Art `Haltestelle Bahn`, auch Metro-Halte (Lausanne).
- `bus`: `Haltestelle Bus`, auch nahe an einem Tramgleis.
- `schiff`: `Haltestelle Schiff`.
- `seilbahn`: `Uebrige Bahnen` und die Stationen an den Linienenden von Seilbahnen. Skilift-Stationen bekommen
  `skilift`. `swisstopo:oev_art` nennt die Art: `luftseilbahn`, `gondelbahn`, `sesselbahn`, `lift` oder
  `skilift`. Bei Haltestellen kommt die Art von der nächsten Seilbahn im Umkreis von 80 m.

**Heuristik nach Gebäudename** (nur, wenn Objektart/Nutzung nichts liefert, Tag
`swisstopo:poi_heuristik=name`):

| Name enthält | OSM-Tags |
|---|---|
| `SAC`, `Clubhütte`, `Passhütte`, `Berghütte`, `Berghaus` | `tourism=alpine_hut` |
| `Waldhütte`, `Schirmhütte`, `Grillhütte`, `Forsthütte`, `Schützenhütte`, `Pfadihütte` | `amenity=shelter`, `shelter_type=basic_hut` |
| `Hotel` | `tourism=hotel` |
| `Berggasthaus`, `Gasthaus`, `Gasthof`, `Restaurant`, `Alpwirtschaft`, `Beizli`, `Wirtschaft` | `amenity=restaurant` |

Andere „…hütte“-Namen (meist Alphütten) bleiben benannte Gebäude ohne Klasse. Mehrere
Footprints mit gleichem Namen innerhalb von 150 m ergeben einen POI (am grössten Footprint).

Nicht in swissTLM3D und deshalb nicht enthalten: Restaurants und Hotels ohne Hinweis im Namen,
Läden, Tankstellen, Apotheken usw. Fremdquellen dafür nur nach Rücksprache.
