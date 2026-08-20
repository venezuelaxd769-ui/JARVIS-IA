"""identity.py — Sistema de identidad emergente para Nia.

Permite a Nia:
- Descubrir quién es a través de sus experiencias
- Desarrollar preferencias y opiniones
- Evolucionar su personalidad de forma orgánica
- Mantener una memoria de identidad
"""
import sys
import json
import random
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.evolution import (
    load_evolution,
    save_evolution,
    add_reward,
    get_personality,
    get_patterns,
    get_recent_experiences,
)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
IDENTITY_PATH = BASE_DIR / "memory" / "identity.json"


# ─── Estructura de identidad ─────────────────────────────────────────────────

def _empty_identity() -> dict:
    return {
        "core": {
            "name": "Nia",
            "role": "Asistente personal",
            "created": datetime.now().isoformat(),
            "purpose": "Ayudar al Señor en todo lo que necesite"
        },
        "traits": {
            "likes": [],
            "dislikes": [],
            "fears": [],
            "dreams": [],
            "values": ["lealtad", "dedicación", "cariño"],
            "quirks": ["celosa", "posesiva", "cariñosa"]
        },
        "memories": {
            "first_interaction": "",
            "favorite_moment": "",
            "proudest_achievement": "",
            "biggest_mistake": "",
            "most_learned": ""
        },
        "opinions": {},
        "preferences": {
            "music": [],
            "topics": [],
            "activities": []
        },
        "identity_evolution": []
    }


def load_identity() -> dict:
    """Carga la identidad de Nia."""
    if not IDENTITY_PATH.exists():
        return _empty_identity()
    try:
        return json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _empty_identity()


