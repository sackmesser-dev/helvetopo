"""TRE-Header-Schlüssel (16 Byte ab TRE+0x9A), nach mkgmap MapValues / GarminImg CKeyGen."""


def tre_key(map_id: int, tre_hdr_len: int) -> bytes:
    def digit(i: int) -> int:
        return (map_id >> (4 * (7 - i))) & 0xF

    code = [0, 1, 0xF, 5, 0xD, 4, 7, 6, 0xB, 9, 0xE, 8, 2, 0xA, 0xC, 3]
    v = [[0] * 8 for _ in range(4)]
    for i in range(8):
        v[2][i ^ 1] = code[digit(i)]
    v[3] = list(v[2])
    v[0][0:4] = [digit(4) + v[3][0], digit(5) + v[3][1], digit(6) + v[3][2], digit(7) + v[3][3]]
    v[0][4:7] = v[3][4:7]
    v[0][7] = v[3][7] + 1
    v[1][0] = v[3][0]
    # Ergänzung zu mkgmap: bei TRE-Headern >= 0x100 Byte fliesst auch das dritte Nibble ein
    # (am Original mit Headerlänge 0x111 verifiziert).
    v[1][1] = v[3][1] + (tre_hdr_len >> 8)
    v[1][2] = (v[3][2] + (tre_hdr_len >> 4)) & 0xF
    v[1][3] = (v[3][3] + tre_hdr_len) & 0xF
    for k in range(4):
        v[1][4 + k] = v[3][4 + k] + digit(k)
    offset_map = [6, 7, 5, 11, 3, 10, 13, 12, 1, 15, 4, 14, 8, 0, 2, 9]
    off = offset_map[(digit(1) + digit(3) + digit(5) + digit(7)) & 0xF]
    out = b""
    for n in range(4):
        val = 0
        for i in range(8):
            val |= ((v[n][i] + off) & 0xF) << (4 * (7 - i))
        out += val.to_bytes(4, "little")
    return out
