# -*- coding: utf-8 -*-
"""codebase.py — Analizador e indexador de proyectos de código (real).

Qué hace Nia con esto:
- ¿Qué hace este proyecto? → info genera un informe final y en español.
- Buscar en código / "¿dónde está la función X?" → search y find_symbol.
- Generate docs → documentación automática del proyecto a markdown.

100% local (stdlib): construye un índice ligero en memory/codebase_index/
con estructura, símbolos (funciones/clases con su línea) y contenido
acotado, y responde sin depender de servicios externos.
"""
import json
import os
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

sys.setrecursionlimit(3000)

INDEX_DIR = Path(__file__).resolve().parent.parent / "memory" / "codebase_index"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

_MAX_FILES = 400
_MAX_READ = 256 * 1024
_MAX_SYMBOLS_FILE = 250

_SKIP_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules", ".tox",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".eggs", ".nox",
    "coverage", "htmlcov", "logs", "backups", "env",
}

_TEXT_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".java", ".kt", ".rs", ".go", ".rb", ".php", ".swift",
    ".html", ".css", ".scss", ".less", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".sh", ".bash", ".zsh",
    ".md", ".txt", ".rst", ".sql", ".xml", ".vue", ".svelte",
    ".gd", ".godot", ".tscn", ".tres", ".m", ".mm",
}

_ENTRY_NAMES = {
    "main.py", "app.py", "index.js", "index.ts", "main.go", "main.rs",
    "main.cpp", "main.c", "program.cs", "server.py", "__main__.py",
    "manage.py", "cli.py", "run.py", "bot.py",
}

