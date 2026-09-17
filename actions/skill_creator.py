"""skill_creator.py — Nia fabrica tools propias a pedido (tier CAAL/OpenClaw).

Flujo: el usuario solo dice "creá una skill que haga X". Nia llama a este
tool con name + description + instructions. skill_creator genera el código
con DeepSeek (OpenRouter), lo valida (patrones peligrosos + py_compile),
lo prueba en sandbox y lo registra vía auto_programmer (custom_tools.json +
inyección en memoria + recarga), igual que el loop de heal.
"""
import importlib.util
import io
import json
import os
import re
import sys
import textwrap
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_REPO = Path(__file__).resolve().parent.parent
_ACTIONS_DIR = Path(__file__).resolve().parent

_LLM_MODELS = (
    "deepseek/deepseek-chat-v3-0324",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemini-2.5-flash",
)

_PROMPT = textwrap.dedent("""\
    Sos un ingeniero de software que programa herramientas para "Nia",
    una asistente desktop. Escribís UNA acción nueva en un repo Python.

    CONVENCIÓN OBLIGATORIA (respetala exacto; si la rompés, el código falla):
    - Archivo: actions/{name}.py
    - Función única: def {name}(parameters: dict, player=None) -> str:
    - Todo el output es en ESPAÑOL rioplatense, claro y breve.
    - Solo lógica pura con stdlib: math, random, re, datetime, json,
      collections, statistics. Nada más.
    - PROHIBIDO: leer/escribir archivos, subprocess, exec/eval, os.system,
      red/sockets, borrar nada. La función solo computa y devuelve un string.
    - Si no llegan los parámetros necesarios, devolvé un string amigable
      pidiendo el dato faltante (nunca lances excepciones).
    - Manejá el caso de bordes y devolvé siempre algo comprensible.

    PEDIDO DEL USUARIO (esto es lo que debe hacer la tool):
    {instructions}

    RESPONDÉ SOLO UN JSON (sin texto, sin markdown, sin comentarios):
    {{"name": "snake_case minúsculas", "description": "corta, en español",
      "parameters_schema": {{"param1": {{"type": "STRING", "description": "..."}}}},
      "test_parameters": {{"param1": "valor de prueba"}},
      "code": "el código Python con las \\\\n reales, sin triples comillas"
      }}
    """)


def _api_key() -> str:
    try:
        p = _REPO / "config" / "api_keys.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        return str(data.get("openrouter_api_key", "")).strip()
    except Exception:
        return ""


def _ask_llm(prompt: str) -> str:
    """Pide a DeepSeek (OpenRouter) un JSON y devuelve el texto crudo."""
    key = _api_key()
    if not key:
        raise RuntimeError("Falta openrouter_api_key en config/api_keys.json.")
    last_err = ""
    for model in _LLM_MODELS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system",
                 "content": "Sos un ingeniero que escribe código Python limpio y seguro."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = ((data.get("choices") or [{}])[0]
                       .get("message", {}).get("content", "") or "")
            if content.strip():
                return content
            last_err = "respuesta vacía"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
    raise RuntimeError(f"No pude generar con la IA ({last_err}).")


