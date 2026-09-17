# -*- coding: utf-8 -*-
"""buscar.py — Búsqueda local de archivos por voz.

Encuentra archivos por nombre en las carpetas del usuario sin salir de Nia.
Evita AppData/venv/node_modules/etc. para no colgarse.
"""
import fnmatch
import os

_SKIP = {".venv", "venv", "node_modules", ".git", "__pycache__", ".cache",
         "AppData", "Site-packages", "site-packages", "Program Files",
         "Program Files (x86)", "Windows", "$RECYCLE.BIN", "System Volume Information",
         "Application Data", "Local Settings", ".thumbnails"}


def _roots(extra):
    home = os.path.expanduser("~")
    base = [os.path.join(home, "Desktop"), os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"), os.path.join(home, "Music"),
            os.path.join(home, "Pictures"), os.path.join(home, "Videos")]
    if extra and os.path.isdir(extra):
        base.append(extra)
    limpio = []
    for r in base:
        r = os.path.abspath(r)
        if r not in limpio:
            limpio.append(r)
    return limpio


def _buscar(query, tipo, carpetas, limite):
    q = query.lower().strip()
    found = []
    entries = 0
    for root in carpetas:
        if not os.path.isdir(root):
            continue
        for base, subs, files in os.walk(root):
            entries += 1
            if entries > 200000:
                subs[:] = []
            subs[:] = [s for s in subs if s not in _SKIP and not s.startswith("._")]
            for f in files:
                try:
                    if q in f.lower() or (tipo and f.lower().endswith(tipo.lower())):
                        p = os.path.join(base, f)
                        try:
                            sz = os.path.getsize(p)
                        except OSError:
                            sz = 0
                        found.append((p, sz))
                        if len(found) >= limite:
                            return found, entries
                except OSError:
                    continue
            if len(found) >= limite:
                return found, entries
    return found, entries


def buscar(parameters: dict, player=None, speak=None) -> str:
    """Búsqueda local de archivos por nombre en tus carpetas."""
    query = str(parameters.get("query", "") or parameters.get("archivo", "")).strip()
    tipo = str(parameters.get("tipo", "") or parameters.get("extension", "")).strip()
    ruta = str(parameters.get("ruta", "") or parameters.get("carpeta", "")).strip()
    limite = max(1, min(20, int(parameters.get("limite") or 10)))
    if player:
        player.write_log(f"🔍 buscar: {query}")

    if not query and not tipo:
        return ("Decime qué archivo buscar (query). Ej: 'buscá el archivo de CV', "
                "'buscá todos los PDFs' (con tipo='pdf'). Filtro opcional: ruta, limite.")

    carpetas = _roots(ruta)
    found, entries = _buscar(query, tipo, carpetas, limite)
    if not found:
        escaneadas = ", ".join(os.path.basename(c) or c for c in carpetas)
        return f"No encontré nada con eso en {escaneadas}."
    lineas = [f"🔎 Encontré {len(found)} archivo{'s' if len(found) > 1 else ''}:"]
    for p, sz in found:
        try:
            tamaño = f"{sz/1024/1024:.1f} MB" if sz > 1024 * 1024 else f"{sz/1024:.0f} KB"
        except Exception:
            tamaño = "?"
        lineas.append(f"   • {p}  ({tamaño})")
    if entries > 200000:
        lineas.append("   ⚠️ Corte por límite de búsqueda.")
    if len(found) >= limite:
        lineas.append(f"   (mostrando los primeros {limite}, hay más)")
    return "\n".join(lineas)