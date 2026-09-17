"""timer.py — Temporizador y alarma de cuenta regresiva."""
import threading
import time

_active = {}  # key -> {"label": str, "hasta": float}
_lock = threading.Lock()


def _parse_seconds(value):
    v = str(value or "").strip().lower()
    try:
        if v.endswith("s"):
            return max(1, int(float(v[:-1])))
        if v.endswith("m"):
            return max(1, int(float(v[:-1]) * 60))
        if v.endswith("h"):
            return max(1, int(float(v[:-1]) * 3600))
        if v.endswith("ms"):
            return max(1, int(float(v[:-2]) / 1000))
        return max(1, int(float(v)))
    except Exception:
        return None


def _formato(seg):
    seg = max(0, int(seg))
    h = seg // 3600
    m = (seg % 3600) // 60
    s = seg % 60
    if h:
        return f"{h} h {m} min"
    if m:
        return f"{m} min {s} s"
    return f"{s} s"


def timer(parameters: dict, player=None, speak=None) -> str:
    """Establece un temporizador/cuenta regresiva y avisa al cumplirse."""
    action = str(parameters.get("action", "start")).lower().strip()
    label = str(parameters.get("label", "") or parameters.get("message", "")).strip()

    if action in ("estado", "falta", "listar"):
        with _lock:
            vivos = []
            ahora = time.time()
            for key, info in list(_active.items()):
                restan = info["hasta"] - ahora
                if restan <= 0:
                    _active.pop(key, None)
                    continue
                vivos.append(f"{info['label']} ({_formato(restan)})")
        if not vivos:
            return "No hay ningún temporizador en marcha. Cuando quieras, decime 'poné un timer de 5 minutos'."
        return "Temporizadores en marcha: " + ", ".join(vivos) + "."

    if action in ("cancel", "stop", "cancelar"):
        key = label.lower() if label else None
        with _lock:
            if key is None:
                n = len(_active)
                _active.clear()
                if player:
                    player.write_log(f"⏱️ Temporizadores cancelados ({n}).")
                return f"Cancelé {n} temporizador(es)."
            found = _active.pop(key, None)
        if found:
            if player:
                player.write_log(f"⏱️ Temporizador '{label}' cancelado.")
            return f"Cancelé el temporizador '{label}'."
        return f"No hay ningún temporizador activo con '{label}'."

    if action not in ("start", "poner", "set", "iniciar", "temporizador"):
        return "Acciones: poner | estado | cancelar. Por ejemplo 'poner' con duration='90'."

    seconds = _parse_seconds(parameters.get("duration", "") or parameters.get("time", ""))
    if seconds is None:
        return "Decime la duración, por ejemplo duration='90' (segundos), '5m' o '2h'."

    if not label:
        label = f"Temporizador de {parameters.get('duration') or seconds} segundos"
    key = label.lower()
    with _lock:
        _active[key] = {"label": label, "hasta": time.time() + seconds}

    def _run():
        try:
            time.sleep(seconds)
        finally:
            with _lock:
                _active.pop(key, None)
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass
        message = f"⏰ {label}"
        if player:
            player.write_log(message)
        if speak:
            try:
                speak(f"Se cumplió el tiempo: {label}.")
                return
            except Exception:
                pass
        if player:
            try:
                player.write_log(f"🔔 {label} — tiempo cumplido.")
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True).start()

    if player:
        player.write_log(f"⏱️ {label} — suena en {seconds} segundos.")
    return (f"Listo, suena en {seconds} segundos ({label}). "
            f"Te aviso cuando se cumpla.")
