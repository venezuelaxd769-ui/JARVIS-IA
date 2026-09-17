"""web_kb.py — Control del navegador por teclado (multiplataforma).

Reemplazo con fuente del módulo .pyc original (Linux/ydotool). Usa
pyautogui (teclado virtual) y webbrowser (apertura de URL). API compatible
con main.py: go_to, navigate_and_click, type_text, tab, new_tab, close_tab,
search_bar, search_on_page, get_active_window_title, google_search,
youtube_search, full_browse_session, switch_tab, go_back, go_forward, scroll,
scroll_up, scroll_down, arrow, reopen_closed_tab, enter, reload.
"""
import time
from urllib.parse import quote

import pyautogui

pyautogui.FAILSAFE = True


def _url(url):
    url = str(url).strip()
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


def go_to(url):
    import webbrowser
    webbrowser.open(_url(url))
    time.sleep(1.2)


def google_search(text):
    import webbrowser
    webbrowser.open("https://www.google.com/search?q=" + quote(str(text)))
    time.sleep(1.0)


def youtube_search(text):
    import webbrowser
    webbrowser.open("https://www.youtube.com/results?search_query=" + quote(str(text)))
    time.sleep(1.0)


def search_bar():
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.3)


def search_on_page(text):
    pyautogui.hotkey("ctrl", "f")
    time.sleep(0.4)
    pyautogui.write(str(text), interval=0.01)
    pyautogui.press("enter")


def type_text(text):
    pyautogui.write(str(text), interval=0.005)


def enter():
    pyautogui.press("enter")


def tab(times=1):
    for _ in range(max(1, int(times or 1))):
        pyautogui.press("tab")
        time.sleep(0.05)


def new_tab():
    pyautogui.hotkey("ctrl", "t")
    time.sleep(0.6)


def close_tab():
    pyautogui.hotkey("ctrl", "w")
    time.sleep(0.2)


def reopen_closed_tab():
    pyautogui.hotkey("ctrl", "shift", "t")
    time.sleep(0.4)


def switch_tab(index):
    index = int(index)
    if 1 <= index <= 9:
        pyautogui.hotkey("ctrl", str(index))
        time.sleep(0.5)


def go_back():
    pyautogui.hotkey("alt", "left")
    time.sleep(0.4)


def go_forward():
    pyautogui.hotkey("alt", "right")
    time.sleep(0.4)


def reload():
    pyautogui.hotkey("ctrl", "r")
    time.sleep(0.5)


def scroll_up(times=1):
    pyautogui.scroll(max(1, int(times or 1)) * 3)


def scroll_down(times=1):
    pyautogui.scroll(-max(1, int(times or 1)) * 3)


def scroll(direction="down", times=1):
    if direction == "up":
        scroll_up(times)
    else:
        scroll_down(times)


def arrow(direction="down", times=1):
    key = {"up": "up", "down": "down", "left": "left", "right": "right"}.get(
        str(direction).lower(), "down")
    for _ in range(max(1, int(times or 1))):
        pyautogui.press(key)
        time.sleep(0.04)


def get_active_window_title():
    try:
        import pygetwindow
        w = pygetwindow.getActiveWindow()
        return w.title or "" if w else ""
    except Exception:
        return ""


def navigate_and_click(tab_presses=30, enter_every=10):
    tp = max(1, int(tab_presses))
    ee = max(1, int(enter_every))
    for i in range(tp):
        pyautogui.press("tab")
        time.sleep(0.06)
        if i > 0 and i % ee == 0:
            time.sleep(0.6)
    title = get_active_window_title()
    return bool(title), title


def full_browse_session(url):
    go_to(url)
    time.sleep(2.2)
    return get_active_window_title()