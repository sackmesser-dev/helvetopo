#!/usr/bin/env python3
"""Einfacher Vorschau-Renderer für mkgmap-IMG-Dateien mit TYP-Quelltext.

Liest eine einzelne Kartenkachel (z. B. 77019001.img, nicht gmapsupp.img), dekodiert
TRE/RGN/LBL/NET (Formatlogik nach mkgmap RGNFileReader/TREFileReader, GPL) und zeichnet die
Objekte einer Zoomstufe mit den Farben, Breiten und Mustern aus der TYP-Textdatei.

Das ist keine Garmin-Darstellung: Schriften, Beschriftungsplatzierung, Liniendicken-
Skalierung und Zeichenreihenfolge der Linien sind angenähert. Ziel ist eine schnelle
Sichtkontrolle von Typzuordnung, Farben, Mustern und Zoomstufen ohne BaseCamp.

Aufruf:
    python3 -I render_img.py KARTE.img TYP.txt AUSGABE.png [--res 24] [--night] [--scale 1.0]
                             [--bbox minlon,minlat,maxlon,maxlat] [--list]
"""
import argparse
import math
import re
import struct
import sys

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------- IMG-Container
def read_imgfs(data):
    if data[0] != 0:
        x = data[0]
        data = bytes(b ^ x for b in data)
    bs = 1 << (data[0x61] + data[0x62])
    dirstart = data[0x40] * 512
    files = {}
    pos = dirstart
    while pos + 512 <= len(data):
        e = data[pos:pos + 512]
        pos += 512
        if e[0] != 1:
            continue
        name = (e[1:9].decode('latin-1').strip() + '.' + e[9:12].decode('latin-1').strip())
        part = e[0x11]
        blocks = struct.unpack('<240H', e[0x20:0x20 + 480])
        f = files.setdefault(name, {'size': 0, 'blocks': []})
        if part == 0:
            f['size'] = struct.unpack('<I', e[0x0c:0x10])[0]
        f['blocks'] += [b for b in blocks if b != 0xffff]
    out = {}
    for name, f in files.items():
        if name.strip('.') == '':
            continue
        buf = b''.join(data[b * bs:(b + 1) * bs] for b in f['blocks'])
        out[name] = buf[:f['size']]
    return out


def u(b, o, n):
    return int.from_bytes(b[o:o + n], 'little')


def s(b, o, n):
    return int.from_bytes(b[o:o + n], 'little', signed=True)


# ---------------------------------------------------------------- Bitstream
class BitReader:
    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def get(self, n):
        res = 0
        p = 0
        while p < n:
            idx, off = divmod(self.pos, 8)
            b = self.buf[idx] >> off
            nb = min(n - p, 8 - off)
            res |= (b & ((1 << nb) - 1)) << p
            p += nb
            self.pos += nb
        return res

    def get1(self):
        return self.get(1) == 1

    def sget2(self, n):
        top = 1 << (n - 1)
        mask = top - 1
        base = 0
        res = self.get(n)
        while res == top:
            base += mask
            res = self.get(n)
        if res & top == 0:
            return res + base
        return (res | ~mask) - base


def read_bitstream(buf, shift, lon0, lat0, extra, ln, base, ext, polygon):
    pts = [(lon0, lat0)]
    def width(n):
        return 2 + (n if n <= 9 else 2 * n - 9)
    xb, yb = width(base & 0xf), width((base >> 4) & 0xf)
    if ln == 0:
        return pts
    br = BitReader(buf)
    xsame = br.get1()
    xneg = br.get1() if xsame else False
    if not xsame:
        xb += 1
    ysame = br.get1()
    yneg = br.get1() if ysame else False
    if not ysame:
        yb += 1
    if ext:
        br.get1()
    if extra:
        br.get1()
    lon, lat = lon0, lat0
    while br.pos <= 8 * ln - ((1 if extra else 0) + xb + yb):
        if xsame:
            dx = br.get(xb)
            dx = -dx if xneg else dx
        else:
            dx = br.sget2(xb)
        if ysame:
            dy = br.get(yb)
            dy = -dy if yneg else dy
        else:
            dy = br.sget2(yb)
        node = br.get1() if extra else False
        if not node and dx == 0 and dy == 0:
            continue
        lat += dy << shift
        lon += dx << shift
        pts.append((lon, lat))
    if polygon:
        pts.append(pts[0])
    return pts


