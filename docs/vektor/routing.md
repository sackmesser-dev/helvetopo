# Routing und Präferenz für Velo und Wandern

Stand: 2026-11-04. Stilregeln: `src/style/swisstopo/inc/routing_pref`. Prüfwerkzeuge: `src/routing/`.

## Wie Garmin auf mkgmap-Karten routet

### Attribute einer Kante

| Attribut | mkgmap | je Profil |
|---|---|---|
| Strassenklasse 0–4 | `road_class`, `mkgmap:road-class` | nein |
| Geschwindigkeitsklasse 0–7 | `road_speed`, `mkgmap:road-speed-class`, `mkgmap:road-speed` | nein |
| Zugang | `mkgmap:foot`, `bicycle`, `car`, `truck`, `bus`, `taxi`, `delivery`, `emergency` | ja |
| Durchfahrt | `mkgmap:throughroute=no` (nur Start und Ziel) | nein |
| Vermeidbar | `mkgmap:toll`, `mkgmap:unpaved`, `mkgmap:ferry`, `mkgmap:carpool` | Flag gemeinsam, Vermeidung je Profil |
| Abbiegeverbote | `type=restriction`-Relationen, je Fahrzeug | ja |

- Garmin speichert je Kante eine Strassenklasse und eine Geschwindigkeitsklasse für alle
  Verkehrsmittel. Profilabhängig sind nur Zugang und Vermeidungen.
- `mkgmap:road-class` und `mkgmap:road-speed-class` als Tag überschreiben die Werte in der
  Elementdefinition. Der Stil setzt sie in Abschnitt 1 von `src/style/swisstopo/lines`.
- `--link-pois-to-ways` überträgt Zugang und Geschwindigkeit von Barrieren-POIs auf ein kurzes
  Wegstück. Der Build verwendet die Option.
- `--cycle-map` ist für reine Velokarten. Helvetopo verwendet die Option nicht.
- Abbiegekosten berechnet Garmin intern aus Winkel und Klasse.
- „Popularity Routing“ gibt es nur auf Garmin-eigenen Karten.

### Gewichtung der Profile

Garmin veröffentlicht die Kostenfunktion nicht. Bekannt bzw. gemessen:
- **Auto:** Zeit ≈ Länge / Geschwindigkeitsklasse. Auf langen Routen nutzt der Router im mittleren
  Teil nur höhere Klassen.
- **Velo (BaseCamp):** routet nach Distanz plus Vermeidungen. Die Geschwindigkeitsklasse spielt kaum
  eine Rolle. BaseCamp rechnet konstant ca. 19 km/h.
