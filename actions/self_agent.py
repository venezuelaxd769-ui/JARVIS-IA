"""Wrapper sobre el módulo premium compilado `self_agent`.

El binario original quedó con una lista de modelos free de OpenRouter
obsoleta (p. ej. `openai/gpt-oss-120b:free` ya no existe → 404). Este
wrapper carga el núcleo compilado (`_self_agent_core.pyc`), re-exporta
todo lo que expone y reemplaza `_call_llm` por una implementación robusta
con modelos free vigentes y una cadena de respaldo a Gemini (usando la key
propia, sin tocar la cuota de la sesión Live).
"""

from __future__ import annotations

import json as _json
import re as _re
import urllib.error as _ue
import urllib.parse as _up
import urllib.request as _ur
from pathlib import Path as _Path

from actions import _self_agent_core as _core

_ORIG_PARSE = _core._parse_json_response
_ORIG_EXECUTE = _core._execute_tool

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# Modelos free vigentes en OpenRouter (verificados el 2026-08-11).
_OR_MODELS = [
    "nvidia/nemotron-3-super-120b-a12b:free",
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "openai/gpt-oss-20b:free",
    "liquid/lfm-2.5-2.6b:free",
]

# Cadena de respaldo en Gemini con la key propia de api_keys.json.
_GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"]

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"


def _error_json(thought: str, detail: str) -> str:
    return _json.dumps({
        "thought": thought,
        "next_action": "tool",
        "parameters": {
            "action": "write",
            "file": "Autoconocimiento/Errores/LLMError.md",
            "content": f"Error: {detail}",
        },
        "message_to_user": "",
    })