# ---------------------------------------------------------------- Kartenkachel
class Tile:
    def __init__(self, files):
        def pick(ext):
            for k, v in files.items():
                if k.endswith('.' + ext):
                    return v
            return None
        self.tre, self.rgn, self.lbl, self.net = pick('TRE'), pick('RGN'), pick('LBL'), pick('NET')
        self._levels()
        self._lbl()

    def _lbl(self):
        b = self.lbl
        self.lbl_off = u(b, 0x15, 4)
        self.lbl_size = u(b, 0x19, 4)
        self.lbl_mult = b[0x1d]
        self.lbl_fmt = b[0x1e]
        self.poi_off = u(b, 0x57, 4)
        self.poi_mult = b[0x5f]
        if self.net is not None:
            self.net1 = u(self.net, 0x15, 4)
            self.net_mult = self.net[0x1d]

    def label(self, off):
        if off == 0 or self.lbl_fmt not in (9, 10):
            return ''
        p = self.lbl_off + (off << self.lbl_mult)
        end = self.lbl.index(0, p)
        raw = self.lbl[p:end]
        txt = raw.decode('utf-8' if self.lbl_fmt == 10 else 'cp1252', 'replace')
        # Höhenfeld (0x1f + Fuss, height-Filter): wie das Gerät in Meter anzeigen
        if '\x1f' in txt:
            name, _, ft = txt.partition('\x1f')
            try:
                txt = (name + ' ' + str(int(round(float(ft) * 0.3048)))).strip()
            except ValueError:
                pass
        return ''.join(ch if ord(ch) >= 0x20 else ' ' for ch in txt).strip()

    def poi_label(self, off):
        p = self.poi_off + (off << self.poi_mult)
        return self.label(u(self.lbl, p, 3) & 0x3fffff)

    def road_label(self, netoff):
        p = self.net1 + (netoff << self.net_mult)
        return self.label(u(self.net, p, 3) & 0x3fffff)

    def _levels(self):
        t = self.tre
        hl = u(t, 0, 2)
        lv_off, lv_size = u(t, 0x21, 4), u(t, 0x25, 4)
        sd_off, sd_size = u(t, 0x29, 4), u(t, 0x2d, 4)
        self.levels = []
        for i in range(lv_size // 4):
            o = lv_off + 4 * i
            self.levels.append({'level': t[o] & 0x7f, 'bits': t[o + 1], 'ndiv': u(t, o + 2, 2)})
        self.subdivs = []
        pos = sd_off
        last_rgn = u(t, pos, 3)
        for li, lv in enumerate(self.levels):
            for _ in range(lv['ndiv']):
                flags = t[pos + 3]
                lon = s(t, pos + 4, 3)
                lat = s(t, pos + 7, 3)
                rec = 16 if li < len(self.levels) - 1 else 14
                end_rgn = u(t, pos + rec, 3) if pos + rec + 3 <= sd_off + sd_size + 3 else None
                self.subdivs.append({'level': li, 'bits': lv['bits'], 'flags': flags, 'lon': lon,
                                     'lat': lat, 'start': last_rgn, 'end': end_rgn})
                last_rgn = end_rgn
                pos += rec
        rgn_size = u(self.rgn, 0x19, 4)
        if self.subdivs:
            self.subdivs[-1]['end'] = rgn_size
        # Offsets der erweiterten Typen (TRE-Abschnitt, 13 Byte je Unterteilung + Schlussrecord)
        if hl > 0x86:
            eo, es, er = u(t, 0x7c, 4), u(t, 0x80, 4), u(t, 0x84, 2)
        else:
            eo = es = er = 0
        n = len(self.subdivs)
        if er and es >= (n + 1) * er:
            recs = [(u(t, eo + i * er, 4), u(t, eo + i * er + 4, 4), u(t, eo + i * er + 8, 4))
                    for i in range(n + 1)]
            for i, sd in enumerate(self.subdivs):
                sd['ext'] = [(recs[i][k], recs[i + 1][k] - recs[i][k]) for k in range(3)]
        else:
            for sd in self.subdivs:
                sd['ext'] = [(0, 0)] * 3

    def objects(self, li):
        r = self.rgn
        data_off = u(r, 0x15, 4)
        ext_area = u(r, 0x1d, 4)
        ext_line = u(r, 0x39, 4)
        ext_point = u(r, 0x55, 4)
        pts, lines, polys = [], [], []
        for sd in self.subdivs:
            if sd['level'] != li:
                continue
            shift = 24 - sd['bits']
            f = sd['flags']
            hp, hi, hl, hg = f & 0x10, f & 0x20, f & 0x40, f & 0x80
            start = data_off + sd['start']
            end = data_off + sd['end']
            p = start
            ptr = {}
            if hi and hp:
                ptr['i'] = u(r, p, 2); p += 2
            if hl and (hp or hi):
                ptr['l'] = u(r, p, 2); p += 2
            if hg and (hp or hi or hl):
                ptr['g'] = u(r, p, 2); p += 2
            hdr_end = p
            starts = {}
            order = [('p', hp), ('i', hi), ('l', hl), ('g', hg)]
            present = [k for k, h in order if h]
            for k in present:
                starts[k] = start + ptr[k] if k in ptr else hdr_end
            for idx, k in enumerate(present):
                kend = starts[present[idx + 1]] if idx + 1 < len(present) else end
                pos = starts[k]
                if k in 'pi':
                    while pos < kend:
                        t = r[pos]
                        val = u(r, pos + 1, 3)
                        dlon, dlat = s(r, pos + 4, 2), s(r, pos + 6, 2)
                        pos += 8
                        typ = t << 8
                        if val & 0x800000:
                            typ |= r[pos]
                            pos += 1
                        lab = self.poi_label(val & 0x3fffff) if val & 0x400000 else self.label(val & 0x3fffff)
                        pts.append((typ, sd['lon'] + (dlon << shift), sd['lat'] + (dlat << shift), lab))
                else:
                    polygon = (k == 'g')
                    while pos < kend:
                        t = r[pos]
                        typ = t & (0x7f if polygon else 0x3f)
                        lo = u(r, pos + 1, 3)
                        dlon, dlat = s(r, pos + 4, 2), s(r, pos + 6, 2)
                        pos += 8
                        if t & 0x80:
                            ln = u(r, pos, 2); pos += 2
                        else:
                            ln = r[pos]; pos += 1
                        base = r[pos]; pos += 1
                        buf = r[pos:pos + ln]; pos += ln
                        extra = bool(lo & 0x400000) and not polygon
                        if lo & 0x800000 and not polygon:
                            lab = self.road_label(lo & 0x3fffff)
                        else:
                            lab = self.label(lo & 0x3fffff)
                        coords = read_bitstream(buf, shift, sd['lon'] + (dlon << shift),
                                                sd['lat'] + (dlat << shift), extra, ln, base, False, polygon)
                        (polys if polygon else lines).append((typ, coords, lab))
            # erweiterte Typen
            for kind, (off, size), base_off in zip('glp', sd['ext'], (ext_area, ext_line, ext_point)):
                if size <= 0:
                    continue
                pos = base_off + off
                kend = pos + size
                while pos < kend:
                    typ = 0x10000 + (r[pos] << 8)
                    b1 = r[pos + 1]
                    typ |= b1 & 0x1f
                    dlon, dlat = s(r, pos + 2, 2), s(r, pos + 4, 2)
                    pos += 6
                    lon0, lat0 = sd['lon'] + (dlon << shift), sd['lat'] + (dlat << shift)
                    if kind == 'p':
                        lab = ''
                        if b1 & 0x20:
                            lo = u(r, pos, 3); pos += 3
                            lab = self.poi_label(lo & 0x3fffff) if lo & 0x400000 else self.label(lo & 0x3fffff)
                        if b1 & 0x80:
                            pos = skip_extra(r, pos)
                        pts.append((typ, lon0, lat0, lab))
                        continue
                    c = r[pos]
                    if c & 1:
                        ln = (c >> 1) & 0x7f; pos += 1
                    else:
                        ln = (u(r, pos, 2)) >> 2; pos += 2
                    ln -= 1
                    base = r[pos]; pos += 1
                    buf = r[pos:pos + ln]; pos += ln
                    coords = read_bitstream(buf, shift, lon0, lat0, False, ln, base, True, kind == 'g')
                    lab = ''
                    if b1 & 0x20:
                        lab = self.label(u(r, pos, 3) & 0x3fffff); pos += 3
                    if b1 & 0x80:
                        pos = skip_extra(r, pos)
                    (polys if kind == 'g' else lines).append((typ, coords, lab))
        return pts, lines, polys


def skip_extra(r, pos):
    b1 = r[pos]; pos += 1
    if b1 & 0xe0 == 0xe0:
        while r[pos] != 0x01:
            pos += 1
        return pos + 1
    if b1 & 0xa0 == 0xa0:
        return pos + 2
    if b1 & 0x80:
        return pos + 1
    return pos


# ---------------------------------------------------------------- TYP-Text
def parse_typ(path):
    typ = {'polygon': {}, 'line': {}, 'point': {}, 'order': {}}
    lines = open(path, encoding='utf-8').read().splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        m = re.match(r'\[_(polygon|line|point|drawOrder)\]', ln)
        if not m:
            i += 1
            continue
        kind = m.group(1)
        sec = {}
        i += 1
        while i < len(lines) and lines[i].strip() != '[end]':
            l = lines[i].strip()
            if kind == 'drawOrder' and l.startswith('Type='):
                t, lv = l[5:].split(',')
                typ['order'][int(t, 16)] = int(lv)
            elif re.match(r'(Day|Night)?Xpm=', l):
                key = l.split('=')[0]
                hdr = l.split('=', 1)[1].strip('"').split()
                w, h, nc, cpp = (int(x) for x in hdr)
                cols = {}
                for ci in range(nc):
                    i += 1
                    c = lines[i].strip().strip('"')
                    ch = c[:cpp] if cpp else str(ci)
                    val = c[cpp:].split()[-1]
                    cols[ch] = val
                rows = []
                for _ in range(h):
                    i += 1
                    rows.append(lines[i].strip().strip('"'))
                sec[key] = {'w': w, 'h': h, 'cols': cols, 'order': list(cols.keys()), 'rows': rows}
            elif '=' in l:
                k, v = l.split('=', 1)
                sec.setdefault(k, v)
            i += 1
        if kind != 'drawOrder':
            typ[kind][int(sec['Type'], 16)] = sec
        i += 1
    return typ


def hexrgb(v):
    if v == 'none':
        return None
    v = v.lstrip('#')
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


# ---------------------------------------------------------------- Zeichnen
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('img')
    ap.add_argument('typ')
    ap.add_argument('out')
    ap.add_argument('--res', type=int, default=24)
    ap.add_argument('--night', action='store_true')
    ap.add_argument('--scale', type=float, default=1.0, help='Pixel je Karteneinheit der Auflösung')
    ap.add_argument('--bbox')
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--labels', choices=('all', 'points', 'none'), default='all')
    a = ap.parse_args()

    tile = Tile(read_imgfs(open(a.img, 'rb').read()))
    li = min(range(len(tile.levels)), key=lambda k: abs(tile.levels[k]['bits'] - a.res))
    bits = tile.levels[li]['bits']
    pts, lines, polys = tile.objects(li)
    if a.list:
        from collections import Counter
        print('Ebenen:', [(lv['level'], lv['bits']) for lv in tile.levels])
        print('Ebene %d (%d bit): %d Punkte, %d Linien, %d Flächen' % (li, bits, len(pts), len(lines), len(polys)))
        for name, objs in (('Punkte', [p[0] for p in pts]), ('Linien', [l[0] for l in lines]),
                           ('Flächen', [p[0] for p in polys])):
            print(name, ' '.join('0x%x:%d' % kv for kv in sorted(Counter(objs).items())))
    typ = parse_typ(a.typ)

    unit = 360.0 / (1 << 24)
    allc = [(p[1], p[2]) for p in pts] + [c for l in lines for c in l[1]] + [c for p in polys for c in p[1]]
    if a.bbox:
        x0, y0, x1, y1 = (float(v) / unit for v in a.bbox.split(','))
    else:
        x0 = min(c[0] for c in allc); x1 = max(c[0] for c in allc)
        y0 = min(c[1] for c in allc); y1 = max(c[1] for c in allc)
    lat_mid = (y0 + y1) / 2 * unit
    kx = math.cos(math.radians(lat_mid))
    f = a.scale / (1 << (24 - bits))
    pad = 40
    W = int((x1 - x0) * kx * f) + 2 * pad + 260
    H = int((y1 - y0) * f) + 2 * pad

    def P(c):
        return ((c[0] - x0) * kx * f + pad, (y1 - c[1]) * f + pad)

    day = not a.night

    def pick_cols(xpm):
        """Tag- bzw. Nachtfarben einer Linien-/Flächen-XPM."""
        order = xpm['order']
        cols = [hexrgb(xpm['cols'][k]) for k in order]
        if len(cols) == 4 and not day:
            return {order[0]: cols[2], order[1]: cols[3]}, cols[2], cols[3]
        if len(cols) == 2 and xpm['w'] == 0 and not day:
            return None, cols[1], None
        return {order[0]: cols[0], order[1]: cols[1] if len(cols) > 1 else None}, cols[0], cols[1] if len(cols) > 1 else None

    bg = (252, 252, 252, 255) if day else (24, 26, 32, 255)
    img = Image.new('RGBA', (W, H), bg)
    dr = ImageDraw.Draw(img)
    try:
        fonts = {k: ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial Narrow.ttf', sz)
                 for k, sz in (('SmallFont', 11), ('NormalFont', 13), ('LargeFont', 16))}
    except OSError:
        fonts = {k: ImageFont.load_default() for k in ('SmallFont', 'NormalFont', 'LargeFont')}

    # Flächen nach drawOrder
    for typ_, coords, lab in sorted(polys, key=lambda p: typ['order'].get(p[0], 0)):
        if typ_ not in typ['order']:
            continue
        sec = typ['polygon'].get(typ_)
        xy = [P(c) for c in coords]
        if len(xy) < 3:
            continue
        if sec is None:
            dr.polygon(xy, fill=(200, 200, 200, 255))
            continue
        xpm = sec['Xpm']
        if xpm['w'] == 0:
            col = hexrgb(xpm['cols'][xpm['order'][0 if day else min(1, len(xpm['order']) - 1)]])
            dr.polygon(xy, fill=col)
        else:
            cmap, _, _ = pick_cols(xpm)
            pat = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
            for yy, row in enumerate(xpm['rows']):
                for xx, ch in enumerate(row):
                    c = cmap.get(ch)
                    if c:
                        pat.putpixel((xx, yy), c)
            big = Image.new('RGBA', (W, H), (0, 0, 0, 0))
            for ty in range(0, H, 32):
                for tx in range(0, W, 32):
                    big.paste(pat, (tx, ty))
            mask = Image.new('L', (W, H), 0)
            ImageDraw.Draw(mask).polygon(xy, fill=255)
            img.paste(big, (0, 0), Image.composite(big, Image.new('RGBA', (W, H), (0, 0, 0, 0)), mask))

    # Linien: zuerst Nicht-Strassen (absteigend), dann Strassen (aufsteigend wichtiger)
    ROADS = [0x16, 0x0f, 0x11, 0x12, 0x0e, 0x0a, 0x08, 0x07, 0x06, 0x05, 0x13, 0x04, 0x03, 0x09, 0x02, 0x01]
    def lkey(l):
        return (1, ROADS.index(l[0])) if l[0] in ROADS else (0, -l[0] if l[0] < 0x10000 else -0x40)
    lines_sorted = sorted(lines, key=lkey)
    draw_list = []
    for typ_, coords, lab in lines_sorted:
        sec = typ['line'].get(typ_)
        xy = [P(c) for c in coords]
        if sec is None:
            dr.line(xy, fill=(255, 0, 255, 255), width=1)
            continue
        xpm = sec['Xpm']
        if xpm['w'] == 0:
            lw = int(sec.get('LineWidth', 1))
            bw = int(sec.get('BorderWidth', 0))
            cols = [hexrgb(xpm['cols'][k]) for k in xpm['order']]
            if day:
                fill, border = cols[0], (cols[1] if len(cols) >= 2 and bw else None)
            else:
                fill = cols[2] if len(cols) == 4 else cols[-1]
                border = cols[3] if len(cols) == 4 else None
            draw_list.append((xy, lw, bw, fill, border))
        else:
            cmap, _, _ = pick_cols(xpm)
            draw_list.append((xy, None, None, cmap, xpm))
    # Ränder zuerst, damit Kreuzungen sauber aussehen
    for xy, lw, bw, fill, border in draw_list:
        if lw is not None and border is not None:
            dr.line(xy, fill=border, width=lw + 2 * bw, joint='curve')
    for xy, lw, bw, fill, extra in draw_list:
        if lw is not None:
            dr.line(xy, fill=fill, width=lw, joint='curve')
        else:
            cmap, xpm = fill, extra
            h = xpm['h']
            spos = 0.0
            for (ax, ay), (bx, by) in zip(xy, xy[1:]):
                L = math.hypot(bx - ax, by - ay)
                if L == 0:
                    continue
                ux, uy = (bx - ax) / L, (by - ay) / L
                nx, ny = -uy, ux
                t = 0.0
                while t < L:
                    col_i = int(spos + t) % 32
                    for rr in range(h):
                        c = cmap.get(xpm['rows'][rr][col_i])
                        if c:
                            off = rr - (h - 1) / 2.0
                            px = ax + ux * t + nx * off
                            py = ay + uy * t + ny * off
                            dr.point((round(px), round(py)), fill=c)
                    t += 0.5
                spos += L

    # Linienbeschriftung (einfach: Mitte der Linie)
    txtcol = (0, 0, 0, 255) if day else (230, 230, 230, 255)
    for typ_, coords, lab in (lines if a.labels == 'all' else []):
        sec = typ['line'].get(typ_, {})
        if not lab or sec.get('FontStyle', 'NoLabel') == 'NoLabel':
            continue
        c = coords[len(coords) // 2]
        x, y = P(c)
        col = hexrgb(sec.get('DayCustomColor' if day else 'NightCustomColor', '')) if sec.get('DayCustomColor') else txtcol
        dr.text((x, y - 14), lab, fill=col, font=fonts['SmallFont'], stroke_width=2,
                stroke_fill=bg)

    # Punkte
    for typ_, lon, lat, lab in pts:
        if typ_ in (0x6200, 0x6300) and lab.isdigit():
            lab = str(int(round(int(lab) * 0.3048)))  # Höhen-/Tiefenpunkt: Label in Fuss, Gerät zeigt Meter
        x, y = P((lon, lat))
        sec = typ['point'].get(typ_)
        if sec is None:
            dr.rectangle((x - 2, y - 2, x + 2, y + 2), fill=(255, 0, 255, 255))
            continue
        xpm = sec.get('DayXpm' if day else 'NightXpm') or sec.get('DayXpm')
        iw, ih = xpm['w'], xpm['h']
        for yy, row in enumerate(xpm['rows']):
            for xx, ch in enumerate(row):
                c = hexrgb(xpm['cols'][ch])
                if c:
                    dr.point((int(x - iw / 2 + xx), int(y - ih / 2 + yy)), fill=c)
        style = sec.get('FontStyle', 'SmallFont')
        if lab and style != 'NoLabel' and a.labels != 'none':
            col = hexrgb(sec.get('DayCustomColor' if day else 'NightCustomColor', '')) if sec.get('DayCustomColor') else txtcol
            dr.text((x + iw / 2 + 2, y - 7), lab, fill=col, font=fonts.get(style, fonts['SmallFont']),
                    stroke_width=2, stroke_fill=bg)

    dr.text((6, H - 18), 'Vorschau Ebene %d (Auflösung %d), %s – Helvetopo, Daten ©swisstopo' % (
        tile.levels[li]['level'], bits, 'Tag' if day else 'Nacht'), fill=txtcol, font=fonts['SmallFont'])
    img.convert('RGB').save(a.out)


if __name__ == '__main__':
    main()
