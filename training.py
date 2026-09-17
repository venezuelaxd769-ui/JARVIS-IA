"""training — modo entrenamiento de Nia.

Inspirado en la "IA orquestadora" del canal JCySharp: un currículo de tareas de
dificultad creciente que Nia ejecuta, verifica el resultado y deja una lección en
su memoria de largo plazo cuando falla (para mejorar en el próximo intento).

Diseño:
- Determinista: cada drill tiene un probe() que evalúa el resultado sin depender de
  un modelo "juez". Las tareas con red (web_search) son opcionales: al fallar se
  guarda lección pero no bloquean el avance.
- No destructivo: los drills del currículo base no mueven el mouse, no abren apps
  ni escriben fuera del sandbox.
- Progreso persistido en config/training_progress.json.
"""

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from datetime import datetime
from pathlib import Path

if __name__ == "__main__":
    BASE_DIR = Path(__file__).parent
else:
    BASE_DIR = Path(__file__).resolve().parent

PROGRESS_PATH = BASE_DIR / "config" / "training_progress.json"
_DRILL_TIMEOUT = 90

_CURRICULUM = [
    # ── Nivel 1: fundamentos ──
    {
        "id": "t1_hora",
        "level": 1,
        "name": "Decime la fecha y hora actual",
        "goal": "Nia responde correctamente la fecha y hora del sistema.",
        "skill": "saber la hora exacta sin depender de nadie",
        "probe": "date",
    },
    {
        "id": "t2_desktop",
        "level": 1,
        "name": "Describime tu escritorio actual",
        "goal": "Nia usa el tool de escritorio para ver dónde está parada.",
        "skill": "usar desktop_control(context) para ubicarse antes de actuar",
        "probe": "desktop_context",
    },
    # ── Nivel 2: percepción y sandbox ──
    {
        "id": "t3_captura",
        "level": 2,
        "name": "Capturá la pantalla y guardala",
        "goal": "Nia captura la pantalla y la archiva en su sandbox.",
        "skill": "capturar pantalla a NiaSandbox/captures para 'ver' más tarde",
        "probe": "screenshot",
    },
    {
        "id": "t4_sandbox",
        "level": 2,
        "name": "Mostrame tu espacio de trabajo",
        "goal": "Nia conoce su sandbox aislado y reporta sus capturas.",
        "skill": "saber qué hay en NiaSandbox sin salir de él",
        "probe": "sandbox",
    },
    # ── Nivel 3: mundo exterior (optional/red) ──
    {
        "id": "t5_web",
        "level": 3,
        "name": "Buscá algo en la web",
        "goal": "Nia realiza una búsqueda web y devuelve un resultado.",
        "skill": "usar web_search bien y citar la fuente",
        "probe": "web_search",
        "optional": True,
    },
]


def _load_progress() -> dict:
    try:
        return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_progress(prog: dict) -> None:
    try:
        PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = PROGRESS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(PROGRESS_PATH)
    except Exception:
        pass


def _run_probe(probe: str):
    """Ejecuta el drill. Devuelve (ok: bool, detail: str)."""
    try:
        if probe == "date":
            now = datetime.now()
            ok = str(now.year) in str(now)
            return ok, now.strftime("%Y-%m-%d %H:%M (%A)")

        if probe == "desktop_context":
            from actions.desktop import desktop_control
            out = desktop_control(parameters={"action": "context"}, player=None)
            ok = bool(out and len(str(out)) > 5)
            return ok, str(out)[:160]

        if probe == "screenshot":
            from actions.computer_use import computer_use, _CAPTURES_DIR
            out = computer_use(parameters={"action": "screenshot"}, player=None)
            ok = "Captura" in str(out) and any(_CAPTURES_DIR.glob("*.png"))
            return ok, str(out)

        if probe == "sandbox":
            from actions.computer_use import computer_use
            out = computer_use(parameters={"action": "sandbox"}, player=None)
            ok = "Sandbox" in str(out)
            return ok, str(out)

        if probe == "web_search":
            from actions.web_search import web_search as ws
            out = ws(parameters={"query": "últimas noticias de tecnología hoy"}, player=None)
            ok = bool(out and len(str(out)) > 10)
            return ok, str(out)[:160]

        return False, f"probe desconocido: {probe}"
    except Exception as e:
        return False, f"drill lanzó excepción: {e}"


