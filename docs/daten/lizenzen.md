# Lizenzen der Quelldaten

Stand: 2026-11-03 (Recherche). Diese Datei beschreibt die Lizenzen der Daten, die Helvetopo
verwendet. Die Lizenz der Kartendateien steht in [LICENSE-KARTEN.md](../../LICENSE-KARTEN.md),
die Lizenz des Codes in [LICENSE](../../LICENSE).

## Zulässige Quellen

Helvetopo verwendet nur zwei Gruppen von Quellen:

| Quelle | Lizenz | Pflicht-Quellenangabe |
|---|---|---|
| swisstopo-Daten | swisstopo-OGD | `©swisstopo` |
| SchweizMobil-Routen Wanderland, Veloland, Mountainbikeland, Skatingland (`ch.astra.*`) | Opendata BY | `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` |
| Kanuland, hindernisfreie Wege, Winterrouten (Stiftung SchweizMobil) | Open Data BY | `Stiftung SchweizMobil` |

Die Quellenangabe gehört in das Copyright-Feld der IMG (beide Zeilen), in Kartenname bzw.
Beschreibung, auf die Downloadseite und in README und LICENSE jedes Downloads. Jeder Build prüft
mit `src/build/check_license.sh`, dass keine OSM- oder ODbL-Texte in der Karte stehen.

Nicht zulässig sind:
- OpenStreetMap (ODbL, Share-Alike) und mkgmap-Hilfsdaten auf OSM-Basis
- kantonale Daten (eigene Bedingungen je Kanton, teils mit Bewilligungspflicht)
- kostenpflichtige swisstopo-Varianten (siehe unten)
- SchweizMobil-Logos und -Marken, die SchweizMobil-Webkarten-API, GPX-Dateien auf Antrag, Fotos
  und Daten von der Website schweizmobil.ch

Eine neue Quelle braucht vorher eine dokumentierte Prüfung der Lizenzfolgen.

## swisstopo-OGD

Bedingungen: <https://www.swisstopo.admin.ch/ogd-conditions>. Sie gelten seit dem 1. März 2021.

- Nutzung, Bearbeitung, Weitergabe und Veröffentlichung sind erlaubt, auch kommerziell.
- Die Quellenangabe ist Pflicht, digital und analog und auch bei Weitergabe. Zulässig sind
  `©swisstopo`, `Bundesamt für Landestopografie swisstopo` und `Federal Office of Topography
  swisstopo` (auch auf Französisch, Italienisch, Rätoromanisch).
- swissALTIRegio und swissEO verlangen einen eigenen Wortlaut aus der Datendokumentation.
  Helvetopo verwendet diese Produkte nicht.
- Zusätzlich gelten die allgemeinen Nutzungsbedingungen der BGDI. Bei übermässiger Nutzung der
  Infrastruktur (z. B. massives Abrufen von WMTS-Kacheln) kann swisstopo den Zugang sperren.
  Helvetopo bezieht Daten deshalb nur über den STAC-Katalog `data.geo.admin.ch`.
- Eine IMG ist ein abgeleitetes Produkt. Für eine öffentliche Weitergabe braucht es keine
  Bewilligung und keinen Vertrag.

Nicht frei (Gebühr oder kostenpflichtige Dienstleistung):
- ältere Datenversionen auf Bestellung
- Swiss Map Vector mit abweichendem Perimeter und als Vektor-PDF
- Swiss Map Raster als einzelne thematische Ebenen (EE) und als CMYK-Druckdaten (1270 dpi)

Liechtenstein: Swiss Map Vector, Swiss Map Raster und swissTLM3D enthalten das Gebiet von
Liechtenstein unter OGD. Eigene Landesdaten von Liechtenstein haben eigene Bedingungen.

### swisstopo-Produkte unter OGD

Vektor:

| Produkt | Inhalt | Formate | STAC-Collection |
|---|---|---|---|
| Swiss Map Vector 10 | 1:10'000, Kartengrafik | GDB, GPKG | `ch.swisstopo.swiss-map-vector10` |
| Swiss Map Vector 25 | 1:25'000, Kartengrafik | GDB, GPKG | `ch.swisstopo.swiss-map-vector25` |
| Swiss Map Vector 500 | 1:500'000 | GDB, GPKG | `ch.swisstopo.swiss-map-vector500` |
| Swiss Map Vector 1000 | 1:1 Mio. | GDB, GPKG | `ch.swisstopo.swiss-map-vector1000` |
| swissTLM3D | Landschaftsmodell: Strassen, Wege, Gewässer, Gebäude, Bodenbedeckung | GDB, GPKG, SHP, Interlis | `ch.swisstopo.swisstlm3d` |
| swissTLM3D Wanderwege | Wanderwegnetz | GPKG, GDB | `ch.swisstopo.swisstlm3d-wanderwege` |
| swissTLMRegio | Landschaftsmodell ca. 1:250'000 | GDB, GPKG, SHP | `ch.swisstopo.swisstlmregio` |
| swissNAMES3D | Orts- und Flurnamen | SHP, GDB, CSV | `ch.swisstopo.swissnames3d` |
| swissBOUNDARIES3D | Landes-, Kantons-, Gemeindegrenzen | SHP, GDB, GPKG | `ch.swisstopo.swissboundaries3d` |
| swissBUILDINGS3D | 3D-Gebäude | diverse | `ch.swisstopo.swissbuildings3d_*` |

- Swiss Map Vector 50, 100 und 200 gibt es nicht.
- Swiss Map Vector 10 erhält 2026 kein vollständiges Update (ca. ein Sechstel der Schweiz). Ab 2027
  ist das Update wieder jährlich.

Raster:

| Produkt | Inhalt | Format | STAC-Collection |
|---|---|---|---|
| Swiss Map Raster 10 | Landeskarte 1:10'000 | GeoTIFF | `ch.swisstopo.landeskarte-farbe-10` |
| Swiss Map Raster 25 | 1:25'000, 508 dpi | GeoTIFF | `ch.swisstopo.pixelkarte-farbe-pk25.noscale` |
| Swiss Map Raster 50 | 1:50'000, 508 dpi | GeoTIFF | `ch.swisstopo.pixelkarte-farbe-pk50.noscale` |
| Swiss Map Raster 100 | 1:100'000 | GeoTIFF | `ch.swisstopo.pixelkarte-farbe-pk100.noscale` |
| Swiss Map Raster 200 | 1:200'000 | GeoTIFF | `ch.swisstopo.pixelkarte-farbe-pk200.noscale` |
| Swiss Map Raster 500 | 1:500'000 | GeoTIFF | `ch.swisstopo.pixelkarte-farbe-pk500.noscale` |
| Swiss Map Raster 1000 | 1:1 Mio. | GeoTIFF | `ch.swisstopo.pixelkarte-farbe-pk1000.noscale` |
| SWISSIMAGE 10 cm | Orthofoto | COG | `ch.swisstopo.swissimage-dop10` |
| swissALTI3D | Höhenmodell 0,5 m und 2 m | COG, XYZ | `ch.swisstopo.swissalti3d` |
| swissSURFACE3D Raster | Oberflächenmodell | COG | `ch.swisstopo.swisssurface3d-raster` |

SWISSIMAGE 10 cm hat im STAC ebenfalls keinen Lizenz-Link (`license: proprietary`). Das Produkt gehört zu den
swisstopo-OGD-Daten. Die Collection `ch.swisstopo.swissimage` (SWISSIMAGE Background) verweist auf die
OGD-Bedingungen.

Die Landeskarte Winter (`ch.swisstopo.landeskarte-farbe_winter_*`) hat im STAC keinen Lizenz-Link.
Vor einer Verwendung ist die Lizenz zu prüfen.

Varianten von Swiss Map Raster (Produktblatt Nov. 2024):

| Variante | Beschreibung | Frei |
|---|---|---|
| KREL | Farbe mit Relief, RGB, 508 dpi | ja |
| KOMB | Farbe ohne Relief, indizierte Farben (nicht für SMR 10) | ja |
| KGRS | Graustufen ohne Relief | ja |
| KRELWINTER | Winterdarstellung mit Relief | ja |
| EE | einzelne thematische Ebenen | nein |
| CMYK | 1270 dpi für Nachdrucke | nein |

## Wanderwege und SchweizMobil-Routen

Kein untersuchter Bundesdatensatz zu Wanderwegen oder SchweizMobil-Routen hat die
opendata.swiss-Kategorie `terms_ask` oder `terms_by_ask`. Das wurde in der opendata.swiss-API für
jede Ressource geprüft. Umwandlung, Weitergabe und kommerzielle Nutzung sind erlaubt.

