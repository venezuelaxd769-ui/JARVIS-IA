"""self_improve.py — Auto-mejora: analiza, mejora y SE REPARA código propio de Nia.

Puede: analizar un archivo y sugerir mejoras, reescribir funciones,
agregar tests, documentar, refactorizar. Y con la acción 'heal/arreglar'
Nia diagnostica un módulo que falla, pide a DeepSeek un patch mínimo,
lo VERIFICA en una copia (compile + import), lo aplica con backup y
hace rollback automático si rompe la compilación.

Opera sobre archivos .py del proyecto con protección: backup antes de modificar.
"""
import os
import re
import time
import json
import difflib
import shutil
import importlib.util
import py_compile as _py_compile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ACTIONS_DIR = _REPO / "actions"


def _backup_file(path):
    """Crea backup antes de modificar."""
    backup_dir = _REPO / ".backups"
    backup_dir.mkdir(exist_ok=True)
    ts = int(time.time())
    name = Path(path).name
    backup = backup_dir / f"{name}.{ts}.bak"
    try:
        import shutil
        shutil.copy2(path, backup)
        return str(backup)
    except Exception:
        return None


def _analyze_code(path):
    """Analiza un archivo .py y devuelve métricas."""
    try:
        content = Path(path).read_text(encoding="utf-8")
    except Exception as e:
        return {"error": str(e)}

    lines = content.split("\n")
    functions = re.findall(r"def (\w+)\(", content)
    classes = re.findall(r"class (\w+)", content)
    imports = re.findall(r"^(?:from|import)\s+", content, re.MULTILINE)

    # Detectar problemas comunes
    issues = []
    if len(lines) > 200:
        issues.append(f"Archivo largo ({len(lines)} líneas) — considerar dividir")
    for func in functions:
        pattern = re.compile(rf"def {func}\(.*?\).*?:\n(.*?)(?=\ndef |\nclass |\Z)", re.DOTALL)
        match = pattern.search(content)
        if match:
            body = match.group(1)
            body_lines = [l for l in body.split("\n") if l.strip()]
            if len(body_lines) > 50:
                issues.append(f"Función '{func}' muy larga ({len(body_lines)} líneas)")

    # Complejidad ciclomática básica
    complexity = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("if ", "elif ", "for ", "while ", "try:", "except")):
            complexity += 1
        if " and " in stripped or " or " in stripped:
            complexity += 1

    # Duplicación
    unique_lines = set(l.strip() for l in lines if l.strip() and not l.strip().startswith("#"))
    dup_ratio = 1 - (len(unique_lines) / max(len([l for l in lines if l.strip()]), 1))

    return {
        "lines": len(lines),
        "functions": len(functions),
        "function_names": functions[:20],
        "classes": len(classes),
        "imports": len(imports),
        "cyclomatic_complexity": complexity,
        "duplication_ratio": round(dup_ratio, 2),
        "issues": issues,
    }


def _generate_improvements(path, analysis):
    """Genera sugerencias de mejora basadas en el análisis."""
    suggestions = []

    if analysis.get("lines", 0) > 200:
        suggestions.append({
            "type": "refactor",
            "priority": "alta",
            "description": f"Archivo con {analysis['lines']} líneas. Dividir en módulos más pequeños.",
        })

    if analysis.get("cyclomatic_complexity", 0) > 15:
        suggestions.append({
            "type": "refactor",
            "priority": "media",
            "description": f"Complejidad ciclomática alta ({analysis['cyclomatic_complexity']}). Simplificar lógica.",
        })

    if analysis.get("duplication_ratio", 0) > 0.3:
        suggestions.append({
            "type": "dedup",
            "priority": "media",
            "description": f"Duplicación alta ({analysis['duplication_ratio']*100:.0f}%). Extraer funciones comunes.",
        })

    for issue in analysis.get("issues", []):
        suggestions.append({
            "type": "issue",
            "priority": "media",
            "description": issue,
        })

    if not suggestions:
        suggestions.append({
            "type": "ok",
            "priority": "baja",
            "description": "El código parece saludable. No hay problemas detectados.",
        })

    return suggestions


def self_improve(parameters: dict, player=None) -> str:
    """Analiza, sugiere mejoras y repara código del proyecto."""
    action = str(parameters.get("action", "analyze")).lower().strip()
    path = str(parameters.get("path", "")).strip()

    if action in ("analyze", "analizar", "a"):
        return _do_analyze(path, player)
    elif action in ("suggest", "sugerir", "s", "improve"):
        return _do_suggest(path, player)
    elif action in ("list_project", "proyecto", "ls"):
        return _list_project_files(player)
    elif action in ("heal", "arreglar", "reparar", "fix"):
        return _heal(parameters, player)
    else:
        return "Acciones: analyze/analizar, suggest/sugerir, heal/arreglar (reparar un módulo que falla), list_project/proyecto."


