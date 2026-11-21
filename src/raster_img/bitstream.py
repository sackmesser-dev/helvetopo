"""Garmin-Koordinaten-Bitstream (Polylinien/Polygone), Dekodierung nach QMapShack (CShiftReg)."""


def _nbits(base: int, signed: bool) -> int:
    n = 2 + (base if base <= 9 else 2 * base - 9)
    return n + (1 if signed else 0)


def decode_deltas(info: int, data: bytes, ext: bool = True):
    """info = Basisbyte, data = restliche Bytes. Gibt (Kopfinfo, [(dx, dy), ...]) zurück."""
    bfirst = data[0] if data else 0
    mask = 1
    sib = 2
    xsame = bool(bfirst & mask); mask <<= 1
    nx = False
    if xsame:
        nx = bool(bfirst & mask); mask <<= 1; sib += 1
    bx = _nbits(info & 0xF, not xsame)
    ysame = bool(bfirst & mask); mask <<= 1
    ny = False
    if ysame:
        ny = bool(bfirst & mask); mask <<= 1; sib += 1
    by = _nbits(info >> 4, not ysame)
    extra = False
    if ext:
        sib += 1
        if bfirst & mask:
            extra = True
            bx += 1
            by += 1
    bitlist = [(b >> i) & 1 for b in data for i in range(8)][sib:]
    pos = 0

    def take(n):
        nonlocal pos
        v = 0
        for i in range(n):
            v |= bitlist[pos + i] << i
        pos += n
        return v

    def coord(nb, has_sign, neg):
        if not has_sign:
            v = take(nb)
            return -v if neg else v
        sign = 1 << (nb - 1)
        acc = 0
        while True:
            if pos + nb > len(bitlist):
                raise EOFError
            t = take(nb)
            if t != sign:
                break
            acc += t - 1
        return acc + t if t < sign else t - 2 * sign - acc

    pts = []
    while len(bitlist) - pos >= bx + by:
        try:
            dx = coord(bx, not xsame, nx)
            dy = coord(by, not ysame, ny)
        except EOFError:
            break
        pts.append((dx, dy))
    return dict(bx=bx, by=by, xsame=xsame, nx=nx, ysame=ysame, ny=ny, extra=extra), pts
