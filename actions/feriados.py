# -*- coding: utf-8 -*-
"""feriados.py — Feriados y efemérides por voz (Argentina).

Consulta la API pública de feriados argentinos (argentinadatos.com) con
respaldo offline de fechas fijas conocidas, y tira efemérides de cada día.
Todo en español.
"""
import json
import urllib.request
from datetime import date, datetime

_API = "https://api.argentinadatos.com/v1/feriados/{año}"
_UA = {"User-Agent": "Mozilla/5.0"}

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Fechas fijas (inamovibles) como respaldo sin internet. Clave: MM-DD
_FIJOS = {
    "01-01": "Año nuevo",
    "03-24": "Día de la Memoria por la Verdad y la Justicia",
    "04-02": "Día del Veterano y de los Caídos en Malvinas",
    "05-01": "Día del Trabajador",
    "05-25": "Revolución de Mayo",
    "06-17": "Día del Paso a la Inmortalidad del General Güemes",
    "06-20": "Día del Paso a la Inmortalidad del General Belgrano",
    "07-09": "Día de la Independencia",
    "08-17": "Paso a la Inmortalidad del General San Martín",
    "10-12": "Día del Respeto a la Diversidad Cultural",
    "11-20": "Día de la Soberanía Nacional",
    "12-08": "Día de la Inmaculada Concepción de María",
    "12-25": "Navidad",
}

# Efemérides famosas (Argentina/mundo). Clave: MM-DD
_EFEMERIDES = {
    "01-01": "Almanaque mundial: arranca el año nuevo.",
    "01-06": "Día de Reyes.",
    "02-14": "San Valentín, día de los enamorados.",
    "03-08": "Día Internacional de la Mujer Trabajadora.",
    "03-19": "En 1812 Belgrano creó y enarboló por primera vez la Bandera Argentina.",
    "03-24": "Día de la Memoria por la Verdad y la Justicia (golpe de 1976).",
    "04-02": "Día del Veterano y de los Caídos en Malvinas (1982).",
    "04-07": "Día Mundial de la Salud.",
    "04-19": "En 1818 murió el general Manuel Belgrano.",
    "05-01": "Día Internacional de los Trabajadores.",
    "05-25": "Revolución de Mayo de 1810: nacimiento del primer gobierno patrio.",
    "06-15": "En 1919 nació, según su documento, el zorzal criollo Carlos Gardel.",
    "06-20": "Día de la Bandera: muere Manuel Belgrano en 1820.",
    "07-09": "Grito de la Independencia Argentina en 1816 en San Miguel de Tucumán.",
    "08-23": "Éxodo Jujeño de 1812, la retirada popular liderada por Belgrano.",
    "09-11": "Muere Domingo Faustino Sarmiento en 1888; día del Maestro.",
    "09-17": "Día del Profesor: muere José Manuel Estrada en 1894.",
    "10-12": "Día del Respeto a la Diversidad Cultural (1492, llegada a América).",
    "11-20": "Combate de la Vuelta de Obligado (1845), por la Soberanía Nacional.",
    "12-01": "Día Mundial de la Lucha contra el SIDA.",
    "12-08": "Inmaculada Concepción.",
    "12-25": "Navidad.",
    "12-31": "Fin de año global.",
}


def _consulta(año):
    try:
        req = urllib.request.Request(_API.format(año=año), headers=_UA)
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [x for x in data if x.get("fecha")]
    except Exception:
        return None


def _feriados_año(año):
    data = _consulta(año)
    if data:
        return data, False
    tmp = []
    for mmdd, nombre in _FIJOS.items():
        tmp.append({"fecha": f"{año}-{mmdd}", "tipo": "inamovible",
                    "nombre": nombre, "_offline": True})
    return tmp, True


def _parse_fecha(s):
    s = s.strip().replace("/", "-")
    fmt = "%d-%m" if len(s) == 5 else ("%d-%m-%Y" if len(s) == 10 else "%Y-%m-%d")
    try:
        return datetime.strptime(s, fmt).date()
    except ValueError:
        return None


def _efemeride(fecha):
    return _EFEMERIDES.get(fecha.strftime("%m-%d"))