_SYMBOL_PATTERNS = {
    ".py": re.compile(r"^(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)"),
    ".js": re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$]\w*)|^(?:const|let|var)\s+([A-Za-z_$]\w*)\s*=\s*(?:async\s*)?(?:function|\(.*\)\s*=>)|^(?:export\s+)?class\s+([A-Za-z_$]\w*)"),
    ".ts": re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$]\w*)|^(?:export\s+)?(?:class|interface|type|enum)\s+([A-Za-z_$]\w*)"),
    ".c": re.compile(r"^([A-Za-z_]\w*)\s*\([^;]*\)\s*\{|^(?:static\s+)?[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*\("),
    ".cpp": re.compile(r"^([A-Za-z_]\w*)\s*\([^;]*\)\s*\{|^(?:class|struct)\s+([A-Za-z_]\w*)"),
    ".java": re.compile(r"^(?:public|private|protected|static|final|abstract|synchronized|native|default|strictfp|transient)?\s*(?:public|private|protected|static|final|abstract|synchronized|native|default|strictfp|transient)?\s*(class|interface|enum)\s+([A-Za-z_]\w*)|(?:public|private|protected|static|final|synchronized)\s+[\w<>\[\], \.]+\([^;{}]*\)\s*(?:throws\s+[\w, ]*\s*)?\{"),
    ".go": re.compile(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\("),
    ".rs": re.compile(r"^(?:pub\s+)?fn\s+([a-z_]\w*)|^(?:pub\s+)?(?:struct|enum|trait|impl)\s+([A-Za-z_]\w*)"),
    ".kt": re.compile(r"^fun\s+([A-Za-z_]\w*)\s*\(|^(?:class|interface|object)\s+([A-Za-z_]\w*)"),
    ".cs": re.compile(r"^(?:public|private|protected|internal|static|sealed|abstract|readonly)?\s*(?:public|private|protected|internal|static|sealed|abstract)?\s*(?:class|interface|struct|enum)\s+([A-Za-z_]\w*)|(?:public|private|protected|internal|static|virtual|async)?\s*[\w<>\[\], \.]+\s+([A-Za-z_]\w*)\s*\("),
    ".php": re.compile(r"^(?:public|private|protected|static|final|abstract)?\s*(?:public|private|protected|static|final|abstract)?\s*function\s+([A-Za-z_]\w*)|^(?:class|interface|trait)\s+([A-Za-z_]\w*)"),
    ".rb": re.compile(r"^(?:def|class|module)\s+([A-Za-z_]\w*)"),
    ".swift": re.compile(r"^func\s+([a-z_]\w*)|^(?:class|struct|enum|protocol|extension)\s+([A-Za-z_]\w*)"),
}

_GENERIC_SYMBOL = re.compile(r"\b(?:def|function|class|func|fn|struct|interface|type|module)\s+([A-Za-z_]\w*)")


def _text_ext(ext):
    return ext in _TEXT_EXTS


def _read_snippet(path: Path) -> str | None:
    try:
        if path.stat().st_size > 1024 * 1024:
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(_MAX_READ)
    except Exception:
        return None


def _first_meaningful(text):
    for line in text.splitlines()[:6]:
        s = line.strip(" \t#*;\"'").strip()
        if s:
            return s[:220]
    return ""


def _extract_docstring(text, ext):
    if ext == ".py":
        m = re.search(r'("""|\'\'\')(.*?)(\1)', text, re.S)
        if m:
            return m.group(2).strip().replace("\n", " ")[:260]
    m = re.search(r"/\*\*(.*?)\*/", text, re.S)
    if m:
        return m.group(1).strip().replace("\n", " ")[:260]
    return ""


def _scan_symbols(text, ext):
    pat = _SYMBOL_PATTERNS.get(ext, _GENERIC_SYMBOL)
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for m in pat.finditer(line):
            name = next((g for g in m.groups() if g), "")
            if name and name != "main":
                out.append({"name": name, "line": i})
    return out[: _MAX_SYMBOLS_FILE]


def _walk_files(base):
    files = []
    for root, dirs, names in os.walk(base):
        dirs[:] = [d for d in dirs
                   if d not in _SKIP_DIRS and not d.startswith(".")]
        for f in sorted(names):
            if len(files) >= _MAX_FILES:
                return files
            files.append(Path(root) / f)
    return files


def _find_readme(base):
    for probe in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
        p = base / probe
        if p.exists():
            try:
                return p.read_text("utf-8", errors="replace")
            except Exception:
                return ""
    return ""


def _tree(base, max_shown=18):
    lines = []
    shown = 0
    try:
        entries = sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        for e in entries:
            if e.name.startswith(".") or e.name in _SKIP_DIRS:
                continue
            prefix = "📁" if e.is_dir() else "📄"
            lines.append(f"    {prefix} {e.name}")
            shown += 1
            if shown >= max_shown:
                lines.append("    ... (más elementos)")
                break
    except Exception:
        pass
    return lines


def _detect_lang(ext_counts):
    markers = {
        "Python": {".py"} | {".pyw"},
        "TypeScript": {".ts", ".tsx"},
        "JavaScript": {".js", ".mjs", ".cjs"},
        "Rust": {".rs"},
        "Go": {".go"},
        "C": {".c", ".h"},
        "C++": {".cpp", ".hpp", ".cc"},
        "C#": {".cs"},
        "Java": {".java"},
        "Kotlin": {".kt"},
        "Ruby": {".rb"},
        "PHP": {".php"},
        "Swift": {".swift"},
        "C/ObjC": {".m", ".mm"},
    }
    ranked = []
    for name, exts in markers.items():
        total = sum(ext_counts.get(e, 0) for e in exts)
        if total:
            ranked.append((total, name))
    ranked.sort(reverse=True)
    return ranked[0][1] if ranked else None


def build_index(base):
    base = Path(base).resolve()
    files = _walk_files(base)
    ext_counts = {}
    entries = []
    total_lines = 0
    readme = _find_readme(base)
    modules = []
    for p in files:
        try:
            rel = str(p.relative_to(base))
        except Exception:
            rel = p.name
        ext = p.suffix.lower()
        if _text_ext(ext):
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
        size = p.stat().st_size
        if p.name in _ENTRY_NAMES:
            entries.append(rel)
        text = None
        if ext != ".pyc" and _text_ext(ext):
            text = _read_snippet(p)
        info = {
            "rel": rel,
            "ext": ext,
            "size": size,
            "lines": 0,
            "desc": "",
            "symbols": [],
        }
        if text:
            info["lines"] = text.count("\n") + 1
            total_lines += info["lines"]
            info["desc"] = _extract_docstring(text, ext) or _first_meaningful(text)
            info["symbols"] = _scan_symbols(text, ext)
        modules.append(info)
    lang = _detect_lang(ext_counts)
    return {
        "name": base.name,
        "path": str(base),
        "lang": lang,
        "files_total": len(files),
        "lines_total": total_lines,
        "ext_counts": ext_counts,
        "entries": entries[:6],
        "readme": readme[:4500],
        "tree": _tree(base),
        "modules": modules,
    }


def _index_path(name):
    return INDEX_DIR / f"{name}.json"


def index_project(base, name=None):
    base = Path(base)
    if not base.is_dir():
        return f"Ruta no válida: {base}"
    data = build_index(base)
    if name:
        data["name"] = name
    _index_path(data["name"]).write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    f = data["files_total"]
    l = data["lang"] or "desconocido"
    sym = sum(len(m["symbols"]) for m in data["modules"])
    return (
        f"✅ Proyecto '{data['name']}' indexado: {f} archivos, "
        f"{data['lines_total']} líneas, lenguaje {l}, {sym} símbolos. "
        "Podés preguntar '¿qué hace?' (info), buscar (search), o generar docs."
    )


def _load_index(project, path):
    data = None
    if project:
        p = _index_path(project)
        if p.exists():
            data = json.loads(p.read_text("utf-8"))
    if data is None and path:
        for p in INDEX_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text("utf-8"))
            except Exception:
                continue
            if d.get("path") and Path(d["path"]).resolve() == Path(path).resolve():
                data = d
                break
    return data


