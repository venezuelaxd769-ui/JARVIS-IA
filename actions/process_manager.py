"""process_manager.py — Gestiona procesos del sistema.

Lista procesos en ejecución, busca por nombre, mata procesos,
muestra info detallada. Usa psutil si está disponible, fallback
a subprocess con ps/kill.
"""
import os
import signal
import subprocess


def _psutil_available():
    try:
        import psutil
        return True
    except ImportError:
        return False


def _list_psutil(name=None, limit=30):
    import psutil
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info",
                                   "status", "username", "create_time"]):
        try:
            info = p.info
            if name and name.lower() not in info["name"].lower():
                continue
            mem = info["memory_info"]
            procs.append({
                "pid": info["pid"],
                "name": info["name"],
                "cpu": info["cpu_percent"],
                "mem_mb": round(mem.rss / 1024 / 1024, 1) if mem else 0,
                "status": info["status"],
                "user": info.get("username", "?"),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    procs.sort(key=lambda x: -x["mem_mb"])
    return procs[:limit]


def _list_ps(name=None, limit=30):
    """Fallback: parsea output de ps."""
    result = subprocess.run(
        ["ps", "aux", "--sort=-rss"],
        capture_output=True, text=True, timeout=5,
    )
    procs = []
    for line in result.stdout.split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        user, pid, cpu, mem = parts[0], parts[1], parts[2], parts[3]
        cmd = parts[10]
        pname = cmd.split()[0] if cmd else "?"
        if name and name.lower() not in pname.lower():
            continue
        try:
            procs.append({
                "pid": int(pid), "name": pname,
                "cpu": float(cpu), "mem_mb": float(mem),
                "status": "running", "user": user,
            })
        except ValueError:
            continue
    return procs[:limit]


def _kill_pid(pid, sig="SIGTERM"):
    """Mata un proceso por PID."""
    try:
        pid = int(pid)
        sig_val = getattr(signal, sig.upper(), signal.SIGTERM)
        os.kill(pid, sig_val)
        return True, f"Señal {sig} enviada a PID {pid}"
    except ProcessLookupError:
        return False, f"Proceso {pid} no encontrado"
    except PermissionError:
        return False, f"Sin permisos para matar PID {pid}"
    except Exception as e:
        return False, f"Error: {e}"


def process_manager(parameters: dict, player=None) -> str:
    """Gestiona procesos: listar, buscar, matar."""
    action = str(parameters.get("action", "list")).lower().strip()
    name = str(parameters.get("name", "")).strip()
    pid = str(parameters.get("pid", "")).strip()
    signal_name = str(parameters.get("signal", "SIGTERM")).strip()
    limit = int(parameters.get("limit", 30))

    if action in ("list", "ls", "ver"):
        if player:
            player.write_log(f"📋 Listando procesos...")
        if _psutil_available():
            procs = _list_psutil(name=name, limit=limit)
        else:
            procs = _list_ps(name=name, limit=limit)

        if not procs:
            return "No se encontraron procesos."

        lines = [f"📋 {len(procs)} proceso(s):\n"]
        lines.append(f"{'PID':>7} {'CPU%':>6} {'RAM MB':>8} {'Nombre':<25}")
        lines.append("─" * 55)
        for p in procs:
            lines.append(f"{p['pid']:>7} {p['cpu']:>6.1f} {p['mem_mb']:>8.1f} {p['name'][:25]:<25}")

        return "\n".join(lines)

    if action in ("kill", "matar", "k"):
        if not pid:
            return "Necesito el PID para matar un proceso."
        if player:
            player.write_log(f"🔫 Matando proceso {pid}...")
        ok, msg = _kill_pid(pid, signal_name)
        return f"{'✅' if ok else '❌'} {msg}"

    if action in ("search", "buscar", "s"):
        if not name:
            return "Necesito un nombre para buscar."
        if _psutil_available():
            procs = _list_psutil(name=name, limit=limit)
        else:
            procs = _list_ps(name=name, limit=limit)

        if not procs:
            return f"No encontré procesos con '{name}'."

        lines = [f"🔍 {len(procs)} proceso(s) con '{name}':\n"]
        for p in procs:
            lines.append(f"  PID {p['pid']} — {p['name']} — CPU {p['cpu']}% — RAM {p['mem_mb']} MB")

        return "\n".join(lines)

    return "Acciones: list/ls, kill/matar (requiere pid), search/buscar (requiere name)."