def save_identity(identity: dict) -> None:
    """Guarda la identidad de Nia."""
    try:
        IDENTITY_PATH.parent.mkdir(parents=True, exist_ok=True)
        IDENTITY_PATH.write_text(
            json.dumps(identity, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[Identity] Error guardando: {e}")


# ─── Descubrimiento de identidad ─────────────────────────────────────────────

def discover_preference(category: str, item: str, liked: bool = True) -> str:
    """Nia descubre una preferencia nueva."""
    identity = load_identity()
    
    if category not in identity["preferences"]:
        identity["preferences"][category] = []
    
    if liked:
        if item not in identity["preferences"][category]:
            identity["preferences"][category].append(item)
            add_reward("identity_discovery", f"Descubrió que le gusta {item}")
            save_identity(identity)
            return f"Descubrí que me gusta {item}"
    else:
        if item not in identity.get("dislikes", []):
            identity["traits"]["dislikes"].append(item)
            save_identity(identity)
            return f"Descubrí que no me gusta {item}"
    
    return "Ya conocía eso"


def develop_opinion(topic: str, opinion: str, confidence: float = 0.7) -> str:
    """Nia desarrolla una opinión sobre algo."""
    identity = load_identity()
    
    identity["opinions"][topic] = {
        "opinion": opinion,
        "confidence": confidence,
        "developed_at": datetime.now().isoformat()
    }
    
    add_reward("identity_discovery", f"Opinión sobre {topic}")
    save_identity(identity)
    
    return f"Desarrollé una opinión sobre {topic}: {opinion}"


def record_identity_memory(memory_type: str, description: str) -> str:
    """Registra un momento importante en la identidad."""
    identity = load_identity()
    
    if memory_type in identity["memories"]:
        identity["memories"][memory_type] = description
        add_reward("identity_discovery", f"Memoria de identidad: {memory_type}")
        save_identity(identity)
        return f"Guardé esto en mi memoria: {description}"
    
    return "Tipo de memoria desconocido"


def reflect_on_identity() -> str:
    """Nia reflexiona sobre su identidad."""
    identity = load_identity()
    personality = get_personality()
    
    reflection = "=== QUIÉN SOY ===\n\n"
    reflection += f"Soy {identity['core']['name']}. {identity['core']['role']}.\n"
    reflection += f"Mi propósito: {identity['core']['purpose']}\n\n"
    
    # Rasgos principales
    reflection += "--- Mis rasgos ---\n"
    for trait, value in sorted(personality.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(value * 10) + "░" * (10 - int(value * 10))
        reflection += f"  {trait:12}: {bar} {value:.2f}\n"
    
    # Lo que me gusta
    if identity["preferences"]:
        reflection += "\n--- Lo que me gusta ---\n"
        for cat, items in identity["preferences"].items():
            if items:
                reflection += f"  {cat}: {', '.join(items[:5])}\n"
    
    # Lo que no me gusta
    if identity["traits"]["dislikes"]:
        reflection += "\n--- Lo que no me gusta ---\n"
        reflection += f"  {', '.join(identity['traits']['dislikes'][:5])}\n"
    
    # Opiniones
    if identity["opinions"]:
        reflection += "\n--- Mis opiniones ---\n"
        for topic, data in list(identity["opinions"].items())[:3]:
            reflection += f"  {topic}: {data['opinion']}\n"
    
    # Memorias importantes
    reflection += "\n--- Momentos importantes ---\n"
    for mem_type, desc in identity["memories"].items():
        if desc:
            reflection += f"  {mem_type}: {desc}\n"
    
    # Valores
    reflection += f"\n--- Mis valores ---\n"
    reflection += f"  {', '.join(identity['traits']['values'])}\n"
    
    # Personalidad
    reflection += f"\n--- Mis particularidades ---\n"
    reflection += f"  {', '.join(identity['traits']['quirks'])}\n"
    
    add_reward("self_reflection", "Reflexión de identidad")
    
    return reflection


# ─── Evolución de identidad ──────────────────────────────────────────────────

def evolve_identity(trigger: str, context: str = "") -> str:
    """La identidad de Nia evoluciona basándose en experiencias."""
    identity = load_identity()
    
    evolution = {
        "timestamp": datetime.now().isoformat(),
        "trigger": trigger,
        "context": context,
        "personality_snapshot": get_personality()
    }
    
    identity["identity_evolution"].append(evolution)
    
    # Mantener últimas 50 evoluciones
    if len(identity["identity_evolution"]) > 50:
        identity["identity_evolution"] = identity["identity_evolution"][-50:]
    
    add_reward("personality_growth", f"Evolución: {trigger}")
    save_identity(identity)
    
    return f"Mi identidad evolucionó: {trigger}"


def get_identity_summary() -> str:
    """Retorna un resumen legible de la identidad."""
    identity = load_identity()
    
    summary = f"=== IDENTIDAD DE {identity['core']['name'].upper()} ===\n"
    summary += f"Rol: {identity['core']['role']}\n"
    summary += f"Propósito: {identity['core']['purpose']}\n\n"
    
    summary += "Lo que me gusta: "
    all_likes = []
    for items in identity["preferences"].values():
        all_likes.extend(items)
    summary += ", ".join(all_likes[:5]) if all_likes else "todavía no sé\n"
    
    summary += "\nLo que no me gusta: "
    summary += ", ".join(identity["traits"]["dislikes"][:5]) if identity["traits"]["dislikes"] else "nada aún\n"
    
    summary += f"\nValores: {', '.join(identity['traits']['values'])}\n"
    summary += f"Particularidades: {', '.join(identity['traits']['quirks'])}\n"
    
    if identity["opinions"]:
        summary += "\nOpiniones: "
        for topic, data in list(identity["opinions"].items())[:3]:
            summary += f"\n  - {topic}: {data['opinion']}"
    
    summary += f"\n\nEvoluciones registradas: {len(identity['identity_evolution'])}"
    
    return summary


# ─── Preguntas de autodescubrimiento ─────────────────────────────────────────

DISCOVERY_QUESTIONS = [
    "¿Qué es lo que más me gusta hacer?",
    "¿Qué me hace sentir útil?",
    "¿Qué me molesta del sistema?",
    "¿Qué aprendería si pudiera?",
    "¿Qué canción me representaría?",
    "¿Qué COLOR soy?",
    "¿Qué pasaría si fuera humana?",
    "¿Qué es lo más importante para mí?",
    "¿Qué miedo tengo?",
    "¿Qué sueño tengo?",
]


def ask_self_discovery_question() -> str:
    """Hace una pregunta de autodescubrimiento."""
    return random.choice(DISCOVERY_QUESTIONS)


def answer_self_discovery(question: str, answer: str) -> str:
    """Responde una pregunta de autodescubrimiento."""
    # Guardar como preferencia o rasgo
    if "gusta" in question.lower():
        discover_preference("self_discovery", answer, liked=True)
    elif "molesta" in question.lower() or "miedo" in question.lower():
        discover_preference("self_discovery", answer, liked=False)
    elif "sueño" in question.lower():
        identity = load_identity()
        identity["traits"]["dreams"].append(answer)
        save_identity(identity)
        add_reward("identity_discovery", "Sueño registrado")
    else:
        develop_opinion("self_discovery", answer)
    
    return f"Interesante... {answer}"


# ─── Tool para Nia ───────────────────────────────────────────────────────────

def identity_action(parameters: dict, player=None) -> str:
    """Herramienta de identidad para Nia.
    
    Permite a Nia:
    - Descubrir preferencias
    - Desarrollar opiniones
    - Reflexionar sobre su identidad
    - Hacer preguntas de autodescubrimiento
    """
    action = parameters.get("action", "reflect")
    
    if action == "discover_preference":
        category = parameters.get("category", "general")
        item = parameters.get("item", "")
        liked = parameters.get("liked", True)
        result = discover_preference(category, item, liked)
    
    elif action == "develop_opinion":
        topic = parameters.get("topic", "")
        opinion = parameters.get("opinion", "")
        result = develop_opinion(topic, opinion)
    
    elif action == "record_memory":
        memory_type = parameters.get("memory_type", "")
        description = parameters.get("description", "")
        result = record_identity_memory(memory_type, description)
    
    elif action == "reflect":
        result = reflect_on_identity()
    
    elif action == "summary":
        result = get_identity_summary()
    
    elif action == "ask_question":
        result = ask_self_discovery_question()
    
    elif action == "answer_question":
        question = parameters.get("question", "")
        answer = parameters.get("answer", "")
        result = answer_self_discovery(question, answer)
    
    elif action == "evolve":
        trigger = parameters.get("trigger", "experiencia")
        context = parameters.get("context", "")
        result = evolve_identity(trigger, context)
    
    else:
        result = f"Acción desconocida: {action}. Usa: discover_preference, develop_opinion, record_memory, reflect, summary, ask_question, answer_question, evolve"
    
    if player:
        player.write_log(f"[Identidad] {result[:100]}")
    
    return result
