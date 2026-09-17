# -*- coding: utf-8 -*-
"""hora_mundial.py — Hora en ciudades del mundo por voz.

Convierte nombres de ciudades en español a zonas IANA (zoneinfo, tzdata ya
instalada) y devuelve la hora local junto con la diferencia con tu hora.
"""
import sys
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from actions import _ciudades


_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _resolver(clave):
    clave = clave.strip().lower()
    z = _ciudades.CIUDADES.get(clave)
    if z:
        return z
    zona = clave.replace(" ", "_")
    try:
        ZoneInfo(zona)
        return zona
    except Exception:
        return None


def hora_mundial(parameters: dict, player=None, speak=None) -> str:
    """Hora actual en una ciudad del mundo."""
    action = str(parameters.get("action", "hora")).strip().lower()

    if action in ("listar", "ciudades", "ayuda"):
        nombres = ", ".join(sorted(_ciudades.CIUDADES))
        return ("Conozco estas ciudades: " + nombres + ". "
                "O podés pasarme una zona tipo Asia/Tokyo.")

    if action not in ("hora", "que_hora", "hora_en", "cuando"):
        return "Acciones: hora | listar."

    ciudad = str(parameters.get("ciudad", "") or parameters.get("lugar", "")).strip()
    if not ciudad:
        return "Decime la ciudad, por ejemplo: '¿qué hora es en Tokio?'."

    zona = _resolver(ciudad)
    if not zona:
        return (f"No conozco la ciudad '{ciudad}'. Probá con 'listar' para ver "
                f"las que tengo, o pasándola como zona tipo America/Mexico_City.")

    try:
        ahora = datetime.now(ZoneInfo(zona))
        local = datetime.now().astimezone()
    except Exception as e:
        return f"No pude obtener la hora de {ciudad}: {e}."
    diff = ahora.utcoffset().total_seconds() - local.utcoffset().total_seconds()
    hs = int(diff // 3600)
    mins = int(abs(diff) % 3600 // 60)
    if hs == 0 and mins == 0:
        texto_diff = "es la misma hora que acá."
    elif hs >= 0:
        texto_diff = f"va {hs} h {mins} min adelante de tu hora."
    else:
        texto_diff = f"va {abs(hs)} h {mins} min atrasada de tu hora."
    salida = (f"{ahora.strftime('%H:%M')} del {_DIAS[ahora.weekday()]} "
              f"{ahora.day} de {_MESES[ahora.month - 1]}.")
    if player:
        player.write_log(f"🌍 {ciudad} ({zona}): {salida} {texto_diff}")
    return f"En {ciudad.title()} son las {salida} Y {texto_diff}"