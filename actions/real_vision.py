"""real_vision.py — Visión real: envía imágenes a Gemini para análisis.

Toma una imagen (archivo o screenshot), la convierte a base64,
y la envía a Gemini Vision para que "la vea" y la describa/analice.
La herramienta más cercana a lo que yo puedo hacer con imágenes.
"""
import base64
import io
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _capture_screen():
    """Captura pantalla con grim (Wayland) o scrot (X11)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=str(_REPO / ".tmp"))
    os.makedirs(os.path.dirname(tmp.name), exist_ok=True)
    tmp.close()
    for cmd in [
        ["grim", tmp.name],
        ["scrot", tmp.name],
        ["import", "-window", "root", tmp.name],
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=5)
            if result.returncode == 0 and os.path.getsize(tmp.name) > 1000:
                return tmp.name
        except Exception:
            continue
    return None


def _image_to_base64(path, max_size=1024):
    """Convierte imagen a base64, redimensionando si es necesario."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            # Redimensionar si es muy grande
            if max(img.size) > max_size:
                ratio = max_size / max(img.size)
                new_size = (int(img.width * ratio), int(img.height * ratio))
                img = img.resize(new_size, Image.LANCZOS)
            # Convertir a RGB si es necesario
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode()
    except ImportError:
        pass

    # Fallback sin Pillow: leer raw y enviar tal cual
    with open(path, "rb") as f:
        raw = f.read(5_000_000)
    return base64.b64encode(raw).decode()


def _call_gemini_vision(image_b64, prompt, api_key, models=None, retries=3):
    """Envía imagen a Gemini Vision API, probando varios modelos y reintentando
    ante 429/5xx (alta demanda), por si uno se depreca o se congestiona."""
    import urllib.request

    models = models or [
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    ]

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_b64,
                }},
            ]
        }],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048,
        },
    }

    data = json.dumps(payload).encode("utf-8")
    last_error = None
    for model in models:
        for attempt in range(retries):
            if attempt > 0:
                time.sleep(2 * attempt)
            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={api_key}")
            req = urllib.request.Request(url, data=data, headers={
                "Content-Type": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    result = json.loads(resp.read().decode())
                    candidates = result.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        text = "".join(p.get("text", "") for p in parts)
                        if text.strip():
                            return text
                    return "Gemini no devolvió contenido."
            except urllib.error.HTTPError as e:
                last_error = e
                # 429/5xx = congestión de modelo → reintentar con otro modelo/backoff
                if e.code in (429, 500, 502, 503):
                    continue
                # 4xx determinista (modelo no disponible) → probar siguiente modelo
                break
            except Exception as e:
                last_error = e
                continue
    return f"Error llamando a Gemini Vision: {last_error}"


def real_vision(parameters: dict, player=None) -> str:
    """Envía una imagen a Gemini para que la analice."""
    path = str(parameters.get("path", "")).strip()
    prompt = str(parameters.get("prompt", "Describí esta imagen en detalle.")).strip()
    use_screenshot = str(parameters.get("screenshot", "")).lower() == "true"
    max_size = int(parameters.get("max_size", 1024))

    # Obtener API key
    api_key = None
    keys_path = _REPO / "config" / "api_keys.json"
    if keys_path.exists():
        try:
            keys = json.loads(keys_path.read_text(encoding="utf-8"))
            api_key = keys.get("gemini_api_key", "")
        except Exception:
            pass

    if not api_key:
        return "No encontré la API key de Gemini en config/api_keys.json."

    # Obtener imagen
    if use_screenshot:
        if player:
            player.write_log("📸 Capturando pantalla...")
        path = _capture_screen()
        if not path:
            return "No pude capturar la pantalla."
        cleanup = True
    elif path:
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            return f"Imagen no encontrada: {path}"
        cleanup = False
    else:
        return "Necesito una ruta de imagen o screenshot=true."

    if player:
        player.write_log(f"👁️ Analizando imagen con Gemini...")

    try:
        image_b64 = _image_to_base64(path, max_size=max_size)
        if not image_b64:
            return "No pude procesar la imagen."
        result = _call_gemini_vision(image_b64, prompt, api_key)
    finally:
        if cleanup and path and os.path.exists(path):
            try:
                os.unlink(path)
            except Exception:
                pass

    return f"👁️ Análisis de imagen:\n\n{result}"
