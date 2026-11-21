# Stilmessung gegen SMV25 und SMR

Stand: 2026-11-04. Code: `src/style_qa/`.

`src/style_qa/` misst den Stil gegen zwei Referenzen und schreibt eine priorisierte
Abweichungsliste.

```bash
bash src/style_qa/run.sh            # Stil-Build work/style/testgebiet/
bash src/style_qa/run.sh --gesamt   # Gesamtbuild work/build/, Ausgabe work/style_qa/gesamt/
bash src/style_qa/run.sh --refs     # Referenzbilder neu rendern
```

| Ziel | IMG | TYP | Overlays |
|---|---|---|---|
| `style` (Vorgabe) | `work/style/testgebiet/` | `src/style/typ/swisstopo.txt` | Höhenlinien 7703 |
| `gesamt` | `work/build/7701/` (mit DEM und Koten) | `work/build/meta/ch_7701.txt` | `work/build/7701-contours/`. Routen nur mit `QA_ROUTES=yes` (die LK zeigt keine Routen). |

Ausgabe:
- `work/style_qa/report.md` mit Nebeneinander-Bildern in `work/style_qa/vergleich/`
- `results.json` (Rohwerte), `findings.json` (Befunde), `history.json` (Verlauf über Stilversionen)
- Referenzbilder in `work/style_qa/<ausschnitt>/<zoom>/ref_*.png`

## Referenzen

| Referenz | Quelle | Erzeugung |
|---|---|---|
| SMV25 | STAC `ch.swisstopo.swiss-map-vector25`, Blätter 216, 217, 226, 227 (GPKG, 2,5 GB) | offizielles QGIS-Projekt `SMV25_CHLV95LN02.qgs`, headless mit PyQGIS (QGIS 4.2.3) |
| SMR25, SMR50, SMR100 | `downloads/smr/pk25`, `pk50`, `pk100` | `gdal.Warp`, Mittelwert beim Verkleinern |
| Relief | KOMB-Raster der SMV25 | Messung der Schummerung |

`src/style_qa/merge_smv25.sh` führt die Blätter in `downloads/smv25/merged/` zusammen (GPKG und
VRT). Die Projektkopie `SMV25_qa.qgs` weicht vom Original ab:
- Raster als VRT über die vier Blätter.
- Die 1-Bit-Raster FELS, GEROELL und GLET haben in der STAC-Lieferung 0 = Objekt. Das Projekt
  erwartet 1 = Objekt. Die Kopie kehrt die Paletteneinträge um.
- „Liberation Sans Narrow“ fehlt unter macOS. `render_ref_qgis.py` ersetzt sie zur Laufzeit durch
  die metrisch gleiche „Arial Narrow“ (`QgsFontManager.addFontFamilyReplacement`).
- Das Koordinatennetz (T28) ist ausgeblendet. Für Farb- und Breitenmessung gibt es eine Variante
  ohne `*_ANNO`-Layer.

## Raster und Ausschnitte

Alle Bilder eines Ausschnitts und einer Stufe liegen auf demselben LV95-Raster (800 × 600 px,
nordorientiert). Die Pixelgrösse folgt dem GPSMAP 66/67: 1 px = 0,16 mm (px = mm × 6,25).

| Stufe | m/px | Garmin-Auflösung | Referenzen |
|---|---|---|---|
| 1:12 500 | 2 | 24 | SMV25, SMR25 |
| 1:25 000 | 4 | 23 | SMV25, SMR25 |
| 1:50 000 | 8 | 22 | SMR50, SMV25 |
| 1:100 000 | 16 | 21 | SMR100 |

Soll-Breite = LK-Geländebreite der Stufe: 12,5 px/mm bei 1:12 500, 6,25 px/mm bei 1:25 000 und
1:50 000. Die SMV25 wird mit dpi = 25,4 × k gerendert. Die Annotationen haben den
Referenzmassstab 1:25 000.

Ausschnitte (Mittelpunkt LV95, änderbar in `config.py`):

| Ausschnitt | Mittelpunkt |
|---|---|
| St. Gallen Zentrum | 2 746 220 / 1 254 440 |
| Herisau | 2 738 950 / 1 249 960 |
| Wil SG | 2 721 420 / 1 257 970 |
| Säntis, Alpstein | 2 744 180 / 1 234 910 |
| Oberbüren–Niederuzwil | 2 730 670 / 1 252 460 |

## Eigene Karte

`render_ours.py` ruft `src/style/tools/render_img.py` auf: alle Kacheln, je Kachel die Ebene der
Auflösung, mit der TYP. Darüber liegen die Höhenlinien ohne Beschriftung. Das Bild wird
georeferenziert und auf das LV95-Raster gebracht (nächster Nachbar). `ours_objects.json` enthält die
Objekte in Pixelkoordinaten für die Masken.

BaseCamp-Bilder aus der VM haben keine Georeferenz. `measure.py` kann sie messen, sobald Ausschnitt
und Bildgrösse bekannt sind.

## Messgrössen

Die Zuordnung SMV25-Objektart (Layer und Feld `Symbol`) ↔ Garmin-Typ steht in `classes.py`.

