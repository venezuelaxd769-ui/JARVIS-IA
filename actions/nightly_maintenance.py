"""nightly_maintenance.py — Mantenimiento nocturno automático (la "Neuro-sleep").

Mientras la PC está idle (ventana 02:00–06:00, una vez por día), Nia corre:
  1. Regresión completa (tests/smoke_tools.py) → acciones OK/FAIL.
  2. Diagnóstico de tools rotas (lecciones training.fallo_* de long_term).
  3. Backup del proyecto (zip en backups/, excluye .venv/caches/logs).
  4. Limpieza de capturas viejas (NiaSandbox/captures > 7 días).

Deja un informe en memory/maintenance_report.json + .md que morning_brief
puede resumir a la mañana. tool: nightly_maintenance (run | report | status).
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, date
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_STATE = _BASE / "memory" / "maintenance_state.json"
_REPORT = _BASE / "memory" / "maintenance_report.json"
_REPORT_MD = _BASE / "memory" / "maintenance_report.md"
_HOUR_START, _HOUR_END = 2, 6
_CAPTURES = Path.home() / "NiaSandbox" / "captures"
_CAPTURES_MAX_DAYS = 7
_log = print


def _state() -> dict:
    try:
        if _STATE.exists():
            return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_state(data: dict):
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _run_smoke() -> dict:
    """Corre la regresión en un subproceso y extrae el resultado."""
    out = ""
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [sys.executable, str(_BASE / "tests" / "smoke_tools.py")],
            cwd=str(_BASE), capture_output=True, text=True,
            timeout=300, env=env,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        out = "TIMEOUT: la regresión tardó más de 5 minutos."
    except Exception as e:
        out = f"ERROR al lanzar la regresión: {e}"

    ok = bool(out and "VEREDICTO: OK" in out)
    failures = []
    for line in out.splitlines():
        if line.strip().startswith("FAIL") and not line.strip().startswith("FAIL:"):
            failures.append(line.strip())
    m_total = 0
    for line in out.splitlines():
        if "Total:" in line:
            m_total = line.strip()
    tail = "\n".join(out.splitlines()[-6:])
    return {"ok": ok, "summary": m_total or "", "failures": failures[:10],
            "tail": tail[:1200]}


def _broken_tools() -> list[str]:
    try:
        from memory.memory_manager import load_memory
        mem = load_memory()
        training = mem.get("training", {})
        if not isinstance(training, dict):
            return []
        names = []
        for key in training:
            if "_" in key and str(key).startswith("fallo_"):
                names.append(str(key).split("_", 1)[1])
        return sorted(set(names))
    except Exception:
        return []


def _zip_project() -> str | None:
    zip_name = f"nia_maintenance_{date.today().isoformat()}.zip"
    zip_path = _BASE / "backups" / zip_name
    if zip_path.exists():
        return str(zip_path)
    exts = {".py", ".json", ".md", ".txt", ".html", ".js", ".css", ".sh", ".bat", ".vbs", ".yaml", ".yml"}
    skip_dirs = {".venv", "node_modules", "__pycache__", ".git", "backups", "logs", ".idea", ".vscode"}
    try:
        zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(_BASE):
                dirs[:] = [d for d in dirs if d not in skip_dirs]
                for f in files:
                    if Path(f).suffix.lower() in exts:
                        fp = Path(root) / f
                        try:
                            zf.write(fp, fp.relative_to(_BASE))
                        except Exception:
                            pass
        return str(zip_path)
    except Exception:
        return None


def _clean_captures() -> int:
    cleaned = 0
    try:
        if not _CAPTURES.exists():
            return 0
        cutoff = time.time() - _CAPTURES_MAX_DAYS * 86400
        for f in _CAPTURES.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < cutoff:
                    f.unlink()
                    cleaned += 1
            except Exception:
                pass
    except Exception:
        pass
    return cleaned


def _write_report(report: dict):
    try:
        _REPORT.parent.mkdir(parents=True, exist_ok=True)
        _REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    lines = [
        f"# Mantenimiento nocturno — {report['date']}",
        "",
        f"- **Regresión**: {'OK ✅' if report['smoke']['ok'] else '⚠️ FALLAS'} — {report['smoke']['summary'] or 'sin resumen'}",
        f"- **Tools rotas**: {', '.join(report['broken_tools']) or 'ninguna'}",
        f"- **Backup**: `{report['backup']}`",
        f"- **Capturas limpiadas**: {report['cleaned_captures']}",
        f"- **Manual**: {'sí' if report['manual'] else 'no'}",
    ]
    if report["smoke"]["failures"]:
        lines += ["", "Fallas detectadas:", *[f"  - {f}" for f in report["smoke"]["failures"]]]
    try:
        _REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


_MAINT_LOCK = threading.Lock()


def run_maintenance(force_running: bool = True) -> str:
    """Ejecuta el ciclo completo. `force_running` solo evita duplicados."""
    with _MAINT_LOCK:
        if not force_running:
            st = _state()
            if st.get("running"):
                return "⚠️ Ya hay un mantenimiento en curso."
        _save_state({"running": True, "started": datetime.now().isoformat(timespec="seconds")})

        report = {
            "date": date.today().isoformat(),
            "ts": time.time(),
            "manual": False,
            "smoke": {},
            "broken_tools": [],
            "backup": None,
            "cleaned_captures": 0,
        }
        _log("[Maintenance] Regresión de tools…")
        report["smoke"] = _run_smoke()
        _log(f"[Maintenance] Smoke: {'OK' if report['smoke']['ok'] else 'FALLAS'} "
             f"→ {report['smoke']['summary']}")

        report["broken_tools"] = _broken_tools()
        _log(f"[Maintenance] Tools rotas: {report['broken_tools'] or 'ninguna'}")

        report["backup"] = _zip_project() or "no se pudo crear"
        _log(f"[Maintenance] Backup: {report['backup']}")

        report["cleaned_captures"] = _clean_captures()
        _log(f"[Maintenance] Capturas limpiadas: {report['cleaned_captures']}")

        _write_report(report)
        _save_state({"last": report["date"], "ts": time.time(), "running": False,
                     "ok": report["smoke"]["ok"]})
        if report["smoke"]["ok"]:
            return "completado: regresión OK ✅"
        return "completado con fallas ⚠️ — revisá tu regresión"


def maybe_run_maintenance():
    """Programado: solo en la ventana nocturna y una vez por día. Corre en thread."""
    try:
        st = _state()
        if st.get("running") or st.get("last") == date.today().isoformat():
            return
        hour = datetime.now().hour
        if _HOUR_START <= hour < _HOUR_END:
            _log("[Maintenance] Ventana nocturna activa → corriendo mantenimiento.")
            threading.Thread(target=lambda: run_maintenance(True), daemon=True).start()
    except Exception as e:
        _log(f"[Maintenance] error de chequeo: {e}")


def _last_report() -> str:
    try:
        if _REPORT.exists():
            r = json.loads(_REPORT.read_text(encoding="utf-8"))
            return (f"Último mantenimiento: {r['date']} — regresión "
                    f"{'OK ✅' if r['smoke'].get('ok') else '⚠️ con fallas'} ({r['smoke'].get('summary', '')})"
                    f" | rotas: {', '.join(r['broken_tools']) or 'ninguna'}"
                    f" | backup: {r.get('backup')}")
    except Exception:
        pass
    return "Todavía no hay informe de mantenimiento nocturno."


def nightly_maintenance(parameters: dict, player=None) -> str:
    action = str(parameters.get("action", "report")).lower()
    if action in ("run", "correr", "ejecutar"):
        return "🧹 Mantenimiento " + run_maintenance(True) + "."
    if action in ("status", "estado"):
        st = _state()
        if st.get("running"):
            return "Mantenimiento en curso ahora mismo."
        if st.get("last"):
            return (f"Última corrida del mantenimiento: {st['last']} "
                    f"({'OK' if st.get('ok') else 'con fallas'}). "
                    f"Próxima: ventana 02:00–06:00.")
        return "Nunca corrí el mantenimiento. Pedime 'ejecutá el mantenimiento' o esperá la madrugada automática."
    return _last_report()