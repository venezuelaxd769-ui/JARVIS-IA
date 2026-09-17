"""screen_capture.py — Captura de pantalla multiplataforma (mss + PIL).

Fuente de reemplazo del módulo .pyc original (Linux/Hyprland): el guardado en
un .py con el mismo nombre tiene precedencia sobre el .pyc (AGENTS.md).
API compatible: capture_screen(save_path=None, max_size=None) -> base64 PNG.
"""
import base64
import io
from pathlib import Path

import numpy as np
from PIL import Image

import mss


def capture_screen(save_path=None, max_size=None):
    """Captura el monitor primario y devuelve la imagen en base64 (PNG).

    save_path (opcional): si se pasa, además guarda el PNG en esa ruta.
    max_size (opcional): si se pasa, escala la imagen a ese ancho/alto máx.
    """
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        shot = sct.grab(monitor)

    pil = Image.frombytes("RGB", shot.size, shot.rgb)
    if max_size is not None:
        try:
            size = max_size[0:2] if isinstance(max_size, (tuple, list)) else (int(max_size), int(max_size))
            pil.thumbnail(size, Image.Resampling.LANCZOS)
        except Exception:
            pass

    buf = io.BytesIO()
    pil.save(buf, format="PNG")

    if save_path is not None:
        try:
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_bytes(buf.getvalue())
        except Exception:
            pass

    return base64.b64encode(buf.getvalue()).decode("ascii")