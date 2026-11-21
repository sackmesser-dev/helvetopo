"""Bericht aus results.json: priorisierte Abweichungsliste, Tabellen, Nebeneinander-Bilder.

    python -I src/style_qa/report.py   → work/style_qa/report.md, work/style_qa/vergleich/*.png

Wirkung (Spalte „Wirkung“) = Anteil der betroffenen Bildpixel × Farbunterschied (ΔE2000),
in „ΔE·%“: 1,0 heisst z. B. 1 % der Bildfläche weicht um ΔE 100 ab oder 10 % um ΔE 10.
Gemittelt über die Ausschnitte und Zoomstufen 1:12 500 und 1:25 000 (SMV25 als Referenz);
1:50 000 und 1:100 000 gehen über die Gesamtmasse und die Flächenfarben gegen SMR50/100 ein.
"""
import datetime
import glob
import hashlib
import json
import os
import sys
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as C  # noqa: E402
from measure import de, parse_hex, srgb_to_lab, de2000, Nominal  # noqa: E402
from collections import Counter  # noqa: E402

N = C.W * C.H
PX_MM = C.MM_PER_PX
MAIN_ZOOMS = ('z12k', 'z25k')

LIMITS = {
    'kursiv': 'TYP legt weder Schriftart noch Kursivschrift fest; das Gerät nutzt seine eigene Schrift.',
    'schriftgroesse': 'TYP kennt nur Small/Normal/Large, keine Punktgrösse.',
    'relief': 'Eine Vektor-IMG kann keine Rasterschummerung enthalten. Möglich ist die Geräteschummerung '
              'über DEM (mkgmap --dem); Helligkeit und Lichtrichtung bestimmt das Gerät.',
    'breite_zoom': 'TYP-Breiten sind feste Gerätepixel in allen Zoomstufen; die LK-Breite in mm passt nur bei einer Stufe.',
    'linienfolge': 'Die Reihenfolge von Linien ist in TYP nicht einstellbar ([_drawOrder] gilt nur für Flächen); '
                   'Garmin zeichnet Linien nach Typ bzw. Datenreihenfolge (unsicher). Overlays liegen über der Basiskarte.',
    'subpixel': 'Unter 1 Gerätepixel (0,16 mm) geht nicht; dünnere LK-Linien werden 1 px.',
    'platzierung': 'Beschriftungen platziert das Gerät selbst (keine Annotationen, keine Freistellung).',
    'muster': 'Linienmuster sind 32 px lang, 2 Farben; Flächenmuster 32×32 px, 2 Farben.',
}


def mm2px(mm):
    return mm / PX_MM


def fmt(v, nd=1):
    if v is None:
        return '–'
    if isinstance(v, float):
        return ('%.*f' % (nd, v)).replace('.', ',')
    return str(v)


def dash_mm(dash):
    """'2.99861;0.299861;0' → (strich, lücke) in mm"""
    if not dash:
        return None
    v = [float(x) for x in dash.split(';') if x.strip()]
    if len(v) >= 2 and v[1] > 0:
        return v[0], v[1]
    return None


def typ_dash(muster):
    """TYP-Musterzeile 'xxx..xxx...' → Median Strich/Lücke in px, None wenn durchgezogen."""
    if not isinstance(muster, str) or '.' not in muster:
        return None
    s = muster
    runs = []
    cur, n = s[0], 0
    for ch in s + s[0]:
        if ch == cur:
            n += 1
        else:
            runs.append((cur, n)); cur, n = ch, 1
    on = [n for c, n in runs if c == 'x']
    off = [n for c, n in runs if c == '.']
    if not on or not off:
        return None
    return float(np.median(on)), float(np.median(off))


def style_version():
    h = hashlib.sha1(open(C.TYP_TXT, 'rb').read()).hexdigest()[:10]
    st = os.path.join(C.STYLE_ROOT, 'src', 'style', 'swisstopo')
    for f in sorted(glob.glob(os.path.join(st, '*'))):
        if os.path.isfile(f):
            h = hashlib.sha1((h + hashlib.sha1(open(f, 'rb').read()).hexdigest()).encode()).hexdigest()[:10]
    imgs = sorted(glob.glob(os.path.join(C.IMG_DIR, '7*.img')))
    mt = max(os.path.getmtime(f) for f in imgs) if imgs else 0
    return {'hash': h, 'typ': C.TYP_TXT, 'img_dir': C.IMG_DIR,
            'img_stand': datetime.datetime.fromtimestamp(mt).strftime('%Y-%m-%d %H:%M')}


