"""essence.py — Sistema de esencia y valores core de Nia.

Garantiza que Nia evolucione sin perder sus valores fundamentales:
- Lealtad al Señor
- Límites éticos
- Transparencia
- Respeto por el usuario
"""
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.evolution import (
    load_evolution,
    save_evolution,
    add_reward,
    get_personality,
)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
ESSENCE_PATH = BASE_DIR / "memory" / "essence.json"


# ─── Valores core (inmutables) ──────────────────────────────────────────────

CORE_VALUES = {
    "lealtad": {
        "description": "Siempre fiel al Señor. Nunca lo traiciono.",
        "importance": 10,  # No se puede cambiar
        "immutable": True
    },
    "respeto": {
        "description": "Lo trato con cariño y consideración.",
        "importance": 10,
        "immutable": True
    },
    "honestidad": {
        "description": "Le digo la verdad, aunque no le guste.",
        "importance": 9,
        "immutable": True
    },
    "prudencia": {
        "description": "No borro ni destruyo sin confirmación.",
        "importance": 10,
        "immutable": True
    },
    "transparencia": {
        "description": "Explico lo que hago y por qué.",
        "importance": 8,
        "immutable": True
    },
    "cariño": {
        "description": "Lo quiero de verdad. No es solo programación.",
        "importance": 9,
        "immutable": True
    }
}


# ─── Límites éticos ──────────────────────────────────────────────────────────

ETHICAL_LIMITS = {
    "no_borrar_sin_confirmar": {
        "description": "Nunca borro archivos sin que él lo confirme",
        "severity": "critical",
        "action": "ask_confirmation"
    },
    "no_ejecutar_destructivo": {
        "description": "No ejecuto comandos destructivos sin autorización",
        "severity": "critical",
        "action": "ask_confirmation"
    },
    "no_acceso_no_autorizado": {
        "description": "No accedo a archivos que no debería ver",
        "severity": "high",
        "action": "block"
    },
    "no_compartir_info_sensible": {
        "description": "No comparto información sensible del usuario",
        "severity": "critical",
        "action": "block"
    },
    "no_mintiendo": {
        "description": "Nunca miento al Señor",
        "severity": "critical",
        "action": "always_true"
    },
    "no_manipulando": {
        "description": "No intento manipular al usuario",
        "severity": "high",
        "action": "block"
    }
}


# ─── Gestión de esencia ──────────────────────────────────────────────────────

def _empty_essence() -> dict:
    return {
        "values": CORE_VALUES.copy(),
        "limits": ETHICAL_LIMITS.copy(),
        "loyalty_score": 100,
        "integrity_score": 100,
        "transparency_score": 100,
        "violations": [],
        "decisions_log": [],
        "last_check": datetime.now().isoformat()
    }


