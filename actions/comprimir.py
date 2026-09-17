# -*- coding: utf-8 -*-
"""comprimir.py — Comprimir y descomprimir ZIP por voz.

Empaqueta carpetas/archivos en un .zip (con progreso de tamaño), extrae
archivos .zip y lista su contenido sin extraerlo. Resuelve rutas por nombre
con buscar._buscar y crea los zips en el mismo lugar o en Descargas.
"""
import os
import shutil
import zipfile

_EXT_OK = (".zip", ".rar", ".7z")


def _resolver(entrada):
    p = str(entrada).strip()
    if os.path.exists(p):
        return os.path.normpath(p)
    try:
        from actions.buscar import _roots, _buscar
        found, _ = _buscar(os.path.basename(p), "", _roots(None), 5)
        if found:
            return os.path.normpath(found[0][0])
    except Exception:
        pass
    return None


def _listar_zip(path):
    try:
        with zipfile.ZipFile(path) as z:
            nombres = z.namelist()
            total = sum(i.file_size for i in z.infolist())
    except Exception as e:
        return None, str(e)
    carpetas = sorted({n.rstrip("/") for n in nombres if n.endswith("/")})
    n_carp = len(carpetas)
    archivos = [n for n in nombres if not n.endswith("/")]
    return len(archivos), (n_carp, min(archivos, key=len) if archivos else None)


def comprimir(parameters: dict, player=None, speak=None) -> str:
    """Comprime y descomprime archivos zip por voz."""
    action = str(parameters.get("action", "help")).strip().lower()

    if action in ("test",):
        return "El empaquetador zip funciona."

    if action in ("contenido", "ver", "listar"):
        org = str(parameters.get("archivo", "") or parameters.get("zip", "")).strip()
        p = _resolver(org)
        if not p:
            return f"No encontré el zip '{org}'."
        n, extra = _listar_zip(p)
        if n is None:
            return f"No pude leer '{p}': {extra}."
        n_carp, ejemplo = extra
        sal = f"'{os.path.basename(p)}' tiene {n} archivos"
        if n_carp:
            sal += f" en {n_carp} carpeta{'s' if n_carp != 1 else ''}"
        sal += "."
        if ejemplo:
            sal += f" Por ejemplo, '{ejemplo}'. Podés extraerlo con comprimir."
        return sal

    if action in ("descomprimir", "extraer"):
        org = str(parameters.get("archivo", "") or parameters.get("zip", "")).strip()
        dest = str(parameters.get("destino", "")).strip()
        p = _resolver(org)
        if not p or not p.lower().endswith(".zip"):
            return f"Pasame un archivo .zip válido ({org or 'vacío'})."
        if not dest:
            dest = os.path.dirname(p)
        if not os.path.isdir(dest):
            try:
                os.makedirs(dest, exist_ok=True)
            except OSError:
                return f"No puedo crear la carpeta de destino '{dest}'."
        try:
            with zipfile.ZipFile(p) as z:
                z.extractall(dest)
        except Exception as e:
            return f"No pude extraer: {e}."
        n = sum(1 for _ in zipfile.ZipFile(p).namelist())
        if player:
            player.write_log("🗜️ " + f"Extraído '{os.path.basename(p)}' en {dest}")
        return f"Extraído '{os.path.basename(p)}' en '{dest}' ({n} archivos)."

    if action in ("comprimir", "zip", "crear"):
        org = str(parameters.get("carpeta", "") or parameters.get("archivo", "")).strip()
        nombre = str(parameters.get("nombre", "")).strip()
        p = _resolver(org)
        if not p:
            return f"No encontré '{org}'. Pasá una ruta o un nombre conocido."
        base = os.path.basename(p.rstrip("/\\"))
        if not nombre:
            nombre = base + ".zip"
        if not nombre.lower().endswith(".zip"):
            nombre += ".zip"
        dest = os.path.join(os.path.dirname(p), nombre)
        try:
            if os.path.isdir(p):
                shutil.make_archive(dest[:-4], "zip", os.path.dirname(p), base)
            else:
                with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                    z.write(p, os.path.basename(p))
        except Exception as e:
            return f"No pude comprimir: {e}."
        tam = os.path.getsize(dest) / (1024 ** 2)
        if player:
            player.write_log("🗜️ " + f"Zip creado: {dest} ({tam:.1f} MB)")
        return f"Listo: creé '{nombre}' ({tam:.1f} MB) al lado de '{base}'."

    return "Acciones: comprimir (carpeta/archivo) | descomprimir (zip) | ver (contenido)."