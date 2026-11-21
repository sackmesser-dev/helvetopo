"""Messungen je Objektart und Gesamtmasse.

    python -I src/style_qa/measure.py            → work/style_qa/results.json

Für jeden Ausschnitt und jede Zoomstufe:
- Masken aus den Vektordaten: SMV25-Geometrie (die QGIS genau so zeichnet, und die der
  Pixelkarte entspricht) bzw. die Objekte unserer IMG (ours_objects.json).
- Farbe: dominante Farbe (Modus in 5-bit-Klassen) auf der Mittellinie bzw. im Flächeninnern,
  ohne Kreuzungen; Abweichung als ΔE2000.
- Breite: Distanztransformation der linienfarbigen Pixel auf der Mittellinie, getrennt für die
  Füllung und mit Rand (Rand = abweichende Farbe direkt neben der Füllung).
- Strichmuster: Abtastung entlang der Geometrie (0,5 px), Lauflängen Strich/Lücke.
- Zeichenreihenfolge: an den Überlagerungspixeln zweier Klassen, welche Farbe sichtbar ist.
- Beschriftung: Namen der SMV25-Annotationen gegen die Labels der IMG; Grösse, Farbe, kursiv.
- Symbole: Anzahl je Objektart im Ausschnitt.
- Gesamt: SSIM, ΔE nach Weichzeichnung, Lab-Histogramm-Schnitt, Relief-Korrelation.
"""
import csv
import importlib.util
import json
import math
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
import classes as K  # noqa: E402

from osgeo import ogr  # noqa: E402

DE_TOL = 15.0     # ΔE2000-Toleranz für „gleiche Farbe“ (Antialiasing, JPEG/Resampling)


# ------------------------------------------------------------------ Farbe
def srgb_to_lab(rgb):
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ M.T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    L = 116 * f[..., 1] - 16
    a = 500 * (f[..., 0] - f[..., 1])
    b = 200 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1)


def de2000(lab1, lab2):
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    C1 = np.hypot(a1, b1); C2 = np.hypot(a2, b2)
    Cm = (C1 + C2) / 2
    G = 0.5 * (1 - np.sqrt(Cm ** 7 / (Cm ** 7 + 25 ** 7)))
    a1p = (1 + G) * a1; a2p = (1 + G) * a2
    C1p = np.hypot(a1p, b1); C2p = np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp = L2 - L1
    dCp = C2p - C1p
    dh = h2p - h1p
    dh = np.where(np.abs(dh) > 180, dh - 360 * np.sign(dh), dh)
    dh = np.where(C1p * C2p == 0, 0, dh)
    dHp = 2 * np.sqrt(C1p * C2p) * np.sin(np.radians(dh / 2))
    Lpm = (L1 + L2) / 2
    Cpm = (C1p + C2p) / 2
    hsum = h1p + h2p
    hpm = np.where(np.abs(h1p - h2p) > 180, (hsum + 360) / 2, hsum / 2)
    hpm = np.where(C1p * C2p == 0, hsum, hpm)
    T = (1 - 0.17 * np.cos(np.radians(hpm - 30)) + 0.24 * np.cos(np.radians(2 * hpm))
         + 0.32 * np.cos(np.radians(3 * hpm + 6)) - 0.20 * np.cos(np.radians(4 * hpm - 63)))
    dtheta = 30 * np.exp(-((hpm - 275) / 25) ** 2)
    RC = 2 * np.sqrt(Cpm ** 7 / (Cpm ** 7 + 25 ** 7))
    SL = 1 + 0.015 * (Lpm - 50) ** 2 / np.sqrt(20 + (Lpm - 50) ** 2)
    SC = 1 + 0.045 * Cpm
    SH = 1 + 0.015 * Cpm * T
    RT = -np.sin(np.radians(2 * dtheta)) * RC
    return np.sqrt((dLp / SL) ** 2 + (dCp / SC) ** 2 + (dHp / SH) ** 2 + RT * (dCp / SC) * (dHp / SH))


def de(c1, c2):
    return float(de2000(srgb_to_lab(np.array(c1, float)), srgb_to_lab(np.array(c2, float))))


def hexc(rgb):
    return '#%02X%02X%02X' % tuple(int(round(v)) for v in rgb[:3])


def parse_hex(h):
    h = h.strip().lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mode_color(pix):
    """Dominante Farbe: häufigste 5-bit-Klasse, Mittelwert der Pixel darin."""
    if len(pix) == 0:
        return None
    q = (pix >> 3).astype(np.int32)
    key = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
    vals, cnt = np.unique(key, return_counts=True)
    k = vals[np.argmax(cnt)]
    sel = pix[key == k]
    return tuple(float(v) for v in sel.mean(axis=0)), float(cnt.max() / len(pix))


