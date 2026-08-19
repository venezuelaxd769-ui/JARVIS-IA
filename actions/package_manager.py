"""package_manager.py — Gestiona paquetes Python (pip).

Instala, actualiza, lista y busca paquetes. Ejecuta pip del venv
del proyecto. Protección: solo gestiona paquetes, no toma el control
del sistema.
"""
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_VENV_PIP = str(_REPO / ".venv" / "bin" / "pip")
_VENV_PY = str(_REPO / ".venv" / "bin" / "python")


def _run_pip(args, timeout=60):
    """Ejecuta pip con los argumentos dados."""
    cmd = [_VENV_PIP] + args
    if not os.path.exists(_VENV_PIP):
        cmd = [sys.executable, "-m", "pip"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


def package_manager(parameters: dict, player=None) -> str:
    """Gestiona paquetes Python: install, update, list, search, info."""
    action = str(parameters.get("action", "list")).lower().strip()
    package = str(parameters.get("package", "")).strip()

    if action in ("list", "ls", "instalados"):
        if player:
            player.write_log("📦 Listando paquetes instalados...")
        rc, out, err = _run_pip(["list", "--format=columns"], timeout=30)
        if rc != 0:
            return f"Error listando paquetes: {err[:500]}"
        lines = out.strip().split("\n")
        if len(lines) > 20:
            return f"📦 {len(lines)-2} paquetes instalados:\n\n" + "\n".join(lines[:20]) + f"\n\n... ({len(lines)-22} más)"
        return f"📦 Paquetes:\n{out}"

    if action in ("install", "instalar", "i"):
        if not package:
            return "Necesito el nombre del paquete a instalar."
        if player:
            player.write_log(f"📦 Instalando {package}...")
        rc, out, err = _run_pip(["install", package], timeout=120)
        if rc == 0:
            return f"✅ {package} instalado correctamente.\n{out[-300:] if out else ''}"
        return f"❌ Error instalando {package}:\n{err[-500:] if err else out[-500:]}"

    if action in ("update", "actualizar", "u"):
        if package:
            if player:
                player.write_log(f"📦 Actualizando {package}...")
            rc, out, err = _run_pip(["install", "--upgrade", package], timeout=120)
        else:
            if player:
                player.write_log("📦 Actualizando pip...")
            rc, out, err = _run_pip(["install", "--upgrade", "pip"], timeout=60)
        if rc == 0:
            return f"✅ Actualizado.\n{out[-300:] if out else ''}"
        return f"❌ Error: {err[-500:] if err else out[-500:]}"

    if action in ("search", "buscar", "s"):
        if not package:
            return "Necesito un nombre para buscar."
        if player:
            player.write_log(f"🔍 Buscando {package}...")
        rc, out, err = _run_pip(["index", "versions", package], timeout=30)
        if rc == 0 and out.strip():
            return f"🔍 {out.strip()}"
        # Fallback: mostrar info
        rc, out, err = _run_pip(["show", package], timeout=15)
        if rc == 0 and out.strip():
            return f"📦 {out.strip()}"
        return f"No encontré info de '{package}' en PyPI."

    if action in ("info", "información"):
        if not package:
            return "Necesito el nombre del paquete."
        rc, out, err = _run_pip(["show", package], timeout=15)
        if rc == 0 and out.strip():
            return f"📦 {out.strip()}"
        return f"No encontré el paquete '{package}'."

    if action in ("uninstall", "desinstalar", "remove"):
        if not package:
            return "Necesito el nombre del paquete a desinstalar."
        if player:
            player.write_log(f"📦 Desinstalando {package}...")
        rc, out, err = _run_pip(["uninstall", "-y", package], timeout=60)
        if rc == 0:
            return f"✅ {package} desinstalado."
        return f"❌ Error: {err[-300:] if err else out[-300:]}"

    return ("Acciones: list/ls, install/instalar (requiere package), "
            "update/actualizar, search/buscar, info, uninstall/desinstalar.")


def run_script(parameters: dict, player=None) -> str:
    """Ejecuta un script Python con el venv del proyecto."""
    path = str(parameters.get("path", "")).strip()
    args = str(parameters.get("args", "")).strip()

    if not path:
        return "Necesito la ruta del script."

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Script no encontrado: {path}"

    cmd = [_VENV_PY, path]
    if args:
        cmd.extend(args.split())

    if player:
        player.write_log(f"🐍 Ejecutando script: {os.path.basename(path)}...")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            cwd=str(_REPO),
        )
        lines = []
        if result.returncode == 0:
            lines.append(f"✅ Script ejecutado (exit 0)")
        else:
            lines.append(f"⚠️ Exit code: {result.returncode}")
        if result.stdout.strip():
            lines.append(f"\n📤 stdout:\n{result.stdout.strip()}")
        if result.stderr.strip():
            lines.append(f"\n⚠️ stderr:\n{result.stderr.strip()}")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return "⏰ Timeout después de 60 segundos."
    except Exception as e:
        return f"Error: {e}"
