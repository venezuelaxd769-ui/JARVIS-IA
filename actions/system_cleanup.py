# -*- coding: utf-8 -*-
"""system_cleanup.py — Limpieza y apps del equipo por voz (Windows).

Espacio en disco, borrar temporales, vaciar la papelera, carpetas más
pesadas y desinstalar/instalar/buscar programas con winget. Las acciones
destructivas piden confirmación (SÍ).
"""
import os
import shutil
import subprocess
import threading

_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")


def _winget():
    w = shutil.which("winget")
    if w:
        return w
    alias = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         r"Microsoft\WindowsApps\winget.exe")
    return alias if os.path.exists(alias) else None


def _fmt_b(b, dec=1):
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return f"{b:.{dec}f} {u}" if isinstance(b, float) else f"{b:.0f} {u}"
        b /= 1024.0


def _disk():
    lines = []
    for part in __import__("psutil").disk_partitions():
        if not part.fstype and not part.mountpoint.startswith("\\\\"):
            continue
        try:
            u = __import__("psutil").disk_usage(part.mountpoint)
            lines.append(f"   • {part.mountpoint} — {_fmt_b(u.free)} libre de {_fmt_b(u.total)} "
                         f"({_fmt_b(u.used)} usados)")
        except (OSError, PermissionError):
            continue
    return "💾 Discos:\n" + "\n".join(lines) if lines else "No pude leer los discos."


def _clean_temp():
    dirs = [os.environ.get("TEMP", ""), os.environ.get("TMP", ""),
            r"C:\Windows\Temp"]
    freed = 0
    for d in {x for x in dirs if x and os.path.isdir(x)}:
        for base, subs, files in os.walk(d, topdown=False):
            for f in files:
                try:
                    p = os.path.join(base, f)
                    sz = os.path.getsize(p)
                    os.remove(p)
                    freed += sz
                except OSError:
                    pass
            for s in subs:
                try:
                    os.rmdir(os.path.join(base, s))
                except OSError:
                    pass
    return (f"🧹 Eliminé {_fmt_b(freed)} de archivos temporales."
            if freed > 0 else "No había temporales para borrar (o están en uso).")


def _large_files(root, top=12, max_depth=3):
    found = []
    root = os.path.abspath(root)
    for base, subs, files in os.walk(root):
        depth = len(os.path.relpath(base, root).split(os.sep))
        if depth > max_depth:
            subs[:] = []
        subs[:] = [s for s in subs if s not in (".venv", "node_modules", "venv",
                                                ".git", "__pycache__", "Program Files")]
        for f in files:
            try:
                p = os.path.join(base, f)
                sz = os.path.getsize(p)
                if sz >= 10 * 1024 * 1024:
                    found.append((sz, p))
            except OSError:
                pass
        if len(found) > top * 4:
            found = sorted(found, reverse=True)[:top]
    found = sorted(found, reverse=True)[:top]
    if not found:
        return "No encontré archivos grandes (más de 10 MB) en esa carpeta."
    lines = [f"🏋️  Top {len(found)} archivos pesados en {root}:"]
    for sz, p in found:
        lines.append(f"   • {_fmt_b(sz, 2)} — {p}")
    return "\n".join(lines)


def _bg_run(cmd_args, on_done):
    def job():
        try:
            p = subprocess.run(cmd_args, capture_output=True, text=True, timeout=900,
                               creationflags=0x08000000)
            msg = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""
            done = f"Listo. {msg}" if p.returncode == 0 else f"No salió bien ({p.returncode}). {p.stderr[:200]}"
        except Exception as e:
            done = f"Fallo al ejecutar: {e}"
        try:
            on_done(done)
        except Exception:
            pass
    threading.Thread(target=job, daemon=True).start()