# ------------------------------------------------------------------ Geometrie → Masken
def draw_mask(polys, kind, W, H, width=1):
    im = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(im)
    for pts in polys:
        if len(pts) < 2:
            continue
        xy = [tuple(p) for p in pts]
        if kind == 'area':
            if len(xy) >= 3:
                d.polygon(xy, fill=255)
        else:
            d.line(xy, fill=255, width=width)
    return np.array(im) > 0


class SMV:
    def __init__(self):
        self.ds = ogr.Open(C.SMV25_GPKG)

    def features(self, layer, where, grid):
        e0, n0, e1, n1, W, H, mpx = grid
        lyr = self.ds.GetLayerByName(layer)
        lyr.SetSpatialFilterRect(e0, n0, e1, n1)
        lyr.SetAttributeFilter(where)
        out = []
        for f in lyr:
            g = f.GetGeometryRef()
            if g is None:
                continue
            out.append((f, g.Clone()))
        lyr.SetAttributeFilter(None)
        lyr.SetSpatialFilter(None)
        return out

    def geoms_px(self, layer, where, grid):
        e0, n0, e1, n1, W, H, mpx = grid
        rings = []
        cats = Counter()
        for f, g in self.features(layer, where, grid):
            try:
                cats[f.GetField('Symbol')] += 1
            except Exception:
                pass
            for part in explode(g):
                rings.append([((x - e0) / mpx, (n1 - y) / mpx) for x, y in part])
        return rings, cats


def explode(g):
    t = ogr.GT_Flatten(g.GetGeometryType())
    if t in (ogr.wkbPoint,):
        return [[(g.GetX(), g.GetY())]]
    if t in (ogr.wkbLineString, ogr.wkbLinearRing):
        return [g.GetPoints() or []]
    out = []
    for i in range(g.GetGeometryCount()):
        out += explode(g.GetGeometryRef(i))
    return out


def ours_geoms(obj, types, kind):
    key = {'line': 'lines', 'area': 'polygons', 'point': 'points'}[kind]
    ts = set(types)
    if kind == 'point':
        return [o[1] for o in obj['points'] if o[0] in ts]
    return [o[1] for o in obj[key] if o[0] in ts]


# ------------------------------------------------------------------ Nennwerte
class Nominal:
    def __init__(self):
        spec = importlib.util.spec_from_file_location('render_img', C.RENDER_IMG)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.typ = mod.parse_typ(C.TYP_TXT)
        self.sym = defaultdict(list)
        p = os.path.join(C.DOWNLOADS, 'style-swisstopo', 'symbology.tsv')
        for r in csv.DictReader(open(p, encoding='utf-8'), delimiter='\t'):
            self.sym[(r['layer'], r['kategorie'])].append(r)

    def typ_line(self, t):
        sec = self.typ['line'].get(int(t, 16))
        if not sec:
            return None
        x = sec['Xpm']
        cols = [x['cols'][k] for k in x['order']]
        if x['w'] == 0:
            lw = int(sec.get('LineWidth', 1)); bw = int(sec.get('BorderWidth', 0))
            return {'fill': cols[0], 'border': cols[1] if bw and len(cols) > 1 else None,
                    'w_fill': lw, 'w_total': lw + 2 * bw, 'muster': None}
        rows = x['rows']
        on = [any(r[i] == x['order'][0] for r in rows) for i in range(x['w'])]
        return {'fill': cols[0], 'border': cols[1] if len(cols) > 1 and cols[1] != 'none' else None,
                'w_fill': x['h'], 'w_total': x['h'], 'muster': ''.join('x' if o else '.' for o in on)}

    def typ_poly(self, t):
        sec = self.typ['polygon'].get(int(t, 16))
        if not sec:
            return None
        x = sec['Xpm']
        cols = [x['cols'][k] for k in x['order']]
        return {'fill': cols[0], 'muster': x['w'] > 0, 'zweitfarbe': cols[1] if len(cols) > 1 else None,
                'draworder': self.typ['order'].get(int(t, 16))}

    def typ_point(self, t):
        return self.typ['point'].get(int(t, 16))

    def smv(self, layer, cats):
        """Nennwerte der häufigsten Kategorie: Füllfarbe (oberste Linie), Breiten in mm, Strich."""
        if not cats:
            return None
        cat = cats.most_common(1)[0][0]
        rows = self.sym.get((layer, cat)) or self.sym.get((layer, '(alle)'))
        if not rows:
            return {'kategorie': cat}
        lines = [r for r in rows if r['klasse'] == 'SimpleLine' and r['breite']]
        fills = [r for r in rows if r['klasse'] in ('SimpleFill',) and r['farbe']]
        res = {'kategorie': cat}
        if lines:
            ws = [float(r['breite']) for r in lines]
            top = lines[-1]
            res.update({'fill': top['farbe'], 'w_fill_mm': float(top['breite']), 'w_total_mm': max(ws),
                        'dash': next((r['dash'] for r in lines if r['stil'] == 'dash' and r['dash']), None)})
            if max(ws) > float(top['breite']) + 1e-6:
                res['border'] = lines[ws.index(max(ws))]['farbe']
        if fills:
            res['fill'] = fills[0]['farbe']
            res['rand'] = fills[0].get('rand') or None
        return res


