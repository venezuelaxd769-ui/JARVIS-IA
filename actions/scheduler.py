"""scheduler.py — Task scheduler with persistent JSON storage and background runner."""
import json
import os
import threading
import time
import subprocess
import traceback
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
SCHED_PATH = BASE_DIR / "config" / "scheduled_tasks.json"


def _notify(title: str, message: str):
    """Notificación del sistema (notify-send en Linux, Toast en Windows)."""
    try:
        if os.name == "nt":
            ps = (
                "$ErrorActionPreference='SilentlyContinue';"
                "[Windows.UI.Notifications.ToastNotificationManager, "
                "Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
                "$Template=[Windows.UI.Notifications.ToastNotificationManager]"
                "::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]"
                "::ToastText02);"
                "$TextNodes=$Template.GetElementsByTagName('text');"
                f"$TextNodes.Item(0).AppendChild($Template.CreateTextNode('{title}'))|Out-Null;"
                f"$TextNodes.Item(1).AppendChild($Template.CreateTextNode('{message}'))|Out-Null;"
                "$Toast=[Windows.UI.Notifications.ToastNotification]::new($Template);"
                "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
                "'Nia').Show($Toast)"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(["notify-send", title, message],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


TASKS: dict[str, dict] = {}
_runner_active = False
_runner_thread = None
_PLAYER = None


def _load_tasks():
    global TASKS
    if SCHED_PATH.exists():
        try:
            TASKS = json.loads(SCHED_PATH.read_text(encoding="utf-8"))
        except Exception:
            TASKS = {}
    else:
        TASKS = {}


def _save_tasks():
    SCHED_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHED_PATH.write_text(json.dumps(TASKS, indent=2, ensure_ascii=False), encoding="utf-8")


def _generate_id() -> str:
    import hashlib, time
    return hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:6]


def _execute_task(task: dict) -> str:
    task_action = task.get("task_action", "")
    task_params = task.get("task_parameters", {})
    task_name = task.get("name", "sin nombre")

    try:
        if task_action == "notify":
            msg = task_params.get("message", "Recordatorio desde Nia")
            _notify("Nia", msg)
            return f"Notificación enviada: {msg}"

        elif task_action == "custom_script":
            cmd = task_params.get("command", "")
            if cmd:
                subprocess.Popen(cmd, shell=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Script ejecutado: {cmd}"
            return "Sin comando"

        elif task_action == "open_app":
            app = task_params.get("app_name", "")
            if app:
                subprocess.Popen([app], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"App abierta: {app}"
            return "Sin app_name"

        elif task_action == "browser_control":
            url = task_params.get("url", "")
            if url:
                if os.name == "nt":
                    import webbrowser
                    webbrowser.open(url)
                else:
                    subprocess.Popen(["xdg-open", url],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"URL abierta: {url}"
            return "Sin URL"

        elif task_action == "daily_summary":
            from actions.daily_summary import daily_summary
            return daily_summary({"action": "generate"})

        elif task_action in ("speak", "nia_speak", "voice", "recordatorio_voz"):
            msg = task_params.get("message", "Recordatorio desde Nia")
            if msg:
                if _PLAYER is not None and hasattr(_PLAYER, "speak"):
                    try:
                        if os.name == "nt":
                            import winsound
                            winsound.PlaySound("SystemExclamation",
                                               winsound.SND_ALIAS | winsound.SND_ASYNC)
                        _PLAYER.speak(msg)
                        return f"Audio: {msg}"
                    except Exception as e:
                        return f"Fallo el audio: {e}"
                subprocess.Popen(["spd-say", msg],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Audio: {msg}"
            return "Sin mensaje"

        else:
            return f"Acción '{task_action}' no implementada"

    except Exception as e:
        return f"Error ejecutando tarea '{task_name}': {e}"


def _should_run_now(task: dict) -> bool:
    now = datetime.now()
    frequency = task.get("frequency", "once")
    last_run_str = task.get("last_run", "")
    last_run = datetime.fromisoformat(last_run_str) if last_run_str else None
    enabled = task.get("enabled", True)
    if not enabled:
        return False

    if frequency == "once":
        hour = task.get("hour", now.hour)
        minute = task.get("minute", 0)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if last_run:
            return False
        return now >= target and now < target + timedelta(seconds=120)

    if frequency == "daily":
        hour = task.get("hour", now.hour)
        minute = task.get("minute", 0)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < target:
            return False
        if last_run and last_run.date() == now.date():
            return False
        # Catch-up: si Nia arrancó después de la hora objetivo, correr igual
        # (la ventana de 2 min hacía que el resumen diario NUNCA corriera
        # si Nia estaba apagada a la hora exacta).
        return True

    if frequency == "weekly":
        weekday = task.get("weekday", "").lower()
        days_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                     "friday": 4, "saturday": 5, "sunday": 6}
        target_day = days_map.get(weekday, now.weekday())
        if now.weekday() != target_day:
            return False
        hour = task.get("hour", now.hour)
        minute = task.get("minute", 0)
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < target:
            return False
        if last_run and last_run.date() == now.date():
            return False
        return True

    if frequency == "interval":
        interval = task.get("interval_minutes", 60)
        if not last_run:
            return True
        elapsed = (now - last_run).total_seconds()
        return elapsed >= interval * 60

    return False


def _background_runner(player=None, speak=None):
    global _runner_active
    _load_tasks()
    while _runner_active:
        try:
            for task_id, task in TASKS.copy().items():
                if _should_run_now(task):
                    result = _execute_task(task)
                    TASKS[task_id]["last_run"] = datetime.now().isoformat()
                    _save_tasks()
                    print(f"[Scheduler] Tarea '{task.get('name')}': {result}")
        except Exception:
            traceback.print_exc()
        time.sleep(30)


def scheduler(parameters: dict, player=None, speak=None) -> str:
    action = parameters.get("action", "").lower()
    _load_tasks()

    if action == "list":
        if not TASKS:
            return json.dumps({"tasks": [], "total": 0}, ensure_ascii=False)
        tasks_list = []
        for tid, t in TASKS.items():
            tasks_list.append({
                "id": tid,
                "name": t.get("name", ""),
                "frequency": t.get("frequency", ""),
                "hour": t.get("hour", ""),
                "minute": t.get("minute", ""),
                "task_action": t.get("task_action", ""),
                "enabled": t.get("enabled", True),
                "last_run": t.get("last_run", ""),
            })
        return json.dumps({"tasks": tasks_list, "total": len(tasks_list)}, ensure_ascii=False, indent=2)

    elif action == "create":
        name = parameters.get("name", "")
        frequency = parameters.get("frequency", "once")
        hour = parameters.get("hour", 0)
        minute = parameters.get("minute", 0)
        weekday = parameters.get("weekday", "")
        interval_minutes = parameters.get("interval_minutes", 60)
        task_action = parameters.get("task_action", "notify")
        task_params = parameters.get("task_parameters", {})

        if not name:
            return "Error: Se requiere 'name' para crear la tarea."

        task_id = _generate_id()
        task = {
            "name": name,
            "frequency": frequency,
            "hour": hour,
            "minute": minute,
            "weekday": weekday,
            "interval_minutes": interval_minutes,
            "task_action": task_action,
            "task_parameters": task_params,
            "enabled": True,
            "created": datetime.now().isoformat(),
            "last_run": "",
        }
        TASKS[task_id] = task
        _save_tasks()
        return json.dumps({"success": True, "task_id": task_id, "name": name}, ensure_ascii=False)

    elif action in ("delete", "remove"):
        task_id = parameters.get("task_id", "")
        if task_id in TASKS:
            name = TASKS[task_id].get("name", "")
            del TASKS[task_id]
            _save_tasks()
            return f"Tarea '{name}' eliminada."
        return f"Tarea con ID '{task_id}' no encontrada."

    elif action in ("enable", "disable"):
        task_id = parameters.get("task_id", "")
        if task_id in TASKS:
            is_enable = action == "enable"
            TASKS[task_id]["enabled"] = is_enable
            _save_tasks()
            estado = "habilitada" if is_enable else "deshabilitada"
            return f"Tarea '{TASKS[task_id]['name']}' {estado}."
        return f"Tarea con ID '{task_id}' no encontrada."

    elif action == "run_now":
        task_id = parameters.get("task_id", "")
        if task_id in TASKS:
            result = _execute_task(TASKS[task_id])
            TASKS[task_id]["last_run"] = datetime.now().isoformat()
            _save_tasks()
            return f"Ejecutada: {result}"
        return f"Tarea con ID '{task_id}' no encontrada."

    return "Acción no reconocida. Usá: list, create, delete, enable, disable, run_now."


def start_runner(player=None, speak=None) -> None:
    global _runner_active, _runner_thread, _PLAYER
    _PLAYER = player
    if _runner_active:
        return
    _runner_active = True
    _runner_thread = threading.Thread(target=_background_runner, args=(player, speak), daemon=True)
    _runner_thread.start()
    print("[Scheduler] Runner iniciado en background.")


def stop_runner():
    global _runner_active
    _runner_active = False