def _call_llm(system_prompt: str, user_message: str, max_tokens: int = 1000) -> str:
    """Llama al LLM autónomo: OpenRouter (free) con respaldo a Gemini.

    Devuelve el texto crudo del modelo (JSON con thought/next_action) o, si
    todo falla, un JSON de error con la misma forma que el binario original.
    """
    try:
        key = _core._api_key() or ""
    except Exception:
        key = ""
    if not key:
        return _json.dumps({
            "thought": "No tengo API key para pensar.",
            "next_action": "tool",
            "parameters": {
                "action": "write",
                "file": "Autoconocimiento/Error_API.md",
                "content": "No pude pensar porque falta la API key.",
            },
            "message_to_user": "Necesito una API key configurada para poder pensar autónomamente.",
        })

    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://github.com/nia-ai",
        "X-Title": "Nia Autonomous Agent",
        "Content-Type": "application/json",
    }
    last_err = None

    for model in _OR_MODELS:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.85,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        try:
            req = _ur.Request(
                _OPENROUTER_URL,
                data=_json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with _ur.urlopen(req, timeout=60) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            if text:
                if _looks_like_json(text):
                    return text
                last_err = "Respuesta sin JSON del modelo " + model
                continue
        except Exception as e:
            last_err = e
            continue

    # Reintento con refuerzo de formato JSON (los free a veces responden prosa).
    _JSON_REFORZADO = (
        "\n\nIMPORTANTE: Responde EXCLUSIVAMENTE con un objeto JSON válido que "
        "contenga las claves \"thought\", \"emotional_shift\", \"next_action\" y "
        "\"message_to_user\". next_action debe ser un objeto con claves \"tool\" "
        "y \"parameters\". No escribas nada fuera del JSON."
    )
    for model in _OR_MODELS[:2]:
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message + _JSON_REFORZADO},
            ],
        }
        try:
            req = _ur.Request(
                _OPENROUTER_URL,
                data=_json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with _ur.urlopen(req, timeout=60) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            text = (data["choices"][0]["message"].get("content") or "").strip()
            if text and _looks_like_json(text):
                return text
        except Exception:
            continue

    # Respaldo: Gemini con la key propia (no compite por la cuota Live).
    try:
        gkey = _core._load_config().get("gemini_api_key", "").strip()
        if gkey:
            for gmodel in _GEMINI_MODELS:
                try:
                    gurl = _GEMINI_BASE + gmodel + ":generateContent?key=" + gkey
                    gbody = {
                        "system_instruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"parts": [{"text": user_message}]}],
                    }
                    greq = _ur.Request(
                        gurl,
                        data=_json.dumps(gbody).encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with _ur.urlopen(greq, timeout=30) as gresp:
                        gdata = _json.loads(gresp.read())
                    texts = [p.get("text") for p in gdata["candidates"][0]["content"]["parts"]
                             if p.get("text")]
                    if texts:
                        return texts[0].strip()
                except Exception:
                    continue
    except Exception:
        pass

    return _error_json("Error al llamar al LLM.", str(last_err))


# ── Normalización del schema del LLM ─────────────────────────────────────────

# Nombres de herramientas que el núcleo sabe ejecutar (mirror de _execute_tool).
_TOOL_NAMES = {
    "screen_vision", "query", "web_search", "browser_control", "obsidian_bridge",
    "youtube_video", "visual_click", "desktop", "open_app", "computer_settings",
    "file_controller", "self_edit", "web_kb", "youtube_kb", "desktop_kb",
    "mouse_kb", "game_kb",
}

# Referencia al parser original del núcleo (para no perderlo al patchear).
_ORIGINAL_PARSE = _core._parse_json_response


def _looks_like_json(text: str) -> bool:
    """Heurística rápida: ¿el texto del LLM parece JSON (con next_action)?"""
    t = text.strip()
    if not t:
        return False
    if t.startswith("{"):
        return True
    # código fence
    for prefix in ("```json", "```"):
        if t.startswith(prefix) and "next_action" in t:
            return True
    return "next_action" in t and ("\"thought\"" in t or '"thought"' in t)


def _normalize_llm_schema(parsed):
    """Ajusta el JSON del LLM al esquema que espera el núcleo compilado.

    El núcleo (think_cycle) lee `next_action` como DICT y hace
    next_action.get("tool") y next_action.get("parameters"). Los modelos free
    a veces devuelven next_action como string ("tool"/"nothing") o falta.
    Este normalizador garantiza la forma:

        {"thought": str, "next_action": {"tool": str, "parameters": dict},
         "message_to_user": str}
    """
    if not isinstance(parsed, dict):
        return parsed
    data = dict(parsed)

    na = data.get("next_action")
    top_tool = data.get("tool")
    top_params = data.get("parameters")
    if not isinstance(top_params, dict):
        top_params = {}

    if isinstance(na, dict):
        # Ya es la forma anidada que espera el núcleo.
        inner = na
        tool = inner.get("tool") or inner.get("action") or inner.get("name") or top_tool
        inner_params = inner.get("parameters")
        if isinstance(inner_params, dict):
            params = dict(inner_params)
        else:
            params = {}
        for k, v in inner.items():
            if k in ("tool", "action", "name", "parameters"):
                continue
            params.setdefault(k, v)
        params.update(top_params)
        if tool not in _TOOL_NAMES and tool:
            tool = _core._resolve_tool_name(tool)
        data["next_action"] = {"tool": tool or "obsidian_bridge", "parameters": params}
    elif isinstance(na, str):
        nl = na.strip().lower()
        if nl in ("nothing", "none", "no_action", "noaction", "wait", "idle", "sleep", "done"):
            tool = "nothing"
        elif nl in ("tool", "tool_call", "call_tool", "execute"):
            tool = top_tool or top_params.get("action")
        elif nl:
            tool = na if na in _TOOL_NAMES else top_tool
        else:
            tool = top_tool
        data["next_action"] = {
            "tool": tool or "obsidian_bridge",
            "parameters": top_params,
        }
    else:
        # Sin next_action: construirlo desde tool/parameters a nivel raíz.
        tool = top_tool or top_params.get("action")
        data["next_action"] = {
            "tool": tool if tool in _TOOL_NAMES else "obsidian_bridge",
            "parameters": top_params,
        }
    data.pop("tool", None)
    data.pop("parameters", None)

    # Pensamiento y mensaje en claves alternativas
    if not data.get("thought"):
        for alt in ("thinking", "reasoning", "analysis"):
            if data.get(alt):
                data["thought"] = data[alt]
                break
    if not data.get("message_to_user"):
        for alt in ("reply", "response", "text_response", "message"):
            if data.get(alt):
                data["message_to_user"] = data[alt]
                break
    return data


def _extract_json_block(raw: str) -> str | None:
    """Extrae el primer bloque JSON equilibrado, reparando truncados.

    El JSON de los LLM free suele venir cortado a mitad de string o de objeto
    (límite de max_tokens). Se recorre el texto, se respeta el contenido de
    strings (con sus escapes) y se devuelve el bloque desde el primer '{'
    hasta la última '}' cerrada; si queda sin cerrar, se intenta reparar
    cerrando strings, corchetes y llaves pendientes.
    """
    start = raw.find("{")
    if start < 0:
        return None
    i = start
    depth = 0
    in_str = False
    escaped = False
    while i < len(raw):
        ch = raw[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start:i + 1]
        i += 1
    if depth > 0 or in_str:
        tail = raw[start:]
        if in_str:
            tail += '"'
        while depth > 0:
            tail += "}"
            depth -= 1
        tail = _re.sub(r",\s*([}\]])", r"\1", tail)
        try:
            _json.loads(tail)
            return tail
        except Exception:
            return None
    return None


def _parse_json_response(raw: str) -> dict:
    """Parsea la respuesta del LLM y normaliza el esquema al del núcleo.

    Si el núcleo compilado falla (devuelve el dict de ParseError), se reintenta
    con un extractor propio que repara JSON truncado.
    """
    parsed = _ORIGINAL_PARSE(raw)
    na = parsed.get("next_action")
    if isinstance(na, dict) and (na.get("parameters") or {}).get("file") == "Autoconocimiento/ParseError.md":
        block = _extract_json_block(raw)
        if block:
            try:
                repaired = _json.loads(block)
                if isinstance(repaired, dict):
                    parsed = repaired
            except Exception:
                pass
    return _normalize_llm_schema(parsed)


# Re-exportar todo el núcleo compilado (excepto las funciones que reemplazamos).
for _k, _v in vars(_core).items():
    if _k.startswith("__") or _k in ("_call_llm", "_parse_json_response"):
        continue
    globals()[_k] = _v

# El núcleo llama a estas funciones desde sus propios globals → apuntarlas.
_core._call_llm = _call_llm
_core._parse_json_response = _parse_json_response

self_agent = _core.self_agent
SelfAgent = _core.SelfAgent
exploration_mode = _core.exploration_mode
stop_exploration = _core.stop_exploration
_agent_instance = _core._agent_instance