def _info_report(data):
    lines = [f"📁 Proyecto '{data['name']}' ({data.get('path', '')})"]
    if data.get("lang"):
        lines.append(f"   Lenguaje: {data['lang']}")
    lines.append(
        f"   Archivos: {data['files_total']} | Líneas: {data['lines_total']}"
    )
    readme = (data.get("readme") or "").strip()
    if readme:
        first = readme.splitlines()
        essence = next((l.strip() for l in first if l.strip() and not l.strip().startswith("#")), "")
        if essence:
            lines.append(f"   Qué dice el README: {essence[:240]}")
    exts = data.get("ext_counts") or {}
    if exts:
        top = ", ".join(f"{e}({n})" for e, n in
                        sorted(exts.items(), key=lambda x: -x[1])[:6])
        lines.append(f"   Extensiones: {top}")
    entries = data.get("entries") or []
    if entries:
        lines.append(f"   Punto de entrada: {', '.join(entries[:5])}")
    tree = data.get("tree") or []
    if tree:
        lines.append("   Estructura:")
        lines.extend(tree)
    modules = [m for m in data.get("modules", [])
               if (m.get("desc") or "") and m["ext"] in {".py", ".js", ".ts", ".go", ".rs", ".kt", ".cs", ".java"}]
    if modules:
        lines.append("   Módulos y su función:")
        for m in modules[:10]:
            lines.append(f"    • {m['rel']}: {m['desc'][:180]}")
    if not modules and not readme:
        lines.append("   Sin descripciones: probá 'indexar <ruta>' para refrescar.")
    return "\n".join(lines)


def _search(data, query):
    toks = [t for t in re.split(r"\W+", query.lower()) if len(t) > 1]
    hits = []
    for m in data.get("modules", []):
        rel = m["rel"].lower()
        score = 4 * sum(1 for t in toks if t in rel)
        score += sum(1 for t in toks if t in m["desc"].lower())
        score += sum(1 for s in m["symbols"] if any(t in s["name"].lower() for t in toks))
        if score:
            hits.append((score, m))
    hits.sort(key=lambda x: -x[0])
    out = []
    shown = 0
    for score, m in hits[:6]:
        path = Path(data["path"]) / m["rel"]
        snippet = m["desc"][:160]
        text = _read_snippet(path)
        if text:
            low = text.lower()
            for t in toks:
                idx = low.find(t)
                if idx >= 0:
                    line_no = text[:idx].count("\n") + 1
                    start = max(0, text.rfind("\n", 0, idx) + 1) if idx > 0 else 0
                    end = text.find("\n", idx)
                    snippet = text[start: end if end > 0 else idx + 180].strip()[:180]
                    break
        out.append(f"· {m['rel']} (línea ~{m['lines']}) → {snippet}")
        shown += 1
    return "\n".join(out) if out else "Sin resultados."


