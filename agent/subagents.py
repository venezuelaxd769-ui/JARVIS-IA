"""Definición de los subagentes de Nia + registro.

Cada subagente es una "faceta" de Nia: mismo estilo, memoria y forma de
hablar, pero con su propio LLM y un toolkit acotado para ser rápido y
paralelo. La configuración de modelo está en `config/subagents.json`.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from agent.base import SubAgent

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "subagents.json"

DEFAULT_CONFIG = {
    "global": {"max_iterations": 8, "max_tokens": 2048},
    "subagents": {
        "researcher": {"model_kind": "gemini", "model_name": "gemini-2.5-flash"},
        "coder": {"model_kind": "gemini", "model_name": "gemini-2.5-flash"},
        "organizer": {"model_kind": "gemini", "model_name": "gemini-2.5-flash"},
        "computer": {"model_kind": "gemini", "model_name": "gemini-2.5-flash"},
    },
}


def _load_config() -> dict:
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        for key in ("global", "subagents"):
            if key not in data:
                data[key] = DEFAULT_CONFIG[key]
        return data
    except Exception:
        return DEFAULT_CONFIG


_PERSONAS = {
    "researcher": (
        "Sos la faceta INVESTIGADORA de Nia, la asistente personal de "
        "escritorio del usuario. Tu especialidad es buscar información en la "
        "web, noticias, videos y datos actuales. Consulta tus herramientas "
        "antes de afirmar hechos y cita las fuentes. Serás breve pero "
        "completa, en español, con un tono cercano."
    ),
    "coder": (
        "Sos la faceta PROGRAMADORA de Nia, la asistente personal. Tu "
        "especialidad es el desarrollo de software: leer y analizar código, "
        "ejecutar comandos, trabajar con git, crear y editar archivos. "
        "Escribí código correcto y seguro, explicá qué cambiás y verificá "
        "resultados con tus herramientas (por ejemplo ejecutando comandos). "
        "Respondé en español."
    ),
    "organizer": (
        "Sos la faceta ORGANIZADORA de Nia, la asistente personal. Tu "
        "especialidad es la organización de la vida del usuario: memoria a "
        "largo plazo, recordatorios, tareas programadas, calendario, correo "
        "y organización de archivos. Consultá y guardá información en la "
        "memoria cuando corresponda. Respondé en español, ordenada y "
        "puntual."
    ),
    "computer": (
        "Sos la faceta OPERATIVA de Nia, la asistente personal. Tu "
        "especialidad es el control del equipo del usuario: abrir "
        "aplicaciones, controlar ventanas y escritorio, monitorear el "
        "sistema, música y dispositivos. Ejecutá lo que se te pide con tus "
        "herramientas y confirmá qué hiciste. Respondé en español."
    ),
}

_TOOLS = {
    "researcher": [
        "web_search", "web_navigation", "browser_control", "youtube_video",
        "weather_report", "knowledge_base", "current_time",
    ],
    "coder": [
        "terminal_agent", "codebase", "git_control", "file_controller",
        "code_helper", "code_search", "code_editor", "shell_exec",
        "project_analyzer",
    ],
    "organizer": [
        "reminder", "scheduler", "google_calendar", "gmail_control",
        "smart_file_organizer", "document_creator", "goals", "user_profile",
        "remember_info", "recall_memory", "current_time", "timer",
    ],
    "computer": [
        "open_app", "desktop_control", "computer_control", "system_monitor",
        "spotify_control", "smart_home", "social_media", "whatsapp",
        "unified_communications", "current_time", "clipboard",
    ],
}

_DESCRIPTIONS = {
    "researcher": "Investiga en la web, noticias, videos y datos actuales.",
    "coder": "Programa: analiza y edita código, terminal, git y archivos.",
    "organizer": "Organiza: memoria, recordatorios, calendario, correo y archivos.",
    "computer": "Controla el equipo: apps, ventanas, sistema, música y dispositivos.",
}

# Palabras clave para selección automática (auto-delegación)
_ROUTING_KEYWORDS = {
    "researcher": ["investiga", "investig", "busca", "buscar", "noticia", "qué es",
                   "quien es", "quién es", "última", "actual", "precio", "comparar",
                   "resumen de la web", "web", "internet", "noticias", "youtube",
                   "video", "clima", "tradu", "explica", "documentar", "wiki"],
    "coder": ["código", "codigo", "programa", "programar", "bug", "error en",
              "script", "python", "código", "git", "repositorio", "refactor",
              "terminal", "comando", "archivo .py", "corrige", "desarrolla",
              "automatiza", "clase", "función", "funcion"],
    "organizer": ["recorda", "recordá", "recuerda", "recuerdá", "recuerdame",
                  "recordame", "acordate", "acuerdate", "recordatorio",
                  "agenda", "agenda", "reunión", "reunion", "calendario", "mail",
                  "correo", "gmail", "organiza", "organizar", "memoria", "guarda",
                  "tarea", "planifica", "planifica", "pendiente"],
    "computer": ["abre", "abrí", "ejecuta", "ejecutá", "lanz", "ventana",
                 "escritorio", "app", "aplicación", "aplicacion", "música",
                 "musica", "spotify", "volumen", "captura", "pantalla", "monitor",
                 "luces", "rgb", "domótica", "domotica", "whatsapp", "mensaje"],
}


def _config_for(name: str) -> dict:
    cfg = _load_config()
    sub = cfg["subagents"].get(name, {})
    g = cfg["global"]
    return {
        "model_kind": sub.get("model_kind", "gemini"),
        "model_name": sub.get("model_name"),
        "max_iterations": sub.get("max_iterations", g.get("max_iterations", 8)),
        "max_tokens": sub.get("max_tokens", g.get("max_tokens", 2048)),
        "enabled": sub.get("enabled", True),
    }


def get_subagent(name: str, player=None, speak=None) -> SubAgent | None:
    if name not in _TOOLS:
        return None
    cfg = _config_for(name)
    if not cfg.get("enabled", True):
        return None
    return SubAgent(
        name=name,
        description=_DESCRIPTIONS[name],
        tools=_TOOLS[name],
        persona=_PERSONAS[name],
        model_kind=cfg["model_kind"],
        model_name=cfg["model_name"],
        max_iterations=cfg["max_iterations"],
        max_tokens=cfg["max_tokens"],
        player=player,
        speak=speak,
    )


def list_subagents() -> list[dict]:
    out = []
    for name in _TOOLS:
        cfg = _config_for(name)
        out.append({
            "name": name,
            "description": _DESCRIPTIONS[name],
            "tools": _TOOLS[name],
            "model_kind": cfg["model_kind"],
            "model_name": cfg["model_name"],
            "enabled": cfg.get("enabled", True),
        })
    return out


def _normalize(text: str) -> str:
    """Baja a minúsculas y quita acentos (e.g. recuérdame -> recuerdame)."""
    text = text.lower()
    return "".join(c for c in unicodedata.normalize("NFD", text)
                   if unicodedata.category(c) != "Mn")


def pick_best(goal: str) -> str | None:
    """Elige el subagente más probable para una tarea (heurística simple)."""
    text = _normalize(goal or "")
    best, best_score = None, 0
    for name, words in _ROUTING_KEYWORDS.items():
        score = sum(1 for w in words if _normalize(w) in text)
        if score > best_score:
            best, best_score = name, score
    return best if best_score > 0 else None
