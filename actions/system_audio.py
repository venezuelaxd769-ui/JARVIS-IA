# -*- coding: utf-8 -*-
"""system_audio.py — Audio avanzado por voz (Windows, pycaw).

Listar y cambiar el dispositivo de salida por defecto, silenciar/sonar el
micrófono, su nivel, y el volumen por aplicación.
"""
from ctypes import POINTER, cast


def _speakers():
    from pycaw.pycaw import AudioUtilities
    try:
        sp = AudioUtilities.GetSpeakers()
        return (sp, sp.GetId())
    except Exception:
        return (None, "")


def _render_devices():
    from pycaw.pycaw import AudioUtilities
    try:
        out = []
        for d in AudioUtilities.GetAllDevices():
            did = str(getattr(d, "id", ""))
            if did.startswith("{0.0.0.00000000}") and getattr(d, "state", None):
                if "Active" in str(getattr(d, "state", "")):
                    out.append((did, getattr(d, "FriendlyName", "")))
        return out
    except Exception:
        return []


def _mic_volume():
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    try:
        mic = AudioUtilities.GetMicrophone()
        ev = cast(mic.Activate(IAudioEndpointVolume._iid_, 7, None),
                  POINTER(IAudioEndpointVolume))
        return ev
    except Exception:
        return None


def _sessions():
    from pycaw.pycaw import AudioUtilities
    try:
        return AudioUtilities.GetAllSessions() or []
    except Exception:
        return []


def system_audio(parameters: dict, player=None, speak=None) -> str:
    """Audio: dispositivo, micrófono y volumen por app (Windows/pycaw)."""
    action = str(parameters.get("action", "estado")).strip().lower()
    nombre = str(parameters.get("nombre", "")).strip()
    nivel = parameters.get("nivel")
    if player:
        player.write_log(f"🔊 system_audio: {action} {nombre}")

    if action in ("dispositivos", "lista", "devices"):
        devs = _render_devices()
        _, dflt = _speakers()
        if not devs:
            return "No encontré dispositivos de audio activos."
        lines = ["🎧 Dispositivos de salida:"]
        for did, name in devs:
            marca = " ◀ (en uso)" if did == dflt else ""
            lines.append(f"   • {name}{marca}")
        return "\n".join(lines)

    if action in ("dispositivo", "cambiar", "switch", "salida"):
        if not nombre:
            return "Decime el nombre del dispositivo, ej: 'auriculares' o 'altavoces'."
        devs = _render_devices()
        hits = [d for d in devs if nombre.lower() in d[1].lower()]
        if not hits:
            return "No encontré ese dispositivo. Probá 'dispositivos' para ver los que hay."
        ok = False
        from pycaw.pycaw import AudioUtilities
        try:
            AudioUtilities.SetDefaultDevice(hits[0][0])
            ok = True
        except Exception:
            try:
                AudioUtilities.SetDefaultDevice(hits[0][0], roles=0xFFFFFFFF)
                ok = True
            except Exception as e:
                return f"No pude cambiar el dispositivo: {e}"
        _, dflt = _speakers()
        estado = "confirmado" if dflt == hits[0][0] else "intentado"
        return f"🔄 Cambié la salida a '{hits[0][1]}' ({estado})."

    if action in ("mic", "mic_estado"):
        ev = _mic_volume()
        if not ev:
            return "No pude leer el micrófono."
        muted = bool(ev.GetMute())
        vol = int(round(ev.GetMasterVolumeLevelScalar() * 100))
        return f"🎙️  Micrófono: {'SILENCIADO' if muted else 'activo'}, nivel {vol}%."

    if action in ("mic_silenciar", "mic_mute", "callar_mic"):
        ev = _mic_volume()
        if not ev:
            return "No pude acceder al micrófono."
        ev.SetMute(1, None)
        ev.SetMasterVolumeLevelScalar(0.0, None)
        return "🎙️  Micrófono silenciado."

    if action in ("mic_sonar", "mic_unmute"):
        ev = _mic_volume()
        if not ev:
            return "No pude acceder al micrófono."
        ev.SetMute(0, None)
        try:
            ev.SetMasterVolumeLevelScalar(0.8, None)
        except Exception:
            pass
        return "🎙️  Micrófono activado de nuevo."

    if action in ("mic_nivel", "mic_volumen"):
        if nivel is None:
            return "Decime el nivel (0-100), ej: nivel='80'."
        ev = _mic_volume()
        if not ev:
            return "No pude acceder al micrófono."
        v = max(0, min(100, int(nivel))) / 100.0
        ev.SetMasterVolumeLevelScalar(v, None)
        ev.SetMute(0, None)
        return f"🎙️  Nivel de micrófono en {int(v * 100)}%."

    if action in ("apps", "app_list"):
        outs = []
        for s in _sessions():
            try:
                proc = getattr(s, "Process", None)
                name = getattr(proc, "name", lambda: "?")().lower() if proc else "?"
                vol = getattr(s, "SimpleAudioVolume", None)
                valor = int(round(vol.GetMasterVolumeLevelScalar() * 100)) if vol else -1
                if name:
                    outs.append(f"   • {name}: {valor}%")
            except Exception:
                continue
        return "🔊 Aplicaciones con audio:\n" + ("\n".join(outs[:15]) if outs else "Ninguna reproducida.")

    if action in ("app", "app_volumen", "app_vol"):
        if not nombre or nivel is None:
            return "Decime proceso y nivel, ej: app='chrome' nivel='50'."
        v = max(0, min(100, int(nivel))) / 100.0
        hit = False
        for s in _sessions():
            try:
                proc = getattr(s, "Process", None)
                name = getattr(proc, "name", lambda: "?")().lower() if proc else ""
                if nombre.lower() in name:
                    vol = getattr(s, "SimpleAudioVolume", None)
                    if vol:
                        vol.SetMasterVolumeLevelScalar(v, None)
                        hit = True
            except Exception:
                continue
        return f"Ajusté '{nombre}' a {int(v * 100)}%." if hit else f"No encontré '{nombre}' reproduciendo."

    return ("Acciones: dispositivos | dispositivo (nombre) | mic | mic_silenciar | "
            "mic_sonar | mic_nivel (nivel) | apps | app (proceso, nivel).")


if __name__ == "__main__":
    import sys
    p = {"action": sys.argv[1] if len(sys.argv) > 1 else "estado"}
    if len(sys.argv) > 2:
        p["nombre"] = sys.argv[2]
    print(system_audio(p))