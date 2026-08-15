# -*- coding: utf-8 -*-
"""accessibility.py — módulo de accesibilidad universal de Nia.

Incluye: task_simplify (descomponer tareas en pasos), emotional
(regulación emocional), routine (rutinas gamificadas con racha),
eye_tracking (control por seguimiento ocular con webcam), micro_movement
(navegación por movimientos de cabeza), speech_config (tolerancia de voz)
y feedback (retroalimentación visual).

Config en config/accessibility_config.json. Las rutinas se guardan en
config/routines.json.
"""

import json
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "accessibility_config.json"
ROUTINES_FILE = BASE_DIR / "config" / "routines.json"

_lock = threading.Lock()
_tracker = {"thread": None, "stop": False, "kind": None, "status": "detenido"}

DEFAULT_CONFIG = {
    "task_simplification_enabled": True,
    "emotional_regulation_enabled": True,
    "routine_gamification_enabled": True,
    "eye_tracking_enabled": False,
    "micro_movement_enabled": False,
    "visual_feedback_enabled": True,
    "high_contrast_mode": False,
    "auto_learn_routines": False,
    "speech_error_threshold": 0.5,
    "font_size_scale": 1.0,
}


def _load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg


def _save_config(cfg: dict) -> None:
    try:
        CONFIG_FILE.write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _load_routines() -> dict:
    try:
        data = json.loads(ROUTINES_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "routines" in data:
            return data
    except Exception:
        pass
    return {"routines": {}, "streaks": {}}


def _save_routines(data: dict) -> None:
    try:
        ROUTINES_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def task_simplify(text: str, format: str = "steps") -> str:
    """Descompone un texto/tarea compleja en pasos simples y accionables."""
    text = (text or "").strip()
    if not text:
        return "Error: no me pasaste ninguna tarea para simplificar."

    import re
    sentences = [s.strip() for s in re.split(r"[.;\n]+", text) if s.strip()]
    if not sentences:
        sentences = [text]

    if format == "summary":
        return ("📌 Resumen: " + " ".join(sentences)[:300])
    if format == "explain":
        return ("🧠 Explicación:\n- " + "\n- ".join(sentences))

    steps = []
    for i, s in enumerate(sentences, 1):
        s = s.rstrip(".").strip()
        if s.lower().startswith(("paso", "step", "primero", "luego", "después", "despues", "finalmente")):
            steps.append(f"{i}. {s}")
        else:
            steps.append(f"{i}. {s[0].upper() + s[1:]}")
    return "✅ Tarea descompuesta en pasos:\n" + "\n".join(steps)


def routine_gamify(parameters: dict) -> str:
    """Gestiona rutinas diarias gamificadas (add/complete/list) con racha."""
    action = str(parameters.get("action", "list")).lower()
    name = str(parameters.get("name", "")).strip()
    data = _load_routines()
    routines = data.setdefault("routines", {})
    streaks = data.setdefault("streaks", {})
    today = _today()

    if action == "add":
        if not name:
            return "Error: necesito un nombre para la rutina."
        routines.setdefault(name, {"created": today, "completed": [], "total": 0})
        _save_routines(data)
        return f"✅ Rutina '{name}' agregada. ¡Empecemos hoy!"

    if action == "complete":
        if name not in routines:
            return f"No encontré la rutina '{name}'. Usá 'agregar rutina <nombre>' primero."
        if today in routines[name]["completed"]:
            return f"🏆 La rutina '{name}' ya está completa hoy. ¡Gran trabajo!"
        routines[name]["completed"].append(today)
        routines[name]["total"] += 1
        streak = streaks.get(name, 0)
        streak = streak + 1 if today not in routines[name]["completed"][:-1] else streak
        streaks[name] = streak
        _save_routines(data)
        return f"🏆 ¡Rutina '{name}' completada! Racha actual: {streak} día(s)."

    if action == "delete":
        if name not in routines:
            return f"No existe la rutina '{name}'."
        del routines[name]
        streaks.pop(name, None)
        _save_routines(data)
        return f"🗑️ Rutina '{name}' eliminada."

    if not routines:
        return "Aún no tenés rutinas. Decime 'agregar rutina <nombre>' para crear una."

    lines = ["📋 Tus rutinas:"]
    for rname, info in sorted(routines.items()):
        done_today = "✅" if today in info["completed"] else "⬜"
        streak = streaks.get(rname, 0)
        lines.append(f"  {done_today} {rname} — {info['total']} hecha(s), racha {streak} día(s)")
    return "\n".join(lines)


def _track_loop(kind: str) -> None:
    """Hilo de seguimiento ocular / micromovimientos con webcam + cv2."""
    import cv2
    try:
        import pyautogui
    except Exception:
        pyautogui = None

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        _tracker["status"] = "error: no se pudo abrir la cámara"
        return
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    screen_w, screen_h = (1920, 1080)
    if pyautogui is not None:
        try:
            screen_w, screen_h = pyautogui.size()
        except Exception:
            pass
    _tracker["status"] = f"activo ({kind})"
    smooth = None
    while not _tracker["stop"]:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.3, 5, minSize=(80, 80))
        if len(faces) > 0 and pyautogui is not None:
            (x, y, w, h) = faces[0]
            cx = x + w / 2
            cy = y + h / 2
            if kind == "micro_movement":
                tx = screen_w * (0.15 + 0.7 * (cx / frame.shape[1]))
                ty = screen_h * (0.15 + 0.7 * (cy / frame.shape[0]))
            else:  # eye_tracking: más sensible, centrado en la parte alta
                tx = screen_w * (cx / frame.shape[1])
                ty = screen_h * (0.25 + 0.6 * (cy / frame.shape[0]))
            if smooth is None:
                smooth = (tx, ty)
            smooth = (smooth[0] + (tx - smooth[0]) * 0.35,
                      smooth[1] + (ty - smooth[1]) * 0.35)
            try:
                pyautogui.moveTo(int(smooth[0]), int(smooth[1]), duration=0.05)
            except Exception:
                pass
        time.sleep(0.03)
    cap.release()
    _tracker["status"] = "detenido"


