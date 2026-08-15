# -*- coding: utf-8 -*-
"""
vision_guardian.py — Premium active screen monitoring and contextual suggestion agent for JARVIS.
"""
import os
import json
import time
import base64
import threading
import traceback
import urllib.request
import urllib.error
from pathlib import Path
from PIL import Image
import io
from actions.screen_capture import capture_screen

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
STATE_FILE = CONFIG_DIR / "vision_guardian_state.json"
API_FILE = CONFIG_DIR / "api_keys.json"

_inject_fn = None
_speaking_fn = None
_loop_thread = None
_running = False

def _load_config() -> dict:
    if not API_FILE.exists():
        return {}
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _load_state() -> dict:
    if not STATE_FILE.exists():
        # Default state: disabled by default, check every 45s
        return {"enabled": False, "interval": 45}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": False, "interval": 45}

def _save_state(state: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")

def _capture_screen_base64() -> str:
    return capture_screen()

def _try_ollama(cfg: dict, query: str, b64_image: str):
    ollama_url = cfg.get("ollama_url", "http://127.0.0.1:11434").strip().rstrip("/")
    ollama_model = cfg.get("ollama_model", "phi3").strip()
    url = f"{ollama_url}/api/chat"
    payload = {
        "model": ollama_model,
        "messages": [{"role": "user", "content": query, "images": [b64_image]}],
        "options": {"temperature": 0.1, "num_predict": 30},
        "stream": False,
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        resp_data = json.loads(response.read().decode("utf-8"))
        if "message" in resp_data and "content" in resp_data["message"]:
            return resp_data["message"]["content"].strip()
    return None


def _try_gemini(cfg: dict, query: str, b64_image: str):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=cfg.get("gemini_api_key", "").strip())
    raw_bytes = base64.b64decode(b64_image)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(parts=[
                types.Part(text=query),
                types.Part(inline_data=types.Blob(data=raw_bytes, mime_type="image/jpeg")),
            ])
        ],
    )
    res_text = response.text
    return res_text.strip() if res_text and res_text.strip() else None


def _try_openrouter(cfg: dict, query: str, b64_image: str):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {cfg.get('openrouter_api_key', '').strip()}",
        "HTTP-Referer": "https://github.com/jarvis-beta",
        "X-Title": "JARVIS Proactive Vision Guardian",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "google/gemini-2.5-flash",
        "max_tokens": 150,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": query},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}},
                ],
            }
        ],
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as response:
        resp_data = json.loads(response.read().decode("utf-8"))
        if "choices" in resp_data and len(resp_data["choices"]) > 0:
            return resp_data["choices"][0]["message"]["content"].strip()
    return None


def _perform_vision_analysis() -> str:
    """Takes screenshot and queries Gemini, OpenRouter or Ollama Local for proactive alerts.

    Prueba el proveedor configurado primero y, si falla (p. ej. 402 sin crédito en
    OpenRouter), hace fallback automático a los demás proveedores con clave válida.
    """
    cfg = _load_config()
    preferred = cfg.get("ai_provider", "gemini").lower().strip()
    gemini_key = cfg.get("gemini_api_key", "").strip()
    openrouter_key = cfg.get("openrouter_api_key", "").strip()

    # Orden de intento: proveedor preferido primero, luego los demás con clave.
    order = [preferred, "gemini", "openrouter", "ollama"]
    seen = set()
    providers = [p for p in order if p not in seen and not seen.add(p)]
    providers = [p for p in providers if p != preferred]  # no duplicar preferido
    providers = [preferred] + providers
    providers = [p for p in providers if p in ("gemini", "openrouter", "ollama")]
    providers = [p for p in providers
                 if (p == "gemini" and gemini_key)
                 or (p == "openrouter" and openrouter_key)
                 or p == "ollama"]

    try:
        b64_image = _capture_screen_base64()
    except Exception as e:
        print(f"[Guardian] Error capturing screen: {e}")
        return "NORMAL"

    query = (
        "Eres el Guardián de Visión de JARVIS. Analiza esta captura de pantalla del usuario. "
        "Si encuentras un error crítico en una terminal, un aviso importante, un mensaje urgente de chat "
        "o si el usuario está claramente atascado o necesita ayuda contextual inmediata en lo que está haciendo, "
        "genera una sugerencia o aviso súper conciso, directo e inteligente en español de MÁXIMO 12 palabras. "
        "Si todo está normal, no hay errores, alertas urgentes ni oportunidades de ayuda contextual inmediata, "
        "responde ÚNICAMENTE con la palabra 'NORMAL' y nada más. Sé sumamente selectivo."
    )

    last_err = ""
    for provider in providers:
        try:
            if provider == "ollama":
                res = _try_ollama(cfg, query, b64_image)
            elif provider == "gemini":
                res = _try_gemini(cfg, query, b64_image)
            else:
                res = _try_openrouter(cfg, query, b64_image)
            if res:
                return res
            last_err = f"{provider}: sin respuesta"
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = f"{provider}: HTTP {e.code} {body[:120]}"
            if e.code in (401, 402, 403):
                print(f"[Guardian] {last_err} → probando siguiente proveedor...")
                continue
            # Otros errores (429, 5xx): intentar el siguiente proveedor igualmente.
            continue
        except Exception as e:
            last_err = f"{provider}: {e}"
            continue

    if last_err:
        print(f"[Guardian] Todos los proveedores fallaron: {last_err}")
    return "NORMAL"

