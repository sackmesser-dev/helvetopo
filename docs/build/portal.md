# Portal (Downloadseite)

Stand: 2026-11-05. Code: `src/portal/`.

## Prototyp
Unter `src/portal/prototype/` liegt ein klickbarer Prototyp als statische Seite:
- `index.html` mit dem Markup, `app.css` mit den Styles, `app.js` mit der Logik
- `lang.js` wählt die Sprache früh im `<head>`
- `manifest.json` mit Beispieldaten (Schema siehe unten, Release siehe [release.md](release.md))
- `i18n/de|fr|it|en.json` mit allen Texten
- `regions.json` mit vereinfachten Umrissen der Download-Regionen für die kleine Schweizerkarte. Erzeugt wird sie aus swissBOUNDARIES3D: `.venv/bin/python -I src/portal/build_regions.py`.
- `img/` mit zugeschnittenen BaseCamp-Screenshots der Release-Karten (Stand Release 2026-11): Vektor, Pixel 25-1000 und Luftbild Detail. Die drei Vergleichsbilder `vgl-*.jpg` zeigen St. Gallen im gleichen Ausschnitt und haben die gleiche Grösse.
Lokal ansehen: `python3 -m http.server 8765 --directory src/portal/prototype`, dann http://localhost:8765 öffnen.
Direkt als Datei (Doppelklick auf `index.html`) geht es auch: Weil der Browser unter `file://` keine JSON-Dateien nachladen darf, liest die Seite dann `data.js`. Diese Datei bündelt `manifest.json`, `regions.json` und `i18n/*.json` und wird nach jeder Änderung daran neu erzeugt:
`python3 -I src/portal/build_data.py` (Prüfung mit `--check`). Über einen Webserver liest die Seite weiterhin die JSON-Dateien.

## Ziel
Ein einladendes, benutzerfreundliches Portal als Single-Page-App (SPA) für die öffentlichen Karten-Downloads.
Ganz oben gibt es einen Download-Button für die verschiedenen Karten und gleich daneben einen Link zu den Screenshots.
Weiter unten folgen Features, Screenshots, Installation und Quellen.

## Hosting
- **Portal:** statische Seite über HTTPS.
- **Kartendateien:** eigener Download-Server. Je Release gibt es einen Ordner `<v>/`. Es bleiben das aktuelle Release und ein Vorgänger. `make_release.py` liest die älteren Release-Ordner aus der Ablage und schreibt sie nach `older[]` ins Manifest. Wird ein altes Release gelöscht, verschwindet sein Link mit dem nächsten Manifest.
- Das Portal verweist auf die Dateien über `baseUrl` im Manifest. Ein Wechsel des Anbieters ändert nur diesen Wert.
- **Keine GitHub Releases.** Die Kartendateien gibt es nur über das Portal, weil viele grösser als die Grenze von 2 GiB je Datei sind. Das README im Repo verlinkt das Portal. Der Link „Quellcode (GitHub)“ im Portal nutzt nur `repo.url` aus dem Manifest.
- **Europa für Endnutzer:** Portal, Downloads und die Doku je Release (README, Quellstand, Lizenz) liegen auf Servern in Europa. Ausgenommen sind GitHub und die E-Mail: Die Kontaktadresse liegt bei einem Anbieter in den USA, eine europäische Adresse gibt es nicht. GitHub brauchen nur Entwickler (Quellcode, Pull Requests). Fehlermeldungen gehen per E-Mail.
- Gehostet werden nur eigene Erzeugnisse (IMG, BaseCamp-ZIP, Prüfsummen, Portal). Die swisstopo-Rohdaten holt sich jeder selbst über STAC.
- **Domain:** Das Portal läuft unter `helvetopo.sackmesser.dev`, die Downloads unter `dl.sackmesser.dev/helvetopo/`. Im Manifest ist `baseUrl` dann `https://dl.sackmesser.dev/helvetopo/<v>/`. DNS-Einstellungen und Zugänge stehen nicht im Repo.
- Anbieter, Kosten und Zugang zum eigenen Betrieb stehen nicht im Repo.
- Das Repo wird ohne die bisherige Versionshistorie veröffentlicht (siehe AGENTS.md).