def eye_tracking(parameters: dict) -> str:
    action = str(parameters.get("action", "status")).lower()
    if action == "start":
        with _lock:
            if _tracker["thread"] and _tracker["thread"].is_alive():
                return "El seguimiento ocular ya está activo."
            _tracker["stop"] = False
            _tracker["kind"] = "eye_tracking"
            _tracker["thread"] = threading.Thread(
                target=_track_loop, args=("eye_tracking",), daemon=True,
                name="nia-eye-tracking")
            _tracker["thread"].start()
        cfg = _load_config()
        cfg["eye_tracking_enabled"] = True
        _save_config(cfg)
        return "👀 Seguimiento ocular iniciado. Mové la cabeza para controlar el cursor."
    if action == "stop":
        with _lock:
            _tracker["stop"] = True
            if _tracker["thread"]:
                _tracker["thread"].join(timeout=3)
            _tracker["thread"] = None
        cfg = _load_config()
        cfg["eye_tracking_enabled"] = False
        _save_config(cfg)
        return "👀 Seguimiento ocular detenido."
    return _tracker["status"]


def micro_movement(parameters: dict) -> str:
    action = str(parameters.get("action", "status")).lower()
    if action == "start":
        with _lock:
            if _tracker["thread"] and _tracker["thread"].is_alive():
                return "La navegación por movimientos ya está activa."
            _tracker["stop"] = False
            _tracker["kind"] = "micro_movement"
            _tracker["thread"] = threading.Thread(
                target=_track_loop, args=("micro_movement",), daemon=True,
                name="nia-micro-movement")
            _tracker["thread"].start()
        cfg = _load_config()
        cfg["micro_movement_enabled"] = True
        _save_config(cfg)
        return "🙂 Navegación por movimientos de cabeza iniciada."
    if action == "stop":
        with _lock:
            _tracker["stop"] = True
            if _tracker["thread"]:
                _tracker["thread"].join(timeout=3)
            _tracker["thread"] = None
        cfg = _load_config()
        cfg["micro_movement_enabled"] = False
        _save_config(cfg)
        return "🙂 Navegación por movimientos detenida."
    return _tracker["status"]


