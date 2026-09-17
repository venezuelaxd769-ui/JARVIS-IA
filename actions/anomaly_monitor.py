"""anomaly_monitor.py — Detección de anomalías del sistema con baseline (estilo Cryp).

Nia aprende "lo normal" por franja horaria (CPU/RAM/proceso top de cada hora del
día, con una ventana deslizante) y avisa solo cuando una lectura se desvía
>2.2σ respecto a su propia normalidad Y supera un umbral absoluto. Así captura
casos que un umbral fijo nunca ve (un proceso que nunca usaba CPU y de golpe
come 40%) sin volverse ruidosa.

Persistencia: memory/anomaly_hourly.json  ·  tool: anomaly_monitor
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_BASE = Path(__file__).resolve().parent.parent
_STORE = _BASE / "memory" / "anomaly_hourly.json"

_MAX_PER_BUCKET = 60     # hasta ~5 h de muestras por hora del día
_MIN_SAMPLES = 6         # mínimo de muestras para calcular baseline
_Z_THRESHOLD = 2.2       # desviación estándar exigida
_HIGH_THRESHOLD = {"cpu": 60.0, "ram": 80.0, "top": 55.0}


def _read() -> dict:
    try:
        if _STORE.exists():
            data = json.loads(_STORE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _write(data: dict):
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        _STORE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _system_reading() -> dict:
    reading = {"cpu": 0.0, "ram": 0.0, "top": 0.0, "top_name": ""}
    try:
        import psutil
        reading["cpu"] = float(psutil.cpu_percent(interval=0.2))
        reading["ram"] = float(psutil.virtual_memory().percent)
        try:
            top = max(
                psutil.process_iter(["name", "cpu_percent"]),
                key=lambda p: p.info["cpu_percent"] or 0,
            )
            reading["top"] = float(top.info.get("cpu_percent", 0.0) or 0.0)
            reading["top_name"] = str(top.info.get("name", ""))
        except Exception:
            pass
    except Exception:
        pass
    return reading


def record_sample(force: dict = None) -> None:
    """Registra una muestra del estado actual (o `force`) en su balde horario."""
    reading = _system_reading() if not force else {
        "cpu": float(force.get("cpu", 0.0)),
        "ram": float(force.get("ram", 0.0)),
        "top": float(force.get("top", 0.0)),
        "top_name": str(force.get("top_name", "")),
    }
    hour = str(datetime.now().hour)
    data = _read()
    bucket = data.setdefault(hour, [])
    bucket.append({"ts": time.time(),
                   "cpu": reading["cpu"], "ram": reading["ram"],
                   "top": reading["top"], "top_name": reading["top_name"]})
    if len(bucket) > _MAX_PER_BUCKET:
        bucket = bucket[-_MAX_PER_BUCKET:]
        data[hour] = bucket
    data["_last"] = reading
    _write(data)


def _mean_std(vals):
    n = len(vals)
    if n == 0:
        return 0.0, 0.0
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    return mean, var ** 0.5


def detect_anomaly(reading: dict = None) -> dict | None:
    """Compara la lectura actual contra su baseline horario (z-score 2σ).

    Exige DESVIACIÓN GAUSSiana Y umbral absoluto Y que la muestra anterior ya
    venía alta (desviación sostenida, no un pico de 20 ms).
    """
    data = _read()
    hour = str(datetime.now().hour)
    bucket = data.get(hour, []) or []
    if len(bucket) < _MIN_SAMPLES:
        return None

    r = reading or data.get("_last") or _system_reading()
    candidates = []
    for name in ("cpu", "ram", "top"):
        val = float(r.get(name, 0.0))
        vals = [float(b.get(name, 0.0)) for b in bucket]
        mean, std = _mean_std(vals)
        if std < 1e-6:
            continue
        z = (val - mean) / std
        if z > _Z_THRESHOLD and val > _HIGH_THRESHOLD.get(name, 60.0):
            prev = bucket[-2] if len(bucket) > 1 else None
            sustained = bool(prev and prev.get(name, 0.0) > mean + std)
            if sustained:
                candidates.append({
                    "metric": name, "value": round(val, 1),
                    "mean": round(mean, 1), "z": round(z, 2),
                    "top_name": r.get("top_name", ""), "n": len(bucket),
                })

    if not candidates:
        return None
    candidates.sort(key=lambda c: c["z"], reverse=True)
    return candidates[0]


def anomaly_monitor(parameters: dict, player=None) -> str:
    """Tool: status (baseline por hora), detect (anomalía ahora) o reset (borrar)."""
    action = str(parameters.get("action", "detect")).lower()

    if action in ("reset", "borrar"):
        _write({})
        return "Baseline de normalidad borrado. Voy a volver a aprender desde cero."

    if action in ("status", "ver"):
        data = _read()
        hours = {k: len(v) for k, v in data.items() if k.isdigit()}
        if not hours:
            return ("Todavía no tengo baseline de normalidad. "
                    "Lleva un par de horas de uso para aprender.")
        lines = ["📊 Baseline de normalidad (muestras por hora del día):"]
        for h in sorted(hours, key=int):
            lines.append(f"  {int(h):02d}:00 → {hours[h]} muestras")
        lines.append(f"Último estado: {data.get('_last', {})}")
        return "\n".join(lines)

    anomaly = detect_anomaly()
    if not anomaly:
        return ("No hay anomalías: todo dentro de mi baseline de normalidad "
                f"(última muestra {data_latest()}).")
    metric_name = {"cpu": "CPU", "ram": "RAM", "top": "proceso"}.get(
        anomaly["metric"], anomaly["metric"])
    extra = f" ({anomaly['top_name']})" if anomaly["top_name"] and anomaly["metric"] == "top" else ""
    return (f"¡Anomalía! {metric_name} al {anomaly['value']}% cuando normalmente "
            f"está en {anomaly['mean']}% (desviación {anomaly['z']}σ){extra}.")


def data_latest() -> str:
    data = _read()
    last = data.get("_last", {})
    if not last:
        return "sin datos"
    return (f"CPU {last.get('cpu', 0):.0f}% · RAM {last.get('ram', 0):.0f}% · "
            f"top {last.get('top_name', '?')} "
            f"{last.get('top', 0):.0f}%")