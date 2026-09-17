import os
import subprocess
import json
import shutil
from pathlib import Path

try:
    import pygetwindow as gw
except (ImportError, NotImplementedError):
    gw = None

_IS_WINDOWS = os.name == "nt"
_HAS_HYPRCTL = shutil.which("hyprctl") is not None
_HAS_GSETTINGS = shutil.which("gsettings") is not None

# ── Hyprland helpers (Linux) ────────────────────────────────────────────────
def _hyprctl(cmd: list[str]) -> str:
    try:
        return subprocess.run(["hyprctl"] + cmd, capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ""

def _list_workspaces_hyprland() -> list[dict]:
    out = _hyprctl(["workspaces", "-j"])
    if not out:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []

def _list_clients_hyprland() -> list[dict]:
    out = _hyprctl(["clients", "-j"])
    if not out:
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []

def _get_active_workspace() -> dict:
    out = _hyprctl(["activeworkspace", "-j"])
    if not out:
        return {"id": 1, "name": "1"}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {"id": 1, "name": "1"}

def _get_active_window() -> dict:
    out = _hyprctl(["activewindow", "-j"])
    if not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}

# ── Windows helpers (pygetwindow + ctypes) ─────────────────────────────────
def _win_all_windows() -> list:
    if not gw:
        return []
    try:
        return [w for w in gw.getAllWindows() if w.title and w.title.strip()]
    except Exception:
        return []

def _win_active() -> object | None:
    if not gw:
        return None
    try:
        win = gw.getActiveWindow()
        return win if (win and win.title and win.title.strip()) else None
    except Exception:
        return None

def _win_find(title_match: str = "", class_match: str = "") -> object | None:
    if not gw:
        return None
    try:
        for w in gw.getAllWindows():
            if not w.title:
                continue
            t = w.title
            if title_match and title_match.lower() in t.lower():
                return w
            if class_match and class_match.lower() in t.lower():
                return w
    except Exception:
        pass
    return None

def _win_activate(w) -> bool:
    try:
        import ctypes
        if hasattr(w, "_hWnd") and w._hWnd:
            hwnd = int(w._hWnd)
            ctypes.windll.user32.ShowWindow(hwnd, 9)   # SW_RESTORE (si estuvo minimizada)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
    except Exception:
        pass
    try:
        w.activate()
        return True
    except Exception:
        return False

def _win_close(w) -> bool:
    try:
        import ctypes
        WM_CLOSE = 0x0010
        if hasattr(w, "_hWnd") and w._hWnd:
            hwnd = int(w._hWnd)
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            return True
    except Exception:
        pass
    try:
        w.close()
        return True
    except Exception:
        return False

def _win_set_wallpaper(absolute_path: str) -> bool:
    try:
        import ctypes
        SPI_SETDESKWALLPAPER = 0x0014
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDCHANGE = 0x02
        path = Path(absolute_path).resolve()
        if not path.exists():
            return False
        r = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, str(path), SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )
        return bool(r)
    except Exception:
        return False

def _win_go_to_desktop(target: str) -> bool:
    """Cambia de escritorio virtual en Windows (solo next/prev; Windows no
    expone escritorios numerados sin API extra)."""
    target = (str(target) or "").lower()
    import pyautogui
    try:
        if target in ("next", "derecha", "siguiente", "right", "siguiente escritorio"):
            pyautogui.hotkey("win", "ctrl", "right")
            return True
        if target in ("prev", "previous", "izquierda", "anterior", "left", "anterior escritorio"):
            pyautogui.hotkey("win", "ctrl", "left")
            return True
    except Exception:
        pass
    return False

def _win_wallpaper_msg(action: str, target: str) -> str:
    try:
        if action == "wallpaper_url":
            import requests
            from tempfile import gettempdir
            resp = requests.get(target, timeout=30)
            ext = target.split("?")[0].split(".")[-1] if "." in target.split("?")[0] else "jpg"
            tmp = Path(gettempdir()) / f"jarvis_wallpaper.{ext}"
            tmp.write_bytes(resp.content)
            target = str(tmp)
        ok = _win_set_wallpaper(target)
        if ok:
            return f"Wallpaper cambiado a '{Path(target).name}'."
        return "No se pudo cambiar el wallpaper de Windows."
    except Exception as e:
        return f"Error cambiando wallpaper: {e}"

