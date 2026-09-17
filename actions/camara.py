# -*- coding: utf-8 -*-
"""camara.py — Cámara web por voz (Windows, OpenCV).

Saca una foto con la webcam y la guarda en ~/NiaSandbox/captures/.
"""
import os
import time
from datetime import datetime


def _capture(nombre=None):
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        cap.release()
        return None, "No pude abrir la cámara web. Revisala y volvé a intentar."
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        for _ in range(4):
            cap.grab()
        ok, frame = cap.read()
        if not ok:
            return None, "No pude capturar la imagen de la cámara."
        folder = os.path.join(os.path.expanduser("~"), "NiaSandbox", "captures")
        os.makedirs(folder, exist_ok=True)
        base = nombre.strip() if nombre else datetime.now().strftime("webcam_%Y%m%d_%H%M%S")
        base = "".join(c if c.isalnum() or c in "_- " else "_" for c in base)
        ruta = os.path.join(folder, f"{base}.png")
        ok = cv2.imwrite(ruta, frame)
        if not ok:
            return None, "No pude guardar la foto."
        return ruta, None
    finally:
        cap.release()


def camara(parameters: dict, player=None, speak=None) -> str:
    """Cámara web: sacar fotos con la webcam por voz."""
    action = str(parameters.get("action", "foto")).strip().lower()
    nombre = str(parameters.get("nombre", "")).strip()
    if player:
        player.write_log(f"📸 camara: {action}")

    if action in ("foto", "fotografia", "captura", "selfie"):
        ruta, err = _capture(nombre)
        if err:
            return err
        return (f"Listo, te saqué la foto. La guardé en {ruta}. "
                "Decime 'mirala' y la veo.")

    if action in ("test", "probar", "check"):
        import cv2 as _cv
        cap = _cv.VideoCapture(0, _cv.CAP_DSHOW)
        ok = cap.isOpened()
        cap.release()
        return ("Tu cámara web está disponible." if ok
                else "No encuentro la cámara web.")

    return "Acciones: foto (nombre opcional) | test."