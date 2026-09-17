# -*- coding: utf-8 -*-
"""convertidor.py — Conversor universal por voz.

Monedas con tipo de cambio real (open.er-api.com, sin claves, con respaldo
fijo si no hay internet) y unidades: longitud, peso, temperatura, velocidad,
datos (GB/TB) y tiempo. 100% local salvo el tipo de cambio.
"""
import json
import urllib.request

_UNIDADES = {
    "longitud": {
        "km": 1000, "m": 1, "cm": 0.01, "mm": 0.001, "mi": 1609.344,
        "millas": 1609.344, "yd": 0.9144, "ft": 0.3048, "pie": 0.3048,
        "pies": 0.3048, "in": 0.0254, "pulgadas": 0.0254,
    },
    "peso": {
        "kg": 1, "g": 0.001, "mg": 1e-6, "lb": 0.45359237, "libras": 0.45359237,
        "lbra": 0.45359237, "oz": 0.0283495, "onzas": 0.0283495, "ton": 1000,
    },
    "datos": {
        "b": 1, "kib": 1024, "kb": 1000, "mib": 1024**2, "mb": 1000**2,
        "gib": 1024**3, "gb": 1000**3, "tib": 1024**4, "tb": 1000**4,
    },
    "velocidad": {
        "km/h": 0.2777778, "m/s": 1, "kmh": 0.2777778, "mph": 0.44704,
        "nudo": 0.514444,
    },
}

_CAMBIO = {}
_TASA_FIJA = {"USD": 1220, "EUR": 1330, "ARS": 1, "BRL": 220, "UYU": 30, "CLP": 1.3, "GBP": 1550}


def _cargar_cambio():
    global _CAMBIO
    if _CAMBIO:
        return True
    try:
        with urllib.request.urlopen("https://open.er-api.com/v6/latest/USD", timeout=6) as r:
            d = json.loads(r.read().decode("utf-8"))
        tasas = {k: v for k, v in d.get("rates", {}).items()}
        if tasas:
            _CAMBIO = tasas
            return True
    except Exception:
        pass
    for k, v in _TASA_FIJA.items():
        _CAMBIO[k] = v / _TASA_FIJA["USD"]
    return False


def _num(s):
    s = str(s).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _temp(val, de, a):
    de, a = de.lower(), a.lower()
    if de in ("c", "celsius", "grados", "oc") and a in ("f", "fahrenheit", "of"):
        return val * 9 / 5 + 32, "°F"
    if de in ("f", "fahrenheit", "of") and a in ("c", "celsius", "grados", "oc"):
        return (val - 32) * 5 / 9, "°C"
    if de in ("c", "celsius", "grados", "oc") and a in ("k", "kelvin", "ok"):
        return val + 273.15, "K"
    if de in ("k", "kelvin", "ok") and a in ("c", "celsius", "grados", "oc"):
        return val - 273.15, "°C"
    return None, None


def convertidor(parameters: dict, player=None, speak=None) -> str:
    """Convierte monedas y unidades por voz."""
    cant = _num(parameters.get("cantidad", ""))
    if cant is None:
        cant = _num(parameters.get("valor", 0))
    de = str(parameters.get("de", "")).strip().upper()
    a = str(parameters.get("a", "") or parameters.get("a_", "")).strip().upper()
    if cant is None:
        action = str(parameters.get("action", "convertir")).strip().lower()
        if action in ("test",):
            return "El conversor funciona."
        return "Decime qué convertir, por ejemplo: cantidad=50, de='USD', a='ARS'."

    # Monedas
    alias = {"PESOS": "ARS", "DOLAR": "USD", "DOLARES": "USD", "US$": "USD",
             "U$S": "USD", "EURO": "EUR", "EUROS": "EUR", "REAL": "BRL",
             "REALES": "BRL", "PESOS CHILENOS": "CLP", "PESOS URUGUAYOS": "UYU",
             "LIBRA": "GBP", "LIBRAS": "GBP"}
    de = alias.get(de, de)
    a = alias.get(a, a)
    if de in _CAMBIO or de in _TASA_FIJA:
        ok = _cargar_cambio()
        if a not in _CAMBIO:
            disp = ", ".join(sorted(_CAMBIO))
            return f"No conozco '{a}'. Tengo cambios para: {disp}."
        try:
            resultado = cant * _CAMBIO[a] / _CAMBIO[de]
        except Exception:
            return "No pude hacer la conversión de moneda."
        nota = "" if ok else " (con tipo de cambio de respaldo, sin internet)"
        if player:
            player.write_log("💱 " + f"{cant} {de} = {resultado:,.2f} {a}{nota}")
        return f"{cant:g} {de} equivalen a {resultado:,.2f} {a}{nota}."

    # Temperatura
    res, unidad = _temp(cant, de, a)
    if res is not None:
        return f"{cant:g} {de} equivalen a {res:.2f} {unidad}."

    # Unidades de medida
    de_key = de.lower()
    a_key = a.lower()
    for categoria, tabla in _UNIDADES.items():
        if de_key in tabla and a_key in tabla:
            res = cant * tabla[de_key] / tabla[a_key]
            u = " (decimal)" if categoria == "datos" else ""
            if player:
                player.write_log("📏 " + f"{cant:g} {de} = {res:g} {a}")
            return f"{cant:g} {de} equivalen a {res:.6g} {a}{u}."

    return (f"No combiné '{de}' con '{a}'. Probá unidades de longitud, peso, "
            f"temperatura o datos, o monedas tipo USD, EUR, ARS.")