# Überblick

Stand: 2026-11-05.

Helvetopo baut aus freien swisstopo-Daten (OGD) und den SchweizMobil-Routen (Open Data BY) Karten für
Garmin-Geräte und BaseCamp. Zielgeräte sind GPSMAP und Montana.

## Produkte

| FID | Produkt | Format | Code | Doku |
|---|---|---|---|---|
| 7701 | Vektorkarte: Basis, Routen, Höhen in einer Familie, routingfähig | IMG, gmapi | `src/vector/`, `src/style/`, `src/dem/`, `src/routes/`, `src/build/` | [basiskarte.md](vektor/basiskarte.md) |
| 7702 | Routen als eigene Familie (nur `DEVICE_FAMILIES=split`) | IMG | `src/routes/` | [routen.md](vektor/routen.md) |
| 7703 | Höhenlinien als eigene Familie (nur `split`) | IMG | `src/dem/` | [hoehen.md](vektor/hoehen.md) |
| 7704 | Pixelkarte 1:50'000–1:1 Mio. | Raster-IMG | `src/raster_img/` | [raster-img.md](raster/raster-img.md) |
| 7705 | Pixelkarte 1:25'000–1:1 Mio. | Raster-IMG | `src/raster_img/` | dito |
| 7706 | Pixelkarte 1:10'000–1:1 Mio., Regionen | Raster-IMG | `src/raster_img/` | dito |
| – | Pixelkarte als Custom Map (Eigenbedarf) | KMZ | `src/raster_kmz/` | [kmz.md](raster/kmz.md) |

- Product-ID 1, Codepage 1252, `--lower-case`. Map-IDs je FID im Bereich `<FID>0000`–`<FID>9999`.
- Gebiet: Schweiz und Liechtenstein. Die Adresssuche gibt es nur für die Schweiz.
- Testgebiet: Wil–St. Gallen–Säntis, WGS84 9,00–9,50° O / 47,20–47,50° N.

## Pipeline

```
STAC data.geo.admin.ch (GPKG, COG, GeoTIFF) → downloads/
 ├─ swissTLM3D, swissNAMES3D, swissBOUNDARIES3D, Adressen, SMV25-Annotationen, Routenzuordnung
 │    └─ src/vector/ (LV95 → WGS84, Tag-Schema) → Basis-PBF
 ├─ Swiss Map Vector 25 → src/dem/smv25_heights.py → Höhenkurven- und Koten-PBF
 ├─ swissALTI3D → src/dem/ → HGT (DEM) und Gletscherkurven
 ├─ swissTLM3D Wanderwege, SchweizMobil → src/routes/ → Routen-PBF und Kantenzuordnung
 │    └─ src/build/build_all.sh: osmium merge → splitter → mkgmap (Stil, TYP, Routing, Index, DEM)
 │         → gmapsupp.img, gmapi
 └─ Swiss Map Raster 10–1000 → src/raster_img/ (eigener Encoder) → Raster-IMG, gmapi
                             → src/raster_kmz/ → KMZ
src/release/make_release.py → Downloads, Prüfsummen, manifest.json → src/portal/
```

OSM-PBF dient nur als Dateiformat. Die Karten enthalten keine OSM-Daten.

## Grundsatzentscheide

### Vektor über OSM-PBF und mkgmap

- mkgmap und splitter sind die einzige freie, gepflegte und skriptbare Kette, die Routing,
  Adress- und POI-Index, DEM-Schummerung, Höhenlinien und TYP zusammen liefert. Sie läuft unter
  macOS und Linux (Java).
- Das zweistufige Mapping (swissTLM3D → OSM-ähnliche Tags → mkgmap-Stil → Garmin-Typen) ist testbar
  (die PBF lässt sich in QGIS ansehen) und nutzt die Routing- und Multipolygonlogik von mkgmap.
- Der direkte Weg über das Polish-Format (cGPSmapper, GPSMapEdit) ist verworfen: Die Werkzeuge sind
  eingefroren, laufen nur unter Windows und lassen sich kaum automatisieren.
- mkgmap erzeugt das klassische IMG-Format (nicht NT). Aktuelle Geräte lesen es.

### Raster als IMG mit eigenem Encoder

- Garmin-IMG kann eingebettete JPEG-Bilder enthalten. Weder mkgmap noch andere freie Werkzeuge
  schreiben solche Dateien so, dass ein Gerät sie zeigt. Helvetopo hat dafür einen eigenen Encoder.
- KMZ Custom Maps sind auf 500 Kacheln je Gerät begrenzt und eignen sich nur für Regionen.
- JNX (BirdsEye) ist verworfen: Unsignierte Dateien sind auf ca. 1 km² begrenzt
  ([jnx.md](raster/jnx.md)).

### Lizenzregeln in der Technik

Die ODbL gilt für die OSM-Datenbank, nicht für das Dateiformat. Diese mkgmap-Funktionen würden
OSM-Daten einschleusen und sind deshalb nicht im Einsatz:
- vorgefertigte `bounds` von mkgmap.org.uk (Ersatz: `is_in:*` aus swissBOUNDARIES3D)
- `--precomp-sea`
- fremde Höhendaten (SRTM, viewfinderpanoramas)
- mkgmap-Standardtexte („OSM map“, ODbL-Lizenz): `--family-name`, `--series-name`, `--copyright-file`,
  `--license-file` und `--overview-mapname` sind immer gesetzt.

Garmin zeigt am Gerät nur die zweite Copyright-Zeile. Die Quellenangabe steht deshalb in beiden Zeilen.
Details: [lizenzen.md](daten/lizenzen.md).

## Gerätefunktionen

| Funktion | Stand |
|---|---|
| Darstellung, TYP | ja |
| Routing Fuss und Velo | ja |
| Routing Auto | nur topografisch (keine Einbahnen, Abbiegeverbote, Tempolimits) |
| Adress-, Orts- und POI-Suche | ja |
| Schummerung (DEM) | ja |
| Höhenprofil | ja |
| Trendline (Popularity Routing), Rundkurse | nur mit Garmin-Karten |
| Codepage | 1252. `--unicode` lädt nicht auf allen Geräten. |

## Werkzeuge

| Werkzeug | Version | Ablage |
|---|---|---|
| mkgmap | r4924 | `tools/mkgmap-r4924/` |
| splitter | r654 | `tools/splitter-r654/` |
| GDAL | 3.13 | Homebrew |
| osmium | 1.19 | Homebrew |
| Java | 26 | Homebrew |
| Python | 3.13 im venv `.venv/` | numpy, scipy, shapely, pyogrio, pyproj, Pillow, GDAL-Bindings (`--system-site-packages`) |

Rohdaten liegen unter `downloads/`, Zwischenstände und Ausgaben unter `work/`. Beide Ordner sind nicht
versioniert und liegen im Haupt-Checkout (`src/paths.py`, `src/paths.sh`).

## Risiken

| Risiko | Gegenmassnahme |
|---|---|
| mkgmap und splitter haben wenige Entwickler | Versionen gepinnt, JARs lokal in `tools/` |
| BaseCamp für macOS läuft nur über Rosetta | BaseCamp für Windows, `gmapsupp.img` als Hauptauslieferung |
| Firmware ändert die Behandlung von Fremdkarten (z. B. fēnix 8) | je Gerät und Firmware testen |
| Datenvolumen (swissALTI3D 49 GB, SMR10 ca. 400–470 GB) | blockweise Verarbeitung, Downloads nur bei Bedarf |
