# -*- coding: utf-8 -*-
"""cofre.py — Cofre secreto por voz (encriptado con Fernet).

Guarda contraseñas y datos sensibles en un archivo encriptado con una
clave local (memory/cofre.key). Solo Nia con acceso a esa clave puede
leerlos.
"""
import json
import os

_KEY_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "cofre.key")
_VAULT_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "cofre.vault")

_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")


def _clave():
    from cryptography.fernet import Fernet
    if os.path.exists(_KEY_FILE):
        with open(_KEY_FILE, "rb") as f:
            k = f.read().strip()
        if k:
            return Fernet(k)
    k = Fernet.generate_key()
    os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
    with open(_KEY_FILE, "wb") as f:
        f.write(k)
    return Fernet(k)


def _leer_vault(f):
    if not os.path.exists(_VAULT_FILE):
        return {}
    try:
        with open(_VAULT_FILE, "rb") as raw:
            blob = raw.read()
        return json.loads(f.decrypt(blob).decode("utf-8"))
    except Exception:
        return None  # señal: corrupto o clave distinta


def _escribir_vault(f, datos):
    os.makedirs(os.path.dirname(_VAULT_FILE), exist_ok=True)
    blob = f.encrypt(json.dumps(datos, ensure_ascii=False).encode("utf-8"))
    tmp = _VAULT_FILE + ".tmp"
    with open(tmp, "wb") as raw:
        raw.write(blob)
    os.replace(tmp, _VAULT_FILE)


def _nombre_ok(nombre):
    nombre = nombre.strip().lower()
    return nombre.replace(" ", "_")


def cofre(parameters: dict, player=None, speak=None) -> str:
    """Cofre secreto encriptado: guarda y lee contraseñas por voz."""
    action = str(parameters.get("action", "listar")).strip().lower()
    nombre = _nombre_ok(str(parameters.get("nombre", "") or parameters.get("clave", "")))
    valor = str(parameters.get("valor", "") or parameters.get("secreto", ""))
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in _CONFIRM
    if player:
        player.write_log(f"🔒 cofre: {action}")

    try:
        f = _clave()
    except Exception as e:
        return f"No pude iniciar el cofre: {e}"

    if action in ("guardar", "agregar", "set", "save", "metele"):
        if not nombre:
            return "Decime cómo registrar esto (nombre). Ej: 'contraseña de la red WiFi'."
        if not valor:
            return "Decime cuál es el secreto (valor). Ej: contraseña o dato."
        datos = _leer_vault(f)
        if datos is None:
            return "El cofre está dañado o la clave es distinta. No toco nada."
        datos[nombre] = {"valor": valor}
        _escribir_vault(f, datos)
        return f"Guardado en el cofre como '{nombre}'."

    if action in ("leer", "abrir", "get", "dame"):
        if not nombre:
            return "Decime qué guardado querés leer (nombre)."
        datos = _leer_vault(f)
        if datos is None:
            return "No pude abrir el cofre (clave distinta o archivo dañado)."
        item = datos.get(nombre)
        if not item:
            return f"No hay nada guardado como '{nombre}'. Decime 'listá el cofre'."
        ok_leer = str(parameters.get("confirm", _CONFIRM[0])).strip().lower() in _CONFIRM
        if not ok_leer:
            return (f"El cofre tiene '{nombre}'. ¿Seguro que querés que te lo diga "
                    "en voz alta? Confirmá con 'SÍ' (puede haber gente cerca).")
        return (f"🗝️ {nombre}: {item.get('valor')} "
                "(no lo repitas si no hace falta).")

    if action in ("listar", "lista", "claves"):
        datos = _leer_vault(f)
        if datos is None:
            return "El cofre está dañado o la clave es distinta."
        if not datos:
            return "El cofre está vacío. Decime 'guardá en el cofre' para sumar algo."
        lineas = ["🔐 El cofre tiene:"]
        for k in sorted(datos):
            lineas.append(f"   • {k}")
        lineas.append("Decime 'leé del cofre <nombre>' para ver uno, con SÍ.")
        return "\n".join(lineas)

    if action in ("borrar", "quitar", "delete", "remove"):
        if not nombre:
            return "Decime qué borrar del cofre (nombre)."
        if not ok:
            return f"Voy a BORRAR '{nombre}' del cofre. Confirmá con 'SÍ'."
        datos = _leer_vault(f)
        if datos is None:
            return "El cofre está dañado o la clave es distinta."
        if nombre in datos:
            del datos[nombre]
            _escribir_vault(f, datos)
            return f"Borrado '{nombre}' del cofre."
        return f"No existe '{nombre}' en el cofre."

    return ("Acciones: guardar (nombre, valor) | leer (nombre, confirm='SÍ') | "
            "listar | borrar (nombre + SÍ).")