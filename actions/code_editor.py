"""code_editor.py — Lee, analiza y modifica archivos de código fuente.

Fase 2: escritura con dry-run. Toda operación de escritura puede
ejecutarse en modo vista previa (dry_run=true) para que el usuario
vea los cambios antes de aplicar. Las escrituras se registran en el log.
"""
import os
from pathlib import Path

_MAX_LINES = 500
_MAX_WRITE_SIZE = 200 * 1024  # 200 KB warn
_REPO = Path(__file__).resolve().parent.parent


def _safe_path(path_str):
    p = Path(path_str).expanduser().resolve()
    return p


def _file_info(path_str):
    p = _safe_path(path_str)
    if not p.exists():
        return f"Archivo no encontrado: {p}"
    if not p.is_file():
        if p.is_dir():
            return f"Es un directorio: {p}. Usá code_search action=list."
        return f"No es un archivo: {p}"
    stat = p.stat()
    size = stat.st_size
    if size > 1024 * 1024:
        size_str = f"{size / (1024*1024):.1f} MB"
    elif size > 1024:
        size_str = f"{size / 1024:.1f} KB"
    else:
        size_str = f"{size} B"
    ext = p.suffix or "(sin ext)"
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = sum(1 for _ in f)
    except Exception:
        lines = "?"
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            first = f.read(200).replace("\r", "")
    except Exception:
        first = ""
    lang = _guess_lang(p)
    return (f"📄 {p.name}\n"
            f"   Ruta: {p}\n"
            f"   Tamaño: {size_str} | Líneas: {lines} | Extensión: {ext}\n"
            f"   Lenguaje estimado: {lang}\n"
            f"   Primeras líneas:\n{first[:150]}")


def _guess_lang(p):
    ext_map = {
        ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
        ".jsx": "React/JSX", ".tsx": "React/TSX",
        ".c": "C", ".cpp": "C++", ".h": "C/C++ Header",
        ".cs": "C#", ".java": "Java", ".kt": "Kotlin",
        ".rs": "Rust", ".go": "Go", ".rb": "Ruby", ".php": "PHP",
        ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
        ".json": "JSON", ".yaml": "YAML", ".yml": "YAML",
        ".toml": "TOML", ".sh": "Shell", ".sql": "SQL",
        ".md": "Markdown", ".gd": "GDScript",
        ".vue": "Vue", ".svelte": "Svelte",
    }
    return ext_map.get(p.suffix.lower(), p.suffix or "?")


def _read_file(path_str, offset=0, limit=_MAX_LINES):
    p = _safe_path(path_str)
    if not p.exists():
        return f"Archivo no encontrado: {p}"
    if not p.is_file():
        return f"No es un archivo: {p}"
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        start = max(0, int(offset))
        end = min(total, start + int(limit))
        chunk = lines[start:end]
        numbered = []
        for i, line in enumerate(chunk, start=start + 1):
            numbered.append(f"{i:>5}: {line.rstrip()}")
        out = "\n".join(numbered)
        if end < total:
            out += f"\n... (mostrando {start+1}-{end} de {total} líneas)"
        return out
    except Exception as e:
        return f"Error al leer: {e}"


def _read_segment(path_str, start_line, end_line):
    return _read_file(path_str, offset=start_line - 1,
                      limit=(end_line - start_line + 1))


def _warn_size(content, path_str):
    size = len(content.encode("utf-8"))
    if size > _MAX_WRITE_SIZE:
        return (f"⚠️ Archivo grande ({size / 1024:.0f} KB). "
                "Estás seguro de que querés sobreescribir este archivo?\n")
    return ""


def _write_file(path_str, content, dry_run=False):
    p = _safe_path(path_str)
    warn = _warn_size(content, path_str)
    if dry_run:
        if p.exists():
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    old = f.read()
            except Exception:
                old = ""
            return (f"🔍 DRY-RUN — No se aplicó nada.\n"
                    f"Vista previa del cambio en {p}:\n"
                    f"{'='*60}\n"
                    f"{content[:2000]}\n"
                    f"{'='*60}\n"
                    f"El archivo tiene {len(old)} caracteres actuales. "
                    f"El nuevo contenido tiene {len(content)} caracteres.")
        else:
            return (f"🔍 DRY-RUN — No se aplicó nada.\n"
                    f"Se crearía archivo nuevo: {p}\n"
                    f"Contenido ({len(content)} caracteres):\n{'='*60}\n"
                    f"{content[:2000]}\n{'='*60}")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return (f"{warn}✅ Archivo escrito: {p} "
                f"({len(content)} caracteres)")
    except Exception as e:
        return f"Error al escribir: {e}"


