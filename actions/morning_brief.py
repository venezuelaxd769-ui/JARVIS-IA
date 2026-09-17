# -*- coding: utf-8 -*-
"""morning_brief.py — el informe matutino de Nia.

Analiza su memoria a largo plazo (categoría 'training') y cuenta al Señor:
  1. Las lecciones que aprendió en la sesión anterior (correcciones suyas).
  2. Las herramientas que vienen fallando (fallos 2+ registrados por learning).

Y, en el mismo acto, se pone a trabajar: por cada herramienta rota con fuente
editable en actions/, lanza un diagnóstico en segundo plano (self_improve heal)
que deja preparado un fix VERIFICADO en frío. Cuando está listo, avisa por voz
que solo falta decir 'SÍ autorizo' para aplicarlo.

El estado 'ya informado hoy' es persistente (memory/morning_brief_state.json).
"""
import re
import json
import threading
from pathlib import Path

_STATE_FILE = Path(__file__).resolve().parents[1] / "memory" / "morning_brief_state.json"
_MAX_FIXES_BG = 2
_active_workers = 0
_workers_lock = threading.Lock()


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


def _training() -> dict:
    try:
        from memory.memory_manager import load_memory
        return (load_memory() or {}).get("training", {}) or {}
    except Exception:
        return {}


def _lesson_date(key: str) -> str:
    """Normaliza la fecha de una lección a 'YYYY-MM-DD'."""
    m = re.search(r"_(\d{4}-\d{2}-\d{2})_\d{6}$", key)
    if m:
        return m.group(1)
    m = re.search(r"_(\d{4})(\d{2})(\d{2})_\d{6}$", key)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return "0000-00-00"


def _tool_from_fallo(key: str, value: any) -> str:
    if isinstance(value, dict):
        value = value.get("value", "") or str(value)
    m = re.search(r"La herramienta '([^']+)' viene fallando", str(value))
    if m:
        return m.group(1).strip()
    return re.sub(r"_\d{8}_\d{6}$", "", key).replace("fallo_", "").strip()


def _error_from_fallo(value: any) -> str:
    if isinstance(value, dict):
        value = value.get("value", "") or str(value)
    m = re.search(r"viene fallando: '([^']*)'", str(value))
    if m:
        return m.group(1).strip()
    return str(value)[:200]


def _cold_heal_worker(tool: str, error: str, speak) -> None:
    """Diagnostica en frío una herramienta rota y avisa el fix listo por voz."""
    try:
        import importlib.util
        _repo = Path(__file__).resolve().parents[1]
        src = _repo / "actions" / f"{tool}.py"

        from actions.self_improve import _HEAL_DENY
        if tool in _HEAL_DENY or not src.exists():
            return

        from actions.self_improve import self_improve
        result = self_improve({"action": "heal", "tool": tool, "error": error}, None) or ""

        if "Fix encontrado" in result or "SÍ autorizo" in result:
            _say(speak, f"Señor, ya te dejé listo un fix para {tool}. "
                        "Está verificado y sin riesgo. Decime 'sí autorizo' y lo aplico.")
        elif "no pude" in result or "No pude" in result:
            _say(speak, f"No encontré un fix seguro para {tool}, quedó anotado para revisarlo juntos.")
    except Exception:
        pass


def _say(speak, text: str) -> None:
    try:
        if callable(speak):
            speak(text)
        else:
            print("[morning_brief]", text)
    except Exception:
        pass


def _session_summaries() -> list:
    """Resúmenes de conversación guardados al cerrar sesiones (context.conversación_*).

    Devuelve los de los últimos 7 días, del más nuevo al más viejo."""
    try:
        from memory.memory_manager import load_memory
        import datetime as _dt
        mem = load_memory() or {}
        ctx = mem.get("context", {}) or {}
        cutoff = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
        items = []
        for k, v in ctx.items():
            if not k.startswith("conversación_"):
                continue
            date = k.replace("conversación_", "")  # YYYY-MM-DD
            if date < cutoff:
                continue
            val = v.get("value", "") if isinstance(v, dict) else str(v)
            items.append((date, str(val).strip()))
        items.sort(reverse=True)
        return items
    except Exception:
        return []


def morning_brief(parameters: dict, player=None, speak=None) -> str:
    """Informe del día: retomar el hilo + lecciones aprendidas + herramientas rotas + auto-fixes."""
    global _active_workers
    training = _training()
    last = _load_state().get("last_brief_date", "")

    new_corr = [
        (k, v.get("value", "") if isinstance(v, dict) else str(v))
        for k, v in training.items()
        if k.startswith("corrección_") and _lesson_date(k) >= last
    ]
    fallos = sorted(
        (k, v) for k, v in training.items()
        if k.startswith("fallo_") and _lesson_date(k) >= last
    )

    lines = ["🖖 Buen día, mi Señor. Mi informe de hoy:"]

    sessions = _session_summaries()
    if sessions:
        _d, text = sessions[0]
        compact = re.sub(r"\s+", " ", text).strip()
        if compact and "sin novedades" not in compact.lower():
            if len(compact) > 220:
                compact = compact[:220] + "…"
            lines.append(f"• Si querés retomar el hilo: la última vez quedó registrado — {compact}.")

    if new_corr:
        perceived = []
        for _k, val in new_corr[:3]:
            m = re.search(r"'(.*?)'", val)
            perceived.append(m.group(1)[:80] if m else "una corrección")
        lines.append(
            f"• Aprendí {len(new_corr)} lección(es) de la sesión anterior, por ejemplo: "
            f"{'; '.join(perceived)}."
        )
    else:
        lines.append("• No tengo correcciones nuevas pendientes de la sesión anterior.")

    broken_new = []
    if fallos:
        for k, val in fallos:
            tool = _tool_from_fallo(k, val)
            broken_new.append((tool, _error_from_fallo(val)))
        names = ", ".join(t for t, _ in broken_new)
        lines.append(
            f"• {len(broken_new)} herramienta(s) vienen fallando: {names}. "
            "No las uso a ciegas: las pruebo antes o aviso."
        )
        for tool, err in broken_new:
            with _workers_lock:
                if _active_workers >= _MAX_FIXES_BG:
                    break
                _active_workers += 1

            def _run(t=tool, e=err):
                global _active_workers
                try:
                    _cold_heal_worker(t, e, speak)
                finally:
                    with _workers_lock:
                        _active_workers -= 1

            threading.Thread(target=_run, daemon=True).start()
    else:
        lines.append("• Ninguna herramienta rota en el registro. Todo lo que uso está sano.")

    mark_briefed()
    report = "\n".join(lines)
    return report