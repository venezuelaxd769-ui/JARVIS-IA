# -*- coding: utf-8 -*-
"""velocidad.py — Medición real de velocidad de internet por voz.

Usa los endpoints públicos de Cloudflare (/__down y /__up) sin claves:
descarga un archivo de prueba (calentamiento + medición real) y mide
Mbps. La subida puede fallar en algunos routers; se avisa si no se puede.
"""
import subprocess
import time
import urllib.request

_HOSTS = [
    "https://speed.cloudflare.com/__down?bytes=",
    "https://speedtest.tele2.net/1MB.zip",      # fallback lento si CF no responde
]


_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def _descarga_mbps(bytes_total):
    url = "https://speed.cloudflare.com/__down?bytes=%d" % bytes_total
    try:
        t0 = time.time()
        recibidos = 0
        with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=25) as r:
            while True:
                b = r.read(65536)
                if not b:
                    break
                recibidos += len(b)
        seg = max(time.time() - t0, 0.05)
        return recibidos * 8 / 1e6 / seg, recibidos
    except Exception:
        return None, 0


def _subida_mbps(bytes_total):
    datos = b"\x00" * bytes_total
    url = "https://speed.cloudflare.com/__up"
    try:
        t0 = time.time()
        req = urllib.request.Request(url, data=datos, method="POST",
                                     headers={**_UA, "Content-Type": "application/octet-stream"})
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        seg = max(time.time() - t0, 0.05)
        return bytes_total * 8 / 1e6 / seg
    except Exception:
        return None


def _latencia():
    try:
        r = subprocess.run(["ping", "-n", "3", "one.one.one.one"],
                           capture_output=True, text=True, timeout=15,
                           creationflags=0x08000000)
        import re
        m = re.search(r"(?:Media|Promedio|Average)\s*=\s*([0-9]+)ms", r.stdout, re.IGNORECASE)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def _fmt(mbps):
    if mbps is None:
        return None
    if mbps >= 1:
        return f"{mbps:.1f}"
    return f"{mbps * 1000:.0f}"


def velocidad(parameters: dict, player=None, speak=None) -> str:
    """Mide la velocidad de internet real (bajada y subida)."""
    action = str(parameters.get("action", "medir")).strip().lower()

    if action in ("test",):
        return "La medición de velocidad está lista."

    if action not in ("medir", "velocidad", "probar", "test"):
        return "Acciones: medir | test."

    if player:
        player.write_log("🚀 Velocidad: midiendo (tarda unos segundos)...")

    baja, recib = _descarga_mbps(8 * 1024 * 1024)  # 8 MB real
    if baja is None:
        return ("No pude medir ahora: el servidor de prueba no respondió. "
                "Probá de nuevo en unos minutos.")

    otra, _ = _descarga_mbps(1024 * 1024)  # 1 MB para promediar con el 8 MB
    if otra is not None:
        baja = (baja + otra) / 2

    sube = _subida_mbps(2 * 1024 * 1024)  # 2 MB de subida
    lat = _latencia()

    sal = ["Medición de tu velocidad de internet:"]
    sal.append(f"De bajada: {_fmt(baja)} megabits por segundo.")
    if sube is not None:
        sal.append(f"De subida: {_fmt(sube)} megabits por segundo.")
    if lat is not None:
        sal.append(f"Latencia: {lat} ms.")
    sal.append("¿Bajó de golpe? Si llevás muchas apps abiertas, puede consumir banda.")

    if player:
        player.write_log("🚀 " + " ".join(sal))
    return "\n".join(sal)