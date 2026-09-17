# -*- coding: utf-8 -*-
"""volumen.py — Control de volumen del sistema por voz (Windows, WASAPI vía pycaw).

Nia puede subir, bajar, fijar, silenciar y destapar el volumen del equipo,
y decirte en qué nivel está. Sin librerías nuevas: usa pycaw+comtypes
(ya instalados).
"""
try:
    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    _POWER = True
except Exception:
    _POWER = False


def _get_volume():
    if not _POWER:
        return None
    comtypes.CoInitialize()
    device = AudioUtilities.GetSpeakers()
    return device.EndpointVolume


def _fmt(frac):
    return max(0, min(100, int(round(frac * 100))))


def volumen(parameters: dict, player=None, speak=None) -> str:
    """Control del volumen del sistema por voz: fijar (nivel), subir, bajar,
    silenciar, destapar y consultar el estado. Windows + pycaw."""
    action = str(parameters.get("action", "estado")).strip().lower()
    if player:
        player.write_log(f"🔊 volumen: {action}")
    if not _POWER:
        return "No pude acceder al dispositivo de audio. Si estás en Linux o sin tarjeta, no puedo controlar el volumen."
    try:
        vol = _get_volume()
    except Exception as e:
        return f"No pude tomar el volumen: {e}"
    if vol is None:
        return "No pude tomar el volumen del sistema."

    if action in ("estado", "info", "como_estoy"):
        nivel = _fmt(vol.GetMasterVolumeLevelScalar())
        muted = bool(vol.GetMute())
        estado = "silenciado" if muted else "activado"
        return f"El volumen está en {nivel} por ciento y el audio está {estado}."

    if action in ("silenciar", "mutear", "mute", "callar"):
        vol.SetMute(1, None)
        return "Listo, quedó todo silenciado."

    if action in ("sonar", "desmutear", "destapar", "unmute"):
        vol.SetMute(0, None)
        return "Listo, el sonido vuelve a estar activo."

    try:
        pasos = int(parameters.get("nivel") or 0)
    except (TypeError, ValueError):
        pasos = None

    if action in ("subir", "mas", "arriba"):
        nivel = int(round(vol.GetMasterVolumeLevelScalar() * 100))
        nivel = min(100, nivel + (pasos or 10))
        vol.SetMasterVolumeLevelScalar(nivel / 100.0, None)
        return f"Subí el volumen a {nivel} por ciento."

    if action in ("bajar", "menos", "abajo"):
        nivel = int(round(vol.GetMasterVolumeLevelScalar() * 100))
        nivel = max(0, nivel - (pasos or 10))
        vol.SetMasterVolumeLevelScalar(nivel / 100.0, None)
        return f"Bajé el volumen a {nivel} por ciento."

    if action in ("nivel", "fijar", "set", "poner"):
        if pasos is None:
            return "Decime el nivel: ej. action='nivel', nivel=40."
        nivel = max(0, min(100, pasos))
        vol.SetMasterVolumeLevelScalar(nivel / 100.0, None)
        return f"Dejé el volumen en {nivel} por ciento."

    nivel = _fmt(vol.GetMasterVolumeLevelScalar())
    muted = bool(vol.GetMute())
    estado = "silenciado" if muted else "activado"
    return f"El volumen está en {nivel} por ciento y el audio está {estado}."


if __name__ == "__main__":
    import sys
    a = sys.argv[1] if len(sys.argv) > 1 else "estado"
    n = sys.argv[2] if len(sys.argv) > 2 else None
    print(volumen({"action": a, "nivel": n}))