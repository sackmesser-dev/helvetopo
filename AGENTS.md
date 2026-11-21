# AGENTS.md

Projekt: **Helvetopo** (der Repo-Ordner heisst GarminSwissTopo). Freie swisstopo-Geodaten (OGD) sollen zu Karten für
Garmin-Geräte werden (Vektor → IMG über OSM-PBF + splitter/mkgmap, Raster → KMZ Custom Maps,
kein JNX). Hintergrund: [docs/ueberblick.md](docs/ueberblick.md).

## Sprache
- Kommunikation und Doku auf Deutsch mit korrekten Umlauten. Code-Bezeichner auf Englisch.
- Doku unter `docs/` ist Sachdoku zum aktuellen Stand, gegliedert nach Thema (Index: [docs/README.md](docs/README.md)). Neue Befunde ändern die passende Stelle, statt einen Abschnitt anzuhängen.
- **Schreibregeln ASD-STE100 (verbindlich):** für alle `.md`-Dateien, von Skripten erzeugte Markdown-Texte, PR- und Issue-Beschreibungen und Commit-Nachrichten. Vor dem Schreiben den Skill [.agents/skills/asd-ste100/](.agents/skills/asd-ste100/SKILL.md) laden und [docs/schreibregeln.md](docs/schreibregeln.md) (Übertragung auf Deutsch) anwenden. Vor der Abgabe `python3 src/doc_lint/check_md.py` ausführen. Fehler (E) beheben, Warnungen (W) prüfen.

## Lokales bleibt lokal (verbindlich)
Das Repo ist öffentlich. Es enthält nur, was Dritten beim Verstehen, Nachbauen oder Mitentwickeln hilft.
- **Lokale Anweisungen und Angaben** zum eigenen Arbeitsplatz gehören nie in versionierte Dateien. Dazu zählen Sessions, Orchestrator, VM, Heimnetz, Server, Hosting-Anbieter, Konten, Zugangsdaten, Benutzerpfade und Gerätenamen.
- Solche Angaben gehören nur an gitignorierte Orte:
  - `AGENTS.local.md`, eingebunden über `CLAUDE.local.md`
  - private Skills unter `.claude/skills/`
  - `work/`, `tmp/` oder `scratch/`
- Einen neuen lokalen Ort zuerst in `.gitignore` eintragen und mit `git check-ignore <pfad>` prüfen. Erst dann die Datei schreiben.
- **Keine Agenten-Kommentare** in Code, Doku, Commit-Nachrichten und PR-Texten. Beispiele: „Session 33: …“, „Wunsch Orchestrator“, „Auftrag aus Session style-typ“, „Test 22 im Chat“.
- Stattdessen die Sache selbst begründen: Was der Code tut und warum. Gibt es einen Beleg, auf die Doku oder die Quelle verweisen, nicht auf eine Session.
- Vorgaben im Code sind allgemein gültig. Feste Pfade auf Worktrees, Mounts oder installierte App-Versionen kommen nur über Umgebungsvariablen.
- Vor jeder Abgabe die geänderten Dateien auf solche Angaben durchsehen. `check_md.py` meldet „Session“ in `docs/` als Warnung W4. Code und Kommentare prüft es nicht.

## Lizenz (verbindlich)
- Erlaubte Quellen:
  - swisstopo-Daten unter OGD, siehe [docs/daten/lizenzen.md](docs/daten/lizenzen.md).
  - SchweizMobil-Routen (Wanderland, Veloland, Mountainbikeland, Skatingland aus `ch.astra.*`, Kanuland, hindernisfreie Wege, Winterrouten von der Stiftung SchweizMobil), alle unter Open Data BY. Siehe [docs/daten/lizenzen.md](docs/daten/lizenzen.md).
- Pflicht-Quellenangaben, je nachdem welche Daten in einer Karte stecken. Sie gehören ins Copyright-Feld (beide Zeilen), in den Kartennamen bzw. die Beschreibung, auf die Downloadseite und in die README/LICENSE:
  - swisstopo-Daten: `©swisstopo`
  - ASTRA-Layer: `Bundesamt für Strassen, Kanton, Stiftung SchweizMobil`
  - Daten direkt von SchweizMobil: `Stiftung SchweizMobil`
- SchweizMobil-Logos und -Marken, die Webkarten-API und GPX-Dateien auf Antrag sind nicht frei und werden nicht verwendet. Den Routennamen und die Routennummer darf man als Attribut übernehmen.
- Nicht verwenden: kostenpflichtige Varianten (SMR-Einzelebenen, CMYK, Sonderperimeter, ältere Versionen).
- Ziel ist eine öffentlich herunterladbare IMG. Weitergabe ist erlaubt. Keine Logos von swisstopo oder SchweizMobil und kein Anschein einer offiziellen Karte.
- Keine weiteren Fremdquellen (OSM/ODbL, kantonale Daten, mkgmap-Hilfsdaten auf OSM-Basis) beimischen, ohne die Lizenzfolgen in der Doku festzuhalten.
- Bezug über den STAC-Katalog `data.geo.admin.ch`, ohne massives Scraping von WMTS-Kacheln.

