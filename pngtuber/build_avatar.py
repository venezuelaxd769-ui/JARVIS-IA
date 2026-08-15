"""build_avatar.py — Genera el avatar .veado de Nia para Veadotube Mini.

Toma las 4 capas VT1-4.png (boca cerrada/abierta × ojos abiertos/cerrados) y
construye un archivo de avatar Mini con un estado "Normal".

Estructura: réplica del layout real de autosave.veado (veadotube mini 2.2):
  - Chunks: id(u32 LE) + FourCC + len(u32 LE) + data
  - MSTA: nombre, flags, 8 refs big-endian (4 thumbs + 4 imgs), efectos
  - AIMG/ABMP: texturas RAW. (RGBA, bottom-to-top, left-to-right)

Uso: python build_avatar.py [destino.veado]
"""
import io
import struct
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
DEFAULT_SRC = HERE / "VT1.png"
DEFAULT_DST = Path.home() / ".veadotube" / "data" / "mini" / "autosave.veado"

IMAGE_SIZE = 600
THUMB_SIZE = 120


class Writer:
    def __init__(self):
        self.buf = bytearray()

    def u8(self, v):
        self.buf += struct.pack('<B', v)

    def u32(self, v):
        self.buf += struct.pack('<I', v)

    def varint(self, v):
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                self.buf.append(b | 0x80)
            else:
                self.buf.append(b)
                return

    def string(self, s):
        b = s.encode('utf-8')
        self.varint(len(b))
        self.buf += b

    def f64(self, v):
        self.buf += struct.pack('<d', v)

    def bytes(self, b):
        self.buf += b


def raw_rgba(img: Image.Image) -> bytes:
    """Convierte imagen a textura RAW. (RGBA, bottom-to-top)."""
    img = img.convert('RGBA')
    w, h = img.size
    rows = []
    for y in range(h - 1, -1, -1):
        for x in range(w):
            r, g, b, a = img.getpixel((x, y))
            rows.append(bytes((r, g, b, a)))
    return b''.join(rows)


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert('RGBA').save(buf, format='PNG')
    return buf.getvalue()


def build_chunk(cid: int, ctype: str, data: bytes) -> bytes:
    return struct.pack('<I4sI', cid, ctype.encode('ascii'), len(data)) + data


