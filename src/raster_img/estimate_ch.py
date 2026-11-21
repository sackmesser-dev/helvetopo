"""Hochrechnung der Raster-IMG-Grösse je Region und für die ganze Schweiz (Stichprobe).

Je Region werden zufällig gewählte JPEG-Kacheln (512 × 512) aus den GMP der Region gerechnet und mit
verschiedenen JPEG-Qualitäten kodiert. Grösse = GMP-Zahl × 100 Kacheln × mittlere Kachelgrösse
+ Verwaltungsdaten je GMP (gemessen) + Auffüllen auf 64-KiB-Blöcke.

Aufruf: python3 -I estimate_ch.py [--samples 30] [--jobs 4]
Ausgabe: Tabelle (Markdown) auf stdout, Rohdaten als JSON unter work/raster_img/regionen/estimate.json
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import subprocess
import sys
import tempfile
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image  # noqa: E402

import regions as R  # noqa: E402

QUALITIES = (85, 75, 65)
GMP_OVERHEAD = 30_000      # RGN/TRE/LBL ohne JPEG je GMP (gemessen ~25–30 KB)
BLOCK_PAD = 32 * 1024      # im Mittel halber 64-KiB-Block je Subdatei


def sample_tile(job):
    out, series, col, row, tx, ty = job
    s = R.SERIES[series]
    vrt = R.vrt_for(s.source, os.path.join(out, "_vrt"))
    w, _, _, n = s.bounds(col, row)
    step = R.TILE_PX * s.dpp
    tw, tn = w + tx * step, n - ty * step
    fd, tif = tempfile.mkstemp(suffix=".tif", dir=os.path.join(out, "_vrt"))
    os.close(fd)
    try:
        subprocess.run(["gdalwarp", "-q", "-overwrite", "-t_srs", "EPSG:4326", "-te", repr(tw), repr(tn - step),
                        repr(tw + step), repr(tn), "-ts", "512", "512", "-r", "cubic", "-wo", "INIT_DEST=255",
                        vrt, tif], check=True)
        im = Image.open(tif).convert("RGB")
        res = {}
        for q in QUALITIES:
            b = io.BytesIO()
            im.save(b, "JPEG", quality=q, subsampling=2)
            res[q] = len(b.getvalue())
        return series, col, row, res
    finally:
        os.remove(tif)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=30)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()
    out = R.OUT_DEFAULT
    rnd = random.Random(7704)
    sel = {(r, s): R.select_gmps(r, s, os.path.join(out, "_mask")) for r in R.REGIONS for s in R.SERIES}
    jobs = []
    nsamp = {"smr25": a.samples, "smr25h": a.samples, "smr50": a.samples // 2, "smr100": a.samples // 3}
    for r in R.REGIONS:
        if r == "schweiz":
            continue
        for s in R.SERIES:
            for _ in range(nsamp[s]):
                c, row = rnd.choice(sel[(r, s)])
                jobs.append((out, s, c, row, rnd.randrange(10), rnd.randrange(10)))
    with Pool(a.jobs) as pool:
        res = pool.map(sample_tile, jobs)
    # Mittelwerte je (Serie, GMP) → für jede Region aus den Stichproben, die in ihren GMP liegen
    by = {}
    for s, c, row, q in res:
        by.setdefault((s, c, row), []).append(q)
    stats = {}
    for (r, s), gmps in sel.items():
        vals = [q for g in gmps for q in by.get((s, *g), [])]
        mean = {qq: sum(v[qq] for v in vals) / len(vals) for qq in QUALITIES} if vals else {}
        stats[f"{r}/{s}"] = dict(gmp=len(gmps), samples=len(vals), mean=mean)
    json.dump(dict(stats=stats, raw=res), open(os.path.join(out, "estimate.json"), "w"), indent=1)

    def size(r, fine, q):
        tot = 0
        for s in (fine, "smr50", "smr100"):
            st = stats[f"{r}/{s}"]
            tot += st["gmp"] * (100 * st["mean"][q] + GMP_OVERHEAD + BLOCK_PAD)
        return tot

    print("| Region | GMP fein/50/100 | voll q85 | voll q75 | voll q65 | halb q85 | halb q75 |")
    print("|---|---|---|---|---|---|---|")
    for r in R.REGIONS:
        n = "/".join(str(stats[f"{r}/{s}"]["gmp"]) for s in ("smr25", "smr50", "smr100"))
        row = [size(r, "smr25", 85), size(r, "smr25", 75), size(r, "smr25", 65), size(r, "smr25h", 85),
               size(r, "smr25h", 75)]
        print(f"| {r} | {n} | " + " | ".join(f"{v / 1e9:.2f} GB" for v in row) + " |")
    print()
    for s in R.SERIES:
        allv = [q for (ss, *_), qs in by.items() if ss == s for q in qs]
        print(f"{s}: {len(allv)} Stichproben, Mittel " +
              ", ".join(f"q{q} {sum(v[q] for v in allv) / len(allv) / 1000:.1f} KB" for q in QUALITIES))


if __name__ == "__main__":
    main()
