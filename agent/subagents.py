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
        "weather_report", "knowledge_base", "current_time", "skill_manager",
        "web_fetch", "pdf_reader", "csv_analyzer", "image_reader",
        "web_crawler", "multi_search", "noticias", "groq_stt",
    ],
    "coder": [
        "terminal_agent", "codebase", "git_control", "file_controller",
        "code_helper", "code_search", "code_editor", "shell_exec",
        "project_analyzer", "code_executor", "multi_step_executor",
        "self_improve", "test_runner", "doc_generator",
        "skill_creator",
    ],
    "organizer": [
        "reminder", "scheduler", "google_calendar", "gmail_control",
        "smart_file_organizer", "document_creator", "goals", "user_profile",
        "remember_info", "recall_memory", "current_time", "timer",
        "persistent_context", "env_manager", "backup_manager",
        "episodic_memory", "gastos",
    ],
    "computer": [
        "open_app", "desktop_control", "computer_control", "system_monitor",
        "spotify_control", "smart_home", "social_media", "whatsapp",
        "unified_communications", "current_time", "clipboard",
        "real_vision", "process_manager", "file_watcher",
        "package_manager",
        "screen_pointer", "describe_screen",
        "windows_settings", "computer_settings",
        "ambient_context_action",
        "anomaly_monitor",
        "nightly_maintenance",
        "volumen",
        "system_power",
        "system_services",
        "system_startup",
        "system_network",
        "system_cleanup",
        "system_audio",
        "system_display",
        "alarma",
        "musica",
        "system_health",
        "modo_foco",
        "camara",
        "notas",
        "buscar",
        "feriados",
        "leer_pdf",
        "ventanas",
        "uso_pc",
        "descargas",
        "macros",
        "cofre",
        "calculadora",
        "captura",
        "preferencias",
        "specs",
        "fondo",
        "links",
        "changes",
        "qrgen",
        "duplicados",
        "hora_mundial",
        "red_check",
        "checksum",
        "tareas",
        "convertidor",
        "comprimir",
        "wifi_clave",
        "pomodoro",
        "impresora",
        "temperatura",
        "trivia",
        "recetario",
        "ocr",
        "velocidad",
        "flashcards",
        "chistes",
        "traductor",
        "eventos",
        "descargar_yt",
        "silencio_nocturno",
    ],
}

