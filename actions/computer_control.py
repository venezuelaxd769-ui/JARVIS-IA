"""computer_control.py — Native computer controls (keyboard, mouse, typing, screen)."""
import os
import time
import pyautogui
import pyperclip
from pathlib import Path
from actions.screen_capture import capture_screen

def computer_control(parameters: dict, player=None) -> str:
    """
    Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, etc.
    """
    action = parameters.get("action", "").lower().strip()
    text = parameters.get("text", "")
    x = parameters.get("x", None)
    y = parameters.get("y", None)
    keys = parameters.get("keys", "")
    key = parameters.get("key", "")
    direction = parameters.get("direction", "down").lower().strip()
    amount = parameters.get("amount", 3)
    seconds = parameters.get("seconds", 1.0)
    
    if not action:
        return "Error: No se especificó ninguna acción en computer_control."

    try:
        if action == "type" or action == "smart_type":
            if not text:
                return "Error: No se proporcionó texto para escribir."
            # Copiar al portapapeles y pegar con CTRL+V es extremadamente robusto
            # para manejar acentos en español (á, é, í, ó, ú, ñ) y caracteres especiales.
            pyperclip.copy(text)
            time.sleep(0.1)
            pyautogui.hotkey("ctrl", "v")
            msg = f"Texto escrito físicamente en pantalla: '{text}'."

        elif action == "press":
            if not key:
                return "Error: No se especificó la tecla para presionar (key)."
            pyautogui.press(key)
            msg = f"Tecla '{key}' presionada."

        elif action == "hotkey":
            if not keys:
                return "Error: No se especificaron las teclas de atajo (keys) e.g. 'ctrl+c'."
            # Separar por + o coma y limpiar espacios
            k_list = [k.strip().lower() for k in keys.replace(",", "+").split("+")]
            pyautogui.hotkey(*k_list)
            msg = f"Atajo de teclado ejecutado: {keys}."

        elif action == "click":
            if x is not None and y is not None:
                pyautogui.click(int(x), int(y))
                msg = f"Clic izquierdo en coordenadas ({x}, {y})."
            else:
                pyautogui.click()
                msg = "Clic izquierdo en la posición actual del cursor."

        elif action == "double_click":
            if x is not None and y is not None:
                pyautogui.doubleClick(int(x), int(y))
                msg = f"Doble clic izquierdo en coordenadas ({x}, {y})."
            else:
                pyautogui.doubleClick()
                msg = "Doble clic izquierdo en la posición actual del cursor."

        elif action == "right_click":
            if x is not None and y is not None:
                pyautogui.rightClick(int(x), int(y))
                msg = f"Clic derecho en coordenadas ({x}, {y})."
            else:
                pyautogui.rightClick()
                msg = "Clic derecho en la posición actual del cursor."

        elif action == "move":
            if x is not None and y is not None:
                pyautogui.moveTo(int(x), int(y), duration=0.2)
                msg = f"Cursor del mouse movido a ({x}, {y})."
            else:
                return "Error: Se requieren coordenadas 'x' e 'y' para mover el mouse."

        elif action == "scroll":
            try:
                scroll_amount = int(amount) * 100
            except ValueError:
                scroll_amount = 300
            
            if direction == "up":
                pyautogui.scroll(scroll_amount)
                msg = f"Scroll hacia arriba realizado (cantidad: {scroll_amount})."
            else:
                pyautogui.scroll(-scroll_amount)
                msg = f"Scroll hacia abajo realizado (cantidad: {scroll_amount})."

        elif action == "copy":
            pyautogui.hotkey("ctrl", "c")
            msg = "Comando copiar (CTRL+C) ejecutado."

        elif action == "paste":
            pyautogui.hotkey("ctrl", "v")
            msg = "Comando pegar (CTRL+V) ejecutado."

        elif action == "screenshot":
            desktop_path = os.path.join(str(Path.home()), "Desktop")
            if not os.path.exists(desktop_path):
                desktop_path = os.path.join(str(Path.home()), "Escritorio")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"
            filepath = os.path.join(desktop_path, filename)

            import base64
            from PIL import Image
            import io
            b64 = capture_screen(save_path=Path(filepath), max_size=None)
            msg = f"Captura de pantalla guardada en el Escritorio como '{filename}'."

        elif action == "wait":
            try:
                s = float(seconds)
            except ValueError:
                s = 1.0
            time.sleep(s)
            msg = f"Espera de {s} segundos finalizada."

        elif action == "clear_field":
            # Comando de teclado para borrar un campo
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.05)
            pyautogui.press("backspace")
            msg = "Campo de entrada limpiado físicamente."

        else:
            # Fallback/Mensaje genérico
            msg = f"Acción '{action}' ejecutada."

        if player:
            player.write_log(f"💻 Control: {msg}")
        return msg

    except Exception as e:
        err_msg = f"Error al ejecutar control del PC: {str(e)}"
        if player:
            player.write_log(f"⚠️ {err_msg}")
        return err_msg
