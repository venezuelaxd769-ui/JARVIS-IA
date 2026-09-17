# -*- coding: utf-8 -*-
"""eventos.py — Visor de eventos de Windows por voz.

Consulta el registro de eventos (Application/System) de los últimos días y
te devuelve los errores críticos y advertencias, agrupados por proveedor y
con los últimos mensajes. Útil para diagnosticar apagados, cuelgues o apps
que se cierran solas.
"""
import os
import subprocess

_NIVELES = {1: "crítico", 2: "error", 3: "advertencia", 4: "información", 5: "detalle"}


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=30,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return (r.stdout or ""), (r.stderr or ""), r.returncode
    except Exception as e:
        return "", str(e), -1


def _consulta(bitacora, dias, maxe):
    ps = "".join([
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;",
        "$ErrorActionPreference='Stop';",
        "$desde = (Get-Date).AddDays(-%d);" % dias,
        "$evs = Get-WinEvent -FilterHashtable @{LogName='%s'; Level=1,2; "
        "StartTime=$desde} -MaxEvents %d -ErrorAction SilentlyContinue;" % (bitacora, maxe),
        "if (-not $evs) { Write-Output 'SIN_EVENTOS'; exit };",
        "foreach ($e in $evs | Sort-Object TimeCreated -Descending) {",
        "   $msg = ($e.Message -replace \"[\\r\\n]+\", ' ');",
        "   if ($msg.Length -gt 130) { $msg = $msg.Substring(0,130) + '…' };",
        "   Write-Output ($e.TimeCreated.ToString('yyyy-MM-dd HH:mm') + '|' + "
        "$e.ProviderName + '|' + $e.Id + '|' + $msg);",
        "};",
    ])
    return _run(["powershell", "-NoProfile", "-Command", ps])


def _top_proveedores(lineas):
    conteo = {}
    for l in lineas:
        partes = l.split("|", 3)
        if len(partes) >= 3:
            conteo[partes[1]] = conteo.get(partes[1], 0) + 1
    top = sorted(conteo.items(), key=lambda kv: -kv[1])[:3]
    return ", ".join(f"{k} ({v})" for k, v in top) if top else ""


def eventos(parameters: dict, player=None, speak=None) -> str:
    """Lista los errores de Windows recientes para diagnosticar."""
    action = str(parameters.get("action", "semana")).strip().lower()
    if action in ("test",):
        return "El visor de eventos funciona."

    if action in ("hoy", "dia"):
        dias = 1
    elif action in ("semana", "siete"):
        dias = 7
    elif action == "mes":
        dias = 30
    else:
        return "Acciones: hoy | semana (default) | mes | test."

    bitacora = str(parameters.get("bitacora", "Application")).strip().lower()
    bitacora = "System" if bitacora.startswith("sistem") or bitacora == "sistema" else "Application"
    try:
        maxe = max(1, min(int(parameters.get("cantidad", 12)), 30))
    except ValueError:
        maxe = 12

    salida, err, rc = _consulta(bitacora, dias, maxe)
    if "SIN_EVENTOS" in salida:
        return f"En los últimos {dias} día(s) no hubo errores ni advertencias en la bitácora {bitacora}. ¡Todo tranquilo!"
    lineas = [l for l in salida.splitlines() if l.strip()]
    if not lineas:
        if rc != 0 and "Access denied" not in (err or "") and err:
            return f"No pude leer los eventos: {err[:150]}."
        return (f"No encontré eventos de {bitacora} en los últimos {dias} días "
                f"(puede que falte permiso o no haya registros).")

    top = _top_proveedores(lineas)
    encabezado = (f"Los últimos {len(lineas)} eventos problemáticos de la "
                  f"bitácora {bitacora} (últimos {dias} día(s)):")
    detalle = []
    for l in lineas[:maxe]:
        partes = l.split("|", 3)
        if len(partes) == 4:
            detalle.append(f"- {partes[0]}: {partes[1]} (ID {partes[2]}) -> {partes[3]}")
        else:
            detalle.append(f"- {l[:160]}")
    cuerpo = "\n".join(detalle)
    cola = f"Los que más aparecen: {top}." if top else ""
    if player:
        player.write_log("🛠️ " + encabezado + " " + cola)
    return "\n".join([encabezado, cuerpo, cola])