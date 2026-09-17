# -*- coding: utf-8 -*-
"""impresora.py — Impresoras e impresión de documentos por voz.

Lista impresoras instaladas (WMI Win32_Printer) e imprime archivos con el
manejador por defecto de Windows (os.startfile(..., 'print')). Imprimir
exige confirm='SÍ' para no mandar a imprimir por accidente.
"""
import os
import subprocess


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return (r.stdout or "")
    except Exception:
        return ""


def _impresoras():
    ps = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Get-CimInstance Win32_Printer | ForEach-Object { "
        "$e = 'no' ; if ($_.Default) { $e = 'default' } ; "
        "Write-Output ($_.Name + '|' + $e) }"
    )
    out = _run(["powershell", "-NoProfile", "-Command", ps])
    res = []
    for linea in out.splitlines():
        partes = linea.split("|")
        if len(partes) >= 2 and partes[0].strip():
            res.append((partes[0].strip(), partes[1].strip()))
    return res


def _resolver(entrada):
    p = str(entrada).strip()
    if os.path.exists(p) and os.path.isfile(p):
        return os.path.normpath(p)
    try:
        from actions.buscar import _roots, _buscar
        found, _ = _buscar(os.path.basename(p), "", _roots(None), 5)
        if found:
            return os.path.normpath(found[0][0])
    except Exception:
        pass
    return None


def impresora(parameters: dict, player=None, speak=None) -> str:
    """Lista impresoras e imprime documentos por voz."""
    action = str(parameters.get("action", "listar")).strip().lower()

    if action in ("test",):
        return "El módulo de impresión funciona."

    if action in ("listar", "impresoras", "ver"):
        lista = _impresoras()
        if not lista:
            return "No encontré impresoras instaladas en este equipo."
        sal = "Impresoras instaladas:\n" + "\n".join(
            f"- {n} ({'predeterminada' if s == 'default' else 'no default'})"
            for n, s in lista[:12])
        return sal

    if action in ("imprimir", "print"):
        arch = str(parameters.get("archivo", "") or parameters.get("documento", "")).strip()
        if not arch:
            return ("Decime qué documento, por ejemplo archivo='receta.pdf'.")
        if parameters.get("confirm", "").strip().upper() not in ("SI", "SÍ"):
            return "Para imprimir confirmame con confirm='SÍ'."
        p = _resolver(arch)
        if not p:
            return f"No encontré el archivo '{arch}'."
        nombre = str(parameters.get("impresora", "")).strip()
        try:
            if nombre:
                arg = nombre.replace("'", "''")
                cmd = "Start-Process -FilePath '{}' -Verb PrintTo -ArgumentList '{}'".format(p, arg)
                r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                                   capture_output=True, text=True, timeout=30)
                if r.returncode != 0 and r.stderr:
                    return f"No pude imprimir en '{nombre}': {r.stderr[:150]}."
            else:
                if os.name != "nt":
                    return "En este sistema imprimir sin impresora elegida no está soportado."
                os.startfile(p, "print")
        except Exception as e:
            return f"No pude imprimir '{os.path.basename(p)}': {e}."
        if player:
            player.write_log("🖨️ " + f"Enviado a imprimir: {os.path.basename(p)}")
        return (f"Envié '{os.path.basename(p)}' a la impresora"
                + (f" '{nombre}'." if nombre else " predeterminada."))

    return "Acciones: listar | imprimir (archivo, confirm='SÍ', impresora opcional)."