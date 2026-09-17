# -*- coding: utf-8 -*-
"""uso_pc.py — Seguimiento de uso del PC por voz (Windows).

Un hilo daemon muestrea cada 10 segundos la ventana activa y acumula
cuánto tiempo se pasó en cada aplicación. Los datos se guardan en
memory/uso_pc.json y se pueden consultar por voz.
"""
import ctypes
import ctypes.wintypes
import json
import os
import threading
import time
from datetime import date, timedelta

_DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "memory", "uso_pc.json")
_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_psapi = ctypes.windll.psapi

_THREAD = None
_STOP = threading.Event()
_INTERVALO = 10  # segundos por muestra


def _cargar():
    try:
        with open(_DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _guardar(datos):
    os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
    tmp = _DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    os.replace(tmp, _DATA_FILE)


def _foreground_app():
    try:
        hwnd = _user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        hProc = _kernel32.OpenProcess(0x1000, False, pid.value)
        if not hProc:
            return None
        buf = ctypes.create_unicode_buffer(4096)
        size = ctypes.c_uint32(len(buf))
        ok = _kernel32.QueryFullProcessImageNameW(hProc, 0, buf, ctypes.byref(size))
        _kernel32.CloseHandle(hProc)
        if not ok or not buf.value:
            return None
        name = os.path.basename(buf.value).lower()
        if not name:
            return None
        skip = {"program manager.exe", "systemsettings.exe", "nia.exe",
                "searchapp.exe", "startmenuexperiencehost.exe",
                "shellexperiencehost.exe", "runtimebroker.exe",
                "sihost.exe", "ctfmon.exe"}
        if name in skip:
            return None
        return name
    except Exception:
        return None


def _fmt_seg(secs):
    secs = int(secs)
    h = secs // 3600
    m = (secs % 3600) // 60
    if h > 0:
        return f"{h}h {m}m"
    if m > 0:
        return f"{m}m"
    return f"{max(secs, 5)}s"


def _dia_key(d=None):
    return (d or date.today()).isoformat()


def _semana_keys():
    hoy = date.today()
    return [(hoy - timedelta(days=i)).isoformat() for i in range(7)]


def _acumular(dato, app):
    hoy = _dia_key()
    day = dato.setdefault(hoy, {})
    day[app] = day.get(app, 0) + _INTERVALO
    return day


def _muestrear():
    while not _STOP.is_set():
        app = _foreground_app()
        if app:
            try:
                datos = _cargar()
                _acumular(datos, app)
                _guardar(datos)
            except Exception:
                pass
        time.sleep(_INTERVALO)


def _ensure_thread():
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return
    _STOP.clear()
    _THREAD = threading.Thread(target=_muestrear, daemon=True)
    _THREAD.start()


def _hoy(dato):
    d = dato.get(_dia_key(), {})
    top = sorted(d.items(), key=lambda x: -x[1])[:12]
    if not top:
        return "No tengo datos de uso de hoy (¿empezó el seguimiento?)."
    lineas = ["📊 Uso hoy:"]
    for app, seg in top:
        lineas.append(f"   • {app}: {_fmt_seg(seg)}")
    total = sum(d.values())
    lineas.append(f"   Total: {_fmt_seg(total)}")
    return "\n".join(lineas)


def _semana(dato):
    dias = _semana_keys()
    agg = {}
    for dk in dias:
        for app, seg in dato.get(dk, {}).items():
            agg[app] = agg.get(app, 0) + seg
    top = sorted(agg.items(), key=lambda x: -x[1])[:10]
    if not top:
        return "No tengo datos de uso de esta semana."
    lineas = ["📊 Uso de los últimos 7 días:"]
    for app, seg in top:
        lineas.append(f"   • {app}: {_fmt_seg(seg)}")
    return "\n".join(lineas)


def _app_especifica(dato, nombre):
    n = nombre.lower()
    agg = {}
    for dk in _semana_keys():
        for app, seg in dato.get(dk, {}).items():
            if n in app:
                agg[app] = agg.get(app, 0) + seg
    if not agg:
        return f"No encontré uso de '{nombre}' esta semana."
    lineas = [f"📊 Uso de '{nombre}' esta semana:"]
    for app, seg in sorted(agg.items(), key=lambda x: -x[1]):
        lineas.append(f"   • {app}: {_fmt_seg(seg)}")
    return "\n".join(lineas)


def uso_pc(parameters: dict, player=None, speak=None) -> str:
    """Seguimiento de uso del PC: qué apps usás y cuánto tiempo."""
    action = str(parameters.get("action", "hoy")).strip().lower()
    nombre = str(parameters.get("app", "")).strip()
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")
    if player:
        player.write_log(f"⏱️ uso_pc: {action}")

    if action in ("empezar", "start", "iniciar", "on"):
        _ensure_thread()
        return "Empecé a registrar tu uso de apps."

    if action in ("parar", "stop", "detener", "off"):
        _STOP.set()
        return "Detuve el seguimiento de uso."

    if action in ("hoy", "today", "resumen"):
        _ensure_thread()
        return _hoy(_cargar())

    if action in ("semana", "weekly", "ultimos_7"):
        _ensure_thread()
        return _semana(_cargar())

    if action in ("app", "buscar", "por_app"):
        if not nombre:
            return "Decime de cuál app querés saber (app). Ej: '¿cuánto estuve en Chrome?'"
        return _app_especifica(_cargar(), nombre)

    if action in ("top", "ranking"):
        datos = _cargar()
        agg = {}
        for dk in _semana_keys():
            for app, seg in datos.get(dk, {}).items():
                agg[app] = agg.get(app, 0) + seg
        top = sorted(agg.items(), key=lambda x: -x[1])[:10]
        if not top:
            return "No hay datos suficientes."
        lineas = ["🏆 Top apps esta semana:"]
        for i, (app, seg) in enumerate(top, 1):
            lineas.append(f"   {i}. {app}: {_fmt_seg(seg)}")
        return "\n".join(lineas)

    if action in ("borrar", "reset", "limpiar"):
        if not ok:
            return "Voy a BORRAR todos los datos de uso acumulados. Confirmá con 'SÍ'."
        _guardar({})
        return "Datos de uso borrados."

    _ensure_thread()
    return ("Acciones: hoy | semana | app (nombre) | top | empezar | parar | borrar (SÍ).")


if __name__ == "__main__":
    _ensure_thread()
    print("Seguimiento activo. Ctrl+C para parar.")
    try:
        while True:
            time.sleep(30)
            print(_hoy(_cargar()))
    except KeyboardInterrupt:
        _STOP.set()
        print("Detenido.")