## Seitenaufbau (eine Seite, Anker-Navigation)
1. **Hero**
   - Kurzer Titel, der „Garmin“ betont („Basierend auf der swisstopo-Landeskarte – für dein Garmin“), dazu ein Satz Nutzen mit den Zielgeräten (GPSMAP, Montana, BaseCamp).
   - „Garmin“ steht dabei nur beschreibend („für Garmin“, „Garmin-Karte“). Garmin-Logo und offizieller Anschein sind ausgeschlossen, und im Footer steht ein Markenhinweis.
   - Grosses Kartenbild als Hintergrund: Zermatt, eine Zoomstufe näher als `t18-zermatt` (Dorf, Gewässer, Wald und Höhenlinien gut lesbar). Eigene BaseCamp-Aufnahme `hero-zermatt.jpg` mit dem Kartenstand des Releases.
   - **Primärbutton „Karten herunterladen“** springt zur Download-Übersicht. Ein Split-Button mit Dateiliste war zu verwirrend.
   - **Sekundärbutton „So sieht sie aus“** direkt daneben, er springt zu den Screenshots. „Installation“ war missverständlich (man könnte meinen, die Karte installiere sich selbst). GitHub steht nicht im Hero, nur im Footer als Entwickler-Link „Quellcode (GitHub)“.
   - Darunter stehen Version, Datum und „kostenlos, ohne Konto“.
2. **Download-Übersicht** nach [release.md](release.md): eine Karte pro Kartenart mit Vorschaubild, Beschreibung, **Datenstand** (Hauptquellen gross) und einer Zeile je Produkt.
   - Jede Produktzeile zeigt Name, Zweck, Chips (Massstabsbereich, Gebiet, FID) und einen Knopf je Datei mit Grösse: Gerät (IMG), BaseCamp (ZIP). Dateiname und SHA-256 stehen im Tooltip.
   - Darunter Links auf **README, Lizenz und Quellstand auf dem Download-Server** (`<baseUrl>info/…`). `make_release.py` kopiert diese Dateien je Release nach `files/info/`. Endnutzer brauchen kein GitHub.
   - Bei Produkten je Region wählt man die Region in einer Auswahlliste, die Knöpfe passen sich an.
   - **Vektorkarte** (empfohlen): Komplettpaket 7701 als Gerätedatei und BaseCamp-Paket.
   - **Pixelkarte** (experimentell): Kompakt 1:50'000–1:1 Mio. (7704), Standard 1:25'000–1:1 Mio. je Region (7705), Detail 1:10'000–1:1 Mio. geteilt (7706). Die vier Teile West, Süd, Mitte und Ost bestehen aus ganzen Pixel-Regionen. Ihre IDs sind `pixel10-west`, `pixel10-sued`, `pixel10-mitte` und `pixel10-ost` (`members` im Manifest, Umrisse in `pixel-regionen-2026-11.geojson`). SMR1000 ist in allen drei Varianten die Übersicht auf den gröbsten Zoomstufen. Produkt-IDs `pixel-50-1000`, `pixel-25-1000`, `pixel-10-1000`, Dateinamen `Helvetopo_Pixel_50-1000_…` usw. Die Untertitel beschreiben den Inhalt. **Keine Custom Map (KMZ)** im Portal.
   - Darunter das Kleingedruckte: weitere Quellen (swissALTI3D, SMV25, swissBOUNDARIES3D, SchweizMobil), Hinweis „jede Datei unter 4 GB (FAT32)“, Lizenzzeile, Link auf die Prüfsummen-Datei des Releases.
   - **Luftbild** (experimentell): Orthofotos aus SWISSIMAGE als Raster-IMG. Lizenz wie die übrigen swisstopo-Daten (`©swisstopo`). Details: [luftbild.md](../raster/luftbild.md).
     - Standard (FID 7708): eine Datei für die ganze Schweiz.
     - Detail (FID 7707): 18 Teile ohne Überlappung, je unter 4 GB. Die Teile sind die Pixel-Regionen, grosse Regionen sind geteilt (West/Ost, Nord/Mitte/Süd). Ostschweiz und Nordwestschweiz haben eigene IDs (`luftbild-ostschweiz`, `luftbild-nordwestschweiz`), weil ihre Umrisse von den Pixel-Regionen abweichen.
     - Die Umrisse für die kleine Karte kommen aus `src/portal/data/luftbild-detail-2026-11.geojson`. `build_regions.py` liest diese Datei zusammen mit den Pixel-Regionen.
   - Alles kommt aus `manifest.json`. Eine neue Kartenart oder Region braucht nur Einträge im Manifest und Texte in `i18n/`.
