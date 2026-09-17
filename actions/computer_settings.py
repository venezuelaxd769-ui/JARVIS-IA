"""computer_settings.py — controles Win32 de sistema (volumen, ventanas)."""
import os
import sys

def computer_settings(parameters: dict, response=None, player=None) -> str:
    """Ajusta volumen (nivel exacto, subir, bajar, silenciar) y minimiza/maximiza la ventana activa."""
    action = parameters.get("action", "").lower()
    value = parameters.get("value", "")

    if action == "volume":
        try:
            import pyautogui
            if str(value).isdigit():
                target = int(value)
                try:
                    from ctypes import cast, POINTER
                    from comtypes import CoInitialize, CoUninitialize
                    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                    CoInitialize()
                    devices = AudioUtilities.GetSpeakers()
                    interface = devices.Activate(IAudioEndpointVolume._iid_, 1, None)
                    volume_ctrl = cast(interface, POINTER(IAudioEndpointVolume))
                    scalar_vol = max(0.0, min(1.0, target / 100.0))
                    volume_ctrl.SetMasterVolumeLevelScalar(scalar_vol, None)
                    CoUninitialize()
                    msg = f"Volumen al {target}%."
                except Exception as e:
                    msg = f"No pude setear el volumen absoluto: {e}"
            else:
                if "up" in value.lower() or "subir" in value.lower():
                    pyautogui.press("volumeup", presses=5)
                    msg = "Volumen subido."
                elif "down" in value.lower() or "bajar" in value.lower():
                    pyautogui.press("volumedown", presses=5)
                    msg = "Volumen bajado."
                elif "mute" in value.lower() or "silenciar" in value.lower() or "mudo" in value.lower():
                    pyautogui.press("volumemute")
                    msg = "Silenciado."
                else:
                    msg = f"No entendí el valor de volumen: {value}"
            if player:
                player.write_log(f"🔊 {msg}")
            return msg
        except Exception as e:
            return f"No pude ajustar el volumen: {e}"

    elif action in ("minimize", "window_minimize"):
        try:
            try:
                import pygetwindow as gw
            except (ImportError, NotImplementedError):
                return "El control de ventanas no está disponible en esta plataforma."
            window = gw.getActiveWindow()
            if window:
                window.minimize()
                return "Ventana activa minimizada."
            return "No hay una ventana activa."
        except Exception as e:
            return f"No pude minimizar la ventana: {e}"

    elif action in ("maximize", "window_maximize"):
        try:
            try:
                import pygetwindow as gw
            except (ImportError, NotImplementedError):
                return "El control de ventanas no está disponible en esta plataforma."
            window = gw.getActiveWindow()
            if window:
                window.maximize()
                return "Ventana activa maximizada."
            return "No hay una ventana activa."
        except Exception as e:
            return f"No pude maximizar la ventana: {e}"

    return f"La acción '{action}' de computer_settings todavía no está soportada, Señor."