def _find_symbol(data, symbol):
    out = []
    for m in data.get("modules", []):
        for s in m["symbols"]:
            if s["name"].lower() == symbol.lower():
                out.append(f"{m['rel']}:{s['line']}  ({s['name']})")
    if out:
        return "\n".join(out[:25])
    prefix = []
    for m in data.get("modules", []):
        for s in m["symbols"]:
            if symbol.lower() in s["name"].lower():
                prefix.append(f"{m['rel']}:{s['line']}  ({s['name']})")
    if prefix:
        return "Sin coincidencia exacta. Similares:\n" + "\n".join(prefix[:15])
    return "No encontré ese símbolo en el índice."


def _gen_docs(data):
    md = ["# " + data["name"], "", "## Resumen", _info_report(data), "", "## Módulos"]
    md.append("| Archivo | Símbolos |")
    md.append("| --- | --- |")
    for m in data.get("modules", [])[:60]:
        n = len(m["symbols"])
        md.append(f"| {m['rel']} | {n} |")
    md_text = "\n".join(md)
    docs_dir = INDEX_DIR / "docs"
    docs_dir.mkdir(exist_ok=True)
    out_path = docs_dir / f"{data['name']}.md"
    out_path.write_text(md_text, encoding="utf-8")
    head = "\n".join(md_text.splitlines()[:40])
    return f"Documentación guardada en {out_path}.\n\n{head}"


def _list_projects():
    items = []
    for p in sorted(INDEX_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text("utf-8"))
            items.append(f"· {d.get('name', p.stem)} → {d.get('path', '?')} "
                         f"({d.get('files_total', 0)} archivos)")
        except Exception:
            continue
    return "\n".join(items) if items else "Todavía no hay proyectos indexados."


def codebase(parameters: dict, player=None, speak=None) -> str:
    """Analiza e indexa proyectos de código; responde qué hace, dónde está
    un símbolo, busca en el código y genera documentación."""
    action = str(parameters.get("action", "info")).lower().strip()
    path = str(parameters.get("path", "")).strip()
    project = str(parameters.get("project", "")).strip()
    query = str(parameters.get("query", "")).strip()
    symbol = str(parameters.get("symbol", "")).strip()
    name = str(parameters.get("name", "")).strip()

    if player:
        player.write_log(f"💻 codebase: {action}" + (f" '{path or project}'" if path or project else ""))

    if action in ("index", "indexar"):
        base = path or str(Path.cwd())
        if not Path(base).is_dir():
            return f"La ruta '{base}' no es un directorio válido."
        return index_project(Path(base), name or None)

    if action in ("list", "lista"):
        return _list_projects()

    if action in ("remove", "borrar"):
        p = _index_path(project or name or path)
        if p.exists():
            p.unlink()
            return f"Índice '{p.stem}' eliminado."
        return f"No existe el índice '{project or name or path}'."

    data = _load_index(project, path)
    if data is None:
        base = path or str(Path.cwd())
        if Path(base).is_dir():
            return (f"No hay índice para '{base.name}'. Decile "
                    "'indexa el proyecto en <ruta>' para prepararlo.")
        return ("No encuentro ese proyecto indexado. Pedile "
                "'indexa el proyecto' con la ruta, y después pregunten lo que sea.")

    if action in ("info", "overview", "resumen"):
        return _info_report(data)

    if action in ("search", "buscar", "find"):
        if not query:
            return "Decime el texto a buscar (ej: action='search', query='token')."
        return _search(data, query)

    if action in ("find_symbol", "symbol"):
        if not symbol:
            return "Decime el nombre del símbolo (función/clase) a buscar."
        return _find_symbol(data, symbol)

    if action in ("generate_docs", "docs"):
        return _gen_docs(data)

    return ("Acción no reconocida. Uso: index | list | info | search | "
            "find_symbol | generate_docs | remove")