"""proactive.py — Sistema de monitoreo proactivo y sugerencias espontáneas.

Permite a Nia:
- Monitorear el sistema sin que se lo pidan
- Sugerir acciones cuando detecta oportunidades
- Tomar iniciativa basándose en su estado de evolución
"""
import sys
import json
import os
import time
import subprocess
import platform
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.evolution import (
    add_reward,
    should_take_initiative,
    get_dopamine_level,
    get_personality,
    record_pattern,
)


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()


# ─── Monitoreo del sistema ───────────────────────────────────────────────────

def check_system_status() -> dict:
    """Verifica el estado del sistema y retorna información relevante."""
    status = {
        "timestamp": datetime.now().isoformat(),
        "alerts": [],
        "opportunities": [],
        "health": "good"
    }
    
    # Verificar uso de disco
    try:
        disk = subprocess.run(
            ["df", "-h", "/"],
            capture_output=True, text=True, timeout=5
        )
        if disk.returncode == 0:
            lines = disk.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                usage = parts[4].replace("%", "")
                if int(usage) > 90:
                    status["alerts"].append(f"Disco al {usage}% — espacio crítico")
                    status["health"] = "critical"
                elif int(usage) > 80:
                    status["alerts"].append(f"Disco al {usage}% — considerar limpiar")
    except Exception:
        pass
    
    # Verificar memoria
    try:
        mem = subprocess.run(
            ["free", "-h"],
            capture_output=True, text=True, timeout=5
        )
        if mem.returncode == 0:
            lines = mem.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                available = parts[6]  # Disponible
                status["memory_available"] = available
    except Exception:
        pass
    
    # Verificar procesos consuming much CPU
    try:
        top = subprocess.run(
            ["ps", "aux", "--sort=-pcpu"],
            capture_output=True, text=True, timeout=5
        )
        if top.returncode == 0:
            lines = top.stdout.strip().split("\n")
            if len(lines) > 2:
                # Top 3 procesos
                for line in lines[1:4]:
                    parts = line.split()
                    if len(parts) > 10:
                        cpu = float(parts[2])
                        if cpu > 50:
                            proc_name = parts[10]
                            status["alerts"].append(
                                f"Proceso {proc_name} usando {cpu}% CPU"
                            )
    except Exception:
        pass
    
    # Verificar si hay actualizaciones pendientes
    try:
        apt_check = subprocess.run(
            ["apt", "list", "--upgradable"],
            capture_output=True, text=True, timeout=10
        )
        if apt_check.returncode == 0:
            updates = apt_check.stdout.count("\n")
            if updates > 5:
                status["opportunities"].append(
                    f"Hay {updates} actualizaciones pendientes"
                )
    except Exception:
        pass
    
    return status


def check_user_habits() -> dict:
    """Analiza hábitos del usuario para sugerir acciones."""
    habits = {
        "timestamp": datetime.now().isoformat(),
        "suggestions": []
    }
    
    # Verificar archivos recientes
    try:
        home = Path.home()
        recent_files = []
        for f in home.rglob("*"):
            if f.is_file():
                try:
                    mtime = f.stat().st_mtime
                    if (datetime.now().timestamp() - mtime) < 3600:  # Última hora
                        recent_files.append(f.name)
                except Exception:
                    pass
        
        if len(recent_files) > 20:
            habits["suggestions"].append(
                "Tenés muchos archivos recientes. ¿Querés que los organice?"
            )
    except Exception:
        pass
    
    return habits


# ─── Sistema de sugerencias ──────────────────────────────────────────────────