| Grösse | Methode |
|---|---|
| Farbe | TYP-Nennwert gegen SMV25-Nennwert (`downloads/style-swisstopo/symbology.tsv`), ΔE2000. Kontrolle im Bild: dominante Farbe auf der Mittellinie bzw. im Flächeninnern. Flächen zusätzlich gegen SMR25. |
| Linienbreite | Soll = SMV25-Breite in mm × k. Ist = TYP-Pixel. Kontrolle im Bild: Querprofile alle 2 px, Median. |
| Strichmuster | Soll = `dash` der SMV25-Symbolik. Ist = TYP-Muster. Kontrolle: Abtastung alle 0,5 px, Lauflängen. |
| Zeichenreihenfolge | Paare aus `classes.ORDER_PAIRS`: Anteil „A oben“ an den Überlagerungspixeln, eigene Karte gegen SMV25 |
| Beschriftung | SMV25-Annotationen (`TEXTSTRING`, `FONTSIZE`, `ITALIC`, Farbe) gegen die Labels der IMG: Anteil vorhanden, Grösse, Farbe, kursiv. Garmin-Schrift geschätzt: Small 10, Normal 12, Large 15 px. |
| Symbole | Anzahl je Punktklasse im Ausschnitt |
| Gesamt | SSIM (Graustufen, σ 1,5), ΔE2000 nach Weichzeichnung (σ 3 px), Schnitt der Lab-Histogramme. Zum Vergleich dieselben Masse SMV25 ↔ SMR25. |
| Relief | Korrelation der Helligkeit (σ 4 px) mit dem SMV25-Relief auf offenen Flächen |

## Priorisierung

Jeder Befund bekommt eine Wirkung in „ΔE·%“: Anteil der betroffenen Bildpixel × Farbunterschied.
- Farbe: Fläche der Klasse × ΔE
- Breite: Linienlänge × |Δ px| × Kontrast zur Umgebung
- fehlende Klasse: LK-Fläche × Kontrast
- Reihenfolge: Kreuzungspixel × ΔE zwischen den Farben
- fehlende Namen: geschätzte Textfläche × 60

Der Wert ist der Mittelwert über die Ausschnitte bei 1:12 500 und 1:25 000. Er dient der Rangfolge,
nicht als absolute Wahrnehmungsgrösse. Befunde an einer Garmin-Grenze tragen eine Kennung, z. B.
`[kursiv]`, `[breite_zoom]`, `[linienfolge]`, `[relief]`, `[subpixel]`.

## Ergebnis

Gesamtbuild mit DEM, Koten und eingebauten Höhenlinien, Stand 2026-11-04: Summe der Wirkung **3,95**
(45 Befunde). Der erste messbare Stand lag bei 19,7.

| Grösse | Stand |
|---|---|
| Farben | alle TYP-Farben = SMV25-Nennwerte (ΔE 0) |
| Gebäude bei 1:12 500 und 1:25 000 | 96–101 % der LK-Fläche |
| Höhenkoten | 166 von 170 |
| Ortsnamen | 103 von 111 |
| Objektnamen | 69 % |
| Höhenkurven bei 1:50 000 | 49 % (Richtwert, die LK50 ist generalisiert) |

Offene Befunde:
- Zahl der Strassennamen (Namen in Auflösung 24, die LK beschriftet fast nur Nummern)
- Schriftgrössen von Koten, Objekt- und Bergnamen (Garmin kennt nur Small, Normal, Large)
- Zählkurve 2 px statt 1,1 px
- Strichmuster des 1-m-Wegs
- Schummerung (nur in BaseCamp oder am Gerät messbar)
- Kursivschrift (Garmin-Grenze)

## Grenzen der Messung

- `render_img.py` zeichnet die DEM-Subdatei nicht. Die Relief-Korrelation der eigenen Bilder ist
  deshalb ca. 0.
- `render_img.py` zeichnet erweiterte Typen (0x1xxxx) vor den Standardtypen. BaseCamp zeichnet
  eingebettete Höhenlinien unter Strassen und Gebäuden. Paare mit einem erweiterten Typ gelten als
  „im Renderer nicht messbar“ (Wirkung 0).
- Routingtyp (Auflösung 24) und Übersichtstyp (darunter) zählen zur selben LK-Klasse. Gemessen wird
  der Typ, der in der Stufe überwiegt.
- `render_img.py` setzt alle Namen ohne Kollisionsprüfung. Schrift und Linienfolge brauchen eine
  Bestätigung in BaseCamp oder am Gerät.
- Die eigene Geometrie ist swissTLM3D, die LK-Geometrie DKM25 (generalisiert). SSIM und ΔE-Karte
  enthalten deshalb auch Lageunterschiede.
- Linien unter 1 px wirken in der Referenz heller und breiter (Antialiasing). Massgebend sind die
  Nennwerte.
- SMV25 ist Stand 2021, SMR25 Stand 2022, swissTLM3D aktuell.

## Lizenz

Alle Referenzdaten sind swisstopo-OGD. Die Vergleichsbilder enthalten Ausschnitte von SMR und SMV
und tragen den Vermerk „Daten ©swisstopo“. Sie sind Arbeitsmaterial, nicht Teil der Karte. SMV25 und
SMR kommen als Dateien aus dem STAC-Katalog, nicht über WMTS.
