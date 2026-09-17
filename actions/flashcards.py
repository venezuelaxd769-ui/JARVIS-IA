# -*- coding: utf-8 -*-
"""flashcards.py — Tarjetas de estudio con repaso por voz.

memory/flashcards.json: {'cartas': [{'id', 'pregunta', 'respuesta', 'sabida'}]}.
El repaso elige una carta no sabida; Nia pregunta, el usuario responde cómo
fue y 'responder' la marca como sabida o le muestra la respuesta.
"""
import json
import os
import random
from datetime import datetime

_ARCHIVO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "memory", "flashcards.json")


def _cargar():
    try:
        with open(_ARCHIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"cartas": []}


def _guardar(d):
    os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
    with open(_ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def _nid(cartas):
    return max([int(c.get("id", 0) or 0) for c in cartas], default=0) + 1


def flashcards(parameters: dict, player=None, speak=None) -> str:
    """Tarjetas de estudio con repaso por voz."""
    action = str(parameters.get("action", "repasar")).strip().lower()
    d = _cargar()
    cartas = d.get("cartas", [])

    if action in ("test",):
        return "Las flashcards funcionan."

    if action in ("agregar", "nueva", "crear"):
        pregunta = str(parameters.get("pregunta", "") or parameters.get("frente", "")).strip()
        respuesta = str(parameters.get("respuesta", "") or parameters.get("reverso", "")).strip()
        if not pregunta:
            return "Decime la pregunta de la tarjeta, por ejemplo pregunta='¿capital de Francia?'."
        if not respuesta:
            return "Y la respuesta, por ejemplo respuesta='París'."
        cartas.append({"id": _nid(cartas), "pregunta": pregunta,
                       "respuesta": respuesta, "sabida": False,
                       "creada": datetime.now().isoformat(timespec="minutes")})
        d["cartas"] = cartas
        _guardar(d)
        return f"Tarjeta agregada: '{pregunta}'. Tenés {len(cartas)} cartas en el mazo."

    if action in ("listar", "cartas", "ver"):
        if not cartas:
            return "No tenés tarjetas todavía. Decime 'agregá una flashcard'."
        pend = [c for c in cartas if not c.get("sabida", False)]
        sal = f"Tenés {len(cartas)} tarjetas"
        sal += f" ({len(pend)} sin saberse)." if pend else " (todas sabidas)."
        sal += "\n" + "\n".join(f"- #{c['id']}: {c['pregunta']} — {c['respuesta']}"
                                 f"{'' if not c.get('sabida') else ' [sabida]'}"
                                 for c in cartas[:15])
        return sal

    if action in ("repasar", "repaso", "preguntar"):
        pend = [c for c in cartas if not c.get("sabida", False)]
        if not pend:
            if not cartas:
                return "No tenés cartas. Agregá una para arrancar el repaso."
            return "¡Las sabés todas! Estudiás como un campeón. Podés resetear con 'reset' para volver a repasar."
        c = random.choice(pend)
        d["pendiente"] = {"id": c["id"], "pregunta": c["pregunta"],
                          "respuesta": c["respuesta"]}
        _guardar(d)
        if player:
            player.write_log("🃏 " + f"Flashcard: {c['pregunta']}")
        return f"Repaso: {c['pregunta']} ¿La sabés (sí) o te muestro la respuesta (no)?"

    if action in ("responder", "respuesta"):
        pend = d.get("pendiente")
        if not pend:
            return "No hay ninguna carta en el aire. Decime 'repasar'."
        sabida = str(parameters.get("sabida", "") or parameters.get("si", "")).strip().lower()
        ok = sabida in ("si", "sí", "si", "s", "sí la sé", "la sé", "sabia", "true")
        if ok:
            for c in cartas:
                if c.get("id") == pend.get("id"):
                    c["sabida"] = True
            d["cartas"] = cartas
            d["pendiente"] = None
            _guardar(d)
            return f"¡Bien ahí! 'La sé'. Sigo con la siguiente: decime 'repasar'."
        else:
            for c in cartas:
                if c.get("id") == pend.get("id"):
                    break
            resp = pend.get("respuesta", c.get("respuesta", ""))
            d["pendiente"] = None
            _guardar(d)
            return f"La respuesta es: {resp} Quedó para otro repaso."

    if action in ("borrar", "eliminar"):
        cid = str(parameters.get("id", "")).strip()
        if not cid or parameters.get("confirm", "").strip().upper() not in ("SI", "SÍ"):
            return "Decime el id de la tarjeta y confirm='SÍ' para borrarla."
        rest = [c for c in cartas if str(c.get("id", "")) != cid]
        if len(rest) == len(cartas):
            return f"No encontré la tarjeta #{cid}."
        d["cartas"] = rest
        _guardar(d)
        return f"Borrada la tarjeta #{cid}."

    if action in ("reset", "reiniciar", "olvidar_todo"):
        if parameters.get("confirm", "").strip().upper() not in ("SI", "SÍ"):
            return "Confirmame con confirm='SÍ' para marcar todas como no sabidas."
        for c in cartas:
            c["sabida"] = False
        d["cartas"] = cartas
        d["pendiente"] = None
        _guardar(d)
        return "Listo, todas las cartas vuelven a repaso."

    return ("Acciones: agregar (pregunta, respuesta) | listar | repasar | "
            "responder (sabida=si/no) | borrar (id, SÍ) | reset (SÍ).")