# -*- coding: utf-8 -*-
"""ocr.py — Extrae texto de imágenes y PDFs escaneados (Windows OCR).

Usa el OCR nativo de Windows (Windows.Media.Ocr vía winrt, sin instalar
binarios). Solo Windows; en otros SO devuelve un mensaje claro.
sí: lee capturar_*.png, fotos y cualquier imagen. Si es PDF se rasteriza
cada página a PNG (PyMuPDF si está instalado, sino pypdf no alcanza) y se
OCR-ea.
"""
import asyncio
import os
import re
import sys

try:
    import winrt.windows.media.ocr as _wocr
    import winrt.windows.graphics.imaging as imaging
    import winrt.windows.storage as storage
    import winrt.windows.globalization as globalization
    import winrt.windows.storage.streams as streams
    HAS_WINRT = True
except Exception:
    HAS_WINRT = False


def _async(coro):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    except Exception as e:
        return ("", f"OCR falló: {e}")


async def _ocr_imagen(path):
    archivo = await storage.StorageFile.get_file_from_path_async(path)
    flujo = await archivo.open_async(storage.FileAccessMode.READ)
    decodificador = await imaging.BitmapDecoder.create_async(flujo)
    bitmap = await decodificador.get_software_bitmap_async()
    try:
        si_es = [l.language_tag for l in _wocr.OcrEngine.available_recognizer_languages]
    except Exception:
        si_es = []
    lenguaje = _wocr.OcrEngine.try_create_from_user_profile_languages()
    if not lenguaje:
        lenguaje = _wocr.OcrEngine.try_create_from_language(globalization.Language("es-ES"))
    if not lenguaje:
        lenguaje = _wocr.OcrEngine.try_create_from_language(globalization.Language("en-US"))
    if not lenguaje:
        return None, "El OCR de Windows no tiene idiomas disponibles."
    resultado = await lenguaje.recognize_async(bitmap)
    texto = "\n".join(line.text for line in resultado.lines)
    return texto, " | ".join(si_es) if si_es else ""


def _tamaño(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return im.width, im.height
    except Exception:
        return None


def _renderizar_pdf(pdf, pagina):
    """Devuelve bytes de PNG de la página si hay PyMuPDF."""
    try:
        import fitz
    except Exception:
        return None
    doc = fitz.open(pdf)
    if pagina < 0 or pagina >= doc.page_count:
        return None, None
    pix = doc[pagina].get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    return pix.tobytes("png"), doc.page_count


def _ocr_bytes(png_bytes):
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        with open(tmp, "wb") as f:
            f.write(png_bytes)
        return _ocr_imagen(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def ocr(parameters: dict, player=None, speak=None) -> str:
    """Extrae texto de imágenes y PDFs escaneados por voz."""
    action = str(parameters.get("action", "leer")).strip().lower()

    if action in ("test",):
        if not HAS_WINRT:
            return "OCR no disponible: faltan los paquetes winrt (Windows)."
        return "El OCR de Windows está instalado y funcional."

    if not HAS_WINRT:
        return "El OCR nativo solo corre en Windows, y faltan los paquetes winrt acá."

    archivo = str(parameters.get("archivo", "") or parameters.get("imagen", "")).strip()
    if not archivo:
        return "Decime qué imagen o PDF escanear, por ejemplo archivo='captura_20260914.png'."

    path = archivo
    if not os.path.exists(path):
        try:
            from actions.buscar import _roots, _buscar
            found, _ = _buscar(os.path.basename(path), "", _roots(None), 5)
            if not found:
                return f"No encontré '{archivo}'. Pasá una ruta o nombre."
            path = found[0][0]
        except Exception:
            return f"No encontré '{archivo}'."

    ext = path.lower().rsplit(".", 1)[-1]
    if ext in ("pdf",):
        pagina = 0
        try:
            pagina = int(parameters.get("pagina", 1)) - 1
        except ValueError:
            pagina = 0
        try:
            import fitz
        except Exception:
            return ("No tengo la librería para rasterizar PDFs (pymupdf). "
                    "Las imágenes sí funcionan: probá con un png o jpg.")
        png, total = _renderizar_pdf(path, pagina)
        if png is None:
            return f"No pude renderizar la página {pagina + 1} del PDF."
        texto, langs = _async(_ocr_bytes(png))
        if not texto or not texto.strip():
            return f"No capté texto en la página {pagina + 1} del PDF (¿será una imagen sin texto?)."
        if player:
            player.write_log("🔤 " + f"OCR PDF pág {pagina + 1} de {total}: " + texto.strip()[:160])
        return f"Texto de la página {pagina + 1} (de {total}): " + texto.strip()

    if ext not in ("png", "jpg", "jpeg", "bmp", "webp", "tiff", "gif"):
        return f"No soporto '{ext}'. Uso imágenes (png, jpg) o PDFs."

    texto, langs = _async(_ocr_imagen(path))
    if not texto and str(langs).startswith("OCR falló"):
        return langs
    if not texto or not texto.strip():
        return "No capté texto en esa imagen (¿está muy oscura o es puramente gráfica?)."
    if player:
        player.write_log("🔤 " + f"OCR de {os.path.basename(path)}: " + texto.strip()[:200])
    return f"El texto que veo dice: {texto.strip()}"