# -*- coding: utf-8 -*-
"""morning_brief.py — el informe matutino: AÚN NO IMPLEMENTADA como tool.

Devuelve un aviso honesto para que Nia no presente resultados falsos
al usuario ni invierta tiempo en una herramienta que no existe.

Sí implementa el control de "ya informado hoy" (already_briefed_today /
mark_briefed) con estado persistente, para que el arranque automático
entre 6:00–12:00 no falle al importar la función.
"""
import json
from pathlib import Path

_STATE_FILE = Path(__file__).resolve().parents[1] / "memory" / "morning_brief_state.json"


def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        _STATE_FILE.parent.mkdir(exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as _e:
        print(f"[JARVIS] No se pudo guardar el estado del informe matutino: {_e}")


def already_briefed_today() -> bool:
    import datetime
    state = _load_state()
    return state.get("last_brief_date") == datetime.date.today().isoformat()


def mark_briefed() -> None:
    import datetime
    state = _load_state()
    state["last_brief_date"] = datetime.date.today().isoformat()
    _save_state(state)


def morning_brief(parameters: dict, player=None) -> str:
    return "⚠️ La herramienta 'morning_brief' aún no está implementada en esta versión. " \
        "Avisá al usuario que no está disponible por ahora."
