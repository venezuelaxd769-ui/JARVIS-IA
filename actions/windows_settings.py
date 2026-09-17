# -*- coding: utf-8 -*-
"""windows_settings.py — configuración de Windows REAL (subset honesto).

Implementa solo lo que es seguro y verificable sin admin:
  info, battery, get/set_brightness (WMI), lock, sleep, hibernate,
  fast_startup (get/set, si hay permiso), monitor_timeout y suspend_timeout
  (powercfg, esquema activo).

Todo lo demás devuelve un aviso honesto: "no implementado". Nia no inventa.
"""

import os
import platform
import re
import subprocess


def _run(cmd: list, timeout: float = 20.0) -> tuple[str, int]:
    """Ejecuta un comando sin ventanas de consola y devuelve (stdout, code)."""
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout, errors="replace", **kwargs)
        return (r.stdout or "").strip(), r.returncode
    except Exception as e:
        return f"error:{e}", -1


def _ps(script: str) -> str:
    out, _ = _run(["powershell", "-NoProfile", "-NonInteractive",
                   "-ExecutionPolicy", "Bypass", "-Command", script])
    return out.strip()


def _is_windows() -> bool:
    return os.name == "nt"


def _wmi(script: str) -> str:
    if not _is_windows():
        return "NO_SOPORTADO"
    return _ps(script)


def _info() -> str:
    try:
        import psutil
        have_psutil = True
    except Exception:
        have_psutil = False
    import getpass

    lines = []
    try:
        lines.append(f"Sistema: {platform.system()} {platform.release()} ({platform.version()})")
    except Exception:
        pass
    try:
        lines.append(f"PC: {getpass.getuser()}@{platform.node()}")
    except Exception:
        pass
    if have_psutil:
        try:
            lines.append(f"CPU: {psutil.cpu_count(logical=True)} núcleos lógicos")
        except Exception:
            pass
        try:
            gb = psutil.virtual_memory().total / (1024 ** 3)
            lines.append(f"RAM total: {gb:.1f} GB")
        except Exception:
            pass
        try:
            lines.append(f"Encendida hace: {int(psutil.boot_time() and __import__('time').time() - psutil.boot_time())} s")
        except Exception:
            pass
    return "\n".join(lines) or "No pude leer la info del sistema."


def _battery() -> str:
    raw = _wmi(
        "$b = Get-CimInstance -ClassName Win32_Battery; "
        "if ($b) { '{0};{1}' -f $b.BatteryStatus, $b.EstimatedChargeRemaining } else { 'NO_BATTERY' }"
    )
    if not raw or raw in ("NO_SOPORTADO", "NO_BATTERY"):
        return "No hay batería o este equipo no informa estado (escritorio de línea o WMI limitado)."
    parts = raw.split(";")
    try:
        status_code = int(parts[0]) if parts[0:1] else 0
        level = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else -1
    except Exception:
        status_code, level = 0, -1
    estados = {
        1: "a batería", 2: "enchufada", 3: "cargada",
        4: "baja", 5: "crítica", 6: "cargando", 7: "cargando",
        8: "cargando", 9: "cargando",
    }
    estado = estados.get(status_code, "estado desconocido")
    nivel = f"{level}%" if level >= 0 else "?"
    return f"Batería al {nivel} ({estado})."


def _get_brightness() -> str:
    raw = _wmi(
        "$m = Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorBrightness; "
        "if ($m) { $m.CurrentBrightness } else { 'NO_SOPORTADO' }"
    )
    if raw and raw != "NO_SOPORTADO" and raw.isdigit():
        return f"Brillo actual: {raw}%."
    return "Este monitor no informa brillo por WMI (algunos monitores externos no lo soportan)."


def _set_brightness(value) -> str:
    try:
        level = max(0, min(100, int(value)))
    except Exception:
        return "Indicame el brillo como un número de 0 a 100."
    raw = _wmi(
        "$m = Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorBrightnessMethods; "
        f"if ($m) {{ $m.WmiSetBrightness(1, {level}) ; 'OK' }} else {{ 'NO_SOPORTADO' }}"
    )
    if raw == "OK":
        return f"Brillo ajustado a {level}%."
    if raw == "NO_SOPORTADO":
        return "Este monitor no soporta setear brillo por WMI. ¿Querés que lo deje tal cual?"
    return f"No pude ajustar el brillo (respuesta del sistema: {raw[:80]})."


def _lock() -> str:
    out, code = _run(["rundll32.exe", "user32.dll,LockWorkStation"])
    return ("Sesión bloqueada.") if code == 0 else (
        f"No pude bloquear la sesión (code {code}).")


def _sleep() -> str:
    out, code = _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    return ("Equipo a dormir.") if code == 0 else (
        f"No pude suspender (code {code}).")


