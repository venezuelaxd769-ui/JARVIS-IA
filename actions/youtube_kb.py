"""youtube_kb.py — Control de YouTube por teclado (multiplataforma).

Reemplazo con fuente del módulo .pyc original (Linux/ydotool). API compatible
con main.py: open_recommended_video, search, search_and_open, play_pause,
mute, fullscreen, seek_forward, seek_backward.
"""
import time
from urllib.parse import quote

import pyautogui

pyautogui.FAILSAFE = True


def _open_url(url):
    import webbrowser
    webbrowser.open(url)


def search(query):
    _open_url("https://www.youtube.com/results?search_query=" + quote(str(query)))
    time.sleep(1.2)


def search_and_open(query):
    _open_url("https://www.youtube.com/results?search_query=" + quote(str(query)))
    time.sleep(3.2)
    for _ in range(3):
        pyautogui.press("tab")
        time.sleep(0.1)
    pyautogui.press("enter")
    time.sleep(1.5)


def open_recommended_video():
    _open_url("https://www.youtube.com")
    time.sleep(2.6)
    for _ in range(6):
        pyautogui.press("tab")
        time.sleep(0.1)
    pyautogui.press("enter")
    time.sleep(2.0)
    try:
        import pygetwindow
        w = pygetwindow.getActiveWindow()
        title = w.title or "" if w else ""
    except Exception:
        title = ""
    return bool(title), title


def play_pause():
    pyautogui.press("k")


def mute():
    pyautogui.press("m")


def fullscreen():
    pyautogui.press("f")


def seek_forward(seconds=10):
    steps = max(1, int(seconds) // 10)
    for _ in range(steps):
        pyautogui.hotkey("shift", "right")
        time.sleep(0.05)


def seek_backward(seconds=10):
    steps = max(1, int(seconds) // 10)
    for _ in range(steps):
        pyautogui.hotkey("shift", "left")
        time.sleep(0.05)