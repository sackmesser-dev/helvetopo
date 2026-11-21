## Was ändert sich?

<!-- Kurz beschreiben, nach docs/schreibregeln.md (ASD-STE100). Verlinkte Issues mit "Fixes #…". -->

## Wie getestet?

- [ ] Build (Testgebiet oder Schweiz)
- [ ] BaseCamp
- [ ] Gerät:
- [ ] Stilmessung mit `src/style_qa/` (bei Stiländerungen)

## Checkliste

- [ ] Keine neuen Datenquellen ausser swisstopo-OGD und SchweizMobil (Open Data BY)
- [ ] Keine grossen Dateien (Geodaten, IMG, ZIP) im Commit
- [ ] Keine lokalen Angaben (Pfade, Server, Zugangsdaten) und keine Agenten-Kommentare wie „Session 33: …“
- [ ] Texte nach [Schreibregeln](../docs/schreibregeln.md), `python3 src/doc_lint/check_md.py` ohne Fehler
- [ ] Mit KI erzeugt: ja / nein
