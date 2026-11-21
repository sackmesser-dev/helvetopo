"""Referenzbilder erzeugen: SMV25 (offizielles QGIS-Projekt) und Swiss Map Raster 25/50/100.

    python -I src/style_qa/refs.py [--only smv25|smr] [--force]

Ausgabe: work/style_qa/<ausschnitt>/<zoom>/ref_smv25.png, ref_smr25.png, ref_smr50.png, ...
Alle Bilder liegen auf dem Raster aus config.grid().
"""
import argparse
import glob
import json
import re
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402

from osgeo import gdal  # noqa: E402

gdal.UseExceptions()


def project_copy():
    """Kopie des SMV25-Projekts neben dem zusammengeführten GeoPackage.

    Änderungen gegenüber dem Original: Raster als VRT (4 Blätter), Werte der 1-Bit-Raster
    umgekehrt. Die Schrift „Liberation Sans Narrow“ ersetzt render_ref_qgis.py zur Laufzeit durch
    „Arial Narrow“ (metrisch gleich, unter macOS vorhanden).
    """
    dst = os.path.join(C.SMV25_DIR, 'SMV25_qa.qgs')
    if os.path.exists(dst) and os.path.getmtime(dst) > os.path.getmtime(C.QGS_ORIG):
        return dst
    s = open(C.QGS_ORIG, encoding='utf-8').read()
    for r in ('KOMB', 'FELS', 'GEROELL', 'GLET'):
        s = s.replace('SMV25_CHLV95LN02_RASTER/%s.tif' % r, 'SMV25_CHLV95LN02_RASTER/%s.vrt' % r)
    # 1-Bit-Raster FELS/GEROELL/GLET der STAC-Lieferung: 0 = Objekt, 1 = leer (min-is-black).
    # Das Projekt erwartet 1 = Objekt; ohne Umkehr wird das ganze Blatt gletscherblau.
    s = re.sub(r'<item label="0" value="0" alpha="0" color="#ffffff"/>(\s*)<item label="1" value="1" alpha="255" color="(#[0-9a-f]{6})"/>',
               r'<item label="0" value="0" alpha="255" color="\2"/>\1<item label="1" value="1" alpha="0" color="#ffffff"/>', s)
    open(dst, 'w', encoding='utf-8').write(s)
    return dst


def smv25(force=False):
    """Zwei Varianten: vollständig (wie LK) und ohne Annotationen (für Farb-/Breitenmessung)."""
    variants = {'ref_smv25.png': ['T28_DKM25_KOORDINATENNETZLINIE'],
                'ref_smv25_nolabel.png': ['T28_DKM25_KOORDINATENNETZLINIE', '_ANNO']}
    for fname, exclude in variants.items():
        jobs = []
        for cut in C.CUTOUTS:
            for zk, z in C.ZOOMS.items():
                if 'smv25' not in z['refs']:
                    continue
                e0, n0, e1, n1, w, h, mpx = C.grid(cut, zk)
                out = C.ref_path(cut, zk, fname)
                if os.path.exists(out) and not force:
                    continue
                jobs.append({'extent': [e0, n0, e1, n1], 'w': w, 'h': h, 'dpi': z['dpi'], 'out': out})
        if not jobs:
            continue
        cfg = {'qgs': project_copy(), 'exclude': exclude, 'jobs': jobs}
        jf = C.ref_path('_jobs_%s.json' % fname[:-4])
        json.dump(cfg, open(jf, 'w'), indent=1)
        r = subprocess.run([os.path.join(C.HERE, 'qgis_python.sh'), os.path.join(C.HERE, 'render_ref_qgis.py'), jf],
                           capture_output=True, text=True)
        print('\n'.join(l for l in r.stdout.splitlines() if l.startswith(('ok', 'Layer'))))
        if r.returncode:
            print(r.stderr[-3000:], file=sys.stderr)
            raise SystemExit('QGIS-Rendering fehlgeschlagen')


