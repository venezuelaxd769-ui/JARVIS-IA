# -*- coding: utf-8 -*-
"""links.py — Marcadores favoritos por voz.

Guarda títulos con URL en memory/links.json y permite listarlos, abrirlos
o borrarlos. Si guardás sin URL, intenta leer el portapapeles.
"""
import ctypes
import json
import os
import webbrowser
from datetime import datetime

from ctypes import wintypes

_MEM = os.path.join(os.path.dirname(__file__), "..", "memory", "links.json")

_CF_UNICODETEXT = 13
_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")


def _leer():
    if not os.path.exists(_MEM):
        return {}
    try:
        with open(_MEM, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _escribir(d):
    os.makedirs(os.path.dirname(_MEM), exist_ok=True)
    tmp = _MEM + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _MEM)


def _portapapeles():
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.OpenClipboard(0):
            return None
        try:
            h = user32.GetClipboardData(_CF_UNICODETEXT)
            if not h:
                return None
            p = kernel32.GlobalLock(h)
            if not p:
                return None
            try:
                largo = kernel32.GlobalSize(h)
                if not largo:
                    return None
                buf = ctypes.create_string_buffer(largo)
                ctypes.memmove(buf, p, largo)
                txt = buf.raw.split(b"\x00\x00", 1)[0].decode("utf-16-le", "ignore")
                return txt.strip()
            finally:
                kernel32.GlobalUnlock(h)
        finally:
            user32.CloseClipboard()
    except Exception:
        return None


def _pare(link):
    if not link:
        return ""
    if "://" not in link:
        link = "https://" + link
    return link


def links(parameters: dict, player=None, speak=None) -> str:
    """Marcadores: guardar/listar/abrir/borrar enlaces favoritos."""
    action = str(parameters.get("action", "listar")).strip().lower()
    titulo = str(parameters.get("titulo", "") or parameters.get("nombre", "")).strip()
    url = str(parameters.get("url", "") or parameters.get("link", "")).strip()
    confirm = str(parameters.get("confirm", "")).strip().lower()

    if action in ("guardar", "guardar_link", "agregar"):
        if not titulo:
            return "Decime un título para el marcador, por ejemplo titulo='recetas', url='recetas.com'."
        if not url:
            url = _portapapeles() or ""
            if player and url:
                player.write_log(f"🔗 Link leído del portapapeles: {url}")
            if not url:
                return "Pasame la URL del link (o copialo antes en el portapapeles)."
        url = _pare(url)
        datos = _leer()
        datos[titulo.lower()] = {"url": url, "creado": datetime.now().isoformat(timespec="seconds")}
        _escribir(datos)
        if player:
            player.write_log(f"🔖 Marcador '{titulo}' → {url}")
        return f"Guardé el marcador {titulo}: {url}."

    if action in ("abrir", "open", "andá", "ve"):
        if not titulo:
            return "Decime qué marcador abrir, por ejemplo: 'abrí el link de recetas'."
        datos = _leer()
        clave = titulo.lower()
        if clave not in datos:
            disponible = ", ".join(sorted(datos)) if datos else "ninguno"
            return f"No tengo un marcador '{titulo}'. Yo tengo: {disponible}."
        url = datos[clave]["url"]
        try:
            webbrowser.open(url)
        except Exception as e:
            return f"No pude abrir el navegador: {e}."
        if player:
            player.write_log(f"🔗 Abriendo {titulo} → {url}")
        return f"Abierto: {titulo}."

    if action in ("borrar", "quitar"):
        if not titulo:
            return "Decime qué marcador borrar, por ejemplo borrar='recetas'."
        if confirm not in _CONFIRM:
            return f"Para borrar el marcador '{titulo}' confirmá con 'SÍ'."
        datos = _leer()
        clave = titulo.lower()
        if clave not in datos:
            return f"No tengo un marcador '{titulo}'."
        del datos[clave]
        _escribir(datos)
        if player:
            player.write_log(f"🗑️ Marcador '{titulo}' borrado.")
        return f"Listo, borré el marcador {titulo}."

    if action in ("test", "chequear"):
        return "Los marcadores funcionan: puedo guardar, listar, abrir y borrar links."

    # listar / qué tengo guardado
    datos = _leer()
    if not datos:
        return "No tenés marcadores guardados. Decime: 'guardá el link de <título>, <url>'."
    orden = sorted(datos)
    n = len(orden)
    if n <= 8:
        lineas = [f"{t} ({datos[t]['url']})" for t in orden]
        lista = ", ".join(lineas)
    else:
        lista = ", ".join(orden)
    if player:
        player.write_log(f"🔖 {n} marcadores: {lista}")
    return f"Tenés {n} marcadores: {lista}. Decime 'abrí el link de <título>' para abrir uno."