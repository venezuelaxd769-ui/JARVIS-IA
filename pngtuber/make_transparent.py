"""make_transparent.py — Quita el fondo gris de las capas PNGTuber VT*.png

Usa flood-fill desde los bordes con tolerancia y convierte el fondo a transparente.
Guarda las versiones transparentes en pngtuber/transparent/.
"""
import sys
from pathlib import Path
from collections import deque

from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "transparent"
TOLERANCE = 12


def remove_background(src: Path, dst: Path, tol: int = TOLERANCE) -> int:
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.load()
    start = px[0, 0][:3]

    visited = bytearray(w * h)
    q = deque()
    for sx, sy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        visited[sy * w + sx] = 1
        q.append((sx, sy))

    removed = 0
    while q:
        x, y = q.popleft()
        r, g, b, a = px[x, y]
        if a > 0 and abs(r - start[0]) <= tol and abs(g - start[1]) <= tol and abs(b - start[2]) <= tol:
            px[x, y] = (r, g, b, 0)
            removed += 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not visited[ny * w + nx]:
                visited[ny * w + nx] = 1
                q.append((nx, ny))

    OUT.mkdir(parents=True, exist_ok=True)
    im.save(dst)
    return removed


def main() -> None:
    files = sorted(HERE.glob("VT*.png"))
    if not files:
        print("No hay VT*.png en", HERE)
        return 1
    for src in files:
        dst = OUT / (src.stem + "_transparent.png")
        n = remove_background(src, dst)
        im = Image.open(dst)
        total = im.width * im.height
        print(f"{src.name} -> {dst.name}  ({100 * n // total}% transparente)")
    print("Listo. Usá las versiones en pngtuber/transparent/ en Veadotube.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
