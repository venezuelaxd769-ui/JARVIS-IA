# -*- coding: utf-8 -*-
"""system_services.py — Servicios de Windows por voz.

Listar, consultar, iniciar, detener, reiniciar, habilitar o deshabilitar
servicios. Iniciar/detener de servicios del sistema puede requerir
permisos de administrador.
"""
import json
import os
import re
import subprocess

_IS_WIN = os.name == "nt"
_NAME_RE = re.compile(r"^[\w.\- ]+$")


def _ps(cmd):
    kw = {}
    if _IS_WIN:
        kw["creationflags"] = 0x08000000
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", "[Console]::OutputEncoding=[Text.Encoding]::UTF8;" + cmd],
            capture_output=True, timeout=40, **kw)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        return r.returncode, out, err
    except Exception as e:
        return None, "", str(e)


def _valid_name(name):
    return bool(name) and bool(_NAME_RE.match(name))


def _list():
    code, out, err = _ps(
        "Get-Service | Sort-Object Status -Descending | "
        "Select-Object -First 30 Name,Status,DisplayName | ConvertTo-Json -Compress")
    if code != 0 or not out.strip():
        return "No pude listar los servicios."
    try:
        items = json.loads(out)
    except json.JSONDecodeError:
        return "No pude leer el listado de servicios."
    if not isinstance(items, list):
        items = [items]
    if not items:
        return "No hay servicios."
    est = {1: "detenido", 2: "arrancando", 3: "deteniendo", 4: "activo",
           5: "continuando", 6: "pausando", 7: "pausado",
           "Running": "activo", "Stopped": "detenido", "StartPending": "arrancando",
           "StopPending": "deteniendo", "Paused": "pausado", "Disabled": "deshabilitado"}
    def _est(k):
        try:
            return est.get(int(k), str(k))
        except (TypeError, ValueError):
            return est.get(k, str(k))
    lines = [f"📋 {len(items)} servicios principales:"]
    for it in items:
        lines.append(f"   • {it.get('Name','?')} — {_est(it.get('Status','?'))} — {it.get('DisplayName','')[:60]}")
    return "\n".join(lines)


def _service_cmd(verb, name):
    code, out, err = _ps(f"Get-Service -Name '{name}' | Select-Object Name,Status,DisplayName | ConvertTo-Json -Compress")
    if code != 0 or not out.strip():
        return f"No encontré el servicio '{name}'."
    try:
        it = json.loads(out)
    except json.JSONDecodeError:
        return f"No pude leer el servicio '{name}'."
    return (f"Servicio '{name}': {_status_text(it.get('Status','?'))} — {it.get('DisplayName','')[:60]}")


def _status_text(status):
    est = {1: "detenido", 2: "arrancando", 3: "deteniendo", 4: "activo",
           5: "continuando", 6: "pausando", 7: "pausado",
           "Running": "activo", "Stopped": "detenido", "StartPending": "arrancando",
           "StopPending": "deteniendo", "Paused": "pausado", "Disabled": "deshabilitado"}
    try:
        intv = int(status)
    except (TypeError, ValueError):
        intv = None
    if intv is not None:
        return est.get(intv, str(status))
    return est.get(status, str(status))


def system_services(parameters: dict, player=None, speak=None) -> str:
    """Servicios de Windows: listar, estado, iniciar, detener, reiniciar,
    habilitar o deshabilitar. Algunos cambios requieren administrador."""
    action = str(parameters.get("action", "listar")).strip().lower()
    name = str(parameters.get("name", "")).strip()
    if player:
        player.write_log(f"🛠 system_services: {action} {name}")
    if not _IS_WIN:
        return "Solo en Windows gestiono servicios."

    if action in ("listar", "list", "ls"):
        return _list()

    if action in ("estado", "info", "ver"):
        if not _valid_name(name):
            return "Necesito el nombre del servicio (ej. 'estado' con name='Spooler')."
        return _service_cmd("estado", name)

    if not _valid_name(name):
        return "Necesito el nombre del servicio para esta acción (ej. name='Spooler')."

    if action in ("iniciar", "start", "arrancar"):
        code, out, err = _ps(f"Start-Service -Name '{name}'; (Get-Service -Name '{name}').Status")
        if code == 0:
            return f"Servicio '{name}' iniciado ({out.strip()})."
        return f"No pude iniciar '{name}': {err or out}"

    if action in ("detener", "stop", "parar"):
        code, out, err = _ps(f"Stop-Service -Name '{name}' -Force; (Get-Service -Name '{name}').Status")
        if code == 0:
            return f"Servicio '{name}' detenido ({out.strip()})."
        return f"No pude detener '{name}': {err or out}"

    if action in ("reiniciar", "restart"):
        code, out, err = _ps(f"Restart-Service -Name '{name}' -Force; (Get-Service -Name '{name}').Status")
        if code == 0:
            return f"Servicio '{name}' reiniciado ({out.strip()})."
        return f"No pude reiniciar '{name}': {err or out}"

    if action in ("habilitar", "enable", "auto"):
        code, out, err = _ps(f"Set-Service -Name '{name}' -StartupType Automatic")
        if code == 0:
            return f"Servicio '{name}' habilitado (arranca automático)."
        return f"No pude habilitar '{name}' (¿administrador?): {err or out}"

    if action in ("deshabilitar", "disable"):
        code, out, err = _ps(f"Set-Service -Name '{name}' -StartupType Disabled; Stop-Service -Name '{name}' -Force -ErrorAction SilentlyContinue")
        if code == 0:
            return f"Servicio '{name}' deshabilitado y detenido."
        return f"No pude deshabilitar '{name}' (¿administrador?): {err or out}"

    return ("Acciones: listar | estado | iniciar | detener | reiniciar | "
            "habilitar | deshabilitar (con name='NombreDelServicio').")


if __name__ == "__main__":
    import sys
    print(system_services({"action": sys.argv[1] if len(sys.argv) > 1 else "listar",
                           "name": sys.argv[2] if len(sys.argv) > 2 else ""}))