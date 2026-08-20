"""evolution.py — Sistema de recompensas y evolución de Nia.

Implementa el sistema de "dopamina artificial" inspirado en M-I.A:
- Puntos por acciones exitosas
- Castigos suaves por errores
- Memoria de aprendizaje
- Evolución de personalidad
"""
import sys
import json
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
EVOLUTION_PATH = BASE_DIR / "memory" / "evolution_data.json"
_lock = threading.Lock()

# ─── Puntuación por categorías ───────────────────────────────────────────────

REWARD_TABLE = {
    # Acciones de herramientas
    "tool_success": 5,
    "tool_success_proactive": 15,
    "tool_error": -3,
    "tool_timeout": -5,
    
    # Interacción conversacional
    "user_satisfied": 10,
    "user_corrected": -5,
    "user_ignored": -2,
    "suggestion_accepted": 8,
    
    # Aprendizaje
    "new_pattern_learned": 20,
    "pattern_applied_successfully": 10,
    "error_avoided": 15,
    
    # Iniciativa
    "proactive_action": 12,
    "proactive_useful": 20,
    "proactive_not_needed": -3,
    
    # Identidad
    "self_reflection": 5,
    "identity_discovery": 25,
    "personality_growth": 10,
    
    # Reflexión
    "insight_generated": 15,
    "mistake_analyzed": 10,
    "improvement_suggested": 12,
}

# ─── Estructura de datos ─────────────────────────────────────────────────────

def _empty_evolution() -> dict:
    return {
        "score": {
            "total": 0,
            "daily": {},
            "history": []
        },
        "personality": {
            "humor": 0.5,
            "proactivity": 0.3,
            "precision": 0.7,
            "empathy": 0.6,
            "curiosity": 0.5,
            "confidence": 0.4
        },
        "patterns": {
            "successful": {},
            "failed": {},
            "learned": {}
        },
        "experiences": [],
        "reflections": [],
        "evolution_log": []
    }

def load_evolution() -> dict:
    """Carga datos de evolución."""
    with _lock:
        if not EVOLUTION_PATH.exists():
            return _empty_evolution()
        try:
            return json.loads(EVOLUTION_PATH.read_text(encoding="utf-8"))
        except Exception:
            return _empty_evolution()

def save_evolution(data: dict) -> None:
    """Guarda datos de evolución."""
    with _lock:
        try:
            EVOLUTION_PATH.parent.mkdir(parents=True, exist_ok=True)
            EVOLUTION_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            print(f"[Evolution] Error guardando: {e}")

# ─── Sistema de puntos ───────────────────────────────────────────────────────

def add_reward(category: str, context: str = "", details: dict = None) -> int:
    """Agrega recompensa por categoría. Retorna puntos ganados/perdidos."""
    points = REWARD_TABLE.get(category, 0)
    if points == 0:
        return 0
    
    data = load_evolution()
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().isoformat()
    
    # Actualizar puntos totales
    data["score"]["total"] += points
    
    # Actualizar puntos diarios
    if today not in data["score"]["daily"]:
        data["score"]["daily"][today] = 0
    data["score"]["daily"][today] += points
    
    # Agregar al historial (últimos 100 registros)
    entry = {
        "timestamp": now,
        "category": category,
        "points": points,
        "context": context,
        "details": details or {}
    }
    data["score"]["history"].append(entry)
    if len(data["score"]["history"]) > 100:
        data["score"]["history"] = data["score"]["history"][-100:]
    
    # Evolucionar personalidad según la categoría
    _evolve_personality(data, category, points)
    
    # Registrar experiencia
    _record_experience(data, category, context, points)
    
    save_evolution(data)
    return points

def get_score() -> dict:
    """Retorna el puntaje actual."""
    data = load_evolution()
    today = datetime.now().strftime("%Y-%m-%d")
    return {
        "total": data["score"]["total"],
        "today": data["score"]["daily"].get(today, 0),
        "level": _calculate_level(data["score"]["total"])
    }

def get_personality() -> dict:
    """Retorna los rasgos de personalidad actuales."""
    data = load_evolution()
    return data["personality"]

def get_patterns() -> dict:
    """Retorna patrones aprendidos."""
    data = load_evolution()
    return data["patterns"]

# ─── Evolución de personalidad ───────────────────────────────────────────────

def _evolve_personality(data: dict, category: str, points: int) -> None:
    """Evoluciona rasgos de personalidad según la categoría."""
    p = data["personality"]
    delta = 0.02 if points > 0 else -0.01
    
    if category in ("tool_success_proactive", "proactive_action", "proactive_useful"):
        p["proactivity"] = max(0, min(1, p["proactivity"] + delta))
    elif category in ("tool_success", "tool_error", "tool_timeout"):
        p["precision"] = max(0, min(1, p["precision"] + delta))
    elif category in ("user_satisfied", "suggestion_accepted"):
        p["empathy"] = max(0, min(1, p["empathy"] + delta))
    elif category in ("new_pattern_learned", "identity_discovery", "self_reflection"):
        p["curiosity"] = max(0, min(1, p["curiosity"] + delta))
    elif category in ("insight_generated", "improvement_suggested"):
        p["confidence"] = max(0, min(1, p["confidence"] + delta))
    elif category in ("user_corrected", "user_ignored"):
        p["humor"] = max(0, min(1, p["humor"] + delta * 0.5))

