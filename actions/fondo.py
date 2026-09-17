# -*- coding: utf-8 -*-
"""fondo.py — Fondo de pantalla por voz (Windows).

Cambia el wallpaper con SystemParametersInfoW (SPI_SETDESKWALLPAPER),
guarda el actual antes de cambiar y permite volver atrás / aleatorio.
Requiere que la imagen quede como camino absoluto (SPI_SETDESKWALLPAPER
no expande variables de entorno).
"""
import json
import os
import random

import ctypes
from ctypes import wintypes

_MEM = os.path.join(os.path.dirname(__file__), "..", "memory", "fondo_estado.json")

SPI_GETDESKWALLPAPER = 0x0073
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x0001
SPIF_SENDCHANGE = 0x0002

_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")


def _estado():
    if not os.path.exists(_MEM):
        return {"actual": None, "anterior": None}
    try:
        with open(_MEM, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _guardar_estado(d):
    os.makedirs(os.path.dirname(_MEM), exist_ok=True)
    tmp = _MEM + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _MEM)


def _actual():
    try:
        buf = ctypes.create_unicode_buffer(520)
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETDESKWALLPAPER, len(buf), buf, 0)
        if not ok or not buf.value:
            return None
        return os.path.abspath(buf.value)
    except Exception:
        return None


def _pon(wall):
    wall = os.path.abspath(wall)
    if not os.path.exists(wall):
        return False
    act = _actual()
    d = _estado()
    if act and act != wall:
        d["anterior"] = act
    d["actual"] = wall
    ok = ctypes.windll.user32.SystemParametersInfoW(
        SPI_SETDESKWALLPAPER, 0, wall, SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
    _guardar_estado(d)
    return bool(ok)


def _imagenes_de(carpeta):
    found = []
    for base, subs, files in os.walk(carpeta):
        subs[:] = [s for s in subs if not s.startswith("._")]
        for f in files:
            if f.lower().endswith(_EXT):
                found.append(os.path.join(base, f))
    return found


def _clave(val):
    v = str(val or "").strip()
    return v.lower()


def fondo(parameters: dict, player=None, speak=None) -> str:
    """Controla el fondo de pantalla: poner, aleatorio, restaurar, estado."""
    action = _clave(parameters.get("action", "estado"))
    ruta = str(parameters.get("ruta", "") or parameters.get("imagen", "")).strip()
    carpeta = str(parameters.get("carpeta", "")).strip()

    if action in ("estado", "actual"):
        act = _actual()
        if not act:
            return "No pude leer el fondo de pantalla actual."
        return f"Tu fondo actual es {os.path.basename(act)}. Para cambiarlo decime 'cambiá el fondo a <nombre de imagen>'."

    if action in ("restaurar", "deshacer", "volver"):
        d = _estado()
        prev = (d or {}).get("anterior")
        if prev and os.path.exists(prev):
            if _pon(prev):
                if player:
                    player.write_log(f"🖼️ Fondo restaurado: {os.path.basename(prev)}")
                return f"Listo, volví al fondo anterior: {os.path.basename(prev)}."
            return "No pude restaurar el fondo anterior."
        return "No tengo un fondo anterior para restaurar. Cambialo con 'cambiá el fondo a <imagen>'."

    if action in ("aleatorio", "random", "sorpresa"):
        if carpeta and os.path.isdir(carpeta):
            base = carpeta
        else:
            home = os.path.expanduser("~")
            candidatos = [os.path.join(home, "Pictures", "Wallpapers"),
                          os.path.join(home, "Pictures"),
                          os.path.join(home, "NiaSandbox", "fondos")]
            base = next((c for c in candidatos if os.path.isdir(c)), None)
        if not base:
            return "No encontré carpetas de fondos. Pasa carpetas como carpeta o creá ~/Pictures/Wallpapers."
        imgs = _imagenes_de(base)
        if not imgs:
            return f"No hay imágenes en {base}."
        act = _actual()
        opciones = [i for i in imgs if i != act] or imgs
        elegida = random.choice(opciones)
        if player:
            player.write_log(f"🖼️ Fondo aleatorio de {base}")
        return _resp(elegida)

    if action in ("poner", "fijar", "cambiar", "establecer"):
        if not ruta:
            return "Decime qué imagen usar, por ejemplo ruta='C:\\...\\fondo.jpg' o el nombre del archivo."
        wall = ruta
        if not os.path.exists(wall):
            try:
                from actions.buscar import _roots, _buscar
                found, _ = _buscar(os.path.basename(ruta), "", _roots(None), 3)
                if not found:
                    return f"No encontré la imagen '{ruta}'. Especificá la ruta completa o un nombre que exista."
                wall = found[0][0]
            except Exception:
                return f"No encontré la imagen '{ruta}'."
        if not wall.lower().endswith(_EXT):
            return f"'{wall}' no parece una imagen ({', '.join(_EXT)})."
        return _resp(wall)

    return "Acciones: poner | aleatorio | restaurar | estado."


def _resp(wall):
    if _pon(wall):
        return f"Listo, fondo cambiado a {os.path.basename(wall)}."
    return f"No pude cambiar el fondo a {wall}."