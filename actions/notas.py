# -*- coding: utf-8 -*-
"""notas.py — Notas rápidas por voz.

Anota pensamientos/textos en un archivo diario y los relee de vuelta.
Los archivos viven en memory/notas/<AAAA-MM-DD>.md
"""
import glob
import os
import re
from datetime import date, datetime

_NOTA_DIR = os.path.join(os.path.dirname(__file__), "..", "memory", "notas")


def _path(fecha):
    return os.path.join(_NOTA_DIR, f"{fecha}.md")


def _anotar(texto):
    if not texto:
        return "Decime qué querés anotar (texto). Ej: 'anotá que mañana tengo turno médico'."
    try:
        os.makedirs(_NOTA_DIR, exist_ok=True)
        ahora = datetime.now().strftime("%H:%M")
        p = _path(date.today().isoformat())
        linea = f"- *{ahora}* {texto.strip()}\n"
        with open(p, "a", encoding="utf-8") as f:
            f.write(linea)
        return "Anotado. Lo tengo en tus notas de hoy."
    except OSError as e:
        return f"No pude anotar (¿carpeta escrita?): {e}"


def _leer(rango, limite):
    try:
        if not os.path.isdir(_NOTA_DIR):
            return "No tenés notas por ahora. Decime 'anotá que X' y armo la primera."
        archivos = sorted(glob.glob(os.path.join(_NOTA_DIR, "*.md")), reverse=True)
        if rango in ("semana", "semanal", "7"):
            desde = (date.today().toordinal() - 6)
            archivos = [a for a in archivos
                        if datetime.strptime(os.path.splitext(os.path.basename(a))[0],
                                             "%Y-%m-%d").toordinal() >= desde]
        elif rango in ("ayer", "yesterday"):
            archivos = [_path((date.fromordinal(date.today().toordinal() - 1)).isoformat())]
            archivos = [a for a in archivos if os.path.exists(a)]
        elif rango not in ("", "hoy", "today"):
            archivos = []
        archivos = archivos[:limite]
        if not archivos:
            return "No encontré notas para ese período."
        lineas = []
        for a in archivos:
            fecha = os.path.splitext(os.path.basename(a))[0]
            try:
                con = open(a, encoding="utf-8").read().strip()
            except OSError:
                continue
            if con:
                lineas.append(f"📌 {fecha}:\n{con}")
        if not lineas:
            return "No encontré notas para ese período."
        return "\n\n".join(lineas)
    except Exception as e:
        return f"No pude leer las notas: {e}"


def notas(parameters: dict, player=None, speak=None) -> str:
    """Notas rápidas por voz: anotar y releer notas diarias."""
    action = str(parameters.get("action", "anotar")).strip().lower()
    texto = str(parameters.get("texto", "")).strip()
    cuando = str(parameters.get("cuando", "hoy")).strip().lower()
    limite = max(1, min(30, int(parameters.get("limite") or 3)))
    if player:
        player.write_log(f"📝 notas: {action}")

    if action in ("anotar", "guardar", "agregar", "add", "new"):
        return _anotar(texto)

    if action in ("leer", "leeme", "leé", "mostrar", "read"):
        return _leer(cuando, limite)

    if action in ("ultimas", "recientes", "ultimos", "last"):
        return _leer("", limite)

    if action in ("borrar", "delete", "clear"):
        confirm = str(parameters.get("confirm", "")).strip().lower()
        if confirm not in ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale"):
            return "Voy a BORRAR tus notas de hoy. Confirmá con 'SÍ'."
        try:
            p = _path(date.today().isoformat())
            if os.path.exists(p):
                os.remove(p)
                return "Borré las notas de hoy."
            return "No había notas de hoy para borrar."
        except OSError as e:
            return f"No pude borrar las notas: {e}"

    return ("Acciones: anotar (texto) | leer (cuando='hoy'|'ayer'|'semana', limite) | "
            "ultimas (limite) | borrar (confirm='SÍ'). Si no especificás acción, anoto.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "-leer":
        print(notas({"action": "leer", "cuando": "hoy"}))
    elif len(sys.argv) > 2:
        print(notas({"action": "anotar", "texto": sys.argv[1]}))
    else:
        print(notas({}))
        print()
        print(notas({"action": "leer"}))