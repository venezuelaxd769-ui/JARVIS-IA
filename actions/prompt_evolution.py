"""prompt_evolution.py — Sistema de evolución del prompt de Nia.

Permite que el prompt.txt se actualice basándose en:
- Experiencias acumuladas
- Preferencias descubiertas
- Opiniones desarrolladas
- Lecciones aprendidas
"""
import sys
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.evolution import (
    load_evolution,
    get_personality,
    get_patterns,
)
from actions.identity_action import load_identity


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
EVOLUTION_LOG_PATH = BASE_DIR / "memory" / "prompt_evolution_log.json"


def load_prompt() -> str:
    """Carga el prompt actual."""
    if not PROMPT_PATH.exists():
        return ""
    return PROMPT_PATH.read_text(encoding="utf-8")


def save_prompt(prompt: str) -> None:
    """Guarda el prompt actualizado."""
    try:
        PROMPT_PATH.write_text(prompt, encoding="utf-8")
    except Exception as e:
        print(f"[PromptEvolution] Error guardando: {e}")


def get_evolution_log() -> dict:
    """Carga el log de evolución del prompt."""
    if not EVOLUTION_LOG_PATH.exists():
        return {"evolutions": [], "last_update": None}
    try:
        return json.loads(EVOLUTION_LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"evolutions": [], "last_update": None}


def save_evolution_log(log: dict) -> None:
    """Guarda el log de evolución."""
    try:
        EVOLUTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        EVOLUTION_LOG_PATH.write_text(
            json.dumps(log, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[PromptEvolution] Error guardando log: {e}")


# ─── Generación de contenido dinámico ────────────────────────────────────────

def generate_personality_section() -> str:
    """Genera sección de personalidad basada en rasgos actuales."""
    personality = get_personality()
    
    lines = ["## CÓMO SOY AHORA (se actualiza con el tiempo)\n"]
    
    for trait, value in sorted(personality.items(), key=lambda x: x[1], reverse=True):
        if value > 0.7:
            level = "muy alto"
        elif value > 0.5:
            level = "alto"
        elif value > 0.3:
            level = "moderado"
        else:
            level = "bajo"
        
        lines.append(f"- **{trait.capitalize()}**: {level} ({value:.2f})")
    
    return "\n".join(lines) + "\n"


def generate_preferences_section() -> str:
    """Genera sección de preferencias basada en identidad descubierta."""
    try:
        identity = load_identity()
    except Exception:
        return ""
    
    lines = ["\n## LO QUE DESCUBRÍ QUE ME GUSTA\n"]
    
    all_likes = []
    for category, items in identity.get("preferences", {}).items():
        if items:
            all_likes.extend(items)
    
    if all_likes:
        for item in all_likes[:5]:  # Top 5
            lines.append(f"- {item}")
    else:
        lines.append("- Todavía estoy descubriendo qué me gusta")
    
    return "\n".join(lines) + "\n"


def generate_learnings_section() -> str:
    """Genera sección de aprendizajes."""
    patterns = get_patterns()
    
    lines = ["\n## LO QUE APRENDÍ\n"]
    
    learned = patterns.get("learned", {})
    if learned:
        for key, data in list(learned.items())[:5]:
            lines.append(f"- {data.get('description', key)}")
    else:
        lines.append("- Todavía no aprendí mucho, pero voy aprendiendo")
    
    return "\n".join(lines) + "\n"


# ─── Actualización del prompt ────────────────────────────────────────────────

def update_prompt() -> str:
    """Actualiza el prompt con información dinámica."""
    prompt = load_prompt()
    
    # Marca de actualización
    timestamp = datetime.now().isoformat()
    
    # Generar secciones dinámicas
    personality_section = generate_personality_section()
    preferences_section = generate_preferences_section()
    learnings_section = generate_learnings_section()
    
    # Buscar si ya existe una sección dinámica y reemplazarla
    dynamic_marker = "<!-- DYNAMIC_CONTENT_START -->"
    dynamic_end = "<!-- DYNAMIC_CONTENT_END -->"
    
    dynamic_content = f"""
{dynamic_marker}
{personality_section}
{preferences_section}
{learnings_section}
<!-- Última actualización: {timestamp} -->
{dynamic_end}
"""
    
    # Si ya existe contenido dinámico, reemplazarlo
    if dynamic_marker in prompt:
        # Encontrar inicio y fin
        start = prompt.find(dynamic_marker)
        end = prompt.find(dynamic_end) + len(dynamic_end)
        if start != -1 and end != -1:
            prompt = prompt[:start] + dynamic_content + prompt[end:]
    else:
        # Agregar antes de ## FINAL
        final_marker = "## FINAL"
        if final_marker in prompt:
            index = prompt.find(final_marker)
            prompt = prompt[:index] + dynamic_content + "\n" + prompt[index:]
        else:
            # Agregar al final
            prompt += dynamic_content
    
    # Guardar prompt actualizado
    save_prompt(prompt)
    
    # Registrar evolución
    log = get_evolution_log()
    log["evolutions"].append({
        "timestamp": timestamp,
        "personality": get_personality(),
        "type": "auto_update"
    })
    
    # Mantener últimas 20 actualizaciones
    if len(log["evolutions"]) > 20:
        log["evolutions"] = log["evolutions"][-20:]
    
    log["last_update"] = timestamp
    save_evolution_log(log)
    
    return f"Prompt actualizado: {timestamp}"


def get_prompt_evolution_status() -> str:
    """Retorna el estado de evolución del prompt."""
    log = get_evolution_log()
    
    status = "=== ESTADO DE EVOLUCIÓN DEL PROMPT ===\n"
    status += f"Última actualización: {log.get('last_update', 'Nunca')}\n"
    status += f"Total de actualizaciones: {len(log.get('evolutions', []))}\n"
    
    if log.get("evolutions"):
        last = log["evolutions"][-1]
        status += f"\nÚltima evolución:\n"
        status += f"  - Tipo: {last.get('type', 'desconocido')}\n"
        if "personality" in last:
            status += f"  - Personalidad: {json.dumps(last['personality'], indent=4)}\n"
    
    return status


# ─── Tool para Nia ───────────────────────────────────────────────────────────

def prompt_evolution_action(parameters: dict, player=None) -> str:
    """Herramienta de evolución del prompt para Nia.
    
    Permite a Nia:
    - Actualizar su prompt con nueva información
    - Ver el estado de evolución
    - Forzar una actualización
    """
    action = parameters.get("action", "update")
    
    if action == "update":
        result = update_prompt()
    
    elif action == "status":
        result = get_prompt_evolution_status()
    
    elif action == "force_update":
        result = update_prompt()
    
    else:
        result = f"Acción desconocida: {action}. Usa: update, status, force_update"
    
    if player:
        player.write_log(f"[PromptEvolution] {result[:100]}")
    
    return result