# ------------------------------------------------------------------ Messungen
def lab_img(path):
    a = np.array(Image.open(path).convert('RGB'))
    return a, srgb_to_lab(a)


def color_near(lab, col, tol=DE_TOL):
    ref = srgb_to_lab(np.array(col, float))[None, None, :]
    return de2000(lab, np.broadcast_to(ref, lab.shape)) < tol


def samples_along(geoms, step, W, H, excl):
    """Punkte (x, y, nx, ny) im Abstand step entlang der Geometrien, ausserhalb von excl."""
    out = []
    for pts in geoms:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            if L < 1e-6:
                continue
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            t = step / 2
            while t < L:
                x, y = x0 + ux * t, y0 + uy * t
                xi, yi = int(round(x)), int(round(y))
                if 12 <= xi < W - 12 and 12 <= yi < H - 12 and not excl[yi, xi]:
                    out.append((x, y, -uy, ux))
                t += step
    return out


def profiles(rgb, smp, half=12, step=0.5):
    """Farbprofile quer zur Linie: Array (n, k, 3) und Offsets (k)."""
    offs = np.arange(-half, half + step / 2, step)
    if not smp:
        return np.zeros((0, len(offs), 3)), offs
    S = np.array(smp)
    xs = np.rint(S[:, 0:1] + S[:, 2:3] * offs[None, :]).astype(int).clip(0, rgb.shape[1] - 1)
    ys = np.rint(S[:, 1:2] + S[:, 3:4] * offs[None, :]).astype(int).clip(0, rgb.shape[0] - 1)
    return rgb[ys, xs].astype(float), offs


def run_width(match, offs, step=0.5, centre_tol=1.0):
    """Breite des zusammenhängenden True-Laufs um die Mitte (Mitte ±centre_tol erlaubt)."""
    k0 = len(offs) // 2
    tol = int(centre_tol / step)
    res = np.full(match.shape[0], np.nan)
    for i, row in enumerate(match):
        cand = [k0 + d for d in sorted(range(-tol, tol + 1), key=abs) if row[k0 + d]]
        if not cand:
            continue
        c = cand[0]
        l = c
        while l - 1 >= 0 and row[l - 1]:
            l -= 1
        r = c
        while r + 1 < len(row) and row[r + 1]:
            r += 1
        if l == 0 or r == len(row) - 1:
            continue          # läuft in den Hintergrund aus (z. B. weisse Strasse auf Weiss)
        res[i] = (r - l + 1) * step
    return res