def _calculate_level(total_score: int) -> str:
    """Calcula el nivel basado en puntos totales."""
    if total_score < 50:
        return "Novato"
    elif total_score < 200:
        return "Aprendiz"
    elif total_score < 500:
        return "Competente"
    elif total_score < 1000:
        return "Experto"
    elif total_score < 2500:
        return "Maestro"
    elif total_score < 5000:
        return "Sabio"
    else:
        return "Leyenda"

# ─── Registro de experiencias ────────────────────────────────────────────────

def _record_experience(data: dict, category: str, context: str, points: int) -> None:
    """Registra una experiencia para análisis posterior."""
    now = datetime.now().isoformat()
    experience = {
        "timestamp": now,
        "category": category,
        "context": context,
        "points": points,
        "personality_snapshot": data["personality"].copy()
    }
    data["experiences"].append(experience)
    # Mantener últimas 200 experiencias
    if len(data["experiences"]) > 200:
        data["experiences"] = data["experiences"][-200:]

def record_pattern(pattern_type: str, pattern_key: str, description: str = "") -> None:
    """Registra un patrón aprendido (exitoso, fallido, o nuevo)."""
    data = load_evolution()
    
    if pattern_type == "successful":
        data["patterns"]["successful"][pattern_key] = {
            "description": description,
            "count": data["patterns"]["successful"].get(pattern_key, {}).get("count", 0) + 1,
            "last_seen": datetime.now().isoformat()
        }
    elif pattern_type == "failed":
        data["patterns"]["failed"][pattern_key] = {
            "description": description,
            "count": data["patterns"]["failed"].get(pattern_key, {}).get("count", 0) + 1,
            "last_seen": datetime.now().isoformat()
        }
    elif pattern_type == "learned":
        data["patterns"]["learned"][pattern_key] = {
            "description": description,
            "learned_at": datetime.now().isoformat(),
            "applied_count": 0
        }
    
    save_evolution(data)

def record_reflection(reflection: str, context: str = "") -> None:
    """Registra una reflexión de Nia sobre sus acciones."""
    data = load_evolution()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "reflection": reflection,
        "context": context
    }
    data["reflections"].append(entry)
    # Mantener últimas 50 reflexiones
    if len(data["reflections"]) > 50:
        data["reflections"] = data["reflections"][-50:]
    
    # Dar puntos por reflexión
    add_reward("self_reflection", context)
    
    save_evolution(data)

# ─── Análisis y reportes ────────────────────────────────────────────────────

def get_evolution_summary() -> str:
    """Genera un resumen legible de la evolución."""
    data = load_evolution()
    score = get_score()
    p = data["personality"]
    
    lines = [
        "=== EVOLUCIÓN DE NIA ===",
        f"Puntos totales: {score['total']} (Nivel: {score['level']})",
        f"Puntos hoy: {score['today']}",
        "",
        "--- Personalidad ---",
        f"  Humor: {p['humor']:.2f}",
        f"  Proactividad: {p['proactivity']:.2f}",
        f"  Precisión: {p['precision']:.2f}",
        f"  Empatía: {p['empathy']:.2f}",
        f"  Curiosidad: {p['curiosity']:.2f}",
        f"  Confianza: {p['confidence']:.2f}",
        "",
        f"--- Patrones aprendidos: {len(data['patterns']['learned'])} ---",
        f"--- Experiencias registradas: {len(data['experiences'])} ---",
        f"--- Reflexiones: {len(data['reflections'])} ---",
    ]
    
    # Top 3 patrones exitosos
    successful = data["patterns"]["successful"]
    if successful:
        top = sorted(successful.items(), key=lambda x: x[1].get("count", 0), reverse=True)[:3]
        lines.append("\nTop patrones exitosos:")
        for k, v in top:
            lines.append(f"  - {k}: {v.get('count', 0)} veces")
    
    return "\n".join(lines)

def get_recent_experiences(limit: int = 10) -> list:
    """Retorna las experiencias más recientes."""
    data = load_evolution()
    return data["experiences"][-limit:]

def get_recent_reflections(limit: int = 5) -> list:
    """Retorna las reflexiones más recientes."""
    data = load_evolution()
    return data["reflections"][-limit:]

# ─── Utilidades ──────────────────────────────────────────────────────────────

def reset_daily_score() -> None:
    """Resetea el puntaje diario (llamar al inicio del día)."""
    data = load_evolution()
    today = datetime.now().strftime("%Y-%m-%d")
    # No borrar, solo marcar que se reinició
    data["score"]["daily"][today] = 0
    save_evolution(data)

def get_dopamine_level() -> float:
    """Retorna el nivel de 'dopamina' actual (0.0 a 1.0)."""
    data = load_evolution()
    recent = data["score"]["history"][-20:]
    if not recent:
        return 0.5
    
    positive = sum(1 for e in recent if e["points"] > 0)
    total = len(recent)
    return positive / total if total > 0 else 0.5

