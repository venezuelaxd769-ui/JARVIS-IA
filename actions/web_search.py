from ddgs import DDGS

_LAST_RESULTS = []

def web_search(parameters: dict, player=None) -> str:
    global _LAST_RESULTS
    query = parameters.get("query", "")
    max_results = parameters.get("max_results", 8)

    if not query:
        return "Error: No se especificó la búsqueda (query)."

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=int(max_results)))
    except Exception as e:
        return f"Error al buscar: {e}"

    if not raw:
        return f"No se encontraron resultados para '{query}'."

    _LAST_RESULTS = []
    lines = [f"🔍 Resultados para: {query}", ""]

    for i, r in enumerate(raw, 1):
        title = r.get("title", "").strip()
        url = r.get("href", "").strip()
        snippet = r.get("body", "").strip()

        _LAST_RESULTS.append({"index": i, "title": title, "url": url, "snippet": snippet})

        lines.append(f"[{i}] {title}")
        lines.append(f"    {snippet[:120]}")
        lines.append(f"    {url}")
        lines.append("")

    lines.append(f"📌 Para abrir un resultado, decí: 'abrí el link X' o 'abrí el resultado X'")
    lines.append(f"📌 También podés pedir: 'abrí el primero', 'abrí el segundo', 'el tercero', etc.")

    result = "\n".join(lines)
    if player:
        player.write_log(f"🔍 {result[:200]}...")

    return result


def get_last_results() -> list[dict]:
    return _LAST_RESULTS
