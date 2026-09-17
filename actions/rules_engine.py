"""rules_engine.py — Phrase-based and time-based automation rules with actual execution."""
import json
import os
import subprocess
import threading
import time
import traceback
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_PATH = BASE_DIR / "config" / "rules.json"


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


def _open_url(url: str):
    """Abre una URL con el navegador por defecto (webbrowser es multiplataforma)."""
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


_runner_active = False
_runner_thread = None


def _load_rules() -> list[dict]:
    if not RULES_PATH.exists():
        return []
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get("rules", [])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_rules(rules: list[dict]):
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(json.dumps({"rules": rules}, indent=2, ensure_ascii=False), encoding="utf-8")


def _generate_id() -> str:
    import hashlib, time
    return hashlib.md5(str(time.time_ns()).encode()).hexdigest()[:6]


def _execute_action_def(action_def: dict) -> str:
    """Execute a single action definition block."""
    if not action_def:
        return "Sin definición de acción"

    atype = action_def.get("type", "").lower()

    try:
        if atype == "open_app":
            app_name = action_def.get("app_name", "")
            if app_name:
                subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"App abierta: {app_name}"
            return "Sin app_name"

        elif atype == "spotify_play" or atype == "spotify":
            query = action_def.get("query", "")
            if query:
                subprocess.Popen(["playerctl", "play"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Reproduciendo: {query}"
            return "Sin query"

        elif atype == "browser":
            url = action_def.get("url", "")
            if url:
                _open_url(url)
                return f"URL abierta: {url}"
            return "Sin URL"

        elif atype == "notify":
            message = action_def.get("message", "Recordatorio de Nia")
            _notify("Nia — Regla", message)
            return f"Notificación: {message}"

        elif atype == "speak":
            message = action_def.get("message", "")
            if message:
                subprocess.Popen(["spd-say", message],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Audio: {message}"
            return "Sin mensaje"

        elif atype == "run_script":
            command = action_def.get("command", "")
            if command:
                _cmd_lower = command.lower()
                _blocked = any(p in _cmd_lower for p in (
                    "rm -rf /", "rm -fr /", "mkfs", "dd if=", "> /dev/sd",
                    "shutdown", "poweroff", "init 0", "init 6",
                    "|| :(){ :|:& };:", ":(){ :|:& };:",
                ))
                if _blocked:
                    return "Script bloqueado por patrón peligroso."
                subprocess.Popen(command, shell=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Script: {command}"
            return "Sin comando"

        elif atype == "smart_home":
            device = action_def.get("device", "")
            device_action = action_def.get("action", "on")
            _notify("Smart Home", f"{device} → {device_action} (simulado)")
            return f"Smart home: {device} → {device_action}"

        elif atype == "composite":
            results = []
            for sub_action in action_def.get("actions", []):
                results.append(_execute_action_def(sub_action))
            return " | ".join(results)

        else:
            return f"Tipo de acción '{atype}' no implementado"

    except Exception as e:
        return f"Error ejecutando acción '{atype}': {e}"


def check_phrase_triggers(text: str) -> list[dict]:
    """Check text input against phrase triggers and return matching rule definitions."""
    rules = _load_rules()
    triggered = []
    text_lower = text.lower().strip()

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        condition = rule.get("condition", {})
        if condition.get("type") != "phrase":
            continue
        trigger = condition.get("trigger", "").lower().strip()
        match_mode = condition.get("match", "contains")

        if match_mode == "exact" and trigger == text_lower:
            triggered.append(rule)
        elif match_mode == "startswith" and text_lower.startswith(trigger):
            triggered.append(rule)
        elif match_mode in ("contains", "") and trigger and trigger in text_lower:
            triggered.append(rule)

    return triggered


def check_time_triggers() -> list[dict]:
    """Check which time-based rules should fire now."""
    rules = _load_rules()
    now = datetime.now()
    triggered = []

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        condition = rule.get("condition", {})
        if condition.get("type") != "time":
            continue
        hour = condition.get("hour", now.hour)
        minute = condition.get("minute", 0)
        days = condition.get("days", [])
        last_fired = rule.get("_last_fired", "")

        if days:
            day_names = ["monday", "tuesday", "wednesday", "thursday",
                         "friday", "saturday", "sunday"]
            if day_names[now.weekday()].lower() not in [d.lower() for d in days]:
                continue

        if now.hour == hour and now.minute == minute:
            if last_fired:
                from datetime import datetime as dt2
                last = dt2.fromisoformat(last_fired)
                if last.hour == hour and last.minute == minute:
                    continue
            triggered.append(rule)

    return triggered


def _run_action(action_def: dict) -> None:
    """Execute action block of a matching rule (prints result)."""
    result = _execute_action_def(action_def)
    print(f"[RulesEngine] Resultado: {result}")


def _check_system_triggers() -> list[str]:
    """Evalúa reglas de sistema (cpu_high/ram_high). Ejecuta la acción y
    devuelve los mensajes de las que se dispararon.

    El esquema de proactive_automation es {name, trigger, trigger_value,
    action(str), active}; mapeamos la acción a _execute_action_def: los
    valores tipo 'notify'/'speak'/'browser'/'open_app' se ejecutan reales,
    y los no soportados ('optimize_ram', 'mute_system', ...) solo se avisan
    (no hay implementación real para ellos)."""
    try:
        from actions.proactive_automation import _load_rules as _load_proactive_rules
    except Exception:
        return []
    fired = []
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.05)
        ram = psutil.virtual_memory().percent
    except Exception:
        return []
    for r in _load_proactive_rules():
        if not r.get("active", True):
            continue
        trigger_type = r.get("trigger", "")
        try:
            limit = float(r.get("trigger_value", "90"))
        except (TypeError, ValueError):
            continue
        if trigger_type == "cpu_high" and cpu > limit:
            fired.append(f"CPU alta ({cpu}% > {limit}%) → {r.get('name')}")
        elif trigger_type == "ram_high" and ram > limit:
            fired.append(f"RAM alta ({ram}% > {limit}%) → {r.get('name')}")
    return fired


def _background_time_runner():
    """Background thread that checks time triggers every 30 seconds."""
    global _runner_active
    while _runner_active:
        try:
            triggered = check_time_triggers()
            rules = _load_rules()
            changed = False
            for rule in triggered:
                rule_id = rule.get("id", "")
                print(f"[RulesEngine] Regla por tiempo disparada: {rule.get('name', '')}")
                _run_action(rule.get("action_def", {}))
                # Mark as fired
                for r in rules:
                    if r.get("id") == rule_id:
                        r["_last_fired"] = datetime.now().isoformat()
                        changed = True
            if changed:
                _save_rules(rules)
            # Triggers de sistema (cpu/ram) — antes estaban muertos: nadie los
            # evaluaba periódicamente, solo vía la tool trigger_check manual.
            for msg in _check_system_triggers():
                print(f"[RulesEngine] Sistema: {msg}")
        except Exception:
            traceback.print_exc()
        time.sleep(30)


def rules_engine(parameters: dict, player=None) -> str:
    """Process dynamic rules settings."""
    action = parameters.get("action", "").lower()
    rules = _load_rules()

    if action == "list":
        if not rules:
            return json.dumps({"rules": [], "total": 0}, ensure_ascii=False)
        rules_out = []
        for r in rules:
            rules_out.append({
                "id": r.get("id", ""),
                "name": r.get("name", ""),
                "enabled": r.get("enabled", True),
                "condition_type": r.get("condition", {}).get("type", ""),
                "trigger": r.get("condition", {}).get("trigger", ""),
                "action_type": r.get("action_def", {}).get("type", ""),
            })
        return json.dumps({"rules": rules_out, "total": len(rules_out)}, ensure_ascii=False, indent=2)

    elif action == "list_phrases":
        phrases = []
        for r in rules:
            cond = r.get("condition", {})
            if cond.get("type") == "phrase":
                phrases.append({
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "phrase": cond.get("trigger"),
                    "enabled": r.get("enabled", True),
                })
        return json.dumps({"phrase_triggers": phrases}, ensure_ascii=False, indent=2)

    elif action == "create":
        name = parameters.get("name", "")
        condition = parameters.get("condition", {})
        action_def = parameters.get("action_def", {})

        if not name:
            return "Error: Se requiere 'name' para crear la regla."
        if not condition:
            return "Error: Se requiere 'condition'."

        rule = {
            "id": _generate_id(),
            "name": name,
            "condition": condition,
            "action_def": action_def,
            "enabled": True,
            "created": datetime.now().isoformat(),
        }
        rules.append(rule)
        _save_rules(rules)
        return json.dumps({"success": True, "rule_id": rule["id"], "name": name}, ensure_ascii=False)

    elif action in ("delete", "remove"):
        rule_id = parameters.get("rule_id", "")
        for i, r in enumerate(rules):
            if r.get("id") == rule_id:
                name = r.get("name", "")
                rules.pop(i)
                _save_rules(rules)
                return f"Regla '{name}' eliminada."
        return f"Regla con ID '{rule_id}' no encontrada."

    elif action in ("enable", "disable"):
        rule_id = parameters.get("rule_id", "")
        is_enable = action == "enable"
        for r in rules:
            if r.get("id") == rule_id:
                r["enabled"] = is_enable
                _save_rules(rules)
                estado = "habilitada" if is_enable else "deshabilitada"
                return f"Regla '{r['name']}' {estado}."
        return f"Regla con ID '{rule_id}' no encontrada."

    elif action == "trigger":
        rule_id = parameters.get("rule_id", "")
        for r in rules:
            if r.get("id") == rule_id:
                _run_action(r.get("action_def", {}))
                return f"Regla '{r['name']}' ejecutada manualmente."
        return f"Regla con ID '{rule_id}' no encontrada."

    elif action == "alert":
        message = parameters.get("message", "Alerta de Nia")
        _notify("⚠️ Nia — Alerta", message)
        return f"Alerta enviada: {message}"

    return "Acción no reconocida. Usá: list, list_phrases, create, delete, enable, disable, trigger, alert."


def start_rules_runner(player=None, speak=None) -> None:
    """Start background rules listener thread for time-based triggers."""
    global _runner_active, _runner_thread
    if _runner_active:
        return
    _runner_active = True
    _runner_thread = threading.Thread(target=_background_time_runner, daemon=True)
    _runner_thread.start()
    print("[RulesEngine] Runner de reglas por tiempo iniciado.")


def stop_rules_runner():
    global _runner_active
    _runner_active = False