def desktop_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    path_val = parameters.get("path", "")
    url_val = parameters.get("url", "")
    mode_val = parameters.get("mode", "")
    task_val = parameters.get("task", "")
    search_name = parameters.get("search_name", "")
    search_path = parameters.get("search_path", "desktop")

    # ── list / stats ───────────────────────────────────────────────────────
    if action == "list" or action == "stats":
        if _IS_WINDOWS or _HAS_HYPRCTL:
            if _IS_WINDOWS:
                wins = _win_all_windows()
                active = _win_active()
                active_title = active.title if active else ""
                lines = []
                for w in wins[:60]:
                    mark = " ← ACTIVO" if (active_title and w.title == active_title) else ""
                    lines.append(f"  • {w.title[:70]}{mark}")
                extra = f"\n(Windows: sin escritorios virtuales numerados; {len(_win_all_windows())} ventanas)" if False else ""
                result = f"Ventanas abiertas ({len(wins)}):\n" + "\n".join(lines)
                if player:
                    player.write_log(f"🖥️ {result}")
                return result
            ws = _list_workspaces_hyprland()
            if ws:
                active_ws = _get_active_workspace()
                active_id = active_ws.get("id", "?")
                lines = []
                for w in ws:
                    marker = " ← ACTIVO" if w.get("id") == active_id else ""
                    lines.append(f"  • Escritorio {w.get('id')}: {w.get('windows', 0)} ventanas ({w.get('name', '')}){marker}")
                result = f"Escritorios virtuales ({len(ws)} totales, activo: {active_id}):\n" + "\n".join(lines)
                if player:
                    player.write_log(f"🖥️ {result}")
                return result
            return "No se pudieron listar los escritorios."
        return "El listado de escritorios no está disponible en este entorno."

    # ── context ────────────────────────────────────────────────────────────
    if action == "context":
        if _IS_WINDOWS:
            wins = _win_all_windows()
            active = _win_active()
            active_title = active.title if active else ""
            lines = [f"🖥️ Ventana activa: {active_title or '(ninguna)'}"]
            lines.append(f"   Ventanas abiertas ({len(wins)}):")
            for w in wins[:40]:
                mark = " ← ACTIVO" if (active_title and w.title == active_title) else ""
                lines.append(f"     {w.title[:70]}{mark}")
            lines.append(f"   Total ventanas: {len(wins)}")
            result = "\n".join(lines)
            if player:
                player.write_log(f"🖥️ {result}")
            return result
        if not _HAS_HYPRCTL:
            return "El contexto de escritorio no está disponible en este entorno."
        active_ws = _get_active_workspace()
        active_id = active_ws.get("id", "?")
        active_name = active_ws.get("name", str(active_id))
        clients = _list_clients_hyprland()
        all_ws = _list_workspaces_hyprland()

        active_win = _get_active_window()
        active_class = active_win.get("class", "")
        active_title = active_win.get("title", "").strip()

        this_ws_windows = [c for c in clients if c.get("workspace", {}).get("id") == active_id]
        other_ws_windows = [c for c in clients if c.get("workspace", {}).get("id") != active_id]

        ws_list = []
        for w in all_ws:
            wid = w.get("id")
            ws_wins = [c for c in clients if c.get("workspace", {}).get("id") == wid]
            ws_list.append({
                "id": wid,
                "name": w.get("name", str(wid)),
                "windows": len(ws_wins),
                "is_active": wid == active_id,
            })

        lines = [f"🖥️ Escritorio activo: {active_id} ({active_name})"]
        if active_class:
            lines.append(f"   Ventana activa: [{active_class}] {active_title}")
        lines.append(f"   Ventanas en este escritorio ({len(this_ws_windows)}):")
        for c in this_ws_windows:
            cls = c.get("class", "?")
            title = c.get("title", "").strip()
            lines.append(f"     [{cls}] {title}" if title else f"     [{cls}]")
        lines.append(f"   Ventanas en otros escritorios ({len(other_ws_windows)}):")
        for c in other_ws_windows:
            wid = c.get("workspace", {}).get("id", "?")
            cls = c.get("class", "?")
            title = c.get("title", "").strip()
            lines.append(f"     Escritorio {wid}: [{cls}] {title}" if title else f"     Escritorio {wid}: [{cls}]")
        lines.append(f"   Total escritorios: {len(all_ws)}")

        result = "\n".join(lines)
        if player:
            player.write_log(f"🖥️ {result}")
        return result

    # ── list_windows / windows ─────────────────────────────────────────────
    if action == "list_windows" or action == "windows":
        if _IS_WINDOWS:
            wins = _win_all_windows()
            active = _win_active()
            active_title = active.title if active else ""
            lines = []
            for w in wins:
                mark = " ← ACTIVO" if (active_title and w.title == active_title) else ""
                lines.append(f"  • {w.title[:70]}{mark}")
            result = f"Ventanas abiertas ({len(wins)}):\n" + "\n".join(lines) if lines else "No hay ventanas abiertas."
            if player:
                player.write_log(f"🪟 {result}")
            return result
        if _HAS_HYPRCTL:
            clients = _list_clients_hyprland()
            active = _hyprctl(["activewindow", "-j"])
            active_addr = ""
            try:
                active_addr = json.loads(active).get("address", "")
            except Exception:
                pass
            if clients:
                lines = []
                for c in clients:
                    ws_id = c.get("workspace", {}).get("id", "?")
                    cls = c.get("class", "?")
                    title = c.get("title", "").strip()
                    addr = c.get("address", "")
                    is_active = " ← ACTIVO" if addr == active_addr else ""
                    if title:
                        lines.append(f"  • Escritorio {ws_id}: [{cls}] {title}{is_active}")
                    else:
                        lines.append(f"  • Escritorio {ws_id}: [{cls}]{is_active}")
                result = f"Ventanas abiertas ({len(clients)} totales):\n" + "\n".join(lines)
                if player:
                    player.write_log(f"🪟 {result}")
                return result
            return "No hay ventanas abiertas."
        return "Listar ventanas no está disponible en este entorno."

    # ── wallpaper / wallpaper_url ──────────────────────────────────────────
    if action == "wallpaper" or action == "wallpaper_url":
        target = url_val if action == "wallpaper_url" else path_val
        if not target:
            return "Error: Se requiere 'path' o 'url' para cambiar el wallpaper."
        if _IS_WINDOWS:
            msg = _win_wallpaper_msg(action, target)
            if player:
                player.write_log(f"🖼️ {msg}")
            return msg
        if action == "wallpaper_url":
            import tempfile
            import requests
            try:
                resp = requests.get(url_val, timeout=30)
                ext = url_val.split("?")[0].split(".")[-1] if "." in url_val.split("?")[0] else "jpg"
                tmp = Path(tempfile.gettempdir()) / f"jarvis_wallpaper.{ext}"
                tmp.write_bytes(resp.content)
                target = str(tmp)
            except Exception as e:
                return f"Error descargando la imagen: {e}"

        if _HAS_HYPRCTL:
            abs_path = str(Path(target).resolve())
            _hyprctl(["hyprpaper", "preload", abs_path])
            _hyprctl(["hyprpaper", "wallpaper", ", " + abs_path])
            msg = f"Wallpaper cambiado a '{Path(target).name}'."
            if player:
                player.write_log(f"🖼️ {msg}")
            return msg

        if _HAS_GSETTINGS:
            abs_path = str(Path(target).resolve())
            uri = Path(abs_path).as_uri()
            try:
                subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri], timeout=5)
                subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri], timeout=5)
                msg = f"Wallpaper cambiado a '{Path(target).name}'."
                if player:
                    player.write_log(f"🖼️ {msg}")
                return msg
            except Exception as e:
                return f"Error cambiando wallpaper: {e}"

        return "Cambiar wallpaper no está soportado en este entorno."

    # ── organize / clean / task ────────────────────────────────────────────
    if action == "organize":
        if _IS_WINDOWS:
            return "La organización automática del escritorio se hace empezando por 'list_windows'."
        return "La función de organizar archivos no está disponible en Linux."

    if action == "clean":
        if _IS_WINDOWS:
            return "Limpieza de escritorio no soportada (evita borrar archivos sin confirmación)."
        return "La función de limpiar escritorio no está disponible en Linux."

    if action == "task":
        return f"Tarea de escritorio '{task_val}' no soportada."

    # ── go_to / switch ─────────────────────────────────────────────────────
    if action == "go_to" or action == "switch":
        target_desk = parameters.get("desktop", parameters.get("workspace", ""))
        if not target_desk:
            return "Error: Se requiere 'desktop' o 'workspace' para cambiar de escritorio."
        if _IS_WINDOWS:
            if _win_go_to_desktop(target_desk):
                msg = f"Cambiado al escritorio virtual {target_desk}."
                if player:
                    player.write_log(f"🖥️ {msg}")
                return msg
            return "Windows solo permite cambiar entre escritorios 'next'/'prev' (Win+Ctrl+←/→)."
        if _HAS_HYPRCTL:
            _hyprctl(["dispatch", "workspace", str(target_desk)])
            msg = f"Cambiado al escritorio {target_desk}."
            if player:
                player.write_log(f"🖥️ {msg}")
            return msg
        return "Cambiar de escritorio no está soportado en este entorno."

    # ── focus_window ───────────────────────────────────────────────────────
    if action == "focus_window":
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
        if not cls and not title_match:
            return "Error: Se requiere 'class' (ej: brave-browser) o 'title' para enfocar una ventana."
        if _IS_WINDOWS:
            w = _win_find(title_match, cls)
            if w and _win_activate(w):
                msg = f"Enfocada ventana '{w.title[:60]}'"
                if player:
                    player.write_log(f"🎯 {msg}")
                return msg
            return f"No se encontró ventana con title='{title_match or cls}'."
        if _HAS_HYPRCTL:
            clients = _list_clients_hyprland()
            target = None
            for c in clients:
                if cls and c.get("class", "").lower() == cls.lower():
                    target = c
                    break
                if title_match and title_match.lower() in c.get("title", "").lower():
                    target = c
                    break
            if target:
                addr = target.get("address", "")
                if addr:
                    _hyprctl(["dispatch", "focuswindow", f"address:{addr}"])
                    msg = f"Enfocada ventana [{target.get('class')}] {target.get('title', '')[:60]}"
                    if player:
                        player.write_log(f"🎯 {msg}")
                    return msg
            return f"No se encontró ventana con class='{cls}' o title='{title_match}'."
        return "Enfocar ventanas no está soportado en este entorno."

    # ── move_window / move_to / move ───────────────────────────────────────
    if action in ("move_window", "move_to", "move"):
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
        target_ws = parameters.get("workspace", parameters.get("desktop", ""))
        if not target_ws:
            return "Error: Se requiere 'workspace' o 'desktop' para mover la ventana."
        if not cls and not title_match:
            return "Error: Se requiere 'class' o 'title' para identificar la ventana a mover."
        if _IS_WINDOWS:
            return "Mover ventanas entre escritorios no está soportado en Windows sin API adicional."
        if _HAS_HYPRCTL:
            clients = _list_clients_hyprland()
            target = None
            for c in clients:
                if cls and c.get("class", "").lower() == cls.lower():
                    target = c
                    break
                if title_match and title_match.lower() in c.get("title", "").lower():
                    target = c
                    break
            if target:
                addr = target.get("address", "")
                if addr:
                    _hyprctl(["dispatch", "movetoworkspace", str(target_ws), f"address:{addr}"])
                    msg = f"Ventana [{target.get('class')}] movida al escritorio {target_ws}."
                    if player:
                        player.write_log(f"🔄 {msg}")
                    return msg
            return f"No se encontró ventana para mover."
        return "Mover ventanas no está soportado en este entorno."

    # ── pin_window / pin ───────────────────────────────────────────────────
    if action in ("pin_window", "pin"):
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
        if not cls and not title_match:
            return "Error: Se requiere 'class' o 'title' para fijar una ventana."
        if _IS_WINDOWS:
            return "Fijar ventanas (always-on-top) no está soportado en Windows sin API adicional."
        if _HAS_HYPRCTL:
            clients = _list_clients_hyprland()
            target = None
            for c in clients:
                if cls and c.get("class", "").lower() == cls.lower():
                    target = c
                    break
                if title_match and title_match.lower() in c.get("title", "").lower():
                    target = c
                    break
            if target:
                addr = target.get("address", "")
                if addr:
                    _hyprctl(["dispatch", "pin", f"address:{addr}"])
                    msg = f"Ventana [{target.get('class')}] fijada en todos los escritorios."
                    if player:
                        player.write_log(f"📌 {msg}")
                    return msg
            return f"No se encontró ventana para fijar."
        return "Fijar ventanas no está soportado en este entorno."

    # ── fullscreen ─────────────────────────────────────────────────────────
    if action == "fullscreen":
        if _IS_WINDOWS:
            try:
                active = _win_active()
                if active:
                    active.maximize()
                    msg = "Ventana activa maximizada."
                    if player:
                        player.write_log(f"🖥️ {msg}")
                    return msg
                return "No hay ventana activa para maximizar."
            except Exception as e:
                return f"Error maximizando ventana: {e}"
        if _HAS_HYPRCTL:
            _hyprctl(["dispatch", "fullscreen", "1"])
            msg = "Ventana activa maximizada a pantalla completa."
            if player:
                player.write_log(f"🖥️ {msg}")
            return msg
        return "Pantalla completa no soportada."

    # ── close_window / close ───────────────────────────────────────────────
    if action == "close_window" or action == "close":
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
        if _IS_WINDOWS:
            if cls or title_match:
                w = _win_find(title_match, cls)
                if w and _win_close(w):
                    msg = f"Ventana '{w.title[:50]}' cerrada."
                    if player:
                        player.write_log(f"❌ {msg}")
                    return msg
                return f"No se encontró ventana con title='{title_match or cls}'."
            else:
                active = _win_active()
                if active and _win_close(active):
                    msg = "Ventana activa cerrada."
                    if player:
                        player.write_log(f"❌ {msg}")
                    return msg
                return "No se pudo cerrar la ventana activa."
        if cls or title_match:
            if _HAS_HYPRCTL:
                clients = _list_clients_hyprland()
                targets = []
                for c in clients:
                    if cls and c.get("class", "").lower() == cls.lower():
                        targets.append(c)
                    elif title_match and title_match.lower() in c.get("title", "").lower():
                        targets.append(c)
                if targets:
                    closed = []
                    for t in targets:
                        addr = t.get("address", "")
                        if addr:
                            _hyprctl(["dispatch", "closewindow", f"address:{addr}"])
                            closed.append(f"[{t.get('class')}] {t.get('title', '')[:40]}")
                    msg = "Ventanas cerradas:\n  " + "\n  ".join(closed)
                    if player:
                        player.write_log(f"❌ {msg}")
                    return msg
                return f"No se encontró ventana con class='{cls}' o title='{title_match}'."
            return "Cerrar ventanas no está soportado en este entorno."
        else:
            if _HAS_HYPRCTL:
                _hyprctl(["dispatch", "killactive"])
                msg = "Ventana activa cerrada."
                if player:
                    player.write_log(f"❌ {msg}")
                return msg
            return "Cerrar ventana no está soportado en este entorno."

    return "Comando de escritorio ejecutado."