3. **Features** als Kacheln mit Icon und einem Satz:
   - im Stil der Landeskarte 1:25'000
   - Routing für Fuss und Velo aus swissTLM3D. Auto wird nicht beworben, weil Abbiegeverbote fehlen. In der FAQ steht es als „eingeschränkt“.
   - Wanderwege und SchweizMobil-Routen als eigenes Overlay
   - Adresssuche und Strassennamen
   - Gipfel- und Ortsnamen aus swissNAMES3D
   - Höhenlinien aus swissALTI3D
   - frei und regelmässig aktualisiert
4. **Screenshots**
   - Galerie mit Lightbox: BaseCamp-Screenshots mit dem Kartenstand des Releases. Später kommen Fotos bzw. Screenshots vom Gerät (GPSMAP/Montana) dazu.
   - Neue Screenshots bei jedem Release, an dem sich der Look ändert: JPEG mit Qualität 80, ca. 1300 Pixel breit, ohne Suchmarken und ohne eigene Benutzerdaten.
   - **Vorher/Nachher-Schieberegler**: eigene Karte gegen SMR25-Ausschnitt an derselben Stelle. Das zeigt den Look und dient zugleich der Fortschrittsmessung (siehe [messung.md](../stil/messung.md)).
5. **Vorschaukarte (später):** MapLibre mit PMTiles aus den eigenen Vektordaten, statisch über HTTP-Range-Requests, ohne Tile-Server und ohne swisstopo-WMTS-Kacheln.
6. **Installation** in drei Schritten, mit Tabs:
   - Gerät per USB: die Gerätedatei (IMG) nach `Garmin/` kopieren, ohne Umbenennen.
   - BaseCamp: ZIP entpacken, den `.gmap`-Ordner nach `C:\ProgramData\Garmin\Maps\` bzw. `~/Library/Application Support/Garmin/Maps/` kopieren. Kein unsignierter Installer.
   - Pixelkarte (IMG): Variante wählen, Datei(en) nach `Garmin/` kopieren, einblenden
7. **FAQ:**
   - offiziell? (nein, inoffizielle Umwandlung)
   - **Abgrenzung zu Garmin TOPO Schweiz:** Kein Zusammenhang mit den kostenpflichtigen Garmin-Karten wie [TOPO Schweiz v2 PRO](https://www.garmin.com/de-CH/p/730051/). Betont werden „kostenlos“ und der ausgewiesene Datenstand.
   - Warum Helvetopo? (Motivation: gratis statt kostenpflichtig)
   - Liechtenstein enthalten? (ja, Adresssuche nur Schweiz)
   - Geräte, Vektor oder Pixel, Auto-Navigation (eingeschränkt), Datenstand, Fehler melden
8. **Footer**
   - Quellenangaben: `©swisstopo` und `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`.
   - Hinweis „Inoffizielle Umwandlung, nicht von swisstopo herausgegeben“. Er steht auch unter der Download-Übersicht und in der FAQ.
   - Impressum, Datenschutz, Lizenz.

## Gebiet
- Die Karten decken die **Schweiz und Liechtenstein** ab: swissTLM3D, swissNAMES3D, SMR und swissBOUNDARIES3D enthalten Liechtenstein. Der Gesamtbuild heisst „Schweiz und Liechtenstein“.
- Die Adresssuche gibt es nur für die Schweiz, weil das amtliche Gebäudeadressverzeichnis nur Schweizer Adressen enthält.
- Auf der Seite steht überall „Schweiz und Liechtenstein“, ausser im Titel. Dateinamen behalten `Schweiz` (Release-Plan).

## manifest.json (Schema 2)
Die Pipeline schreibt die Datei beim Release. Die SPA liest nur sie, ein neues Release braucht keine Änderung am Portal. Das Manifest enthält keine Texte. Die stehen in `i18n/` unter den IDs.

| Feld | Inhalt |
|---|---|
| `schema` | `2` |
| `release`, `date` | Release-Version `JJJJ-MM` (bzw. `JJJJ-MM-TT`) und Datum |
| `prefix` | Dateinamen-Präfix `Helvetopo` |
| `baseUrl` | URL oder Pfad der Dateien dieses Releases, z. B. `files/2026-11/` (siehe [Hosting](#hosting)) |
| `checksums` | Name der `SHA256SUMS`-Datei |
| `older[]` | Ältere Releases, die beim Bau des Manifests noch auf dem Download-Server liegen: `release`, `baseUrl`, `checksums`, `files[]` (`name`, `size`). Das Portal verlinkt nur diese. Leer, wenn es keine gibt |
| `repo` | `url` des GitHub-Repos und `ref` (Release-Tag, z. B. `v2026-11`). Nur für den Entwickler-Link „Quellcode (GitHub)“ |
| `attribution` | Pflicht-Quellenangaben wörtlich: `swisstopo`, `astra`, `schweizmobil` |
| `sources[]` | `id`, `title`, `edition` (Ausgabe oder Spanne), `date` (Bezugsdatum), `stac` (Collection-ID), `prominent` (true = gross auf der Seite) |
| `regions[]` | `id` (Texte unter `region.<id>`), später optional `bbox` |
| `groups[]` | `id`, `recommended`, `experimental`, `planned` |
| `products[]` | `id`, `group`, `kind` (`vektor`, `pixel`), `fid`, `scale` (`min`, `max` als Massstabszahl), `area` (`schweiz`, `regionen` oder `testgebiet`), `experimental`, `sources` (IDs), `docs` (`readme`, `license`, `sources`: Pfade relativ zu `baseUrl`, z. B. `info/vektor/README.md`) |
| `products[].files[]` | `target` (`device`, `basecamp`), `format`, `name`, `size` (Byte), `sha256`, `primary`, optional `region`, `part`/`parts`, `os` |

Sprechende Dateinamen nach Release-Plan (`Helvetopo_<Art>_<Massstab>_<Gebiet>_<JJJJ-MM>.<ext>`) stehen im Feld `name`. Das Portal baut die URL aus `baseUrl` + `name`.

## Technik
- Vanilla HTML, CSS und JavaScript ohne Framework und ohne Build. Die Quelle sind die statischen Dateien in `src/portal/prototype/`.
- `make_release.py --site` baut eine lokale Vorschau in `work/portal/site/`. Dort zeigt `files/<v>/` per Symlink auf die Release-Dateien.
- Für den Webserver baut `src/portal/build_site.py --manifest work/release/<v>-ch/manifest.json` die Website nach `work/portal/deploy/`:
  - Es kopiert den Prototyp und legt das Release-Manifest daneben.
  - Es entfernt den Hinweis „Prototyp mit Beispieldaten“ und erzeugt `data.js` neu.
  - Es hängt an jeden Bildverweis `img/<datei>` und an `lang.js`, `app.css` und `app.js` in `index.html` die Version `?v=<SHA-256>` an. Ändert sich eine Datei, ändert sich ihre URL, und alle Browser laden sie sofort neu.
  - Es bricht ab, wenn das Manifest Beispieldaten enthält oder `baseUrl` keine absolute https-URL ist.
  - Dieser Ordner geht unverändert per Deploy auf den Webserver. Die Kartendateien gehören nicht dazu.
- Veröffentlichen der Kartendateien: Der Upload geht zuerst in einen versteckten Ordner `.staging-<v>/` in der Ablage. nginx liefert keine Punkt-Ordner aus. Die IMGs sind dort relative Links in die Build-Ablage (`../.build/…`), es gibt also keine zweite Kopie. Erst das Umbenennen in `<v>/` macht die Dateien öffentlich. Danach folgt der Deploy des Portals.
- Schriften und Icons lokal eingebunden (keine Google Fonts, kein CDN), keine Tracker und keine Cookies. Dadurch bleibt der Datenschutz einfach.
- Der Webserver sendet eine strenge Content-Security-Policy ohne `'unsafe-inline'`. Deshalb gilt:
  - Kein Inline-Skript, kein `<style>`-Block, keine `style`-Attribute und keine Event-Attribute wie `onclick`.
  - Styles gehören in `app.css`. Dynamische Werte setzt `app.js` per CSSOM (`el.style.…`), zum Beispiel die Vorschaubilder über `data-bg`.
  - Lokal prüfen: `python3 -I src/portal/serve_csp.py` (Port 8768). Der Server sendet dieselbe Policy, Verstösse erscheinen in der Browser-Konsole.
- Responsiv (Smartphone zuerst), Hell- und Dunkelmodus, barrierearm (Kontraste, Tastatur, Alt-Texte).
- **Sprachen DE, FR, IT, EN.**
  - Die Sprache wird in dieser Reihenfolge bestimmt: `?lang=` in der URL, dann die gespeicherte Wahl (`localStorage`), dann die erste passende Browsersprache, sonst Englisch.
  - Die Sprachwahl (DE/FR/IT/EN) steht oben rechts. Eine Wahl dort wird gespeichert und setzt `?lang=`, damit Links in einer Sprache teilbar sind.
  - Texte stehen in `i18n/<sprache>.json`. `de.json` ist die Quelle. Das Deutsch im HTML ist nur der Fallback ohne JavaScript und wird aus `de.json` nachgeführt.
  - Zahlen, Daten und Massstäbe werden nach Gebietsschema formatiert (`de-CH`, `fr-CH`, `it-CH`, `en-GB`).
  - Die Pflicht-Quellenangabe `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` bleibt in allen Sprachen wörtlich. Eine Übersetzung in Klammern darunter ist erlaubt, ersetzt sie aber nicht.
  - FR, IT und EN sollte vor der Veröffentlichung jemand mit Muttersprache gegenlesen.
  - Für Suchmaschinen später je Sprache eine vorgerenderte Seite (`/fr/`, `/it/`, `/en/`) mit `hreflang`.

## Rechtliches
- Impressum und Datenschutzerklärung (Server in Deutschland: DSGVO, zusätzlich revDSG). nginx-Logs kurz halten oder die IP-Adressen anonymisieren. Die Datenschutzerklärung nennt die nginx-Logs und die Zugriffsprotokolle des Download-Speichers, mit Inhalt und Aufbewahrungsdauer. Die FAQ „Wo ist der Haken?“ verweist darauf.
- Keine Logos oder Marken von swisstopo und SchweizMobil, kein Anschein einer offiziellen Karte.
- Sichtbar auf der Seite: `©swisstopo` und, wegen der Routen, `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil` (Footer und unter der Download-Übersicht).
- Wortwahl: Nie „offizielle Landeskarte“ schreiben. Die Vektorkarte ist „im Stil der Landeskarte“, nicht „die Landeskarte“.
- **Name: Helvetopo**.
  - Markenrecherche 2026-11-04: kein Eintrag in TMview (EUIPO, IGE und weitere Ämter), auch nicht für „helvetop…“, keine Treffer im Web.
  - Die Domains `helvetopo.ch`, `.li`, `.com`, `.org` und `.eu` waren frei. `.app` war nicht prüfbar. Der Betreiber hat keine davon registriert. Das Portal läuft unter einer Subdomain (siehe „Hosting“).
  - Der Name enthält keine fremde Marke. Er teilt nur den Anfang „Helvet…“ mit der Marke „Helvetia“ der Versicherung, das ist eine andere Branche.
  - „Garmin“ und „swisstopo“ stehen weiterhin nur beschreibend daneben („für Garmin“, „auf Basis von swisstopo-Daten“).

## Texte zum Routing

- FAQ „Wie bevorzugt das Routing Velorouten und Wanderwege?“: Im Velo- und MTB-Profil „Mautstrassen
  vermeiden“ einschalten, im Auto- und Wanderprofil ausschalten (siehe
  [routing.md](../vektor/routing.md#bedienung)).
- Nicht schreiben: „In der Schweiz gibt es keine Mautstrassen.“ Der Grosse-St.-Bernhard-Tunnel und der
  Tunnel Munt la Schera sind kostenpflichtig, die Autobahnvignette ist eine Gebühr. Richtig: „Die Karte
  kennt keine Mautgebühren und nutzt das Maut-Flag als Velo-Hinweis.“
- „Bevorzugt“ erst schreiben, wenn der Gerätetest die Wirkung bestätigt. BaseCamp bestätigt sie.

## Offene Entscheide
- Regionen und Grössen der Pixel-Pakete
- Muttersprachliches Gegenlesen von FR, IT und EN