# ─────────────────────────── Auto-reparación ───────────────────────────
# Módulos de seguridad que Nia no debe parcharse sola en caliente.
_HEAL_DENY = {"self_edit", "self_improve", "learning", "auto_programmer", "main"}


def _or_key() -> str:
    p = _REPO / "config" / "api_keys.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("openrouter_api_key", "")
    except Exception:
        return ""


def _ask_patch(source: str, tool: str, error: str) -> dict:
    """Pide un patch mínimo (target/replacement) a DeepSeek por OpenRouter."""
    import urllib.request

    key = _or_key()
    if not key:
        return {}
    prompt = (
        f"Sos un ingeniero experto. El módulo actions/{tool}.py de un asistente de "
        "escritorio (Python) falla. Este es el error:\n"
        f"{error[:1200]}\n\n"
        "Encontrá el bug y armá un fix MÍNIMO y localizado. Este es el código actual:\n\n"
        f"```python\n{source[:7000]}\n```\n\n"
        "Respondé ÚNICAMENTE un JSON con dos campos:\n"
        "- 'target': el bloque de texto EXACTO a reemplazar, copiado tal cual aparece "
        "en el código (respetá indentación y comillas).\n"
        "- 'replacement': el bloque corregido completo.\n"
        "El fix no debe cambiar la firma de la función ni agregar imports innecesarios. "
        "Sin explicaciones. Solo JSON."
    )
    payload = {
        "model": "deepseek/deepseek-chat-v3-0324",
        "max_tokens": 2200,
        "messages": [{"role": "user", "content": prompt}],
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
        with urllib.request.urlopen(req, timeout=35) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
    except Exception:
        return {}
    # Extraer objeto JSON (tolerante a fences)
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        patch = json.loads(text[start:end + 1])
    except Exception:
        return {}
    target = str(patch.get("target", "") or "").strip()
    replacement = str(patch.get("replacement", "") or "")
    if not target or not replacement:
        return {}
    return {"target": target, "replacement": replacement}


def _heal(parameters: dict, player) -> str:
    """Repara un módulo de actions/ que viene fallando. Seguro: verifica en copia,
    aplica con backup y hace rollback si la compilación real se rompe."""
    tool = str(parameters.get("tool", "") or parameters.get("file", "")).strip()
    error = str(parameters.get("error", "") or parameters.get("traceback", "")).strip()
    apply_now = (str(parameters.get("apply", "")).strip() == "SÍ autorizo"
                 or str(parameters.get("confirm", "")).strip() == "SÍ autorizo")

    if not tool:
        return "Decime qué herramienta reparar (tool='nombre', ej: tool='computer_settings')."
    tool = tool.replace("\\", "/").split("/")[-1].replace(".py", "").replace(".pyc", "")

    if tool in _HEAL_DENY:
        return f"'{tool}' es parte de mi núcleo; no me parcheo sola en caliente por seguridad."

    path = _ACTIONS_DIR / f"{tool}.py"
    if not path.exists():
        if (_ACTIONS_DIR / f"{tool}.pyc").exists() or (_ACTIONS_DIR / f"{tool}.py").exists():
            return f"El módulo '{tool}' no tiene fuente .py editable (es bytecode o no encontré falla)."
        return f"No encontré el módulo actions/{tool}.py."

    source = path.read_text(encoding="utf-8", errors="replace")
    if not error:
        error = "(sin detalle: reparación preventiva) Dato: la herramienta viene fallando en tu entorno."

    if player:
        player.write_log(f"🛠️ Diagnóstico de actions/{tool}.py...")

    # Reintenta el patch hasta 3 veces; el fix SOLO pasa si verifica:
    # 1) target es exacto  2) compila en copia  3) importa en copia  4) no cambia la firma
    patch = {}
    verified = None
    last_blocker = "sin respuesta de IA"
    for attempt in range(3):
        if attempt > 0:
            _log(player, f"🔄 Reintento de diagnóstico {attempt + 1}/3...")
        patch = _ask_patch(source, tool, error)
        if not patch:
            last_blocker = "sin respuesta de IA (sin key de OpenRouter o falló la llamada)"
            continue
        if patch["target"] not in source:
            last_blocker = "el patch no coincide exactamente con el código"
            continue
        new_source = source.replace(patch["target"], patch["replacement"], 1)

        # Verificar en COPIA (compile + import)
        import tempfile
        with tempfile.TemporaryDirectory(prefix="nia_heal_") as tmp:
            copy = Path(tmp) / f"{tool}.py"
            copy.write_text(new_source, encoding="utf-8")
            try:
                _py_compile.compile(str(copy), doraise=True)
            except Exception as e:
                last_blocker = f"el fix no compila ({e})"
                continue
            spec = importlib.util.spec_from_file_location(f"nia_heal_{tool}", copy)
            try:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception as e:
                last_blocker = f"el fix rompe el import ({e})"
                continue
            if not callable(getattr(mod, tool, None)):
                last_blocker = "el fix cambió la firma pública"
                continue
        verified = new_source
        break

    if verified is None:
        _log(player, f"⛔ No encontré fix válido para {tool} ({last_blocker}).")
        return (f"No pude armar un fix seguro para '{tool}': {last_blocker}. "
                "Todos los candidatos fallaron la verificación o no hubo respuesta de IA; "
                "no toco nada. Reintentá más tarde o pasame el traceback.")

    patch, new_source = patch, verified

    old_text = source if source.endswith("\n") else source + "\n"
    new_text = new_source if new_source.endswith("\n") else new_source + "\n"
    diff = "".join(difflib.unified_diff(
        old_text.splitlines(keepends=True), new_text.splitlines(keepends=True), n=2))[:1200]

    if not apply_now:
        return (
            f"🛠️ Fix encontrado para {tool}:\n\n{diff}\n\n"
            "Está verificado (compila e importa en copia) pero NO lo apliqué todavía. "
            "Para que lo aplique con backup y rollback automático, que el Señor diga 'SÍ autorizo'."
        )

    # 2) Aplicar con backup
    from actions.self_edit import _make_backup
    backup = _make_backup(path)
    path.write_text(new_source, encoding="utf-8")
    _log(player, f"💾 Backup: {Path(backup).name}")

    # 3) Re-verificar el real; rollback si rompe
    try:
        _py_compile.compile(str(path), doraise=True)
    except Exception as e:
        shutil.copy2(backup, path)
        _log(player, f"⛔ El fix rompió la compilación real; rollback automático hecho.")
        return f"El fix rompió la compilación real ({e}). Hice rollback al backup {backup}."

    return (
        f"✅ Reparé actions/{tool}.py.\n"
        f"Verificado: compila e importa. Backup: {backup}.\n"
        f"Cambio aplicado:\n\n{diff}"
    )


def _log(player, msg: str):
    if player:
        try:
            player.write_log(msg)
        except Exception:
            pass


def _do_analyze(path, player):
    if not path:
        return "Necesito la ruta del archivo a analizar."

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Archivo no encontrado: {path}"

    if player:
        player.write_log(f"🔍 Analizando: {os.path.basename(path)}...")

    analysis = _analyze_code(path)

    if "error" in analysis:
        return f"Error: {analysis['error']}"

    lines = [f"📊 Análisis de {os.path.basename(path)}"]
    lines.append(f"   Líneas: {analysis['lines']}")
    lines.append(f"   Funciones: {analysis['functions']} ({', '.join(analysis['function_names'][:10])})")
    lines.append(f"   Clases: {analysis['classes']}")
    lines.append(f"   Imports: {analysis['imports']}")
    lines.append(f"   Complejidad ciclomática: {analysis['cyclomatic_complexity']}")
    lines.append(f"   Ratio de duplicación: {analysis['duplication_ratio']*100:.0f}%")

    if analysis.get("issues"):
        lines.append("\n⚠️ Problemas detectados:")
        for issue in analysis["issues"]:
            lines.append(f"  • {issue}")

    return "\n".join(lines)


def _do_suggest(path, player):
    if not path:
        return "Necesito la ruta del archivo."

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Archivo no encontrado: {path}"

    if player:
        player.write_log(f"💡 Generando sugerencias para: {os.path.basename(path)}...")

    analysis = _analyze_code(path)
    if "error" in analysis:
        return f"Error: {analysis['error']}"

    suggestions = _generate_improvements(path, analysis)

    lines = [f"💡 Mejoras sugeridas para {os.path.basename(path)}:\n"]
    for i, s in enumerate(suggestions):
        prio = {"alta": "🔴", "media": "🟡", "baja": "⚪"}.get(s["priority"], "⚪")
        lines.append(f"{prio} [{s['type']}] {s['description']}")

    return "\n".join(lines)


def _list_project_files(player):
    """Lista archivos .py del proyecto."""
    files = []
    for py in sorted(_ACTIONS_DIR.glob("*.py")):
        size = py.stat().st_size
        lines = len(py.read_text(encoding="utf-8", errors="replace").split("\n"))
        files.append(f"  📄 {py.name} — {lines} líneas, {size:,} bytes")

    main_py = _REPO / "main.py"
    if main_py.exists():
        lines = len(main_py.read_text(encoding="utf-8", errors="replace").split("\n"))
        files.insert(0, f"  📄 main.py — {lines} líneas")

    return f"📁 Archivos del proyecto ({len(files)}):\n" + "\n".join(files)