def system_cleanup(parameters: dict, player=None, speak=None) -> str:
    """Limpieza del equipo y apps (winget). Acciones destructivas: confirm='SÍ'."""
    action = str(parameters.get("action", "disco")).strip().lower()
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in _CONFIRM
    ruta = str(parameters.get("path", "")).strip()
    app = str(parameters.get("app", "")).strip()
    if player:
        player.write_log(f"🧹 system_cleanup: {action}")

    if action in ("disco", "espacio", "disks", "space"):
        return _disk()

    if action in ("temporales", "temp", "borrar_temp"):
        if not ok:
            return "Voy a borrar los archivos temporales del sistema. Confirmá con 'SÍ'."
        return _clean_temp()

    if action in ("papelera", "vaciar_papelera", "recycle"):
        if not ok:
            return "Voy a VACIAR la papelera de reciclaje. Confirmá con 'SÍ'."
        try:
            p = subprocess.run(["powershell.exe", "-NoProfile", "-Command",
                                "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"],
                               capture_output=True, timeout=120, creationflags=0x08000000)
            return "Papelera vaciada." if p.returncode == 0 else "No pude vaciar la papelera."
        except Exception as e:
            return f"No pude vaciar la papelera: {e}"

    if action in ("pesadas", "pesados", "grandes", "big"):
        root = ruta or os.path.expanduser("~")
        if not os.path.isdir(root):
            return f"No existe la carpeta '{root}'."
        return _large_files(root)

    if action in ("buscar_app", "buscar", "apps"):
        if not app:
            return "Decime qué app buscar (app)."
        w = _winget()
        if not w:
            return "No encontré winget en el sistema."
        try:
            r = subprocess.run([w, "list", "--name", app, "--accept-source-agreements"],
                               capture_output=True, text=True, timeout=120,
                               creationflags=0x08000000)
            lines = [l for l in (r.stdout or "").splitlines() if app.lower() in l.lower()]
            lines = lines[:10]
            return "🔍 Apps encontradas:\n" + "\n".join(f"   • {l.strip()}" for l in lines) if lines else f"No encontré '{app}' instalada."
        except Exception as e:
            return f"No pude buscar: {e}"

    if action in ("instalar", "install"):
        if not app:
            return "Decime qué app instalar (app). Ej: 'instalar' con app='Spotify'."
        w = _winget()
        if not w:
            return "No encontré winget."
        args = [w, "install", "--name", app, "--silent", "--exact",
                "--accept-source-agreements", "--accept-package-agreements"]
        if speak:
            _bg_run(args, lambda msg: speak(f"Instalación de {app}: {msg}"))
            return f"Arranqué a instalar '{app}' en segundo plano. Te aviso cuando termine."
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=1200,
                               creationflags=0x08000000)
            return ("Instalado." if r.returncode == 0 else f"No se pudo instalar: {r.stderr[:200]}")
        except Exception as e:
            return f"No pude instalar: {e}"

    if action in ("desinstalar", "uninstall"):
        if not app:
            return "Decime qué app desinstalar (app)."
        if not ok:
            return f"Voy a DESINSTALAR '{app}'. Confirmá con 'SÍ'."
        w = _winget()
        if not w:
            return "No encontré winget."
        args = [w, "uninstall", "--name", app, "--silent", "--exact",
                "--accept-source-agreements", "--accept-package-agreements"]
        if speak:
            _bg_run(args, lambda msg: speak(f"Desinstalación de {app}: {msg}"))
            return f"Arranqué a desinstalar '{app}' en segundo plano. Aviso cuando termine."
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=1200,
                               creationflags=0x08000000)
            return ("Desinstalado." if r.returncode == 0 else f"No se pudo desinstalar: {r.stderr[:200]}")
        except Exception as e:
            return f"No pude desinstalar: {e}"

    return ("Acciones: disco | temporales (SÍ) | papelera (SÍ) | pesadas (path) | "
            "buscar_app (app) | instalar (app) | desinstalar (app + SÍ).")


if __name__ == "__main__":
    import sys
    p = {"action": sys.argv[1] if len(sys.argv) > 1 else "disco"}
    if len(sys.argv) > 2:
        p["app"] = sys.argv[2]
    print(system_cleanup(p))