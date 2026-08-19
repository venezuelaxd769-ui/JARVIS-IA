"""git_control.py — Control de Git para Nia.

Operaciones de solo lectura (status, diff, log) y commit con mensaje
explícito. El commit solo se ejecuta cuando se llama con action=commit
y un message proporcionado. Nia debe mostrar el diff al usuario y pedir
confirmación ANTES de llamar a commit — el LLM maneja la conversación.
"""
import subprocess
from pathlib import Path

_TIMEOUT = 15.0
_REPO = Path(__file__).resolve().parent.parent


def _git(*args, timeout=_TIMEOUT):
    try:
        r = subprocess.run(
            ["git"] + list(args),
            cwd=_REPO,
            capture_output=True,
            timeout=timeout,
        )
        out = r.stdout.decode("utf-8", errors="replace").strip()
        err = r.stderr.decode("utf-8", errors="replace").strip()
        return out or err or "(sin salida)", r.returncode
    except subprocess.TimeoutExpired:
        return "Timeout: git tardó demasiado.", 1
    except Exception as e:
        return f"Error: {e}", 1


def _is_repo():
    out, rc = _git("rev-parse", "--is-inside-work-tree")
    return rc == 0 and "true" in out.lower()


def git_control(parameters: dict, player=None) -> str:
    """Interactúa con git: status, diff, log y commit."""
    if not _is_repo():
        return "No estoy en un repositorio git."

    action = str(parameters.get("action", "status")).lower().strip()

    if action in ("status", "estado"):
        out, _ = _git("status", "--short")
        if not out.strip:
            return "El repositorio está limpio, sin cambios."
        lines = out.strip().split("\n")
        summary = {
            "modificados": 0, "nuevos": 0, "borrados": 0, "otros": 0,
        }
        for l in lines:
            if l.startswith(" M") or l.startswith(" M"):
                summary["modificados"] += 1
            elif l.startswith("??"):
                summary["nuevos"] += 1
            elif l.startswith(" D") or l.startswith("D"):
                summary["borrados"] += 1
            else:
                summary["otros"] += 1
        header = (f"Git status: {len(lines)} archivo(s). "
                  f"Modificados: {summary['modificados']}, "
                  f"Nuevos: {summary['nuevos']}, "
                  f"Borrados: {summary['borrados']}.")
        if player:
            player.write_log(f"📋 {header}")
        preview = "\n".join(lines[:25])
        if len(lines) > 25:
            preview += f"\n... y {len(lines)-25} más."
        return f"{header}\n\n{preview}"

    if action in ("diff",):
        out, _ = _git("diff", "--stat")
        if not out.strip():
            out2, _ = _git("diff", "--cached", "--stat")
            if not out2.strip():
                return "Sin cambios para mostrar (ni staged ni unstaged)."
            full, _ = _git("diff", "--cached")
            return f"Staged:\n{out2}\n\n{full[:3000]}"
        full, _ = _git("diff")
        return f"Unstaged:\n{out}\n\n{full[:3000]}"

    if action in ("diff_staged", "staged"):
        out, _ = _git("diff", "--cached", "--stat")
        if not out.strip():
            return "No hay nada staged (git add)."
        full, _ = _git("diff", "--cached")
        return f"Staged:\n{out}\n\n{full[:3000]}"

    if action in ("log", "historial"):
        n = min(int(parameters.get("max_results", 10) or 10), 30)
        out, _ = _git("log", f"-{n}", "--oneline", "--decorate")
        return out if out.strip() else "Sin historial."

    if action in ("commit",):
        message = str(parameters.get("message", "")).strip()
        if not message:
            return ("Necesito un mensaje de commit (message). "
                    "Mostrame primero el diff y pedí confirmación al usuario.")
        # Verificar que hay algo staged
        staged, _ = _git("diff", "--cached", "--name-only")
        if not staged.strip():
            return ("No hay nada staged. Primero el usuario debe hacer "
                    "'git add' o indicarme qué archivos agregar.")
        # Ejecutar commit
        out, rc = _git("commit", "-m", message)
        if rc == 0:
            # Obtener el hash corto
            short, _ = _git("log", "-1", "--format=%h")
            if player:
                player.write_log(f"✅ Commit {short}: {message[:60]}")
            return f"Commit {short}: {message}"
        return f"Error al commitear:\n{out}"

    if action in ("branch", "branches"):
        out, _ = _git("branch", "-a")
        return out if out.strip() else "Sin branches."

    if action in ("add",):
        files = str(parameters.get("files", "")).strip()
        add_all = str(parameters.get("add_all", "")).lower() in ("true", "1", "yes", "si", "")
        if add_all or not files:
            out, rc = _git("add", "-A")
            if rc == 0:
                staged, _ = _git("diff", "--cached", "--name-only")
                count = len(staged.strip().split("\n")) if staged.strip() else 0
                if player:
                    player.write_log(f"📋 git add -A: {count} archivos staged")
                return f"Staged {count} archivo(s) con git add -A."
            return f"Error: {out}"
        else:
            file_list = [f.strip() for f in files.split(",") if f.strip()]
            out, rc = _git("add", *file_list)
            if rc == 0:
                if player:
                    player.write_log(f"📋 git add: {len(file_list)} archivos")
                return f"Staged {len(file_list)} archivo(s)."
            return f"Error: {out}"

    return ("Acciones: status, diff, diff_staged, log, commit, "
            "branch, add.")
