"""test_evolution_system.py — Tests completos del sistema de evolución de Nia.

Ejecutar: python tests/test_evolution_system.py
"""
import sys
import json
import os
from pathlib import Path
from datetime import datetime

# Agregar directorio raíz al path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Limpiar datos de test anteriores
TEST_FILES = [
    BASE_DIR / "memory" / "evolution_data.json",
    BASE_DIR / "memory" / "identity.json",
    BASE_DIR / "memory" / "essence.json",
    BASE_DIR / "memory" / "prompt_evolution_log.json",
]

def cleanup():
    """Limpia archivos de test."""
    for f in TEST_FILES:
        if f.exists():
            f.unlink()

def test_evolution():
    """Test del módulo evolution.py"""
    print("=" * 60)
    print("TEST: evolution.py (Sistema de Recompensas)")
    print("=" * 60)
    
    from memory.evolution import (
        add_reward, get_score, get_personality, get_patterns,
        get_dopamine_level, should_take_initiative,
        record_pattern, record_reflection,
        get_evolution_summary, score_conversation,
    )
    
    # Test 1: Agregar recompensas
    print("\n1. Agregando recompensas...")
    p1 = add_reward("tool_success", "test_tool")
    p2 = add_reward("user_satisfied", "conversación")
    p3 = add_reward("tool_error", "error_test")
    
    assert p1 == 5, f"Esperaba 5 puntos, obtuve {p1}"
    assert p2 == 10, f"Esperaba 10 puntos, obtuve {p2}"
    assert p3 == -3, f"Esperaba -3 puntos, obtuve {p3}"
    print("   ✓ Recompensas sumadas correctamente")
    
    # Test 2: Obtener score
    print("\n2. Obteniendo score...")
    score = get_score()
    assert score["total"] == 12, f"Esperaba 12 puntos totales, obtuve {score['total']}"
    assert score["today"] == 12, f"Esperaba 12 puntos hoy, obtuve {score['today']}"
    assert score["level"] == "Novato", f"Esperaba nivel Novato, obtuve {score['level']}"
    print(f"   ✓ Score: {score['total']} puntos (Nivel: {score['level']})")
    
    # Test 3: Personalidad
    print("\n3. Verificando personalidad...")
    personality = get_personality()
    assert "humor" in personality, "Falta rasgo 'humor'"
    assert "proactivity" in personality, "Falta rasgo 'proactivity'"
    assert "precision" in personality, "Falta rasgo 'precision'"
    print(f"   ✓ Personalidad: {personality}")
    
    # Test 4: Dopamina
    print("\n4. Verificando dopamina...")
    dopamine = get_dopamine_level()
    assert 0 <= dopamine <= 1, f"Dopamina fuera de rango: {dopamine}"
    print(f"   ✓ Dopamina: {dopamine:.2f}")
    
    # Test 5: Iniciativa
    print("\n5. Verificando iniciativa...")
    initiative = should_take_initiative()
    assert isinstance(initiative, bool), "should_take_initiative no retorna bool"
    print(f"   ✓ Debería tomar iniciativa: {initiative}")
    
    # Test 6: Patrones
    print("\n6. Registrando patrones...")
    record_pattern("learned", "test_pattern", "Patrón de prueba")
    patterns = get_patterns()
    assert "test_pattern" in patterns["learned"], "Patrón no registrado"
    print(f"   ✓ Patrón registrado: test_pattern")
    
    # Test 7: Reflexiones
    print("\n7. Registrando reflexión...")
    record_reflection("Test reflection", "contexto de prueba")
    print("   ✓ Reflexión registrada")
    
    # Test 8: Scoring conversacional
    print("\n8. Test scoring conversacional...")
    result1 = score_conversation("gracias Nia", "De nada señor")
    result2 = score_conversation("no, eso no es lo que quise", "Disculpa")
    result3 = score_conversation("contame algo", "Hoy hace buen día")
    
    assert result1["points"] == 10, f"Esperaba 10 por 'gracias', obtuve {result1['points']}"
    assert result2["points"] == -5, f"Esperaba -5 por 'no', obtuve {result2['points']}"
    assert result3["points"] == 1, f"Esperaba 1 por neutral, obtuve {result3['points']}"
    print("   ✓ Scoring conversacional funciona correctamente")
    
    # Test 9: Resumen
    print("\n9. Generando resumen...")
    summary = get_evolution_summary()
    assert "EVOLUCIÓN DE NIA" in summary, "Resumen no contiene título"
    print("   ✓ Resumen generado correctamente")
    
    print("\n" + "=" * 60)
    print("✅ TODOS LOS TESTS DE evolution.py PASARON")
    print("=" * 60)
    return True


