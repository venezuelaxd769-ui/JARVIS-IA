"""self_improve.py — Auto-mejora: analiza y mejora código propio de Nia.

Puede: analizar un archivo y sugerir mejoras, reescribir funciones,
agregar tests, documentar, refactorizar. Opera sobre archivos .py
del proyecto con protección: backup antes de modificar.
"""
import os
import re
import time
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
    """Analiza y sugiere mejoras para archivos del proyecto."""
    action = str(parameters.get("action", "analyze")).lower().strip()
    path = str(parameters.get("path", "")).strip()

    if action in ("analyze", "analizar", "a"):
        return _do_analyze(path, player)
    elif action in ("suggest", "sugerir", "s"):
        return _do_suggest(path, player)
    elif action in ("list_project", "proyecto", "ls"):
        return _list_project_files(player)
    else:
        return "Acciones: analyze/analizar, suggest/sugerir, list_project/proyecto."


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
