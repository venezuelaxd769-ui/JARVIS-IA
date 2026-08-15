def camera_bus(parameters: dict, player=None) -> str:
    action = parameters.get("action", "toggle").lower().strip()
    if player and hasattr(player, "_win") and player._win:
        win = player._win
        is_open = getattr(win, "camera_window", None) is not None
        if action in ("enable", "show", "on", "activar", "conectar"):
            if is_open:
                return "El subsistema de cámara gestual ya está activo."
            try:
                win._open_camera()
                return "Cámara gestual activada."
            except Exception as e:
                return f"Error al activar cámara: {e}"
        elif action in ("disable", "hide", "off", "desactivar", "apagar"):
            if not is_open:
                return "La cámara gestual ya está apagada."
            try:
                win._close_camera()
                return "Cámara gestual desactivada."
            except Exception as e:
                return f"Error al desactivar cámara: {e}"
        else:
            if is_open:
                try:
                    win._close_camera()
                    return "Cámara gestual desactivada."
                except:
                    pass
            try:
                win._open_camera()
                return "Cámara gestual activada."
            except Exception as e:
                return f"Error al alternar cámara: {e}"
    return "La cámara gestual no está disponible en la interfaz actual."
