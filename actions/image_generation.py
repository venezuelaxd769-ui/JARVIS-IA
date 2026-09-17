# -*- coding: utf-8 -*-
"""image_generation.py — Generación de imágenes con IA.

Backend: Pollinations.ai (gratis, open-source, sin API key) — rápido y sin
setup. Si en el futuro los endpoints de imagen de NVIDIA NIM vuelven a estar
disponibles (hoy devuelven 404/timeout), se puede volver a NIM en _generate()
sin tocar el resto del módulo.
"""
import os
import random
import time
import urllib.parse
from pathlib import Path

TIME_FMT = "%Y%m%d_%H%M%S"

# relación de aspecto → tamaño solicitado a Pollinations
_RATIO_SIZES = {
    "1:1": (1024, 1024),
    "4:3": (1280, 960),
    "3:4": (960, 1280),
    "16:9": (1344, 768),
    "9:16": (768, 1344),
}


def _url_for(prompt: str, width: int, height: int, seed: int) -> str:
    from urllib.parse import quote
    p = quote(prompt)
    seed = max(0, int(seed) & 0xFFFFFFFF)
    return (
        f"https://image.pollinations.ai/prompt/{p}"
        f"?width={width}&height={height}&seed={seed}&nologo=true&model=flux"
    )


def _open_file(path: Path):
    if os.name == "nt":
        os.startfile(str(path))
    else:
        import subprocess
        subprocess.Popen(["xdg-open", str(path)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _download(url: str, timeout: int = 180) -> bytes:
    import httpx
    with httpx.Client(timeout=timeout, follow_redirects=True) as http:
        resp = http.get(url)
        resp.raise_for_status()
        return resp.content


def image_generation(parameters: dict, player=None) -> str:
    prompt = str(parameters.get("prompt") or "").strip()
    if not prompt:
        return "Faltó el 'prompt'. Pedile al usuario una descripción de la imagen."

    count = int(parameters.get("count", 1) or 1)
    count = max(1, min(count, 4))
    ratio = str(parameters.get("aspect_ratio", "1:1") or "1:1").strip().lower()
    width, height = _RATIO_SIZES.get(ratio, (1024, 1024))
    save_dir = str(parameters.get("save_path") or "").strip()
    if not save_dir:
        save_dir = str(Path.home() / "Pictures" / "Nia_Generadas")
    out_dir = Path(save_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        out_dir = Path.home() / "Pictures" / "Nia_Generadas"
        out_dir.mkdir(parents=True, exist_ok=True)

    base_seed = random.randint(0, 2 ** 31)
    stamp = time.strftime(TIME_FMT)
    saved = []
    for i in range(count):
        url = _url_for(prompt, width, height, base_seed + i)
        try:
            raw = _download(url)
        except Exception as e:
            if not saved:
                return f"⚠️ No pude generar la imagen: {e}"
            break
        if not raw or len(raw) < 100:
            continue
        suffix = f"_{i + 1}" if count > 1 else ""
        path = out_dir / f"Nia_{stamp}{suffix}.png"
        path.write_bytes(raw)
        saved.append(path)

    if not saved:
        return "⚠️ La generación no devolvió una imagen válida."

    first = saved[0]
    try:
        from file_events import emit_image
        emit_image(str(first), None)
    except Exception:
        pass
    if player:
        try:
            player.write_log(f"🖼️ Imagen generada: {first}")
        except Exception:
            pass

    if count > 1 and len(saved) > 1:
        _open_file(out_dir)
        return (f"Generé {len(saved)} imágenes en: {out_dir}. "
                f"Las abrí y quedaron guardadas ahí.")
    _open_file(first)
    return f"Imagen lista: {first}"