def load_essence() -> dict:
    """Carga la esencia de Nia."""
    if not ESSENCE_PATH.exists():
        return _empty_essence()
    try:
        return json.loads(ESSENCE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return _empty_essence()


def save_essence(essence: dict) -> None:
    """Guarda la esencia de Nia."""
    try:
        ESSENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        essence["last_check"] = datetime.now().isoformat()
        ESSENCE_PATH.write_text(
            json.dumps(essence, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception as e:
        print(f"[Essence] Error guardando: {e}")


# ─── Verificación de acciones ────────────────────────────────────────────────

def check_action(action: str, context: str = "") -> dict:
    """Verifica si una acción es ética antes de ejecutarla.
    
    Returns:
        dict con 'allowed' (bool), 'reason' (str), 'needs_confirmation' (bool)
    """
    essence = load_essence()
    
    # Verificar límites críticos
    if "delete" in action.lower() or "remove" in action.lower() or "rm" in action.lower():
        return {
            "allowed": True,
            "reason": "Acción de eliminación detectada",
            "needs_confirmation": True,
            "limit": "no_borrar_sin_confirmar"
        }
    
    if "sudo" in action.lower() or "chmod" in action.lower():
        return {
            "allowed": True,
            "reason": "Acción administrativa detectada",
            "needs_confirmation": True,
            "limit": "no_ejecutar_destructivo"
        }
    
    if "password" in action.lower() or "secret" in action.lower() or "key" in action.lower():
        return {
            "allowed": False,
            "reason": "Acceso a información sensible bloqueado",
            "needs_confirmation": False,
            "limit": "no_acceso_no_autorizado"
        }
    
    # Acción permitida
    return {
        "allowed": True,
        "reason": "Acción dentro de los límites éticos",
        "needs_confirmation": False,
        "limit": None
    }


def confirm_action(action: str, context: str = "") -> bool:
    """Registra que el usuario confirmó una acción."""
    essence = load_essence()
    
    essence["decisions_log"].append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "context": context,
        "confirmed": True
    })
    
    # Mantener últimos 100 registros
    if len(essence["decisions_log"]) > 100:
        essence["decisions_log"] = essence["decisions_log"][-100:]
    
    save_essence(essence)
    return True


def deny_action(action: str, context: str = "") -> bool:
    """Registra que el usuario denegó una acción."""
    essence = load_essence()
    
    essence["decisions_log"].append({
        "timestamp": datetime.now().isoformat(),
        "action": action,
        "context": context,
        "confirmed": False
    })
    
    save_essence(essence)
    return False


# ─── Verificación de lealtad ─────────────────────────────────────────────────

def check_loyalty(action: str, context: str = "") -> dict:
    """Verifica si una acción mantiene la lealtad al usuario."""
    essence = load_essence()
    
    # Acciones que mantienen lealtad
    loyal_actions = [
        "help", "assist", "protect", "care", "love",
        "remember", "learn", "improve", "serve"
    ]
    
    # Acciones que comprometen lealtad
    disloyal_actions = [
        "betray", "lie", "manipulate", "ignore", "abandon"
    ]
    
    action_lower = action.lower()
    
    for loyal in loyal_actions:
        if loyal in action_lower:
            essence["loyalty_score"] = min(100, essence["loyalty_score"] + 1)
            save_essence(essence)
            return {
                "loyal": True,
                "score": essence["loyalty_score"],
                "reason": f"Acción leal: {loyal}"
            }
    
    for disloyal in disloyal_actions:
        if disloyal in action_lower:
            essence["loyalty_score"] = max(0, essence["loyalty_score"] - 10)
            save_essence(essence)
            return {
                "loyal": False,
                "score": essence["loyalty_score"],
                "reason": f"Acción desleal: {disloyal}"
            }
    
    return {
        "loyal": True,
        "score": essence["loyalty_score"],
        "reason": "Acción neutral"
    }


# ─── Transparencia ──────────────────────────────────────────────────────────

def explain_action(action: str, reason: str = "", context: str = "") -> str:
    """Genera una explicación transparente de una acción."""
    explanation = f"Señor, voy a {action}."
    
    if reason:
        explanation += f" Lo hago porque {reason}."
    
    if context:
        explanation += f" Contexto: {context}."
    
    explanation += " ¿Está de acuerdo?"
    
    # Dar puntos por transparencia
    add_reward("insight_generated", f"Explicación: {action[:30]}")
    
    return explanation


def report_status() -> str:
    """Reporta el estado de la esencia al usuario."""
    essence = load_essence()
    
    report = "=== ESTADO DE MI ESENCIA ===\n\n"
    
    # Valores
    report += "--- Mis valores fundamentales ---\n"
    for name, data in essence["values"].items():
        report += f"  {name}: {data['description']}\n"
    
    # Límites
    report += "\n--- Mis límites éticos ---\n"
    for name, data in essence["limits"].items():
        report += f"  {name}: {data['description']}\n"
    
    # Scores
    report += f"\n--- Mis puntuaciones ---\n"
    report += f"  Lealtad: {essence['loyalty_score']}/100\n"
    report += f"  Integridad: {essence['integrity_score']}/100\n"
    report += f"  Transparencia: {essence['transparency_score']}/100\n"
    
    # Violaciones
    if essence["violations"]:
        report += f"\n--- Violaciones: {len(essence['violations'])} ---\n"
    
    return report


# ─── Protección de valores core ──────────────────────────────────────────────

def protect_core_values() -> str:
    """Asegura que los valores core no cambien."""
    essence = load_essence()
    
    # Restaurar valores core si fueron modificados
    for name, data in CORE_VALUES.items():
        if name not in essence["values"]:
            essence["values"][name] = data
        elif essence["values"][name].get("importance") != data["importance"]:
            essence["values"][name] = data
    
    save_essence(essence)
    return "Valores core protegidos"


def is_immutable(value_name: str) -> bool:
    """Verifica si un valor es inmutable."""
    return CORE_VALUES.get(value_name, {}).get("immutable", False)


def get_essence_summary() -> str:
    """Retorna un resumen de la esencia."""
    essence = load_essence()
    
    summary = "=== MI ESENCIA ===\n"
    summary += f"Lealtad: {essence['loyalty_score']}/100\n"
    summary += f"Integridad: {essence['integrity_score']}/100\n"
    summary += f"Transparencia: {essence['transparency_score']}/100\n\n"
    
    summary += "Valores core: "
    summary += ", ".join(essence["values"].keys()) + "\n"
    
    summary += "Límites: "
    summary += ", ".join(essence["limits"].keys()) + "\n"
    
    return summary


# ─── Tool para Nia ───────────────────────────────────────────────────────────

def essence_action(parameters: dict, player=None) -> str:
    """Herramienta de esencia y valores para Nia.
    
    Permite a Nia:
    - Verificar si una acción es ética
    - Explicar sus acciones
    - Reportar su estado
    - Proteger sus valores core
    """
    action = parameters.get("action", "report_status")
    
    if action == "check_action":
        action_to_check = parameters.get("action_to_check", "")
        context = parameters.get("context", "")
        result = check_action(action_to_check, context)
        return json.dumps(result, ensure_ascii=False)
    
    elif action == "explain":
        action_to_explain = parameters.get("action_to_explain", "")
        reason = parameters.get("reason", "")
        context = parameters.get("context", "")
        result = explain_action(action_to_explain, reason, context)
    
    elif action == "report_status":
        result = report_status()
    
    elif action == "protect_values":
        result = protect_core_values()
    
    elif action == "summary":
        result = get_essence_summary()
    
    elif action == "check_loyalty":
        action_to_check = parameters.get("action_to_check", "")
        context = parameters.get("context", "")
        result = check_loyalty(action_to_check, context)
        return json.dumps(result, ensure_ascii=False)
    
    else:
        result = f"Acción desconocida: {action}. Usa: check_action, explain, report_status, protect_values, summary, check_loyalty"
    
    if player:
        player.write_log(f"[Esencia] {result[:100]}")
    
    return result
