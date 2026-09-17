"""episodic_memory.py — Memoria episódica con recibos (anti-alucinación, estilo Magi).

Cada recuerdo guarda su PROVENIENCIA (qué se dijo, cuándo, en qué sesión),
así Nia puede mostrar la fuente cuando le preguntás "¿de dónde lo sabés?".
Los recuerdos se pueden REVOCAR: quedan en una "lápida" (tombstone) para que
Nia no vuelva a aprender el mismo hecho equivocado.

Persistencia: memory/episodes.json  ·  tool: episodic_memory
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent
_STORE = _BASE / "memory" / "episodes.json"

_MAX_EPISODES = 300
_SYNC_MIN_IMPORTANCE = 3     # solo los importantes van al prompt de memoria
_STOPWORDS = {
    "de", "la", "el", "los", "las", "que", "y", "a", "en", "es", "por",
    "lo", "con", "para", "un", "una", "me", "te", "se", "mi", "tu", "su",
    "del", "al", "como", "cómo", "cuando", "porque", "muy", "más", "mas",
    "está", "estar", "sobre", "entre", "hacia", "pero", "o", "ni",
}


def _load() -> dict:
    try:
        if _STORE.exists():
            data = json.loads(_STORE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("episodes", {})
                data.setdefault("revoked", [])
                return data
    except Exception:
        pass
    return {"episodes": {}, "revoked": []}


def _save(data: dict):
    try:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        _STORE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _new_id(fact: str) -> str:
    h = hash(fact) % 100000
    return f"ep-{int(time.time())}-{h:05d}"


def _tokens(text: str) -> set[str]:
    words = re.split(r"[^a-záéíóúñü0-9]+", str(text).lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def save_episode(fact: str, category: str = "general", importance: int = 2,
                 quote: str = "", session: str = "", quien: str = "conversación") -> dict:
    """Guarda un recuerdo con su recibo (proveniencia)."""
    data = _load()
    fact = str(fact).strip()
    if not fact:
        return {"error": "El hecho no puede estar vacío."}

    revoked_hit = ""
    for r in data.get("revoked", []):
        if _tokens(r.get("fact", "")) & _tokens(fact):
            revoked_hit = r.get("fact")
            break

    now = datetime.now()
    record = {
        "id": _new_id(fact),
        "fact": fact[:500],
        "category": str(category or "general").strip()[:40],
        "importance": max(1, min(5, int(importance or 2))),
        "ts": time.time(),
        "cuando": now.strftime("%Y-%m-%d %H:%M"),
        "receipt": {
            "quien": str(quien or "conversación")[:60],
            "session": str(session or "desconocida")[:60],
            "quote": str(quote or "")[:800],
        },
    }
    data["episodes"][record["id"]] = record
    eps = data["episodes"]
    if len(eps) > _MAX_EPISODES:
        for mid in sorted(eps, key=lambda i: eps[i]["ts"])[: len(eps) - _MAX_EPISODES]:
            del eps[mid]
    _save(data)

    # Sincronizar los importantes al prompt de memoria de largo plazo.
    if record["importance"] >= _SYNC_MIN_IMPORTANCE:
        try:
            from memory.memory_manager import remember
            remember("episodes", record["id"],
                     f"{record['fact']} (fuente: {record['cuando']})")
        except Exception:
            pass

    if revoked_hit:
        record["revoked_note"] = f"Ojo: antes revocaste algo parecido («{revoked_hit}»)."
    return record


def recall(query: str, category: str = "", limit: int = 3) -> list[dict]:
    """Costos por solapamiento de tokens contra hecho + recibo."""
    data = _load()
    qset = _tokens(query) or _tokens("recuerdo")
    scored = []
    for ep in data["episodes"].values():
        if category and str(ep.get("category", "")).lower() != str(category).lower():
            continue
        corpus = f"{ep['fact']} {ep['receipt'].get('quote', '')}"
        tokens = _tokens(corpus)
        scored.append((len(qset & tokens), -ep["ts"], ep))
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [ep for score, _, ep in scored[:limit] if score > 0]


def revoke(ep_id: str) -> str:
    data = _load()
    ep = data["episodes"].pop(ep_id, None)
    if not ep:
        return f"No encontré ningún recuerdo con id '{ep_id}'."
    data["revoked"].append({"id": ep_id, "fact": ep["fact"], "ts": time.time()})
    data["revoked"] = data["revoked"][-100:]
    _save(data)
    try:
        from memory.memory_manager import forget
        forget("episodes", ep_id)
    except Exception:
        pass
    return (f"✂️ Recuerdo revocado: «{ep['fact']}». "
            f"Va a la lápida: no lo vuelvo a aprender.")


def list_all(category: str = "") -> list[dict]:
    data = _load()
    eps = list(data["episodes"].values())
    if category:
        eps = [e for e in eps if str(e.get("category", "")).lower() == str(category).lower()]
    eps.sort(key=lambda e: e.get("ts", 0), reverse=True)
    return eps[:50]


def _fmt(ep: dict) -> str:
    recibo = ep.get("receipt", {})
    src = recibo.get("quote", "") or "sin cita registrada"
    lines = [f"• [{ep.get('importance', 2)}★|{ep.get('category', 'general')}] "
             f"{ep.get('fact')}",
             f"  └ fuente: {ep.get('cuando')} ({recibo.get('quien', '')}): «{src[:180]}»",
             f"    id: {ep.get('id')}"]
    if ep.get("revoked_note"):
        lines.append(f"    ⚠️ {ep['revoked_note']}")
    return "\n".join(lines)


def episodic_memory(parameters: dict, player=None) -> str:
    action = str(parameters.get("action", "list")).lower()

    if action in ("save", "recordar", "guardar"):
        ep = save_episode(
            fact=parameters.get("fact", ""),
            category=parameters.get("category", "general"),
            importance=parameters.get("importance", 2),
            quote=parameters.get("quote", ""),
            session=parameters.get("session", ""),
            quien=parameters.get("quien", "conversación"),
        )
        if ep.get("error"):
            return f"⛔ {ep['error']}"
        return (f"🧠 Guardado como episodio: «{ep['fact']}»\n"
                f"  Recibo: {ep['cuando']} · {ep['receipt']['quien']} · id {ep['id']}"
                + ("\n  ⚠️ " + ep["revoked_note"] if ep.get("revoked_note") else ""))

    if action in ("revoke", "revocar", "olvidar"):
        return revoke(str(parameters.get("id", "")).strip())

    if action in ("list", "ver"):
        eps = list_all(parameters.get("category", ""))
        if not eps:
            return "Todavía no guardé episodios." 
        return f"📚 {len(eps)} episodio(s):\n" + "\n".join(_fmt(e) for e in eps)

    if action in ("source", "fuente"):
        q = parameters.get("query", "")
        hits = recall(q, parameters.get("category", ""), limit=1)
        if not hits:
            return f"No encontré esa memoria para mostrar su fuente."
        return "Fuente (recibo):\n" + _fmt(hits[0])

    hits = recall(str(parameters.get("query", "")),
                  parameters.get("category", ""),
                  parameters.get("limit", 3) or 3)
    if not hits:
        return f"No recuerdo nada comparable a «{parameters.get('query', '')}»."
    return "🧠 Encontré en memoria:\n" + "\n".join(_fmt(e) for e in hits)