# -*- coding: utf-8 -*-
"""preferencias.py — Memoria de gustos y preferencias por voz.

Guarda pares clave-valor ("prefiero café sin azúcar") en memory/prefs.json
para que Nia los tenga en cuenta en el futuro.
"""
import json
import os

_MEM = os.path.join(os.path.dirname(__file__), "..", "memory", "prefs.json")

_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")


def _leer():
    if not os.path.exists(_MEM):
        return {}
    try:
        with open(_MEM, "r", encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except Exception:
        return {}


def _escribir(datos):
    os.makedirs(os.path.dirname(_MEM), exist_ok=True)
    tmp = _MEM + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _MEM)


def preferencias(parameters: dict, player=None, speak=None) -> str:
    """Guarda, lista u olvida preferencias de usuario (gustos)."""
    action = str(parameters.get("action", "listar")).strip().lower()
    nombre = str(parameters.get("nombre", "")).strip()
    valor = str(parameters.get("valor", "")).strip()
    confirm = str(parameters.get("confirm", "")).strip().lower()

    if action in ("guardar", "guardar_preferencia", "agregar"):
        if not nombre or not valor:
            return "Decime qué preferencia guardar, por ejemplo: 'recordá que prefiero café sin azúcar' (nombre='cafe', valor='sin azúcar')."
        datos = _leer()
        antes = datos.get(nombre)
        datos[nombre] = valor
        _escribir(datos)
        if antes is None:
            msg = f"Anotado: {nombre}: {valor}."
        else:
            msg = f"Actualicé tu preferencia: {nombre} ahora es {valor}."
        if player:
            player.write_log(f"⭐ {msg}")
        return msg

    if action in ("olvidar", "borrar"):
        if not nombre:
            return "Decime qué preferencia borrar con su nombre."
        if confirm not in _CONFIRM:
            return f"Para borrar '{nombre}' confirmá con 'SÍ'."
        datos = _leer()
        if nombre not in datos:
            return f"No tenía registrada la preferencia '{nombre}'."
        del datos[nombre]
        _escribir(datos)
        if player:
            player.write_log(f"🗑️ Preferencia '{nombre}' olvidada.")
        return f"Listo, olvidé que {nombre}."

    if action in ("borrar_todo",):
        if confirm not in _CONFIRM:
            return "Para borrar todas tus preferencias confirmá con 'SÍ'."
        n = len(_leer())
        _escribir({})
        if player:
            player.write_log(f"🗑️ {n} preferencias borradas.")
        return f"Borré las {n} preferencias que tenía guardadas."

    # listar / estado
    datos = _leer()
    if not datos:
        return "No tengo preferencias guardadas todavía. Decime una, por ejemplo: 'recordá que prefiero descansar a las 23'."
    lineas = [f"{k}: {v}" for k, v in datos.items()]
    if player:
        player.write_log("⭐ Preferencias: " + "; ".join(lineas))
    return "Tus preferencias: " + ". ".join(lineas) + "."