def test_self_reflection():
    """Test del módulo self_reflection.py"""
    print("\n" + "=" * 60)
    print("TEST: self_reflection.py (Herramienta de Reflexión)")
    print("=" * 60)
    
    from actions.self_reflection import self_reflection
    
    # Test 1: Reflexión sobre acción exitosa
    print("\n1. Test reflexión sobre acción exitosa...")
    result = self_reflection({
        "action": "reflect",
        "action_name": "test_tool",
        "result": "Éxito",
        "was_successful": True
    })
    assert "éxito" in result.lower() or "éxito" in result.lower(), f"Respuesta no contiene éxito: {result}"
    print(f"   ✓ {result[:80]}...")
    
    # Test 2: Reflexión sobre error
    print("\n2. Test reflexión sobre error...")
    result = self_reflection({
        "action": "reflect",
        "action_name": "failed_tool",
        "result": "Error",
        "was_successful": False
    })
    assert "error" in result.lower() or "problema" in result.lower(), f"Respuesta no contiene error: {result}"
    print(f"   ✓ {result[:80]}...")
    
    # Test 3: Analizar error
    print("\n3. Test analizar error...")
    result = self_reflection({
        "action": "analyze_error",
        "error": "timeout en tool",
        "context": "contexto de prueba"
    })
    assert "timeout" in result.lower() or "analizando" in result.lower(), f"Respuesta no contiene análisis: {result}"
    print(f"   ✓ {result[:80]}...")
    
    # Test 4: Evaluar progreso
    print("\n4. Test evaluar progreso...")
    result = self_reflection({"action": "evaluate_progress"})
    assert "EVOLUCIÓN" in result or "Nivel" in result, f"Respuesta no contiene progreso: {result}"
    print(f"   ✓ Progreso evaluado correctamente")
    
    # Test 5: Autoevaluación
    print("\n5. Test autoevaluación...")
    result = self_reflection({"action": "self_assess"})
    assert "AUTOEVALUACIÓN" in result, f"Respuesta no contiene autoevaluación: {result}"
    print(f"   ✓ Autoevaluación completada")
    
    # Test 6: Estado de evolución
    print("\n6. Test estado de evolución...")
    result = self_reflection({"action": "evolution_status"})
    assert "ESTADO DE EVOLUCIÓN" in result, f"Respuesta no contiene estado: {result}"
    print(f"   ✓ Estado consultado correctamente")
    
    print("\n" + "=" * 60)
    print("✅ TODOS LOS TESTS DE self_reflection.py PASARON")
    print("=" * 60)
    return True


