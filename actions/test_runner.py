"""test_runner.py — Ejecuta tests del proyecto.

Detecta framework de tests (pytest, unittest), ejecuta tests,
y devuelve resultados formateados. Puede ejecutar tests específicos,
archivos, o todos.
"""
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_VENV_PY = str(_REPO / ".venv" / "bin" / "python")
_VENV_PYTEST = str(_REPO / ".venv" / "bin" / "pytest")


def _detect_framework():
    """Detecta el framework de tests usado."""
    if os.path.exists(_VENV_PYTEST):
        return "pytest"
    # Buscar archivos de tests
    for pattern in ["tests/", "test/", "tests.py", "test_*.py", "*_test.py"]:
        if list(_REPO.glob(pattern)):
            return "unittest"
    # Buscar pytest.ini, setup.cfg, pyproject.toml con pytest
    for cfg in ["pytest.ini", "setup.cfg", "pyproject.toml"]:
        p = _REPO / cfg
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="replace")
            if "pytest" in content:
                return "pytest"
    return None


def _run_pytest(args, timeout=120):
    """Ejecuta pytest."""
    cmd = [_VENV_PYTEST, "-v", "--tb=short"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(_REPO),
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return -1, "", "pytest no encontrado. Instalá: pip install pytest"
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout después de {timeout}s"


def _run_unittest(args, timeout=120):
    """Ejecuta unittest."""
    cmd = [_VENV_PY, "-m", "unittest", "-v"] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(_REPO),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Timeout después de {timeout}s"


def test_runner(parameters: dict, player=None) -> str:
    """Ejecuta tests del proyecto."""
    action = str(parameters.get("action", "run")).lower().strip()
    path = str(parameters.get("path", "")).strip()
    pattern = str(parameters.get("pattern", "")).strip()
    timeout = int(parameters.get("timeout", 120))

    if action in ("detect", "detectar"):
        framework = _detect_framework()
        if framework:
            return f"🔍 Framework detectado: {framework}"
        return "No se detectó framework de tests. Creá tests/ o instalá pytest."

    if action in ("list", "ls", "ver"):
        """Lista archivos de tests."""
        test_files = []
        for pattern_g in ["test_*.py", "*_test.py", "tests/**/*.py"]:
            test_files.extend(_REPO.glob(pattern_g))
        if not test_files:
            return "No se encontraron archivos de tests."
        lines = [f"🧪 {len(test_files)} archivo(s) de tests:\n"]
        for f in sorted(test_files):
            lines.append(f"  📄 {f.relative_to(_REPO)}")
        return "\n".join(lines)

    if action in ("run", "ejecutar", "r"):
        framework = _detect_framework()
        if not framework:
            return ("No se detectó framework de tests. "
                    "Creá archivos test_*.py o instalá pytest: "
                    "pip install pytest")

        if player:
            player.write_log(f"🧪 Ejecutando tests ({framework})...")

        args = []
        if path:
            args.append(os.path.expanduser(path))
        elif pattern:
            args.extend(["-k", pattern])

        if framework == "pytest":
            rc, out, err = _run_pytest(args, timeout)
        else:
            rc, out, err = _run_unittest(args, timeout)

        lines = []
        if rc == 0:
            lines.append("✅ Todos los tests pasaron.")
        elif rc > 0:
            lines.append(f"⚠️ Tests fallaron (exit code: {rc}).")
        else:
            lines.append("❌ Error ejecutando tests.")

        if out.strip():
            lines.append(f"\n{out.strip()}")
        if err.strip() and rc != 0:
            lines.append(f"\n{err.strip()}")

        return "\n".join(lines)

    return "Acciones: detect/detectar, list/ls, run/ejecutar."


def run_tests(parameters: dict, player=None) -> str:
    """Wrapper: ejecuta todos los tests."""
    return test_runner({"action": "run"}, player=player)