def smr_vrt(kind):
    folder = {'smr25': 'pk25', 'smr50': 'pk50', 'smr100': 'pk100'}[kind]
    vrt = C.ref_path('_' + kind + '.vrt')
    tifs = sorted(glob.glob(os.path.join(C.SMR_DIR, folder, '*.tif')))
    if not os.path.exists(vrt):
        gdal.BuildVRT(vrt, tifs)
    return vrt


def warp_to_grid(src, out, cut, zk, resample=None):
    e0, n0, e1, n1, w, h, mpx = C.grid(cut, zk)
    srcres = abs(gdal.Info(src, format='json')['geoTransform'][1])
    if resample is None:
        resample = 'average' if mpx > srcres * 1.2 else 'cubic'
    tmp = out + '.tif'
    gdal.Warp(tmp, src, dstSRS='EPSG:2056', outputBounds=(e0, n0, e1, n1), width=w, height=h,
              resampleAlg=resample, dstNodata=None, format='GTiff', outputType=gdal.GDT_Byte)
    ds = gdal.Open(tmp)
    if ds.RasterCount == 1 and ds.GetRasterBand(1).GetColorTable() is not None:
        gdal.Translate(out, tmp, format='PNG', rgbExpand='rgb')
    else:
        gdal.Translate(out, tmp, format='PNG', bandList=[1, 2, 3][:ds.RasterCount])
    ds = None
    os.remove(tmp)
    for x in glob.glob(out + '.aux.xml'):
        os.remove(x)


def smr(force=False):
    for cut in C.CUTOUTS:
        for zk, z in C.ZOOMS.items():
            for kind in z['refs']:
                if not kind.startswith('smr'):
                    continue
                out = C.ref_path(cut, zk, 'ref_%s.png' % kind)
                if os.path.exists(out) and not force:
                    continue
                src = smr_vrt(kind)
                ds = gdal.Open(src)
                pal = ds.GetRasterBand(1).GetColorTable() is not None
                ds = None
                rgb = src
                if pal:   # Paletten-TIFF: erst nach RGB, dann mitteln (sonst mittelt GDAL Indizes)
                    rgb = C.ref_path('_%s_rgb.vrt' % kind)
                    if not os.path.exists(rgb):
                        gdal.Translate(rgb, src, format='VRT', rgbExpand='rgb')
                warp_to_grid(rgb, out, cut, zk)
                print('ok', out)


def hillshade(force=False):
    """Relief der SMV25 (KOMB-Raster) auf jedes Zielraster, für die Schummerungs-Messung."""
    src = os.path.join(C.SMV25_DIR, 'SMV25_CHLV95LN02_RASTER', 'KOMB.vrt')
    for cut in C.CUTOUTS:
        for zk in C.ZOOMS:
            out = C.ref_path(cut, zk, 'relief_komb.png')
            if os.path.exists(out) and not force:
                continue
            e0, n0, e1, n1, w, h, mpx = C.grid(cut, zk)
            tmp = out + '.tif'
            gdal.Warp(tmp, src, dstSRS='EPSG:2056', outputBounds=(e0, n0, e1, n1), width=w, height=h,
                      resampleAlg='average')
            ds = gdal.Open(tmp)
            if ds.GetRasterBand(1).GetColorTable() is not None:
                gdal.Translate(out, tmp, format='PNG', rgbExpand='rgb')
            else:
                gdal.Translate(out, tmp, format='PNG', bandList=list(range(1, min(3, ds.RasterCount) + 1)))
            ds = None
            os.remove(tmp)
            for x in glob.glob(out + '.aux.xml'):
                os.remove(x)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', choices=('smv25', 'smr', 'relief'))
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    if a.only in (None, 'smr'):
        smr(a.force)
    if a.only in (None, 'relief'):
        hillshade(a.force)
    if a.only in (None, 'smv25'):
        smv25(a.force)
