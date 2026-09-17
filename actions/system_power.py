# -*- coding: utf-8 -*-
"""system_power.py — Energía del equipo por voz (Windows).

Apagar, reiniciar, suspender, hibernar, bloquear o cerrar la sesión,
con retardo opcional y confirmación explícita para no apagar nada por error.
"""
import ctypes
import os
import subprocess

_IS_WIN = os.name == "nt"
_OK_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")


def _ps(cmd_args):
    kw = {}
    if _IS_WIN:
        kw["creationflags"] = 0x08000000
    try:
        r = subprocess.run(
            cmd_args, capture_output=True, text=True, timeout=30, **kw
        )
        out = (r.stdout or "").strip() + (" " + r.stderr.strip() if r.stderr else "")
        return r.returncode, out
    except Exception as e:
        return None, str(e)


def _battery():
    if not _IS_WIN:
        return None, None
    class _SPS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_uint8),
            ("BatteryFlag", ctypes.c_uint8),
            ("BatteryLifePercent", ctypes.c_uint8),
            ("SystemStatusFlag", ctypes.c_uint8),
            ("BatteryLifeTime", ctypes.c_uint32),
            ("BatteryFullLifeTime", ctypes.c_uint32),
        ]
    sps = _SPS()
    try:
        ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps))
    except Exception:
        return None, None
    if not ok:
        return None, None
    ac = "enchufado" if sps.ACLineStatus == 1 else None
    if sps.ACLineStatus == 0:
        ac = "desenchufado"
    pct = int(sps.BatteryLifePercent)
    if pct == 255:
        pct = None
    return ac, pct


def _seconds(delay):
    try:
        m = max(0, min(600, int(float(delay))))
        if "delay" not in ("",) or delay is not None:
            return int(m * 60)
    except (TypeError, ValueError):
        pass
    return 0


def system_power(parameters: dict, player=None, speak=None) -> str:
    """Energía y sesión del equipo: apagar, reiniciar, suspender, hibernar,
    bloquear, cerrar sesión o consultar el estado. Confirmá con SÍ."""
    action = str(parameters.get("action", "estado")).strip().lower()
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in _OK_CONFIRM
    delay = parameters.get("delay", 0)
    if player:
        player.write_log(f"⚡ system_power: {action} (confirm={ok})")

    if action in ("estado", "info", "bateria", "batería"):
        if not _IS_WIN:
            return "Solo en Windows gestiono la energía."
        ac, pct = _battery()
        linea = "PC de escritorio (sin batería)" if pct is None else f"Batería al {pct}%"
        if ac:
            linea += f", {ac}"
        return "⚡ " + linea + "." if not linea.endswith(".") else "⚡ " + linea

    if action in ("cancelar", "cancel"):
        code, out = _ps(["shutdown.exe", "/a"])
        return ("Cancelé el apagado programado." if code == 0
                else "No había ningún apagado programado para cancelar.")

    if action in ("apagar", "shutdown", "off"):
        if not ok:
            return "Estoy por APAGAR el equipo. Confirmá con action='SÍ' (respuesta 'SÍ' bastará)."
        secs = _seconds(delay) or 0
        code, out = _ps(["shutdown.exe", "/s", "/t", str(secs)])
        return ("Apago el equipo" + (" en %d minutos." % (secs // 60) if secs else " ahora mismo.")
                if code == 0 else f"No pude apagar: {out}")

    if action in ("reiniciar", "restart", "reboot"):
        if not ok:
            return "Estoy por REINICIAR el equipo. Confirmá con 'SÍ'."
        secs = _seconds(delay) or 0
        code, out = _ps(["shutdown.exe", "/r", "/t", str(secs)])
        return ("Reinicio el equipo" + (" en %d minutos." % (secs // 60) if secs else " ahora mismo.")
                if code == 0 else f"No pude reiniciar: {out}")

    if not _IS_WIN:
        return "Solo en Windows controlo la energía."

    if action in ("suspender", "susp", "dormir"):
        code = ctypes.windll.powrprof.SetSuspendState(0, 0, 0)
        return "Pongo el equipo a dormir." if code else "No pude suspender el equipo."

    if action in ("hibernar", "hiber"):
        code = ctypes.windll.powrprof.SetSuspendState(1, 0, 0)
        return "Hiberno el equipo." if code else "No pude hibernar (¿la hibernación está activada?)."

    if action in ("bloquear", "lock", "candado"):
        ok_lock = ctypes.windll.user32.LockWorkStation()
        return "Bloqueé la sesión." if ok_lock else "No pude bloquear la pantalla."

    if action in ("cerrar_sesion", "logout", "salir"):
        code = ctypes.windll.user32.ExitWindowsEx(0, 0)
        return "Cierro la sesión." if code else "No pude cerrar la sesión (necesito permiso de administrador)."

    return ("Acciones: estado | apagar | reiniciar | suspender | hibernar | "
            "bloquear | cerrar_sesion | cancelar. Para apagar/reiniciar confirmá con confirm='SÍ'.")


if __name__ == "__main__":
    import sys
    print(system_power({"action": sys.argv[1] if len(sys.argv) > 1 else "estado"}))