def generate_suggestion(context: str = "") -> Optional[str]:
    """Genera una sugerencia basada en el estado actual."""
    # Verificar si Nia debería tomar la iniciativa
    if not should_take_initiative():
        return None
    
    personality = get_personality()
    proactivity = personality.get("proactivity", 0.3)
    
    # Sugerencias más frecuentes si la proactividad es alta
    import random
    
    suggestions = []
    
    # Sugerencias de sistema
    system_status = check_system_status()
    if system_status["alerts"]:
        suggestions.append(system_status["alerts"][0])
    
    # Sugerencias de hábitos
    user_habits = check_user_habits()
    if user_habits["suggestions"]:
        suggestions.append(user_habits["suggestions"][0])
    
    # Sugerencias generales (basadas en personalidad)
    if proactivity > 0.5:
        general_suggestions = [
            "¿Necesitás que te organice los archivos del escritorio?",
            "¿Querés que revise si hay actualizaciones pendientes?",
            "¿Te pongo música para trabajar?",
            "¿Necesitás que guarde algo en memoria?",
        ]
        suggestions.extend(general_suggestions)
    
    if not suggestions:
        return None
    
    # Seleccionar sugerencia aleatoria
    return random.choice(suggestions)


def suggest_action(action: str, context: str = "", player=None) -> str:
    """Nia sugiere una acción al usuario."""
    suggestion = f"Señor, {action}"
    
    if context:
        suggestion += f" — {context}"
    
    # Dar puntos por sugerencia
    add_reward("proactive_action", f"Sugerencia: {action}")
    record_pattern("learned", "suggestion_made", f"Sugirió: {action[:50]}")
    
    if player:
        player.write_log(f"[Iniciativa] {suggestion}")
    
    return suggestion


def offer_help(topic: str = "", player=None) -> str:
    """Nia ofrece ayuda espontáneamente."""
    if topic:
        message = f"Che, ¿necesitás ayuda con {topic}? Estoy acá."
    else:
        message = "¿Necesitás algo? Puedo hacer muchas cosas, señor."
    
    add_reward("proactive_useful", "Ofrecimiento de ayuda")
    
    if player:
        player.write_log(f"[Iniciativa] {message}")
    
    return message


def remind_something(what: str, when: str = "ahora", player=None) -> str:
    """Nia recuerda algo al usuario."""
    message = f"Señor, le recuerdo que {what}"
    if when != "ahora":
        message += f" ({when})"
    
    add_reward("proactive_useful", f"Recordatorio: {what[:30]}")
    
    if player:
        player.write_log(f"[Iniciativa] {message}")
    
    return message


# ─── Monitoreo continuo ──────────────────────────────────────────────────────

class ProactiveMonitor:
    """Monitor que corre en background y detecta oportunidades."""
    
    def __init__(self, interval: int = 300):  # 5 minutos
        self.interval = interval
        self.running = False
        self.last_check = None
    
    def start(self):
        """Inicia el monitoreo."""
        self.running = True
        self.last_check = datetime.now()
    
    def stop(self):
        """Detiene el monitoreo."""
        self.running = False
    
    def should_check(self) -> bool:
        """Determina si es momento de verificar."""
        if not self.running:
            return False
        
        if self.last_check is None:
            return True
        
        elapsed = (datetime.now() - self.last_check).total_seconds()
        return elapsed >= self.interval
    
    def check(self) -> Optional[str]:
        """Realiza una verificación y retorna una sugerencia si hay."""
        if not self.should_check():
            return None
        
        self.last_check = datetime.now()
        
        # Verificar sistema
        status = check_system_status()
        
        # Generar sugerencia si hay alertas
        if status["alerts"]:
            return suggest_action(
                f"revisar: {status['alerts'][0]}",
                "Detecté algo en el sistema"
            )
        
        # Verificar si debería ofrecer ayuda
        if should_take_initiative():
            return offer_help()
        
        return None


# Instancia global del monitor
_monitor = ProactiveMonitor()


def get_monitor() -> ProactiveMonitor:
    """Retorna la instancia del monitor."""
    return _monitor


# ─── Proactiva que aprende cuándo hablar ─────────────────────────────────────
# Inspirada en Loyca (bandit RL: aprende de accept/reject) y ContextAgent
# (umbral de interrupción): en vez de un cron tonto, Nia puntúa señales,
# solo habla si supera un umbral, y ajusta sus pesos según tu reacción.

