#!/usr/bin/env python3
"""Farben und Linienarten aus der swisstopo-QGIS-Projektdatei (SMV25-Hilfsdateien) auslesen.

Aufruf:
    python3 -I extract_qgs_symbology.py <SMV25_CHLV95LN02.qgs> > symbology.tsv

Ausgabe (TSV): layer, kategorie, symbol-layer-nr, klasse, farbe, randfarbe,
breite_mm, randbreite_mm, linienstil, dash, zusatz
Die Projektdatei ist OGD-Hilfsmaterial von swisstopo (Download auf der SMV25-Produktseite).
"""
import sys
import xml.etree.ElementTree as ET


def props(layer_el):
    """Eigenschaften eines symbol layer als dict (QGIS 3.x: <Option> oder <prop>)."""
    d = {}
    for p in layer_el.findall('prop'):
        d[p.get('k')] = p.get('v')
    opt = layer_el.find('Option')
    if opt is not None:
        for o in opt.findall('Option'):
            if o.get('name') and o.get('value') is not None:
                d.setdefault(o.get('name'), o.get('value'))
    return d


def hexcol(v):
    if not v:
        return ''
    parts = v.split(',')
    try:
        r, g, b = (int(x) for x in parts[:3])
        a = int(parts[3]) if len(parts) > 3 else 255
    except ValueError:
        return v
    if a == 0:
        return 'none'
    return '#%02X%02X%02X' % (r, g, b) + ('' if a == 255 else '@%d' % a)


def walk_symbol(sym, prefix=''):
    """Liefert alle (Pfad, symbol layer) eines Symbols, auch verschachtelte Subsymbole."""
    out = []
    for i, sl in enumerate(sym.findall('layer')):
        out.append((prefix + str(i), sl))
        for sub in sl.findall('symbol'):
            out.extend(walk_symbol(sub, prefix + str(i) + '.'))
    return out


def main(path):
    root = ET.parse(path).getroot()
    print('\t'.join(['layer', 'kategorie', 'sl', 'klasse', 'farbe', 'rand', 'breite',
                     'randbreite', 'stil', 'dash', 'zusatz']))
    for ml in root.iter('maplayer'):
        name = (ml.findtext('layername') or '').strip()
        rend = ml.find('renderer-v2')
        if rend is None:
            continue
        symbols = {}
        syms = rend.find('symbols')
        if syms is not None:
            for s in syms.findall('symbol'):
                symbols[s.get('name')] = s
        cats = []
        if rend.get('type') == 'categorizedSymbol':
            for c in rend.find('categories').findall('category'):
                cats.append((c.get('label'), c.get('symbol')))
        elif rend.get('type') == 'RuleRenderer':
            for r in rend.iter('rule'):
                if r.get('symbol'):
                    cats.append((r.get('label') or r.get('filter'), r.get('symbol')))
        else:
            cats = [('(alle)', k) for k in symbols]
        for label, key in cats:
            sym = symbols.get(key)
            if sym is None:
                continue
            for slpath, sl in walk_symbol(sym):
                p = props(sl)
                cls = sl.get('class')
                col = p.get('color') or p.get('line_color') or ''
                rand = p.get('outline_color') or ''
                width = p.get('line_width') or p.get('width') or p.get('size') or ''
                owidth = p.get('outline_width') or ''
                style = p.get('line_style') or p.get('style') or p.get('outline_style') or ''
                dash = p.get('customdash') if p.get('use_custom_dash') == '1' else ''
                extra = []
                for k in ('name', 'chr', 'font', 'interval', 'placement', 'offset', 'angle',
                          'distance', 'imageFile'):
                    if p.get(k) not in (None, '', '0', '0,0'):
                        extra.append('%s=%s' % (k, p[k]))
                print('\t'.join([name, label or '', slpath, cls or '', hexcol(col), hexcol(rand),
                                 width, owidth, style, dash or '', ' '.join(extra)]))


if __name__ == '__main__':
    main(sys.argv[1])