def _guardian_loop():
    global _running, _inject_fn, _speaking_fn
    print("[Guardian] Thread loop started successfully.")
    
    while _running:
        try:
            state = _load_state()
            enabled = state.get("enabled", False)
            interval = int(state.get("interval", 45))
            if interval < 10: interval = 10
            
            # Simple sleep intervals
            for _ in range(interval):
                if not _running:
                    return
                time.sleep(1.0)

            if enabled and _inject_fn and _speaking_fn:
                # Avoid injecting text if JARVIS is already talking
                is_speaking = False
                try:
                    is_speaking = _speaking_fn()
                except Exception:
                    pass

                if not is_speaking:
                    print("[Guardian] Performing proactive screen check...")
                    result = _perform_vision_analysis()
                    
                    # Clean response
                    res_clean = result.replace("'", "").replace('"', '').strip()
                    if res_clean and "normal" not in res_clean.lower() and len(res_clean) > 3:
                        print(f"[Guardian] Sugerencia proactiva detectada: {res_clean}")
                        try:
                            # Thread-safe text injection into the live stream
                            _inject_fn(f"[ALERTA PROACTIVA DE TU PANTALLA]: {res_clean}")
                        except Exception as ie:
                            print(f"[Guardian] Error injecting suggestion: {ie}")
                            
        except Exception as ex:
            print(f"[Guardian] Loop Exception: {ex}")
            time.sleep(5.0)

def start(inject_fn, speaking_fn) -> None:
    """Registers callbacks and starts the proactive background scanner loop."""
    global _inject_fn, _speaking_fn, _loop_thread, _running
    _inject_fn = inject_fn
    _speaking_fn = speaking_fn

    if _running:
        return

    _running = True
    _loop_thread = threading.Thread(target=_guardian_loop, name="vision-guardian", daemon=True)
    _loop_thread.start()
    print("[Guardian] Vision Guardian subsystem initialized.")

def vision_guardian(parameters: dict, player=None) -> str:
    """
    JARVIS tool function. Controls activation and settings of the screen monitoring system.
    """
    action = parameters.get("action", "status").lower().strip()
    seconds = parameters.get("seconds", None)

    state = _load_state()

    if action == "enable":
        state["enabled"] = True
        _save_state(state)
        msg = "El Guardián de Visión ha sido ACTIVADO. Vigilaré tu pantalla en segundo plano para darte asistencia proactiva."
        if player: player.write_log(f"👁️ {msg}")
        return msg

    elif action == "disable":
        state["enabled"] = False
        _save_state(state)
        msg = "El Guardián de Visión ha sido DESACTIVADO. Ya no monitorearé tu pantalla en segundo plano."
        if player: player.write_log(f"👁️ {msg}")
        return msg

    elif action == "set_interval":
        if seconds is None:
            return "Error: Se requiere el parámetro 'seconds' para cambiar el intervalo."
        sec = int(seconds)
        if sec < 15 or sec > 600:
            return "Error: El intervalo debe estar entre 15 y 600 segundos."
        state["interval"] = sec
        _save_state(state)
        msg = f"Intervalo del Guardián de Visión configurado a {sec} segundos."
        if player: player.write_log(f"👁️ {msg}")
        return msg

    elif action == "check_now":
        if player: player.write_log("👁️ Ejecutando escaneo inmediato de pantalla...")
        result = _perform_vision_analysis()
        if not result or "normal" in result.lower():
            return "Escaneo de pantalla completado. Todo se ve normal y en orden."
        return f"Escaneo de pantalla completado. Sugerencia proactiva: {result}"

    else: # status action
        status_str = "Activo" if state.get("enabled", False) else "Inactivo"
        interval = state.get("interval", 45)
        return f"Estado del Guardián de Visión: {status_str}. Intervalo de escaneo actual: cada {interval} segundos."
