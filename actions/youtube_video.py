"""youtube_video.py — YouTube search/play via yt-dlp + playback control via playerctl/ydotool."""
import subprocess
import json
import urllib.parse
import shutil
import time
from pathlib import Path

_HAS_YTDLP = shutil.which("yt-dlp") is not None
_HAS_PLAYERCTL = shutil.which("playerctl") is not None
_HAS_YDOTOOL = shutil.which("ydotool") is not None


def _yt_search(query: str, max_results: int = 1) -> list[dict]:
    if not _HAS_YTDLP:
        return []
    try:
        out = subprocess.run(
            ["yt-dlp", f"ytsearch{max_results}:{query}", "--dump-json", "--no-warnings"],
            capture_output=True, text=True, timeout=15
        ).stdout.strip()
        if not out:
            return []
        results = []
        for line in out.split("\n"):
            if line.strip():
                results.append(json.loads(line))
        return results
    except Exception:
        return []


def _get_brave_instance() -> str | None:
    if not _HAS_PLAYERCTL:
        return None
    try:
        out = subprocess.run(
            ["playerctl", "-l"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()
        for name in out.split("\n"):
            if "brave" in name.lower():
                return name
    except Exception:
        pass
    return None


def _playerctl_player() -> str | None:
    """Return the best MPRIS player name for controlling YouTube."""
    brave = _get_brave_instance()
    if brave:
        return brave
    # Fallback: any player
    if _HAS_PLAYERCTL:
        try:
            out = subprocess.run(
                ["playerctl", "-l"],
                capture_output=True, text=True, timeout=3
            ).stdout.strip()
            for name in out.split("\n"):
                name = name.strip()
                if name:
                    return name
        except Exception:
            pass
    return None


def _playerctl_cmd(action: str, player: str | None = None) -> bool:
    if not _HAS_PLAYERCTL:
        print("[YT] playerctl no encontrado")
        return False
    try:
        args = ["playerctl"]
        if player:
            args += ["--player=" + player]
        args.append(action)
        result = subprocess.run(args, capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print(f"[YT] playerctl {action} falló: {result.stderr[:100]}")
            return False
        return True
    except Exception as e:
        print(f"[YT] playerctl excepción: {e}")
        return False


def _ydotool_key(key: str):
    """Send a key via ydotool."""
    if not _HAS_YDOTOOL:
        return False
    try:
        subprocess.run(
            ["ydotool", "key", key],
            capture_output=True, timeout=3
        )
        return True
    except Exception:
        return False


def _ensure_ydotoold() -> bool:
    """Ensure ydotoold daemon is running."""
    try:
        subprocess.run(["pgrep", "-x", "ydotoold"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        pass
    bin_path = shutil.which("ydotoold") or str(Path.home() / ".local/bin/ydotoold")
    try:
        subprocess.Popen([bin_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        return True
    except Exception:
        return False


def _get_current_video_title() -> str:
    """Get the title of the currently playing video from playerctl."""
    try:
        out = subprocess.run(
            ["playerctl", "metadata", "xesam:title"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()
        return out
    except Exception:
        return ""


def _navigate_current_tab(url: str) -> bool:
    """Navigate the current browser tab to a URL via Ctrl+L → Ctrl+V (clipboard) → Enter.
    Uses wl-copy for clipboard to avoid keyboard layout issues with ':' '/' '?' etc."""
    _ensure_ydotoold()
    if not _focus_browser():
        return False
    time.sleep(0.5)
    try:
        ydotool_bin = shutil.which("ydotool") or str(Path.home() / ".local/bin/ydotool")
        subprocess.run([ydotool_bin, "key", "ctrl+l"], capture_output=True, timeout=5)
        time.sleep(0.4)
        subprocess.run(["wl-copy", url], capture_output=True, timeout=5)
        time.sleep(0.2)
        subprocess.run([ydotool_bin, "key", "ctrl+v"], capture_output=True, timeout=5)
        time.sleep(0.4)
        subprocess.run([ydotool_bin, "key", "enter"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def _focus_browser():
    """Try to focus a browser window before sending keys."""
    try:
        out = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5
        ).stdout
        clients = json.loads(out)
        for c in clients:
            cls = c.get("class", "").lower()
            if "brave" in cls or "chrome" in cls or "firefox" in cls:
                addr = c.get("address", "")
                if addr:
                    subprocess.run(
                        ["hyprctl", "dispatch", "focuswindow", f"address:{addr}"],
                        capture_output=True, timeout=3
                    )
                    return True
    except Exception:
        pass
    return False


def youtube_video(parameters: dict, response=None, player=None) -> str:
    from actions.browser_control import open_url

    action = parameters.get("action", "play").strip().lower()
    query = parameters.get("query", "").strip()
    url_param = parameters.get("url", "").strip()
    workspace = parameters.get("workspace", None)
    if workspace is not None:
        try:
            workspace = int(workspace)
        except (ValueError, TypeError):
            workspace = None

    # --- Playback control (pause, resume, toggle, etc.) ---
    if action in ("pause", "resume", "toggle", "play_pause", "next", "previous", "stop", "mute", "volume"):
        media_player = _playerctl_player()
        print(f"[YT] Playback action={action}, media_player={media_player}")

        if action == "pause":
            if _playerctl_cmd("pause", media_player):
                return "Video pausado."
            print(f"[YT] playerctl pause falló, intentando ydotool...")
            _focus_browser()
            time.sleep(0.2)
            if _ydotool_key("k"):
                return "Video pausado (tecla k)."
            print(f"[YT] ydotool también falló")
            return "No se pudo pausar el video. Asegurate de que Brave esté abierto reproduciendo YouTube."

        elif action in ("resume", "play"):
            if _playerctl_cmd("play", media_player):
                return "Video reanudado."
            _focus_browser()
            time.sleep(0.2)
            if _ydotool_key("k"):
                return "Video reanudado (tecla k)."
            return "No se pudo reanudar."

        elif action in ("toggle", "play_pause"):
            if _playerctl_cmd("play-pause", media_player):
                return "Toggle."
            _focus_browser()
            time.sleep(0.2)
            if _ydotool_key("k"):
                return "Toggle (tecla k)."
            return "No se pudo cambiar estado."

        elif action == "next":
            if _playerctl_cmd("next", media_player):
                return "Siguiente video."
            return "No se pudo pasar al siguiente."

        elif action == "previous":
            if _playerctl_cmd("previous", media_player):
                return "Video anterior."
            return "No se pudo volver al anterior."

        elif action == "stop":
            _focus_browser()
            time.sleep(0.2)
            if _ydotool_key("k"):
                return "Video detenido."
            return "No se pudo detener."

        elif action == "mute":
            if _playerctl_cmd("volume 0", media_player):
                return "YouTube silenciado."
            _focus_browser()
            time.sleep(0.2)
            if _ydotool_key("m"):
                return "Silenciado (tecla m)."
            return "No se pudo silenciar."

        elif action == "volume":
            value = parameters.get("value", parameters.get("volume", ""))
            if value and media_player:
                try:
                    vol = int(value)
                    if _playerctl_cmd(f"volume {vol/100:.2f}", media_player):
                        return f"Volumen de YouTube a {vol}%."
                except ValueError:
                    pass
            return "No se pudo ajustar volumen."

        return f"Acción '{action}' no disponible."

    # --- Play video ---
    if action == "play":
        if url_param:
            video_url = url_param
        elif query:
            results = _yt_search(query)
            if results:
                video_id = results[0].get("id", "")
                title = results[0].get("title", "")
                video_url = f"https://youtube.com/watch?v={video_id}"
            else:
                fallback = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
                open_url(fallback, workspace=workspace)
                return f"Buscando '{query}' en YouTube (no se encontró resultado exacto)."
        else:
            return "Indicame qué video o canción reproducir en YouTube."

        open_url(video_url, workspace=workspace)
        title_local = title if 'title' in locals() and title else video_url
        msg = f"Reproduciendo {title_local} en YouTube."
        if player:
            player.write_log(f"📺 {msg}")
        return msg

    # --- Play suggested video in current tab (no new tab) ---
    if action == "play_in_tab":
        if query:
            results = _yt_search(query)
            if results:
                video_id = results[0].get("id", "")
                title = results[0].get("title", "")
                video_url = f"https://youtube.com/watch?v={video_id}"
            else:
                return f"No encontré '{query}' en YouTube."
        elif url_param:
            video_url = url_param
        else:
            return "Indicame qué video reproducir en la pestaña actual."

        title_local = title if 'title' in locals() and title else video_url

        old_title = _get_current_video_title()

        if _navigate_current_tab(video_url):
            time.sleep(2.0)
            new_title = _get_current_video_title()
            if new_title and new_title != old_title:
                msg = f"Reproduciendo {title_local} en la misma pestaña."
                if player:
                    player.write_log(f"📺 {msg}")
                return msg

        # Fallback 1: try open_url (opens as new tab in same window)
        if player:
            player.write_log("⚠️ No se pudo navegar la pestaña actual. Abriendo como nueva pestaña...")
        open_url(video_url, workspace=workspace)
        msg = f"Reproduciendo {title_local} en una nueva pestaña (no se pudo navegar la actual)."
        if player:
            player.write_log(f"📺 {msg}")
        return msg

    # --- Search YouTube ---
    elif action == "search":
        if not query:
            return "Indicame qué buscar en YouTube."
        url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
        open_url(url, workspace=workspace)
        return f"Mostrando resultados de '{query}' en YouTube."

    else:
        return f"Acción '{action}' no soportada."