def measure_line(rgb, lab, center, excl, geoms):
    """Querprofile alle 2 px: Füllfarbe, Füllbreite, Randfarbe, Gesamtbreite, Hintergrund."""
    H, W = center.shape
    smp = samples_along(geoms, 2.0, W, H, excl)
    if len(smp) < 15:
        return None
    P, offs = profiles(rgb, smp)
    k0 = len(offs) // 2
    centre = P[:, k0 - 1:k0 + 2].reshape(-1, 3)
    mc = mode_color(centre.astype(np.uint8))
    fill, purity = mc
    Pl = srgb_to_lab(P)
    dfill = de2000(Pl, np.broadcast_to(srgb_to_lab(np.array(fill)), Pl.shape))
    F = dfill < DE_TOL
    bgpix = np.concatenate([P[:, :5], P[:, -5:]], axis=1).reshape(-1, 3).astype(np.uint8)
    bgc = mode_color(bgpix)[0]
    wf = run_width(F, offs)
    res = {'n': len(smp), 'fill': hexc(fill), 'purity': round(purity, 2), 'bg': hexc(bgc)}
    if np.isfinite(wf).sum() >= 8:
        res['w_fill'] = round(float(np.nanmedian(wf)), 1)
    # Rand: erste Nicht-Füllfarbe aussen an der Füllung
    edge = []
    for i, row in enumerate(F):
        if not row[k0 - 2:k0 + 3].any():
            continue
        r = k0
        while r + 1 < len(row) and row[r + 1]:
            r += 1
        l = k0
        while l - 1 >= 0 and row[l - 1]:
            l -= 1
        for k in (l - 2, r + 2):
            if 0 <= k < len(row):
                edge.append(P[i, k])
    if len(edge) > 10:
        bc = mode_color(np.array(edge).astype(np.uint8))[0]
        if de(bc, fill) > DE_TOL and de(bc, bgc) > 10:
            Bm = de2000(Pl, np.broadcast_to(srgb_to_lab(np.array(bc)), Pl.shape)) < DE_TOL
            wt = []
            tol = 2
            for i, row in enumerate(F):
                cand = [k0 + d for d in sorted(range(-tol, tol + 1), key=abs) if row[k0 + d]]
                if not cand:
                    continue
                l = r = cand[0]
                while l - 1 >= 0 and row[l - 1]:
                    l -= 1
                while r + 1 < len(row) and row[r + 1]:
                    r += 1
                if (r - l) * 0.5 > 10:
                    continue
                l2, r2 = l, r
                while l2 - 1 >= 0 and Bm[i, l2 - 1]:
                    l2 -= 1
                while r2 + 1 < len(row) and Bm[i, r2 + 1]:
                    r2 += 1
                if l2 < l and r2 > r and l2 > 0 and r2 < len(row) - 1:
                    wt.append((r2 - l2 + 1) * 0.5)
            if len(wt) >= 8:
                res['border'] = hexc(bc)
                res['w_total'] = round(float(np.median(wt)), 1)
    if 'w_total' not in res and 'w_fill' in res:
        res['w_total'] = res['w_fill']
    res['contrast'] = round(max(de(fill, bgc), de(parse_hex(res['border']), bgc) if 'border' in res else 0), 1)
    return res


def dash_pattern(lab, fill, geoms, excl, W, H):
    """Strich/Lücke entlang der Geometrie: Füllfarbe innerhalb ±1 px quer zur Linie."""
    if fill is None:
        return None
    F = ndi.binary_dilation(color_near(lab, parse_hex(fill)), iterations=1)
    on_runs, off_runs = [], []
    total_on = total = 0
    for pts in geoms:
        seq = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            k = max(1, int(L / 0.5))
            for i in range(k):
                x = x0 + (x1 - x0) * i / k; y = y0 + (y1 - y0) * i / k
                xi, yi = int(round(x)), int(round(y))
                if not (0 <= xi < W and 0 <= yi < H) or excl[yi, xi]:
                    seq.append(None)
                else:
                    seq.append(bool(F[yi, xi]))
        run_v, run_n, started = None, 0, False
        for v in seq + [None]:
            if v is None:
                run_v, run_n, started = None, 0, False
                continue
            total += 1; total_on += v
            if v == run_v:
                run_n += 1
                continue
            if run_v is not None and started:
                (on_runs if run_v else off_runs).append(run_n * 0.5)
            started = run_v is not None
            run_v, run_n = v, 1
    if total < 80:
        return None
    frac_off = 1 - total_on / total
    res = {'anteil_luecke': round(frac_off, 2)}
    if frac_off < 0.12 or len(off_runs) < 3:
        res['art'] = 'durchgezogen'
    else:
        res['art'] = 'unterbrochen'
        res['strich_px'] = round(float(np.median(on_runs)), 1) if on_runs else 0
        res['luecke_px'] = round(float(np.median(off_runs)), 1)
    return res


def measure_area(rgb, mask, excl, median=False):
    inner = ndi.binary_erosion(mask, iterations=2) & ~excl
    if inner.sum() < 40:
        return None
    fill, purity = mode_color(rgb[inner])
    if median:      # Pixelkarte: Druckraster und Relief, der Modus ist dort zufällig
        fill = tuple(float(v) for v in np.median(rgb[inner], axis=0))
    return {'n': int(mask.sum()), 'fill': hexc(fill), 'purity': round(purity, 2)}