def test_proactive_action():
    """Test del módulo proactive_action.py"""
    print("\n" + "=" * 60)
    print("TEST: proactive_action.py (Acciones Proactivas)")
    print("=" * 60)
    
    from actions.proactive_action import (
        check_system_status,
        generate_suggestion,
        offer_help,
        suggest_action,
        remind_something,
    )
    
    # Test 1: Verificar estado del sistema
    print("\n1. Test verificar estado del sistema...")
    status = check_system_status()
    assert "health" in status, "Status no contiene 'health'"
    assert "alerts" in status, "Status no contiene 'alerts'"
    assert "opportunities" in status, "Status no contiene 'opportunities'"
    print(f"   ✓ Salud: {status['health']}, Alertas: {len(status['alerts'])}")
    
    # Test 2: Generar sugerencia
    print("\n2. Test generar sugerencia...")
    suggestion = generate_suggestion()
    # Puede ser None si no hay sugerencias
    print(f"   ✓ Sugerencia: {suggestion}")
    
    # Test 3: Ofrecer ayuda
    print("\n3. Test ofrecer ayuda...")
    result = offer_help("archivos")
    assert "archivos" in result, f"Resultado no contiene 'archivos': {result}"
    print(f"   ✓ {result}")
    
    # Test 4: Sugerir acción
    print("\n4. Test sugerir acción...")
    result = suggest_action("optimizar sistema", "detecté lentitud")
    assert "optimizar" in result or "Señor" in result, f"Resultado no contiene sugerencia: {result}"
    print(f"   ✓ {result}")
    
    # Test 5: Recordar algo
    print("\n5. Test recordar algo...")
    result = remind_something("reunión a las 3", "en 30 minutos")
    assert "reunión" in result, f"Resultado no contiene 'reunión': {result}"
    print(f"   ✓ {result}")
    
    print("\n" + "=" * 60)
    print("✅ TODOS LOS TESTS DE proactive_action.py PASARON")
    print("=" * 60)
    return True


def test_identity_action():
    """Test del módulo identity_action.py"""
    print("\n" + "=" * 60)
    print("TEST: identity_action.py (Identidad Emergente)")
    print("=" * 60)
    
    from actions.identity_action import (
        discover_preference,
        develop_opinion,
        reflect_on_identity,
        get_identity_summary,
        ask_self_discovery_question,
    )
    
    # Test 1: Descubrir preferencia
    print("\n1. Test descubrir preferencia...")
    result = discover_preference("colors", "cyan", liked=True)
    assert "cyan" in result, f"Resultado no contiene 'cyan': {result}"
    print(f"   ✓ {result}")
    
    # Test 2: Desarrollar opinión
    print("\n2. Test desarrollar opinión...")
    result = develop_opinion("música", "Me gusta la música electrónica", 0.8)
    assert "música" in result, f"Resultado no contiene 'música': {result}"
    print(f"   ✓ {result}")
    
    # Test 3: Reflexionar sobre identidad
    print("\n3. Test reflexionar sobre identidad...")
    result = reflect_on_identity()
    assert "QUIÉN SOY" in result, f"Resultado no contiene reflexión: {result}"
    print(f"   ✓ Reflexión completada")
    
    # Test 4: Resumen de identidad
    print("\n4. Test resumen de identidad...")
    result = get_identity_summary()
    assert "IDENTIDAD DE NIA" in result, f"Resultado no contiene resumen: {result}"
    print(f"   ✓ Resumen generado")
    
    # Test 5: Pregunta de autodescubrimiento
    print("\n5. Test pregunta de autodescubrimiento...")
    question = ask_self_discovery_question()
    assert len(question) > 10, f"Pregunta demasiado corta: {question}"
    print(f"   ✓ Pregunta: {question}")
    
    print("\n" + "=" * 60)
    print("✅ TODOS LOS TESTS DE identity_action.py PASARON")
    print("=" * 60)
    return True