def main():
    dst = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DST
    srcs = [Path(HERE / f"VT{n}.png") for n in (1, 2, 3, 4)]
    for s in srcs:
        if not s.exists():
            print(f"Falta {s}")
            return 1

    imgs = [Image.open(s) for s in srcs]

    # ── leer MSTA original para conservar efectos del estado ───────────────
    ref = DEFAULT_DST
    ref_msta = None
    if ref.exists():
        data = ref.read_bytes()
        off = 9
        while off + 12 <= len(data):
            cid, ctype, clen = struct.unpack_from('<I4sI', data, off)
            if ctype == b'MSTA':
                ref_msta = data[off + 12:off + 12 + clen]
                break
            if cid == 0:
                break
            off += 12 + clen

    # ── MSTA: nombre "Normal", refs iguales, efectos originales ────────────
    # layout: varint nombre, 1 flag, 8 refs BE (thumbs+imgs), luego efectos
    if ref_msta is None:
        print("No encontré MSTA de referencia; generando estado sin efectos.")
        msta = Writer()
        msta.string("Normal")
        msta.u8(0x02)
        # thumbC thumbO thumbBC thumbBO imgC imgO imgBC imgBO (BE)
        for v in (43, 28, 32, 36, 41, 26, 30, 34):
            msta.buf += struct.pack('>I', v)
        msta.varint(0)   # eff cerrada
        msta.varint(0)   # eff abierta
        msta.varint(0)   # trans C->O
        msta.varint(0)   # trans O->C
        msta.varint(0)   # shortcuts
        msta.bytes(b'PRES')
        msta_data = bytes(msta.buf)
    else:
        # copiar byte a byte y reemplazar el nombre "aaAAA!" por "Normal"
        msta_data = ref_msta
        old_name = b'\x06aaAAA!'
        if msta_data.startswith(old_name):
            msta_data = b'\x06Normal' + msta_data[len(old_name):]
        else:
            print("⚠ MSTA de referencia inesperado; usando como está (revisar nombre).")

    # ── thumbnails y texturas ───────────────────────────────────────────────
    thumbs = [img.resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS) for img in imgs]
    full = [(img.size == (IMAGE_SIZE, IMAGE_SIZE)) and img for img in imgs]
    for i, img in enumerate(full):
        if not img:
            print(f"VT{i+1}.png no es {IMAGE_SIZE}x{IMAGE_SIZE}, se ajusta.")
            full[i] = imgs[i].resize((IMAGE_SIZE, IMAGE_SIZE), Image.LANCZOS)

    thumb_abmp = [44, 29, 33, 37]   # ids ABMP para thumbs
    img_abmp = [42, 27, 31, 35]     # ids ABMP para imágenes

    # ── AIMG chunks (thumbnails: ids 43,28,32,36) ──────────────────────────
    aimg_thumb_ids = [43, 28, 32, 36]
    aimg_img_ids = [41, 26, 30, 34]

    def aimg(w, h, abmp_id):
        w_buf = Writer()
        w_buf.u32(w)
        w_buf.u32(h)
        w_buf.varint(1)          # frame count
        w_buf.u32(abmp_id)
        w_buf.u32(0)             # offset X
        w_buf.u32(0)             # offset Y
        w_buf.f64(0.0)           # frame duration
        return bytes(w_buf.buf)

    # ── ABMP chunks ────────────────────────────────────────────────────────
    def abmp(img, w, h):
        raw = raw_rgba(img.resize((w, h), Image.LANCZOS))
        return struct.pack('<I', w) + struct.pack('<I', h) + b'RAW.' + raw

    chunks = bytearray()

    # META (constante, réplica del original)
    chunks += build_chunk(1, 'META', b'\x12veadotube mini 1.4\x00\x00')
    # MLST: un solo estado (id 3)
    chunks += build_chunk(2, 'MLST', struct.pack('<I', 3))
    # MEPL: vacío
    chunks += build_chunk(38, 'MEPL', b'')
    # THMB: preview del avatar (PNG 128x128 de VT1)
    chunks += build_chunk(21, 'THMB', png_bytes(thumbs[0].resize((128, 128), Image.LANCZOS)))
    # MANL: vacío
    chunks += build_chunk(39, 'MANL', b'')
    # ASFD: lista de imágenes (compat 2.0/2.1)
    asfd = Writer()
    asfd.bytes(b'MINI')
    for aid in aimg_thumb_ids + aimg_img_ids:
        asfd.string(f"image{aid:08X}")
        asfd.u32(aid)
        asfd.u8(0)
    chunks += build_chunk(40, 'ASFD', bytes(asfd.buf))
    # MSTA: estado "Normal"
    chunks += build_chunk(3, 'MSTA', msta_data)
    # AIMG + ABMP: thumbs
    for i, (aid, tid, tabid) in enumerate(zip(aimg_thumb_ids, thumbs, thumb_abmp)):
        chunks += build_chunk(aid, 'AIMG', aimg(THUMB_SIZE, THUMB_SIZE, tabid))
        chunks += build_chunk(tabid, 'ABMP', abmp(tid, THUMB_SIZE, THUMB_SIZE))
    # AIMG + ABMP: imágenes full
    for i, (aid, fid, fiabid) in enumerate(zip(aimg_img_ids, full, img_abmp)):
        chunks += build_chunk(aid, 'AIMG', aimg(IMAGE_SIZE, IMAGE_SIZE, fiabid))
        chunks += build_chunk(fiabid, 'ABMP', abmp(fid, IMAGE_SIZE, IMAGE_SIZE))

    out = b'VEADOTUBE' + bytes(chunks)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out)
    print(f"✔ Avatar escrito en {dst} ({len(out)/1024/1024:.1f} MB)")
    print("  Estado: Normal | 4 imágenes 600x600 + 4 thumbs 120x120")
    return 0


if __name__ == '__main__':
    sys.exit(main())
