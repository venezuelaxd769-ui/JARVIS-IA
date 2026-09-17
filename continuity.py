"""Continuidad entre reinicios: Nia sabe cuánto tiempo estuvo apagada.

Un hilo daemon escribe a disco un heartbeat cada N segundos. Al arrancar,
build_continuity_note() compara la última marca con el tiempo actual y devuelve
una nota para el system prompt (solo el primer arranque), para que Nia pueda
mencionar de forma natural la ausencia cuando el usuario la salude.

La escritura es atómica (tmp + replace): si la PC se apaga de golpe, el archivo
nunca queda corrupto. La nota opcional (save_note/clear_note) permite dejar una
tarea pendiente para retomar en el próximo arranque.
"""

import json
import sys
import threading
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

NIA_STATE_PATH = BASE_DIR / "config" / "nia_state.json"

_MIN_OFFLINE_SECS = 120


def _write_state(state: dict) -> None:
    try:
        NIA_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = NIA_STATE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(NIA_STATE_PATH)
    except Exception:
        pass


def read_state() -> dict:
    try:
        return json.loads(NIA_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_heartbeat() -> None:
    try:
        state = read_state()
        state["last_online_ts"] = int(time.time())
        _write_state(state)
    except Exception:
        pass


def start_heartbeat(interval: int = 60) -> None:
    """Hilo daemon que actualiza el timestamp de actividad.

    La primera escritura espera 'interval' segundos de propósito: así la nota de
    continuidad (leída en el primer arranque) todavía ve el timestamp de la
    ejecución anterior, no el recién escrito.
    """

    def _loop() -> None:
        while True:
            time.sleep(interval)
            write_heartbeat()

    threading.Thread(target=_loop, daemon=True, name="nia-heartbeat").start()


def save_note(text: str) -> None:
    try:
        state = read_state()
        state["note"] = str(text)[:500]
        _write_state(state)
    except Exception:
        pass


def clear_note() -> None:
    try:
        state = read_state()
        state.pop("note", None)
        _write_state(state)
    except Exception:
        pass


def _fmt_duration(secs: int) -> str:
    if secs < 60:
        return "menos de un minuto"
    minutes = secs // 60
    if minutes < 60:
        return "1 minuto" if minutes == 1 else f"{minutes} minutos"
    hours = minutes // 60
    minutes %= 60
    label_h = "hora" if hours == 1 else "horas"
    if hours < 24:
        if minutes == 0:
            return f"{hours} {label_h}"
        label_m = "minuto" if minutes == 1 else "minutos"
        return f"{hours} {label_h} y {minutes} {label_m}"
    days = hours // 24
    hours %= 24
    label_d = "día" if days == 1 else "días"
    if hours == 0:
        return f"{days} {label_d}"
    return f"{days} {label_d} y {hours} {label_h}"


def build_continuity_note() -> str:
    """Nota para el system prompt del primer arranque tras una ausencia.

    La parte de tiempo solo entra si la ausencia supera el umbral; la nota
    pendiente (si existe) siempre entra, sin importar cuánto haya durado el apagón.
    """
    try:
        state = read_state()
        ts = state.get("last_online_ts")
        note = (state.get("note") or "").strip()

        lines = []
        if ts and int(time.time()) - int(ts) >= _MIN_OFFLINE_SECS:
            offline_s = max(0, int(time.time()) - int(ts))
            duration = _fmt_duration(offline_s)
            lines.append(
                "[CONTINUIDAD — solo para tu voz]\n"
                f"Estuviste sin actividad por {duration}. Si el Señor te saluda o "
                f"retoma la conversación, mencioná esa ausencia de forma natural y "
                f"breve (ej: 'buenos días, Señor, estuve fuera {duration}'), sin "
                f"dramatizar ni inventar qué pasó mientras tanto."
            )
        elif note:
            lines.append(
                "[CONTINUIDAD — solo para tu voz]\n"
                "Retomás la conversación tras un reinicio breve."
            )
        if note:
            lines.append(f"Dejaste una nota pendiente antes de apagarte: {note}")
        return ("\n".join(lines) + "\n") if lines else ""
    except Exception:
        return ""