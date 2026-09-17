# -*- coding: utf-8 -*-
"""tareas.py — Lista de pendientes por voz.

Tareas con prioridad y estado en memory/tareas.json. Modo minimalista y
100% local: agregar, listar por prioridad, marcar hechas, borrar, limpiar.
"""
import json
import os
from datetime import datetime

_ARCHIVO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "memory", "tareas.json")


def _cargar():
    try:
        with open(_ARCHIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"tareas": []}


def _guardar(data):
    os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
    with open(_ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _formatear(t):
    estado = "hecha" if t.get("lista", False) else "pendiente"
    prio = t.get("prioridad", 0)
    etiqueta = {1: "baja", 2: "media", 3: "alta"}.get(prio, "media")
    txt = f"{t['id']}. {t['texto']} ({estado}, prioridad {etiqueta})"
    vence = t.get("vence", "")
    if vence:
        txt += f", vence {vence}"
    return txt


def tareas(parameters: dict, player=None, speak=None) -> str:
    """Lista de tareas pendientes por voz."""
    action = str(parameters.get("action", "listar")).strip().lower()
    data = _cargar()
    ts = data.get("tareas", [])

    def ordenar(lista):
        return sorted(lista, key=lambda t: (t.get("lista", False), -t.get("prioridad", 0),
                                            t.get("vence", "")))

    if action in ("test",):
        return "La lista de tareas funciona."

    if action in ("agregar", "agregar_tarea", "nueva", "add", "crear"):
        texto = str(parameters.get("texto", "") or parameters.get("tarea", "")).strip()
        if not texto:
            return "Decime qué tarea querés, por ejemplo tarea='pagar la luz'."
        prio = str(parameters.get("prioridad", "media")).strip().lower()
        prio = {"alta": 3, "media": 2, "baja": 1}.get(prio, 2)
        vence = str(parameters.get("vence", "") or parameters.get("para", "")).strip()
        nid = 1
        if ts:
            nid = max(int(t.get("id", 0) or 0) for t in ts) + 1
        ts.append({"id": nid, "texto": texto, "prioridad": prio,
                   "vence": vence, "lista": False,
                   "creada": datetime.now().isoformat(timespec="minutes")})
        data["tareas"] = ts
        _guardar(data)
        return f"Lista, tengo la tarea '{texto}' en tu lista."

    if action in ("listar", "ver", "mostrar"):
        if not ts:
            return "Estás al día, no tenés tareas pendientes."
        pend = [t for t in ts if not t.get("lista", False)]
        hechas = [t for t in ts if t.get("lista", False)]
        sal = []
        if pend:
            sal.append("Tus pendientes:")
            sal.extend("- " + _formatear(t) for t in ordenar(pend))
        else:
            sal.append("No tenés tareas pendientes.")
        if hechas:
            sal.append("Hechas: " + ", ".join(f"#{t['id']} {t['texto']}" for t in hechas))
        return "\n".join(sal)

    if action in ("hecha", "completar", "hacer", "terminar"):
        tid = str(parameters.get("id", "") or parameters.get("tarea", "")).strip()
        match = [t for t in ts if str(t.get("id", "")) == tid or
                 tid.lower() in str(t.get("texto", "")).lower()]
        if not match:
            return f"No encontré la tarea '{tid}'. Decime 'listar' para ver los IDs."
        for t in match:
            t["lista"] = True
        _guardar(data)
        nombre = match[0].get("texto", "")
        return f"Marca la tarea '{nombre}' como hecha. ¡Bien ahí!"

    if action in ("deshacer", "reabrir"):
        tid = str(parameters.get("id", "")).strip()
        match = [t for t in ts if str(t.get("id", "")) == tid]
        if not match:
            return "Pasame el ID de la tarea a reabrir."
        match[0]["lista"] = False
        _guardar(data)
        return f"Reabrí '#{tid} {match[0].get('texto', '')}'."

    if action in ("borrar", "quitar", "remove"):
        tid = str(parameters.get("id", "")).strip()
        if not tid or parameters.get("confirm", "").strip().upper() not in ("SI", "SÍ"):
            return "Para borrar una tarea pasame su ID y confirm='SÍ'."
        rest = [t for t in ts if str(t.get("id", "")) != tid]
        if len(rest) == len(ts):
            return f"No encontré la tarea con ID '{tid}'."
        data["tareas"] = rest
        _guardar(data)
        return f"Borrada la tarea #{tid}."

    if action in ("limpiar", "limpieza"):
        if parameters.get("confirm", "").strip().upper() not in ("SI", "SÍ"):
            return "Confirmame con confirm='SÍ' para vaciar la lista completa."
        data["tareas"] = []
        _guardar(data)
        return "Listo, quedó la lista vacía."

    if action in ("prioridad", "importante"):
        tid = str(parameters.get("id", "")).strip()
        prio = str(parameters.get("prioridad", "alta")).strip().lower()
        prio = {"alta": 3, "media": 2, "baja": 1}.get(prio, 3)
        for t in ts:
            if str(t.get("id", "")) == tid:
                t["prioridad"] = prio
                _guardar(data)
                etiqueta = {1: "baja", 2: "media", 3: "alta"}[prio]
                return f"La tarea #{tid} ahora es prioridad {etiqueta}."
        return f"No encontré la tarea con ID '{tid}'."

    return "Acciones: agregar | listar | hecha | deshacer | borrar (SÍ) | limpiar (SÍ) | prioridad."