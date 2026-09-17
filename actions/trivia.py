# -*- coding: utf-8 -*-
"""trivia.py — Preguntas de cultura general con puntaje.

Banco local de preguntas (sin internet). Nia hace la pregunta, el usuario
responde, y 'responder' valida contra la pregunta pendiente y suma puntos.
Estado y puntaje en memory/trivia.json.
"""
import json
import os
import random

_BANCO = [
    {"p": "¿Cuál es el río más largo del mundo?", "opc": ["Nilo", "Amazonas", "Misisipi"], "r": "Amazonas"},
    {"p": "¿En qué año llegó el hombre a la Luna?", "opc": ["1965", "1969", "1972"], "r": "1969"},
    {"p": "¿Cuál es el planeta más grande del sistema solar?", "opc": ["Júpiter", "Saturno", "Neptuno"], "r": "Júpiter"},
    {"p": "¿Quién pintó 'La Gioconda'?", "opc": ["Van Gogh", "Leonardo da Vinci", "Picasso"], "r": "Leonardo da Vinci"},
    {"p": "¿Cuál es la capital de Japón?", "opc": ["Osaka", "Kioto", "Tokio"], "r": "Tokio"},
    {"p": "¿Cuántos huesos tiene el cuerpo humano adulto?", "opc": ["206", "256", "186"], "r": "206"},
    {"p": "¿Cuál es el océano más grande?", "opc": ["Atlántico", "Pacífico", "Índico"], "r": "Pacífico"},
    {"p": "¿En qué continente está el desierto del Sahara?", "opc": ["Asia", "África", "Oceanía"], "r": "África"},
    {"p": "¿Quién escribió 'Cien años de soledad'?", "opc": ["Borges", "García Márquez", "Cortázar"], "r": "García Márquez"},
    {"p": "¿Cuál es el metal más liviano?", "opc": ["Aluminio", "Litio", "Magnesio"], "r": "Litio"},
    {"p": "¿Cuántos continentes hay?", "opc": ["5", "6", "7"], "r": "6"},
    {"p": "¿Qué país tiene la Torre Eiffel?", "opc": ["Italia", "Francia", "España"], "r": "Francia"},
    {"p": "¿Cuál es el animal más veloz del mundo?", "opc": ["Guepardo", "León", "Caballo"], "r": "Guepardo"},
    {"p": "¿Cuál es la moneda de Estados Unidos?", "opc": ["Euro", "Libra", "Dólar"], "r": "Dólar"},
    {"p": "¿Quién era 'El Che' en la Revolución Cubana?", "opc": ["Fidel Castro", "Ernesto Guevara", "Camilo Cienfuegos"], "r": "Ernesto Guevara"},
    {"p": "¿En qué deporte se usa una 'mesa verde'?", "opc": ["Tenis", "Ping pong", "Pool"], "r": "Ping pong"},
    {"p": "¿Cuál es el país más poblado?", "opc": ["China", "India", "EE.UU."], "r": "India"},
    {"p": "¿Qué gas respiramos principalmente?", "opc": ["Oxígeno", "Nitrógeno", "Hidrógeno"], "r": "Nitrógeno"},
    {"p": "¿Cuál es el instrumento con más cuerdas en un piano?", "opc": ["88", "76", "61"], "r": "88"},
    {"p": "¿En qué año terminó la Segunda Guerra Mundial?", "opc": ["1944", "1945", "1946"], "r": "1945"},
    {"p": "¿Cuál es el deporte más popular del planeta?", "opc": ["Básquet", "Cricket", "Fútbol"], "r": "Fútbol"},
    {"p": "¿Qué órgano bombea sangre?", "opc": ["Pulmón", "Hígado", "Corazón"], "r": "Corazón"},
    {"p": "¿Cuál es la capital de Australia?", "opc": ["Sídney", "Melbourne", "Canberra"], "r": "Canberra"},
    {"p": "¿Cuántos días tiene un año bisiesto?", "opc": ["364", "365", "366"], "r": "366"},
    {"p": "¿Quién descubrió la penicilina?", "opc": ["Fleming", "Pasteur", "Curie"], "r": "Fleming"},
]

