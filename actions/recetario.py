# -*- coding: utf-8 -*-
"""recetario.py — Recetas guardadas por voz.

Cada receta queda en memory/recetario.json {nombre: {ingredientes, pasos}}.
Nia guarda la receta al natural, la lista, la lee completa o recuérdale una
parte. Solo lectura y borrado con confirm='SÍ'.
"""
import json
import os
from datetime import datetime

_ARCHIVO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "memory", "recetario.json")


def _cargar():
    try:
        with open(_ARCHIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar(d):
    os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
    with open(_ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _encontrar(d, nombre):
    nombre = nombre.strip().lower()
    for k in d:
        if k.lower() == nombre:
            return k
    return next((k for k in d if nombre in k.lower()), None)


def recetario(parameters: dict, player=None, speak=None) -> str:
    """Guarda y lee recetas de cocina por voz."""
    action = str(parameters.get("action", "listar")).strip().lower()
    d = _cargar()

    if action in ("test",):
        return "El recetario funciona."

    if action in ("guardar", "agregar", "guardar_receta"):
        nombre = str(parameters.get("nombre", "") or parameters.get("receta", "")).strip()
        texto = str(parameters.get("texto", "") or parameters.get("ingredientes", "")).strip()
        if not nombre:
            return "Decime el nombre de la receta, por ejemplo nombre='tarta de zapallitos'."
        if not texto:
            return "Y me falta el contenido: ingredientes y pasos."
        d[nombre.lower().strip()] = {
            "texto": texto,
            "creada": datetime.now().isoformat(timespec="minutes"),
        }
        _guardar(d)
        if player:
            player.write_log("🍳 Receta guardada: " + nombre)
        return f"¡Anotada la receta de {nombre}! Cuando cocines decime 'leé la receta de {nombre}'."

    if action in ("listar", "recetas"):
        if not d:
            return "No tenés recetas guardadas todavía. Decime 'guardá una receta'."
        nombres = ", ".join(sorted(k.title() for k in d))
        return f"Tus recetas: {nombres}. ¿Cuál querés que te lea?"

    if action in ("leer", "mostrar", "leer_receta"):
        nombre = str(parameters.get("nombre", "") or parameters.get("receta", "")).strip()
        clave = _encontrar(d, nombre)
        if not clave:
            return f"No encontré la receta '{nombre}'. Decime 'listar' para ver todas."
        receta = d[clave]
        if player:
            player.write_log("🍳 " + f"Receta '{clave}': " + receta["texto"][:160])
        return f"Receta de {clave.title()}. {receta['texto']}"

    if action in ("borrar", "quitar"):
        nombre = str(parameters.get("nombre", "") or parameters.get("receta", "")).strip()
        clave = _encontrar(d, nombre)
        if not clave:
            return f"No encontré la receta '{nombre}'."
        if parameters.get("confirm", "").strip().upper() not in ("SI", "SÍ"):
            return f"Confirma con confirm='SÍ' para borrar '{clave}'."
        del d[clave]
        _guardar(d)
        return f"Borrada la receta de {clave.title()}."

    return "Acciones: guardar (nombre, texto) | listar | leer (nombre) | borrar (SÍ)."