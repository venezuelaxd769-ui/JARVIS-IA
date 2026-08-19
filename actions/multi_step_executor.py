"""multi_step_executor.py — Ejecuta una secuencia de tools en orden.

Permite encadenar múltiples operaciones: leer archivo → procesar →
escribir resultado. Cada paso recibe el output del anterior como
input. Ejecuta en el mismo proceso para compartir contexto.
"""
import json
import time
from pathlib import Path


def multi_step_executor(parameters: dict, player=None) -> str:
    """Ejecuta una secuencia de steps (tools encadenadas).

    Cada step: {"tool": "nombre", "params": {...}, "save_as": "variable"}
    Resultados previos se inyectan como {variable} en params string.
    """
    steps_raw = parameters.get("steps", "[]")
    stop_on_error = str(parameters.get("stop_on_error", "true")).lower() != "false"
    max_steps = int(parameters.get("max_steps", 10))

    if isinstance(steps_raw, str):
        try:
            steps = json.loads(steps_raw)
        except json.JSONDecodeError:
            return f"Error parseando steps JSON: {steps_raw[:200]}"
    else:
        steps = steps_raw

    if not steps:
        return "Necesito al menos un step. Formato: [{\"tool\": \"nombre\", \"params\": {...}}]"
    if len(steps) > max_steps:
        return f"Demasiados steps ({len(steps)}). Máximo: {max_steps}."

    if player:
        player.write_log(f"🔗 Ejecutando {len(steps)} steps...")

    # Lookup de tools disponibles
    try:
        import importlib
        _TOOL_MODULES = {}
        for mod_name in [
            "file_controller", "code_editor", "code_search", "code_executor",
            "web_fetch", "pdf_reader", "csv_analyzer", "image_reader",
            "knowledge_base", "clipboard", "shell_exec", "git_control",
        ]:
            try:
                mod = importlib.import_module(f"actions.{mod_name}")
                # Buscar la función principal
                fn = getattr(mod, mod_name, None)
                if fn is None:
                    # Buscar cualquier función pública
                    for attr_name in dir(mod):
                        attr = getattr(mod, attr_name)
                        if callable(attr) and not attr_name.startswith("_"):
                            fn = attr
                            break
                if fn:
                    _TOOL_MODULES[mod_name] = fn
            except ImportError:
                pass
    except Exception:
        _TOOL_MODULES = {}

    # Dispatch manual de tools que no están en módulos importables
    def _execute_tool(tool_name, tool_params):
        if tool_name in _TOOL_MODULES:
            return _TOOL_MODULES[tool_name](parameters=tool_params, player=player)
        return f"Tool '{tool_name}' no disponible para multi_step."

    results = {}
    output_lines = [f"🔗 Ejecutando {len(steps)} steps:\n"]
    start_time = time.time()

    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            output_lines.append(f"Step {i+1}: formato inválido (no es dict)")
            if stop_on_error:
                break
            continue

        tool_name = step.get("tool", "")
        tool_params = dict(step.get("params", {}))
        save_as = step.get("save_as", "")

        if not tool_name:
            output_lines.append(f"Step {i+1}: sin tool name")
            if stop_on_error:
                break
            continue

        # Inyectar resultados previos en params (strings)
        for key, val in tool_params.items():
            if isinstance(val, str):
                for var_name, var_val in results.items():
                    placeholder = "{" + var_name + "}"
                    if placeholder in val:
                        tool_params[key] = val.replace(placeholder, str(var_val))

        output_lines.append(f"Step {i+1}/{len(steps)}: {tool_name}")
        try:
            result = _execute_tool(tool_name, tool_params)
            output_lines.append(f"  → {result[:200]}{'...' if len(result) > 200 else ''}")
            if save_as:
                results[save_as] = result
        except Exception as e:
            output_lines.append(f"  ❌ Error: {e}")
            if stop_on_error:
                break

    elapsed = time.time() - start_time
    output_lines.append(f"\n⏱️ Tiempo total: {elapsed:.1f}s")
    if results:
        output_lines.append(f"📦 Variables guardadas: {', '.join(results.keys())}")

    return "\n".join(output_lines)
