#!/usr/bin/env python3
"""Check Markdown text against the project writing rules (German, based on ASD-STE100).

Rules (see docs/README.md, section "Schreibregeln"):
  E1  semicolon in running text (code is ignored)
  E2  umlaut written as ae/oe/ue (e.g. "fuer", "Groesse")
  W1  sentence with more than 25 words
  W2  paragraph with more than 6 sentences
  W3  vague word (vielleicht, eventuell, wohl, ...)
  W4  chronicle word in docs/ (Session, inzwischen, bisher, ...)

Errors (E) give exit code 1. Warnings (W) give exit code 0, with --strict exit code 1.

Usage:
  python3 src/doc_lint/check_md.py                 # all tracked *.md files
  python3 src/doc_lint/check_md.py docs/a.md b.md  # given files
  python3 src/doc_lint/check_md.py --stdin --name PR < body.txt
  --github  print GitHub Actions annotations
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_SENTENCE_WORDS = 25
MAX_PARAGRAPH_SENTENCES = 6

# Files that are not prose or are generated elsewhere.
SKIP_FILES = {"CLAUDE.md"}
# Third-party content in English (vendored skills with deliberate bad examples).
SKIP_DIRS = (".agents/",)

UMLAUT_STEMS = (
    "fuer", "ueber", "moeglich", "koenn", "muess", "waehl", "hoeh", "groess", "aender",
    "pruef", "naechst", "gueltig", "zurueck", "schluess", "fuehr", "loesch", "oeffn",
    "haeufig", "spaeter", "taeglich", "wuerd", "koennt", "muesst", "uebrig", "aehnlich",
    "schoen", "gehoer", "erhoeh", "verfueg", "unterstuetz", "massstaeb", "stueck",
)
UMLAUT_RE = re.compile(r"\b\w*(" + "|".join(UMLAUT_STEMS) + r")\w*", re.IGNORECASE)

VAGUE_RE = re.compile(
    r"\b(vielleicht|eventuell|evtl\.|wohl|irgendwie|gegebenenfalls|ggf\.|eigentlich|ziemlich|"
    r"möglicherweise|vermutlich|grundsätzlich)(?!\w)",
    re.IGNORECASE,
)
CHRONICLE_RE = re.compile(
    r"\b(Session|Sessions|Learnings?|inzwischen|neuerdings|gestern|"
    r"bisher|mittlerweile|zuletzt)\b",
    re.IGNORECASE,
)

ABBREVIATIONS = (
    "z. B.", "z.B.", "d. h.", "d.h.", "u. a.", "u.a.", "ca.", "bzw.", "usw.", "vgl.", "inkl.",
    "ggf.", "evtl.", "Nr.", "resp.", "etc.", "Mio.", "Mrd.", "max.", "min.", "rund.", "bspw.",
    "S.", "Abb.", "Kap.", "u. U.", "o. Ä.", "St.", "Gr.", "v. a.", "sog.", "Str.",
)


@dataclass
class Finding:
    path: str
    line: int
    code: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.code.startswith("E")


def strip_inline(text: str) -> str:
    """Remove code, links targets, URLs, HTML comments and emphasis markers."""
    text = re.sub(r"`[^`]*`", "CODE", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<!--.*?-->", "", text)
    text = re.sub(r"https?://\S+", "URL", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("**", "").replace("__", "")
    return text


def split_sentences(text: str, colon: bool = True) -> list[str]:
    protected = text
    for abbr in ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", "\u2024"))
    # Ordinal numbers like "am 5. November" are not sentence ends. Other numbers can end a sentence.
    months = "Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember"
    protected = re.sub(r"((?:^|\s)\d{1,2})\.(\s+(?:" + months + r"))", "\\1\u2024\\2", protected)
    pattern = r"(?<=[.!?])\s+(?=[\wÄÖÜ„\"])"
    if colon:
        pattern += r"|(?<=:)\s+(?=[A-ZÄÖÜ„\"])"
    parts = re.split(pattern, protected)
    return [p.replace("\u2024", ".").strip() for p in parts if p.strip()]


def word_count(sentence: str) -> int:
    # A list of code values ("`a`, `b`, `c`") counts as one word.
    sentence = re.sub(r"CODE(?:\s*(?:,|und|oder|bzw\.)\s*CODE)+", "CODE", sentence)
    return len(re.findall(r"[\wÄÖÜäöüß'’\-/]+", sentence))


def blocks(lines: list[str]):
    """Yield (start_line, kind, text) for paragraphs, list items, table rows and headings."""
    in_fence = False
    in_comment = False
    current: list[str] = []
    start = 0
    kind = "para"

    def flush():
        nonlocal current
        if current:
            yield_item = (start, kind, " ".join(s.strip() for s in current))
            current = []
            return yield_item
        return None

    out = []
    for no, raw in enumerate(lines, 1):
        line = re.sub(r"^\s*>\s?", "", raw.rstrip("\n"))  # blockquote marker
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            item = flush()
            if item:
                out.append(item)
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_comment:
            if "-->" in stripped:
                in_comment = False
            continue
        if stripped.startswith("<!--") and "-->" not in stripped:
            in_comment = True
            continue
        if not stripped:
            item = flush()
            if item:
                out.append(item)
            continue
        if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("---"):
            item = flush()
            if item:
                out.append(item)
            kind_here = "head" if stripped.startswith("#") else "table"
            out.append((no, kind_here, stripped))
            continue
        is_item = re.match(r"^\s*([-*+]|\d+[.)])\s+", line)
        if is_item:
            item = flush()
            if item:
                out.append(item)
            start, kind = no, "item"
            current = [line[is_item.end():]]
            continue
        if not current:
            start, kind = no, "para"
        current.append(line)
    item = flush()
    if item:
        out.append(item)
    return out


def check_text(path: str, text: str, chronicle: bool) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    # Front matter (YAML) is not prose.
    if lines and lines[0].strip() == "---":
        try:
            end = lines.index("---", 1)
            lines = [""] * (end + 1) + lines[end + 1:]
        except ValueError:
            pass
    for no, kind, raw in blocks(lines):
        plain = strip_inline(raw)
        # Quoted source values („8;16“) are data, not text.
        unquoted = re.sub(r"„[^“]*“|\"[^\"]*\"", "", plain)
        if ";" in unquoted:
            findings.append(Finding(path, no, "E1", "Semikolon: zwei Sätze daraus machen"))
        # Quoted source values („Uebrige Bahnen“) and identifiers (hoehen.md, T62_HOEHE) stay as they are.
        prose = re.sub(r"\S*[._/]\S*", "", unquoted)
        for m in UMLAUT_RE.finditer(prose):
            findings.append(Finding(path, no, "E2", f"Umlaut ausschreiben: „{m.group(0)}“"))
        for m in VAGUE_RE.finditer(unquoted):
            findings.append(Finding(path, no, "W3", f"Unscharfes Wort „{m.group(0)}“: Tatsache nennen"))
        if chronicle:
            for m in CHRONICLE_RE.finditer(unquoted):
                findings.append(Finding(path, no, "W4", f"Chronik-Wort „{m.group(0)}“: aktuellen Stand beschreiben"))
        if kind in ("para", "item"):
            sentences = split_sentences(plain)
            for s in sentences:
                n = word_count(s)
                if n > MAX_SENTENCE_WORDS:
                    findings.append(Finding(path, no, "W1", f"Satz mit {n} Wörtern (max. {MAX_SENTENCE_WORDS}): „{s[:50]}…“"))
            n_sentences = len(split_sentences(plain, colon=False))
            if kind == "para" and n_sentences > MAX_PARAGRAPH_SENTENCES:
                findings.append(Finding(path, no, "W2", f"Absatz mit {n_sentences} Sätzen (max. {MAX_PARAGRAPH_SENTENCES})"))
    return findings


def tracked_markdown(root: Path) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "*.md"], cwd=root, capture_output=True, text=True, check=True)
    return [root / p for p in out.stdout.split()
            if Path(p).name not in SKIP_FILES and not p.startswith(SKIP_DIRS)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--stdin", action="store_true", help="Text von stdin prüfen (PR-Beschreibung, Commit-Nachricht)")
    ap.add_argument("--name", default="stdin", help="Name für --stdin in der Ausgabe")
    ap.add_argument("--strict", action="store_true", help="Warnungen wie Fehler behandeln")
    ap.add_argument("--errors-only", action="store_true", help="Nur Fehler ausgeben")
    ap.add_argument("--github", action="store_true", help="GitHub-Actions-Annotationen ausgeben")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parents[2]
    findings: list[Finding] = []
    if args.stdin:
        findings += check_text(args.name, sys.stdin.read(), chronicle=False)
    else:
        files = args.files or tracked_markdown(root)
        for f in files:
            if f.suffix != ".md" or f.name in SKIP_FILES or not f.exists():
                continue
            try:
                rel = f.resolve().relative_to(root).as_posix()
            except ValueError:
                rel = str(f)
            if rel.startswith(SKIP_DIRS):
                continue
            findings += check_text(rel, f.read_text(encoding="utf-8"), chronicle=rel.startswith("docs/"))

    if args.errors_only:
        findings = [f for f in findings if f.is_error]
    for f in findings:
        if args.github:
            level = "error" if f.is_error or args.strict else "warning"
            print(f"::{level} file={f.path},line={f.line},title={f.code}::{f.message}")
        else:
            print(f"{f.path}:{f.line}: {f.code} {f.message}")
    errors = sum(f.is_error for f in findings)
    warnings = len(findings) - errors
    print(f"{errors} Fehler, {warnings} Warnungen", file=sys.stderr)
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