def order_at(rgb, lab, ma, mb, ca, cb, la_line=True, lb_line=True):
    ov = (ndi.binary_dilation(ma, iterations=1) if la_line else ma) & (ndi.binary_dilation(mb, iterations=1) if lb_line else mb)
    if ov.sum() < 6 or ca is None or cb is None:
        return None
    la = srgb_to_lab(np.array(parse_hex(ca), float)); lb = srgb_to_lab(np.array(parse_hex(cb), float))
    px = lab[ov]
    da = de2000(px, np.broadcast_to(la, px.shape)); db = de2000(px, np.broadcast_to(lb, px.shape))
    ok = np.minimum(da, db) < 25
    if ok.sum() < 4:
        return None
    return {'n': int(ok.sum()), 'a_oben': round(float((da[ok] < db[ok]).mean()), 2)}


# ------------------------------------------------------------------ Gesamtmasse
def ssim_gray(a, b):
    a = a.astype(float); b = b.astype(float)
    g = lambda x: ndi.gaussian_filter(x, 1.5)
    mu_a, mu_b = g(a), g(b)
    saa = g(a * a) - mu_a ** 2; sbb = g(b * b) - mu_b ** 2; sab = g(a * b) - mu_a * mu_b
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    s = ((2 * mu_a * mu_b + c1) * (2 * sab + c2)) / ((mu_a ** 2 + mu_b ** 2 + c1) * (saa + sbb + c2))
    return float(s.mean())


def hist_intersection(la, lb):
    def h(l):
        H, _ = np.histogramdd(l.reshape(-1, 3), bins=(10, 12, 12), range=((0, 100), (-60, 60), (-60, 60)))
        return H / H.sum()
    return float(np.minimum(h(la), h(lb)).sum())


def blur_de(ra, rb, sigma=3):
    fa = np.stack([ndi.gaussian_filter(ra[..., i].astype(float), sigma) for i in range(3)], -1)
    fb = np.stack([ndi.gaussian_filter(rb[..., i].astype(float), sigma) for i in range(3)], -1)
    return float(de2000(srgb_to_lab(fa), srgb_to_lab(fb)).mean())


def relief_corr(lab, relief_L, open_mask):
    a = ndi.gaussian_filter(lab[..., 0], 4)[open_mask]
    b = ndi.gaussian_filter(relief_L, 4)[open_mask]
    if len(a) < 500 or a.std() < 1e-6 or b.std() < 1e-6:
        return 0.0, 0.0
    r = float(np.corrcoef(a, b)[0, 1])
    slope = float(np.polyfit(b, a, 1)[0])
    return r, abs(slope) * float(b.std())


# ------------------------------------------------------------------ Beschriftung
def norm(t):
    t = unicodedata.normalize('NFKC', t or '').casefold()
    t = re.sub(r'\s+\d{3,4}(\s*m)?$', '', t)      # „Säntis 2502“ → „säntis“
    return re.sub(r'[\s\-‐.]', '', t)


def anno_colors():
    """Schriftfarbe je Annotationslayer und Regel ("Symbol" = '…') aus dem QGIS-Projekt."""
    s = open(os.path.join(C.SMV25_DIR, 'SMV25_qa.qgs'), encoding='utf-8').read()
    cols = {}
    for m in re.finditer(r'<maplayer[^>]*>(.*?)</maplayer>', s, re.S):
        body = m.group(1)
        name = re.search(r'<layername>([^<]*)', body).group(1)
        d = {}
        for r in re.finditer(r'<rule [^>]*filter="&quot;Symbol&quot; = \'([^\']*)\'"[^>]*>.*?textColor="(\d+),(\d+),(\d+)', body, re.S):
            d.setdefault(r.group(1), hexc([int(r.group(i)) for i in (2, 3, 4)]))
        c = re.search(r'textColor="(\d+),(\d+),(\d+)', body)
        if c:
            d[None] = hexc([int(c.group(i)) for i in (1, 2, 3)])
        cols[name] = d
    return cols


GARMIN_FONT_PX = {'SmallFont': 10, 'NormalFont': 12, 'LargeFont': 15}   # GPSMAP 66/67, unsicher