def _proximos(feriados, desde, n=3):
    lista = []
    ordenado = sorted(feriados, key=lambda x: x["fecha"])
    for f in ordenado:
        try:
            df = datetime.strptime(f["fecha"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if df >= desde:
            lista.append(f)
            if len(lista) >= n:
                break
    return lista


def _fecha_es(d):
    anio = "" if d.year == 1900 else (f" de {d.year}" if d.year != date.today().year else "")
    return f"{d.day} de {_MESES[d.month - 1]}{anio}"


def _dia_sem(d):
    return _SEMANA[d.weekday()]


def _formato(f):
    try:
        df = datetime.strptime(f["fecha"], "%Y-%m-%d").date()
    except ValueError:
        return f["fecha"]
    d = _fecha_es(df)
    tipo = f.get("tipo", "").lower()
    etiqueta = {"inamovible": "ℹ️ inamovible", "trasladable": "↪️ trasladable",
                "puente": "🌉 puente"}.get(tipo, "")
    return f"• {d}: {f.get('nombre')} {etiqueta}".strip(), df


def feriados(parameters: dict, player=None, speak=None) -> str:
    """Feriados y efemérides (Argentina): hoy, próximo, año o efeméride."""
    action = str(parameters.get("action", "hoy")).strip().lower()
    fecha = str(parameters.get("fecha", "")).strip()
    año = str(parameters.get("año", "") or parameters.get("anio", "")).strip()
    n = max(1, min(10, int(parameters.get("limite") or 3)))
    if player:
        player.write_log(f"📅 feriados: {action}")

    if action in ("hoy", "hoy_es", "que_hay_hoy"):
        hoy = date.today()
        fer, offline = _feriados_año(hoy.year)
        eshoy = None
        for f in fer:
            if f.get("fecha") == hoy.isoformat():
                eshoy = f
                break
        partes = [f"Hoy es {_dia_sem(hoy)}, {_fecha_es(hoy)}."]
        if eshoy:
            partes.append(f"🎉 Hoy es FERIADO: {eshoy.get('nombre')} ({eshoy.get('tipo')}).")
        else:
            partes.append("Hoy no es feriado.")
        ef = _efemeride(hoy)
        if ef:
            partes.append(f"📜 Efeméride: {ef}")
        prox = _proximos(fer, hoy, 1)
        if prox:
            pf = prox[0]
            try:
                df = datetime.strptime(pf["fecha"], "%Y-%m-%d").date()
                faltan = (df - hoy).days
                partes.append(f"⏭️ Próximo feriado: {pf.get('nombre')} el {_dia_sem(df)} "
                              f"{_fecha_es(df)}, en {faltan} día{'s' if faltan != 1 else ''}.")
            except ValueError:
                pass
        if offline:
            partes.append("(Datos sin conexión: solo feriados fijos del calendario.)")
        return "\n".join(partes)

    if action in ("proximo", "proximos", "siguiente", "next"):
        desde = _parse_fecha(fecha) or date.today()
        fer, offline = _feriados_año(desde.year)
        lista = _proximos(fer, desde, n)
        if not lista:
            return "No hay feriados próximos para esa fecha."
        lines = ["⏭️ Próximos feriados:"]
        for f in lista:
            texto, df = _formato(f)
            lines.append(texto.replace("de 2026", "", 1))
        if offline:
            lines.append("(Datos sin conexión.).")
        return "\n".join(lines)

    if action in ("año", "anio", "feriados", "todos", "listar"):
        año_int = int(año) if año.isdigit() else date.today().year
        fer, offline = _feriados_año(año_int)
        if not fer:
            return f"No tengo feriados para {año_int}."
        lines = [f"📅 Feriados de {año_int} ({len(fer)}):"]
        for f in sorted(fer, key=lambda x: x["fecha"]):
            texto, _ = _formato(f)
            lines.append(texto)
        if offline:
            lines.append("(Datos sin conexión: solo fijos.).")
        return "\n".join(lines)

    if action in ("efemeride", "efemerides", "que_paso"):
        d = _parse_fecha(fecha) if fecha else date.today()
        if not d:
            return "Escribí la fecha como dd/mm (ej: 25/05) o dd/mm/aaaa."
        ef = _efemeride(d)
        if ef:
            return f"📜 {_dia_sem(d)} {_fecha_es(d)}: {ef}"
        return f"No tengo una efeméride anotada para el {d.day} de {_MESES[d.month - 1]}."

    return ("Acciones: hoy | proximo (fecha desde) | año (año) | efemeride (fecha dd/mm).")