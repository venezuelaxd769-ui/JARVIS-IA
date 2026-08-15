import os
import subprocess
import json
import shutil
from pathlib import Path

_HAS_HYPRCTL = shutil.which("hyprctl") is not None
_HAS_GSETTINGS = shutil.which("gsettings") is not None

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

def desktop_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    path_val = parameters.get("path", "")
    url_val = parameters.get("url", "")
    mode_val = parameters.get("mode", "")
    task_val = parameters.get("task", "")
    search_name = parameters.get("search_name", "")
    search_path = parameters.get("search_path", "desktop")

    if action == "list" or action == "stats":
        if _HAS_HYPRCTL:
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

    if action == "context":
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

    if action == "list_windows" or action == "windows":
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

    if action == "wallpaper" or action == "wallpaper_url":
        target = url_val if action == "wallpaper_url" else path_val
        if not target:
            return "Error: Se requiere 'path' o 'url' para cambiar el wallpaper."

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

    if action == "organize":
        return "La función de organizar archivos no está disponible en Linux."

    if action == "clean":
        return "La función de limpiar escritorio no está disponible en Linux."

    if action == "task":
        return f"Tarea de escritorio '{task_val}' no soportada."

    if action == "go_to" or action == "switch":
        target_desk = parameters.get("desktop", parameters.get("workspace", ""))
        if not target_desk:
            return "Error: Se requiere 'desktop' o 'workspace' para cambiar de escritorio."
        if _HAS_HYPRCTL:
            _hyprctl(["dispatch", "workspace", str(target_desk)])
            msg = f"Cambiado al escritorio {target_desk}."
            if player:
                player.write_log(f"🖥️ {msg}")
            return msg
        return "Cambiar de escritorio no está soportado en este entorno."

    if action == "focus_window":
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
        if not cls and not title_match:
            return "Error: Se requiere 'class' (ej: brave-browser) o 'title' para enfocar una ventana."
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

    if action in ("move_window", "move_to", "move"):
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
        target_ws = parameters.get("workspace", parameters.get("desktop", ""))
        if not target_ws:
            return "Error: Se requiere 'workspace' o 'desktop' para mover la ventana."
        if not cls and not title_match:
            return "Error: Se requiere 'class' o 'title' para identificar la ventana a mover."
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

    if action in ("pin_window", "pin"):
        """Sticky window — visible across all workspaces."""
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
        if not cls and not title_match:
            return "Error: Se requiere 'class' o 'title' para fijar una ventana."
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

    if action == "fullscreen":
        if _HAS_HYPRCTL:
            _hyprctl(["dispatch", "fullscreen", "1"])
            msg = "Ventana activa maximizada a pantalla completa."
            if player:
                player.write_log(f"🖥️ {msg}")
            return msg
        return "Pantalla completa no soportada."

    if action == "close_window" or action == "close":
        cls = parameters.get("class", "")
        title_match = parameters.get("title", "")
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
            # No filter → kill active window
            if _HAS_HYPRCTL:
                _hyprctl(["dispatch", "killactive"])
                msg = "Ventana activa cerrada."
                if player:
                    player.write_log(f"❌ {msg}")
                return msg
            return "Cerrar ventana no está soportado en este entorno."

    return "Comando de escritorio ejecutado."
