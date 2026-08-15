import json
import urllib.request
import urllib.error
import base64
import re
import time
from pathlib import Path
from actions.screen_capture import capture_screen
from actions.gesture_engine import _mouse_move_to, _click

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"

def _get_api_key() -> str:
    if not API_FILE.exists(): return ""
    try:
        data = json.loads(API_FILE.read_text(encoding="utf-8"))
        return data.get("openrouter_api_key", "")
    except: return ""

def _ask_vision(prompt: str, img_b64: str, api_key: str, max_tokens: int = 300) -> str:
    payload = {
        "model": "google/gemini-2.5-flash",
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                ]
            }
        ]
    }
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/jarvis-beta",
        "X-Title": "JARVIS UI Automation",
        "Content-Type": "application/json"
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        response_data = json.loads(response.read().decode("utf-8"))
        if "choices" in response_data and len(response_data["choices"]) > 0:
            return response_data["choices"][0]["message"]["content"].strip()
        return ""

def _click_at(x: int, y: int):
    _mouse_move_to(x, y)
    time.sleep(0.3)
    _click('left')

def _has_page_changed(before_b64: str, api_key: str, element_desc: str) -> bool:
    after_b64 = capture_screen(max_size=None)
    from PIL import Image
    import io
    after_img = Image.open(io.BytesIO(base64.b64decode(after_b64)))
    after_buf = io.BytesIO()
    after_img.save(after_buf, format="JPEG", quality=75)
    after_img_b64 = base64.b64encode(after_buf.getvalue()).decode("utf-8")

    check_prompt = (
        f"Te mostré la pantalla ANTES de hacer clic en '{element_desc}' y AHORA después del clic. "
        "¿El contenido cambió? ¿Se ve un video diferente reproduciéndose? "
        "Respondé SOLO 'SI' si el clic funcionó y la página cambió, o 'NO' si sigue igual."
    )

    payload = {
        "model": "google/gemini-2.5-flash",
        "max_tokens": 10,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": check_prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{before_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{after_img_b64}"}}
                ]
            }
        ]
    }
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://github.com/jarvis-beta",
        "X-Title": "JARVIS UI Automation",
        "Content-Type": "application/json"
    }
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            answer = data["choices"][0]["message"]["content"].strip().upper()
            return answer.startswith("S")
    except:
        return True

def visual_click(parameters: dict, player=None) -> str:
    element_desc = parameters.get("element_description", "")
    if not element_desc:
        return "Error: No se especificó el elemento a cliquear."

    api_key = _get_api_key()
    if not api_key:
        return "Error: No se encontró openrouter_api_key en config/api_keys.json."

    from PIL import Image
    import io

    if player:
        player.write_log(f"visual_click: buscando '{element_desc}'...")

    try:
        b64_large = capture_screen(max_size=None)
        raw_bytes = base64.b64decode(b64_large)
        img = Image.open(io.BytesIO(raw_bytes))
        orig_w, orig_h = img.size

        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        prompt = (
            f"Localizá el centro EXACTO del área cliqueable del elemento '{element_desc}'. "
            f"La imagen mide exactamente {orig_w}x{orig_h} píxeles. "
            "Buscá el centro del link, botón o miniatura que representa ese elemento. "
            "DEBES devolver ÚNICA Y EXCLUSIVAMENTE un array JSON [X, Y] con las coordenadas en píxeles de la imagen. "
            "Nada más, sin texto, sin markdown, sin explicación. "
            "Si el elemento no existe, devolvé []."
        )

        raw_text = _ask_vision(prompt, img_b64, api_key)
        if not raw_text:
            return "Error: Sin respuesta del modelo de visión."

        match = re.search(r"\[\s*\d+\s*,\s*\d+\s*\]", raw_text)
        if not match:
            if "[]" in raw_text:
                return f"No se encontró '{element_desc}' en la pantalla."
            return f"No se pudieron obtener coordenadas. Respuesta: {raw_text}"

        coords = json.loads(match.group(0))
        click_x, click_y = coords[0], coords[1]

        click_x = max(0, min(click_x, orig_w - 1))
        click_y = max(0, min(click_y, orig_h - 1))

        if player:
            player.write_log(f"visual_click: coordenadas obtenidas ({click_x}, {click_y}), ejecutando clic...")

        _click_at(click_x, click_y)

        time.sleep(1.0)

        if player:
            player.write_log("visual_click: verificando si el clic funcionó...")

        if not _has_page_changed(img_b64, api_key, element_desc):
            if player:
                player.write_log("visual_click: primer intento falló, reintentando con ajustes...")

            found = False
            offsets = [(0, 20), (0, -20), (20, 0), (-20, 0), (0, 40), (0, -40)]
            for dx, dy in offsets:
                tx = max(0, min(click_x + dx, orig_w - 1))
                ty = max(0, min(click_y + dy, orig_h - 1))
                _click_at(tx, ty)
                time.sleep(1.0)
                if _has_page_changed(img_b64, api_key, element_desc):
                    click_x, click_y = tx, ty
                    found = True
                    break

            if not found:
                return (f"Se intentó hacer clic en '{element_desc}' en ({click_x}, {click_y}) "
                        "pero la página no cambió. Quizás el video no es cliqueable o necesitás especificar mejor.")

        return f"Clic visual ejecutado en '{element_desc}' (coordenadas: X={click_x}, Y={click_y})."

    except Exception as e:
        return f"Error en visual_click: {str(e)}"