def labels_for(smv, nom, obj, grid, zoom, acol):
    res = {}
    allour = defaultdict(set)
    raw_by_type = defaultdict(list)
    for kind in ('points', 'lines', 'polygons'):
        for o in obj[kind]:
            if o[2]:
                allour[o[0]].add(norm(o[2]))
                raw_by_type[o[0]].append(o[2].strip())
    for key, name, layers, gtypes in K.LABELS:
        refn = {}
        sizes, ital, cols = [], [], Counter()
        for l in layers:
            for f, g in smv.features(l, None, grid):
                t = f.GetField('TEXTSTRING')
                if not t:
                    continue
                if re.fullmatch(r'\s*\d{3,4}\s*', t) and key not in ('kote', 'kurve'):
                    continue          # Höhenzahl an einem Namenpunkt → zählt bei den Höhenkoten
                refn.setdefault(norm(t), t)
                sizes.append(f.GetField('FONTSIZE') or 0)
                ital.append(int(f.GetField('ITALIC') or 0))
                lc = acol.get(l, {})
                try:
                    sym = f.GetField('Symbol')
                except Exception:
                    sym = None
                cols[lc.get(sym) or lc.get(None) or '#000000'] += 1
        ours = set()
        for t in gtypes:
            ours |= allour.get(t, set())
        ours.discard('')
        if not refn and not ours:
            continue
        anyour = set().union(*allour.values()) if allour else set()
        if key == 'kote':
            # Garmin speichert Höhen in Fuss (Style: ele|height:m=>ft), das Gerät zeigt Meter.
            def meters(lst):
                out = set()
                for o in lst:
                    mm = re.search(r'(\d{3,5})$', o)
                    if mm:     # Meter oder Fuss (Style-abhängig): beide Lesarten zulassen
                        v = int(mm.group(1))
                        out.add(v)
                        out.add(int(round(v * 0.3048)))
                return out
            om = set()
            for t in gtypes:
                om |= meters(raw_by_type.get(t, []))
            refm = {k: int(k) for k in refn if k.isdigit()}
            hitk = {k for k, v in refm.items() if any(abs(v - x) <= 1 for x in om)}
            hit = hit_cat = hitk
            ours = {str(x) for x in om}
            anyour = anyour | ours | hitk
        else:
            hit = set(refn) & anyour          # Name irgendwo in unserer Karte vorhanden
            hit_cat = set(refn) & ours        # … und beim passenden Garmin-Typ
        # TYP-Schrift der Garmin-Typen, die tatsächlich Namen tragen
        styles, tcols = Counter(), Counter()
        for t in gtypes:
            if not allour.get(t):
                continue
            sec = (nom.typ_point(t) if t.startswith('0x') and int(t, 16) >= 0x100 and key not in ('strasse', 'gewaesser', 'kurve')
                   else None) or nom.typ['line'].get(int(t, 16)) or nom.typ['polygon'].get(int(t, 16)) or {}
            styles[sec.get('FontStyle', 'SmallFont')] += len(allour[t])
            tcols[sec.get('DayCustomColor', '#000000').upper()] += len(allour[t])
        k = C.ZOOMS[zoom]['k'] * C.ZOOMS[zoom]['lk'] / 25000.0   # px je mm bei Referenzmassstab 1:25 000
        res[key] = {
            'name': name, 'ref_n': len(refn), 'ours_n': len(ours), 'treffer': len(hit),
            'anteil_vorhanden': round(len(hit) / len(refn), 2) if refn else None,
            'treffer_typ': len(hit_cat),
            'fehlend_beispiele': sorted(refn[k] for k in set(refn) - anyour)[:8],
            'ueberschuss_n': len(ours - set(refn)),
            'ref_pt_median': round(float(np.median(sizes)), 1) if sizes else None,
            'ref_px': round(float(np.median(sizes)) * 25.4 / 72.0 * k, 1) if sizes else None,
            'ref_kursiv': round(float(np.mean(ital)), 2) if ital else None,
            'ref_farbe': cols.most_common(1)[0][0] if cols else None,
            'ours_font': styles.most_common(1)[0][0] if styles else None,
            'ours_px': GARMIN_FONT_PX.get(styles.most_common(1)[0][0]) if styles else None,
            'ours_farbe': tcols.most_common(1)[0][0] if tcols else None,
        }
    return res


