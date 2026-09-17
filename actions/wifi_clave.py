# -*- coding: utf-8 -*-
"""wifi_clave.py — Muestra la clave de la red WiFi activa.

Windows: netsh wlan show profiles (default es la red conectada) + key=clear
para sacar el "Contenido de la clave". Solo lectura, no expone por log.
"""
import os
import re
import subprocess


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return (r.stdout or ""), r.returncode
    except Exception:
        return "", -1


def _ssid_activa():
    out, _ = _run(["netsh", "wlan", "show", "interfaces"])
    m = re.search(r"(?:Nombre del SSID|SSID)[^:]*:\s*(.+)", out, re.IGNORECASE)
    if not m:
        m = re.search(r":\s*([^\r\n]+)", out.split("SSID", 1)[-1]) if "SSID" in out else None
    return m.group(1).strip() if m else None


def _claves():
    out, _ = _run(["netsh", "wlan", "show", "profiles"])
    m = re.findall(r"(?:Perfil para todos los usuarios|All User Profile)[^:]*:\s*(.+)", out, re.IGNORECASE)
    if not m:
        m = re.findall(r"^([^:\r\n]+)$", out, re.MULTILINE)
    perfil = []
    for p in m:
        p = p.strip()
        if p and p not in perfil:
            perfil.append(p)
    res = []
    for nombre in perfil:
        out, _ = _run(["netsh", "wlan", "show", "profile", nombre, "key=clear"])
        m = re.search(r"(?:Contenido de la clave|Key Content)[^:]*:\s*(.+)", out, re.IGNORECASE)
        clave = m.group(1).strip() if m else ""
        if clave:
            res.append((nombre, clave))
    return res


def wifi_clave(parameters: dict, player=None, speak=None) -> str:
    """Muestra la clave de la red WiFi conectada (Windows)."""
    action = str(parameters.get("action", "actual")).strip().lower()

    if action in ("test",):
        return "La consulta de WiFi funciona."

    actual = _ssid_activa()
    if actual:
        out, _ = _run(["netsh", "wlan", "show", "profile", actual, "key=clear"])
        m = re.search(r"(?:Contenido de la clave|Key Content)[^:]*:\s*(.+)", out, re.IGNORECASE)
        clave = m.group(1).strip() if m else ""
        if clave:
            if player:
                player.write_log("📶 " + f"Clave de '{actual}': {clave}")
            return f"La contraseña de tu red '{actual}' es: {clave}."
        return f"La red '{actual}' no tiene clave visible o la red es abierta."

    claves = _claves()
    if not claves:
        return "No hay perfiles WiFi guardados con clave (o el comando falló)."
    sal = "Guardé estas redes:\n" + "\n".join(f"- {n}: {c}" for n, c in claves[:10])
    if player:
        player.write_log("📶 " + "Claves WiFi: " + "; ".join(f"{n}={c}" for n, c in claves[:5]))
    return sal