"""decode_veado.py — Parser/decoder del formato .veado para entender la estructura real.

Uso: python decode_veado.py <archivo.veado>
"""
import struct
import sys


class Reader:
    def __init__(self, data, off=0):
        self.d = data
        self.o = off

    def u8(self):
        v = self.d[self.o]
        self.o += 1
        return v

    def u32(self):
        v = struct.unpack_from('<I', self.d, self.o)[0]
        self.o += 4
        return v

    def varint(self):
        shift = 0
        result = 0
        while True:
            b = self.u8()
            result |= (b & 0x7f) << shift
            if not (b & 0x80):
                return result
            shift += 7

    def string(self):
        n = self.varint()
        s = self.d[self.o:self.o + n].decode('utf-8', 'replace')
        self.o += n
        return s

    def f64(self):
        v = struct.unpack_from('<d', self.d, self.o)[0]
        self.o += 8
        return v

    def remaining(self):
        return self.d[self.o:]


def decode_effects(r: Reader, label: str):
    n = r.varint()
    print(f'    {label}: {n} entradas')
    for i in range(n):
        t = r.string()
        flags = r.u8()
        extra = ''
        if flags & 0x4:
            extra = f' preset custom id={r.u32()}'
        elif flags & 0x2:
            extra = f' preset="{r.string()}"'
        vc = r.varint()
        vals = [round(r.f64(), 4) for _ in range(vc)]
        print(f'      [{i}] {t} flags=0x{flags:x}{extra} valores={vals}')


def decode_shortcuts(r: Reader):
    n = r.varint()
    print(f'    shortcuts: {n} entradas')
    for i in range(n):
        prov = r.string()
        sig = r.string()
        print(f'      [{i}] provider={prov} signal={sig}')


def decode_msta(r: Reader, cid: int):
    name = r.string()
    flags = r.u8()
    thumb_closed, thumb_open, thumb_blclosed, thumb_blopen = r.u32(), r.u32(), r.u32(), r.u32()
    img_closed, img_open, img_blclosed, img_blopen = r.u32(), r.u32(), r.u32(), r.u32()
    print(f'  MSTA id={cid} nombre="{name}" flags=0x{flags:x}')
    print(f'    thumbs: closed={thumb_closed} open={thumb_open} blinkC={thumb_blclosed} blinkO={thumb_blopen}')
    print(f'    images: closed={img_closed} open={img_open} blinkC={img_blclosed} blinkO={img_blopen}')
    decode_effects(r, 'eff cerrada')
    decode_effects(r, 'eff abierta')
    decode_effects(r, 'trans cerrada->abierta')
    decode_effects(r, 'trans abierta->cerrada')
    decode_shortcuts(r)
    mode = self_u32(r)
    print(f'    shortcut mode FourCC: {mode!r}')


def self_u32(r):
    return struct.unpack_from('<I', r.d, r.o)[0]


def decode_aimg(r: Reader, cid: int):
    w = r.u32()
    h = r.u32()
    n = r.varint()
    loop = r.varint() if n > 1 else None
    frames = []
    for _ in range(n):
        abmp = r.u32()
        ox = r.u32()
        oy = r.u32()
        dur = r.f64()
        frames.append((abmp, ox, oy, dur))
    print(f'  AIMG id={cid} {w}x{h} frames={n} loop={loop} frames={frames}')


def decode_abmp(r: Reader, cid: int):
    w = r.u32()
    h = r.u32()
    fmt = r.d[r.o:r.o + 4].decode('ascii', 'replace')
    r.o += 4
    print(f'  ABMP id={cid} {w}x{h} format={fmt} resto={len(r.remaining())} bytes')


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else '/home/nautilos/.veadotube/data/mini/autosave.veado'
    data = open(path, 'rb').read()
    print('magic:', data[:9], '| primer byte:', hex(data[9]))
    off = 9
    while off + 12 <= len(data):
        cid, ctype, clen = struct.unpack_from('<I4sI', data, off)
        t = ctype.decode('ascii', 'replace')
        if cid == 0:
            break
        body = data[off + 12:off + 12 + clen]
        print(f'--- chunk id={cid} type={t} len={clen}')
        r = Reader(body)
        if t == 'META':
            print('  version:', repr(r.remaining()[:40]))
        elif t == 'MLST':
            vals = []
            for _ in range(len(body) // 4):
                vals.append(struct.unpack_from('<I', body, _ * 4)[0])
            print('  estado ids:', vals)
        elif t == 'MSTA':
            decode_msta(r, cid)
        elif t == 'AIMG':
            decode_aimg(r, cid)
        elif t == 'ABMP':
            decode_abmp(r, cid)
        elif t == 'ASFD':
            print('  ASFD:', r.remaining()[:60].hex())
        elif t in ('MEPL', 'MANL', 'THMB'):
            print(f'  ({t} len={clen})')
        else:
            print(f'  (tipo {t} sin decodificar, {clen} bytes)')
        off += 12 + clen


if __name__ == '__main__':
    main()
