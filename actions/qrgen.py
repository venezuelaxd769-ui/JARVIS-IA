# -*- coding: utf-8 -*-
"""qrgen.py — Generador y LECTOR de QR por voz.

Convierte texto/URL/credenciales WiFi en un PNG de código QR usando la
librería 'qrcode'. Para WiFi usar formato estándar:
wifi:T:WPA;S:<nombre red>;P:<contraseña>;;

También descifra QRs desde una imagen ('leer'): usa el QRCodeDetector de
OpenCV (cv2 ya instalado), resuelve rutas por nombre con buscar._buscar o
toma una captura de pantalla activa ('captura'). Devuelve el contenido
(para un QR tipo WiFi sería el string wifi:...).
"""
import os
import re
from datetime import datetime

_FOLDER = os.path.join(os.path.expanduser("~"), "NiaSandbox", "qr")


def _nombre_limpio(nombre):
    nombre = os.path.basename(str(nombre or "").strip())
    nombre = re.sub(r"[^A-Za-z0-9áéíóúñüÁÉÍÓÚÑÜ._-]+", "_", nombre)
    if not nombre.endswith(".png"):
        nombre += ".png"
    return nombre


def _resolver_ruta(ruta):
    if not ruta:
        return None
    nombre = os.path.basename(ruta).strip().strip('"')
    for base in (_FOLDER, os.path.join(os.path.expanduser("~"), "NiaSandbox", "captures")):
        candidata = os.path.join(base, nombre)
        if os.path.isfile(candidata):
            return candidata
    ruta = os.path.expanduser(str(ruta).strip().strip('"'))
    if os.path.isfile(ruta):
        return ruta
    from actions.buscar import _buscar
    for patron in ("*.png", "*.jpg", "*.jpeg"):
        hit = _buscar(ruta, tipo=patron)
        if hit:
            return hit[0]
    return None


def _decodificar(img):
    import cv2
    det = cv2.QRCodeDetector()
    data, _p, _s = det.detectAndDecode(img)
    return (data or "").strip()


def qrgen(parameters: dict, player=None, speak=None) -> str:
    """Genera un código QR desde texto, URL o red WiFi; o lo lee de una imagen."""
    action = str(parameters.get("action", "generar")).strip().lower()
    contenido = str(parameters.get("contenido", "") or parameters.get("texto", "") or parameters.get("url", "")).strip()
    nombre = _nombre_limpio(parameters.get("nombre", ""))
    imagen = str(parameters.get("imagen", "") or parameters.get("archivo", "") or "").strip()

    if action in ("test", "chequear"):
        try:
            import qrcode  # noqa: F401
            import cv2  # noqa: F401
            return "El generador y lector de QR funciona."
        except Exception:
            return "No está instalada la librería qrcode o OpenCV."

    if action in ("listar", "cuales", "guan"):
        if not os.path.isdir(_FOLDER):
            return "Todavía no generaste ningún QR."
        archivos = sorted(os.listdir(_FOLDER))
        if not archivos:
            return "Todavía no hay QRs generados en NiaSandbox/qr."
        return "Tus QRs: " + ", ".join(archivos[-10:]) + "."

    if action in ("leer", "decodificar", "escaneame"):
        from actions.buscar import _buscar
        directorio = os.path.join(os.path.expanduser("~"), "NiaSandbox", "captures")
        ruta = _resolver_ruta(imagen)
        if ruta is None and os.path.isdir(directorio):
            capturas = [os.path.join(directorio, f) for f in
                        sorted(os.listdir(directorio), reverse=True)
                        if f.lower().endswith((".png", ".jpg", ".jpeg"))]
            if capturas:
                ruta = capturas[0]  # la captura mas reciente
        if ruta is None:
            if imagen:
                return f"No encontré una imagen llamada '{imagen}'. Decime el nombre de archivo o sacá una captura."
            return "No encontré ninguna captura para escanear. Pasame imagen='<archivo>' o sacá una captura primero."
        try:
            import cv2
            img = cv2.imread(ruta)
            if img is None:
                return f"No pude leer la imagen {ruta}."
            data = _decodificar(img)
        except Exception as e:
            return f"No pude escanear el QR: {e}."
        if not data:
            return "No vi ningún QR en esa imagen. Asegurate de que el código esté completo y bien enfocado."
        if player:
            player.write_log(f"🔳 QR leído de {ruta} → {data[:160]}")
        return f"El QR dice: {data}."

    if action not in ("generar", "crear", "armar"):
        return "Acciones: generar | listar | leer | test."

    if not contenido:
        return ("Decime qué codificar en el QR, por ejemplo contenido='wifi:T:WPA;S:mired;P:clave;;' "
                "para tu WiFi o una URL. Podés agregar nombre='wifi_casa'.")
    try:
        import qrcode
        from PIL import Image  # noqa: F401  (backends de pintado)
    except Exception as e:
        return f"Falta la librería qrcode o Pillow: {e}."
    try:
        os.makedirs(_FOLDER, exist_ok=True)
        marca = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = nombre or f"qr_{marca}.png"
        path = os.path.join(_FOLDER, fname)
        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(contenido)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path, "PNG")
    except Exception as e:
        return f"No pude generar el QR: {e}."
    if player:
        player.write_log(f"🔳 QR guardado: {path}")
    return f"Listo, generé el QR y quedó en {path}."