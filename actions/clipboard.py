"""clipboard.py — Portapapeles del sistema (copiar, pegar, limpiar).

En Wayland usa wl-clipboard (wl-copy/wl-paste); en X11, xclip/xsel;
última opción: pyperclip con timeout. 'wl-copy' queda vivo como dueño
del portapapeles hasta que lo reemplace otra copia (comportamiento normal).
"""
import shutil
import subprocess
import time

COPY_TIMEOUT = 8.0
PASTE_TIMEOUT = 8.0


def _has(cmd):
    return shutil.which(cmd) is not None


def _paste_wl():
    out = subprocess.run(
        ["wl-paste", "--no-newline", "--type", "text/plain"],
        capture_output=True, timeout=PASTE_TIMEOUT)
    return out.stdout.decode("utf-8", errors="replace").rstrip("\n") if out.returncode == 0 else None


def _paste_xclip():
    out = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                         capture_output=True, timeout=PASTE_TIMEOUT)
    return out.stdout.decode("utf-8", errors="replace").rstrip("\n") if out.returncode == 0 else None


def _copy_wl(text):
    p = subprocess.Popen(
        ["wl-copy", "--type", "text/plain"],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        p.stdin.write(text.encode("utf-8"))
        p.stdin.close()
    except Exception:
        pass
    time.sleep(0.15)
    return True


def _copy_xclip(text):
    subprocess.run(["xclip", "-selection", "clipboard", "-i"],
                   input=text.encode("utf-8"),
                   capture_output=True, timeout=COPY_TIMEOUT)
    return True


def clipboard(parameters: dict, player=None) -> str:
    """Accede al portapapeles del sistema: copiar, obtener o limpiar."""
    action = str(parameters.get("action", "get")).lower().strip()
    text = str(parameters.get("text", "") or parameters.get("content", ""))

    if action in ("get", "paste", "pegar", "leer"):
        value = None
        if _has("wl-paste"):
            value = _paste_wl()
        elif _has("xclip"):
            value = _paste_xclip()
        if value is None:
            try:
                import pyperclip
                value = pyperclip.paste()
            except Exception:
                value = None
        if value is None:
            if player:
                player.write_log("📋 No pude leer el portapapeles.")
            return "No pude leer el portapapeles en este entorno."
        preview = value[:200].replace("\n", " ")
        if player:
            player.write_log("📋 Portapapeles leído.")
        return (f"El portapapeles contiene ({len(value)} caracteres):\n{preview}"
                if value.strip() else "El portapapeles está vacío.")

    if action in ("copy", "set", "copiar", "poner"):
        if not text:
            return "Nada que copiar: pasá el texto en 'text'."
        if _has("wl-copy"):
            _copy_wl(text)
        elif _has("xclip"):
            _copy_xclip(text)
        else:
            try:
                import pyperclip
                pyperclip.copy(text)
            except Exception as e:
                return f"No pude copiar: {e}"
        if player:
            player.write_log("📋 Texto copiado al portapapeles.")
        return f"Copié al portapapeles ({len(text)} caracteres)."

    if action in ("clear", "vaciar", "limpiar"):
        if _has("wl-copy"):
            _copy_wl("")
        elif _has("xclip"):
            _copy_xclip("")
        else:
            try:
                import pyperclip
                pyperclip.copy("")
            except Exception:
                pass
        if player:
            player.write_log("📋 Portapapeles limpiado.")
        return "Limpié el portapapeles."

    return "Acción desconocida. Usá: get/paste, copy/set con 'text', o clear."
