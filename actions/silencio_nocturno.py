# -*- coding: utf-8 -*-
"""silencio_nocturno.py — que Nia no hable en una franja del día.

Config en memory/silencio_nocturno.json: {habilitado, inicio '23:00', fin
'07:00'}. _dentro() se usa desde main._proactive_monitor para frenar las
sugerencias proactivas en la ventana (no bloquea las respuestas cuando el
usuario le habla directo). Soporta franjas que cruzan la medianoche.
"""
import json
import os

_ARCHIVO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "memory", "silencio_nocturno.json")


def _leer():
    try:
        with open(_ARCHIVO, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "habilitado": bool(data.get("habilitado", False)),
            "inicio": str(data.get("inicio", "23:00")),
            "fin": str(data.get("fin", "07:00")),
        }
    except Exception:
        return {"habilitado": False, "inicio": "23:00", "fin": "07:00"}


def _escribir(d):
    try:
        os.makedirs(os.path.dirname(_ARCHIVO), exist_ok=True)
        with open(_ARCHIVO, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise RuntimeError(str(e))


def _min(hhmm):
    try:
        h, m = str(hhmm).strip().split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 23 * 60


def _ahora_min():
    from datetime import datetime
    return datetime.now().hour * 60 + datetime.now().minute


def _dentro():
    """True si la franja de silencio está activa en este momento."""
    cfg = _leer()
    if not cfg["habilitado"]:
        return False
    ahora = _ahora_min()
    ini = _min(cfg["inicio"])
    fin = _min(cfg["fin"])
    if ini <= fin:      # franja normal, ej 01:00-05:00
        return ini <= ahora < fin
    return ahora >= ini or ahora < fin  # cruza medianoche, ej 23:00-07:00


def _fmt(hhmm):
    try:
        h, m = str(hhmm).strip().split(":")
        return f"{int(h):02d}:{int(m):02d}"
    except Exception:
        return "00:00"


def silencio_nocturno(parameters: dict, player=None, speak=None) -> str:
    """Activa o desactiva la franja en la que Nia no habla sola."""
    action = str(parameters.get("action", "estado")).strip().lower()
    cfg = _leer()

    if action in ("test",):
        return "El modo silencio nocturno funciona."

    if action in ("activar", "poner", "encender"):
        inicio = _fmt(parameters.get("inicio", cfg["inicio"]))
        fin = _fmt(parameters.get("fin", cfg["fin"]))
        if _min(inicio) == _min(fin) and inicio != "00:00":
            return "La franja de inicio y fin no puede ser la misma."
        nuevo = {"habilitado": True, "inicio": inicio, "fin": fin}
        try:
            _escribir(nuevo)
        except Exception as e:
            return f"No pude guardar la configuración: {e}."
        if player:
            player.write_log("🌙 Silencio nocturno activado "
                             f"{inicio} → {fin}")
        return (f"Listo. Entre las {inicio} y las {fin} no voy a meter ruido: "
                "te aviso solo si me hablás directo.")

    if action in ("desactivar", "apagar", "quitar"):
        nuevo = dict(cfg, habilitado=False)
        try:
            _escribir(nuevo)
        except Exception as e:
            return f"No pude guardar la configuración: {e}."
        return "Apagué el silencio nocturno: vuelvo a estar atenta en todo momento."

    if action in ("estado", "como"):
        if not cfg["habilitado"]:
            return "El silencio nocturno está apagado: te hablo a cualquier hora."
        ahora_cnt = "de silencio" if _dentro() else "normal"
        return (f"El silencio nocturno está activado de {cfg['inicio']} a "
                f"{cfg['fin']}. Ahora mismo estamos en el período "
                f"{ahora_cnt}.")

    return "Acciones: activar (inicio, fin) | desactivar | estado | test."