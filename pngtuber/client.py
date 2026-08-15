# -*- coding: utf-8 -*-
"""client.py — Cliente mínimo y seguro para hablar con la app PNGtuber.

Nia envía comandos (talk_start, talk_end, show, hide, quit) y escucha
'reopen' para restaurar su ventana. Cada envío abre/cierra conexión local:
es barato y no comparte estado entre hilos.

Además mantiene una conexión persistente para el nivel de voz en directo
(vol:<rms>), con la que el modelo abre/cierra la boca siguiendo el ritmo
real del audio que reproduce Nia.
"""
import socket
import threading
import time

HOST = "127.0.0.1"
PORT = 8791
TIMEOUT = 1.0
_VOL_BLOCK_RETRY = 5.0   # s sin reintentar conectar si el socket murió

_vol_conn = None
_vol_lock = threading.Lock()
_vol_blocked_until = 0.0


def send(cmd: str) -> bool:
    """Envía un comando al PNGtuber. Devuelve True si pudo conectarse."""
    try:
        with socket.create_connection((HOST, PORT), timeout=TIMEOUT) as s:
            s.sendall((cmd + "\n").encode("utf-8"))
        return True
    except Exception:
        return False


def send_volume(level: float) -> bool:
    """Envía la energía del audio en directo usando una conexión persistente.

    No bloquea la reproducción: si la conexión está caída no reintenta hasta
    pasados unos segundos, para no congelar la salida de audio."""
    global _vol_conn, _vol_blocked_until
    now = time.time()
    if _vol_conn is None and now < _vol_blocked_until:
        return False
    try:
        with _vol_lock:
            if _vol_conn is None:
                _vol_conn = socket.create_connection((HOST, PORT), timeout=0.5)
            _vol_conn.sendall(f"vol:{level:.4f}\n".encode("utf-8"))
        return True
    except Exception:
        _vol_conn = None
        _vol_blocked_until = time.time() + _VOL_BLOCK_RETRY
        return False


def close_volume() -> None:
    """Cierra la conexión persistente de volumen (al terminar de hablar)."""
    global _vol_conn
    with _vol_lock:
        if _vol_conn is not None:
            try:
                _vol_conn.close()
            except Exception:
                pass
            _vol_conn = None


def pngtuber_available() -> bool:
    return send("ping")