| Datensatz | Datenherr | Lizenz | Quellenangabe | Bezug |
|---|---|---|---|---|
| swissTLM3D Wanderwege (`ch.swisstopo.swisstlm3d-wanderwege`) | swisstopo, mit ASTRA, SchweizMobil, Schweizer Wanderwege, Kantonen | swisstopo-OGD | `©swisstopo` | STAC: GPKG-ZIP (ca. 198 MB), GDB-ZIP, LV95 |
| swissTLM3D, Attribut `WANDERWEGE` in `TLM_STRASSE` | swisstopo | swisstopo-OGD | `©swisstopo` | STAC `ch.swisstopo.swisstlm3d` |
| Wanderland (`ch.astra.wanderland`) | ASTRA, Kantone, Stiftung SchweizMobil | Opendata BY (`terms_by`) | `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` | STAC: GPKG (ca. 130 MB), GDB, SHP |
| Veloland (`ch.astra.veloland`) | wie Wanderland | `terms_by` | wie Wanderland | STAC: GPKG (ca. 96 MB) |
| Mountainbikeland (`ch.astra.mountainbikeland`) | wie Wanderland | `terms_by` | wie Wanderland | STAC: GPKG (ca. 100 MB) |
| Skatingland (`ch.astra.skatingland`) | wie Wanderland | `terms_by` | wie Wanderland | STAC: GPKG (ca. 4 MB) |
| Kanuland | Stiftung SchweizMobil | Open Data BY, keine Geobasisdaten nach GeoIV | `Stiftung SchweizMobil` | `data.schweizmobil.ch/gpkg_export/kanu.gpkg` |
| Hindernisfreie Wege | Stiftung SchweizMobil | Open Data BY | `Stiftung SchweizMobil` | im Wanderland-Datensatz |
| Winter- und Schneeschuhwanderwege (`ch.astra.winterwanderwege`, `ch.astra.schneeschuhwanderwege`) | ASTRA, SchweizMobil, Schweizer Wanderwege, Kantone | `terms_by` | `Stiftung SchweizMobil` | STAC: GPKG |
| Langlauf, Schlitteln | Stiftung SchweizMobil | Open Data BY | `Stiftung SchweizMobil` | `data.schweizmobil.ch/gpkg_export/` |
| Sperrungen und Umleitungen (`ch.astra.*-sperrungen_umleitungen`) | ASTRA und weitere | `terms_by` | wie Routen | tagesaktuell, für eine statische IMG ungeeignet |

opendata.swiss kennt vier Kategorien: `terms_open` (freie Nutzung), `terms_by` (Quellenangabe
Pflicht), `terms_ask` (kommerzielle Nutzung nur mit Bewilligung) und `terms_by_ask`.

### swissTLM3D Wanderwege und Attribut `WANDERWEGE`

- Das Wanderwegnetz ist der Geobasisdatensatz Nr. 38.1. Die Kantone liefern die Daten, swisstopo
  integriert sie. Einen eigenen ASTRA-Layer „Wanderwege“ gibt es nicht.
- Domäne `TLM_WANDERWEGE_CD` (Objektkatalog swissTLM3D 2.4, Februar 2026): `0` Wanderweg,
  `1` Bergwanderweg, `2` Alpinwanderweg, `3` andere, `NULL` nicht erfasst. Der Objektkatalog
  erklärt den Wert `3` nicht näher.
- Die Objektart `Markierte Spur` hat keinen sichtbaren Weg, trägt aber einen markierten
  Langsamverkehrsweg. Markierte Wanderwege haben in swissTLM3D keine Minimallänge.
- Aktualisierung: jährlich mit swissTLM3D, dazu punktuelle Korrekturen.
- Die Wanderwegklassierung kommt mit swissTLM3D. Dafür braucht es keinen zweiten Datensatz und
  keine weitere Quellenangabe.

### SchweizMobil-Routen

- Die Geobasisdaten gehören dem ASTRA, den Kantonen und der Stiftung SchweizMobil. Auf
  opendata.swiss ist das ASTRA Publisher. Kontakt- und Vertriebsstelle ist die Stiftung SchweizMobil.
- geocat nennt Zugangsberechtigungsstufe A (GeoIV Art. 21), Opendata BY und die Pflicht-Quellenangabe
  `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`.
