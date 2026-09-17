# -*- coding: utf-8 -*-
"""specs.py — Reporte del hardware del equipo por voz.

CPU (modelo + núcleos), RAM total, disco principal, GPU, sistema operativo
y hostname. CPU/GPU/OS vienen de WMI vía PowerShell (con salida UTF-8).
"""
import json
import os
import platform
import subprocess


def _cim(cmd):
    try:
        ps = (
            "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            + cmd
        )
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=10,
        )
        out = r.stdout.decode("utf-8", errors="replace").strip()
        return out or None
    except Exception:
        return None


def _un_trucho():
    return dict(
        cpu=None, cores=None, ram=None, disco=None,
        gpu=None, os=None, host=platform.node().split(".")[0],
    )


def _reporte():
    d = _un_trucho()
    try:
        import psutil
        d["ram"] = psutil.virtual_memory().total
        d["disco"] = psutil.disk_usage(os.path.expanduser("~")).total
        d["cores"] = (psutil.cpu_count(logical=False) or "?", psutil.cpu_count(logical=True) or "?")
    except Exception:
        pass
    cpu = _cim("(Get-CimInstance Win32_Processor).Name")
    gpu = _cim("(Get-CimInstance Win32_VideoController).Name")
    so = _cim("(Get-CimInstance Win32_OperatingSystem).Caption")
    if cpu:
        d["cpu"] = cpu.strip()
    if gpu:
        gpu = gpu.strip().splitlines()
        d["gpu"] = " / ".join(g.strip() for g in gpu if g.strip()) or None
    if so:
        vers = _cim("(Get-CimInstance Win32_OperatingSystem).Version")
        d["os"] = so.strip() + (f" (build {vers.strip()})" if vers and vers.strip() else "")
    return d


def _gb(n):
    if not n:
        return "?"
    return f"{round(int(n) / (1024 ** 3), 1)} GB"


def specs(parameters: dict, player=None, speak=None) -> str:
    """Reporta los specs del equipo (CPU, RAM, disco, GPU, SO)."""
    action = str(parameters.get("action", "reporte")).strip().lower()
    if action not in ("reporte", "todo", "specs", "equipo"):
        return "Acciones: reporte."
    d = _reporte()
    cpu = d["cpu"] or "no disponible"
    cores_p, cores_l = d["cores"] if isinstance(d["cores"], tuple) else ("?", "?")
    lineas = [
        f"Hola, acá va tu equipo.",
        f"Procesador: {cpu}, con {cores_p} núcleos físicos y {cores_l} lógicos.",
        f"Memoria RAM: {_gb(d['ram'])}.",
        f"Disco principal: {_gb(d['disco'])}.",
    ]
    if d["gpu"]:
        lineas.append(f"Placa de video: {d['gpu']}.")
    lineas.append(f"Sistema: {d['os']}.")
    if d["host"]:
        lineas.append(f"El equipo se llama {d['host']}.")
    texto = "\n".join(lineas)
    if player:
        player.write_log("🖥️ " + texto.replace("\n", " · "))
    return texto