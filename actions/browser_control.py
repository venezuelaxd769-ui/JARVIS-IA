"""browser_control.py — URL opening without duplicate windows."""
import subprocess
import shutil
import urllib.parse

_HAS_HYPRCTL = shutil.which("hyprctl") is not None

BROWSER_MAP = [
    ("brave-browser", "brave"),
    ("google-chrome", "google-chrome-stable"),
    ("chromium", "chromium"),
    ("firefox", "firefox"),
    ("firefox-esr", "firefox-esr"),
    ("microsoft-edge", "microsoft-edge"),
]

_BROWSER_CLASSES = [c for c, _ in BROWSER_MAP]


def _find_default_browser() -> tuple[str, str] | None:
    for cls, bin_name in BROWSER_MAP:
        if shutil.which(bin_name):
            return (cls, bin_name)
    return None


def _hyprctl(cmd: list[str]) -> str:
    try:
        return subprocess.run(["hyprctl"] + cmd, capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ""


def _go_to_workspace(num: int):
    try:
        subprocess.run(["hyprctl", "dispatch", "workspace", str(num)],
                       capture_output=True, timeout=5)
        import time
        time.sleep(0.3)
    except Exception:
        pass


def _browser_on_workspace(workspace: int) -> str | None:
    """Check if any browser window exists on the given workspace.
    Returns its class name if found, None otherwise."""
    r = _hyprctl(["clients", "-j"])
    if not r:
        return None
    import json, time
    try:
        clients = json.loads(r)
    except Exception:
        return None
    for c in clients:
        if c.get("workspace", {}).get("id") == workspace:
            cls = c.get("class", "").lower()
            for bcls in _BROWSER_CLASSES:
                if bcls in cls:
                    return c.get("class", "")
    return None


def open_url(url: str, new_window: bool = False, workspace: int | None = None) -> bool:
    """Open URL in the default browser. By default opens as a tab in existing window.
    Set new_window=True to force a new window.
    Set workspace=N to switch to that workspace and open there."""
    import time
    browser = _find_default_browser()
    if not browser:
        import webbrowser
        webbrowser.open(url)
        return False
    cls, bin_name = browser

    if workspace is not None:
        _go_to_workspace(workspace)
        time.sleep(0.15)
        existing = _browser_on_workspace(workspace)
        if existing:
            # Browser already here → focus it and open a tab via hyprctl
            _hyprctl(["dispatch", "focuswindow", existing])
            time.sleep(0.15)
            # Open as a new tab in the existing window
            subprocess.Popen([bin_name, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # No browser here → open a new window on this workspace
            subprocess.Popen([bin_name, "--new-window", url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        # No workspace specified — default behavior
        args = [bin_name, url]
        if new_window:
            args.insert(1, "--new-window")
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def _hyprctl(cmd: list[str]) -> str:
    try:
        return subprocess.run(["hyprctl"] + cmd, capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ""


def browser_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "")
    url = parameters.get("url", "")
    query = parameters.get("query", "")
    index = parameters.get("index", None)
    new_window = parameters.get("new_window", False)
    workspace = parameters.get("workspace", None)
    if workspace is not None:
        try:
            workspace = int(workspace)
        except (ValueError, TypeError):
            workspace = None

    if action == "go_to" or action == "open_result":
        if action == "open_result":
            from actions.web_search import get_last_results
            results = get_last_results()
            if not results:
                return "Error: No hay resultados de búsqueda recientes. Primero usá web_search."
            if index is None:
                return "Error: Para abrir un resultado de búsqueda, pasá el número con 'index'."
            idx = int(index) - 1
            if idx < 0 or idx >= len(results):
                return f"Error: Solo hay {len(results)} resultados (1-{len(results)})."
            url = results[idx]["url"]
        if not url:
            return "Error: Falta la URL."
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url
        if workspace is not None:
            open_url(url, new_window=True, workspace=workspace)
            return f"Navegando a {url} en escritorio {workspace}."
        open_url(url, new_window=new_window)
        return f"Navegando a {url}."

    elif action == "search":
        if not query:
            return "Error: Falta la búsqueda (query)."
        search_url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        if workspace is not None:
            open_url(search_url, new_window=True, workspace=workspace)
            return f"Buscando '{query}' en Google desde escritorio {workspace}."
        open_url(search_url, new_window=new_window)
        return f"Buscando '{query}' en Google."

    elif action == "new_window":
        if url:
            return browser_control({"action": "go_to", "url": url, "new_window": True, "workspace": workspace}, player)
        return "Indicame una URL para abrir en nueva ventana."

    elif action == "close_tab":
        if _HAS_HYPRCTL:
            _hyprctl(["dispatch", "killactive"])
            return "Pestaña/ventana actual cerrada."
        return "Cerrar no está soportado."

    elif action == "new_tab":
        from actions.web_kb import new_tab
        new_tab()
        return "Nueva pestaña abierta."

    else:
        return f"Acción '{action}' no compatible."
