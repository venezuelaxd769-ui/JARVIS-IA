import os, json, base64, urllib.request, urllib.error, time
from pathlib import Path
from actions.screen_capture import capture_screen

API_FILE = Path("config/api_keys.json")

_IDENTIFY_KEYWORDS = [
    "quien", "who is", "who's", "identifica", "identify",
    "reconoce", "recognize", "como se llama", "nombre", "name of",
    "personaje", "actor", "actriz", "famoso",
    "dime quien", "decime quien", "sabes quien",
]

_GEMINI_LAST_CALL = 0.0
_GEMINI_MIN_INTERVAL = 3.5


def _load_config() -> dict:
    if not API_FILE.exists():
        return {}
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _capture_screen_base64(save_path: Path = None) -> str:
    return capture_screen(save_path=save_path)


def _is_identify_query(query: str) -> bool:
    q = query.lower()
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "n"}
    for acc, plain in replacements.items():
        q = q.replace(acc, plain)
    return any(kw in q for kw in _IDENTIFY_KEYWORDS)


def _build_prompt(query: str) -> str:
    if _is_identify_query(query):
        return (
            f"Analizá esta imagen en detalle. {query}\n\n"
            "IMPORTANTE: Si hay una persona visible, decí SU NOMBRE COMPLETO. "
            "Si no estás segura, describí sus características físicas distintivas "
            "(color de pelo, ojos, vestimenta, rasgos faciales, contexto) y tu mejor estimación."
        )
    return f"Analizá esta imagen. {query}"


def _gemini_vision_rest(prompt: str, b64_image: str, gemini_key: str) -> str | None:
    global _GEMINI_LAST_CALL

    models = [
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
    ]
    for model in models:
        for attempt in range(3):
            elapsed = time.time() - _GEMINI_LAST_CALL
            if elapsed < _GEMINI_MIN_INTERVAL:
                time.sleep(_GEMINI_MIN_INTERVAL - elapsed)
            _GEMINI_LAST_CALL = time.time()
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                body = {
                    "contents": [{
                        "parts": [
                            {"text": prompt},
                            {"inline_data": {"mime_type": "image/jpeg", "data": b64_image}}
                        ]
                    }]
                }
                req = urllib.request.Request(
                    url, data=json.dumps(body).encode(),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30) as resp:
                    result = json.loads(resp.read())
                    if "candidates" in result and result["candidates"]:
                        parts = result["candidates"][0]["content"]["parts"]
                        texts = [p["text"] for p in parts if "text" in p]
                        if texts:
                            return texts[0].strip()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode()
                if "429" in str(e):
                    wait = 10 * (attempt + 1)
                    try:
                        import re
                        m = re.search(r'retry in (\d+\.?\d*)s', err_body)
                        if m:
                            wait = float(m.group(1)) + 1
                    except Exception:
                        pass
                    time.sleep(wait)
                    continue
                if "404" in str(e):
                    break
            except Exception:
                break
    return None


def _openrouter_vision(prompt: str, b64_image: str, api_key: str) -> str | None:
    models = [
        "google/gemini-2.5-flash",
        "google/gemma-4-31b-it:free",
        "nvidia/nemotron-nano-12b-v2-vl:free",
    ]
    for model in models:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                ]}]
            }
            req = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=45) as r:
                data = json.loads(r.read().decode())
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"]
        except Exception:
            continue
    return None


def screen_vision(parameters: dict, player=None) -> str:
    cfg = _load_config()
    provider = cfg.get("ai_provider", "gemini").lower().strip()
    gemini_key = cfg.get("gemini_api_key", "").strip()
    openrouter_key = cfg.get("openrouter_api_key", "").strip()

    query = parameters.get("query") or parameters.get("text") or parameters.get("question") or "¿Qué ves en mi pantalla?"
    action = parameters.get("action", "describe").lower().strip()
    img_path = Path("config/last_captured_screen.png")

    if player:
        player.write_log("Capturando pantalla para an&aacute;lisis...")

    try:
        b64_image = _capture_screen_base64(save_path=img_path)
    except Exception as e:
        return f"Error al capturar la pantalla: {e}"

    prompt = _build_prompt(query)

    errors = []

    if provider == "gemini" and gemini_key:
        if player:
            player.write_log("Analizando con Google Gemini...")
        result = _gemini_vision_rest(prompt, b64_image, gemini_key)
        if result:
            return result
        errors.append("Gemini: todas las variantes agotadas o rate-limited")

    if provider == "openrouter" and openrouter_key:
        if player:
            player.write_log("Analizando con OpenRouter...")
        result = _openrouter_vision(prompt, b64_image, openrouter_key)
        if result:
            return result
        errors.append("OpenRouter: todos los modelos fallaron")

    if provider != "gemini" and gemini_key:
        if player:
            player.write_log("Fallback a Gemini...")
        result = _gemini_vision_rest(prompt, b64_image, gemini_key)
        if result:
            return result

    if provider != "openrouter" and openrouter_key:
        if player:
            player.write_log("Fallback a OpenRouter...")
        result = _openrouter_vision(prompt, b64_image, openrouter_key)
        if result:
            return result

    err_report = "\n- ".join(errors) if errors else "Ningún proveedor configurado."
    return (
        f"No se pudo procesar la imagen:\n- {err_report}\n\n"
        "Verific&aacute; tu configuraci&oacute;n de IA."
    )
