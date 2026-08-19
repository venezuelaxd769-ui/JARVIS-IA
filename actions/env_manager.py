"""env_manager.py — Gestiona variables de entorno.

Lee, establece y elimina variables de entorno. Puede guardar/load
desde un archivo .env. Útil para configurar el entorno de ejecución.
"""
import os
import re
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ENV_FILE = _REPO / ".env"


def _parse_env_file(path):
    """Parsea un archivo .env."""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Quitar comillas
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                env[key] = value
    return env


def _save_env_file(env_dict, path):
    """Guarda variables en archivo .env."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("# Auto-generado por Nia env_manager\n")
        for key, value in sorted(env_dict.items()):
            if " " in value or "'" in value:
                f.write(f'{key}="{value}"\n')
            else:
                f.write(f"{key}={value}\n")


def env_manager(parameters: dict, player=None) -> str:
    """Gestiona variables de entorno: get, set, list, load, save."""
    action = str(parameters.get("action", "list")).lower().strip()
    name = str(parameters.get("name", "")).strip()
    value = str(parameters.get("value", "")).strip()

    if action in ("list", "ls", "env", "ver"):
        """Lista variables de entorno relevantes."""
        relevant = ["PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL",
                     "PYTHONPATH", "VIRTUAL_ENV", "DISPLAY", "WAYLAND_DISPLAY",
                     "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS",
                     "FASTEMBED_CACHE_PATH", "NODE_ENV", "EDITOR"]
        lines = ["📋 Variables de entorno relevantes:\n"]
        for key in sorted(relevant):
            val = os.environ.get(key, "")
            if val:
                if len(val) > 80:
                    val = val[:80] + "..."
                lines.append(f"  {key}={val}")

        # Mostrar .env si existe
        if _ENV_FILE.exists():
            env_file = _parse_env_file(_ENV_FILE)
            if env_file:
                lines.append(f"\n📄 Variables en .env ({len(env_file)}):")
                for k, v in env_file.items():
                    lines.append(f"  {k}={v[:60]}")

        return "\n".join(lines)

    if action in ("get", "obtener", "g"):
        if not name:
            return "Necesito el nombre de la variable."
        val = os.environ.get(name)
        if val is None:
            # Buscar en .env
            if _ENV_FILE.exists():
                env_file = _parse_env_file(_ENV_FILE)
                val = env_file.get(name)
            if val is None:
                return f"Variable '{name}' no encontrada."
        return f"{name}={val}"

    if action in ("set", "establecer", "s"):
        if not name or not value:
            return "Necesito nombre y valor."
        os.environ[name] = value

        # Actualizar .env
        env_file = _parse_env_file(_ENV_FILE) if _ENV_FILE.exists() else {}
        env_file[name] = value
        _save_env_file(env_file, _ENV_FILE)

        if player:
            player.write_log(f"🔧 Variable {name} establecida.")
        return f"✅ {name}={value}"

    if action in ("unset", "eliminar", "del"):
        if not name:
            return "Necesito el nombre de la variable."
        if name in os.environ:
            del os.environ[name]
        if _ENV_FILE.exists():
            env_file = _parse_env_file(_ENV_FILE)
            if name in env_file:
                del env_file[name]
                _save_env_file(env_file, _ENV_FILE)
        return f"✅ Variable '{name}' eliminada."

    if action in ("load", "cargar"):
        """Carga variables desde .env."""
        path = str(parameters.get("path", "")).strip() or str(_ENV_FILE)
        if not os.path.exists(path):
            return f"Archivo no encontrado: {path}"
        env_file = _parse_env_file(path)
        loaded = 0
        for k, v in env_file.items():
            os.environ[k] = v
            loaded += 1
        return f"✅ {loaded} variables cargadas desde {os.path.basename(path)}."

    return ("Acciones: list/ls, get/obtener (requiere name), "
            "set/establecer (requiere name+value), "
            "unset/eliminar, load/cargar.")


def load_dotenv(parameters: dict, player=None) -> str:
    """Carga .env del proyecto. Wrapper para load_dotenv."""
    return env_manager({"action": "load"}, player=player)