def _edit_file(path_str, old_text, new_text, dry_run=False):
    p = _safe_path(path_str)
    if not p.exists():
        return f"Archivo no encontrado: {p}"
    if not old_text:
        return "Necesito el texto a reemplazar (old_text)."
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return f"Error al leer: {e}"
    count = content.count(old_text)
    if count == 0:
        return (f"No encontré '{old_text[:80]}...' en {p.name}. "
                "Verificá el texto exacto.")
    if count > 1:
        return (f"Encontré {count} coincidencias de '{old_text[:60]}...'. "
                "Especificá más contexto para que sea único.")
    new_content = content.replace(old_text, new_text, 1)
    if dry_run:
        idx = content.index(old_text)
        ctx_before = content[max(0, idx-100):idx]
        ctx_after = content[idx+len(old_text):idx+len(old_text)+100]
        return (f"🔍 DRY-RUN — No se aplicó nada.\n"
                f"Cambio en {p.name}:\n"
                f"  Quitar:  ...{old_text[:200]}...\n"
                f"  Poner:   ...{new_text[:200]}...")
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(new_content)
        return f"✅ Editado: {p.name} (1 reemplazo)"
    except Exception as e:
        return f"Error al escribir: {e}"


def _append_file(path_str, content, dry_run=False):
    p = _safe_path(path_str)
    if dry_run:
        return (f"🔍 DRY-RUN — No se aplicó nada.\n"
                f"Se agregaría al final de {p}:\n{'='*60}\n"
                f"{content[:2000]}\n{'='*60}")
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return f"✅ Agregado al final de: {p}"
    except Exception as e:
        return f"Error al escribir: {e}"


def code_editor(parameters: dict, player=None) -> str:
    """Lee y modifica archivos de código fuente (Fase 2: con dry-run)."""
    action = str(parameters.get("action", "read")).lower().strip()
    path = str(parameters.get("path", "")).strip()
    dry_run = str(parameters.get("dry_run", "")).lower() in ("true", "1", "yes", "si")

    if not path and action not in ("write", "create"):
        return "Necesito la ruta del archivo (path)."

    if action in ("info", "metadata"):
        if player:
            player.write_log(f"📄 Info: {Path(path).name}")
        return _file_info(path)

    if action in ("read", "leer", "ver", "view"):
        offset = int(parameters.get("offset", 0) or 0)
        limit = int(parameters.get("limit", _MAX_LINES) or _MAX_LINES)
        if player:
            player.write_log(f"📄 Leyendo: {Path(path).name}")
        return _read_file(path, offset, limit)

    if action in ("segment", "lines", "rango"):
        start = int(parameters.get("start", 1) or 1)
        end = int(parameters.get("end", 100) or 100)
        if player:
            player.write_log(f"📄 Líneas {start}-{end}: {Path(path).name}")
        return _read_segment(path, start, end)

    # --- Escritura (Fase 2) ---
    content = str(parameters.get("content", ""))
    old_text = str(parameters.get("old_text", ""))
    new_text = str(parameters.get("new_text", ""))

    if action in ("write", "create", "guardar", "sobreescribir"):
        if not content:
            return "Necesito el contenido (content) para escribir."
        mode = "DRY-RUN" if dry_run else "ESCRITURA"
        if player:
            player.write_log(f"✏️ {mode}: {Path(path).name} ({len(content)} chars)")
        return _write_file(path, content, dry_run)

    if action in ("edit", "replace", "editar", "reemplazar"):
        if not old_text:
            return "Necesito el texto a buscar (old_text) y el reemplazo (new_text)."
        mode = "DRY-RUN" if dry_run else "EDICIÓN"
        if player:
            player.write_log(f"✏️ {mode}: {Path(path).name}")
        return _edit_file(path, old_text, new_text, dry_run)

    if action in ("append", "agregar", "añadir"):
        if not content:
            return "Necesito el contenido (content) para agregar."
        mode = "DRY-RUN" if dry_run else "ESCRITURA"
        if player:
            player.write_log(f"✏️ {mode} append: {Path(path).name}")
        return _append_file(path, content, dry_run)

    return ("Acciones: info, read/leer, segment/lines, "
            "write/create, edit/replace, append/agregar. "
            "Usá dry_run=true para ver los cambios antes de aplicar.")