def _set_speech_threshold(level: float) -> str:
    """Ajusta la tolerancia de voz de Nia.

    El nivel llega en escala 0.0-1.0 (0.0 = máxima sensibilidad, 1.0 =
    máxima tolerancia). Se convierte al umbral real de la puerta de ruido
    (RMS ~0.0005-0.01, el mismo rango del slider de la UI) para no romper
    el VAD: un valor directo 0.1-1.0 dejaría a Nia prácticamente sorda.
    """
    try:
        level = max(0.0, min(1.0, float(level)))
    except Exception:
        return "Error: el nivel de tolerancia debe ser un número entre 0.0 y 1.0."
    threshold = round(0.0005 + 0.0095 * level, 5)
    api = BASE_DIR / "config" / "api_keys.json"
    try:
        cfg = json.loads(api.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    cfg["mic_sensitivity"] = threshold
    try:
        api.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        return f"Error guardando la configuración: {e}"
    acc = _load_config()
    acc["speech_error_threshold"] = round(level, 2)
    _save_config(acc)
    return f"🎙️ Tolerancia de voz ajustada a {level:.2f} (sensibilidad del micrófono {threshold:.4f})."


def accessibility(parameters: dict, player=None) -> str:
    """Dispatcher principal del módulo de accesibilidad universal."""
    action = str(parameters.get("action", "")).strip().lower()
    if not action:
        return "Error: falta la acción (task_simplify, emotional, routine, eye_tracking, micro_movement, speech_config, feedback, config)."

    if action == "task_simplify":
        fmt = str(parameters.get("format", "steps"))
        return task_simplify(parameters.get("text", ""), fmt)

    if action == "emotional":
        cfg = _load_config()
        if not cfg.get("emotional_regulation_enabled", True):
            return "La regulación emocional está desactivada en la configuración."
        stress = parameters.get("stress_level")
        lines = ["🧘 Ejercicio de respiración guiada:"]
        if stress is not None:
            lines.append(f"  Nivel de estrés detectado: {stress:.0%}.")
        lines.append("  1. Inhalá por la nariz contando hasta 4.")
        lines.append("  2. Retené el aire contando hasta 4.")
        lines.append("  3. Exhalá por la boca contando hasta 6.")
        lines.append("  4. Repetí 5 veces, soltando los hombros.")
        lines.append("¿Querés que te guíe en voz alta?")
        return "\n".join(lines)

    if action == "routine":
        return routine_gamify(parameters)

    if action == "eye_tracking":
        return eye_tracking(parameters)

    if action == "micro_movement":
        return micro_movement(parameters)

    if action == "speech_config":
        if "level" in parameters:
            return _set_speech_threshold(parameters.get("level", 0.5))
        try:
            api = BASE_DIR / "config" / "api_keys.json"
            gate = float(json.loads(api.read_text(encoding="utf-8")).get("mic_sensitivity", 0.003))
        except Exception:
            gate = 0.003
        return f"🎙️ Sensibilidad del micrófono actual: {gate:.4f} (umbral de ruido)."

    if action == "feedback":
        cfg = _load_config()
        cfg["visual_feedback_enabled"] = not cfg.get("visual_feedback_enabled", True)
        _save_config(cfg)
        state = "activado" if cfg["visual_feedback_enabled"] else "desactivado"
        if player is not None:
            try:
                player.write_log(f"💡 Feedback visual {state}.")
            except Exception:
                pass
        return f"💡 Retroalimentación visual {state}."

    if action == "config":
        cfg = _load_config()
        setting = str(parameters.get("setting", "")).strip()
        if setting:
            if "value" in parameters:
                try:
                    value = parameters["value"]
                    if isinstance(value, str):
                        low = value.lower()
                        if low in ("true", "false"):
                            value = low == "true"
                        else:
                            try:
                                value = float(value)
                            except Exception:
                                pass
                    cfg[setting] = value
                    _save_config(cfg)
                    return f"⚙️ '{setting}' = {value}."
                except Exception as e:
                    return f"Error guardando '{setting}': {e}"
            if setting in cfg:
                return f"⚙️ '{setting}' = {cfg[setting]}."
            return f"No existe la clave '{setting}' en la configuración."
        return "⚙️ Configuración:\n" + "\n".join(f"  {k} = {v}" for k, v in cfg.items())

    # Toggle de alto contraste
    if action in ("high_contrast_on", "high_contrast_off"):
        cfg = _load_config()
        cfg["high_contrast_mode"] = action.endswith("_on")
        _save_config(cfg)
        state = "activado" if cfg["high_contrast_mode"] else "desactivado"
        return f"🌓 Alto contraste {state}."

    return ("No entendí esa acción de accesibilidad. Usá: task_simplify, emotional, "
            "routine, eye_tracking, micro_movement, speech_config, feedback o config.")
