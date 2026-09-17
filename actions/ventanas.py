# -*- coding: utf-8 -*-
"""ventanas.py — Ordenar ventanas por voz (Windows, ctypes).

Maximiza, parte a la izquierda/derecha, arma lado a lado, cuadrícula 2x2,
centra o minimiza ventanas buscándolas por título.
"""
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
_EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

SW_RESTORE = 9
SW_MAXIMIZE = 3
SW_MINIMIZE = 6
SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004
_work = None


def _work_area():
    global _work
    if _work:
        return _work
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    rect = RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
    _work = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    return _work


def _visibles():
    r = []

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        r.append((hwnd, buf.value))
        return True

    user32.EnumWindows(_EnumWindowsProc(cb), 0)
    return r


def _hallar(titulo):
    t = titulo.strip().lower()
    for hwnd, txt in _visibles():
        if t in txt.lower():
            return hwnd, txt
    return None, None


def _posicionar(hwnd, x, y, w, h):
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetWindowPos(hwnd, 0, x, y, max(w, 1), max(h, 1),
                        SWP_NOACTIVATE | SWP_NOZORDER)


def _ventana_ok(titulo, tipo):
    if not titulo:
        return None, f"Decime qué ventana (titulo). Ej: '{tipo}' el Chrome."
    hwnd, txt = _hallar(titulo)
    if not hwnd:
        abiertas = [v for _, v in _visibles()][:15]
        sugerencia = "\n".join(f"   • {v}" for v in abiertas) or "(no hay ventanas visibles)"
        return None, (f"No encontré '{titulo}'. ¿Seguro que está abierta en primer plano?\n"
                      f"Ventanas abiertas:\n{sugerencia}")
    return hwnd, None


def ventanas(parameters: dict, player=None, speak=None) -> str:
    """Orden y tamaño de ventanas por voz (Windows)."""
    action = str(parameters.get("action", "listar")).strip().lower()
    titulo = str(parameters.get("titulo", "") or parameters.get("ventana", "")).strip()
    t1 = str(parameters.get("titulo1", "") or parameters.get("a", "")).strip()
    t2 = str(parameters.get("titulo2", "") or parameters.get("b", "")).strip()
    t3 = str(parameters.get("titulo3", "") or parameters.get("c", "")).strip()
    t4 = str(parameters.get("titulo4", "") or parameters.get("d", "")).strip()
    if player:
        player.write_log(f"🪟 ventanas: {action}")

    x, y, wa, ha = _work_area()

    if action in ("listar", "lista", "abiertas", "que_ventanas"):
        abiertas = [v for _, v in _visibles()]
        if not abiertas:
            return "No hay ventanas visibles."
        return "🪟 Ventanas abiertas:\n" + "\n".join(f"   • {v}" for v in abiertas[:15])

    if action in ("completa", "maximizar", "max"):
        hwnd, err = _ventana_ok(titulo, action)
        if err:
            return err
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        return f"Maximicé la ventana de '{titulo}'."

    if action in ("minimizar", "min"):
        hwnd, err = _ventana_ok(titulo, action)
        if err:
            return err
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        return f"Minimicé '{titulo}'."

    if action in ("izquierda", "left", "media_izquierda"):
        hwnd, err = _ventana_ok(titulo, action)
        if err:
            return err
        _posicionar(hwnd, x, y, wa // 2, ha)
        return f"Partí '{titulo}' a la izquierda."

    if action in ("derecha", "right", "media_derecha"):
        hwnd, err = _ventana_ok(titulo, action)
        if err:
            return err
        _posicionar(hwnd, x + wa // 2, y, wa - wa // 2, ha)
        return f"Partí '{titulo}' a la derecha."

    if action in ("centrar", "centre", "centro"):
        hwnd, err = _ventana_ok(titulo, action)
        if err:
            return err
        w, h = wa * 3 // 4, ha * 3 // 4
        _posicionar(hwnd, x + (wa - w) // 2, y + (ha - h) // 2, w, h)
        return f"Centré '{titulo}'."

    if action in ("lado_a_lado", "split", "partir", "dos"):
        if not t1:
            return "Decime las ventanas: titulo1 y titulo2 (ej: lado_a_lado con Chrome y Notepad)."
        h1, err1 = _ventana_ok(t1, action)
        h2, err2 = _ventana_ok(t2 or t1, action)
        if err1:
            return err1
        if err2:
            return err2
        _posicionar(h1, x, y, wa // 2, ha)
        _posicionar(h2, x + wa // 2, y, wa - wa // 2, ha)
        return f"Partí la pantalla: '{t1}' a la izquierda y '{t2 or t1}' a la derecha."

    if action in ("cuadricula", "grid", "cuatro", "4"):
        if not t1:
            return "Decime titulo1 a titulo4 (ej: cuadricula con Chrome, Word, Notepad, Explorer)."
        h1, e1 = _ventana_ok(t1, action)
        h2, e2 = _ventana_ok(t2 or t1, action)
        h3, e3 = _ventana_ok(t3 or t1, action)
        h4, e4 = _ventana_ok(t4 or t1, action)
        for e in (e1, e2, e3, e4):
            if e:
                return e
        w, h = wa // 2, ha // 2
        _posicionar(h1, x, y, w, h)
        _posicionar(h2, x + w, y, wa - w, h)
        _posicionar(h3, x, y + h, w, ha - h)
        _posicionar(h4, x + w, y + h, wa - w, ha - h)
        return "Armé la cuadrícula con las 4 ventanas."

    if action in ("resolver", "arreglar", "solucionar"):
        return ("Para ordenar ventanas decime cosas como: 'partí la pantalla: Chrome a la "
                "izquierda y el editor a la derecha', 'maximizá el Notepad', "
                "'armá una cuadrícula con Chrome, Word, Notepad y Explorer', 'centrá esa ventana'.")

    return ("Acciones: listar | completa (titulo) | izquierda | derecha | centrar | "
            "minimizar | lado_a_lado (titulo1, titulo2) | cuadricula (titulo1..4) | resolver.")