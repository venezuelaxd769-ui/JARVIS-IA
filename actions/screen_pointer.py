# -*- coding: utf-8 -*-
"""screen_pointer — "Magic Pointer" de Nia.

Lee dónde está el cursor y el contexto de la ventana activa, recorta la zona
alrededor del cursor en una captura y le pide a Gemini que diga QUÉ elemento
está apuntando. Sirve para que el Señor diga "esto", "esa parte", "esa
ventanita" y Nia sepa exactamente a qué se refiere sin que tenga que describir.

Reusa la infra de computer_use (mss + PIL + pyautogui) y la visión de
real_vision (misma API de Gemini). Nunca tira: si algo no está disponible,
responde con lo que sí sabe.
"""

import os
import subprocess
import time
from pathlib import Path

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import mss
except Exception:
    mss = None

try:
    from PIL import Image
except Exception:
    Image = None

_CAPTURES_DIR = Path.home() / "NiaSandbox" / "captures"
_DEFAULT_CROP = 460
_DESCRIBE_PROMPT = (
    "Estás mirando un recorte de pantalla centrado en la posición del cursor. "
    "Decime en QUÉ ELEMENTO está apuntando el cursor: qué es (botón, ícono, "
    "campo de texto, link, imagen, pestaña...), su texto o etiqueta si se lee, "
    "y si se ve resaltado o presionado. Respondé en español rioplatense, corto."
)


def _cursor():
    if pyautogui is None:
        return None
    try:
        return tuple(int(v) for v in pyautogui.position())
    except Exception:
        return None


def _screen_size():
    if pyautogui is not None:
        try:
            return tuple(int(v) for v in pyautogui.size())
        except Exception:
            pass
    return None


def _active_window() -> str:
    """Título de la ventana activa. Windows primero, Linux después."""
    if os.name == "nt":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if hwnd:
                length = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()
                if title:
                    return title
        except Exception:
            pass
    for cmd in (
        ["xdotool", "getactivewindow", "getwindowname"],
        ["wmctrl", "-a"],
    ):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    try:
        r = subprocess.run(
            ["hyprctl", "-j", "activewindow"], capture_output=True, text=True, timeout=3
        )
        if r.returncode == 0 and r.stdout.strip():
            import json
            data = json.loads(r.stdout)
            title = data.get("title", "")
            if title:
                return title
    except Exception:
        pass
    return ""


def _capture_crop(cx: int, cy: int, size: int):
    """Recorta un cuadrado de `size` px centrado en el cursor y lo guarda."""
    if mss is None or Image is None:
        return None
    screen = _screen_size()
    sw = screen[0] if screen else 1920
    sh = screen[1] if screen else 1080
    half = size // 2
    left = max(0, min(cx - half, sw - size))
    top = max(0, min(cy - half, sh - size))
    w = min(size, sw - left)
    h = min(size, sh - top)
    try:
        _CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = _CAPTURES_DIR / f"pointer_{stamp}.png"
        with mss.mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": w, "height": h})
            Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(out)
        return out
    except Exception:
        return None


def _describe(path) -> str:
    """Le pide a Gemini que diga qué hay en el recorte (reusa real_vision)."""
    try:
        from actions import real_vision

        _repo = Path(__file__).resolve().parent.parent
        keys = {}
        keys_path = _repo / "config" / "api_keys.json"
        if keys_path.exists():
            import json
            keys = json.loads(keys_path.read_text(encoding="utf-8"))
        api_key = keys.get("gemini_api_key", "")
        if not api_key:
            return ""
        b64 = real_vision._image_to_base64(str(path), max_size=1024)
        if not b64:
            return ""
        return real_vision._call_gemini_vision(b64, _DESCRIBE_PROMPT, api_key).strip()
    except Exception:
        return ""


def screen_pointer(parameters: dict, player=None) -> str:
    if pyautogui is None:
        return "El módulo de puntero no está disponible (no se pudo importar pyautogui)."

    action = (parameters or {}).get("action", "") or "pointer"

    if action == "window":
        title = _active_window()
        if not title:
            return "No pude identificar la ventana activa."
        pos = _cursor()
        pos_txt = f", cursor en ({pos[0]}, {pos[1]})" if pos else ""
        return f"Ventana activa: {title}{pos_txt}."

    pos = _cursor()
    if pos is None:
        return "No pude leer la posición del cursor."
    cx, cy = pos

    title = _active_window()
    size = int(parameters.get("size", _DEFAULT_CROP))
    size = max(200, min(900, size))

    path = None
    if mss is not None and Image is not None:
        path = _capture_crop(cx, cy, size)

    desc = ""
    if path:
        desc = _describe(path)

    win_line = f"Ventana activa: {title}." if title else ""
    if path is None:
        return f"{win_line} Cursor en ({cx}, {cy}). No pude capturar la zona."

    if desc and not desc.lower().startswith(("error", "no pude")):
        return (
            f"{win_line} Cursor en ({cx}, {cy}). "
            f"Recorte: {path}. Lo que hay bajo el cursor: {desc}"
        )

    return (
        f"{win_line} Cursor en ({cx}, {cy}). Recorte guardado en {path}. "
        f"La descripción específica no anduvo (motivo: {desc[:80] or 'desconocido'}); "
        "si lo necesito, puedo usar real_vision sobre ese recorte."
    )