- Datenmodell (MGDM Langsamverkehr): Tabellen `Route`, `Etappe` und `Weg`. Wichtige Attribute:
  `NrR` (Routennummer), `TourNameR` (offizieller Name), `Routenart`, `Richtung`, `BelagTLM`,
  `WegKat` (nur Wanderland), `IsSTrail` (nur Mountainbike), `TLM_ID`.
- Die Geometrien beruhen auf swissTLM3D. Fehlende Wegstücke erfasst SchweizMobil provisorisch
  selbst. Segmente im Ausland sind nur informativ.
- Aktualisierung: jährlich im Frühjahr.
- Den Routennamen und die Routennummer darf Helvetopo als Attribut übernehmen. Routennummer-Schilder
  dürfen frei für die Kommunikation der jeweiligen Route verwendet werden.

Bedingungen der Stiftung SchweizMobil für andere Inhalte:
- Texte: CC-BY-SA. Fotos nur im Kontext der SchweizMobil-Routen.
- Namen und Logos sind in der Regel eingetragene Marken. Logos gibt es nur für Partner.
- Die Webkarten-API gibt es nur für Partner. GPX-Dateien gibt es nur für Partner und
  SchweizMobil-Plus-Nutzende.
- Die Website schweizmobil.ch ist urheberrechtlich geschützt. Daten von dort dürfen nicht
  automatisch abgerufen werden.

## Offene Lizenzfragen

- **Wortlaut „Kanton“:** Die Formel `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` ist
  wörtlich vorgegeben. Ob „Kanton“ ein Platzhalter ist, steht nirgends. Helvetopo übernimmt den
  Wortlaut unverändert. Eine Rückfrage bei info@schweizmobil.ch ist möglich.
- **Kanuland und andere Daten ohne GeoIV-Status:** Die Lizenz stützt sich nur auf Aussagen von
  SchweizMobil (Copyright-Seite, Manual), nicht auf einen Eintrag in opendata.swiss oder geocat.
  Die Quellen nennen „Stiftung SchweizMobil“ bzw. „SchweizMobil“. Helvetopo verwendet
  `Stiftung SchweizMobil`.
- **swissTLM3D auf opendata.swiss:** opendata.swiss führt swissTLM3D als `terms_open`
  (Quellenangabe empfohlen). STAC und geocat verweisen auf die OGD-Bedingungen (Quellenangabe
  Pflicht). Helvetopo wendet die strengere Regel an.
- **Marken:** Ob Routennamen wie „Via Alpina“ oder Bezeichnungen wie „Wanderland“ in einem
  Produkt markenrechtlich heikel sind, ist juristisch nicht geprüft. Als Attribut stehen sie in
  den freien Daten.

## Quellen

- swisstopo OGD-Bedingungen: <https://www.swisstopo.admin.ch/ogd-conditions>
- BGDI-Nutzungsbedingungen: <https://www.geo.admin.ch/de/allgemeine-nutzungsbedingungen-bgdi>
- Übersicht kostenlose Geodaten: <https://www.swisstopo.admin.ch/en/free-geodata-ogd>
- STAC-Katalog: <https://data.geo.admin.ch/api/stac/v0.9/collections>
- swissTLM3D Objektkatalog 2.4: <https://www.swisstopo.admin.ch/dam/de/sd-web/A3kQ2dAgenqG/2026-02%20swissTLM3D%202.4%20OK-DE.pdf>
- swissTLM3D Nachführungsinfo 2026: <https://www.swisstopo.admin.ch/dam/de/sd-web/E9LctZ67DAOl/swissTLM3D%20Release2026-DE.pdf>
- geocat Wanderland: <https://www.geocat.ch/geonetwork/srv/api/records/95638869-ef86-4e95-ae60-20e84e8dca8c>
- geocat swissTLM3D Wanderwege: <https://www.geocat.ch/geonetwork/srv/api/records/4a064664-a346-4c1a-b424-4e8a0f0b56cb>
- opendata.swiss Nutzungsbedingungen: <https://opendata.swiss/de/terms-of-use>
- SchweizMobil Copyright: <https://schweizmobil.ch/de/copyright>
- SchweizMobil Manual „Datenbezug SchweizMobil-Routen“ (Feb. 2026): <https://images.schweizmobil.ch/files/Datenbezug%20SchweizMobil-Routen.pdf>
- SchweizMobil Geodaten: <https://schweizmobil.info/de/geodaten>
