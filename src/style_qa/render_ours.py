"""Unsere Karte rendern: src/style/tools/render_img.py, auf das LV95-Zielraster.

    python -I src/style_qa/render_ours.py [--force] [--night] [--cut CUT] [--zoom Z]

render_img.py zeichnet nur eine Kachel. Hier werden alle Kacheln eines IMG-Ordners gelesen, die
Objekte der passenden Ebene zusammengeführt und render_img.main() mit einer Ersatz-Kachel
aufgerufen. Die Zeichenlogik (Farben, Breiten, Muster, Reihenfolge, Schrift) bleibt die von
render_img.py; dessen Datei wird nicht geändert.

Ebenen (wie am Gerät mit mehreren aktiven Karten): Basiskarte 7701 (C.IMG_DIR, C.TYP_TXT), darüber
die Overlays aus C.OVERLAYS (z. B. Höhenlinien 7703). Overlays werden ohne Beschriftung gezeichnet
(render_img beschriftet Höhenkurven in Fuss) und deckend über die Basiskarte gelegt, wie Garmin
transparente Overlays über die Basiskarte legt.

render_img.py zeichnet in Plattkarte (Länge × cos(Breite)). Das Bild wird darum als EPSG:4326
georeferenziert und mit gdal.Warp (nearest, damit Linienbreiten erhalten bleiben) auf das
LV95-Raster aus config.grid() gebracht.

Zusätzlich: ours_objects.json mit allen Objekten im Ausschnitt (Typ, Pixelkoordinaten im
Zielraster, Beschriftung, Ebene) für die Masken in measure.py.
"""
import argparse
import glob
import importlib.util
import json
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

from osgeo import gdal, osr  # noqa: E402

gdal.UseExceptions()
UNIT = 360.0 / (1 << 24)
PAD = 40           # Rand in render_img.main
BG_DAY = (252, 252, 252)