- **Zugang** wirkt hart, ausser das Ziel ist sonst unerreichbar (Zielausnahme, siehe
  [basiskarte.md](basiskarte.md#garmin-verhalten)).
- **Vermeidungen** wirken als sehr hohe Zusatzkosten, nicht als Verbot. In BaseCamp wirken sie fast
  wie ein Verbot. OpenMTBMap/VeloMap nutzen dafür das Maut-Flag
  ([openmtbmap.org: About the Autorouting](https://openmtbmap.org/?p=42)).
- BaseCamp und Gerät rechnen bei gleichem Profil und gleichen Vermeidungen gleich. Vermeidungen
  stehen in BaseCamp unter *Bearbeiten → Optionen → Aktivitätsprofile → Routing/Vermeidungen*, am
  GPSMAP/Montana unter *Einrichten → Routing → Vermeidungen*. Beide speichern sie je Profil.
- Das Velo-Profil von BaseCamp hat standardmässig viele Vermeidungen aktiv, u. a. Autobahnen,
  Bundesstrassen, unbefestigte Strassen, Steige und schmale Wege.
- Edge-Geräte haben laut OpenMTBMap keine Maut-Vermeidung im Velo-Profil.

## Datenlage

Kilometer im Testgebiet nach Autozugang:

| | mit Autoverkehr | autofrei |
|---|---|---|
| Veloland | 346 km | 65 km |
| Mountainbikeland | 175 km | 81 km |
| Wanderweg | 933 km | 1875 km |
| Bergwanderweg, Alpinwanderweg | 8 km, 0 km | 270 km, 13 km |

- Wanderwege liegen zu zwei Dritteln auf autofreien Kanten.
- Veloland liegt zu über 80 % auf Strassen mit Autoverkehr. Eine Präferenz über Klasse oder
  Geschwindigkeit lenkt dort auch Autos um.
- 19 % der Velo- und MTB-Routenkanten haben Naturbelag.
- swissTLM3D kennt keine Velostreifen und kein Maut-Attribut. Zahlstellen sind Punkte
  (`barrier=toll_booth`).

## Regeln

Der Konverter liefert alle nötigen Tags (`route_bicycle`, `ncn`/`rcn`/`lcn`, `mtb`,
`bicycle=designated`, `sac_scale`, `swisstopo:belagsart`). Die Regeln stehen im Stil.

| Regel | Wirkung |
|---|---|
| A1 | Autofreie Veloland- und MTB-Kanten national und regional: Geschwindigkeit 3, Klasse 1 |
| A2 | Autofreie lokale Velo- und MTB-Routen und `cycleway`: Geschwindigkeit 2 |
| A3 | Autofreie Wander- und Bergwanderwege auf Pfaden: Geschwindigkeit 0 → 1. Fahrwege bleiben bei 1. Alpinwanderwege bleiben bei 0. |
| A4 | Maut-Flag auf autofreien Pfaden, Fusswegen, Treppen und Klettersteigen ohne Velo- oder MTB-Route |
| A5 | Maut-Flag auf `trunk`, `primary`, `secondary` (inkl. `_link`) ohne Velo- oder MTB-Route |
| A5b | Maut-Flag zusätzlich auf `tertiary` ohne Velo- oder MTB-Route (nur `velo_toll=stark`) |
| A6 | Veloland-Kanten verlieren `mkgmap:unpaved`. MTB-Routen behalten das Flag. Die Regel steht in `lines` nach der Belag-Regel. |
| B1, B2 | Nur `routing_pref=velo`: Velorouten auf Nebenstrassen Geschwindigkeit 3, auf `tertiary` 4. Hauptstrassen ohne Veloroute Geschwindigkeit 2 und Maut-Flag. |

Schalter über `mkgmap --style-option`: `routing_pref=off|basis|velo`, `velo_toll=off|on|stark`.
Standard in `src/build/config.sh`: `STYLE_OPTIONS=routing_pref=basis;velo_toll=stark`.

Grundsätze:
- Klasse und Geschwindigkeit ändern sich nur auf Kanten ohne Autozugang. Auf Strassen mit
  Autoverkehr kommt höchstens das Maut-Flag dazu.
- Keine Routennamen in der Basiskarte. Namen und Nummern zeigt das Routen-Overlay.
- Die Basiskarte zeichnet Wege im LK-Stil. Die Wanderwegsignatur kommt aus dem Overlay.

### Bedienung

Velo und MTB: Im Aktivitätsprofil „Mautstrassen vermeiden“ einschalten. Dann folgt die Route
möglichst dem SchweizMobil-Netz, auch mit Umwegen. Sie meidet Hauptstrassen und
Verbindungsstrassen ohne Veloroute und reine Fusswege. „Unbefestigte Strassen vermeiden“ meidet
Naturbelag ausserhalb der Velorouten.

Auto und Wandern: „Mautstrassen vermeiden“ ausschalten. Die Karte kennt keine Mautgebühren. Mit
der Vermeidung im Auto-Profil fährt die Route St. Gallen → Wil 30,1 statt 28,4 km.
„Autobahnen vermeiden“ nicht verwenden.

## Messwerte

### Prüfwerkzeuge

- `src/routing/compare_routes.py` liest die Basis-PBF, bildet Zugang, Klasse, Geschwindigkeit, Maut
  und Belag wie der Stil nach und vergleicht Dijkstra-Routen je Variante. Kostenmodell „Zeit“:
  Länge / Garmin-Geschwindigkeitstabelle (Stufe 0 = 5 km/h). Kostenmodell „Distanz“: Länge.
  Vermeidung: Kosten × 1000. Klassenhierarchie und Profileigenheiten sind nicht modelliert.
- `src/routing/gpx_match.py` bildet eine GPX-Route aus BaseCamp auf die Basis-PBF ab (Abtastung alle
  5 m, nächste routbare Kante bis 15 m). GPX-Dateien mit DOCTYPE oder ENTITY lehnt das Werkzeug ab.

```bash
.venv/bin/python -I src/routing/compare_routes.py <basis.osm.pbf> --json work/routing/compare.json
```

### Velo St. Gallen Bahnhof → Wil Bahnhof

BaseCamp, Stil `basis` mit `velo_toll=stark`, ausgewertet mit `gpx_match.py`:

| Profil | km | Veloland | Hauptstrasse | Verlauf |
|---|---|---|---|---|
| Velo, BaseCamp-Standard | 30,2 | 5,8 (19 %) | 16,7 | Talachse über Fürstenlandstrasse |
| Velo, Standard + Maut vermeiden | 32,6 | 29,8 (92 %) | 0,3 | Regionalroute 33 über Thurdamm, Nielenweg, Uzwil |
| wie oben, „schmale Wege“ aus | gleiche Geometrie | | | |

Das Distanzmodell trifft BaseCamp auf 0,4 km: 32,6 km mit 30,2 km Veloland. Mit `velo_toll=on`
(ohne A5b) sagt das Modell 31,6 km mit 26,0 km Veloland (82 %) voraus.

Ohne A6 machte die Kombination „Maut + unbefestigt vermeiden“ einen Umweg von 53 km, weil 8 km der
Veloroute Naturbelag haben.

### Preis von `velo_toll=stark`

Modell, Distanz, Maut und unbefestigt vermeiden (km gesamt / km Veloland):

| Strecke | ohne Vermeidung | basis | stark |
|---|---|---|---|
| Herisau → Appenzell | 17,3 / 8,7 | 19,8 / 17,6 | 19,9 / 18,4 |
| St. Gallen → Appenzell | 15,9 / 13,4 | 17,2 / 16,3 | 17,7 / 16,9 |
| Wil → Herisau | 22,1 / 3,9 | 24,8 / 17,3 | 29,7 / 26,4 |
| Gossau → Herisau | 4,4 / 0,2 | 4,4 / 0,2 | 7,8 / 5,7 |

Abseits des Velonetzes werden Routen mit Maut-Vermeidung länger (im Testgebiet 195 km `tertiary`
ohne Veloroute).

### Wandern und Fuss

- Wasserauen → Säntis (BaseCamp): 9,8 km über Seealp und den Bergwanderweg.
- Modell Zeit ohne A3: 32,9 km mit 24,2 km Hauptstrasse. Mit A3: 10,0 km mit 9,3 km Bergwanderweg.
- Gossau → Herisau zu Fuss: in allen Varianten 4,5 km auf Strassen.

### Auto

- Matrix über 30 Ortspaare (Wil, St. Gallen, Gossau, Herisau, Appenzell, Wasserauen): `basis` und
  `stark` ändern keine Route. `routing_pref=velo` ändert 22 von 30 Routen (bis 5,8 km).
- BaseCamp St. Gallen → Wil: 29,2 km über die A1. Die A1 ist unbenannt (`ref=A1`). Die
  „Toggenburgerstrasse“ in der Wegbeschreibung ist das Endstück nach der Ausfahrt Wil.

### Grösse

gmapsupp Testgebiet (7701, Höhenlinien eingebaut): `off` 32 856 064 B, `basis` 32 894 976 B,
`velo` 32 899 072 B.

## Varianten

| Variante | Velo | Wandern | Auto | Kosten |
|---|---|---|---|---|
| autofrei (A1–A4) | gering | gut | unverändert | keine |
| basis (A1–A6), `velo_toll=on` | stark mit Maut-Vermeidung | gut | unverändert ohne Maut-Vermeidung | ein Haken je Profil |
| basis mit `velo_toll=stark` (Standard) | stärker, mehr Umwege | gut | unverändert ohne Maut-Vermeidung | ein Haken je Profil |
| velo (eigene Karte, B1/B2) | stark auch ohne Vermeidung | gut | Auto-Profil unbrauchbar | eigene FID, CH ca. +450–700 MB, BaseCamp zeigt nur eine Familie gleichzeitig |

Eine eigene Velokarte gibt es nicht. Eine Erhöhung von Klasse oder Geschwindigkeit auf Strassen mit
Autoverkehr („mild“) ändert im Modell keine Velo-Route und schafft Schleichwege fürs Auto.

## Offene Fragen

- Nutzt das GPSMAP 66/67 im Velo- und Fussprofil die Geschwindigkeitsklasse?
- Ist im Velo- oder Wanderprofil neuerer Geräte eine Vermeidung voreingestellt (laut OpenMTBMap
  Fahrgemeinschaftsspuren)? Dann wäre `mkgmap:carpool` ein Hebel ohne Bedienung.
- A4 hält Velos auch von kurzen, erlaubten Verbindungspfaden fern.
- Echte Maut: Der Grosse-St.-Bernhard-Tunnel (`trunk`) hat das Maut-Flag nur über A5. Der Tunnel
  Munt la Schera (`tertiary`) hat es nur mit `velo_toll=stark`. Autobahnen haben kein Flag.
- Einige Hauptstrassen heissen im Strassenverzeichnis „A1“, „Nationalstrasse“ oder
  „Durchgangsstrasse“. Die Namen erscheinen in Wegbeschreibungen.

## Quellen

- mkgmap-dev zum Velo- und Fussrouting: [2009](https://mkgmap.org.uk/pipermail/mkgmap-dev/2009q2/001912.html),
  [2010](https://mkgmap.org.uk/pipermail/mkgmap-dev/2010q2/008109.html)
- OpenMTBMap: [About the Autorouting](https://openmtbmap.org/?p=42)
