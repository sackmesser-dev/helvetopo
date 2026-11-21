#!/usr/bin/env python3
"""TYP-Quelltexte (mkgmap-Textformat) zu einer TYP für eine Familie zusammenführen.

Prüft Typcode-Kollisionen zwischen den Quellen: Kommt ein [_point]/[_line]/[_polygon]-Typ in
mehr als einer Quelle vor, bricht das Skript ab (Exit 1). Ausnahme sind Typen in --shared
(gleiche Bedeutung, z. B. Garmin-Höhenlinien 0x20–0x22 in Basis- und Höhenlinien-TYP): Dann gilt
die Definition der zuerst genannten Quelle, und das Skript meldet die Überschneidung.

  merge_typ.py --fid 7701 --out merged.txt swisstopo.txt routes.txt contours.txt \
      --shared line:0x20,line:0x21,line:0x22
  merge_typ.py --check-only swisstopo.txt routes.txt contours.txt   # nur Kollisionsprüfung
"""
import argparse
import re
import sys

BLOCK = re.compile(r"^\[(_\w+)\]\s*$")


def parse(path):
    """→ (drawOrder-Einträge, Elementblöcke [(kind, key, text)])"""
    lines = open(path, encoding="utf-8").read().splitlines()
    blocks, order, cur, kind = [], [], None, None
    for ln in lines:
        m = BLOCK.match(ln.strip())
        if m and m.group(1) != "_end":
            kind, cur = m.group(1), [ln]
            continue
        if cur is None:
            continue
        cur.append(ln)
        if ln.strip().lower() == "[end]":
            if kind == "_drawOrder":
                order += [l.strip() for l in cur[1:-1] if l.strip().lower().startswith("type=")]
            elif kind in ("_point", "_line", "_polygon"):
                t = st = None
                for l in cur:
                    s = l.strip()
                    if s.lower().startswith("type="):
                        t = int(s.split("=", 1)[1].split(",")[0], 0)
                    elif s.lower().startswith("subtype="):
                        st = int(s.split("=", 1)[1], 0)
                    elif s.startswith(";") and len(cur) and False:
                        pass
                if t is None:
                    raise SystemExit(f"{path}: Block ohne Type=")
                code = (t << 8 | st) if st is not None and t <= 0xFF else t
                blocks.append((kind[1:], code, "\n".join(cur)))
            cur, kind = None, None
    return order, blocks


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--fid", type=int)
    ap.add_argument("--pid", type=int, default=1)
    ap.add_argument("--codepage", type=int, default=1252)
    ap.add_argument("--out")
    ap.add_argument("--shared", default="", help="erlaubte Überschneidungen, z. B. line:0x20,line:0x21")
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    shared = set()
    for item in filter(None, a.shared.split(",")):
        k, c = item.split(":")
        shared.add((k, int(c, 0)))

    seen, out_blocks, order, order_seen = {}, [], [], set()
    errors, notes = [], []
    for src in a.sources:
        o, blocks = parse(src)
        local = set()
        for kind, code, text in blocks:
            key = (kind, code)
            if key in local:
                errors.append(f"{src}: {kind} 0x{code:x} doppelt in derselben Datei")
                continue
            local.add(key)
            if key in seen:
                if key in shared:
                    notes.append(f"{kind} 0x{code:x}: geteilt, Definition aus {seen[key]} gilt (nicht {src})")
                else:
                    errors.append(f"KOLLISION {kind} 0x{code:x}: {seen[key]} und {src}")
                continue
            seen[key] = src
            out_blocks.append(text)
        for e in o:
            k = e.split("=", 1)[1].split(",")[0].strip().lower()
            if k not in order_seen:
                order_seen.add(k)
                order.append(e)
    for n in notes:
        print("Hinweis:", n, file=sys.stderr)
    for e in errors:
        print("FEHLER:", e, file=sys.stderr)
    counts = {k: sum(1 for kk, _ in seen if kk == k) for k in ("point", "line", "polygon")}
    print(f"TYP-Prüfung: {len(a.sources)} Quellen, {counts}, {len(notes)} geteilt, "
          f"{len(errors)} Kollisionen", file=sys.stderr)
    if errors:
        return 1
    if a.check_only or not a.out:
        return 0
    with open(a.out, "w", encoding="utf-8") as f:
        # mkgmap liest TYP-Quellen ohne diese Kopfzeile als Latin-1; dann landen UTF-8-Bytes
        # in der TYP („GebÃ¤ude“ in BaseCamp). Die Zeile muss die erste sein.
        f.write("; -*- coding: utf-8 -*-\n")
        f.write(f"; Zusammengeführt aus: {', '.join(a.sources)}\n; Erzeugt von src/build/merge_typ.py, nicht von Hand ändern.\n\n")
        f.write(f"[_id]\nFID={a.fid}\nProductCode={a.pid}\nCodePage={a.codepage}\n[end]\n\n")
        if order:
            f.write("[_drawOrder]\n" + "\n".join(order) + "\n[end]\n\n")
        f.write("\n\n".join(out_blocks) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
