# -*- coding: utf-8 -*-
"""system_display.py — Pantalla, brillo y energía por voz (Windows).

Brillo (WMI, pantallas portátiles), planes de energía (powercfg), y
apagar/encender el monitor (WM_SYSCOMMAND SC_MONITORPOWER).
"""
import ctypes
import subprocess

_PLANES = {
    "balanced": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "balanceado": "381b4222-f694-41f0-9685-ff5bb260df2e",
    "ahorro": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "economico": "a1841308-3541-4fab-bc81-f71556f20b4a",
    "alto": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
    "rendimiento": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
}


def _powercfg(*args):
    try:
        r = subprocess.run(["powercfg.exe", *args], capture_output=True, text=True,
                           timeout=120, creationflags=0x08000000)
        return (r.returncode, r.stdout + r.stderr)
    except Exception:
        return (-1, "")


def _get_brightness():
    rc, out = _powercfg()
    try:
        cmd = ("Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness "
               "| Select-Object -ExpandProperty CurrentBrightness")
        r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=60,
                           creationflags=0x08000000)
        v = int((r.stdout or "").strip())
        return v if 0 <= v <= 100 else None
    except Exception:
        return None


def _set_brightness(n):
    n = max(0, min(100, int(n)))
    cmd = ("$m = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods; "
           f"$m.WmiSetBrightness(1, {n})")
    r = subprocess.run(["powershell.exe", "-NoProfile", "-Command", cmd],
                       capture_output=True, text=True, timeout=60,
                       creationflags=0x08000000)
    return r.returncode == 0, n


def _monitor(power):
    try:
        user32 = ctypes.windll.user32
        return user32.SendMessageW(0xFFFF, 0x0112, 0xF170, power)
    except Exception:
        return -1


def _current_plan():
    rc, out = _powercfg("/getactivescheme")
    return (out or "").strip() if rc == 0 else "desconocido"


def system_display(parameters: dict, player=None, speak=None) -> str:
    """Pantalla y energía: brillo, planes y apagar/encender monitor."""
    action = str(parameters.get("action", "estado")).strip().lower()
    valor = str(parameters.get("valor", "")).strip().lower()
    if player:
        player.write_log(f"🖥️  system_display: {action}")

    if action in ("estado", "info", "status"):
        br = _get_brightness()
        btxt = f"{br}%" if br is not None else "no disponible"
        return f"Brillo: {btxt}.\nPlan de energía: {_current_plan()}."

    if action in ("brillo", "brightness", "luma"):
        if not valor:
            br = _get_brightness()
            return f"El brillo está en {br}%." if br is not None else "No pude leer el brillo."
        ok, n = _set_brightness(valor)
        if not ok:
            return ("No pude cambiar el brillo (suele funcionar en notebooks). "
                    "Probá 'plan ahorro' o 'apagar_pantalla'.")
        return f"Brillo seteado al {n}%."

    if action in ("apagar_pantalla", "apagar", "off"):
        _monitor(2)
        return "Apagué el monitor. Mové el mouse o tocá una tecla para volver."

    if action in ("encender_pantalla", "encender", "on"):
        _monitor(-1)
        return "Encendí el monitor."

    if action in ("planes", "plan_list"):
        rc, out = _powercfg("/list")
        return out.strip() or "No pude listar los planes."

    if action in ("plan", "energy", "energia"):
        if not valor:
            return (f"Plan actual: {_current_plan()}.\n"
                    "Guías: balanced | ahorro | alto. Ej: plan='ahorro'.")
        guid = _PLANES.get(valor)
        if not guid:
            return "Planes: balanced, ahorro, alto."
        rc, out = _powercfg("/setactive", guid)
        return "Plan de energía cambiado." if rc == 0 else "No pude cambiar el plan."

    return "Acciones: estado | brillo (valor) | plan (balanced|ahorro|alto) | planes | apagar_pantalla | encender_pantalla."


if __name__ == "__main__":
    import sys
    p = {"action": sys.argv[1] if len(sys.argv) > 1 else "estado"}
    if len(sys.argv) > 2:
        p["valor"] = sys.argv[2]
    print(system_display(p))