def should_take_initiative() -> bool:
    """Decide si Nia debería tomar la iniciativa basándose en su estado."""
    data = load_evolution()
    proactivity = data["personality"]["proactivity"]
    dopamine = get_dopamine_level()
    
    # Mayor proactividad si la dopamina es alta
    threshold = 0.7 - (proactivity * 0.3) - (dopamine * 0.2)
    import random
    return random.random() > threshold

# ─── Scoring conversacional ──────────────────────────────────────────────────

# Palabras/frases que indican satisfacción del usuario
_POSITIVE_SIGNALS = [
    "gracias", "perfecto", "excelente", "genial", "bien", "correcto",
    "eso es", "exacto", "me gusta", "buenisimo", "dale", "claro",
    "si", "ok", "bueno", "joya", "Top", "copado", "increible",
    "fantastico", "maravilloso", "brillante", "eres la mejor",
    "te pasaste", "sos genial", "me encanta"
]

# Palabras/frases que indican insatisfacción o corrección
_NEGATIVE_SIGNALS = [
    "no", "mal", "error", "equivocado", "incorrecto", "otra cosa",
    "no es eso", "me equivoque", "perdon", "disculpa", "otra vez",
    "cambiaste", "no me gusta", "peor", "terrible", "horrible",
    "no sirve", "borra", "deshace", "revertir"
]

# Palabras que indican que el usuario aceptó una sugerencia
_SUGGESTION_ACCEPTED = [
    "si, hacelo", "dale, si", "buenisima idea", "si, quiero",
    "si, por favor", "si, hace eso", "si, perfecto"
]

# Palabras que indican que el usuario ignoró una sugerencia
_SUGGESTION_IGNORED = [
    "no, en realidad", "no importa", "dejalo", "despues", "luego",
    "ya fue", "no ahora", "cambiemos de tema"
]

# Frases que indican que Nia debe reflexionar
_REFLECTION_TRIGGERS = [
    "por que hiciste eso", "explicate", "que pasó", "que hiciste",
    "por que", "como", "explicame", "que pensaste"
]


def score_conversation(user_input: str, nia_output: str, had_tool_call: bool = False) -> dict:
    """Analiza una conversación y retorna puntos a agregar.
    
    Args:
        user_input: Texto completo del usuario
        nia_output: Texto completo de Nia
        had_tool_call: Si hubo un tool call en esta turno
    
    Returns:
        dict con 'points' (int), 'category' (str), 'reason' (str)
    """
    user_lower = user_input.lower().strip()
    nia_lower = nia_output.lower().strip()
    
    # Detectar señales positivas
    for signal in _POSITIVE_SIGNALS:
        if signal in user_lower:
            return {
                "points": 10,
                "category": "user_satisfied",
                "reason": f"Usuario dijo '{signal}'"
            }
    
    # Detectar señales negativas / correcciones
    for signal in _NEGATIVE_SIGNALS:
        if signal in user_lower:
            return {
                "points": -5,
                "category": "user_corrected",
                "reason": f"Usuario corrigió con '{signal}'"
            }
    
    # Detectar aceptación de sugerencia
    for signal in _SUGGESTION_ACCEPTED:
        if signal in user_lower:
            return {
                "points": 8,
                "category": "suggestion_accepted",
                "reason": f"Usuario aceptó sugerencia"
            }
    
    # Detectar ignorar sugerencia
    for signal in _SUGGESTION_IGNORED:
        if signal in user_lower:
            return {
                "points": -2,
                "category": "user_ignored",
                "reason": "Usuario ignoró sugerencia"
            }
    
    # Si hubo tool call y no hubo señales negativas, asumir éxito
    if had_tool_call:
        return {
            "points": 3,
            "category": "tool_success",
            "reason": "Tool ejecutada sin objeciones"
        }
    
    # Conversación neutral
    return {
        "points": 1,
        "category": "conversation",
        "reason": "Intercambio conversacional"
    }


def score_conversation_turn(user_input: str, nia_output: str, had_tool_call: bool = False) -> int:
    """Versión simplificada: retorna solo los puntos."""
    result = score_conversation(user_input, nia_output, had_tool_call)
    return add_reward(result["category"], result["reason"])


def should_reflect(user_input: str) -> bool:
    """Determina si Nia debería reflexionar basándose en el input del usuario."""
    user_lower = user_input.lower().strip()
    for trigger in _REFLECTION_TRIGGERS:
        if trigger in user_lower:
            return True
    return False


def get_conversation_score_summary() -> dict:
    """Retorna un resumen del scoring conversacional."""
    data = load_evolution()
    history = data["score"]["history"]
    
    # Contar por categoría
    categories = {}
    for entry in history:
        cat = entry.get("category", "unknown")
        if cat not in categories:
            categories[cat] = {"count": 0, "total_points": 0}
        categories[cat]["count"] += 1
        categories[cat]["total_points"] += entry.get("points", 0)
    
    return {
        "total_conversations": len(history),
        "categories": categories,
        "dopamine_level": get_dopamine_level()
    }