_DESCRIPTIONS = {
    "researcher": "Investiga en la web, noticias, videos y datos actuales.",
    "coder": "Programa: analiza y edita código, terminal, git y archivos.",
    "organizer": "Organiza: memoria, recordatorios, calendario, correo y archivos.",
    "computer": "Controla el equipo: apps, ventanas, sistema, audio, pantalla, limpieza, alarma, música, salud, foco, cámara, notas, feriados y red.",
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
              "automatiza", "clase", "función", "funcion",
              "creá una skill", "crea una skill", "hacé una herramienta",
              "hace una herramienta", "nueva tool", "nueva herramienta",
              "fabric", "programame una herramienta"],
    "organizer": ["recorda", "recordá", "recuerda", "recuerdá", "recuerdame",
                  "recordame", "acordate", "acuerdate", "recordatorio",
                  "agenda", "agenda", "reunión", "reunion", "calendario", "mail",
                  "correo", "gmail", "organiza", "organizar", "memoria", "guarda",
                  "tarea", "planifica", "planifica", "pendiente",
                  "lo que te dije", "de dónde lo sabés", "de donde lo sabes",
                  "¿cómo sabés", "como sabes", "fuente", "revoca", "olvidá esta", "episodio"],
    "computer": ["abre", "abrí", "ejecuta", "ejecutá", "lanz", "ventana",
                 "escritorio", "app", "aplicación", "aplicacion", "música",
                 "musica", "spotify", "volumen", "captura", "pantalla", "monitor",
                 "parlantes", "auriculares", "audio", "micrófono", "microfono", "mic",
                 "dispositivo de salida", "luces",
                 "luces", "rgb", "domótica", "domotica", "whatsapp", "mensaje",
                 "mirá lo que veo", "mirá", "mirar", "qué ves", "estás viendo",
                 "brillo", "suspender", "bloquear", "hibernar", "estado del equipo",
                 "apagá la compu", "apaga la compu", "alarma", "despertame", "despertá",
                 "snooze", "posponé", "despertar", "alarm",
                 "papelera", "temporales", "disco", "espacio libre", "instalá",
                 "desinstalá", "desinstala", "apps instaladas", "limpiá",
                 "en qué anda", "en qué estás", "qué estás haciendo", "qué hacés",
                 "que estas haciendo", "ventana activa", "qué hay abierto", "portapapeles",
                 "anomalía", "anomalia", "raro", "rara", "qué tan normal", "normalidad",
                 "baseline", "funciona mal el pc", "algo anda raro",
                 "mantenimiento", "regresión", "smoke", "backup", "limpiá las capturas",
                 "memoria libre", "ram", "poca memoria", "matá", "mata", "matar",
                 "proceso pesado", "qué consume", "concentración", "concentrate",
                 "modo foco", "no me molestes", "no molestar", "bloqueá", "bloquea",
                 "distra", "cámara", "camara", "sacame una foto", "saca una foto",
                 "selfie", "webcam", "anotá", "anota", "anotar", "nota", "notas",
                 "apuntá", "anotado", "leé mis notas", "buscá el archivo", "busca el archivo",
                 "buscá un archivo", "dónde está el archivo", "archivo de", "buscá los", "encontrá el archivo",
                 "feriado", "feriados", "efemeride", "efeméride", "qué se celebra", "es feriado",
                 "feriad", "pdf", "leéme el pdf", "leeme el pdf", "documento pdf", "página del pdf",
                 "leé una página", "leela el pdf", "partí la pantalla", "parti la pantalla",
                 "lado a lado", "lado_a_lado", "maximizá", "maximiza", "ventana a la izquierda",
                 "ventana a la derecha", "cuadrícula", "cuadricula", "acomodá las ventanas",
                 "ventanas abiertas", "qué ventanas", "centrá esa ventana", "minimizá",
                 "cuánto tiempo", "cuánto usé", "uso del pc", "uso de apps", "qué app",
                 "mi red", "en mi red", "conectado a mi red", "dispositivo",
                 "descargas", "ordená mis descargas", "ordena mis descargas",
                 "acomodá mis descargas", "macros", "macro", "modo peli", "dispará el macro",
                 "cofre", "guardá la contraseña", "guarda la clave", "contraseña del",
                 "cuánto es", "calcular", "calculá", "cuanto da", "raíz cuadrada",
                 "captura de pantalla", "saca una captura", "sacá una captura", "tomá una captura",
                 "preferencia", "prefiero", "recordá que", "guarda mis gustos",
                 "specs", "procesador", "placa de video", "cuánta ram", "especificaciones",
                 "fondo de pantalla", "wallpaper", "fondo al azar", "cambiá el fondo",
                 "marcador", "links", "marcadores", "guardá el link", "abrí el link", "favorito",
                 "diario de cambios", "qué cambió", "autocommit", "commit común git",
                 "código qr", "qr", "código QR", "armá un qr",
                 "duplicado", "archivos repetidos", "borrá los duplicados",
                  "qué hora es en", "quÉ hora es en", "que hora es en", "hora en",
                  "qué hora hay", "hora en japón", "hora en españa",
                  "probá mi conexión", "prueba la conexión", "chequeá la red",
                  "estado de la red", "anda lento el internet", "internet lento",
                  "ip pública", "mi ip", "señal wifi", "wifi", "conexión a internet",
                  "checksum", "md5", "sha1", "sha256", "sha512", "huella del archivo",
                  "verificá la integridad", "integridad del archivo",
                  "tarea", "tareas", "pendiente", "pendientes", "por hacer",
                  "to do", "lista de tareas", "qué tengo pendiente",
                  "convertí", "convertir", "cuántos pesos", "cuánto son", "dólares en pesos",
                  "cuántos dólares", "a megas", "a gigas", "a millas", "a libras", "grados celsius",
                  "comprimí", "comprime", "zip", "descomprimí", "descomprime", "empaquetá", "extraer el zip",
                  "contraseña del wifi", "clave del wifi", "clave de la red", "contraseña wifi",
                  "pomodoro", "cuánto falta del pomodoro",
                  "impresora", "imprimí", "imprime", "imprimir",
                  "temperatura de la pc", "calentando", "caliente la pc", "sensores térmicos",
                  "trivia", "juguemos", "otra pregunta", "cultura general", "puntaje",
                  "receta", "recetas", "recetario", "cocina",
                  "ocr", "leé el texto de", "leé esta imagen", "qué dice en", "qué dice la imagen",
                  "texto de la imagen", "pdf escaneado",
                  "velocidad de internet", "qué tan rápido anda", "mega", "megas", "de bajada",
                  "de subida", "speedtest",
                  "flashcard", "flashcards", "repasar", "estudiar", "tarjeta de estudio",
                  "chiste", "chistes", "contame un chiste", "otro chiste",
                  "traduci", "traducime", "traducir", "traduccion", "traducción",
                  "como se dice", "pronunciame", "eventos de windows", "visor de eventos",
                  "error de windows", "revisa los eventos", "diagnóstico de errores",
                  "descargate", "descarga el audio", "de youtube", "bajame", "baja el video",
                  "silencio nocturno", "no me hables", "silenciate de noche", "dormí",
                  "a partir de las", "volvé a hablarme",
                  "escanéame", "leé el qr", "decodificame"],
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
