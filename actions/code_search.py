"""code_search.py — Busca archivos y contenido en código fuente.

Usa ripgrep (rg) para búsquedas de contenido (rápido) y Python puro
para buscar por nombre de archivo (glob). Diseñado para que Nia pueda
entender y navegar cualquier proyecto en el disco.
"""
import os
import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

_RG_TIMEOUT = 12.0
_MAX_RESULTS = 40

_SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".tox",
    "dist", "build", ".mypy_cache", ".pytest_cache", "logs", "env",
    ".eggs", "*.egg-info",
}

_TEXT_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".java", ".kt", ".rs", ".go", ".rb", ".php", ".swift",
    ".html", ".css", ".scss", ".less", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash", ".zsh",
    ".md", ".txt", ".rst", ".sql", ".xml", ".vue", ".svelte",
    ".gd", ".gdscript", ".tscn", ".tres", ".cfg",
}


def _run(cmd, timeout=_RG_TIMEOUT):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", errors="replace"), r.returncode
    except subprocess.TimeoutExpired:
        return "[Timeout]", 1
    except Exception as e:
        return f"[Error: {e}]", 1


def _grep(pattern, path, include=None, max_results=_MAX_RESULTS, ignore_case=False):
    cmd = ["rg", "--no-heading", "--line-number", "--color=never",
           "--max-count", str(max_results * 2)]
    if ignore_case:
        cmd.append("-i")
    if include:
        for ext in (include if isinstance(include, list) else [include]):
            cmd += ["-g", f"*{ext}" if ext.startswith(".") else f"*.{ext}"]
    for skip in _SKIP_DIRS:
        cmd += ["--glob", f"-{skip}"]
    cmd += [pattern, path or "."]
    out, rc = _run(cmd)
    if rc == 1 and not out.strip():
        return "No se encontraron coincidencias."
    lines = out.strip().split("\n")[:max_results]
    return "\n".join(lines) if lines else "Sin resultados."


def _glob(pattern, path, max_results=_MAX_RESULTS):
    base = Path(path or ".").resolve()
    results = []
    try:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, base)
                if fnmatch(rel, pattern) or fnmatch(f, pattern):
                    results.append(rel)
                    if len(results) >= max_results:
                        return "\n".join(results)
        return "\n".join(results) if results else "No se encontraron archivos."
    except Exception as e:
        return f"Error: {e}"


def _list_dir(path, max_results=_MAX_RESULTS):
    base = Path(path or ".").resolve()
    try:
        entries = sorted(os.listdir(base))
        dirs = [f"{e}/" for e in entries if os.path.isdir(base / e)
                and not e.startswith(".") and e not in _SKIP_DIRS]
        files = [e for e in entries if os.path.isfile(base / e)
                 and not e.startswith(".")]
        lines = ["📁 Directorio: " + str(base)]
        if dirs:
            lines.append(f"  Subdirectorios ({len(dirs)}):")
            for d in dirs[:15]:
                lines.append(f"    {d}")
            if len(dirs) > 15:
                lines.append(f"    ... y {len(dirs)-15} más.")
        if files:
            lines.append(f"  Archivos ({len(files)}):")
            for f in files[:20]:
                size = (base / f).stat().st_size
                unit = "B"
                if size > 1024:
                    size, unit = size / 1024, "KB"
                if size > 1024:
                    size, unit = size / 1024, "MB"
                lines.append(f"    {f}  ({size:.1f} {unit})")
            if len(files) > 20:
                lines.append(f"    ... y {len(files)-20} más.")
        return "\n".join(lines)
    except Exception as e:
        return f"Error al listar: {e}"


def code_search(parameters: dict, player=None) -> str:
    """Busca archivos y contenido en código fuente de proyectos."""
    action = str(parameters.get("action", "grep")).lower().strip()
    pattern = str(parameters.get("pattern", "")).strip()
    path = str(parameters.get("path", "")).strip()
    include = str(parameters.get("include", "")).strip() or None
    max_r = max(5, min(int(parameters.get("max_results", 30) or 30), 50))
    ignore_case = str(parameters.get("ignore_case", "")).lower() in ("true", "1", "yes", "si")

    if action in ("grep", "search", "buscar"):
        if not pattern:
            return "Decime qué pattern querés buscar (regex)."
        if player:
            player.write_log(f"🔍 Buscando '{pattern}' en {path or 'proyecto actual'}...")
        return _grep(pattern, path, include, max_r, ignore_case)

    if action in ("glob", "files", "archivos"):
        if not pattern:
            return "Decime el patrón de nombre (ej: '*.py', 'test_*.js')."
        if player:
            player.write_log(f"📂 Buscando archivos '{pattern}'...")
        return _glob(pattern, path, max_r)

    if action in ("list", "ls", "directorio"):
        if player:
            player.write_log(f"📂 Listando {path or 'directorio actual'}...")
        return _list_dir(path or ".", max_r)

    return "Acción desconocida. Usá: grep/search, glob/files, o list/ls."
