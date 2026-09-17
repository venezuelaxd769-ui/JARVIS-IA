# -*- coding: utf-8 -*-
"""alarma.py — Despertador y alarmas con sonido real (Windows).

Reproduce un WAV del sistema con winsound aunque Nia esté en silencio,
una sola vez o diaria, con opción de posponer (dormir).
"""
import json
import os
import threading
import time
import winsound
from datetime import datetime, timedelta

_MEM = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory", "alarmas.json")
_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SONIDOS = [
    r"C:\Windows\Media\Alarm08.wav",
    r"C:\Windows\Media\Alarm10.wav",
    r"C:\Windows\Media\Ring08.wav",
    r"C:\Windows\Media\Windows Background.wav",
    r"C:\Windows\Media\chime.wav",
]
_DEFAULT = next((s for s in _SONIDOS if os.path.exists(s)), None)
_STOP = {}
_LOCK = threading.Lock()


def _load():
    try:
        with open(_MEM, "r", encoding="utf-8") as f:
            d = json.load(f)
            return d.get("alarmas", [])
    except Exception:
        return []


def _save(alarmas):
    os.makedirs(os.path.dirname(_MEM), exist_ok=True)
    with open(_MEM, "w", encoding="utf-8") as f:
        json.dump({"alarmas": alarmas}, f, ensure_ascii=False, indent=2)


def _proximo(hhmm, repetir=False):
    h, m = hhmm.split(":")
    now = datetime.now()
    t = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t


def _suena_bucle(bucle=False):
    if not _DEFAULT:
        return False
    while not _STOP.get("_current", threading.Event()).is_set():
        flags = winsound.SND_FILENAME | winsound.SND_ASYNC
        if bucle:
            flags |= winsound.SND_LOOP
        winsound.PlaySound(_DEFAULT, flags)
        if not bucle:
            break
        time.sleep(0.5)
    return True


def _runner(aly):
    stop = _STOP.get(aly["id"])
    while not stop.is_set():
        target = _proximo(aly["hora"], aly.get("repetir") == "diaria")
        wait = (target - datetime.now()).total_seconds()
        if stop.wait(wait):
            return
        _STOP["_current"] = stop
        if aly.get("repetir") == "diaria":
            for _ in range(0, 100):
                if stop.is_set():
                    break
                _suena_bucle(True)
                time.sleep(1)
        else:
            _suena_bucle(False)
            break
    _STOP.pop(aly["id"], None)


def _validar_hora(hhmm):
    try:
        h, m = hhmm.split(":")
        h, m = int(h), int(m)
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ValueError
        return f"{h:02d}:{m:02d}"
    except Exception:
        return None


def _normalizar_hora(valor):
    valor = (valor or "").strip().lower()
    if not valor:
        return None
    valor = valor.replace(".", ":").replace(";", ":")
    if ":" not in valor and valor.isdigit() and len(valor) <= 4:
        if len(valor) == 3:
            valor = f"{valor[0]}:{valor[1:]}"
        elif len(valor) == 4:
            valor = f"{valor[:2]}:{valor[2:]}"
        else:
            valor = f"{int(valor):02d}:00"
    return _validar_hora(valor)


def _parar(id_alarma, todas=False):
    ids = [a["id"] for a in _load()] if todas else [id_alarma]
    stopped = False
    for i in ids:
        ev = _STOP.get(i)
        if ev:
            ev.set()
            stopped = True
    try:
        winsound.PlaySound(None, winsound.SND_PURGE) if stopped else None
    except Exception:
        pass
    return stopped


def alarma(parameters: dict, player=None, speak=None) -> str:
    """Despertador/alarmas con sonido. Acciones: poner(hora), dormir(minutos),
    parar(id), quitar(id), lista. opcional repetir='diaria'."""
    action = str(parameters.get("action", "lista")).strip().lower()
    hora_raw = parameters.get("hora", "") or parameters.get("tiempo", "")
    hora = _normalizar_hora(hora_raw)
    repetir = str(parameters.get("repetir", "")).strip().lower()
    id_alarma = str(parameters.get("id", "")).strip()
    minutos = parameters.get("minutos")
    if player:
        player.write_log(f"⏰ alarma: {action} {hora}")

    if action in ("poner", "set", "apagar_al_dormir"):
        if not hora:
            return "Decime la hora (hora='07:30'). Opcional: repetir='diaria'."
        alarmas = _load()
        nid = f"a{int(time.time())}"
        aly = {"id": nid, "hora": hora,
               "repetir": "diaria" if repetir in ("diaria", "diario", "todos_los_dias") else "",
               "activa": True}
        alarmas.append(aly)
        _save(alarmas)
        ev = threading.Event()
        _STOP[nid] = ev
        threading.Thread(target=_runner, args=(aly,), daemon=True).start()
        obs = f" todos los días" if aly["repetir"] else ""
        return (f"Listo, alarma puesta a las {hora}{obs}. Va a sonar con "
                f"{os.path.basename(_DEFAULT) if _DEFAULT else 'el sonido por defecto'}.")

    if action in ("dormir", "snooze", "posponer"):
        mins = int(minutos) if str(minutos).isdigit() else 5
        ids = [a["id"] for a in _load() if a.get("activa")]
        _parar("", todas=True)
        if not ids:
            for i in list(_STOP):
                _parar(i)
        nid = f"a{int(time.time())}"
        now = datetime.now() + timedelta(minutes=mins)
        aly = {"id": nid, "hora": f"{now.hour:02d}:{now.minute:02d}",
               "repetir": "", "activa": True}
        alarmas = [a for a in _load() if not a.get("activa") or a["id"] in ids]
        if ids:
            alarmas = [a for a in alarmas if a["id"] not in ids]
        alarmas.append(aly)
        _save(alarmas)
        ev = threading.Event()
        _STOP[nid] = ev
        threading.Thread(target=_runner, args=(aly,), daemon=True).start()
        return f"Empiezo a dormir {mins} minutos; te vuelvo a avisar a las {aly['hora']}."

    if action in ("parar", "stop", "callar", "apagar"):
        _parar(id_alarma or "_current", todas=not id_alarma)
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        return "Dejé de sonar. 😴"

    if action in ("quitar", "remove", "borrar"):
        if not id_alarma:
            _parar("", todas=True)
            _save([])
            return "Borré todas las alarmas."
        _parar(id_alarma)
        _save([a for a in _load() if a["id"] != id_alarma])
        return f"Alarma {id_alarma} eliminada."

    if action in ("lista", "list", "cuales"):
        alarmas = _load()
        if not alarmas:
            return "No hay alarmas puestas."
        return "⏰ Alarmas:\n" + "\n".join(
            f"   • {a['id']} — {a['hora']}" + (" (diaria)" if a.get("repetir") else "")
            for a in alarmas)

    return "Acciones: poner(hora) | dormir(minutos) | parar | quitar(id) | lista."


if __name__ == "__main__":
    import sys
    p = {"action": sys.argv[1] if len(sys.argv) > 1 else "lista"}
    if len(sys.argv) > 2:
        p["hora"] = sys.argv[2]
    print(alarma(p))