"""knowledge_base.py — Segundo cerebro: búsqueda y acceso a la bóveda de Obsidian.

Busca en tus notas por similitud semántica (si el modelo de embeddings está
disponible), con ranking TF-IDF local como respaldo siempre funcional y
búsqueda por palabras como última opción. Nunca depende de red.
"""
import json
import math
import re
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
INDEX_PATH = BASE_DIR / "memory" / "obsidian_index.json"
FASTEMBED_CACHE = Path.home() / ".cache" / "fastembed"

STOPWORDS = {
    "a", "al", "ante", "aquí", "así", "bajo", "bien", "como", "con", "contra",
    "cuando", "de", "del", "desde", "donde", "e", "el", "en", "entre", "era",
    "es", "esta", "este", "esto", "fue", "ha", "hay", "hasta", "la", "las",
    "lo", "los", "mas", "más", "me", "mi", "muy", "nada", "no", "nos", "o",
    "para", "pero", "por", "porque", "qué", "que", "se", "si", "sin", "sobre",
    "son", "su", "sus", "te", "the", "and", "to", "of", "a", "in", "for",
    "on", "with", "this", "that", "is", "it", "you", "not", "be", "are",
    "was", "from", "have", "has", "do", "does", "your", "my", "as", "at",
}

_emb_ok = None
_emb_lock = threading.Lock()


def _tokens(text):
    return [w for w in re.findall(r"[a-záéíóúüñ0-9]+", (text or "").lower())
            if w not in STOPWORDS and len(w) > 1]


def _embeddings_available():
    """¿Hay modelo de embeddings cacheado en disco? Chequeo instantáneo, sin red."""
    global _emb_ok
    with _emb_lock:
        if _emb_ok is not None:
            return _emb_ok
        ok = False
        if FASTEMBED_CACHE.exists():
            for p in FASTEMBED_CACHE.rglob("*.onnx"):
                ok = True
                break
        _emb_ok = ok
        return ok