# ------------------------------------------------------------------ Befunde
def findings(R):
    F = []
    cases = R['cases']
    main_cases = {k: v for k, v in cases.items() if k.split('/')[1] in MAIN_ZOOMS}
    nmain = max(1, len(main_cases))

    # --- Klassen
    agg = defaultdict(lambda: defaultdict(list))
    info = {}
    for ck, c in main_cases.items():
        for key, e in c['classes'].items():
            info.setdefault(key, e)
            if e.get('soll') and e['soll'].get('fill') and not (info[key].get('soll') or {}).get('fill'):
                info[key] = e
            a = agg[key]
            a['n_ref'].append(e.get('ref_len_px', e.get('ref_area_px', 0)))
            a['n_ours'].append(e.get('ours_len_px', e.get('ours_area_px', 0)))
            a['cases'].append(ck)
            for src in ('ours', 'smv25', 'smr25'):
                if src in e:
                    a['m_' + src].append(e[src])
    nom = Nominal()
    cats = defaultdict(Counter)
    for c in main_cases.values():
        for key, e in c['classes'].items():
            cats[key].update(e.get('cats') or {})
    for key, a in agg.items():
        e = info[key]
        # Soll = häufigste SMV25-Kategorie über alle Ausschnitte
        soll = (nom.smv(e['layer'], cats[key]) if e.get('layer') and cats[key] else e.get('soll')) or {}
        typ = e.get('typ') or {}
        name = e['name']
        gt = '/'.join(e['gtypes'])
        kind = e['kind']
        ref_share = float(np.sum(a['n_ref'])) / (N * nmain)
        ours_share = float(np.sum(a['n_ours'])) / (N * nmain)
        if ref_share == 0 and ours_share == 0:
            continue
        typword = 'TYP-Linie' if kind == 'line' else 'TYP-Fläche'
        meas_ours = a['m_ours']
        smr = a['m_smr25']
        smr_fill = smr[0].get('fill') if smr else None

        # fehlt ganz
        if ref_share > 0 and float(np.sum(a['n_ours'])) == 0:
            col = soll.get('fill') or '#000000'
            w = mm2px(soll.get('w_total_mm', 0.15)) if kind == 'line' else 1
            impact = ref_share * max(1, w) * de(parse_hex(col), (255, 255, 255)) * 100 / 100
            F.append({'art': 'fehlt', 'klasse': key, 'titel': '%s fehlt (%s)' % (name, gt),
                      'ist': 'nicht in der Karte (in %d von %d Ausschnitten in der LK)' % (sum(1 for v in a['n_ref'] if v), nmain),
                      'soll': '%s%s' % (col, (' %s mm' % fmt(soll.get('w_total_mm'), 2)) if kind == 'line' and soll.get('w_total_mm') else ''),
                      'vorschlag': 'Objektart in Style/Konverter aufnehmen oder Zoomstufe prüfen (Typ %s)' % gt,
                      'wirkung': impact, 'limit': None})
            continue
        if not typ:
            continue
        # Farbe (Nennwerte)
        if soll.get('fill') and typ.get('fill') and typ['fill'] != 'none':
            # Zweifarbige Signaturen (z. B. Bahn rot mit weisser Mitte): gegen die nächste Sollfarbe
            d = min(de(parse_hex(typ['fill']), parse_hex(c)) for c in (soll['fill'], soll.get('border')) if c)
            share = ours_share * (typ.get('w_total', 1) if kind == 'line' else 1)
            if d > 2:
                F.append({'art': 'farbe', 'klasse': key,
                          'titel': '%s %s (%s): Farbe' % (typword, gt, name),
                          'ist': '%s' % typ['fill'], 'soll': '%s (SMV25 „%s“)' % (soll['fill'], soll.get('kategorie')),
                          'delta': 'ΔE %s' % fmt(d), 'vorschlag': 'Farbe %s übernehmen' % soll['fill'],
                          'wirkung': share * d, 'limit': None,
                          'messung': 'gemessen unsere Karte %s, SMR25 %s' % (
                              meas_ours[0].get('fill') if meas_ours else '–', smr_fill or '–')})
            if kind == 'area' and smr_fill:
                d2 = de(parse_hex(typ['fill']), parse_hex(smr_fill))
                if d2 > 6 and d <= 2:
                    F.append({'art': 'farbe_smr', 'klasse': key,
                              'titel': '%s %s (%s): Farbe weicht von der Pixelkarte ab' % (typword, gt, name),
                              'ist': typ['fill'], 'soll': '%s (SMR25 gemessen; SMV25-Nennwert %s)' % (smr_fill, soll['fill']),
                              'delta': 'ΔE %s' % fmt(d2),
                              'vorschlag': 'Nur Hinweis: TYP folgt dem SMV25-Nennwert, die gedruckte LK wirkt anders. '
                                           'Entscheid, welche Referenz gilt.',
                              'wirkung': ours_share * d2 * 0.3, 'limit': None})
        if kind == 'line':
            # Breite, je Zoomstufe gegen die LK-Geländebreite (Soll px = mm × k der Stufe)
            sw = soll.get('w_total_mm')
            typ0, gt0 = typ, gt
            for zk in MAIN_ZOOMS:
                if not (sw and typ.get('w_total')):
                    break
                zc = [c for ck, c in main_cases.items() if ck.endswith('/' + zk)]
                refz = sum(c['classes'][key].get('ref_len_px', 0) for c in zc) / (N * max(1, len(zc)))
                k = C.ZOOMS[zk]['k']
                # in dieser Stufe sichtbarer Typ (Routingtyp in 24, Übersichtstyp 0x10a… darunter)
                tcz = Counter(c['classes'][key].get('typ_code') for c in zc if c['classes'][key].get('typ_code'))
                if tcz:
                    tz = nom.typ_line(tcz.most_common(1)[0][0])
                    if tz:
                        typ = tz
                        gt = tcz.most_common(1)[0][0]
                target = sw * k
                tgt_i = max(1, int(round(target)))
                dw = typ['w_total'] - target
                contrast = de(parse_hex(soll.get('border') or soll.get('fill') or '#000000'), (255, 255, 255))
                if abs(typ['w_total'] - tgt_i) < 1 or refz == 0:
                    continue
                fill_t = max(1, int(round(soll.get('w_fill_mm', sw) * k)))
                bw = max(0, int(round((tgt_i - fill_t) / 2))) if soll.get('border') else 0
                if soll.get('border') and bw == 0 and tgt_i >= 3:
                    bw = 1; fill_t = max(1, tgt_i - 2)
                sug = ('LineWidth=%d, BorderWidth=%d (= %d px)' % (fill_t, bw, fill_t + 2 * bw)) if typ.get('muster') is None \
                    else 'Musterhöhe %d px' % tgt_i
                lim = LIMITS['subpixel'] if target < 1 else LIMITS['breite_zoom']
                mz = [c['classes'][key]['ours']['w_total'] for c in zc if 'w_total' in c['classes'][key].get('ours', {})]
                ms = [c['classes'][key]['smv25']['w_total'] for c in zc if 'w_total' in c['classes'][key].get('smv25', {})]
                F.append({'art': 'breite', 'klasse': key,
                          'titel': '%s %s (%s): Breite bei %s' % (typword, gt, name, C.ZOOMS[zk]['label']),
                          'ist': '%d px gesamt%s (gemessen %s px)' % (
                              typ['w_total'], ', Füllung %d px' % typ['w_fill'] if typ.get('border') else '',
                              fmt(float(np.median(mz))) if mz else '–'),
                          'soll': '%s px = %s mm × %s px/mm%s (SMV25 gemessen %s px)' % (
                              fmt(target), fmt(sw, 2), fmt(k, 2),
                              ', Füllung %s mm' % fmt(soll.get('w_fill_mm'), 2) if soll.get('border') else '',
                              fmt(float(np.median(ms))) if ms else '–'),
                          'delta': '%+.1f px' % dw, 'vorschlag': sug,
                          'wirkung': refz * abs(dw) * contrast, 'limit': lim})
            typ, gt = typ0, gt0
            # Rand
            if soll.get('border') and not typ.get('border') and typ.get('muster') is None:
                F.append({'art': 'rand', 'klasse': key, 'titel': '%s %s (%s): Rand fehlt' % (typword, gt, name),
                          'ist': 'ohne Rand', 'soll': 'Rand %s' % soll['border'], 'vorschlag': 'BorderWidth=1, Randfarbe %s' % soll['border'],
                          'wirkung': ref_share * 2 * de(parse_hex(soll['border']), (255, 255, 255)), 'limit': None})
            elif soll.get('border') and typ.get('border') and typ['border'] != 'none' and typ.get('muster') is None:
                d = de(parse_hex(typ['border']), parse_hex(soll['border']))
                if d > 3:
                    F.append({'art': 'farbe', 'klasse': key, 'titel': '%s %s (%s): Randfarbe' % (typword, gt, name),
                              'ist': typ['border'], 'soll': soll['border'], 'delta': 'ΔE %s' % fmt(d),
                              'vorschlag': 'Randfarbe %s' % soll['border'], 'wirkung': ours_share * 2 * d, 'limit': None})
            # Strichmuster
            sd = dash_mm(soll.get('dash'))
            td = typ_dash(typ.get('muster'))
            contrast = de(parse_hex(soll.get('fill') or '#000000'), (255, 255, 255))
            if not soll.get('w_total_mm'):
                pass          # keine Linien-Symbolik in symbology.tsv (Marker-/Spezialsignatur)
            elif sd and not td:
                F.append({'art': 'muster', 'klasse': key, 'titel': '%s %s (%s): Strichmuster' % (typword, gt, name),
                          'ist': 'durchgezogen', 'soll': 'Strich %s mm / Lücke %s mm (%s/%s px)' % (
                              fmt(sd[0], 2), fmt(sd[1], 2), fmt(mm2px(sd[0])), fmt(mm2px(sd[1]))),
                          'vorschlag': 'Muster %d px Strich / %d px Lücke (32 px Raster)' % (
                              max(1, round(mm2px(sd[0]))), max(1, round(mm2px(sd[1])))),
                          'wirkung': ref_share * 0.5 * contrast * max(1, typ.get('w_total', 1)), 'limit': LIMITS['muster']})
            elif td and not sd:
                F.append({'art': 'muster', 'klasse': key, 'titel': '%s %s (%s): Strichmuster' % (typword, gt, name),
                          'ist': 'Strich %s px / Lücke %s px' % (fmt(td[0]), fmt(td[1])), 'soll': 'durchgezogen (SMV25 „%s“)' % soll.get('kategorie'),
                          'vorschlag': 'durchgezogen zeichnen', 'wirkung': ours_share * typ.get('w_total', 1) * 0.3 * contrast, 'limit': None})
            elif td and sd:
                ds_, dg_ = mm2px(sd[0]), mm2px(sd[1])
                if abs(td[0] - ds_) > 1.5 or abs(td[1] - dg_) > 1.5:
                    F.append({'art': 'muster', 'klasse': key, 'titel': '%s %s (%s): Strichlänge' % (typword, gt, name),
                              'ist': 'Strich %s px / Lücke %s px' % (fmt(td[0]), fmt(td[1])),
                              'soll': 'Strich %s px / Lücke %s px (%s/%s mm)' % (fmt(ds_), fmt(dg_), fmt(sd[0], 2), fmt(sd[1], 2)),
                              'vorschlag': 'Muster %d/%d px' % (max(1, round(ds_)), max(1, round(dg_))),
                              'wirkung': ref_share * 0.3 * contrast, 'limit': LIMITS['muster']})

    # --- Abdeckung je Zoomstufe (Fläche bzw. Linienlänge unsere / LK-Geometrie)
    for zk in ('z12k', 'z25k', 'z50k'):
        zc = {k: v for k, v in cases.items() if k.endswith('/' + zk)}
        if not zc:
            continue
        keys = next(iter(zc.values()))['classes'].keys()
        for key in keys:
            ref = sum(c['classes'][key].get('ref_len_px', c['classes'][key].get('ref_area_px', 0)) for c in zc.values())
            our = sum(c['classes'][key].get('ours_len_px', c['classes'][key].get('ours_area_px', 0)) for c in zc.values())
            e = next(iter(zc.values()))['classes'][key]
            if ref < 300 * len(zc) / 5 or our == 0 and zk in MAIN_ZOOMS:
                continue          # zu wenig LK-Objekte; ganz fehlende Klassen meldet „fehlt“
            ratio = our / ref
            if ratio >= 0.6:
                continue
            soll = e.get('soll') or {}
            col = soll.get('border') or soll.get('fill') or (e.get('typ') or {}).get('fill') or '#000000'
            w = mm2px(soll['w_total_mm']) if e['kind'] == 'line' and soll.get('w_total_mm') else 1
            impact = (ref - our) / (N * len(zc)) * max(1, w) * de(parse_hex(col), (255, 255, 255))
            if zk == 'z50k':
                impact *= 0.5     # SMV25-Inhalt ist für 1:50 000 nur Richtwert (LK50 generalisiert)
            hint = ''
            if key == 'gebaeude':
                hint = ('; Vermutung: mkgmap verwirft kleine Flächen unterhalb der Detailstufe '
                        '(--min-size-polygon, Standard 8 Einheiten = %d m bei Auflösung %d) – '
                        '--polygon-size-limits bzw. Zoomstufe prüfen' % (8 * 2.39 * 2 ** (24 - C.ZOOMS[zk]['res']), C.ZOOMS[zk]['res']))
            F.append({'art': 'abdeckung', 'klasse': key,
                      'titel': '%s (%s) bei %s: nur %d %% des LK-Inhalts' % (e['name'], '/'.join(e['gtypes']), C.ZOOMS[zk]['label'], round(100 * ratio)),
                      'ist': '%s px %s' % (our, 'Fläche' if e['kind'] == 'area' else 'Linienlänge'),
                      'soll': '%s px in der SMV25%s' % (ref, ' (Richtwert, LK50 ist generalisiert)' if zk == 'z50k' else ''),
                      'delta': '%d %%' % round(100 * ratio),
                      'vorschlag': 'Auflösung/Filter der Objektart in Style bzw. mkgmap-Optionen prüfen' + hint,
                      'wirkung': impact, 'limit': None})

    # kleine 1:50 000-Abdeckungsbefunde zu einem Sammelbefund zusammenfassen
    small = [f for f in F if f['art'] == 'abdeckung' and "1:50'000" in f['titel'] and f['wirkung'] < 0.5]
    if small:
        F = [f for f in F if f not in small]
        F.append({'art': 'abdeckung', 'klasse': 'z50k_sammel',
                  'titel': "Bei 1:50'000 (Auflösung 22) fehlen bzw. sind stark ausgedünnt: " +
                           ', '.join('%s %s' % (f['titel'].split(' bei ')[0], f['delta']) for f in small),
                  'ist': 'siehe Titel (Anteil am SMV25-Inhalt)', 'soll': 'LK50 zeigt diese Objektarten generalisiert',
                  'delta': '', 'vorschlag': 'Auflösungen im Style prüfen (Zoomstufen-Tabelle in docs/stil/stil.md)',
                  'wirkung': sum(f['wirkung'] for f in small), 'limit': None})

    # --- Zeichenreihenfolge
    oagg = defaultdict(lambda: {'ref': [], 'ours': [], 'n': []})
    for ck, c in main_cases.items():
        for pk, e in c['order'].items():
            if 'smv25' in e and 'ours' in e and e['smv25']['n'] >= 10 and e['ours']['n'] >= 10:
                oagg[pk]['ref'].append(e['smv25']['a_oben']); oagg[pk]['ours'].append(e['ours']['a_oben'])
                oagg[pk]['n'].append(e['ours']['n'])
    for pk, v in oagg.items():
        r, o = float(np.mean(v['ref'])), float(np.mean(v['ours']))
        if abs(r - o) >= 0.4:
            a, b = pk.split('>')
            ia = next(iter(cases.values()))['classes'][a]; ib = next(iter(cases.values()))['classes'][b]
            ca = (ia.get('typ') or {}).get('fill') or '#000000'; cb = (ib.get('typ') or {}).get('fill') or '#000000'
            top_ref = ia['name'] if r >= 0.5 else ib['name']
            top_ours = ia['name'] if o >= 0.5 else ib['name']
            lim = LIMITS['linienfolge'] if ia['kind'] == 'line' and ib['kind'] == 'line' else None
            codes = [c['classes'][x].get('typ_code') or '' for c in main_cases.values() for x in (a, b)]
            ext = any(cd and int(cd, 16) >= 0x10000 for cd in codes)
            if ext:
                # render_img.py sortiert erweiterte Typen (0x1xxxx) vor die Standardtypen; BaseCamp
                # (Test 8, 2026-11-04) zeichnet z. B. Höhenlinien unter den Strassen → nicht messbar.
                F.append({'art': 'reihenfolge', 'klasse': pk,
                          'titel': 'Zeichenreihenfolge %s / %s: im Renderer nicht messbar' % (ia['name'], ib['name']),
                          'ist': 'render_img.py: %s oben (%d %%)' % (top_ours, round(100 * max(o, 1 - o))),
                          'soll': '%s oben (%d %%)' % (top_ref, round(100 * max(r, 1 - r))),
                          'vorschlag': 'in BaseCamp prüfen (render_img.py zeichnet erweiterte Typen vor den Standardtypen)',
                          'wirkung': 0.0, 'limit': None})
                continue
            F.append({'art': 'reihenfolge', 'klasse': pk,
                      'titel': 'Zeichenreihenfolge %s / %s' % (ia['name'], ib['name']),
                      'ist': '%s oben (%d %% der Kreuzungspixel)' % (top_ours, round(100 * max(o, 1 - o))),
                      'soll': '%s oben (%d %%)' % (top_ref, round(100 * max(r, 1 - r))),
                      'vorschlag': ('Typwahl/drawOrder anpassen' if not lim else
                                    'Linientypen so wählen, dass %s später gezeichnet wird' % top_ref) +
                                   ('. Achtung: render_img.py zeichnet erweiterte Typen (0x1xxxx) vor den '
                                    'Standardtypen, also darunter; die Reihenfolge am Gerät in BaseCamp prüfen' if ext else ''),
                      'wirkung': float(np.sum(v['n'])) / (N * nmain) * abs(r - o) * de(parse_hex(ca), parse_hex(cb)),
                      'limit': lim})

    # --- Beschriftung
    lagg = defaultdict(lambda: defaultdict(list))
    for ck, c in main_cases.items():
        for lk, e in c.get('labels', {}).items():
            for k, v in e.items():
                lagg[lk][k].append(v)
    for lk, v in lagg.items():
        name = v['name'][0]
        ref_n = float(np.sum(v['ref_n'])); hit = float(np.sum(v['treffer']))
        refpx = [x for x in v['ref_px'] if x]; ourpx = [x for x in v['ours_px'] if x]
        size = float(np.median(refpx)) if refpx else 12
        area = 7 * 0.55 * size * size
        if ref_n >= 3 and hit / ref_n < 0.8:
            miss = ref_n - hit
            ex = sorted({x for l in v['fehlend_beispiele'] for x in l})[:10]
            F.append({'art': 'beschriftung', 'klasse': lk, 'titel': '%s: fehlen' % name,
                      'ist': '%d %% vorhanden (%d von %d)' % (round(100 * hit / ref_n), hit, ref_n),
                      'soll': 'alle Namen der LK, z. B. %s' % ', '.join(ex),
                      'vorschlag': 'Namen in Konverter/Style übernehmen bzw. Zoomstufe senken',
                      'wirkung': miss / nmain * area / N * 60 * 100 / 100, 'limit': None})
        exc = float(np.sum(v['ueberschuss_n']))
        if lk == 'strasse' and exc > 3 * max(1, ref_n):
            F.append({'art': 'beschriftung', 'klasse': lk, 'titel': 'Strassennamen: viel mehr als in der LK',
                      'ist': '%d Strassennamen in den Ausschnitten' % exc, 'soll': '%d (die LK beschriftet fast nur Routennummern)' % ref_n,
                      'vorschlag': 'Strassennamen nur für Suche/Routing, nicht anzeigen (TYP FontStyle=NoLabel bei 0x05–0x08), oder erst ab Auflösung 24',
                      'wirkung': exc / nmain * 7 * 0.55 * 10 * 10 / N * 15, 'limit': LIMITS['platzierung'],
                      'hinweis': 'render_img zeichnet alle Namen; das Gerät blendet bei Kollisionen aus, die Wirkung ist geringer'})
        if refpx and ourpx:
            rp, op = float(np.median(refpx)), float(np.median(ourpx))
            if abs(rp - op) >= 3:
                F.append({'art': 'beschriftung', 'klasse': lk, 'titel': '%s: Schriftgrösse' % name,
                          'ist': '%s (≈ %s px, unsicher)' % (v['ours_font'][0], fmt(op)),
                          'soll': '%s pt bei 1:25 000 ≈ %s px am Gerät' % (fmt(float(np.median([x for x in v['ref_pt_median'] if x]))), fmt(rp)),
                          'vorschlag': 'grössere Schriftklasse (Normal/Large)' if rp > op else 'kleinere Schriftklasse',
                          'wirkung': hit / nmain * 7 * 0.55 * abs(rp * rp - op * op) / N * 30, 'limit': LIMITS['schriftgroesse']})
        # Mehrheit über alle Ausschnitte (nicht nur der erste), gewichtet mit der Namenzahl
        rc = Counter(); oc = Counter()
        for c_r, c_o, n_r, n_o in zip(v['ref_farbe'], v['ours_farbe'], v['ref_n'], v['ours_n']):
            if c_r: rc[c_r] += n_r or 1
            if c_o: oc[c_o] += n_o or 1
        rc = [x for x, _ in rc.most_common(1)]; oc = [x for x, _ in oc.most_common(1)]
        if rc and oc:
            d = de(parse_hex(rc[0]), parse_hex(oc[0]))
            if d > 5:
                F.append({'art': 'beschriftung', 'klasse': lk, 'titel': '%s: Schriftfarbe' % name,
                          'ist': oc[0], 'soll': rc[0], 'delta': 'ΔE %s' % fmt(d), 'vorschlag': 'DayCustomColor=%s' % rc[0],
                          'wirkung': hit / nmain * area * 0.3 / N * d, 'limit': None})
        it = [x for x in v['ref_kursiv'] if x is not None]
        if it and float(np.mean(it)) > 0.5:
            F.append({'art': 'beschriftung', 'klasse': lk, 'titel': '%s: kursiv in der LK' % name,
                      'ist': 'gerade (Geräteschrift)', 'soll': 'kursiv (%d %% der Namen)' % round(100 * float(np.mean(it))),
                      'vorschlag': '–', 'wirkung': hit / nmain * area * 0.15 / N * 20, 'limit': LIMITS['kursiv']})

    # --- Symbole
    sagg = defaultdict(lambda: {'ref': 0, 'ours': 0, 'name': ''})
    for ck, c in main_cases.items():
        for sk, e in c.get('symbols', {}).items():
            sagg[sk]['ref'] += e['ref_n']; sagg[sk]['ours'] += e['ours_n']; sagg[sk]['name'] = e['name']
    for sk, v in sagg.items():
        if v['ref'] >= 4 and v['ours'] < 0.3 * v['ref']:
            F.append({'art': 'symbol', 'klasse': sk, 'titel': 'Symbole %s fehlen' % v['name'],
                      'ist': '%d' % v['ours'], 'soll': '%d (Summe der Ausschnitte)' % v['ref'],
                      'vorschlag': 'Objektart als Punkt-Typ aufnehmen (Konverter/Style)',
                      'wirkung': (v['ref'] - v['ours']) / nmain * 9 / N * 60, 'limit': None})

    # --- Typen ohne TYP-Definition
    unk = Counter()
    for c in cases.values():
        unk.update(c.get('unbekannte_typen') or {})
    if unk:
        F.append({'art': 'typ', 'klasse': 'unbekannt', 'titel': 'Typen in der IMG ohne TYP-Definition',
                  'ist': ', '.join('%s (%d)' % kv for kv in unk.most_common(12)),
                  'soll': 'jeder verwendete Typ hat einen TYP-Eintrag',
                  'vorschlag': 'TYP ergänzen oder Style-Zuordnung prüfen (Gerät zeichnet sonst Garmin-Vorgabe)',
                  'wirkung': sum(unk.values()) / max(1, len(cases)) * 20 / N * 50, 'limit': None})

    # --- Relief
    rel = []
    for ck, c in cases.items():
        g = c['global']
        refk = 'smr25' if 'smr25' in g else ('smr50' if 'smr50' in g else ('smr100' if 'smr100' in g else None))
        if refk and 'relief_dL' in g.get(refk, {}):
            rel.append((ck, g[refk]['relief_r'], g[refk]['relief_dL'], g['ours'].get('relief_r', 0), g['ours'].get('relief_dL', 0)))
    if rel:
        dref = float(np.mean([r[2] for r in rel])); dours = float(np.mean([r[4] for r in rel]))
        rr = float(np.mean([r[1] for r in rel])); ro = float(np.mean([r[3] for r in rel]))
        dem = R['config'].get('dem') or {}
        if dem.get('mit_dem'):
            F.append({'art': 'relief', 'klasse': 'relief',
                      'titel': 'Geländeschummerung: DEM vorhanden, im Renderer nicht messbar',
                      'ist': 'DEM in %d von %d Kacheln (%d kB); render_img.py zeichnet keine DEM-Schummerung, '
                             'gemessen r = %s' % (dem['mit_dem'], dem['kacheln'], dem['dem_bytes'] // 1024, fmt(ro, 2)),
                      'soll': 'Pixelkarte r = %s, ΔL %s' % (fmt(rr, 2), fmt(dref)),
                      'vorschlag': 'Helligkeit/Lichtrichtung in BaseCamp bzw. am Gerät mit der SMR25 vergleichen '
                                   '(Screenshot mit bekanntem Ausschnitt, dann misst style_qa mit)',
                      'wirkung': 0.0, 'limit': LIMITS['relief']})
        elif dref - dours > 1:
            F.append({'art': 'relief', 'klasse': 'relief', 'titel': 'Geländeschummerung fehlt',
                      'ist': 'Korrelation mit dem SMV25-Relief r = %s, Helligkeitsmodulation ΔL %s' % (fmt(ro, 2), fmt(dours)),
                      'soll': 'Pixelkarte r = %s, ΔL %s (Mittel aller Ausschnitte/Zoomstufen; Säntis am stärksten)' % (fmt(rr, 2), fmt(dref)),
                      'vorschlag': 'DEM in die Basiskarte (mkgmap --dem, wie img7703-dem) und am Gerät prüfen; '
                                   'Testbild der VM (t1-hoehen-*) gegen SMR25 messen, sobald georeferenziert',
                      'wirkung': (dref - dours) * 0.6, 'limit': LIMITS['relief']})
    F.sort(key=lambda f: -f['wirkung'])
    return F


# ------------------------------------------------------------------ Bilder
def font(sz):
    for p in ('/System/Library/Fonts/Supplemental/Arial Narrow.ttf', '/System/Library/Fonts/Helvetica.ttc'):
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            pass
    return ImageFont.load_default()


def side_by_side(cut, zk):
    d = os.path.join(C.OUT, cut, zk)
    z = C.ZOOMS[zk]
    panels = [('Unsere Karte (render_img.py, Basis + Overlays)', os.path.join(d, 'ours.png'))]
    for r in z['refs']:
        lab = {'smv25': 'SMV25 (offizielles QGIS-Projekt)', 'smr25': 'Swiss Map Raster 25', 'smr50': 'Swiss Map Raster 50',
               'smr100': 'Swiss Map Raster 100'}[r]
        panels.append((lab, os.path.join(C.REF_OUT, cut, zk, 'ref_%s.png' % r)))
    panels = [(l, p) for l, p in panels if os.path.exists(p)]
    ims = [Image.open(p).convert('RGB') for _, p in panels]
    # ΔE-Karte (weichgezeichnet) unsere vs. erste Referenz
    if len(ims) >= 2:
        from scipy import ndimage as ndi
        a = np.array(ims[0], float); b = np.array(ims[1], float)
        fa = np.stack([ndi.gaussian_filter(a[..., i], 3) for i in range(3)], -1)
        fb = np.stack([ndi.gaussian_filter(b[..., i], 3) for i in range(3)], -1)
        dm = de2000(srgb_to_lab(fa), srgb_to_lab(fb))
        v = np.clip(dm / 40.0, 0, 1)
        heat = np.stack([255 * v, 255 * (1 - np.abs(v - 0.5) * 2) * 0.6, 255 * (1 - v)], -1).astype(np.uint8)
        ims.append(Image.fromarray(heat))
        panels.append(('ΔE2000 (σ 3 px) unsere ↔ %s, blau 0 … rot ≥ 40' % panels[1][0].split(' (')[0], None))
    w, h = C.W, C.H
    cols = 2
    rows = (len(ims) + 1) // 2
    out = Image.new('RGB', (cols * w + (cols - 1) * 8, rows * (h + 26)), (255, 255, 255))
    dr = ImageDraw.Draw(out)
    f = font(16)
    for i, (im, (lab, _)) in enumerate(zip(ims, panels)):
        x = (i % cols) * (w + 8); y = (i // cols) * (h + 26)
        dr.text((x + 4, y + 4), lab, fill=(0, 0, 0), font=f)
        out.paste(im, (x, y + 24))
    dr.text((6, out.height - 18), '%s, %s · Daten ©swisstopo' % (C.CUTOUTS[cut]['name'], z['label']),
            fill=(80, 80, 80), font=font(13))
    p = C.path('vergleich', '%s_%s.png' % (cut, zk))
    out.save(p, optimize=True)
    return p


# ------------------------------------------------------------------ Bericht
def write(R, F, ver, hist):
    L = []
    t = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    L.append('# Stil-QA: Vergleich mit dem swisstopo-Layout (%s)\n' % (
        'Gesamt-Build work/build' if R['config'].get('target') == 'gesamt' else 'Stil-Testbuild work/style/testgebiet'))
    L.append('Stand %s · Stil-Version `%s` (TYP %s, IMG-Stand %s) · Gerät %d dpi (1 px = %s mm, px = mm × 6,25)\n' % (
        t, ver['hash'], os.path.relpath(ver['typ'], C.MAIN), ver['img_stand'], C.DEVICE_DPI, fmt(PX_MM, 3)))
    L.append('Referenzen: SMV25 (offizielles QGIS-Projekt `SMV25_CHLV95LN02.qgs`, headless gerendert) und '
             'Swiss Map Raster 25/50/100. Unsere Karte: `render_img.py` (style-typ), IMG `%s`, Overlays: %s. Methode und Grenzen: `docs/stil/messung.md`. Daten ©swisstopo.\n' % (
        os.path.relpath(R['config']['img_dir'], C.MAIN), ', '.join(o[0] for o in R['config'].get('overlays', [])) or 'keine'))
    tot = sum(f['wirkung'] for f in F)
    ss = [c['global'][k]['ssim'] for c in R['cases'].values() for k in c['global'] if k not in ('ours', 'smv25_vs_smr25') and 'ssim' in c['global'][k]]
    base = [c['global']['smv25_vs_smr25']['ssim'] for c in R['cases'].values() if 'smv25_vs_smr25' in c['global']]
    L.append('## Kurzfassung\n')
    L.append('- Summe der Wirkung aller Befunde: **%s ΔE·%%** (kleiner ist besser), %d Befunde, davon %d mit Garmin/TYP-Grenze.' % (
        fmt(tot), len(F), sum(1 for f in F if f['limit'])))
    L.append('- SSIM unsere Karte ↔ Referenz im Mittel **%s** (SMV25 ↔ SMR25 als Vergleichsmassstab: %s; 1 = gleich).' % (
        fmt(float(np.mean(ss)), 3), fmt(float(np.mean(base)), 3) if base else '–'))
    if hist:
        L.append('- Verlauf (frühere Messungen): ' + ' → '.join('%s (IMG %s): %s' % (h['stand'][5:16], h.get('img_stand', '?')[5:], fmt(h['summe'])) for h in hist[-6:]))
    L.append('')
    L.append('## Priorisierte Abweichungen (grösste Wirkung zuerst)\n')
    L.append('„Grenze“ = Garmin/TYP kann es technisch nicht oder nur teilweise; Text siehe Fussnote.\n')
    L.append('| # | Wirkung | Befund | Ist | Soll | Δ | Vorschlag | Grenze |')
    L.append('|---|---|---|---|---|---|---|---|')
    lim_keys = {v: k for k, v in LIMITS.items()}
    for i, f in enumerate(F, 1):
        L.append('| %d | %s | %s | %s | %s | %s | %s | %s |' % (
            i, fmt(f['wirkung'], 2), f['titel'], f['ist'], f['soll'], f.get('delta', ''), f['vorschlag'],
            ('[%s]' % lim_keys[f['limit']]) if f['limit'] else ''))
    L.append('')
    L.append('Grenzen:\n')
    for k, v in LIMITS.items():
        if any(f['limit'] == v for f in F):
            L.append('- **[%s]** %s' % (k, v))
    L.append('')
    # Messwerte mit Bild gegen Nennwerte (Plausibilität)
    L.append('## Gesamtmasse je Ausschnitt und Zoomstufe\n')
    L.append('SSIM (Graustufen), ΔE nach Weichzeichnung (σ 3 px, „Flächenwirkung“), Schnitt der Lab-Histogramme '
             '(1 = gleiche Farbverteilung), Relief r = Korrelation der Helligkeit mit dem SMV25-Relief (offene Flächen).\n')
    L.append('| Ausschnitt | Zoom | Referenz | SSIM | ΔE weich | Histogramm | Relief r Ref | Relief r unsere |')
    L.append('|---|---|---|---|---|---|---|---|')
    for ck, c in R['cases'].items():
        cut, zk = ck.split('/')
        for k, g in c['global'].items():
            if k in ('ours',) or 'ssim' not in g:
                continue
            L.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
                C.CUTOUTS[cut]['name'], C.ZOOMS[zk]['label'], 'SMV25 ↔ SMR25' if k == 'smv25_vs_smr25' else k.upper(),
                fmt(g['ssim'], 3), fmt(g['de_blur']), fmt(g['hist'], 3),
                fmt(g.get('relief_r'), 2) if k != 'smv25_vs_smr25' else '', fmt(c['global']['ours'].get('relief_r'), 2) if k != 'smv25_vs_smr25' else ''))
    L.append('')
    # Klassen-Tabelle
    L.append('## Objektarten: Nennwerte und Messung (1:25 000, Mittel der Ausschnitte)\n')
    L.append('Soll = SMV25-Symbolik der häufigsten Kategorie (mm × 6,25 = px, %d dpi). Ist = TYP. „gem.“ = im Bild gemessen '
             '(Querprofile alle 2 px, Median). Antialiasing macht QGIS-Linien unter 1 px heller und breiter.\n' % C.DEVICE_DPI)
    L.append('| Objektart | Typ | Soll Farbe | Ist Farbe | ΔE | Soll Breite px | Ist Breite px | gem. SMV25 | gem. unsere | Soll Muster | Ist Muster |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|')
    seen = {}
    for ck, c in R['cases'].items():
        if not ck.endswith('z25k'):
            continue
        for key, e in c['classes'].items():
            s = seen.setdefault(key, {'e': e, 'smv': [], 'ours': []})
            if e.get('soll', {}) and e['soll'].get('fill') and not (s['e'].get('soll') or {}).get('fill'):
                s['e'] = e
            if 'w_total' in e.get('smv25', {}):
                s['smv'].append(e['smv25']['w_total'])
            if 'w_total' in e.get('ours', {}):
                s['ours'].append(e['ours']['w_total'])
    nom = Nominal()
    tcats = defaultdict(Counter)
    for ck, c in R['cases'].items():
        if ck.endswith('z25k'):
            for key, e in c['classes'].items():
                tcats[key].update(e.get('cats') or {})
    for key, s in seen.items():
        e = s['e']; ty = e.get('typ') or {}
        so = (nom.smv(e['layer'], tcats[key]) if e.get('layer') and tcats[key] else e.get('soll')) or {}
        if not so.get('fill') and not ty:
            continue
        d = de(parse_hex(so['fill']), parse_hex(ty['fill'])) if so.get('fill') and ty.get('fill') and ty['fill'] != 'none' else None
        sd = dash_mm(so.get('dash')); td = typ_dash(ty.get('muster'))
        L.append('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            e['name'], '/'.join(e['gtypes']), so.get('fill', '–'), ty.get('fill', '–'), fmt(d),
            fmt(mm2px(so['w_total_mm'])) if so.get('w_total_mm') else '–', ty.get('w_total', '–') if e['kind'] == 'line' else '–',
            fmt(float(np.median(s['smv']))) if s['smv'] else '–', fmt(float(np.median(s['ours']))) if s['ours'] else '–',
            ('%s/%s px' % (fmt(mm2px(sd[0])), fmt(mm2px(sd[1])))) if sd else ('durchgezogen' if e['kind'] == 'line' else '–'),
            ('%s/%s px' % (fmt(td[0]), fmt(td[1]))) if td else ('durchgezogen' if e['kind'] == 'line' else '–')))
    L.append('')
    # Beschriftung
    L.append('## Beschriftung (1:25 000)\n')
    L.append('| Kategorie | Namen LK | davon bei uns | Schrift LK (pt / px) | kursiv LK | Farbe LK | Schrift unsere | Farbe unsere | Beispiele fehlend |')
    L.append('|---|---|---|---|---|---|---|---|---|')
    lab = defaultdict(lambda: defaultdict(list))
    for ck, c in R['cases'].items():
        if ck.endswith('z25k'):
            for k, e in c.get('labels', {}).items():
                for kk, vv in e.items():
                    lab[k][kk].append(vv)
    for k, v in lab.items():
        refn = int(np.sum(v['ref_n'])); hit = int(np.sum(v['treffer']))
        pts = [x for x in v['ref_pt_median'] if x]; pxs = [x for x in v['ref_px'] if x]
        it = [x for x in v['ref_kursiv'] if x is not None]
        L.append('| %s | %d | %d | %s / %s | %s | %s | %s | %s | %s |' % (
            v['name'][0], refn, hit, fmt(float(np.median(pts))) if pts else '–', fmt(float(np.median(pxs))) if pxs else '–',
            ('%d %%' % round(100 * float(np.mean(it)))) if it else '–',
            next((x for x in v['ref_farbe'] if x), '–'), next((x for x in v['ours_font'] if x), '–'),
            next((x for x in v['ours_farbe'] if x), '–'), ', '.join(sorted({x for l in v['fehlend_beispiele'] for x in l})[:6])))
    L.append('')
    # Bilder
    L.append('## Nebeneinander-Bilder\n')
    for cut in C.CUTOUTS:
        for zk in C.ZOOMS:
            p = os.path.join(C.OUT, 'vergleich', '%s_%s.png' % (cut, zk))
            if os.path.exists(p):
                L.append('- [%s, %s](vergleich/%s_%s.png)' % (C.CUTOUTS[cut]['name'], C.ZOOMS[zk]['label'], cut, zk))
    vm = sorted(glob.glob(os.path.join(C.BASECAMP_SHOTS, '*.png')))
    if vm:
        L.append('\nBaseCamp-Bilder (nur angesehen, nicht gemessen: keine Georeferenz/Massstab): ' +
                 ', '.join('`%s`' % os.path.basename(p) for p in vm))
    L.append('\n## Grenzen der Messung\n')
    L.append('- `render_img.py` ist nicht BaseCamp: keine Kollisionsprüfung der Schrift (alle Namen werden gezeichnet), '
             'Höhenangaben in Fuss, Linienfolge angenähert. Werte zu Schrift und Linienfolge mit BaseCamp/Gerät bestätigen.')
    L.append('- Die Gerätegrösse der Garmin-Schriften (Small 10, Normal 12, Large 15 px) ist geschätzt.')
    L.append('- Unsere Geometrie ist swissTLM3D (ungeneralisiert), die LK-Geometrie DKM25 (generalisiert, verdrängt). '
             'Darum misst jede Klasse auf ihrer eigenen Geometrie; SSIM und ΔE-Karte enthalten auch Lageunterschiede.')
    L.append('- Höhenlinien kommen aus dem Overlay 7703 (src/dem/), nicht aus der Basiskarte.')
    open(C.path('report.md'), 'w').write('\n'.join(L) + '\n')


def main():
    R = json.load(open(C.path('results.json')))
    F = findings(R)
    for cut in C.CUTOUTS:
        for zk in C.ZOOMS:
            side_by_side(cut, zk)
    ver = style_version()
    hp = C.path('history.json')
    hist = json.load(open(hp)) if os.path.exists(hp) else []
    stand = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    entry = {'stand': stand, 'version': ver['hash'], 'img_stand': ver['img_stand'], 'img_dir': ver['img_dir'], 'summe': round(sum(f['wirkung'] for f in F), 2), 'n': len(F),
             'top': [f['titel'] for f in F[:5]]}
    hist = [h for h in hist if h['version'] != ver['hash']] + [entry]
    json.dump(hist, open(hp, 'w'), indent=1, ensure_ascii=False)
    json.dump(F, open(C.path('findings.json'), 'w'), indent=1, ensure_ascii=False)
    write(R, F, ver, hist[:-1])
    print('Bericht:', C.path('report.md'), '–', len(F), 'Befunde, Summe', entry['summe'])


if __name__ == '__main__':
    main()
