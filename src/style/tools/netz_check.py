"""Netzprüfung: Komponenten und isolierte Stücke je Auflösung (19–22) in Helvetopo-IMG-Kacheln.

Aufruf: python3 -I src/style/tools/netz_check.py <ordner mit 7701000?.img> <maxlänge m> [bbox]
Zählt Strassen-/Wegtypen 0x109xx, 0x10axx, 0x10bxx; T-Anschlüsse über Abstand Endpunkt–Segment,
Komponenten am Kachelrand gelten nicht als isoliert.
"""
import sys, math, glob, collections
sys.path.insert(0, 'src/style/tools')
from render_img import read_imgfs, Tile
K = 360 / 2**24
ROAD = lambda t: (t >> 8) in (0x109, 0x10a, 0x10b) and t not in (0x10a11,)
def run(files, res_list, maxlen, bbox=None):
    out = {}
    for r in res_list:
        tot_comp = small = 0; small_len = 0; cls = collections.Counter(); samples = []
        for f in files:
            fs = read_imgfs(open(f, 'rb').read())
            tn = [k.split('.')[0] for k in fs if k.endswith('.TRE')][0]
            t = Tile({k: v for k, v in fs.items() if k.startswith(tn + '.')})
            lv = [i for i, l in enumerate(t.levels) if l['bits'] == r]
            if not lv: continue
            pts, lines, polys = t.objects(lv[0])
            lines = [l for l in lines if ROAD(l[0]) and len(l[1]) > 1]
            allx = [x for l in lines for x, y in l[1]]; ally = [y for l in lines for x, y in l[1]]
            if not allx: continue
            # Kachelgrenze aus TRE wäre genauer; hier: Rand = äusserste 0.5 % der Koordinaten
            bx0, bx1, by0, by1 = min(allx), max(allx), min(ally), max(ally)
            tol = 2 ** (24 - r) * 3
            par = {}
            def find(a):
                while par.setdefault(a, a) != a:
                    par[a] = par[par[a]]; a = par[a]
                return a
            def key(p): return (round(p[0] / tol), round(p[1] / tol))
            for i, (typ, c, lab) in enumerate(lines):
                # alle Stützpunkte verbinden (T-Kreuzungen liegen meist auf Stützpunkten)
                for p in c:
                    par[find(('p',) + key(p))] = find(('l', i))
            # T-Anschlüsse: Endpunkt nahe an einem Segment einer anderen Linie
            cell = tol * 4; grid = collections.defaultdict(list)
            for i, (typ, c, lab) in enumerate(lines):
                for j in range(1, len(c)):
                    (x1, y1), (x2, y2) = c[j-1], c[j]
                    for gx in range(int(min(x1, x2)//cell), int(max(x1, x2)//cell) + 1):
                        for gy in range(int(min(y1, y2)//cell), int(max(y1, y2)//cell) + 1):
                            grid[(gx, gy)].append((i, x1, y1, x2, y2))
            def dseg(px, py, x1, y1, x2, y2):
                dx, dy = x2 - x1, y2 - y1; L2 = dx*dx + dy*dy
                u = 0 if L2 == 0 else max(0, min(1, ((px-x1)*dx + (py-y1)*dy) / L2))
                return math.hypot(px - x1 - u*dx, py - y1 - u*dy)
            for i, (typ, c, lab) in enumerate(lines):
                for px, py in (c[0], c[-1]):
                    for (k, x1, y1, x2, y2) in grid.get((int(px//cell), int(py//cell)), []):
                        if k != i and dseg(px, py, x1, y1, x2, y2) <= tol:
                            par[find(('l', i))] = find(('l', k))
            comp = collections.defaultdict(list)
            for i in range(len(lines)): comp[find(('l', i))].append(i)
            kx = math.cos(math.radians(47.4)) * 111320 * K; ky = 111320 * K
            for ids in comp.values():
                tot_comp += 1
                L = sum(math.hypot((c[j][0]-c[j-1][0])*kx, (c[j][1]-c[j-1][1])*ky) for i in ids for c in [lines[i][1]] for j in range(1, len(c)))
                xs = [x for i in ids for x, y in lines[i][1]]; ys = [y for i in ids for x, y in lines[i][1]]
                edge = min(xs) - bx0 < tol*2 or bx1 - max(xs) < tol*2 or min(ys) - by0 < tol*2 or by1 - max(ys) < tol*2
                if L < maxlen and not edge:
                    small += 1; small_len += L
                    for i in ids: cls[hex(lines[i][0])] += 1
                    cx, cy = sum(xs)/len(xs)*K, sum(ys)/len(ys)*K
                    if bbox is None or (bbox[0] < cx < bbox[2] and bbox[1] < cy < bbox[3]):
                        samples.append((round(cx, 4), round(cy, 4), round(L), sorted({hex(lines[i][0]) for i in ids})))
        out[r] = (tot_comp, small, round(small_len/1000, 1), cls.most_common(6), samples[:12])
    return out
if __name__ == '__main__':
    d = sys.argv[1]; maxlen = float(sys.argv[2]); bb = tuple(map(float, sys.argv[3].split(','))) if len(sys.argv) > 3 else None
    res = run(sorted(glob.glob(d + '/7701000[1-9].img')), [19, 20, 21, 22], maxlen, bb)
    for r, (n, s, sl, cls, smp) in res.items():
        print('Auflösung %d: Komponenten %d, isoliert < %d m: %d (%.1f km), Typen %s' % (r, n, maxlen, s, sl, cls))
        for x in smp: print('    ', x)
