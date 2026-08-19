"""image_reader.py — Lee y analiza archivos de imagen.

Obtiene metadata (dimensiones, formato, tamaño), puede redimensionar,
y genera base64 para envío a APIs de visión (Gemini, OpenRouter).
Sin dependencias PIL — usa estructura PNG/JPEG nativa o fallback a file.
"""
import base64
import os
import struct
from pathlib import Path


def _png_info(data):
    """Lee dimensiones de PNG desde los primeros bytes."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    try:
        w = struct.unpack(">I", data[16:20])[0]
        h = struct.unpack(">I", data[20:24])[0]
        bit_depth = data[24]
        color_type = data[25]
        ct_names = {0: "Grayscale", 2: "RGB", 3: "Indexed",
                    4: "Grayscale+Alpha", 6: "RGBA"}
        return {"width": w, "height": h, "bit_depth": bit_depth,
                "color": ct_names.get(color_type, f"Tipo {color_type}")}
    except Exception:
        return None


def _jpeg_info(data):
    """Lee dimensiones de JPEG desde los primeros bytes."""
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    try:
        while i < len(data) - 1:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2):
                h = struct.unpack(">H", data[i + 5:i + 7])[0]
                w = struct.unpack(">H", data[i + 7:i + 9])[0]
                return {"width": w, "height": h, "color": "JPEG"}
            if marker == 0xD9:
                break
            if marker == 0xDA:
                break
            if 0xE0 <= marker <= 0xFE:
                seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
                i += 2 + seg_len
            else:
                i += 2
    except Exception:
        pass
    return None


def _gif_info(data):
    if data[:6] not in (b"GIF87a", b"GIF89a"):
        return None
    try:
        w = struct.unpack("<H", data[6:8])[0]
        h = struct.unpack("<H", data[8:10])[0]
        return {"width": w, "height": h, "color": "GIF"}
    except Exception:
        return None


def _webp_info(data):
    if data[8:12] != b"WEBP":
        return None
    try:
        if data[12:16] == b"VP8 ":
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return {"width": w, "height": h, "color": "WebP/VP8"}
        elif data[12:16] == b"VP8L":
            bits = struct.unpack("<I", data[21:25])[0]
            w = (bits & 0x3FFF) + 1
            h = ((bits >> 14) & 0x3FFF) + 1
            return {"width": w, "height": h, "color": "WebP/VP8L"}
    except Exception:
        pass
    return None


_DETECTORS = [
    (b"\x89PNG", _png_info),
    (b"\xff\xd8\xff", _jpeg_info),
    (b"GIF8", _gif_info),
    (b"\x00\x00\x00\x00RIFF", _webp_info),
]


def image_reader(parameters: dict, player=None) -> str:
    """Lee metadata de una imagen: dimensiones, formato, tamaño, base64."""
    path = str(parameters.get("path", "")).strip()
    max_b64_chars = int(parameters.get("max_b64_chars", 2000))
    return_b64 = str(parameters.get("return_b64", "")).lower() == "true"

    if not path:
        return "Necesito la ruta de la imagen."

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Archivo no encontrado: {path}"

    if player:
        player.write_log(f"🖼️ Analizando imagen: {os.path.basename(path)}...")

    size = os.path.getsize(path)
    if size > 50_000_000:
        return f"Imagen demasiado grande: {size:,} bytes (máx 50 MB)."

    try:
        with open(path, "rb") as f:
            header = f.read(32)
    except Exception as e:
        return f"Error leyendo archivo: {e}"

    # Detectar formato
    info = {"format": os.path.splitext(path)[1].upper().lstrip("."), "size_bytes": size}
    for sig, detector in _DETECTORS:
        if header[:len(sig)] == sig:
            detected = detector(header)
            if detected:
                info.update(detected)
            break

    if "width" not in info:
        info["format"] = info.get("format", "DESCONOCIDO")

    # Backends disponibles
    backends = []
    try:
        from PIL import Image
        backends.append("Pillow")
    except ImportError:
        pass
    if os.path.exists("/usr/bin/identify"):
        backends.append("ImageMagick")

    lines = [f"🖼️ {os.path.basename(path)}"]
    lines.append(f"   Formato: {info.get('format', '?')}")
    if "width" in info:
        lines.append(f"   Dimensiones: {info['width']}×{info['height']} px")
    if "color" in info:
        lines.append(f"   Color: {info['color']}")
    lines.append(f"   Tamaño: {size:,} bytes")
    if backends:
        lines.append(f"   Backends disponibles: {', '.join(backends)}")

    # Base64 para envío a APIs de visión
    if return_b64:
        try:
            with open(path, "rb") as f:
                raw = f.read()
            b64 = base64.b64encode(raw).decode()
            lines.append(f"\n   Base64 ({len(b64):,} caracteres)")
            if len(b64) > max_b64_chars:
                lines.append(f"   Preview: {b64[:max_b64_chars]}...")
            else:
                lines.append(f"   Completo: {b64}")
        except Exception as e:
            lines.append(f"\n   Error generando base64: {e}")

    # Intentar leer con Pillow si está disponible
    try:
        from PIL import Image
        with Image.open(path) as img:
            lines.append(f"\n   Pillow info:")
            lines.append(f"     Modo: {img.mode}")
            lines.append(f"     Paleta: {'Sí' if img.palette else 'No'}")
            if hasattr(img, "n_frames"):
                lines.append(f"     Frames: {img.n_frames}")
    except ImportError:
        pass
    except Exception:
        pass

    return "\n".join(lines)
