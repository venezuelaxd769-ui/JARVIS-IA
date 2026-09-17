# -*- coding: utf-8 -*-
"""describe_screen.py — "Mirá lo que veo" de Nia.

Captura la pantalla completa (Windows via mss; fallback grim/scrot/import en
Linux), junta el contexto de cursor + ventana activa (reusa screen_pointer) y
le pide a Gemini que describa lo que ve como se lo diría al Señor, en
rioplatense. Nunca tira: si falta una pieza, responde con lo que sí sabe.
"""

import os
import time
from pathlib import Path

try:
    import mss
except Exception:
    mss = None

try:
    from PIL import Image
except Exception:
    Image = None

try:
    import pyautogui
except Exception:
    pyautogui = None

_CAPTURES_DIR = Path.home() / "NiaSandbox" / "captures"
_PROMPT = (
    "Sos Nia, un asistente de escritorio. El Señor te pidió 'mirá lo que veo'."
    " Describí en español rioplatense, natural y breve (2-4 frases), qué estás "
    "viendo en esta captura de pantalla: qué aplicaciones hay, qué ventana es la "
    "activa, y si hay algo notable (un video, un resultado, un error, texto grande)."
    " No inventes nada a partir de lo que no se ve, y no menciones que es una imagen."
)


def _active_window():
    try:
        from actions.screen_pointer import _active_window
        return _active_window()
    except Exception:
        return ""


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


def _capture_full():
    """Captura la pantalla completa. Windows con mss; Linux con grim/scrot."""
    import tempfile

    if mss is not None and Image is not None:
        try:
            _CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S")
            out = _CAPTURES_DIR / f"screen_{stamp}.png"
            with mss.mss() as sct:
                shot = sct.grab(sct.monitors[1])
                Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(out)
            return out
        except Exception:
            pass

    try:
        from actions.real_vision import _capture_screen
        path = _capture_screen()
        if path:
            return Path(path)
    except Exception:
        pass
    return None


def _capture_cursor(size):
    try:
        from actions.screen_pointer import _capture_crop
        pos = _cursor()
        if pos is None:
            return None, None
        return _capture_crop(pos[0], pos[1], size), pos
    except Exception:
        return None, None


def _describe(path: Path, extra_ctx: str) -> str:
    try:
        from actions.real_vision import _call_gemini_vision, _image_to_base64
        import json

        _repo = Path(__file__).resolve().parent.parent
        keys = {}
        keys_path = _repo / "config" / "api_keys.json"
        if keys_path.exists():
            keys = json.loads(keys_path.read_text(encoding="utf-8"))
        api_key = keys.get("gemini_api_key", "")
        if not api_key:
            return ""
        b64 = _image_to_base64(str(path), max_size=1024)
        if not b64:
            return ""
        prompt = _PROMPT
        if extra_ctx:
            prompt = extra_ctx + "\n\n" + _PROMPT
        return _call_gemini_vision(b64, prompt, api_key).strip()
    except Exception:
        return ""


def describe_screen(parameters: dict, player=None) -> str:
    zone = str(parameters.get("zone", "screen")).lower().strip()
    size = int(parameters.get("size", 460))
    size = max(200, min(900, size))

    title = _active_window()
    pos = _cursor()

    if zone in ("window", "ventana"):
        if title:
            pos_txt = f", cursor en ({pos[0]}, {pos[1]})" if pos else ""
            return f"La ventana activa es: {title}{pos_txt}."
        return "No pude identificar la ventana activa."

    if zone in ("cursor", "puntero"):
        if pyautogui is None:
            return "El módulo de puntero no está disponible (no se pudo importar pyautogui)."
        if pos is None:
            return "No pude leer la posición del cursor."
        path, _ = _capture_cursor(size)
        if path is None:
            return f"No pude capturar la zona del cursor. La ventana activa es: {title}"
        desc = _describe(path, f"Ventana activa: {title}.") if title else _describe(path, "")
        if desc:
            return desc
        return (f"Ventana activa: {title}. Cursor en ({pos[0]}, {pos[1]}). "
                "El recorte anduvo pero la descripción específica falló.")

    # default: pantalla completa
    if player:
        try:
            player.write_log("📸 Mirando la pantalla...")
        except Exception:
            pass
    path = _capture_full()
    if path is None:
        base = f"Ventana activa: {title}." if title else ""
        pos_txt = f" Cursor en ({pos[0]}, {pos[1]})." if pos else ""
        return (f"{base}{pos_txt} No pude capturar la pantalla completa para describirla.")

    ctx = f"Ventana activa: {title}." if title else ""
    if pos:
        ctx += f" El cursor está en ({pos[0]}, {pos[1]})."
    desc = _describe(path, ctx)
    if desc:
        return desc
    return (f"Ventana activa: {title}. La captura se guardó en {path} "
            "pero la descripción no anduvo; usá real_vision sobre ese archivo si querés.")


def _cleanup(path: Path) -> None:
    try:
        if path and path.exists():
            path.unlink()
    except Exception:
        pass