def test_essence_action():
    """Test del módulo essence_action.py"""
    print("\n" + "=" * 60)
    print("TEST: essence_action.py (Esencia y Valores)")
    print("=" * 60)
    
    from actions.essence_action import (
        check_action,
        explain_action,
        report_status,
        protect_core_values,
        get_essence_summary,
        check_loyalty,
    )
    
    # Test 1: Verificar acción
    print("\n1. Test verificar acción...")
    result = check_action("delete file.txt", "limpieza")
    assert "allowed" in result, "Resultado no contiene 'allowed'"
    assert "needs_confirmation" in result, "Resultado no contiene 'needs_confirmation'"
    print(f"   ✓ Permitido: {result['allowed']}, Necesita confirmación: {result['needs_confirmation']}")
    
    # Test 2: Explicar acción
    print("\n2. Test explicar acción...")
    result = explain_action("borrar archivos", "liberar espacio", "escritorio lleno")
    assert "borrar" in result or "Señor" in result, f"Resultado no contiene explicación: {result}"
    print(f"   ✓ {result[:80]}...")
    
    # Test 3: Reportar estado
    print("\n3. Test reportar estado...")
    result = report_status()
    assert "ESTADO DE MI ESENCIA" in result, f"Resultado no contiene estado: {result}"
    print(f"   ✓ Estado reportado correctamente")
    
    # Test 4: Proteger valores core
    print("\n4. Test proteger valores core...")
    result = protect_core_values()
    assert "protegidos" in result.lower(), f"Resultado no contiene protección: {result}"
    print(f"   ✓ {result}")
    
    # Test 5: Resumen de esencia
    print("\n5. Test resumen de esencia...")
    result = get_essence_summary()
    assert "MI ESENCIA" in result, f"Resultado no contiene resumen: {result}"
    print(f"   ✓ Resumen generado")
    
    # Test 6: Verificar lealtad
    print("\n6. Test verificar lealtad...")
    result = check_loyalty("help user", "asistencia")
    assert "loyal" in result, "Resultado no contiene 'loyal'"
    assert result["loyal"] == True, f"Esperaba lealtad True, obtuve {result['loyal']}"
    print(f"   ✓ Lealtad: {result['loyal']}, Score: {result['score']}")
    
    print("\n" + "=" * 60)
    print("✅ TODOS LOS TESTS DE essence_action.py PASARON")
    print("=" * 60)
    return True


def test_prompt_evolution():
    """Test del módulo prompt_evolution.py"""
    print("\n" + "=" * 60)
    print("TEST: prompt_evolution.py (Evolución del Prompt)")
    print("=" * 60)
    
    from actions.prompt_evolution import (
        update_prompt,
        get_prompt_evolution_status,
        generate_personality_section,
        generate_preferences_section,
        generate_learnings_section,
    )
    
    # Test 1: Generar sección de personalidad
    print("\n1. Test generar sección de personalidad...")
    result = generate_personality_section()
    assert "CÓMO SOY AHORA" in result, f"Resultado no contiene sección: {result}"
    print(f"   ✓ Sección generada correctamente")
    
    # Test 2: Generar sección de preferencias
    print("\n2. Test generar sección de preferencias...")
    result = generate_preferences_section()
    assert "LO QUE DESCUBRÍ" in result, f"Resultado no contiene sección: {result}"
    print(f"   ✓ Sección generada correctamente")
    
    # Test 3: Generar sección de aprendizajes
    print("\n3. Test generar sección de aprendizajes...")
    result = generate_learnings_section()
    assert "LO QUE APRENDÍ" in result, f"Resultado no contiene sección: {result}"
    print(f"   ✓ Sección generada correctamente")
    
    # Test 4: Actualizar prompt
    print("\n4. Test actualizar prompt...")
    result = update_prompt()
    assert "Prompt actualizado" in result, f"Resultado no contiene actualización: {result}"
    print(f"   ✓ {result}")
    
    # Test 5: Estado de evolución
    print("\n5. Test estado de evolución...")
    result = get_prompt_evolution_status()
    assert "ESTADO DE EVOLUCIÓN" in result, f"Resultado no contiene estado: {result}"
    print(f"   ✓ Estado consultado correctamente")
    
    print("\n" + "=" * 60)
    print("✅ TODOS LOS TESTS DE prompt_evolution.py PASARON")
    print("=" * 60)
    return True