# ------------------------------------------------------------------ Hauptlauf
def run():
    smv = SMV()
    nom = Nominal()
    ovl_typ = {name: typ for name, d, typ in C.OVERLAYS}
    acol = anno_colors()
    # DEM-Subdateien (Geräteschummerung): render_img.py zeichnet sie nicht, hier nur Bestand
    import glob as _glob
    spec = importlib.util.spec_from_file_location('render_img', C.RENDER_IMG)
    rimg = importlib.util.module_from_spec(spec); spec.loader.exec_module(rimg)
    dem = {'kacheln': 0, 'mit_dem': 0, 'dem_bytes': 0}
    for f in sorted(_glob.glob(os.path.join(C.IMG_DIR, '7*.img'))):
        if f.endswith('0000.img') or '_mdr' in f:
            continue
        files = rimg.read_imgfs(open(f, 'rb').read())
        dem['kacheln'] += 1
        d_ = [v for k, v in files.items() if k.endswith('.DEM')]
        if d_:
            dem['mit_dem'] += 1; dem['dem_bytes'] += sum(len(v) for v in d_)
    results = {'config': {'device_dpi': C.DEVICE_DPI, 'zooms': C.ZOOMS, 'cutouts': C.CUTOUTS, 'target': C.TARGET,
                          'typ': C.TYP_TXT, 'img_dir': C.IMG_DIR, 'render_img': C.RENDER_IMG,
                          'overlays': C.OVERLAYS, 'dem': dem},
               'cases': {}}
    for cut in C.CUTOUTS:
        for zk, z in C.ZOOMS.items():
            grid = C.grid(cut, zk)
            W, H = grid[4], grid[5]
            d = os.path.join(C.OUT, cut, zk)
            dr = os.path.join(C.REF_OUT, cut, zk)
            obj = json.load(open(os.path.join(d, 'ours_objects.json')))
            imgs = {'ours': os.path.join(d, 'ours_nolabel.png')}
            for r in z['refs']:
                p = os.path.join(dr, 'ref_%s_nolabel.png' % r) if r == 'smv25' else os.path.join(dr, 'ref_%s.png' % r)
                if os.path.exists(p):
                    imgs[r] = p
            loaded = {k: lab_img(p) for k, p in imgs.items()}
            case = {'classes': {}, 'order': {}, 'global': {}, 'labels': {}, 'symbols': {}}

            # Masken
            masks = {}
            for kind, lst in (('line', K.LINES), ('area', K.AREAS)):
                for key, name, layer, where, gtypes in lst:
                    rg, cats = smv.geoms_px(layer, where, grid)
                    og = ours_geoms(obj, gtypes, kind)
                    masks[key] = {'kind': kind, 'name': name, 'layer': layer, 'gtypes': gtypes, 'cats': cats,
                                  'ref_geoms': rg, 'ours_geoms': og,
                                  'ref': draw_mask(rg, kind, W, H), 'ours': draw_mask(og, kind, W, H)}
            lines_ref = np.zeros((H, W), bool); lines_ours = np.zeros((H, W), bool)
            for m in masks.values():
                if m['kind'] == 'line':
                    lines_ref |= m['ref']; lines_ours |= m['ours']
            bld_ref, bld_ours = masks['gebaeude']['ref'], masks['gebaeude']['ours']

            for key, m in masks.items():
                entry = {'name': m['name'], 'kind': m['kind'], 'gtypes': m['gtypes'],
                         'ref_len_px' if m['kind'] == 'line' else 'ref_area_px': int(m['ref'].sum()),
                         'ours_len_px' if m['kind'] == 'line' else 'ours_area_px': int(m['ours'].sum())}
                # Länge bzw. Fläche je Garmin-Typ (welcher Typ ist in dieser Stufe sichtbar?)
                tl = Counter()
                okey = 'lines' if m['kind'] == 'line' else 'polygons'
                for o in obj[okey]:
                    if o[0] in m['gtypes']:
                        pts = o[1]
                        tl[o[0]] += sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])) \
                            if m['kind'] == 'line' else 1
                entry['ours_typ'] = dict(tl)
                entry['cats'] = dict(m['cats'])
                entry['layer'] = m['layer']
                if m['kind'] == 'line':
                    entry['soll'] = nom.smv(m['layer'], m['cats'])
                    # typ_code nur, wenn der Typ in diesem Ausschnitt wirklich gezeichnet wird
                    entry['typ_code'] = next((t for t, _ in tl.most_common() if nom.typ_line(t)), None)
                    t0 = entry['typ_code'] or next((t for t in m['gtypes'] if nom.typ_line(t)), None)
                    entry['typ'] = nom.typ_line(t0) if t0 else None
                else:
                    entry['soll'] = nom.smv(m['layer'], m['cats'])
                    entry['typ'] = next((nom.typ_poly(t) for t in m['gtypes'] if nom.typ_poly(t)), None)
                for src, (rgb, lab) in loaded.items():
                    own = 'ours' if src == 'ours' else 'ref'
                    mk = m[own]
                    if m['kind'] == 'line':
                        others = (lines_ours if own == 'ours' else lines_ref) & ~mk
                        excl = ndi.binary_dilation(others | (bld_ours if own == 'ours' else bld_ref), iterations=3)
                        r = measure_line(rgb, lab, mk, excl, m['%s_geoms' % own])
                        if r and r.get('fill') and src in ('ours', 'smv25'):
                            r['muster'] = dash_pattern(lab, r['fill'], m['%s_geoms' % own], excl, W, H)
                    else:
                        excl = ndi.binary_dilation((lines_ours if own == 'ours' else lines_ref), iterations=2)
                        if key != 'gebaeude':
                            excl |= (bld_ours if own == 'ours' else bld_ref)
                        r = measure_area(rgb, mk, excl, median=src.startswith('smr'))
                    if r:
                        entry[src] = r
                case['classes'][key] = entry

            # Zeichenreihenfolge
            for a, b in K.ORDER_PAIRS:
                e = {}
                for src, (rgb, lab) in loaded.items():
                    if src not in ('ours', 'smv25', 'smr25'):
                        continue
                    own = 'ours' if src == 'ours' else 'ref'
                    ca = case['classes'][a].get(src, {}).get('fill') or case['classes'][a].get('smv25', {}).get('fill')
                    cb = case['classes'][b].get(src, {}).get('fill') or case['classes'][b].get('smv25', {}).get('fill')
                    r = order_at(rgb, lab, masks[a][own], masks[b][own], ca, cb,
                                 masks[a]['kind'] == 'line', masks[b]['kind'] == 'line')
                    if r:
                        e[src] = r
                if e:
                    case['order']['%s>%s' % (a, b)] = e

            # Gesamtmasse
            relief = os.path.join(dr, 'relief_komb.png')
            rel_L = srgb_to_lab(np.array(Image.open(relief).convert('RGB')))[..., 0] if os.path.exists(relief) else None
            open_ref = ~ndi.binary_dilation(lines_ref | bld_ref | masks['wald']['ref'] | masks['see']['ref'], iterations=3)
            full = {k: lab_img(os.path.join(d, 'ours.png') if k == 'ours' else os.path.join(dr, 'ref_%s.png' % k)) for k in loaded}
            for src, (rgb, lab) in full.items():
                g = {}
                if rel_L is not None:
                    r, dl = relief_corr(lab, rel_L, open_ref)
                    g['relief_r'] = round(r, 2); g['relief_dL'] = round(dl, 1)
                if src != 'ours':
                    o_rgb, o_lab = full['ours']
                    g['ssim'] = round(ssim_gray(lab[..., 0], o_lab[..., 0]), 3)
                    g['de_blur'] = round(blur_de(rgb, o_rgb), 1)
                    g['hist'] = round(hist_intersection(lab, o_lab), 3)
                case['global'][src] = g
            if 'smv25' in full and 'smr25' in full:
                case['global']['smv25_vs_smr25'] = {
                    'ssim': round(ssim_gray(full['smv25'][1][..., 0], full['smr25'][1][..., 0]), 3),
                    'de_blur': round(blur_de(full['smv25'][0], full['smr25'][0]), 1),
                    'hist': round(hist_intersection(full['smv25'][1], full['smr25'][1]), 3)}

            # Beschriftung (nur wo SMV25 Referenz ist)
            if 'smv25' in z['refs']:
                case['labels'] = labels_for(smv, nom, obj, grid, zk, acol)

            # Symbole
            for key, name, layer, where, gtypes in K.SYMBOLS:
                n_ref = len(smv.features(layer, where, grid))
                n_ours = sum(1 for o in obj['points'] if o[0] in gtypes) + \
                    sum(1 for o in obj['polygons'] if o[0] in gtypes)
                if n_ref or n_ours:
                    case['symbols'][key] = {'name': name, 'ref_n': n_ref, 'ours_n': n_ours}

            # Typen in der IMG ohne TYP-Definition (render_img zeichnet sie magenta, das Gerät nach Vorgabe)
            unk = Counter()
            for kind, sec in (('points', 'point'), ('lines', 'line'), ('polygons', 'polygon')):
                for o in obj[kind]:
                    if len(o) > 3 and o[3] != 'basis' and ovl_typ.get(o[3]) != C.TYP_TXT:
                        continue      # Overlay mit eigener TYP
                    if int(o[0], 16) not in nom.typ[sec]:
                        unk['%s %s' % (sec, o[0])] += 1
            case['unbekannte_typen'] = dict(unk)
            results['cases']['%s/%s' % (cut, zk)] = case
            print('gemessen', cut, zk)
    json.dump(results, open(C.path('results.json'), 'w'), indent=1, ensure_ascii=False)
    return results


if __name__ == '__main__':
    run()
