"""desktop_kb.py — Gestión de ventanas/workspaces por teclado (multiplataforma).

Reemplazo con fuente del módulo .pyc original (Linux/Hyprland). En Windows usa
pygetwindow + pyautogui; la API es compatible con main.py: list_windows,
switch_to_app, go_to_workspace, close_window, get_active_window,
move_to_workspace, toggle_fullscreen, maximize_toggle.
"""
import time

import pyautogui


def _windows():
    try:
        import pygetwindow
        return pygetwindow.getAllWindows()
    except Exception:
        return []


def _active_window():
    try:
        import pygetwindow
        return pygetwindow.getActiveWindow()
    except Exception:
        return None


def _find_window(app_class):
    needle = str(app_class).lower().strip()
    if not needle:
        return None
    for w in _windows():
        title = getattr(w, "title", "") or ""
        if title.lower().find(needle) != -1:
            return w
    for w in _windows():
        title = getattr(w, "title", "") or ""
        words = [p.lower() for p in title.replace("-", " ").split() if p]
        if needle in words:
            return w
    return None


def _activate(w):
    try:
        w.activate()
        time.sleep(0.15)
        return True
    except Exception:
        return False


def list_windows():
    out = []
    for w in _windows():
        title = getattr(w, "title", "") or ""
        if not title:
            continue
        out.append({"title": title, "class": title.split(" - ")[-1] or title})
    return out


def get_active_window():
    w = _active_window()
    if not w:
        return {"title": "", "class": ""}
    title = getattr(w, "title", "") or ""
    return {"title": title, "class": title.split(" - ")[-1] or title}


def switch_to_app(app_class):
    w = _find_window(app_class)
    if w:
        return _activate(w)
    return False


def close_window():
    w = _active_window()
    if w:
        try:
            w.close()
            return
        except Exception:
            pass
    pyautogui.hotkey("alt", "f4")


def go_to_workspace(num):
    _workspace_nav(num)


def move_to_workspace(num):
    _workspace_nav(num)


def _workspace_nav(num):
    val = str(num).lower()
    if val in ("next", "derecha", "siguiente", "+"):
        pyautogui.hotkey("win", "ctrl", "right")
    elif val in ("prev", "previo", "izquierda", "-"):
        pyautogui.hotkey("win", "ctrl", "left")
    time.sleep(0.2)


def toggle_fullscreen():
    pyautogui.press("f11")
    time.sleep(0.2)


def maximize_toggle():
    pyautogui.hotkey("win", "up")
    time.sleep(0.2)