_ARCHIVO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "memory", "trivia.json")


def _cargar():
    try:
        with open(_ARCHIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"puntaje": 0, "aciertos": 0, "errores": 0, "pendiente": None}


def _guardar(d):
    os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
    with open(_ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)


def trivia(parameters: dict, player=None, speak=None) -> str:
    """Juego de preguntas de cultura general con puntaje."""
    action = str(parameters.get("action", "preguntar")).strip().lower()
    d = _cargar()

    if action in ("test",):
        return "La trivia funciona (banco de 25 preguntas)."

    if action in ("preguntar", "siguiente", "nueva", "otra"):
        pend = d.get("pendiente")
        if pend:
            return ("Ya hay una pregunta pendiente: " + pend["p"] +
                    " ¿Me respondés antes de la siguiente?")
        if len(_BANCO) <= d.get("usadas", 0):
            return "¡Terminaste todo el banco! Reiniciá con 'reiniciar' para volver a jugar."
        usadas = set(d.get("usadas_lista", []))
        disponibles = [q for q in _BANCO if q["p"] not in usadas]
        if not disponibles:
            d["usadas_lista"] = []
            d["usadas"] = 0
            _guardar(d)
            disponibles = list(_BANCO)
        q = random.choice(disponibles)
        opciones = list(q["opc"])
        random.shuffle(opciones)
        d["pendiente"] = {"p": q["p"], "opciones": opciones, "resp": q["r"],
                          "ts": __import__("time").time()}
        d.setdefault("usadas_lista", []).append(q["p"])
        d["usadas"] = len(d["usadas_lista"])
        _guardar(d)
        if player:
            player.write_log("🎯 Pregunta: " + q["p"])
        return (f"Trivia: dice así: '{q['p']}'. Las opciones son: "
                + ", ".join(f"{'abc'[i]}) {o}" for i, o in enumerate(opciones))
                + ". Respondeme la correcta.")

    if action in ("responder", "respuesta", "chequear"):
        pend = d.get("pendiente")
        if not pend:
            return "No hay pregunta pendiente. Decime 'preguntar'."
        resp = str(parameters.get("respuesta", "") or parameters.get("resp", "")).strip().lower()
        # Acepta 'a)' / 'b)' o el texto de la opción
        opciones = pend["opciones"]
        resp_texto = None
        texto = resp.strip(" )(").lower()
        if texto in ("a", "b", "c"):
            idx = {"a": 0, "b": 1, "c": 2}[texto]
            if idx < len(opciones):
                resp_texto = opciones[idx]
        else:
            for o in opciones:
                if o.lower() in texto or texto in o.lower():
                    resp_texto = o
                    break
        ok = resp_texto is not None and resp_texto.strip().lower() == pend["resp"].strip().lower()
        d["pendiente"] = None
        if ok:
            d["aciertos"] += 1
            d["puntaje"] += 1
        else:
            d["errores"] += 1
        _guardar(d)
        if not ok:
            return (f"¡Casi! Era '{pend['resp']}'. Llevás {d['puntaje']} puntos "
                    f"({d['aciertos']} bien, {d['errores']} mal). ¿Seguimos?")
        return (f"¡Exacto! '{pend['resp']}' es la correcta. Llevás {d['puntaje']} "
                f"puntos ({d['aciertos']} bien). ¿Otra?")

    if action in ("puntaje", "estado", "score"):
        texto = (f"Puntaje de trivia: {d['puntaje']} puntos, {d['aciertos']} "
                 f"aciertos y {d['errores']} errores.")
        if d.get("pendiente"):
            texto += " Tenés una pregunta pendiente."
        return texto

    if action in ("reiniciar", "reset"):
        if parameters.get("confirm", "").strip().upper() not in ("SI", "SÍ"):
            return "Para resetear el puntaje confirmame con confirm='SÍ'."
        _guardar({"puntaje": 0, "aciertos": 0, "errores": 0, "pendiente": None,
                  "usadas_lista": [], "usadas": 0})
        return "Puntaje reiniciado. Decime 'preguntar' para arrancar de cero."

    return "Acciones: preguntar | responder (respuesta) | puntaje | reiniciar (SÍ)."