# Schreibregeln

Stand: 2026-11-05

Alle Texte im Projekt folgen ASD-STE100 (Simplified Technical English), übertragen auf Deutsch. Die Regeln gelten für:

- alle Markdown-Dateien im Repo (`docs/`, README, CONTRIBUTING, Release-Texte)
- Texte, die ein Skript in Markdown-Dateien schreibt (z. B. `make_release.py`, `make_typ.py --soll-ist`)
- Beschreibungen von Pull Requests und Issues
- Commit-Nachrichten

Die Quelle der Regeln ist der Skill `asd-ste100` in [.agents/skills/asd-ste100/](../.agents/skills/asd-ste100/SKILL.md) (MIT-Lizenz). Er beschreibt die Regeln für Englisch. Diese Datei überträgt sie auf Deutsch.

## Inhalt

- Nur Fakten zum aktuellen Stand. Die Entstehung steht in der Git-Historie.
- Keine Chronik, keine Testprotokolle, keine Arbeitsberichte.
- Neue Befunde ändern die passende Stelle. Keinen Abschnitt anhängen.
- Unsicheres als **(unsicher)** markieren. Keine Füllwörter wie „vielleicht“, „wohl“ oder „vermutlich“.
- Keine privaten Angaben (Benutzerpfade, IP-Adressen, Zugangsdaten). Diese gehören in lokale, nicht versionierte Dateien.

## Wörter

- Ein Begriff je Sache. Ein Begriff hat nur eine Bedeutung.
- Das einfache, häufige Wort statt eines seltenen Synonyms.
- Ein Verb für eine Handlung, kein Substantiv daraus („prüfen“ statt „eine Prüfung durchführen“).
- Umlaute ausschreiben (ä, ö, ü). Kein ae, oe, ue im Fliesstext. Schweizer ss statt ß ist korrekt.
- Code-Bezeichner, Dateinamen und Datenwerte in `Backticks` oder „Anführungszeichen“. Sie bleiben, wie sie sind.

## Sätze

- Ein Gedanke je Satz. Eine Anweisung je Satz.
- Höchstens 20 Wörter in Anweisungen, höchstens 25 Wörter in Beschreibungen.
- Aktiv schreiben. Passiv nur, wenn der Handelnde unbekannt oder unwichtig ist.
- Anweisungen im Imperativ oder Infinitiv („Datei kopieren.“).
- Keine Satzteile weglassen, nur um zu kürzen.
- Kein Semikolon. Zwei Sätze daraus machen.

## Absätze und Aufbau

- Ein Thema je Absatz. Höchstens 6 Sätze je Absatz.
- Abläufe, Bedingungen und Aufzählungen als Liste. Abläufe nummeriert.
- Warnungen und sicherheitsrelevante Anweisungen stehen am Satzanfang.
- Jede Datei unter `docs/` beginnt mit Titel und „Stand: Datum“.

## Prüfung

Das Skript `src/doc_lint/check_md.py` prüft die Regeln, die sich maschinell prüfen lassen.

| Code | Regel | Art |
|---|---|---|
| E1 | Semikolon im Fliesstext | Fehler |
| E2 | Umlaut als ae, oe, ue geschrieben | Fehler |
| W1 | Satz mit mehr als 25 Wörtern | Warnung |
| W2 | Absatz mit mehr als 6 Sätzen | Warnung |
| W3 | unscharfes Wort („vielleicht“, „wohl“, „vermutlich“) | Warnung |
| W4 | Chronik-Wort in `docs/` („Session“, „inzwischen“, „bisher“) | Warnung |

Code-Blöcke, Inline-Code, Link-Ziele und Werte in Anführungszeichen prüft das Skript nicht.
Die englischen Fremdtexte in `.agents/` prüft es ebenfalls nicht.

Erzeugte Markdown-Dateien (z. B. `docs/stil/soll-ist.md`) korrigiert man im erzeugenden Skript, nicht in der Datei.

Aufruf:

1. Alle Markdown-Dateien prüfen: `python3 src/doc_lint/check_md.py`
2. Einzelne Dateien prüfen: `python3 src/doc_lint/check_md.py docs/a.md`
3. PR-Beschreibung oder Commit-Nachricht prüfen: `python3 src/doc_lint/check_md.py --stdin --name PR < text.txt`

Fehler ergeben den Exit-Code 1. Warnungen ergeben den Exit-Code 0, mit `--strict` den Exit-Code 1.

Bei jedem Pull Request prüft der GitHub-Workflow [doku-stil.yml](../.github/workflows/doku-stil.yml) die geänderten Markdown-Dateien und die PR-Beschreibung. Fehler blockieren den PR. Warnungen erscheinen als Hinweis im Diff.

Die Regeln zu Satzbau, Passiv und Begriffen prüft das Skript nicht. Dafür gilt die Durchsicht durch Autorin oder Autor bzw. Agent.
