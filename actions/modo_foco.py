# -*- coding: utf-8 -*-
"""modo_foco.py — Modo concentración por voz (Windows).

Activa el No Molestar de Windows, y opcionalmente fuerza el cierre (y lo
mantiene cerrado) de las apps que distraen durante los minutos pedidos.
"""
import os
import subprocess
import threading
import time

_FOCUS_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "focus_state.json")

_thread = None
_stop = threading.Event()


def _notif_reg(val):
    try:
        import winreg
        with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings",
                0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "NOC_GLOBAL_SETTING_TOASTS_ENABLED", 0,
                              winreg.REG_DWORD, val)
        return True
    except Exception:
        return False


def _use_quiet_hours(val):
    try:
        import winreg
        with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\QuietHours",
                0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "Enabled", 0, winreg.REG_WORD, val)
        return True
    except Exception:
        return False


def _terminate_by_name(nombre):
    base = os.path.basename(nombre.strip().replace("\\", "/")).lower()
    if not base:
        return
    if not base.endswith(".exe"):
        base += ".exe"
    if any(c in base for c in ":/\\*?\"<>|"):
        return
    try:
        subprocess.run(["taskkill", "/F", "/T", "/IM", base],
                       capture_output=True, text=True, timeout=15,
                       creationflags=0x08000000)
    except Exception:
        pass


def _worker(apps, end_ts):
    while not _stop.is_set() and time.time() < end_ts:
        for app in apps:
            _terminate_by_name(app)
        time.sleep(45)


def _estado():
    try:
        import json
        with open(_FOCUS_FILE, encoding="utf-8") as f:
            st = json.load(f)
        restante = max(0, int(st.get("hasta", 0)) - int(time.time()))
        if restante <= 0:
            return "No hay sesión de foco activa."
        min_rest = restante // 60
        seg = restante % 60
        apps = ", ".join(st.get("apps", [])) or "ninguna app en lista"
        return (f"Modo foco activo por {min_rest} min {seg} s. "
                f"No Molestar: {'ON' if st.get('dnd') else 'OFF'}. "
                f"Apps bloqueadas: {apps}.")
    except Exception:
        return "No hay sesión de foco activa."


def modo_foco(parameters: dict, player=None, speak=None) -> str:
    """Modo concentración: No Molestar y bloquear apps que distraen."""
    global _thread, _stop
    import json
    action = str(parameters.get("action", "estado")).strip().lower()
    apps = parameters.get("apps") or []
    if isinstance(apps, str):
        apps = [a for a in apps.replace(" y ", ",").replace(",", " ").split() if a]
    apps = [a for a in apps if a.strip()]
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")
    if player:
        player.write_log(f"🎯 modo_foco: {action}")

    if action in ("estado", "status", "info"):
        return _estado()

    if action in ("terminar", "parar", "stop", "off", "apagar"):
        _stop.set()
        _thread = None
        _use_quiet_hours(0)
        _notif_reg(0)
        try:
            if os.path.exists(_FOCUS_FILE):
                os.remove(_FOCUS_FILE)
        except OSError:
            pass
        return "Listo, terminé el modo foco y volví a activar las notificaciones."

    if action in ("poner", "start", "on", "empezar"):
        minutos = max(1, int(parameters.get("minutos") or 25))
        if apps and not ok:
            return (f"El modo foco va a FORZAR el cierre de: {', '.join(apps)} "
                    f"durante {minutos} min. Confirmá con 'SÍ'.")
        dnd = str(parameters.get("dnd", "on")).strip().lower() not in ("off", "no", "0")
        hasta = int(time.time()) + minutos * 60
        dnd_ok = False
        if dnd:
            dnd_ok = _use_quiet_hours(1) or _notif_reg(1)
        _stop = threading.Event()
        _thread = threading.Thread(target=_worker, args=(apps, hasta), daemon=True)
        _thread.start()
        try:
            os.makedirs(os.path.dirname(_FOCUS_FILE), exist_ok=True)
            with open(_FOCUS_FILE, "w", encoding="utf-8") as f:
                json.dump({"hasta": hasta, "apps": apps, "dnd": dnd}, f)
        except OSError:
            pass
        bloqueo = (f" Y cada vez que abran {', '.join(apps)}, los vuelvo a cerrar."
                   if apps else "")
        dnd_msg = (" No Molestar activado." if dnd_ok else
                   " No pude activar el No Molestar de Windows, seguís recibiendo notificaciones.")
        return (f"Listo: modo foco por {minutos} minutos.{bloqueo}"
                f"{dnd_msg} Avisame 'terminá el foco' para cortar antes.")

    if action in ("agregar", "add"):
        return ("Para el modo foco usá 'poner' con minutos y apps. "
                "Ej: 'modo foco 40 minutos con Chrome y Discord'. Confirmá con SÍ si hay apps.")

    return ("Acciones: poner (minutos, apps, confirm='SÍ' si hay apps, dnd) | "
            "terminar | estado.")