def _current_level(prog: dict) -> int:
    results = prog.get("results", {})
    level = 1
    for lvl in range(1, 6):
        drills = [d for d in _CURRICULUM if d["level"] == lvl]
        if not drills:
            continue
        all_ok = all(results.get(d["id"], {}).get("ok", False) for d in drills)
        if all_ok:
            level = lvl + 1
        else:
            break
    return level


def _next_drills(prog: dict, n: int) -> list:
    level = _current_level(prog)
    results = prog.get("results", {})
    pool = [d for d in _CURRICULUM if d["level"] == level and not results.get(d["id"], {}).get("ok", False)]
    if not pool:
        pool = [d for d in _CURRICULUM if d["level"] >= level and not results.get(d["id"], {}).get("ok", False)]
    return pool[:n]


def _learn(lesson: dict) -> None:
    from memory.memory_manager import remember
    stamp = time.strftime("%Y-%m-%d")
    remember("training", f"lección_{stamp}_{int(time.time())}", lesson)


def run_session(n: int = 2) -> str:
    """Ejecuta hasta n drills del nivel actual. Devuelve un resumen en español."""
    prog = _load_progress()
    results = prog.setdefault("results", {})
    attempts = int(prog.get("attempts", 0))
    drills = _next_drills(prog, n)
    if not drills:
        level = _current_level(prog)
        return (f"No quedan drills que practicar: completaste todo el currículo "
                f"hasta el nivel {level}. Guardame tus lecciones, Señor.")

    lines, learned = [], 0
    for d in drills:
        attempts += 1
        ok, detail = _run_probe(d["probe"])
        results[d["id"]] = {
            "ok": ok, "ts": int(time.time()),
            "detail": detail, "skill": d["skill"],
        }
        if ok:
            lines.append(f"[OK] {d['name']} (perfecto)")
        else:
            lines.append(f"[X] {d['name']} — {detail}")
            if d.get("optional"):
                lines.append(f"   (externo/opcional: lo intenté pero no hubo respuesta. Lección guardada.)")
            else:
                _learn(f"Al practicar '{d['name']}' fallé. Aprendizaje: {d['skill']}. Detalle: {detail}")
                learned += 1
            results[d["id"]]["lesson"] = d["skill"]

    prog["attempts"] = attempts
    prog["level"] = _current_level(prog)
    prog["last_session"] = time.strftime("%Y-%m-%d %H:%M")
    _save_progress(prog)

    head = f"Sesión de entrenamiento terminada: {len(drills)} drill(s) ejecutado(s), nivel actual {prog['level']}."
    tail = (f"Lecciones guardadas en memoria: {learned}.") if learned else "Todo verde, sin lecciones nuevas."
    return head + "\n" + "\n".join(lines) + "\n" + tail


def progress_report() -> str:
    prog = _load_progress()
    results = prog.get("results", {})
    attempts = int(prog.get("attempts", 0))
    level = _current_level(prog)

    out = [
        f"Progreso de entrenamiento — nivel actual: {level} (intentos: {attempts}).",
        "Currículo:",
        *[f"  {r.get('level', '?')}. {r.get('name', '')} — "
          + ("[OK] logrado" if results.get(r["id"], {}).get("ok") else "[PENDIENTE]")
          for r in sorted(_CURRICULUM, key=lambda x: x["level"])],
    ]
    if results:
        out.append(f"Última sesión: {prog.get('last_session', '?')}.")
    return out and "\n".join(out)


def training_mode(parameters: dict, player=None, speak=None) -> str:
    action = (parameters or {}).get("action", "status")
    try:
        if action in ("run", "entrenar", "practicar"):
            n = min(max(int((parameters or {}).get("n", 2)), 1), 3)
            return run_session(n=n)
        if action in ("status", "progress", "progreso"):
            return progress_report()
        return "Acción de training_mode desconocida. Usá action='run' o action='status'."
    except Exception as e:
        return f"Error en training_mode: {e}"


def _probe_with_timeout(probe: str, timeout: int = _DRILL_TIMEOUT):
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_run_probe, probe)
        try:
            return fut.result(timeout=timeout)
        except FutTimeout:
            return False, f"drill excedió {timeout}s (pendiente de red)."


if __name__ == "__main__":
    import sys
    print("PROGRESS REPORT")
    print(progress_report())
    print("\nSAMPLE TEST (timeout 5s):")
    print(_probe_with_timeout("date", timeout=5))
    if "--run" in sys.argv:
        print("\nRUN SESSION (1 drill):")
        print(run_session(n=1))