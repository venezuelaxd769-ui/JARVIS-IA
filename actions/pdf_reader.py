"""pdf_reader.py — Lee y extrae contenido de archivos PDF.

Usa PyPDF2 si está disponible, fallback a pdftotext (poppler-utils),
y último recurso: apertura con app del sistema. Extrae texto, metadata,
número de páginas, y puede leer páginas específicas.
"""
import os
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

_BACKEND = None


def _detect_backend():
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    try:
        import PyPDF2
        _BACKEND = "pypdf2"
        return _BACKEND
    except ImportError:
        pass
    try:
        import pdfplumber
        _BACKEND = "pdfplumber"
        return _BACKEND
    except ImportError:
        pass
    try:
        result = subprocess.run(["pdftotext", "-v"], capture_output=True, timeout=5)
        if result.returncode == 0 or b"pdftotext" in result.stderr:
            _BACKEND = "pdftotext"
            return _BACKEND
    except Exception:
        pass
    _BACKEND = "none"
    return _BACKEND


def _read_pypdf2(path, first_page=None, last_page=None):
    import PyPDF2
    info = {}
    text_parts = []
    with open(path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        info["pages"] = len(reader.pages)
        meta = reader.metadata
        if meta:
            info["title"] = str(meta.get("/Title", ""))
            info["author"] = str(meta.get("/Author", ""))
        start = (first_page or 1) - 1
        end = last_page or len(reader.pages)
        end = min(end, len(reader.pages))
        for i in range(start, end):
            page = reader.pages[i]
            t = page.extract_text() or ""
            text_parts.append(f"--- Página {i+1} ---\n{t}")
    return info, "\n\n".join(text_parts)


def _read_pdfplumber(path, first_page=None, last_page=None):
    import pdfplumber
    info = {}
    text_parts = []
    with pdfplumber.open(path) as pdf:
        info["pages"] = len(pdf.pages)
        meta = pdf.metadata or {}
        info["title"] = str(meta.get("Title", ""))
        info["author"] = str(meta.get("Author", ""))
        start = (first_page or 1) - 1
        end = last_page or len(pdf.pages)
        end = min(end, len(pdf.pages))
        for i in range(start, end):
            page = pdf.pages[i]
            t = page.extract_text() or ""
            text_parts.append(f"--- Página {i+1} ---\n{t}")
    return info, "\n\n".join(text_parts)


def _read_pdftotext(path, first_page=None, last_page=None):
    info = {"pages": "?"}
    args = ["pdftotext", "-layout"]
    if first_page:
        args += ["-f", str(first_page)]
    if last_page:
        args += ["-l", str(last_page)]
    args += [path, "-"]
    result = subprocess.run(args, capture_output=True, timeout=30, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:500])
    return info, result.stdout.strip()


def pdf_reader(parameters: dict, player=None) -> str:
    """Lee un archivo PDF: texto, metadata y páginas específicas."""
    path = str(parameters.get("path", "")).strip()
    first_page = parameters.get("first_page")
    last_page = parameters.get("last_page")
    max_chars = int(parameters.get("max_chars", 20000))

    if not path:
        return "Necesito la ruta del PDF."

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Archivo no encontrado: {path}"

    if player:
        player.write_log(f"📄 Leyendo PDF: {os.path.basename(path)}...")

    backend = _detect_backend()
    if backend == "none":
        try:
            os.startfile(path)
            return f"PDF abierto en app del sistema: {path}"
        except Exception:
            return ("No hay backend de lectura PDF disponible. "
                    "Instalá PyPDF2: pip install PyPDF2")

    try:
        if backend == "pypdf2":
            info, text = _read_pypdf2(path, first_page, last_page)
        elif backend == "pdfplumber":
            info, text = _read_pdfplumber(path, first_page, last_page)
        else:
            info, text = _read_pdftotext(path, first_page, last_page)
    except Exception as e:
        return f"Error leyendo PDF: {e}"

    size = os.path.getsize(path)
    header_parts = [f"📄 {os.path.basename(path)}"]
    if info.get("title"):
        header_parts.append(f"   Título: {info['title']}")
    if info.get("author"):
        header_parts.append(f"   Autor: {info['author']}")
    header_parts.append(f"   Páginas: {info.get('pages', '?')}")
    header_parts.append(f"   Tamaño: {size:,} bytes")
    header_parts.append(f"   Backend: {backend}")

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... (truncado, total {len(text)} chars)"

    return "\n".join(header_parts) + "\n\n" + text
