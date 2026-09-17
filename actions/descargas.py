# -*- coding: utf-8 -*-
"""descargas.py — Organizar la carpeta de Descargas por voz (Windows).

Rebusca el vaivén de archivos en Downloads y los agrupa por tipo en
subcarpetas (Documentos, Imágenes, Videos, Música, Instaladores, Varios).
Guarda el mapa para poder deshacer el movimiento.
"""
import json
import os
import shutil

_UNDO_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "descargas_undo.json")

_TIPOS = {
    "documentos": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
                   ".txt", ".csv", ".md", ".rtf", ".odt", ".epub", ".tex"],
    "imagenes": [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg",
                 ".heic", ".avif", ".tiff"],
    "videos": [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm", ".flv"],
    "musica": [".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"],
    "instaladores": [".exe", ".msi", ".apk", ".zip", ".rar", ".7z", ".tar",
                     ".gz", ".iso"],
    "varios": [],
}

_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")


def _ruta_descargas():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else None


def _clasificar(nombre):
    ext = os.path.splitext(nombre)[1].lower()
    for cat, exts in _TIPOS.items():
        if ext in exts:
            return cat
    return "varios"


def _contenidos(carpeta):
    if not carpeta:
        return []
    return [os.path.join(carpeta, f) for f in os.listdir(carpeta)
            if os.path.isfile(os.path.join(carpeta, f))]


def _plan(carpeta):
    if not carpeta:
        return [], "No encuentro tu carpeta de Descargas."
    plan = []
    for p in _contenidos(carpeta):
        cat = _clasificar(os.path.basename(p))
        plan.append((p, cat))
    return plan, None


def descargas(parameters: dict, player=None, speak=None) -> str:
    """Organiza la carpeta de Descargas por tipo y puede deshacerlo."""
    action = str(parameters.get("action", "ver")).strip().lower()
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in _CONFIRM
    carpeta = _ruta_descargas()
    if player:
        player.write_log(f"📂 descargas: {action}")

    if action in ("ver", "preview", "plan"):
        plan, err = _plan(carpeta)
        if err:
            return err
        if not plan:
            return "Tu carpeta de Descargas está vacía (o solo hay carpetas)."
        por_cat = {}
        for p, cat in plan:
            por_cat.setdefault(cat, 0)
            por_cat[cat] += 1
        lineas = [f"📂 Descargas: {len(plan)} archivos por acomodar."]
        for cat, n in sorted(por_cat.items(), key=lambda x: -x[1]):
            etiqueta = {"instaladores": "⬇️ instaladores", "varios": "🗃️ varios"}.get(cat, cat)
            lineas.append(f"   • {etiqueta}: {n}")
        lineas.append("Confirmá con 'SÍ' y los muevo.")
        return "\n".join(lineas)

    if action in ("organizar", "mover", "acomodar", "organize"):
        plan, err = _plan(carpeta)
        if err:
            return err
        if not plan:
            return "No hay nada que organizar: Descargas está vacía."
        if not ok:
            return ("Voy a MOVER %d archivos de Descargas a subcarpetas "
                    "(Documentos, Imágenes, Videos, Música, Instaladores, Varios). "
                    "Confirmá con 'SÍ'." % len(plan))
        mapa = {}
        movidos = error = 0
        for origen, cat in plan:
            destino_dir = os.path.join(carpeta, cat)
            os.makedirs(destino_dir, exist_ok=True)
            base = os.path.basename(origen)
            destino = os.path.join(destino_dir, base)
            n = 1
            while os.path.exists(destino):
                nombre, ext = os.path.splitext(base)
                destino = os.path.join(destino_dir, f"{nombre} ({n}){ext}")
                n += 1
            try:
                shutil.move(origen, destino)
                mapa[destino] = origen
                movidos += 1
            except OSError:
                error += 1
        try:
            with open(_UNDO_FILE, "w", encoding="utf-8") as f:
                json.dump(mapa, f, ensure_ascii=False)
        except OSError:
            pass
        resumen = f"Moví {movidos} archivos"
        if error:
            resumen += f" (fallaron {error} que estaban bloqueados)"
        return (f"{resumen}. Quedaron separados por tipo. "
                "Decime 'deshacé las descargas' si querés volverlos atrás.")

    if action in ("deshacer", "undo", "revertir"):
        try:
            with open(_UNDO_FILE, encoding="utf-8") as f:
                mapa = json.load(f)
        except Exception:
            return "No hay movimientos que deshacer."
        if not ok:
            return f"Voy a DEVOLVER {len(mapa)} archivos a sus lugares originales. Confirmá con 'SÍ'."
        devueltos = error = 0
        for destino, origen in mapa.items():
            try:
                if os.path.exists(destino):
                    os.makedirs(os.path.dirname(origen), exist_ok=True)
                    shutil.move(destino, origen)
                    devueltos += 1
            except OSError:
                error += 1
        try:
            os.remove(_UNDO_FILE)
        except OSError:
            pass
        return (f"Devolví {devueltos} archivos a su lugar original." +
                (f" ({error} no pudieron)" if error else ""))

    return ("Acciones: ver | organizar (SÍ) | deshacer (SÍ).")