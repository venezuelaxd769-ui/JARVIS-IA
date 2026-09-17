# -*- coding: utf-8 -*-
"""checksum.py — Huella MD5/SHA de un archivo por voz.

Calcula el hash (por bloques, sin cargar todo en memoria) de un archivo
para verificar su integridad contra lo que publica el sitio de descarga.
"""
import hashlib
import os

_ALGOS = {"md5", "sha1", "sha256", "sha512"}


def _hash(path, algo):
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            b = f.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def checksum(parameters: dict, player=None, speak=None) -> str:
    """Calcula MD5/SHA256 de un archivo."""
    action = str(parameters.get("action", "calcular")).strip().lower()
    if action in ("test", "chequear"):
        return "El cálculo de checksum funciona (por bloques, sin colgarse)."

    if action in ("ayuda", "algos"):
        return "Algoritmos: md5 | sha1 | sha256 | sha512."

    if action not in ("calcular", "md5", "sha256", "sha1", "sha512", "hash"):
        return "Acciones: calcular | ayuda | test."

    archivo = str(parameters.get("archivo", "") or parameters.get("ruta", "")).strip()
    if not archivo:
        return "Decime qué archivo, por ejemplo archivo='instalador.exe'."

    algo = str(parameters.get("algoritmo", "md5")).strip().lower()
    if algo not in _ALGOS:
        return f"Solo sé calcular {', '.join(sorted(_ALGOS))}. Por ejemplo algoritmo='sha256'."

    path = archivo
    if not os.path.exists(path):
        try:
            from actions.buscar import _roots, _buscar
            found, _ = _buscar(os.path.basename(path), "", _roots(None), 5)
            if not found:
                return f"No encontré el archivo '{archivo}'. Pasá su ruta completa."
            path = found[0][0]
        except Exception:
            return f"No encontré el archivo '{archivo}'."
    try:
        digest = _hash(path, algo)
        size = os.path.getsize(path)
    except OSError as e:
        return f"No pude leer '{path}': {e}."
    except Exception:
        return f"No pude calcular el {algo.upper()} de '{path}'."

    mb = round(size / (1024 ** 2), 1)
    log = f"{algo.upper()} de {os.path.basename(path)} ({mb} MB): {digest}"
    if player:
        player.write_log("🔐 " + log)
    return f"{algo.upper()} de {os.path.basename(path)}: {digest} (el archivo pesa {mb} MB)."