## Entscheide (2026-11-03)
- **Testgebiet:** Wil bis St. Gallen plus Säntis/Alpstein, WGS84 ca. 9.00–9.50° O / 47.20–47.50° N. Die ganze Schweiz kommt erst, wenn die Kette steht.
- **Zielgeräte:** GPSMAP/Montana (Handhelds). Kachellimit für KMZ beachten.
- **Pixelkarte:** Massstab 1:25'000 (Swiss Map Raster 25). SMR 50 bis 1000 für Übersichtsstufen. Ergänzung 2026-11-04: Raster-IMG gibt es in mehreren Varianten. Für die ganze Schweiz 1:50'000–1:1'000'000 und 1:25'000–1:1'000'000, in Regionen 1:10'000–1:1'000'000. Details: [docs/build/release.md](docs/build/release.md). Beides parallel: KMZ Custom Maps als gesicherter Weg und Raster-IMG nach Vorbild „Topo Schweiz v3 Raster“ (GarminImg-Encoder) als Forschungsast.
- **Look & Feel (hohe Priorität):** nicht nur ähnlich, sondern **möglichst eng am swisstopo-Layout** (Swiss Map Vector 25 / Landeskarte 1:25'000). Gleiche Farben (exakte RGB-Werte aus den offiziellen SMV-Styles), Linienbreiten und -muster, Flächenfüllungen, Symbole, Schriftarten und -grössen soweit Garmin es zulässt, Beschriftungsregeln und Zeichenreihenfolge. Abweichungen nur, wo Garmin/TYP technisch begrenzt ist, und dann je Objektart dokumentiert. Fortschritt wird gemessen (Vergleich gegen SMR25-Ausschnitte), nicht nur geschätzt.
- **Routing:** Metadaten aus swissTLM3D nutzen (Auto/Motorrad, Velo, Fuss, Wanderweg-Kategorien).
- **Metadaten:** Strassennamen, Adressen (amtliches Gebäudeadress- und Strassenverzeichnis, OGD), Gipfel und Namen (swissNAMES3D), Höhen (swissALTI3D: DEM und Höhenlinien).
- **Downloads:** in `downloads/<datensatz>/` im Haupt-Checkout (gitignored). Code ermittelt den Pfad über `src/paths.py` bzw. `src/paths.sh` (Umgebungsvariable `HELVETOPO_ROOT`, sonst der Haupt-Checkout über `git rev-parse --git-common-dir`). Keine absoluten Benutzerpfade in versionierte Dateien schreiben.
- **Werkzeuge:** mkgmap r4924 und splitter r654 in `tools/` des Haupt-Checkouts. GDAL und osmium per Homebrew. Python-Pakete in einem venv (`.venv/`, gitignored).

## Kartennummern (Family-ID / Product-ID 1, Codepage 1252)
| FID | Karte |
|---|---|
| 7701 | Basiskarte Vektor (routingfähig) |
| 7702 | Overlay Routen (Wanderwege, SchweizMobil) |
| 7703 | Overlay Höhenlinien |
| 7704 | Raster-IMG (Forschung, Release: Pixel 1:50'000–1:1'000'000) |
| 7705 | Raster-IMG Pixel 1:25'000–1:1'000'000 (geplant) |
| 7706 | Raster-IMG Pixel 1:10'000–1:1'000'000, Regionen (geplant) |
| 7707 | Raster-IMG Luftbild SWISSIMAGE (Prototyp Testgebiet) |
Map-IDs (8-stellig) je FID im Bereich `<FID>0000`–`<FID>9999` vergeben. Dateinamen, Quellstand und Lizenzangaben für Downloads: [docs/build/release.md](docs/build/release.md).

## Arbeitsweise
- Code unter `src/<modul>/`, Doku unter `docs/`, Build-Ausgaben unter `work/<modul>/` (gitignored).
- Scheitert ein Werkzeug unter macOS (Gatekeeper, fehlender arm64-Build, Cask deaktiviert), nicht lange umgehen und keine Sicherheitsprüfungen aushebeln (kein `xattr -d com.apple.quarantine`, kein `spctl`). Den Fehler dem Benutzer melden.
- Gibt es eine lokale Datei `AGENTS.local.md` (gitignored), gelten zusätzlich ihre Regeln für den eigenen Arbeitsplatz.

## Testumgebung
- Teststufen: CLI-Prüfung (mkgmap-Checks/-Reports, display-Dump), dann Darstellung und Routing/Suche in BaseCamp (macOS-Viewer optional), zum Schluss das Gerät. Siehe [docs/test/teststufen.md](docs/test/teststufen.md).

## Arbeitsordner
- Projekt-Skills liegen agent-neutral in `.agents/skills/<name>/` (versioniert). Claude Code liest Skills aus `.claude/skills/`. Dafür im Haupt-Checkout einen lokalen Symlink anlegen: `ln -s ../../.agents/skills/asd-ste100 .claude/skills/asd-ste100`. Private Skills bleiben in `.claude/skills/` (gitignored).
- Rohdaten, Downloads und Zwischenstände gehören in `downloads/`, `work/`, `tmp/` oder `scratch/`.
  Diese Ordner sind per `.gitignore` ausgeschlossen. Grosse Geodaten (`*.tif`, `*.gpkg`, `*.img`, `*.zip`) nie committen.
- Doku liegt in `docs/`.

## Git
- Branch `main`. Commits nur auf Anweisung.
- Push nur mit `git push origin main` bzw. einzelnen Release-Tags, nie mit `--all`, `--tags` oder `--mirror`.
