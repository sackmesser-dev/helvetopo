#!/usr/bin/env python3
"""Höhenkoten neben benannten Gipfeln, Hügeln und Pässen entfernen.

Eine unbenannte Kote (SMV25 oder swissALTI3D) nahe einem benannten Gipfel verdrängt in BaseCamp
den Gipfelnamen und dessen Kote (z. B. Säntis: Geländekote 2453 an der Bergstation, 196 m neben
dem Gipfel 2502). Diese Koten fallen deshalb weg, wenn sie näher als --radius an einem Knoten mit
natural=peak|hill|saddle und name aus der Basis-PBF liegen.

  python3 -I src/dem/filter_spots.py --spots spot_heights.osm.pbf --base ch.osm.pbf \
      --out spot_heights.filtered.osm.pbf [--radius 300]
Nur osmium und Standardbibliothek (Gitter-Suche statt KD-Baum).
"""
import argparse
import math
import re
import subprocess
import sys

COORD = re.compile(r" x(-?[\d.]+) y(-?[\d.]+)")


def opl_nodes(pbf, *filters):
    cmd = ["osmium", "tags-filter", pbf, *filters, "-f", "opl", "-o", "-"] if filters else \
          ["osmium", "cat", pbf, "-f", "opl", "-o", "-"]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.startswith("n")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spots", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--radius", type=float, default=300.0, help="Mindestabstand zu benannten Gipfeln/Pässen (m)")
    a = ap.parse_args()

    named = []
    for l in opl_nodes(a.base, "n/natural=peak,hill,saddle"):
        if not re.search(r"(?:^| T|,)name=", l):
            continue
        m = COORD.search(l)
        if m:
            named.append((float(m.group(1)), float(m.group(2))))
    if not named:
        print("keine benannten Gipfel/Pässe gefunden, Koten unverändert", file=sys.stderr)
    lat0 = sum(y for _, y in named) / len(named) if named else 46.8
    kx, ky = 111320.0 * math.cos(math.radians(lat0)), 110574.0
    cell = a.radius
    grid = {}
    for x, y in named:
        grid.setdefault((int(x * kx // cell), int(y * ky // cell)), []).append((x * kx, y * ky))

    def near(x, y):
        px, py = x * kx, y * ky
        cx, cy = int(px // cell), int(py // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for qx, qy in grid.get((cx + dx, cy + dy), ()):
                    if (px - qx) ** 2 + (py - qy) ** 2 < a.radius ** 2:
                        return True
        return False

    keep, dropped = [], 0
    for l in opl_nodes(a.spots):
        m = COORD.search(l)
        # Seebodenkoten (swisstopo:kote=seeboden) und alles ohne natural=spot_height bleiben
        if m and "natural=spot_height" in l and near(float(m.group(1)), float(m.group(2))):
            dropped += 1
            continue
        keep.append(l)
    opl = a.out + ".opl"
    with open(opl, "w") as f:
        f.write("\n".join(keep) + "\n")
    subprocess.run(["osmium", "cat", "--overwrite", "-o", a.out, opl], check=True)
    import os
    os.remove(opl)
    print(f"Koten: {len(keep) + dropped} → {len(keep)}, entfernt {dropped} (< {a.radius:g} m neben "
          f"{len(named)} benannten Gipfeln/Hügeln/Pässen)", file=sys.stderr)


if __name__ == "__main__":
    main()