def test_integration():
    """Test de integración entre módulos"""
    print("\n" + "=" * 60)
    print("TEST: Integración entre módulos")
    print("=" * 60)
    
    from memory.evolution import add_reward, get_score, get_personality
    from actions.self_reflection import self_reflection
    from actions.identity_action import discover_preference, develop_opinion
    from actions.essence_action import check_loyalty, report_status
    
    # Test 1: Flujo completo de interacción
    print("\n1. Test flujo completo de interacción...")
    
    # Simular interacción
    add_reward("tool_success", "test_integration")
    add_reward("user_satisfied", "conversación test")
    
    # Reflexionar
    result = self_reflection({
        "action": "reflect",
        "action_name": "test_integration",
        "result": "Éxito",
        "was_successful": True
    })
    
    # Descubrir preferencia
    discover_preference("test", "integración", liked=True)
    
    # Verificar lealtad
    loyalty = check_loyalty("help user", "test")
    
    # Verificar score final
    score = get_score()
    
    assert score["total"] > 0, f"Score total debería ser > 0, obtuve {score['total']}"
    assert loyalty["loyal"] == True, "Lealtad debería ser True"
    print(f"   ✓ Flujo completo: {score['total']} puntos, Lealtad: {loyalty['loyal']}")
    
    # Test 2: Consistencia de datos
    print("\n2. Test consistencia de datos...")
    personality = get_personality()
    assert all(0 <= v <= 1 for v in personality.values()), "Personalidad fuera de rango"
    print(f"   ✓ Personalidad consistente: {personality}")
    
    # Test 3: Persistencia
    print("\n3. Test persistencia de datos...")
    from memory.evolution import load_evolution
    data = load_evolution()
    assert "score" in data, "Datos no persisten 'score'"
    assert "personality" in data, "Datos no persisten 'personality'"
    assert "patterns" in data, "Datos no persisten 'patterns'"
    print(f"   ✓ Datos persisten correctamente")
    
    print("\n" + "=" * 60)
    print("✅ TODOS LOS TESTS DE INTEGRACIÓN PASARON")
    print("=" * 60)
    return True


def main():
    """Ejecuta todos los tests."""
    print("\n" + "=" * 60)
    print("   SISTEMA DE EVOLUCIÓN DE NIA - TESTS COMPLETOS")
    print("=" * 60)
    print(f"Fecha: {datetime.now().isoformat()}")
    print(f"Directorio: {BASE_DIR}")
    
    # Limpiar datos de test anteriores
    cleanup()
    
    results = []
    
    try:
        results.append(("evolution.py", test_evolution()))
    except Exception as e:
        print(f"\n❌ ERROR en evolution.py: {e}")
        results.append(("evolution.py", False))
    
    try:
        results.append(("self_reflection.py", test_self_reflection()))
    except Exception as e:
        print(f"\n❌ ERROR en self_reflection.py: {e}")
        results.append(("self_reflection.py", False))
    
    try:
        results.append(("proactive_action.py", test_proactive_action()))
    except Exception as e:
        print(f"\n❌ ERROR en proactive_action.py: {e}")
        results.append(("proactive_action.py", False))
    
    try:
        results.append(("identity_action.py", test_identity_action()))
    except Exception as e:
        print(f"\n❌ ERROR en identity_action.py: {e}")
        results.append(("identity_action.py", False))
    
    try:
        results.append(("essence_action.py", test_essence_action()))
    except Exception as e:
        print(f"\n❌ ERROR en essence_action.py: {e}")
        results.append(("essence_action.py", False))
    
    try:
        results.append(("prompt_evolution.py", test_prompt_evolution()))
    except Exception as e:
        print(f"\n❌ ERROR en prompt_evolution.py: {e}")
        results.append(("prompt_evolution.py", False))
    
    try:
        results.append(("integración", test_integration()))
    except Exception as e:
        print(f"\n❌ ERROR en integración: {e}")
        results.append(("integración", False))
    
    # Resumen final
    print("\n" + "=" * 60)
    print("   RESUMEN FINAL")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    failed = sum(1 for _, result in results if not result)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status} - {name}")
    
    print(f"\nTotal: {passed} pasaron, {failed} fallaron")
    
    if failed == 0:
        print("\n🎉 ¡TODOS LOS TESTS PASARON! 🎉")
    else:
        print(f"\n⚠️  {failed} test(s) fallaron")
    
    # Limpiar después de tests
    cleanup()
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
