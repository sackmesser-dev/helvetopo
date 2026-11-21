#!/usr/bin/env python3
"""Garmin-Typen je Auflösung über alle Kacheln eines Ordners zählen (für Build-Vergleiche).

Nutzt den Dekoder von src/style/tools/render_img.py (--list) je Kachel und summiert.
Kachelgrenzen unterscheiden sich zwischen Builds (z. B. mit/ohne Höhenlinien), deshalb immer
über alle Kacheln summieren, nie einzelne Kachelnummern vergleichen.

  python3 -I src/build/count_types.py --res 22 work/build/7701 /pfad/zu/anderem/build
  python3 -I src/build/count_types.py --res 22 --types 0x10b06,0x10b07 work/build/7701
"""
import argparse
import collections
import glob
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "..", "style", "tools", "render_img.py")
TYP = os.path.join(HERE, "..", "style", "typ", "swisstopo.txt")


def count(folder, res):
    c = collections.Counter()
    tiles = sorted(f for f in glob.glob(os.path.join(folder, "[0-9]" * 8 + ".img"))
                   if not re.search(r"\d{4}0000\.img$", f))
    with tempfile.TemporaryDirectory() as td:
        for f in tiles:
            out = subprocess.run([sys.executable, "-I", RENDER, f, TYP, os.path.join(td, "x.png"),
                                  "--res", str(res), "--scale", "0.02", "--list"],
                                 capture_output=True, text=True).stdout
            for line in out.splitlines():
                kind = {"Punkte": "point", "Linien": "line", "Flächen": "polygon"}.get(line.split(" ", 1)[0])
                if not kind:
                    continue
                for tok in line.split()[1:]:
                    k, v = tok.rsplit(":", 1)
                    c[(kind, k)] += int(v)
    return len(tiles), c


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("folders", nargs="+")
    ap.add_argument("--res", type=int, default=22)
    ap.add_argument("--types", help="nur diese Typen (Komma), sonst alle")
    a = ap.parse_args()
    results = [(f, *count(f, a.res)) for f in a.folders]
    keys = sorted(set().union(*(c.keys() for _, _, c in results)))
    if a.types:
        want = set(a.types.split(","))
        keys = [k for k in keys if k[1] in want]
    print("typ\t" + "\t".join(f"{os.path.basename(os.path.normpath(f))} ({n} Kacheln)" for f, n, _ in results))
    for k in keys:
        print(f"{k[0]} {k[1]}\t" + "\t".join(str(c.get(k, 0)) for _, _, c in results))
    for kind in ("point", "line", "polygon"):
        print(f"{kind} gesamt\t" + "\t".join(str(sum(v for kk, v in c.items() if kk[0] == kind)) for _, _, c in results))


if __name__ == "__main__":
    main()
