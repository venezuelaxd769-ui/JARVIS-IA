"""game_kb.py — Controles de juego por teclado/ratón (multiplataforma, pyautogui).

Reemplazo con fuente del módulo .pyc original (Linux/ydotool). API compatible
con main.py: look, move, attack, use, jump, sneak, sprint, inventory,
select_slot, drop, mine_block, place_block, key_press, key_down, key_up,
mouse_click, escape, game_status.
"""
import time

import pyautogui

pyautogui.FAILSAFE = True

_DIRECTION_KEYS = {"forward": "w", "back": "s", "left": "a", "right": "d"}


def _hold(key, duration):
    pyautogui.keyDown(key)
    time.sleep(duration)
    pyautogui.keyUp(key)


def look(dx, dy):
    pyautogui.moveRel(int(dx), int(dy), duration=0.1)


def move(direction="forward", duration=1.0):
    key = _DIRECTION_KEYS.get(str(direction).lower(), "w")
    _hold(key, max(0.05, float(duration)))


def attack(duration=0.5):
    pyautogui.mouseDown(button="left")
    time.sleep(max(0.05, float(duration)))
    pyautogui.mouseUp(button="left")


def use():
    pyautogui.click(button="right")


def jump():
    pyautogui.press("space")


def sneak(duration=0.5):
    _hold("shift", max(0.05, float(duration)))


def sprint(duration=1.0):
    pyautogui.keyDown("ctrl")
    time.sleep(max(0.05, float(duration)))
    pyautogui.keyUp("ctrl")


def inventory():
    pyautogui.press("e")


def select_slot(slot):
    slot = int(slot)
    if 1 <= slot <= 9:
        pyautogui.press(str(slot))


def drop():
    pyautogui.press("q")


def mine_block(direction="forward", duration=3.0):
    pyautogui.mouseDown(button="left")
    time.sleep(max(0.1, float(duration)))
    pyautogui.mouseUp(button="left")


def place_block():
    pyautogui.click(button="right")


def key_press(key):
    pyautogui.press(str(key))


def key_down(key):
    pyautogui.keyDown(str(key))


def key_up(key):
    pyautogui.keyUp(str(key))


def mouse_click(button="left"):
    pyautogui.click(button=str(button))


def escape():
    pyautogui.press("esc")


def game_status():
    return {
        "proceso": "simulado",
        "activo": True,
        "soporte": "pyautogui",
        "mensaje": "Modo juego emulado vía pyautogui (multiplataforma).",
    }