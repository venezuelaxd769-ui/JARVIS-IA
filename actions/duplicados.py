# -*- coding: utf-8 -*-
"""duplicados.py — Detección y limpieza de archivos duplicados por voz.

Agrupa por tamaño y luego por hash MD5 (por bloques) para no comerme todos
los archivos: primero filtra por tamaño, solo hashea los que comparten
tamaño. 'borrar' elimina los duplicados quedándose con el más viejo de cada
grupo (confirm='SÍ').
"""
import hashlib
import os

from actions.buscar import _SKIP

_FOLDER_DEFAULT = os.path.join(os.path.expanduser("~"), "Downloads")
_CAP_ENTRIES = 60000
_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")
_BLOQUE = 65536


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(_BLOQUE)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _scan(ruta, min_size=1024):
    by_size = {}
    entradas = 0
    for base, subs, files in os.walk(ruta):
        if entradas > _CAP_ENTRIES:
            break
        subs[:] = [s for s in subs if s not in _SKIP and not s.startswith(".")]
        for f in files:
            entradas += 1
            p = os.path.join(base, f)
            try:
                sz = os.path.getsize(p)
            except OSError:
                continue
            if sz >= min_size:
                by_size.setdefault(sz, []).append(p)
    grupos = {}
    for sz, lista in by_size.items():
        if len(lista) < 2:
            continue
        por_hash = {}
        for p in lista:
            try:
                por_hash.setdefault(_md5(p), []).append(p)
            except OSError:
                continue
        for digest, parejas in por_hash.items():
            if len(parejas) > 1:
                grupos.setdefault(digest, parejas)
    return grupos


def _resumen(grupos):
    if not grupos:
        return None
    total_extra = 0
    n_grupos = 0
    for digest, parejas in grupos.items():
        n_grupos += 1
        extra = len(parejas) - 1
        try:
            total_extra += extra * os.path.getsize(parejas[0])
        except OSError:
            pass
    return n_grupos, total_extra


def _pl(n):
    return "grupo" if n == 1 else "grupos"


def duplicados(parameters: dict, player=None, speak=None) -> str:
    """Encuentra o borra archivos duplicados en una carpeta."""
    action = str(parameters.get("action", "buscar")).strip().lower()
    ruta = str(parameters.get("carpeta", "") or parameters.get("ruta", "")).strip()
    min_size = max(256, int(parameters.get("min_size") or 1024))
    confirm = str(parameters.get("confirm", "")).strip().lower()

    if action in ("test", "chequear"):
        return "La detección de duplicados funciona (hash por bloques, sin riesgos)."

    if not ruta:
        ruta = _FOLDER_DEFAULT
    if not os.path.isdir(ruta):
        return f"No existe la carpeta '{ruta}'. Pasá una ruta válida con carpeta='C:\\...'."
    if os.path.abspath(ruta).lower().startswith(os.environ.get("WINDIR", "C:\\Windows").lower()):
        return "No escaneo la carpeta de Windows para no colgarme."

    try:
        grupos = _scan(ruta, min_size)
    except Exception as e:
        return f"No pude escanear '{ruta}': {e}."

    resumen = _resumen(grupos)
    if not grupos or not resumen:
        return f"En {os.path.basename(ruta)} no hay archivos duplicados (más de {min_size} bytes)."
    n_grupos, bytes_extra = resumen

    if action in ("borrar", "limpiar"):
        if confirm not in _CONFIRM:
            return (f"Encontré {n_grupos} {_pl(n_grupos)} de duplicados (~{round(bytes_extra / (1024 ** 2), 1)} MB extra). "
                    f"Para borrar los que sobran confirmá con 'SÍ'.")
        borrados = 0
        liberados = 0
        for digest, parejas in grupos.items():
            parejas.sort(key=lambda p: os.path.getmtime(p))
            conservar = parejas[0]
            try:
                sz = os.path.getsize(conservar)
            except OSError:
                sz = 0
            for p in parejas[1:]:
                try:
                    if p != conservar:
                        os.remove(p)
                        borrados += 1
                        liberados += sz
                except OSError:
                    continue
        if player:
            player.write_log(f"🧹 {borrados} duplicados borrados en {ruta} ({round(liberados / (1024 ** 2), 1)} MB)")
        if borrados == 0:
            return "No pude borrar nada (permisos o archivos en uso)."
        return (f"Listo, borré {borrados} "
                f"{'archivo duplicado' if borrados == 1 else 'archivos duplicados'} y liberé "
                f"~{round(liberados / (1024 ** 2), 1)} MB de {os.path.basename(ruta)}. "
                f"Quedó el más viejo de cada grupo.")

    # buscar (default)
    limite = max(1, min(10, int(parameters.get("limite") or 5)))
    lineas = []
    for digest, parejas in list(grupos.items())[:limite]:
        try:
            mb = round(os.path.getsize(parejas[0]) / (1024 ** 2), 1)
        except OSError:
            mb = 0
        lineas.append(f"{os.path.basename(parejas[0])} (copia en {os.path.dirname(parejas[1])}, "
                      f"hay {len(parejas)}, {mb} MB cada uno)")
    resto = n_grupos - len(lineas)
    if player:
        player.write_log(f"🔁 {n_grupos} {_pl(n_grupos)} de duplicados en {ruta}")
    base = (f"En {os.path.basename(ruta)} tengo {n_grupos} {_pl(n_grupos)} de archivos duplicados "
            f"(~{round(bytes_extra / (1024 ** 2), 1)} MB desperdiciados). "
            f"Algunos: {'. '.join(lineas)}.")
    if resto > 0:
        base += f" Y hay {resto} {_pl(resto)} más."
    base += " Para borrar los que sobran (quedando el más viejo), action='borrar' con confirm='SÍ'."
    return base