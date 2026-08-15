"""Registro de herramientas que pueden usar los subagentes.

Reutiliza los módulos de `actions/` (misma firma `fn(parameters, player)`),
más unas pocas tools internas (memoria, hora). Los schemas se cargan de
`tool_schemas.json` (extraídos de main.py → TOOL_DECLARATIONS).
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

_SCHEMAS: dict[str, dict] = json.loads(
    (BASE_DIR / "agent" / "tool_schemas.json").read_text(encoding="utf-8")
)


# ── Tools internas ───────────────────────────────────────────────────────────

def remember_info(parameters: dict, player=None, speak=None) -> str:
    from memory.memory_manager import remember
    category = parameters.get("category", "notes")
    key = parameters.get("key", "")
    value = parameters.get("value", "")
    if not key or not value:
        return "Faltan 'key' o 'value'."
    remember(category, key, value)
    return f"Guardado en memoria ({category}/{key})."


def recall_memory(parameters: dict, player=None, speak=None) -> str:
    from memory.memory_manager import load_memory
    mem = load_memory()
    category = parameters.get("category", "")
    if category:
        section = mem.get(category, {})
        if isinstance(section, dict):
            return json.dumps({k: v.get("value") if isinstance(v, dict) else v
                               for k, v in section.items()}, ensure_ascii=False, indent=1)
        return str(section)
    return json.dumps(mem, ensure_ascii=False, indent=1)[:6000]


def current_time(parameters: dict, player=None, speak=None) -> str:
    now = datetime.now()
    return now.strftime("%A %d/%m/%Y %H:%M:%S")


def list_subagent_tools(parameters: dict, player=None, speak=None) -> str:
    return ", ".join(sorted(_SCHEMAS.keys()))


# ── Mapa nombre → función ────────────────────────────────────────────────────

def _import(name: str):
    import importlib
    if "." in name:
        mod_name, fn_name = name.rsplit(".", 1)
    else:
        mod_name, fn_name = name, name
    mod = importlib.import_module(f"actions.{mod_name}")
    fn = getattr(mod, fn_name)
    return fn


INTERNAL_TOOLS: dict[str, callable] = {
    "remember_info": remember_info,
    "recall_memory": recall_memory,
    "current_time": current_time,
}

TOOL_ACTIONS: dict[str, str] = {
    "web_search": "web_search",
    "web_navigation": "web_navigation",
    "youtube_video": "youtube_video",
    "weather_report": "weather_report.weather_action",
    "browser_control": "browser_control",
    "terminal_agent": "terminal_agent",
    "codebase": "codebase",
    "git_control": "git_control",
    "file_controller": "file_controller",
    "code_helper": "code_helper",
    "reminder": "reminder",
    "scheduler": "scheduler",
    "google_calendar": "google_calendar",
    "gmail_control": "gmail_control",
    "smart_file_organizer": "smart_file_organizer",
    "open_app": "open_app",
    "desktop_control": "desktop.desktop_control",
    "computer_control": "computer_control",
    "system_monitor": "system_monitor",
    "spotify_control": "spotify_control",
    "smart_home": "smart_home",
    "knowledge_base": "knowledge_base",
    "morning_brief": "morning_brief",
    "document_creator": "document_creator",
    "goals": "goals",
    "user_profile": "user_profile",
    "social_media": "social_media",
    "whatsapp": "whatsapp",
    "unified_communications": "unified_communications",
}


def available_tool_names() -> list[str]:
    return sorted(set(_SCHEMAS.keys()) | set(INTERNAL_TOOLS.keys()))


def tool_declarations(names: list[str] | None = None) -> list[dict]:
    """Devuelve los schemas estilo Gemini de las tools seleccionadas."""
    decls = []
    for name in (names or available_tool_names()):
        if name in INTERNAL_TOOLS:
            fn = INTERNAL_TOOLS[name]
            doc = (fn.__doc__ or name).strip()
            decls.append({
                "name": name,
                "description": doc,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {},
                    "required": [],
                },
            })
        elif name in _SCHEMAS:
            decls.append(_SCHEMAS[name])
    return decls


def call_tool(name: str, args: dict, player=None, speak=None) -> str:
    """Ejecuta una tool del subagente y devuelve texto con el resultado."""
    try:
        if name in INTERNAL_TOOLS:
            fn = INTERNAL_TOOLS[name]
        elif name in TOOL_ACTIONS:
            fn = _import(TOOL_ACTIONS[name])
        else:
            return f"[toolbox] Tool '{name}' desconocida."
    except Exception as e:
        return f"[toolbox] No se pudo cargar '{name}': {e}"

    try:
        kwargs = {"parameters": args or {}, "player": player}
        sig = inspect.signature(fn)
        if "speak" in sig.parameters:
            kwargs["speak"] = speak
        if "response" in sig.parameters:
            kwargs["response"] = None
        result = fn(**kwargs)
        if result is None:
            return "[toolbox] OK (sin texto)."
        return str(result)
    except Exception as e:
        return f"[toolbox] Error en '{name}': {e}"
