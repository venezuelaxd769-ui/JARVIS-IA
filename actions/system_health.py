# -*- coding: utf-8 -*-
"""system_health.py — Salud del equipo por voz (Windows).

Reporte rápido de RAM/CPU/disco, procesos más pesados por nombre y
vigilancia de RAM crítica en segundo plano con aviso por voz.
"""
import os
import threading
import time

_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")

_vigilancia_thread = None
_vigilancia_stop = threading.Event()
_vigilancia_ya_aviso = False


def _fmt_b(b, dec=1):
    b = float(b)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or u == "TB":
            return f"{b:.{dec}f} {u}"
        b /= 1024.0


def _mem():
    psutil = __import__("psutil")
    vm = psutil.virtual_memory()
    return vm


def _estado():
    psutil = __import__("psutil")
    vm = _mem()
    libre = _fmt_b(vm.available)
    total = _fmt_b(vm.total)
    pct = vm.percent
    cpu = psutil.cpu_percent(interval=0.4)
    lines = [f"🧠 RAM: {pct:.0f}% usada — {libre} libre de {total}",
             f"⚙️  CPU: {cpu:.0f}%",
             f"🔋 Estado procesadores: {psutil.cpu_count()} núcleos"]
    try:
        for part in psutil.disk_partitions():
            if part.fstype:
                u = psutil.disk_usage(part.mountpoint)
                lines.append(f"💾 {part.mountpoint}: {_fmt_b(u.free)} libre de {_fmt_b(u.total)}")
    except Exception:
        pass
    return "\n".join(lines)


def _top(n=5):
    psutil = __import__("psutil")
    procs = []
    for p in psutil.process_iter(["name", "memory_info", "cpu_percent"]):
        try:
            procs.append((p.info["memory_info"].rss or 0, p.info["cpu_percent"] or 0,
                          p.info["name"]))
        except Exception:
            continue
    procs.sort(key=lambda x: (-x[0], -x[1]))
    lines = ["🏆 Procesos que más RAM usan:"]
    for rss, cpu, name in procs[:n]:
        lines.append(f"   • {_fmt_b(rss, 0)} — {name}")
    return "\n".join(lines)


def _matar(nombre):
    import subprocess
    if not nombre:
        return "Decime qué proceso quiero matar (name). Ej: 'matá el Brave'."
    base = os.path.basename(nombre.strip().replace("\\", "/")).lower()
    if not base:
        return "Ese nombre de proceso no es válido."
    if not base.endswith(".exe"):
        base += ".exe"
    if any(c in base for c in ":/\\*?\"<>|") or base.startswith("."):
        return f"'{base}' no parece un proceso válido."
    try:
        r = subprocess.run(["taskkill", "/F", "/T", "/IM", base],
                           capture_output=True, text=True, timeout=30,
                           creationflags=0x08000000)
        ok = r.returncode == 0
        msg = (r.stdout or r.stderr or "").strip().splitlines()
        detalle = msg[-1].strip() if msg else ""
        if ok and "kill" in detalle.lower():
            return f"Listo, maté {base}. {detalle}"
        if ok:
            return f"Listo, maté {base}."
        # retry pidiendo solo el proceso sin árbol si falló por hijos en otras sesiones
        r2 = subprocess.run(["taskkill", "/F", "/IM", base],
                            capture_output=True, text=True, timeout=30,
                            creationflags=0x08000000)
        if r2.returncode == 0:
            return f"Listo, maté {base}."
        return f"No pude matar {base}: {detalle or 'no se encontró o falta permiso'}"
    except Exception as e:
        return f"No pude matar {base}: {e}"


def _vigilar(porcentaje, speak):
    global _vigilancia_ya_aviso
    psutil = __import__("psutil")
    vm_total = psutil.virtual_memory().total
    limite = max(150 * 1024 * 1024, vm_total * porcentaje / 100.0)
    while not _vigilancia_stop.is_set():
        vm = psutil.virtual_memory()
        criticos = vm.available < limite
        if criticos and not _vigilancia_ya_aviso:
            _vigilancia_ya_aviso = True
            libre = _fmt_b(vm.available)
            try:
                if speak:
                    speak(f"Cuidado: te está quedando muy poca memoria libre, {libre}."
                          " Cerré algunos programas para que Nia siga escuchándote.")
            except Exception:
                pass
        elif not criticos and _vigilancia_ya_aviso:
            _vigilancia_ya_aviso = False
        time.sleep(20)


def system_health(parameters: dict, player=None, speak=None) -> str:
    """Salud del equipo: RAM/CPU/disco, matar procesos por nombre y vigilar RAM."""
    global _vigilancia_thread, _vigilancia_stop, _vigilancia_ya_aviso
    action = str(parameters.get("action", "estado")).strip().lower()
    nombre = str(parameters.get("name", "")).strip()
    confirm = str(parameters.get("confirm", "")).strip().lower()
    ok = confirm in _CONFIRM
    if player:
        player.write_log(f"🩺 system_health: {action}")

    if action in ("estado", "health", "reporte", "ram", "resumen"):
        return _estado() + "\n\n" + _top(5)

    if action in ("matar", "kill", "terminar"):
        if not ok:
            return f"Voy a FORZAR el cierre de todos los procesos '{nombre or '?'}'. Confirmá con 'SÍ'."
        return _matar(nombre)

    if action in ("vigilar", "watch", "monitorear"):
        modo = str(parameters.get("modo", "")).strip().lower()
        if modo in ("off", "apagar", "parar", "stop", "0", "no"):
            _vigilancia_stop.set()
            _vigilancia_thread = None
            return "Dejé de vigilar la memoria."
        if _vigilancia_thread and _vigilancia_thread.is_alive():
            return "Ya estoy vigilando la memoria. Decime 'parar' para detenerlo."
        porcentaje = max(1, min(25, float(parameters.get("porcentaje") or 8)))
        _vigilancia_stop = threading.Event()
        _vigilancia_thread = threading.Thread(
            target=_vigilancia, args=(porcentaje, speak), daemon=True)
        _vigilancia_thread.start()
        return (f"Empecé a vigilar la memoria: te aviso por voz si la RAM libre "
                f"baja del {porcentaje:.0f}%.")

    if action in ("top", "pesados"):
        return _top(int(parameters.get("cantidad") or 5))

    return ("Acciones: estado (RAM/CPU/disco + top) | matar (name + SÍ) | "
            "vigilar (modo='off' para parar, porcentaje opcional) | top (cantidad).")