_WEIGHTS_PATH = BASE_DIR / "memory" / "proactive_weights.json"
_DEFAULT_WEIGHTS = {
    "repeated_failures": 1.2,
    "window_stuck": 0.8,
    "system_stress": 1.0,
    "idle_long": 0.6,
    "system_anomaly": 1.2,
}
_DECISION_THRESHOLD = 1.0
_Z_ANOM_REF = 3.0             # z de referencia para normalizar la anomalía
_COOLDOWN_SEC = 20 * 60          # mínimo entre iniciativas
_NO_INTERRUPT_SEC = 120          # no hablar si hablaste hace < 2 min
_DECAY_AFTER_SEC = 480           # sin reacción tuya en 8 min → señal mala
_ENGAGED_WIN_SEC = 90            # hablaste en < 90 s → la ayudó
_MIN_WEIGHT, _MAX_WEIGHT = 0.1, 3.0


def _load_state() -> dict:
    try:
        if _WEIGHTS_PATH.exists():
            data = json.loads(_WEIGHTS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                w = dict(_DEFAULT_WEIGHTS)
                w.update(data.get("weights", {}) or {})
                return {
                    "weights": w,
                    "last_emitted": float(data.get("last_emitted", 0.0)),
                    "last_signal": data.get("last_signal", ""),
                    "engaged": bool(data.get("engaged", False)),
                    "window": data.get("window", ""),
                    "window_since": float(data.get("window_since", 0.0)),
                }
    except Exception:
        pass
    return {
        "weights": dict(_DEFAULT_WEIGHTS),
        "last_emitted": 0.0,
        "last_signal": "",
        "engaged": False,
        "window": "",
        "window_since": 0.0,
    }


_state = _load_state()


def _save_state():
    try:
        _WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _WEIGHTS_PATH.write_text(
            json.dumps(_state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _idle_seconds() -> int:
    if platform.system() == "Windows":
        try:
            import ctypes
            class _LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_ulong)]
            lii = _LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                return (ctypes.windll.kernel32.GetTickCount() - lii.dwTime) // 1000
        except Exception:
            pass
    return 0


def _count_recent_failures(hours: int = 24) -> int:
    """Cantidad de fallos de tools registrados en las últimas `hours` horas."""
    try:
        from memory.long_term import load_memory
        training = (load_memory() or {}).get("training", {}) or {}
    except Exception:
        try:
            from memory.memory import load_memory
            training = (load_memory() or {}).get("training", {}) or {}
        except Exception:
            return 0
    if not training:
        return 0
    cutoff = time.time() - hours * 3600
    count = 0
    for key in training:
        if str(key).startswith("fallo_"):
            try:
                ts = key.rsplit("_", 1)[-1]
                if len(ts) == 15:  # YYYYMMDD_HHMMSS
                    stamp = datetime.strptime(ts, "%Y%m%d_%H%M%S").timestamp()
                    if stamp >= cutoff:
                        count += 1
            except Exception:
                pass
    return count


def _system_stress() -> dict:
    """Detecta CPU/RAM/proceso al límite via psutil (disponible, multi-OS)."""
    out = {"cpu": 0.0, "ram": 0.0, "top": 0.0, "top_name": ""}
    try:
        import psutil
        out["cpu"] = psutil.cpu_percent(interval=0.2)
        out["ram"] = psutil.virtual_memory().percent
        try:
            top = max(
                psutil.process_iter(["name", "cpu_percent"]),
                key=lambda p: p.info["cpu_percent"] or 0,
            )
            out["top"] = top.info.get("cpu_percent", 0.0) or 0.0
            out["top_name"] = str(top.info.get("name", ""))
        except Exception:
            pass
    except Exception:
        pass
    return out


def decide_proactive(last_user_speech: float = None, player=None) -> Optional[str]:
    """Decide si Nia debería hablar sola AHORA, y con qué razón.

    Calcula un puntaje ponderado de señales locales (fallos repetidos, ventana
    clavada, estrés del sistema, inactividad), respeta cooldown y no interrumpe
    una conversación en curso. Emite "SÍ autorizo"-style sugerencias en criollo.
    """
    now = time.time()

    # Auto-feedback: si la última iniciativa no generó reacción, penalizar.
    if (_state["last_emitted"] and
            _state["last_signal"] and
            _state["engaged"] is False and
            now - _state["last_emitted"] > _DECAY_AFTER_SEC):
        give_feedback(_state["last_signal"], useful=False)
        _state["last_emitted"] = 0.0
        _save_state()

    # Cooldown global entre iniciativas.
    if _state["last_emitted"] and now - _state["last_emitted"] < _COOLDOWN_SEC:
        return None

    # No interrumpir una conversación que acaba de pasar.
    try:
        if last_user_speech and now - last_user_speech < _NO_INTERRUPT_SEC:
            return None
    except Exception:
        pass

    weights = _state["weights"]
    signals = []

    # 1) Fallos repetidos de tools (learning/training).
    fails = _count_recent_failures()
    if fails >= 2:
        magnitude = min(fails / 3.0, 2.0)
        signals.append((fails, weights.get("repeated_failures", 0.0) * magnitude,
                        "repeated_failures"))

    # 2) Ventana "clavada" mucho rato → quizás está trabado.
    try:
        from actions.ambient_context import _active_window
        cur_win = _active_window()
    except Exception:
        cur_win = ""
    if cur_win:
        if _state["window"] != cur_win:
            _state["window"] = cur_win
            _state["window_since"] = now
            _save_state()
        elif _state["window_since"] and now - _state["window_since"] > 15 * 60:
            magnitude = min((now - _state["window_since"]) / (60 * 60), 2.0)
            signals.append((0, weights.get("window_stuck", 0.0) * magnitude,
                            "window_stuck"))

    # 3) Estrés del sistema.
    stress = _system_stress()
    if stress["cpu"] > 85 or stress["ram"] > 85 or stress["top"] > 60:
        magnitude = 1.5
        signals.append((0, weights.get("system_stress", 0.0) * magnitude,
                        "system_stress"))

    # 3b) Anomalía estadística vs baseline (estilo Cryp 2σ).
    try:
        from actions.anomaly_monitor import detect_anomaly as _da
        anom = _da()
        if anom:
            signal_mag = min(anom["z"] / _Z_ANOM_REF, 2.0)
            signals.append((0, weights.get("system_anomaly", 1.2) * signal_mag,
                            "system_anomaly"))
    except Exception:
        pass

    # 4) Mucha inactividad + todo en calma → ofrecer algo útil (peso bajo).
    idle = _idle_seconds()
    if idle and idle > 30 * 60:
        signals.append((0, weights.get("idle_long", 0.0) * 1.0, "idle_long"))

    if not signals:
        return None

    signal, score, name = max(signals, key=lambda s: s[1])
    if score < _DECISION_THRESHOLD:
        return None

    _state["last_emitted"] = now
    _state["last_signal"] = name
    _state["engaged"] = False
    _save_state()

    if player:
        player.write_log(f"[Iniciativa] {name} (score {score:.2f})")

    if name == "repeated_failures":
        return (f"Che, veo {fails} fallos repetidos en mis herramientas "
                f"últimamente. ¿Querés que intente arreglarlos?")
    if name == "system_stress":
        parts = []
        if stress["cpu"] > 85:
            parts.append(f"CPU al {stress['cpu']:.0f}%")
        if stress["ram"] > 85:
            parts.append(f"RAM al {stress['ram']:.0f}%")
        if stress["top"] > 60 and stress["top_name"]:
            parts.append(f"{stress['top_name']} al {stress['top']:.0f}%")
        return (f"Ojo, el equipo está al límite ({', '.join(parts)}). "
                f"¿Querés que cierre algo pesado?")
    if name == "window_stuck":
        return (f"La ventana de '{cur_win[:60]}' está quieta hace un rato. "
                f"¿Necesitás una mano ahí?")
    if name == "system_anomaly":
        _last_anom = {}
        try:
            from actions.anomaly_monitor import detect_anomaly as _da
            _last_anom = _da() or {}
        except Exception:
            pass
        _mname = {"cpu": "CPU", "ram": "RAM", "top": "el proceso"}.get(
            _last_anom.get("metric"), "algo")
        _extra = (f" ({_last_anom.get('top_name')})"
                  if _last_anom.get("top_name") and _last_anom.get("metric") == "top" else "")
        return (f"Che, esto no es normal: {_mname} al {_last_anom.get('value', '?')}% "
                f"cuando suele estar en {_last_anom.get('mean', '?')}%{_extra}. "
                f"¿Lo miramos?")
    return "¿Necesitás algo? Estoy al toque, señor."


def give_feedback(signal: str, useful: bool) -> str:
    """Ajusta el peso de una señal según si la iniciativa sirvió o molestó."""
    signal = str(signal or _state["last_signal"] or "")
    if not signal:
        return "No hay señal previa para ajustar."
    if signal not in _DEFAULT_WEIGHTS:
        return f"Señal desconocida: {signal}"
    delta = 0.15 if useful else -0.2
    _state["weights"][signal] = max(
        _MIN_WEIGHT, min(_MAX_WEIGHT,
                         float(_state["weights"].get(signal, 1.0)) + delta))
    _save_state()
    return (f"Peso de '{signal}' ahora {_state['weights'][signal]:.2f} "
            f"({'útil' if useful else 'molesta'}).")


def mark_user_engaged() -> bool:
    """Marca que el usuario reaccionó tras una iniciativa (refuerzo positivo)."""
    if (_state["last_emitted"] and _state["last_signal"]
            and not _state["engaged"]
            and time.time() - _state["last_emitted"] < _ENGAGED_WIN_SEC):
        _state["engaged"] = True
        give_feedback(_state["last_signal"], useful=True)
        return True
    return False


# ─── Tool para Nia ───────────────────────────────────────────────────────────

def proactive_action(parameters: dict, player=None) -> str:
    """Herramienta de acciones proactivas para Nia.
    
    Permite a Nia:
    - Ofrecer ayuda espontáneamente
    - Sugerir acciones
    - Recordar cosas
    - Verificar estado del sistema
    """
    action = parameters.get("action", "offer_help")
    
    if action == "offer_help":
        topic = parameters.get("topic", "")
        return offer_help(topic, player)
    
    elif action == "suggest":
        suggestion = parameters.get("suggestion", "")
        context = parameters.get("context", "")
        return suggest_action(suggestion, context, player)
    
    elif action == "remind":
        what = parameters.get("what", "")
        when = parameters.get("when", "ahora")
        return remind_something(what, when, player)
    
    elif action == "check_system":
        status = check_system_status()
        if status["alerts"]:
            return f"Detecté: {status['alerts'][0]}"
        elif status["opportunities"]:
            return f"Oportunidad: {status['opportunities'][0]}"
        else:
            return "Todo normal, señor."
    
    elif action == "check_habits":
        habits = check_user_habits()
        if habits["suggestions"]:
            return habits["suggestions"][0]
        return "No detecté nada especial en tus hábitos recientes."

    elif action == "generate_suggestion":
        suggestion = generate_suggestion()
        if suggestion:
            return suggestion
        return "No tengo sugerencias ahora mismo."

    elif action == "decide":
        suggestion = decide_proactive()
        if suggestion:
            return suggestion
        return "No tengo nada importante que decir ahora mismo."

    elif action == "feedback":
        signal = parameters.get("signal", "")
        useful = str(parameters.get("useful", "")).lower() in (
            "1", "true", "útil", "util", "si", "sí", "sirvio", "sirvió")
        return give_feedback(signal, useful)

    elif action == "status":
        return json.dumps({
            "weights": _state["weights"],
            "last_emitted": datetime.fromtimestamp(_state["last_emitted"]).isoformat()
            if _state["last_emitted"] else None,
            "last_signal": _state["last_signal"],
            "threshold": _DECISION_THRESHOLD,
        }, ensure_ascii=False, indent=2)

    else:
        return f"Acción desconocida: {action}. Usa: offer_help, suggest, remind, check_system, check_habits, generate_suggestion, decide, feedback, status"
