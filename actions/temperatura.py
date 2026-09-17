# -*- coding: utf-8 -*-
"""temperatura.py — Temperatura del equipo por voz.

Usa WMI térmico (root/wmi MSAcpi_ThermalZoneTemperature, típico en
notebooks) y, si no hay sensores, avisa. Cada zona suele ser un componente
(CPU/placa); el valor llega en décimas de Kelvin.
"""
import os
import re
import subprocess


def _run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                           creationflags=0x08000000 if os.name == "nt" else 0)
        return (r.stdout or "")
    except Exception:
        return ""


def _sensores():
    out = _run(["powershell", "-NoProfile", "-Command",
                "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
                "Get-CimInstance -Namespace root/wmi -ClassName "
                "MSAcpi_ThermalZoneTemperature | ForEach-Object { "
                "{0}|{1}", "-f $_.InstanceName, $_.CurrentTemperature }"])
    sensores = []
    for linea in out.splitlines():
        partes = linea.split("|")
        if len(partes) >= 2 and partes[1].strip():
            try:
                kelvin = int(partes[1].strip()) / 10.0
            except ValueError:
                continue
            c = kelvin - 273.15
            nombre = "sensor"
            m = re.sub(r"^.*?_ACPI\\.*?ThermalZone_(.*)$", r"\1", partes[0], flags=re.IGNORECASE)
            if m and m != partes[0]:
                nombre = m
            sensores.append((nombre, c))
    return sensores


def temperatura(parameters: dict, player=None, speak=None) -> str:
    """Reporta la temperatura interna del equipo."""
    action = str(parameters.get("action", "estado")).strip().lower()

    if action in ("test",):
        return "El módulo de temperatura funciona."

    sensores = _sensores()
    if not sensores:
        return ("No encontré sensores térmicos accesibles (este equipo no "
                "expone MSAcpi_ThermalZone). Si te preocupa el calor, el "
                "uso de CPU/RAM está en 'specs'.")

    sal = []
    para_nia = []
    for nombre, c in sensores:
        estado = "fresco" if c < 60 else "normal" if c < 75 else "caliente" if c < 85 else "¡muy caliente!"
        sal.append(f"{nombre}: {c:.0f}°C ({estado})")
        para_nia.append(f"{nombre}: {c:.0f}°C")
    texto = "Temperaturas internas: " + ", ".join(sal) + "."
    if player:
        player.write_log("🌡️ " + "; ".join(para_nia))
    return texto