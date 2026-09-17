"""mouse_kb.py — Control del ratón (multiplataforma, pyautogui).

Reemplazo con fuente del módulo .pyc original (Linux/ydotool). API compatible
con main.py: get_cursor_pos, move_to, click, move_and_click, double_click,
scroll, drag.
"""
import time

import pyautogui

pyautogui.FAILSAFE = True


def get_cursor_pos():
    return tuple(pyautogui.position())


def move_to(x, y):
    pyautogui.moveTo(int(x), int(y), duration=0.1)


def click(button="left"):
    pyautogui.click(button=str(button))


def move_and_click(x, y):
    pyautogui.moveTo(int(x), int(y), duration=0.1)
    pyautogui.click()
    time.sleep(0.05)


def double_click():
    pyautogui.doubleClick()


def scroll(amount, x=None, y=None):
    amount = int(amount)
    if x is not None and y is not None:
        pyautogui.moveTo(int(x), int(y), duration=0.1)
    pyautogui.scroll(amount if amount > 0 else -abs(amount))


def drag(x1, y1, x2, y2):
    pyautogui.moveTo(int(x1), int(y1), duration=0.1)
    pyautogui.dragTo(int(x2), int(y2), duration=0.3, button="left")