def _hibernate() -> str:
    out, code = _run(["shutdown", "/h"])
    if code == 0:
        return "Equipo en hibernación."
    return "No pude hibernar (¿está habilitada la hibernación?). Puede requerir 'powercfg /hibernate on' como admin."


def _fast_startup_get() -> str:
    out, code = _run([
        "reg", "query",
        r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power",
        "/v", "HiberbootEnabled",
    ])
    if code == 0 and re.search(r"0x([0-9a-fA-F]+)", out):
        return "Inicio rápido: ACTIVADO." if int(re.search(r"0x([0-9a-fA-F]+)", out).group(1), 16) == 1 \
            else "Inicio rápido: desactivado."
    return "No pude leer el estado del inicio rápido."


def _fast_startup_set(value) -> str:
    try:
        on = int(value)
    except Exception:
        on = 1 if str(value).lower() in ("on", "1", "true", "sí", "si", "activar") else 0
    if str(value).lower() in ("off", "0", "false", "no", "desactivar"):
        on = 0
    out, code = _run([
        "reg", "add", r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Power",
        "/v", "HiberbootEnabled", "/t", "REG_DWORD", "/d", str(1 if on else 0), "/f",
    ])
    if code == 0 and "ERROR" not in out.upper():
        return "Inicio rápido ACTIVADO (se aplicará en el próximo arranque)." if on else \
            "Inicio rápido desactivado."
    return "No tengo permisos para cambiar el inicio rápido (necesito admin). Te digo el estado, y si querés lo hacés a mano."


def _power_timeout_get(kind: str) -> str:
    out, code = _run(["powercfg.exe", "/query", "SCHEME_CURRENT"])
    label = "pantalla" if kind == "VIDEOIDLE" else "reposo"
    if code != 0 or kind not in out:
        return f"No pude leer el timeout de {label}."
    rest = out[out.find(kind):]
    m = re.search(r"0x([0-9a-fA-F]+)", rest)
    if not m:
        return f"No encontré el valor de {label} en el esquema."
    seconds = int(m.group(1), 16)
    minutes = seconds // 60
    if seconds == 0:
        return f"Timeouts de {label}: NUNCA (el esquema no apaga la pantalla)."
    return f"Timeout de {label} (enchufado): {minutes} min."


def _power_timeout_set(kind: str, minutes) -> str:
    label = "pantalla" if kind == "VIDEOIDLE" else "reposo"
    try:
        minutes = int(minutes)
    except Exception:
        return f"Indicame los minutos para el timeout de {label}."
    switch = "monitor-timeout-ac" if kind == "VIDEOIDLE" else "standby-timeout-ac"
    out, code = _run(["powercfg.exe", "/change", switch, str(minutes)])
    if code == 0 and "ERROR" not in out.upper():
        how = "NUNCA apagar la pantalla" if minutes == 0 else f"apagar tras {minutes} min"
        return f"Listo: {how} (enchufado)."
    return f"No pude cambiar el timeout (code {code}). {out[:80]}"


_NOT_IMPLEMENTED = (
    "Esa acción de configuración aún no está implementada en Windows; no te invento un resultado. "
    "Las implementadas son: info, battery, get/set_brightness, lock, sleep, hibernate, "
    "fast_startup_get, fast_startup_set, monitor_timeout y suspend_timeout."
)


def windows_settings(parameters: dict, player=None) -> str:
    if not _is_windows():
        return "windows_settings solo aplica en Windows y este equipo no es Windows."
    action = (parameters or {}).get("action", "") or ""
    value = parameters.get("value", "")
    sub = str(parameters.get("value2", "") or "").lower()

    name = action.lower().replace("_", "")

    if name in ("info", "system", "systeminfo"):
        return _info()
    if name in ("battery", "batterystatus"):
        return _battery()
    if name in ("getbrightness", "brightness"):
        return _get_brightness()
    if name in ("setbrightness", "setbrillo"):
        return _set_brightness(value)
    if name in ("lock", "bloquear"):
        return _lock()
    if name in ("sleep", "suspend", "suspendersession", "suspender"):
        return _sleep()
    if name in ("hibernate", "hibernar"):
        return _hibernate()
    if name in ("faststartupget",):
        return _fast_startup_get()
    if name in ("faststartupset",):
        return _fast_startup_set(value)
    if name in ("monitortimeout", "screentimeout", "displaytimeout"):
        return _power_timeout_set("VIDEOIDLE", value) if sub == "set" else _power_timeout_get("VIDEOIDLE")
    if name in ("suspendtimeout", "sleeptimeout", "standbytimeout"):
        return _power_timeout_set("STANDBYIDLE", value) if sub == "set" else _power_timeout_get("STANDBYIDLE")

    return _NOT_IMPLEMENTED