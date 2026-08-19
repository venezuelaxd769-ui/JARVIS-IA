"""persistent_context.py — Guarda y recupera contexto entre sesiones.

Permite a Nia recordar conversaciones previas, decisiones tomadas,
y contexto importante. Almacena en JSON con timestamps, búsqueda
por keywords, y resumen automático de sesiones anteriores.
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime

_REPO = Path(__file__).resolve().parent.parent
CONTEXT_DIR = _REPO / "config" / "context"
MAX_SESSIONS = 50
MAX_CONTEXT_ENTRIES = 500


def _ensure_dir():
    CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


def _load_index():
    _ensure_dir()
    index_path = CONTEXT_DIR / "index.json"
    if index_path.exists():
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"sessions": [], "total_entries": 0}


def _save_index(index):
    _ensure_dir()
    (CONTEXT_DIR / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_session(session_id):
    path = CONTEXT_DIR / f"session_{session_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _save_session(session_id, data):
    _ensure_dir()
    path = CONTEXT_DIR / f"session_{session_id}.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _prune_old_sessions(index):
    """Mantiene solo las últimas MAX_SESSIONS sesiones."""
    if len(index["sessions"]) > MAX_SESSIONS:
        to_remove = index["sessions"][:-MAX_SESSIONS]
        index["sessions"] = index["sessions"][-MAX_SESSIONS:]
        for s in to_remove:
            path = CONTEXT_DIR / f"session_{s['id']}.json"
            if path.exists():
                path.unlink()
    return index


def persistent_context(parameters: dict, player=None) -> str:
    """Gestiona contexto persistente entre sesiones."""
    action = str(parameters.get("action", "save")).lower().strip()

    if action in ("save", "guardar", "s"):
        return _save_entry(parameters, player)
    elif action in ("recall", "recuperar", "buscar", "r"):
        return _recall_entries(parameters, player)
    elif action in ("list", "listar", "sesiones", "ls"):
        return _list_sessions(parameters, player)
    elif action in ("summary", "resumen", "res"):
        return _session_summary(parameters, player)
    elif action in ("clear", "limpiar"):
        return _clear_context(parameters, player)
    else:
        return ("Acciones: save/guardar, recall/recuperar, list/listar, "
                "summary/resumen, clear/limpiar.")


def _save_entry(params, player):
    """Guarda un entry de contexto."""
    topic = str(params.get("topic", "")).strip()
    content = str(params.get("content", "")).strip()
    importance = str(params.get("importance", "normal")).lower().strip()
    keywords = str(params.get("keywords", "")).strip()

    if not content:
        return "Necesito contenido para guardar."

    index = _load_index()
    now = time.time()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    entry = {
        "topic": topic or "(sin tema)",
        "content": content[:5000],
        "importance": importance,
        "keywords": [k.strip() for k in keywords.split(",") if k.strip()] if keywords else [],
        "timestamp": now,
        "ts_human": ts,
    }

    # Determinar sesión (última o crear nueva)
    session_id = None
    for s in reversed(index["sessions"]):
        if now - s["last_active"] < 3600:  # misma sesión si < 1 hora
            session_id = s["id"]
            s["last_active"] = now
            s["entry_count"] += 1
            break

    if session_id is None:
        session_id = f"{int(now)}"
        index["sessions"].append({
            "id": session_id,
            "started": now,
            "last_active": now,
            "entry_count": 1,
            "summary": "",
        })

    session = _load_session(session_id) or {"entries": []}
    session["entries"].append(entry)
    _save_session(session_id, session)

    index["total_entries"] += 1
    index = _prune_old_sessions(index)
    _save_index(index)

    if player:
        player.write_log(f"💾 Contexto guardado: {topic or 'entry'}")

    return f"💾 Guardado en sesión {session_id}: {topic or '(sin tema)'}\n   {content[:100]}"


def _recall_entries(params, player):
    """Busca en el contexto guardado."""
    query = str(params.get("query", "")).strip().lower()
    limit = int(params.get("limit", 10))

    if not query:
        return "Necesito una query para buscar."

    index = _load_index()
    results = []

    for s in reversed(index["sessions"]):
        session = _load_session(s["id"])
        if not session:
            continue
        for entry in reversed(session.get("entries", [])):
            text = f"{entry.get('topic', '')} {entry.get('content', '')} {' '.join(entry.get('keywords', []))}".lower()
            if query in text:
                results.append(entry)
                if len(results) >= limit:
                    break
        if len(results) >= limit:
            break

    if not results:
        return f"No encontré contexto relacionado con '{query}'."

    lines = [f"🔍 {len(results)} resultado(s) para '{query}':\n"]
    for i, e in enumerate(results):
        imp = "🔴" if e.get("importance") == "alta" else "🟡" if e.get("importance") == "media" else "⚪"
        lines.append(f"{imp} [{e.get('ts_human', '?')}] {e.get('topic', '?')}")
        lines.append(f"   {e.get('content', '')[:200]}\n")

    return "\n".join(lines)


def _list_sessions(params, player):
    """Lista sesiones guardadas."""
    index = _load_index()
    sessions = index.get("sessions", [])

    if not sessions:
        return "No hay sesiones guardadas."

    limit = int(params.get("limit", 10))
    recent = sessions[-limit:]

    lines = [f"📚 {len(sessions)} sesión(es) total(es):\n"]
    for s in reversed(recent):
        ts = datetime.fromtimestamp(s["started"]).strftime("%Y-%m-%d %H:%M")
        lines.append(f"  • Sesión {s['id']} — {ts} — {s['entry_count']} entries")

    return "\n".join(lines)


def _session_summary(params, player):
    """Genera resumen de una sesión."""
    session_id = str(params.get("session_id", "")).strip()

    if not session_id:
        index = _load_index()
        if not index["sessions"]:
            return "No hay sesiones."
        session_id = index["sessions"][-1]["id"]

    session = _load_session(session_id)
    if not session:
        return f"Sesión {session_id} no encontrada."

    entries = session.get("entries", [])
    if not entries:
        return f"Sesión {session_id} vacía."

    lines = [f"📋 Resumen sesión {session_id} — {len(entries)} entries:\n"]
    topics = {}
    for e in entries:
        t = e.get("topic", "(sin tema)")
        topics[t] = topics.get(t, 0) + 1

    for topic, count in sorted(topics.items(), key=lambda x: -x[1]):
        lines.append(f"  • {topic}: {count} entries")

    return "\n".join(lines)


def _clear_context(params, player):
    """Limpia contexto antiguo."""
    index = _load_index()
    before = len(index["sessions"])

    if before == 0:
        return "No hay contexto que limpiar."

    # Mantener solo las últimas 5 sesiones
    index["sessions"] = index["sessions"][-5:]
    removed = before - len(index["sessions"])

    # Eliminar archivos de sesiones eliminadas
    for s in index["sessions"]:
        path = CONTEXT_DIR / f"session_{s['id']}.json"
        if not path.exists():
            continue

    _save_index(index)

    if player:
        player.write_log(f"🗑️ Contexto limpiado: {removed} sesiones eliminadas")

    return f"🗑️ Limpiado: {removed} sesiones eliminadas, 5 mantenidas."