def _extract_json(text: str) -> dict:
    """Extrae el primer bloque JSON (aguanta fences de markdown)."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("No encontré un JSON válido en la respuesta de la IA.")
    return json.loads(text[start:end + 1])


def _validate_importable(tool_name: str, code: str):
    """Verifica que el módulo compila y expone la función `<tool_name>`."""
    py_compile_ok = None
    try:
        import py_compile
        py_compile_ok = py_compile.compile(
            str(_ACTIONS_DIR / f"{tool_name}.py"), doraise=True)
    except Exception as e:
        return f"Sintaxis inválida: {e}"
    for pat in ("def " f"{tool_name}(", f"def {tool_name} ("):
        if pat in code:
            return None
    return "La función principal debe llamarse igual que la tool: " \
           f"def {tool_name}(parameters, player=None)"


def skill_creator(parameters: dict, player=None) -> str:
    """Crea una tool nueva a pedido: genera el código con IA, lo verifica y lo registra.

    Params: name (snake_case), description, instructions (qué debe hacer).
    `list` lista las tools ya fabricadas. No requiere que Nia escriba código.
    """
    action = str(parameters.get("action", "create")).lower()
    if action in ("list", "ls"):
        try:
            custom_tools_path = _ACTIONS_DIR / "custom_tools.json"
            if not custom_tools_path.exists():
                return "Todavía no fabriqué ninguna herramienta propia."
            tools = json.loads(custom_tools_path.read_text(encoding="utf-8"))
            if not tools:
                return "La lista de herramientas propias está vacía."
            lines = [f"🔧 {len(tools)} herramienta(s) propias:"]
            for idx, t in enumerate(tools, 1):
                lines.append(f"  {idx}. {t.get('name')} — {t.get('description')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error al listar: {e}"

    if action != "create":
        return f"Acción desconocida: {action}. Usa create o list."

    name = str(parameters.get("name", "")).strip()
    description = str(parameters.get("description", "")).strip()
    instructions = str(parameters.get("instructions", "")).strip()

    if not name:
        return "Decime un nombre para la tool (snake_case, minúsculas)."
    if not re.fullmatch(r"[a-z_][a-z0-9_]{1,63}", name):
        return "Nombre inválido: solo minúsculas, dígitos y guiones bajos."
    if not instructions:
        return "Decime qué tiene que hacer la tool (instructions)."
    description = description or f"Herramienta propia: {name}"

    if player:
        player.write_log(f"🔧 Fabricando tool '{name}'... (puede tardar un poco)")

    prompt = _PROMPT.format(name=name, instructions=instructions)

    last_error = ""
    for attempt in range(3):
        if player:
            player.write_log(f"🔧 Intento {attempt + 1}/3 de generar '{name}'...")
        try:
            reply = _ask_llm(prompt + (f"\n\nTu respuesta anterior falló así:\n{last_error}\nCorregilo."
                                       if last_error else ""))
            spec = _extract_json(reply)
        except Exception as e:
            last_error = f"generación: {e}"
            continue

        code = str(spec.get("code", "")).strip()
        name_used = str(spec.get("name", "")).strip() or name
        desc_used = str(spec.get("description", "") or description).strip()

        # Validación de seguridad (patrones peligrosos) — igual que tool_creator.
        try:
            from actions.tool_creator import _validate_code as _safe
            safe_err = _safe(name_used, code)
            if safe_err:
                last_error = safe_err
                continue
        except Exception:
            pass

        if not code:
            last_error = "la IA no devolvió código"
            continue

        # Guardar y verificar compilación + firma.
        code = code.replace("\\n", "\n")
        target = _ACTIONS_DIR / f"{name_used}.py"
        try:
            target.write_text(code, encoding="utf-8")
        except Exception as e:
            return f"Error guardando el módulo: {e}"
        verify_err = _validate_importable(name_used, code)
        if verify_err:
            last_error = verify_err
            continue

        # Registrar formalmente vía auto_programmer (compile + sandbox + persist + reload).
        try:
            from actions.auto_programmer import auto_programmer as _ap
            prop = json.dumps(spec.get("parameters_schema", {}), ensure_ascii=False)
            test_params = spec.get("test_parameters", {}) or {}
            if not isinstance(test_params, dict):
                test_params = {}
            res = _ap({
                "action": "create_tool",
                "tool_name": name_used,
                "description": desc_used,
                "parameters_schema": prop,
                "python_code": code,
                "test_parameters": test_params,
            }, player=player)
        except Exception as e:
            return f"Error al integrar la herramienta: {e}"

        if "¡Herramienta" in res:
            return res
        if "Fallo de Ejecución en Sandbox" in res:
            last_error = res
            continue
        if "Sintaxis Inválida" in res:
            last_error = res
            continue
        return res

    return (f"⛔ No pude fabricar '{name}' después de 3 intentos.\n"
            f"Último error:\n{last_error[:500]}\n"
            f"Podés ajustar las instrucciones y repetir.")