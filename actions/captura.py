# -*- coding: utf-8 -*-
"""captura.py — Captura de pantalla por voz.

Usa mss (rápido en Windows) con fallback a Pillow ImageGrab. Guarda el PNG
en ~/NiaSandbox/captures/ y devuelve la ruta con la fecha y el tamaño.
"""
import os
import time
from datetime import datetime

_FOLDER = os.path.join(os.path.expanduser("~"), "NiaSandbox", "captures")


def _mss_grab():
    import mss
    with mss.mss() as sct:
        img = sct.grab(sct.monitors[0])
    return img


def captura(parameters: dict, player=None, speak=None) -> str:
    """Saca una captura de pantalla completa y la guarda como PNG."""
    action = str(parameters.get("action", "capturar")).strip().lower()
    if action in ("test", "chequear"):
        try:
            import mss  # noqa: F401
            return "Listo, puedo sacar capturas de pantalla."
        except Exception:
            return "No pude cargar la librería de capturas (mss)."
    if action not in ("capturar", "guardar", "sacar"):
        return "Acciones: capturar | test."
    try:
        os.makedirs(_FOLDER, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_FOLDER, f"captura_{stamp}.png")
        try:
            img = _mss_grab()
            from PIL import Image
            img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
        except Exception:
            from PIL import ImageGrab
            img = ImageGrab.grab()
        img.save(path, "PNG")
        size = os.path.getsize(path)
        kb = round(size / 1024, 1)
        if player:
            player.write_log(f"📸 Captura guardada: {path} ({kb} KB)")
        return f"Listo, guardé la captura en {path}, pesa {kb} kilobytes."
    except Exception as e:
        return f"No pude sacar la captura: {e}."