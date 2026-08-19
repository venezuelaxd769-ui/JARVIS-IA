"""doc_generator.py — Genera documentación de código Python.

Parsea docstrings, firmas de funciones, y genera documentación
en Markdown. Puede documentar archivos específicos o todo el proyecto.
"""
import ast
import os
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def _extract_docstring(node):
    """Extrae docstring de un nodo AST."""
    return ast.get_docstring(node) or ""


def _extract_args(node):
    """Extrae argumentos de una función."""
    args = []
    for arg in node.args.args:
        name = arg.arg
        if name == "self" or name == "cls":
            continue
        annotation = ""
        if arg.annotation:
            if isinstance(arg.annotation, ast.Name):
                annotation = arg.annotation.id
            elif isinstance(arg.annotation, ast.Constant):
                annotation = str(arg.annotation.value)
        args.append(f"{name}: {annotation}" if annotation else name)
    return args


def _document_function(node, indent=""):
    """Documenta una función."""
    name = node.name
    args = _extract_args(node)
    docstring = _extract_docstring(node)

    ret = ""
    if node.returns:
        if isinstance(node.returns, ast.Name):
            ret = f" -> {node.returns.id}"

    lines = [f"{indent}### `{name}({', '.join(args)}){ret}`"]
    if docstring:
        lines.append(f"{indent}{docstring}")
    lines.append("")

    return "\n".join(lines)


def _document_class(node, indent=""):
    """Documenta una clase."""
    name = node.name
    docstring = _extract_docstring(node)
    bases = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            bases.append(base.id)

    lines = [f"{indent}## Class `{name}`{'(' + ', '.join(bases) + ')' if bases else ''}"]
    if docstring:
        lines.append(f"{indent}{docstring}")
    lines.append("")

    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if item.name.startswith("_") and item.name != "__init__":
                continue
            lines.append(_document_function(item, indent + "  "))

    return "\n".join(lines)


def _document_file(path):
    """Genera documentación de un archivo .py."""
    try:
        content = Path(path).read_text(encoding="utf-8")
        tree = ast.parse(content)
    except Exception as e:
        return f"Error procesando {path}: {e}"

    filename = os.path.basename(path)
    lines = [f"# {filename}\n"]

    # Module docstring
    module_doc = ast.get_docstring(tree)
    if module_doc:
        lines.append(f"{module_doc}\n")

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            lines.append(_document_class(node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_"):
                continue
            lines.append(_document_function(node))
        elif isinstance(node, ast.Assign):
            # Constants
            for target in node.targets:
                if isinstance(target, ast.Name) and target.name.isupper():
                    lines.append(f"- `{target.name}`")

    return "\n".join(lines)


def doc_generator(parameters: dict, player=None) -> str:
    """Genera documentación de código Python."""
    action = str(parameters.get("action", "file")).lower().strip()
    path = str(parameters.get("path", "")).strip()

    if action in ("file", "archivo", "f"):
        if not path:
            return "Necesito la ruta del archivo."
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            return f"Archivo no encontrado: {path}"
        if player:
            player.write_log(f"📝 Generando docs de {os.path.basename(path)}...")
        return _document_file(path)

    if action in ("project", "proyecto", "p"):
        if player:
            player.write_log("📝 Generando documentación del proyecto...")
        files = sorted(_ACTIONS_DIR.glob("*.py"))
        lines = [f"# Documentación del Proyecto JARVIS-IA\n"]
        lines.append(f"Generado automáticamente por doc_generator.\n")

        for f in files:
            if f.name.startswith("_"):
                continue
            doc = _document_file(str(f))
            if doc and len(doc) > 50:
                lines.append(f"\n---\n\n{doc}")

        result = "\n".join(lines)

        # Guardar
        output = _REPO / "docs" / "API.md"
        output.parent.mkdir(exist_ok=True)
        output.write_text(result, encoding="utf-8")
        return f"📄 Documentación generada: {output}\n   {len(files)} archivos procesados"

    if action in ("stats", "estadísticas"):
        files = list(_ACTIONS_DIR.glob("*.py"))
        total_lines = 0
        total_funcs = 0
        total_classes = 0
        documented = 0

        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                tree = ast.parse(content)
                total_lines += len(content.split("\n"))
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_funcs += 1
                        if ast.get_docstring(node):
                            documented += 1
                    elif isinstance(node, ast.ClassDef):
                        total_classes += 1
            except Exception:
                continue

        return (f"📊 Estadísticas del proyecto:\n"
                f"  Archivos: {len(files)}\n"
                f"  Líneas totales: {total_lines:,}\n"
                f"  Funciones: {total_funcs}\n"
                f"  Clases: {total_classes}\n"
                f"  Documentadas: {documented}/{total_funcs} "
                f"({documented/max(total_funcs,1)*100:.0f}%)")

    return "Acciones: file/archivo (requiere path), project/proyecto, stats/estadísticas."


_ACTIONS_DIR = _REPO / "actions"
