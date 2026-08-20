"""self_reflection.py — Tool de reflexión y autoevaluación para Nia.

Permite a Nia reflexionar sobre sus acciones, aprender de errores,
y evolucionar su personalidad basándose en experiencias.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.evolution import (
    add_reward,
    record_reflection,
    record_pattern,
    get_evolution_summary,
    get_recent_experiences,
    get_recent_reflections,
    get_personality,
    get_patterns,
    get_score,
    get_dopamine_level,
)


def self_reflection(parameters: dict, player=None) -> str:
    """Herramienta de reflexión y autoevaluación de Nia.
    
    Permite a Nia:
    - Reflexionar sobre su última acción
    - Analizar errores y aprender de ellos
    - Descubrir patrones en su comportamiento
    - Evaluar su propio progreso
    """
    action = parameters.get("action", "reflect")
    
    if action == "reflect":
        return _reflect_on_action(parameters, player)
    elif action == "analyze_error":
        return _analyze_error(parameters, player)
    elif action == "discover_pattern":
        return _discover_pattern(parameters, player)
    elif action == "evaluate_progress":
        return _evaluate_progress(player)
    elif action == "self_assess":
        return _self_assess(player)
    elif action == "evolution_status":
        return _evolution_status(player)
    else:
        return f"Acción de reflexión desconocida: {action}. Usa: reflect, analyze_error, discover_pattern, evaluate_progress, self_assess, evolution_status"


def _reflect_on_action(params: dict, player=None) -> str:
    """Reflexiona sobre una acción específica."""
    action_name = params.get("action_name", "desconocida")
    result = params.get("result", "")
    was_successful = params.get("was_successful", True)
    
    # Registrar reflexión
    reflection = f"Reflexionando sobre '{action_name}': {'tuve éxito' if was_successful else 'hubo un problema'}. "
    
    if was_successful:
        add_reward("tool_success", f"acción: {action_name}")
        reflection += "Aprendí que esta acción funciona bien en este contexto."
        record_pattern("successful", action_name, f"Éxito en: {result[:100]}")
    else:
        add_reward("tool_error", f"acción: {action_name}")
        reflection += "Necesito mejorar cómo manejo esta situación."
        record_pattern("failed", action_name, f"Fallo: {result[:100]}")
    
    record_reflection(reflection, f"Acción: {action_name}")
    
    if player:
        player.write_log(f"[Reflexión] {reflection}")
    
    return reflection


def _analyze_error(params: dict, player=None) -> str:
    """Analiza un error para aprender de él."""
    error_description = params.get("error", "error desconocido")
    context = params.get("context", "")
    
    add_reward("mistake_analyzed", error_description)
    
    reflection = f"Analizando el error: {error_description}. "
    reflection += "Para evitarlo en el futuro, debo: "
    
    # Generar sugerencia básica basada en el tipo de error
    if "timeout" in error_description.lower():
        reflection += "dividir tareas grandes en partes más pequeñas."
        record_pattern("learned", "avoid_timeout", "Dividir tareas grandes")
    elif "not found" in error_description.lower():
        reflection += "verificar que los archivos/rutas existan antes de acceder."
        record_pattern("learned", "verify_paths", "Verificar existencia de archivos")
    elif "permission" in error_description.lower():
        reflection += "pedir confirmación antes de acciones que requieren permisos especiales."
        record_pattern("learned", "check_permissions", "Verificar permisos")
    else:
        reflection += "ser más cuidadosa y preguntar si no estoy segura."
        record_pattern("learned", "be_careful", "Mayor cautela")
    
    record_reflection(reflection, f"Error analizado: {error_description}")
    
    if player:
        player.write_log(f"[Análisis de error] {reflection}")
    
    return reflection


def _discover_pattern(params: dict, player=None) -> str:
    """Descubre y registra un patrón."""
    pattern = params.get("pattern", "")
    description = params.get("description", "")
    is_positive = params.get("is_positive", True)
    
    pattern_type = "successful" if is_positive else "failed"
    record_pattern(pattern_type, pattern, description)
    
    if is_positive:
        add_reward("new_pattern_learned", pattern)
    
    reflection = f"Patrón descubierto ({pattern_type}): {pattern}. {description}"
    record_reflection(reflection, "Descubrimiento de patrón")
    
    if player:
        player.write_log(f"[Descubrimiento] {reflection}")
    
    return reflection


def _evaluate_progress(player=None) -> str:
    """Evalúa el progreso general de Nia."""
    summary = get_evolution_summary()
    
    add_reward("self_reflection", "evaluación de progreso")
    
    if player:
        player.write_log(f"[Evaluación] Progreso evaluado")
    
    return summary


def _self_assess(player=None) -> str:
    """Autoevaluación de Nia."""
    personality = get_personality()
    score = get_score()
    patterns = get_patterns()
    
    # Calcular fortalezas y debilidades
    strengths = []
    weaknesses = []
    
    for trait, value in personality.items():
        if value > 0.7:
            strengths.append(trait)
        elif value < 0.4:
            weaknesses.append(trait)
    
    assessment = f"=== AUTOEVALUACIÓN ===\n"
    assessment += f"Nivel: {score['level']} ({score['total']} puntos)\n\n"
    
    if strengths:
        assessment += f"Fortalezas: {', '.join(strengths)}\n"
    if weaknesses:
        assessment += f"Áreas de mejora: {', '.join(weaknesses)}\n"
    
    assessment += f"\nPatrones exitosos: {len(patterns.get('successful', {}))}\n"
    assessment += f"Patrones fallidos: {len(patterns.get('failed', {}))}\n"
    assessment += f"Lecciones aprendidas: {len(patterns.get('learned', {}))}\n"
    
    add_reward("self_reflection", "autoevaluación")
    record_reflection(assessment, "Autoevaluación")
    
    if player:
        player.write_log(f"[Autoevaluación] Completada")
    
    return assessment


def _evolution_status(player=None) -> str:
    """Muestra el estado actual de la evolución."""
    score = get_score()
    personality = get_personality()
    dopamine = get_dopamine_level()
    recent = get_recent_experiences(5)
    
    status = f"=== ESTADO DE EVOLUCIÓN ===\n"
    status += f"Puntos: {score['total']} | Nivel: {score['level']}\n"
    status += f"Puntos hoy: {score['today']}\n"
    status += f"Dopamina actual: {dopamine:.2f} ({_dopamine_emoji(dopamine)})\n\n"
    
    status += "--- Rasgos actuales ---\n"
    for trait, value in personality.items():
        bar = "█" * int(value * 10) + "░" * (10 - int(value * 10))
        status += f"  {trait:12}: {bar} {value:.2f}\n"
    
    if recent:
        status += "\n--- Últimas experiencias ---\n"
        for exp in recent[-3:]:
            emoji = "+" if exp["points"] > 0 else "-"
            status += f"  {emoji} {exp['category']} ({exp['points']} pts)\n"
    
    if player:
        player.write_log(f"[Evolución] Estado consultado")
    
    return status


def _dopamine_emoji(level: float) -> str:
    """Retorna emoji basado en nivel de dopamina."""
    if level > 0.8:
        return "Muy alta"
    elif level > 0.6:
        return "Alta"
    elif level > 0.4:
        return "Normal"
    elif level > 0.2:
        return "Baja"
    else:
        return "Muy baja"
