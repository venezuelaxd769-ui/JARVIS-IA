"""Runner de subagentes: ejecuta tareas delegadas en segundo plano.

Nia entrega la tarea con `delegate_to_subagent`, el runner la ejecuta en un
hilo aparte (sin bloquear la conversación) y, al terminar, Nia "habla" el
reporte con su propia voz (`speak`).
"""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from agent.subagents import get_subagent, pick_best

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

REPORT_MAX_CHARS = 1200


class SubAgentRunner:
    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── API pública ──────────────────────────────────────────────────────────

    def submit(self, subagent_name: str, goal: str, context: str = "",
               player=None, speak=None) -> str:
        if not subagent_name or subagent_name == "auto":
            subagent_name = pick_best(goal) or "researcher"
        task_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._tasks[task_id] = {
                "id": task_id,
                "subagent": subagent_name,
                "goal": goal,
                "status": "running",
                "result": None,
                "started": datetime.now().strftime("%H:%M:%S"),
                "finished": None,
            }
        threading.Thread(
            target=self._work,
            args=(task_id, subagent_name, goal, context, player, speak),
            daemon=True,
        ).start()
        return task_id

    def status(self, task_id: str) -> dict | None:
        with self._lock:
            t = self._tasks.get(task_id)
            return dict(t) if t else None

    def result(self, task_id: str) -> str | None:
        with self._lock:
            t = self._tasks.get(task_id)
            return t.get("result") if t else None

    def active(self) -> list[str]:
        with self._lock:
            return [k for k, v in self._tasks.items()
                    if v["status"] == "running"]

    # ── Interno ──────────────────────────────────────────────────────────────

    def _work(self, task_id, subagent_name, goal, context, player, speak):
        started = time.time()
        try:
            agent = get_subagent(subagent_name, player=player, speak=speak)
            if agent is None:
                result = (f"No existe o está deshabilitado el subagente "
                          f"'{subagent_name}'.")
            else:
                result = agent.run(goal, context)
        except Exception as e:
            result = f"[{subagent_name}] Error: {e}"
        duration = int(time.time() - started)

        with self._lock:
            self._tasks[task_id]["status"] = "done"
            self._tasks[task_id]["result"] = result
            self._tasks[task_id]["finished"] = datetime.now().strftime("%H:%M:%S")
            self._tasks[task_id]["duration"] = f"{duration}s"

        self._persist(task_id, subagent_name, result)
        self._notify(player, speak, task_id, subagent_name, result, duration)

    def _persist(self, task_id, subagent_name, result):
        try:
            fname = LOG_DIR / f"subagent_{subagent_name}_{task_id}.md"
            fname.write_text(
                f"# Reporte de subagente: {subagent_name}\n\n{result}\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    def _notify(self, player, speak, task_id, subagent_name, result, duration):
        try:
            if player is not None and hasattr(player, "write_log"):
                player.write_log(
                    f"SUBAGENTE [{subagent_name}] ({duration}s): "
                    f"{result[:300]}")
        except Exception:
            pass
        if speak is not None:
            try:
                speak(f"He terminado la tarea delegada a {subagent_name}.")
                speak(result[:REPORT_MAX_CHARS])
            except Exception:
                pass


_instance = SubAgentRunner()


def get_runner() -> SubAgentRunner:
    return _instance
