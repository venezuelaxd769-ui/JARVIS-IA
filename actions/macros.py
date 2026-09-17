# -*- coding: utf-8 -*-
"""macros.py — Macros por voz.

Guarda secuencias de pasos (instrucciones en lenguaje natural para las
herramientas de Nia) bajo un nombre y una o más frases disparadoras.
Cuando escuchás la frase registrada, ejecutás los pasos en orden.
"""
import json
import os

_MACRO_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "macros.json")


def _cargar():
    try:
        with open(_MACRO_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar(macros):
    os.makedirs(os.path.dirname(_MACRO_FILE), exist_ok=True)
    with open(_MACRO_FILE, "w", encoding="utf-8") as f:
        json.dump(macros, f, ensure_ascii=False, indent=1)


def macros(parameters: dict, player=None, speak=None) -> str:
    """Macros: guardá secuencias de acciones y disparalas con una frase."""
    action = str(parameters.get("action", "listar")).strip().lower()
    nombre = str(parameters.get("nombre", "")).strip()
    pasos = parameters.get("pasos") or parameters.get("acciones") or []
    frases = parameters.get("frases") or []
    if isinstance(pasos, str):
        pasos = [s.strip() for s in pasos.splitlines() if s.strip()]
    if isinstance(frases, str):
        frases = [s.strip() for s in frases.split(",") if s.strip()]
    paso_extra = str(parameters.get("paso", "")).strip()
    frase_extra = str(parameters.get("frase", "")).strip()
    if paso_extra:
        pasos.append(paso_extra)
    if frase_extra:
        frases.append(frase_extra)
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")
    if player:
        player.write_log(f"⚡ macros: {action}")

    if action in ("crear", "crea", "add", "nuevo"):
        if not nombre:
            return "Decime el nombre del macro (nombre). Ej: 'modo peli'."
        if not pasos:
            return ("Decime qué pasos va a hacer (pasos: lista de instrucciones). "
                    "Ej: ['bajá el volumen al 30%', 'maximizá el navegador', 'reiniciá la música']")
        pasos = [p for p in pasos if p.strip()]
        mac = {"pasos": pasos, "frases": [f for f in frases if f.strip()]}
        datos = _cargar()
        datos[nombre.lower()] = mac
        _guardar(datos)
        respuesta = (f"Macro '{nombre}' guardado con {len(pasos)} pasos.")
        if mac["frases"]:
            respuesta += f" Lo disparo cuando escucho: {', '.join(mac['frases'])}."
        return respuesta

    if action in ("listar", "lista", "todos"):
        datos = _cargar()
        if not datos:
            return "No tenés macros aún. Decime 'creá una macro' y la armamos."
        lineas = ["⚡ Tus macros:"]
        for nombre_m, mac in datos.items():
            f = f" (frases: {', '.join(mac.get('frases', []))})" if mac.get("frases") else ""
            n_pasos = len(mac.get("pasos", []))
            lineas.append(f"   • {nombre_m}: {n_pasos} pasos{f}")
        return "\n".join(lineas)

    if action in ("disparar", "ejecutar", "run", "play"):
        if not nombre:
            return "Decime qué macro disparo (nombre)."
        datos = _cargar()
        mac = datos.get(nombre.strip().lower())
        if not mac:
            return f"No encontré el macro '{nombre}'. Decime 'listá los macros' para verlos."
        pasos_list = mac.get("pasos", [])
        if not pasos_list:
            return f"El macro '{nombre}' no tiene pasos definidos."
        lineas = [f"⚡ Ejecutá el macro '{nombre}', en orden, con tus herramientas:"]
        for i, p in enumerate(pasos_list, 1):
            lineas.append(f"   {i}. {p}")
        lineas.append("Cuando termines todos, avisame que está listo.")
        return "\n".join(lineas)

    if action in ("borrar", "eliminar", "quitar", "delete"):
        if not nombre:
            return "Decime qué macro quiero borrar (nombre)."
        if not ok:
            return f"Voy a BORRAR el macro '{nombre}'. Confirmá con 'SÍ'."
        datos = _cargar()
        if nombre.strip().lower() in datos:
            del datos[nombre.strip().lower()]
            _guardar(datos)
            return f"Borrado el macro '{nombre}'."
        return f"No existe el macro '{nombre}'."

    if action in ("ayuda", "help", "explicar"):
        return ("Con 'crear' guardo una secuencia: creá un macro 'modo peli' con "
                "pasos=['bajá el volumen al 20%', 'maximizá el navegador'] y "
                "frases=['modo peli']. Después disparámelo con 'disparar' o "
                "decime la frase y lo hago. 'listar' muestra tus macros, "
                "'borrar' con SÍ elimina uno.")

    return ("Acciones: crear (nombre, pasos, frases) | listar | disparar (nombre) | "
            "borrar (nombre + SÍ) | ayuda.")