def _load_index():
    try:
        if not INDEX_PATH.exists():
            return None
        with open(INDEX_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _tfidf_search(query, top_k):
    q_tokens = _tokens(query)
    if not q_tokens:
        return []
    index = _load_index()
    if not index:
        return []
    notes = index.get("notes", {})
    docs = []
    for path, meta in notes.items():
        for chunk in meta.get("chunks", []):
            toks = _tokens(chunk.get("text", ""))
            if toks:
                docs.append((path, chunk, toks))
    if not docs:
        return []
    n_docs = float(len(docs))
    doc_count = {}
    for _, _, toks in docs:
        for t in set(toks):
            doc_count[t] = doc_count.get(t, 0) + 1
    scored = []
    for path, chunk, toks in docs:
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        score = 0.0
        for t in set(q_tokens):
            if t in tf:
                score += (1.0 + math.log(tf[t])) * math.log(
                    n_docs / (doc_count.get(t, 0) + 0.5))
        if score > 0:
            boost = 1.0
            path_toks = _tokens(path.replace("_", " ").replace("-", " "))
            if any(t in path_toks for t in q_tokens):
                boost = 2.5
            scored.append((boost * score / (len(toks) ** 0.5), path, chunk))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def _semantic_search(query, top_k):
    try:
        from actions.obsidian_bridge import semantic_search
        r = semantic_search(query=query, top_k=top_k)
        if isinstance(r, dict):
            results = r.get("results") or r.get("notes") or []
            out = []
            for item in results:
                if isinstance(item, dict):
                    out.append((item.get("path") or item.get("note") or "",
                                item.get("snippet") or item.get("text") or "",
                                float(item.get("similarity") or item.get("score") or 0.0)))
                elif isinstance(item, (list, tuple)) and item:
                    out.append((str(item[0]), str(item[1]) if len(item) > 1 else "", 0.0))
            return out
    except Exception:
        pass
    return []


def _snippet(text, query, width=220):
    text = re.sub(r"[#*_`>\[\]]+", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    q = _tokens(query)
    idx = -1
    for t in q:
        found = text.lower().find(t)
        if found >= 0:
            idx = found
            break
    if idx < 0:
        idx = 0
    start = max(0, idx - width // 2)
    snippet = text[start:start + width].strip()
    if start > 0:
        snippet = "…" + snippet
    if start + width < len(text):
        snippet = snippet + "…"
    return snippet


def _format_search(results, query, source):
    if not results:
        return f"No encontré nada sobre '{query}' en tu bóveda."
    lines = [f"Encontré {len(results)} resultado(s) en tu base de conocimiento "
             f"({source}):"]
    for i, item in enumerate(results, 1):
        path = item.get("path", "") or item.get("note", "")
        title = Path(path).stem if path else "?"
        text = item.get("text") or item.get("snippet") or ""
        score = item.get("score")
        lines.append(f"{i}. {title} — {path}")
        if score is not None:
            lines.append(f"   (afinidad {score:.2f})")
        snippet = _snippet(text, query)
        if snippet:
            lines.append(f"   {snippet[:180]}")
    return "\n".join(lines)


def knowledge_base(parameters: dict, player=None) -> str:
    """Busca, lee, lista o agrega conocimiento a la bóveda de Obsidian."""
    action = str(parameters.get("action", "search")).lower().strip()
    query = str(parameters.get("query", "")).strip()
    top_k = max(1, min(int(parameters.get("top_k", 5) or 5), 10))

    if action in ("search", "find", "query", "buscar"):
        if not query:
            return "Decime qué querés buscar en tu base de conocimiento."
        if player:
            player.write_log(f"🧠 Buscando en tu base de conocimiento: {query}")

        if _embeddings_available():
            sem = _semantic_search(query, top_k)
            if sem:
                results = []
                for path, text, score in sem:
                    results.append({"path": path, "text": text, "score": score})
                return _format_search(results, query, "búsqueda semántica")
            return _format_search([], query, "semántica")

        tfidf = _tfidf_search(query, top_k)
        if tfidf:
            results = [{"path": p, "text": c.get("text", ""), "score": None}
                       for _, p, c in tfidf]
            return _format_search(results, query, "relevancia local")
        return _format_search([], query, "relevancia local")

    elif action in ("stats", "info", "status", "estado"):
        try:
            from actions.obsidian_bridge import get_stats
            st = get_stats()
        except Exception:
            return "No pude consultar las estadísticas de tu bóveda."
        return (f"Tu base de conocimiento tiene {st.get('note_count', 0)} notas "
                f"({st.get('total_chars', 0):,} caracteres), "
                f"{st.get('total_links', 0)} enlaces y {st.get('total_tags', 0)} "
                f"etiquetas en {st.get('vault_path', '')}.")

    elif action in ("list", "ls", "ver"):
        try:
            from actions.obsidian_bridge import list_notes
            folder = str(parameters.get("path", "") or parameters.get("entry_id", "")).strip()
            r = list_notes(folder)
        except Exception as e:
            return f"No pude listar las notas: {e}"
        notes = r.get("notes", [])
        if not notes:
            return "No encontré notas ahí."
        lines = [f"Notas en {r.get('path', folder) or 'raíz'} "
                 f"({r.get('note_count', len(notes))}):"]
        for n in notes[:20]:
            lines.append(f"• {n.get('title', n.get('path', '?'))}")
        if len(notes) > 20:
            lines.append(f"... y {len(notes) - 20} más.")
        return "\n".join(lines)

    elif action in ("read", "get", "view", "abrir"):
        path = str(parameters.get("path", "") or parameters.get("entry_id", "")).strip()
        if not path:
            return "Necesito la ruta de la nota (por ej: 'Diario/2026-08-01.md')."
        try:
            from actions.obsidian_bridge import read_note
            note = read_note(path)
        except Exception as e:
            return f"No pude leer la nota: {e}"
        if not note or not note.get("content"):
            return f"No encontré la nota '{path}'."
        content = note["content"]
        max_chars = int(parameters.get("max_chars", 1500) or 1500)
        shown = content[:max_chars]
        out = [f"📄 {note.get('title', path)} ({note.get('char_count', len(content))} caracteres):"]
        out.append(shown)
        if len(content) > max_chars:
            out.append(f"\n... (nota truncada; tiene {len(content)} caracteres)")
        return "\n".join(out)

    elif action in ("add", "save", "store", "write", "guardar"):
        title = str(parameters.get("title", "")).strip()
        content = str(parameters.get("content", "")).strip()
        if not title or not content:
            return "Necesito un 'title' y un 'content' para guardar la nota."
        try:
            from actions.obsidian_bridge import write_note
            folder = str(parameters.get("path", "")).strip().strip("/")
            path = f"{folder}/{title}.md" if folder else f"{title}.md"
            r = write_note(path, content)
            ok = isinstance(r, dict) and (r.get("ok") or r.get("path"))
            if ok or (isinstance(r, dict) and "error" not in r):
                return f"Guardé la nota '{path}' en tu base de conocimiento."
            return f"No pude guardar la nota: {r}"
        except Exception as e:
            return f"No pude guardar la nota: {e}"

    else:
        return ("Acción desconocida. Usá: search/find, stats, list, read/get, "
                "o add/save con title y content.")