def load_renderer():
    spec = importlib.util.spec_from_file_location('render_img', C.RENDER_IMG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Merged:
    """Ersatz für render_img.Tile: mehrere Kacheln, gefiltert auf eine Box (Karteneinheiten).

    Je Kachel wird die Ebene gewählt, die das Gerät bei der verlangten Auflösung zeigt: die mit
    der kleinsten Bitzahl ≥ Auflösung (mkgmap-Ebenen gelten bis zur nächstgröberen).
    """

    def __init__(self, tiles, box, res):
        self.tiles = tiles
        self.box = box
        self.res = res
        self.levels = [{'level': 0, 'bits': res, 'ndiv': 0}]

    def objects(self, li=0):
        x0, y0, x1, y1 = self.box
        P, L, G = [], [], []

        def inside(cs):
            xs = [c[0] for c in cs]
            ys = [c[1] for c in cs]
            return not (max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1)
        for t in self.tiles:
            cand = [k for k, lv in enumerate(t.levels) if lv['bits'] >= self.res]
            if not cand:
                continue
            lj = min(cand, key=lambda k: t.levels[k]['bits'])
            # Ebene ohne Unterteilungen (leere Oberebene) überspringen
            pts, lines, polys = t.objects(lj)
            P += [p for p in pts if x0 <= p[1] <= x1 and y0 <= p[2] <= y1]
            L += [l for l in lines if l[1] and inside(l[1])]
            G += [g for g in polys if g[1] and inside(g[1])]
        return P, L, G


_tiles_cache = {}


def tiles(mod, img_dir):
    if img_dir not in _tiles_cache:
        files = sorted(f for f in glob.glob(os.path.join(img_dir, '7*.img'))
                       if not os.path.basename(f).endswith('0000.img') and '_mdr' not in f)
        ts = []
        for f in files:
            try:
                ts.append(mod.Tile(mod.read_imgfs(open(f, 'rb').read())))
            except Exception as e:
                print('übersprungen', f, e)
        _tiles_cache[img_dir] = ts
    return _tiles_cache[img_dir]


def transforms():
    s = osr.SpatialReference(); s.ImportFromEPSG(2056)
    t = osr.SpatialReference(); t.ImportFromEPSG(4326)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    t.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return osr.CoordinateTransformation(s, t), osr.CoordinateTransformation(t, s)


def draw_layer(mod, merged, typ, raw, bits, scale, bbox, night, labels):
    orig_tile, orig_read = mod.Tile, mod.read_imgfs
    mod.Tile = lambda files: merged
    mod.read_imgfs = lambda data: None
    argv = sys.argv
    sys.argv = ['render_img.py', C.RENDER_IMG, typ, raw, '--res', str(bits), '--scale', '%.6f' % scale,
                '--bbox', ','.join('%.6f' % v for v in bbox), '--labels', labels] + (['--night'] if night else [])
    try:
        mod.main()
    finally:
        sys.argv = argv
        mod.Tile, mod.read_imgfs = orig_tile, orig_read


def render(mod, cut, zk, night=False, force=False, labels='all'):
    z = C.ZOOMS[zk]
    e0, n0, e1, n1, W, H, mpx = C.grid(cut, zk)
    suffix = ('_nacht' if night else '') + ('' if labels == 'all' else '_nolabel')
    out = C.path(cut, zk, 'ours%s.png' % suffix)
    if os.path.exists(out) and not force:
        return out
    fwd, inv = transforms()
    corners = [fwd.TransformPoint(e, n)[:2] for e in (e0, e1) for n in (n0, n1)]
    lons = [c[0] for c in corners]; lats = [c[1] for c in corners]
    m = 0.002
    bbox = (min(lons) - m, min(lats) - m, max(lons) + m, max(lats) + m)
    bits = z['res']
    m_per_unit_lat = UNIT * 111132.954       # Meter je Karteneinheit in Nord-Süd-Richtung
    scale = m_per_unit_lat * (1 << (24 - bits)) / mpx
    box = tuple(v / UNIT for v in bbox)

    layers = [('basis', C.IMG_DIR, C.TYP_TXT, labels)] + \
             [(name, d, t, 'none') for name, d, t in C.OVERLAYS if os.path.isdir(d)]
    composite = None
    objects = {'points': [], 'lines': [], 'polygons': []}
    for name, img_dir, typ, lab in layers:
        merged = Merged(tiles(mod, img_dir), box, bits)
        raw = C.path(cut, zk, '_raw_%s%s.png' % (name, suffix))
        draw_layer(mod, merged, typ, raw, bits, scale, bbox, night, lab)
        im = np.array(Image.open(raw).convert('RGB'))
        os.remove(raw)
        if composite is None:
            composite = im
        else:
            bg = BG_DAY if not night else (24, 26, 32)
            body = np.any(im != np.array(bg, np.uint8), axis=-1)
            body[-30:, :] = False                         # Fusszeile von render_img
            composite[body] = im[body]
        if not night and labels == 'all':
            pts, lines, polys = merged.objects()

            def px(c):
                e, n = inv.TransformPoint(c[0] * UNIT, c[1] * UNIT)[:2]
                return [round((e - e0) / mpx, 2), round((n1 - n) / mpx, 2)]
            objects['points'] += [[hex(p[0]), px((p[1], p[2])), p[3], name] for p in pts]
            objects['lines'] += [[hex(l[0]), [px(c) for c in l[1]], l[2], name] for l in lines]
            objects['polygons'] += [[hex(g[0]), [px(c) for c in g[1]], g[2], name] for g in polys]

    # Geometrie von render_img.main nachrechnen
    x0, y0, x1, y1 = box
    kx = math.cos(math.radians((y0 + y1) / 2 * UNIT))
    f = scale / (1 << (24 - bits))
    gt = (bbox[0] - PAD * UNIT / (kx * f), UNIT / (kx * f), 0, bbox[3] + PAD * UNIT / f, 0, -UNIT / f)
    tmp = C.path(cut, zk, '_comp%s.png' % suffix)
    Image.fromarray(composite).save(tmp)
    mem = gdal.Translate('/vsimem/o.tif', tmp, format='GTiff', outputSRS='EPSG:4326')
    mem.SetGeoTransform(gt)
    mem = None
    gdal.Warp(out + '.tif', '/vsimem/o.tif', dstSRS='EPSG:2056', outputBounds=(e0, n0, e1, n1),
              width=W, height=H, resampleAlg='near')
    gdal.Translate(out, out + '.tif', format='PNG', bandList=[1, 2, 3])
    os.remove(out + '.tif'); os.remove(tmp)
    gdal.Unlink('/vsimem/o.tif')
    for x in glob.glob(out + '.aux.xml') + glob.glob(tmp + '.aux.xml'):
        os.remove(x)
    if not night and labels == 'all':
        objects['layers'] = [l[:3] for l in layers]
        json.dump(objects, open(C.path(cut, zk, 'ours_objects.json'), 'w'))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--night', action='store_true')
    ap.add_argument('--cut')
    ap.add_argument('--zoom')
    a = ap.parse_args()
    mod = load_renderer()
    for cut in C.CUTOUTS:
        if a.cut and cut != a.cut:
            continue
        for zk in C.ZOOMS:
            if a.zoom and zk != a.zoom:
                continue
            print('ok', render(mod, cut, zk, force=a.force))
            print('ok', render(mod, cut, zk, force=a.force, labels='none'))
            if a.night:
                print('ok', render(mod, cut, zk, night=True, force=a.force))


if __name__ == '__main__':
    main()
