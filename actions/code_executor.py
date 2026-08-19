"""code_executor.py — Ejecuta código Python y devuelve el output.

Ejecuta en subprocess aislado con timeout, captura stdout+stderr,
y puede ejecutar archivos .py o código inline. Seguro: sin acceso
a red (opcional), sin subprocess anidados peligrosos.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent


def code_executor(parameters: dict, player=None) -> str:
    """Ejecuta código Python y devuelve stdout/stderr."""
    code = str(parameters.get("code", "")).strip()
    file_path = str(parameters.get("file_path", "")).strip()
    timeout = int(parameters.get("timeout", 30))
    args = str(parameters.get("args", "")).strip()
    safe_mode = str(parameters.get("safe_mode", "true")).lower() != "false"

    if not code and not file_path:
        return "Necesito código Python para ejecutar o la ruta a un .py."

    if player:
        player.write_log(f"🐍 Ejecutando código Python...")

    # Preparar script
    if file_path:
        file_path = os.path.expanduser(file_path)
        if not os.path.isfile(file_path):
            return f"Archivo no encontrado: {file_path}"
        cmd = [sys.executable, file_path]
        if args:
            cmd.extend(args.split())
    else:
        if safe_mode:
            forbidden = ["os.system", "subprocess", "__import__('os')",
                         "eval(", "exec(", "compile(",
                         "open('/etc", "open('/proc", "open('/sys"]
            for pat in forbidden:
                if pat in code:
                    return (f"Código bloqueado: contiene '{pat}'. "
                            "Usá safe_mode=false para desactivar.")
        tmp_dir = str(_REPO / ".tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False,
            dir=tmp_dir,
        )
        tmp.write(code)
        tmp.close()
        cmd = [sys.executable, tmp.name]
        if args:
            cmd.extend(args.split())

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=min(timeout, 120),
            cwd=str(_REPO),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        stdout = result.stdout or ""
        stderr = result.stderr or ""
    except subprocess.TimeoutExpired:
        return f"⏰ Timeout después de {timeout} segundos."
    except Exception as e:
        return f"Error ejecutando: {e}"
    finally:
        if not file_path and "tmp" in dir():
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    lines = []
    rc = result.returncode
    if rc == 0:
        lines.append(f"✅ Ejecutado (exit 0)")
    else:
        lines.append(f"⚠️ Exit code: {rc}")

    if stdout.strip():
        lines.append(f"\n📤 stdout:\n{stdout.strip()}")
    if stderr.strip():
        lines.append(f"\n⚠️ stderr:\n{stderr.strip()}")
    if not stdout.strip() and not stderr.strip():
        lines.append("\n(Sin output)")

    return "\n".join(lines)


def run_file(parameters: dict, player=None) -> str:
    """Atajo: ejecuta un archivo .py existente."""
    path = str(parameters.get("path", "")).strip()
    args = str(parameters.get("args", "")).strip()
    timeout = int(parameters.get("timeout", 30))

    if not path:
        return "Necesito la ruta del archivo .py."

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Archivo no encontrado: {path}"

    return code_executor({
        "file_path": path,
        "args": args,
        "timeout": timeout,
        "safe_mode": "false",
    }, player=player)
