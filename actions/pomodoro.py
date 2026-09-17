# -*- coding: utf-8 -*-
"""pomodoro.py — Ciclos trabajo/descanso con avisos hablados.

Arranca un hilo daemon que alterna sesiones de trabajo y descanso, avisa por
voz (player.speak) y con beeps de Windows al cambiar de fase. No toca la voz
de Nia; es un aviso adicional como el timer.
"""
import os
import threading
import time
from datetime import datetime

_estado = {"activo": False, "fase": "quieto", "fin": None, "ciclo": 0,
           "trabajo": 25, "descanso": 5, "bloqueado": threading.Lock()}
_stop = threading.Event()


def _beep():
    if os.name == "nt":
        try:
            import winsound
            winsound.Beep(880, 250)
            winsound.Beep(660, 250)
        except Exception:
            pass


def _avisar(player_actual, msg):
    try:
        _beep()
        if player_actual is not None and hasattr(player_actual, "speak"):
            player_actual.speak(msg)
    except Exception:
        pass


def _loop(trabajo, descanso, player_actual):
    ciclo = 0
    while not _stop.is_set():
        ciclo += 1
        with _estado["bloqueado"]:
            _estado.update(fase="trabajo", ciclo=ciclo,
                           fin=time.time() + trabajo * 60)
        _avisar(player_actual, f"¡Pomodoro {ciclo} empezado! {trabajo} minutos de foco.")
        _stop.wait(trabajo * 60)
        if _stop.is_set():
            break
        with _estado["bloqueado"]:
            _estado.update(fase="descanso", fin=time.time() + descanso * 60)
        _avisar(player_actual, "¡Descanso! Pará un poco y estirá el cuerpo.")
        _stop.wait(descanso * 60)
    with _estado["bloqueado"]:
        _estado["activo"] = False
        _estado["fase"] = "quieto"
        _estado["fin"] = None


def _arrancar(trabajo, descanso, player):
    global _stop
    _stop = threading.Event()
    t = threading.Thread(target=_loop, args=(trabajo, descanso, player),
                         daemon=True)
    t.start()
    with _estado["bloqueado"]:
        _estado["activo"] = True
        _estado["trabajo"] = trabajo
        _estado["descanso"] = descanso


def pomodoro(parameters: dict, player=None, speak=None) -> str:
    """Ciclos de trabajo y descanso estilo pomodoro por voz."""
    action = str(parameters.get("action", "estado")).strip().lower()

    if action in ("test",):
        return "El pomodoro funciona."

    if action in ("empezar", "iniciar", "start", "poner"):
        trab = int(parameters.get("trabajo", 25) or 25)
        desc = int(parameters.get("descanso", 5) or 5)
        if not 1 <= trab <= 120 or not 1 <= desc <= 60:
            return "Decime el trabajo entre 1 y 120 minutos y el descanso entre 1 y 60."
        if _estado["activo"]:
            return f"Ya hay un pomodoro activo. Paralo con 'parar' o esperá a que termine."
        _arrancar(trab, desc, player)
        return (f"¡Pomodoro arrancado! {trab} minutos de foco y luego "
                f"{desc} de descanso. Te aviso por voz cuando cambie.")

    if action in ("estado", "cuanto", "falta"):
        with _estado["bloqueado"]:
            act = _estado["activo"]
            fase = _estado["fase"]
            fin = _estado["fin"]
            ciclo = _estado["ciclo"]
        if not act:
            return "No hay pomodoro activo. Decime 'empezar con 25 minutos'."
        falta = max(0, int(fin - time.time()))
        mm, ss = divmod(falta, 60)
        texto = f"{ciclo if fase == 'trabajo' else ciclo - 1}"
        return f"Pomodoro {texto} en {fase}: faltan {mm} minutos {ss} segundos."

    if action in ("parar", "detener", "cancelar", "stop"):
        if not _estado["activo"]:
            return "No hay pomodoro activo."
        _stop.set()
        _avisar(player, "Pomodoro detenido. Buen laburo igual.")
        with _estado["bloqueado"]:
            _estado["activo"] = False
        return "Pomodoro detenido."

    if action in ("agregar_descanso", "descanso"):
        if not _estado["activo"]:
            return "No hay pomodoro activo."
        with _estado["bloqueado"]:
            _estado["fin"] = time.time()
        return "Corté la fase actual: que arranque el descanso."

    return "Acciones: empezar (trabajo minutos, descanso minutos) | estado | parar."