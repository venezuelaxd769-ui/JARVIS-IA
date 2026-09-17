"""ambient_context.py — Contexto ambiental automático por turno.

Inspirado en AYO / Samuel / Cryp: antes de cada turno del usuario, Nia recoge
en silencio qué ventana está activa, la hora y un vistazo del portapapeles,
para "ya saber" en qué anda el usuario sin que se lo pidan y sin guardar nada.

Todo corre 100% local (ctypes en Windows, desktop_kb/xdotool en Linux,
pyperclip para el portapapeles con fallback al tool de acciones).
"""
import os
import shutil
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

MAX_CLIP = 160
MAX_WINDOW = 120
_MAX_CTX_LINES = 6


def _active_window_win() -> str:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()
    except Exception:
        return ""


def _active_window_linux() -> str:
    try:
        from actions.desktop_kb import get_active_window
        w = get_active_window()
        if isinstance(w, dict):
            return str(w.get("title") or w.get("name") or "")
        if w:
            return str(w)
    except Exception:
        pass
    exe = shutil.which("xdotool")
    if exe:
        try:
            out = subprocess.run(
                [exe, "getactivewindow", "getwindowname"],
                capture_output=True, timeout=3)
            if out.returncode == 0:
                return out.stdout.decode("utf-8", "replace").strip()
        except Exception:
            pass
    return ""


def _active_window() -> str:
    if sys.platform.startswith("win"):
        return _active_window_win()
    return _active_window_linux()


def _clipboard_preview() -> str:
    value = None
    try:
        import pyperclip
        value = pyperclip.paste()
    except Exception:
        value = None
    if value is None:
        try:
            from actions.clipboard import clipboard as _clip
            r = _clip({"action": "get"})
            if ":" in r:
                value = r.split(":", 1)[-1].strip()
        except Exception:
            value = None
    if not value:
        return ""
    text = " ".join(str(value).split())
    return text[:MAX_CLIP]


def get_ambient_state() -> dict:
    """Retorna el estado ambiental actual como dict (ventana, hora, clipboard)."""
    state = {"window": "", "time": "", "clipboard": ""}
    try:
        state["time"] = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
    except Exception:
        state["time"] = str(datetime.now())
    state["window"] = _active_window()[:MAX_WINDOW]
    state["clipboard"] = _clipboard_preview()
    return state


def build_ambient_context() -> str:
    """Retorna el bloque [CONTEXTO AMBIENTAL] listo para inyectar al modelo."""
    lines = [
        "[CONTEXTO AMBIENTAL — no lo respondas a esto, solo usalo para entender "
        "en qué está el usuario]"
    ]
    state = get_ambient_state()
    if state["time"]:
        lines.append(f"Fecha/hora: {state['time']}")
    if state["window"]:
        lines.append(f"Ventana activa: {state['window']}")
    if state["clipboard"]:
        lines.append(f"Portapapeles: {state['clipboard']}")
    return "\n".join(lines[: _MAX_CTX_LINES])


def ambient_context_action(parameters: dict, player=None) -> str:
    """Tool para Nia: genera el bloque de contexto ambiental del momento.

    Útil si Nia necesita saber 'en qué carpeta/archivo/ventana' está el usuario.
    Params opcionales: none (retorna el bloque formateado).
    """
    raw = str(parameters.get("raw", "")).strip().lower() in ("1", "true", "sí", "si", "raw")
    if raw:
        return str(get_ambient_state())
    return build_ambient_context()