"""user_profile.py — Clean user habit & configuration recorder."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROFILE_PATH = BASE_DIR / "config" / "user_profile.json"

def user_profile(parameters: dict, player=None) -> str:
    """Manage general user profile variables."""
    action = parameters.get("action", "").lower()
    profile = _load_profile()

    if action in ("get", "view"):
        return f"User preferences: {json.dumps(profile)}"

    elif action == "set_preference":
        key = parameters.get("key", "")
        value = parameters.get("value", "")
        if not key or value is None:
            return "Error: necesito 'key' y 'value' para set_preference."
        profile.setdefault("preferences", {})[key] = value
        _save_profile(profile)
        return f"Preferencia '{key}' guardada."

    elif action == "set_name":
        name = parameters.get("value") or parameters.get("name")
        if not name:
            return "Error: necesito 'value' con el nombre."
        profile["name"] = str(name)
        _save_profile(profile)
        return f"Nombre actualizado a '{name}'."

    elif action == "add_note":
        note = parameters.get("note") or parameters.get("value")
        if not note:
            return "Error: necesito 'note'."
        profile.setdefault("notes", []).append(str(note))
        _save_profile(profile)
        return "Nota agregada al perfil."

    elif action == "habits":
        habits = profile.get("habits", {})
        if not habits:
            return "Todavía no hay hábitos registrados."
        top = sorted(habits.items(), key=lambda kv: kv[1], reverse=True)[:10]
        return "Hábitos más frecuentes: " + ", ".join(f"{k} ({v}x)" for k, v in top)

    elif action == "reset":
        _save_profile({"name": "Sir", "habits": {}})
        return "Perfil de usuario restablecido."

    return f"Acción '{action}' no soportada por user_profile (get | set_preference | set_name | add_note | habits | reset)."

def _load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {"name": "Sir", "habits": {}}
    try:
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"name": "Sir", "habits": {}}

def _save_profile(profile: dict) -> None:
    try:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except Exception:
        pass

def record_action(name: str, args: dict) -> None:
    """Log executed actions to track user habits over time."""
    try:
        profile = _load_profile()
        habits = profile.setdefault("habits", {})
        count = habits.get(name, 0)
        habits[name] = count + 1
        _save_profile(profile)
    except Exception:
        pass
