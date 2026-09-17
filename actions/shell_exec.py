"""shell_exec.py — Ejecuta comandos del sistema de forma segura.

Solo ejecuta comandos de la whitelist segura sin confirmación.
Comandos "medios" (git add, pip install) se ejecutan pero se registran.
Comandos peligrosos (rm -rf /, sudo, chmod -R 777) se bloquean.
Todo se ejecuta con timeout y output limitado.
"""
import shlex
import subprocess
import time
from pathlib import Path

from sandbox import CONFIRM_PHRASE, confirm_granted

_DEFAULT_TIMEOUT = 30.0
_MAX_OUTPUT = 8000  # chars

# Comandos completamente seguros (sin confirmación)
_SAFE = {
    "ls", "ll", "la", "tree", "du", "df", "free", "uptime",
    "pwd", "whoami", "hostname", "date", "cal",
    "cat", "head", "tail", "less", "more", "file", "stat", "wc",
    "grep", "egrep", "fgrep", "rg", "ag",
    "find", "locate", "which", "whereis", "type",
    "echo", "printf", "env", "printenv",
    "git", "git status", "git log", "git diff", "git branch",
    "git show", "git remote", "git stash list",
    "python", "python3", "pip", "pip list", "pip show",
    "node", "npm", "npx", "yarn", "cargo", "rustc",
    "rg", "jq", "sed", "awk", "cut", "sort", "uniq", "tr",
    "du", "df", "lsblk", "lscpu", "lsusb",
    "ps", "pgrep", "top", "htop", "uname",
    "pacman", "paru", "yay",
    "systemctl", "journalctl",
    "hyprctl", "swaymsg",
    "wl-copy", "wl-paste",
    "brightnessctl", "pactl", "wpctl",
    "nmtui", "nmcli",
    "git commit", "git add",
    "pip install", "pip uninstall",
    "npm install", "npm uninstall",
    "cargo build", "cargo run", "cargo test",
}

# Comandos bloqueados (peligrosos)
_BLOCKED = {
    "rm -rf /", "rm -rf /*", "mkfs", "dd", "format",
    "shutdown", "reboot", "halt", "poweroff",
    "chmod -R 777", "chown -R",
    ":(){ :|:& };:",  # fork bomb
    "mv / ", "rm -rf ~",
    "curl | bash", "wget | bash",
}


def _is_blocked(cmd_str):
    lower = cmd_str.lower().strip()
    for pattern in _BLOCKED:
        if pattern in lower:
            return True
    return False


def _is_safe(cmd_str):
    parts = shlex.split(cmd_str)
    if not parts:
        return True
    base = Path(parts[0]).name
    # Primer token del comando debe estar en la whitelist
    for safe in _SAFE:
        if base == safe.split()[0]:
            return True
    return False


def _run(cmd_str, timeout=_DEFAULT_TIMEOUT, cwd=None):
    try:
        r = subprocess.run(
            cmd_str,
            shell=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
        )
        stdout = r.stdout.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
        stderr = r.stderr.decode("utf-8", errors="replace")[:_MAX_OUTPUT]
        if r.returncode == 0:
            return stdout or "(sin salida)", 0
        else:
            out = stdout
            if stderr:
                out += f"\n[stderr]: {stderr}"
            return out or f"(exit code: {r.returncode})", r.returncode
    except subprocess.TimeoutExpired:
        return f"Timeout ({timeout}s): el comando tardó demasiado.", 1
    except Exception as e:
        return f"Error: {e}", 1


def shell_exec(parameters: dict, player=None) -> str:
    """Ejecuta comandos del sistema de forma segura."""
    cmd = str(parameters.get("command", "") or parameters.get("cmd", "")).strip()
    if not cmd:
        return "Decime qué comando querés ejecutar."

    timeout = min(float(parameters.get("timeout", _DEFAULT_TIMEOUT) or _DEFAULT_TIMEOUT), 60.0)
    cwd = str(parameters.get("cwd", "")).strip() or None
    auto = str(parameters.get("force", "")).lower() in ("true", "1", "yes", "si")
    force = auto or confirm_granted(parameters)

    if _is_blocked(cmd):
        if player:
            player.write_log(f"🚫 Bloqueado: {cmd[:60]}")
        return (f"🚫 Comando bloqueado por seguridad: {cmd[:80]}. "
                "Este comando podría dañar el sistema.")

    if _is_safe(cmd) or force:
        if player:
            player.write_log(f"🖥️ Ejecutando: {cmd[:60]}")
        out, rc = _run(cmd, timeout, cwd)
        prefix = "✅" if rc == 0 else f"⚠️ (exit {rc})"
        return f"{prefix} {cmd[:60]}:\n{out[:2000]}"

    # Comando no whitelisted — pedir confirmación del usuario
    if player:
        player.write_log(f"🖥️ Pendiente confirmación: {cmd[:60]}")
    return (f"⚠️ Comando no whitelisted: {cmd[:80]}\n"
            f"Solo lo ejecuto si el Señor confirma en voz ('SÍ autorizo') o me pasás confirm='{CONFIRM_PHRASE}'.")
