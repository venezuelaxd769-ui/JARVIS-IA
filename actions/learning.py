# -*- coding: utf-8 -*-
"""learning.py — Nia aprende.

Dos mecanismos autocontenidos:
  1. Correcciones del Señor: si el texto cruza con un patrón de corrección y hay
     contexto (habló o usó tools), guarda la lección en memoria a largo plazo.
  2. Tools que fallan: si una misma herramienta falla 2+ veces en una racha,
     guarda la lección (testearla antes / avisar al Señor).

Las lecciones viven bajo la categoría 'training' de long_term.json, que se
inyecta sola al prompt — Nia las "recuerda" entre reconexiones y reinicios.
"""

import re
import threading
import time
from datetime import datetime

try:
    from memory.memory_manager import load_memory, remember
except Exception:
    load_memory, remember = None, None  # pragma: no cover


_TRIGGERS = (
    "no hagas", "no uses", "no abras", "no toques", "no borres",
    "no sigas", "no repitas", "no lo hagas", "no se hace así",
    "así no", "no así", "no es así", "no era así",
    "cambialo", "cambialo a", "cambia eso", "cambia eso a",
    "te equivocaste", "te equivocás", "está mal", "eso está mal",
    "no era eso", "no es eso", "basta", "frená", "no vuelvas",
    "no me gusta", "no me gustó", "no digas eso", "no digas",
)

_IGNORE_TOOLS = {"shutdown_jarvis", "restart_jarvis", "update_jarvis"}

_MAX_LESSONS_DAY = 6
_BURST_ELAPSED_MIN = 60          # segundos mínimos entre 2 fallos para contar racha
_BURST_EXPIRE = 12 * 3600


class _Learner:
    def __init__(self):
        self._failures = {}
        self._lock = threading.Lock()

    def note_failure(self, tool: str, err: str) -> None:
        """Registra un fallo de una herramienta; al 2º fallo de la racha, guarda lección."""
        if remember is None or tool in _IGNORE_TOOLS:
            return
        now = time.time()
        with self._lock:
            rec = self._failures.get(tool)
            if rec is None:
                rec = {"count": 1, "since": now, "saved": False}
                self._failures[tool] = rec
            else:
                rec["count"] += 1
                rec["err"] = str(err)[:160]
            if now - rec["since"] > _BURST_EXPIRE:
                rec.clear()
                rec.update({"count": 1, "since": now, "saved": False})
                return
            if rec["count"] >= 2 and (now - rec["since"]) >= _BURST_ELAPSED_MIN and not rec["saved"]:
                rec["saved"] = True
                self._save_lesson(
                    f"fallo_{tool[:30]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    f"La herramienta '{tool}' viene fallando: '{rec['err']}'. "
                    "No apostar a ciegas en ella: probarla primero (test_tool) o avisarle al Señor que no anduvo."
                )

    def tool_succeeded(self, tool: str) -> None:
        """Un éxito reinicia la racha de fallos de la herramienta."""
        with self._lock:
            self._failures.pop(tool, None)

    def learn_from_correction(self, user: str, assistant: str, had_tool: bool) -> bool:
        """Guarda una lección si el texto del Señor parece una corrección."""
        if remember is None:
            return False
        try:
            user = (user or "").strip()
            if len(user) < 6 or len(user) > 240:
                return False
            low = user.lower()
            if not any(tr in low for tr in _TRIGGERS):
                return False
            if not (had_tool or (assistant and assistant.strip())):
                return False

            training = (load_memory() or {}).get("training", {}) or {}
            today = datetime.now().strftime("%Y-%m-%d")
            today_count = sum(1 for k in training if k.startswith(f"corrección_{today}"))
            if today_count >= _MAX_LESSONS_DAY:
                return False

            probe = user[:40]
            for v in training.values():
                val = v.get("value", "") if isinstance(v, dict) else str(v)
                if probe in val:
                    return False

            ctx = (assistant or "").strip()
            ctx_part = f"y dijo: '{ctx[:140]}'" if ctx else ""
            accion = "usaba herramientas" if had_tool else "respondiendo"
            value = (
                f"Corrección del Señor: '{user[:160]}' mientras Nia estaba {accion} {ctx_part}. "
                "REGLA: no repetir este comportamiento sin preguntar antes."
            )
            self._save_lesson(f"corrección_{today}_{datetime.now().strftime('%H%M%S')}", value)
            return True
        except Exception:
            return False

    def _save_lesson(self, key: str, value: str) -> None:
        if remember is None:
            return
        try:
            remember("training", key, value)
            print(f"[Learning] 🧠 Guardada lección '{key}'")
        except Exception as e:
            print(f"[Learning] No se pudo guardar lección: {e}")


learn = _Learner()