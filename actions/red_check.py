# -*- coding: utf-8 -*-
"""red_check.py — Chequeo rápido de conexión por voz.

Latencia (ping al router y a Google), IP pública + ubicación aproximada
(ipify + ip-api, sin claves) y señal WiFi (netsh). Sin instalar nada.
"""
import json
import os
import re
import subprocess
import urllib.request


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return r.stdout or "", r.returncode
    except Exception:
        return "", -1


def _gw():
    for cmd in (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;(Get-NetIPConfiguration | "
        "Where-Object { $_.IPv4DefaultGateway } | Select-Object -First 1).IPv4DefaultGateway.NextHop",
        "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | "
        "Select-Object -First 1).NextHop.IPAddressToString",
    ):
        out, _ = _run(["powershell", "-NoProfile", "-Command", cmd])
        gw = (out or "").strip()
        if gw:
            return gw
    return None


def _ping(host):
    out, _ = _run(["ping", "-n", "4", host])
    prom = None
    perdida = None
    m = re.search(r"(?:Media|Promedio|Average)\s*=\s*([0-9]+)ms", out, re.IGNORECASE)
    if m:
        prom = int(m.group(1))
    m = re.search(r"\(([0-9]+)%\s*\S*[Pp]erd[^)]*\)", out, re.IGNORECASE)
    if not m:
        m = re.search(r"\(([0-9]+)%\s*\S*[Ll]oss\s*\)", out, re.IGNORECASE)
    if m:
        perdida = int(m.group(1))
    return prom, perdida


def _pub_ip():
    try:
        with urllib.request.urlopen("https://api.ipify.org?format=json", timeout=5) as r:
            return json.loads(r.read().decode("utf-8")).get("ip")
    except Exception:
        return None


def _geo(ip):
    try:
        with urllib.request.urlopen(f"http://ip-api.com/json/{ip}?fields=country,city,isp", timeout=5) as r:
            d = json.loads(r.read().decode("utf-8"))
        if d.get("status") != "success":
            return None
        return f"{d.get('city')}, {d.get('country')} ({d.get('isp')})"
    except Exception:
        return None


def _wifi_signal():
    out, _ = _run(["netsh", "wlan", "show", "interfaces"])
    if not out:
        return None
    m = re.search(r"(?:Se\s*n\s*al|Signal)[^:\n]*:\s*([0-9]+)%", out, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+)%", out)
    return int(m.group(1)) if m else None


def red_check(parameters: dict, player=None, speak=None) -> str:
    """Chequea la conexión: latencia, IP pública y señal WiFi."""
    action = str(parameters.get("action", "chequear")).strip().lower()
    if action in ("test", "chequear"):
        pass
    elif action not in ("probar", "estado", "diagnostico"):
        return "Acciones: chequear | probar | estado."

    lineas = ["Pico pepe, acá va el estado de tu conexión."]
    gw = _gw()
    if gw:
        prom, perd = _ping(gw)
        if prom is not None:
            lineas.append(f"Router (su puerta de enlace): {prom} ms de promedio"
                          + (f", {perd}% pérdida" if perd else "") + ".")
        else:
            lineas.append("No pude medir la latencia al router.")
    else:
        lineas.append("No encontré la puerta de enlace por defecto.")

    prom, perd = _ping("8.8.8.8")
    if prom is not None:
        lineas.append(f"Internet (Google): {prom} ms" +
                      (f" con {perd}% pérdida de paquetes." if perd else "."))
        if perd and perd >= 10:
            lineas.append("Esa pérdida alta sugiere que la señal está floja.")
    else:
        lineas.append("No respondió el ping a Google: puede haber cortes.")

    ip = _pub_ip()
    if ip:
        geo = _geo(ip)
        lineas.append(f"Tu IP pública es {ip}" + (f" ({geo})." if geo else "."))
    else:
        lineas.append("No pude conseguir tu IP pública.")

    sen = _wifi_signal()
    if sen is not None:
        calif = "excelente" if sen >= 80 else "buena" if sen >= 60 else "regular" if sen >= 40 else "floja"
        lineas.append(f"Señal WiFi: {sen}% ({calif}).")

    if player:
        player.write_log("🌐 " + " ".join(lineas))
    return "\n".join(lineas)