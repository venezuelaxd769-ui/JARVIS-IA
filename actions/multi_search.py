"""multi_search.py — Búsqueda web multi-provider.

Busca en múltiples motores simultáneamente: DuckDuckGo, Google (scraping),
Bing (scraping). Combina y deduplica resultados. Más completo que
web_search individual.
"""
import re
import urllib.request
import urllib.parse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def _search_ddg(query, limit=8):
    """Busca en DuckDuckGo via librería ddgs."""
    results = []
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=limit):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", r.get("link", "")),
                    "snippet": r.get("body", r.get("snippet", "")),
                    "source": "DuckDuckGo",
                })
    except Exception:
        pass
    return results


def _search_google(query, limit=8):
    """Busca en Google via scraping (sin API key)."""
    results = []
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&hl=es&num={limit}"
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Parsear resultados de Google
        # Patrón: <a href="/url?q=URL&..."><h3>TITLE</h3></a>...<span>SNIPPET</span>
        link_pattern = re.compile(
            r'<a[^>]+href="/url\?q=([^&"]+)[^"]*"[^>]*>.*?<h3[^>]*>(.*?)</h3>.*?</a>',
            re.DOTALL
        )
        snippet_pattern = re.compile(
            r'<span[^>]*class="[^"]*"[^>]*>(.*?)</span>',
            re.DOTALL
        )

        for match in link_pattern.finditer(html)[:limit]:
            raw_url = urllib.parse.unquote(match.group(1))
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if raw_url.startswith(("http://", "https://")):
                results.append({
                    "title": title,
                    "url": raw_url,
                    "snippet": "",
                    "source": "Google",
                })

        # Intentar extraer snippets
        snippets = snippet_pattern.findall(html)
        for i, s in enumerate(snippets[:len(results)]):
            clean = re.sub(r"<[^>]+>", "", s).strip()
            if clean and len(clean) > 20:
                results[i]["snippet"] = clean[:200]
    except Exception:
        pass
    return results


def _search_bing(query, limit=8):
    """Busca en Bing via scraping (sin API key)."""
    results = []
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={limit}"
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        # Parsear resultados de Bing
        pattern = re.compile(
            r'<li class="b_algo"[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?<p[^>]*>(.*?)</p>',
            re.DOTALL
        )
        for match in pattern.finditer(html)[:limit]:
            raw_url = match.group(1)
            title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            snippet = re.sub(r"<[^>]+>", "", match.group(3)).strip()
            if raw_url.startswith(("http://", "https://")):
                results.append({
                    "title": title,
                    "url": raw_url,
                    "snippet": snippet[:200],
                    "source": "Bing",
                })
    except Exception:
        pass
    return results


def _deduplicate(all_results):
    """Elimina duplicados por URL, priorizando mejor snippet."""
    seen = {}
    for r in all_results:
        url = r["url"].rstrip("/").lower()
        if url in seen:
            # Mantener el que tiene mejor snippet
            if len(r.get("snippet", "")) > len(seen[url].get("snippet", "")):
                seen[url] = r
        else:
            seen[url] = r
    return list(seen.values())


def multi_search(parameters: dict, player=None) -> str:
    """Busca en múltiples motores y combina resultados."""
    query = str(parameters.get("query", "")).strip()
    providers = str(parameters.get("providers", "all")).lower().strip()
    limit = int(parameters.get("limit", 8))
    dedupe = str(parameters.get("deduplicate", "true")).lower() != "false"

    if not query:
        return "Necesito una query para buscar."

    if player:
        player.write_log(f"🔍 Buscando '{query}' en múltiples motores...")

    # Determinar providers
    use_ddg = providers in ("all", "ddg", "duckduckgo")
    use_google = providers in ("all", "google")
    use_bing = providers in ("all", "bing")

    all_results = []

    # Búsqueda paralela
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}
        if use_ddg:
            futures[executor.submit(_search_ddg, query, limit)] = "DuckDuckGo"
        if use_google:
            futures[executor.submit(_search_google, query, limit)] = "Google"
        if use_bing:
            futures[executor.submit(_search_bing, query, limit)] = "Bing"

        for future in as_completed(futures, timeout=15):
            source = futures[future]
            try:
                results = future.result()
                all_results.extend(results)
            except Exception:
                pass

    if not all_results:
        return f"No se encontraron resultados para '{query}'."

    # Deduplicar
    if dedupe:
        all_results = _deduplicate(all_results)

    # Formatear salida
    lines = [f"🔍 {len(all_results)} resultados para '{query}':\n"]
    for i, r in enumerate(all_results[:limit * 2]):
        source_badge = {"DuckDuckGo": "🟢", "Google": "🔵", "Bing": "🟠"}.get(r["source"], "⚪")
        lines.append(f"{i+1}. {source_badge} {r['title']}")
        lines.append(f"   🔗 {r['url']}")
        if r.get("snippet"):
            lines.append(f"   {r['snippet'][:150]}")
        lines.append("")

    # Estadísticas
    sources_count = {}
    for r in all_results:
        s = r["source"]
        sources_count[s] = sources_count.get(s, 0) + 1
    stats = " | ".join(f"{k}: {v}" for k, v in sources_count.items())
    lines.append(f"📊 Fuentes: {stats}")

    return "\n".join(lines)


def search_all(parameters: dict, player=None) -> str:
    """Wrapper: búsqueda en todos los motores."""
    return multi_search({**parameters, "providers": "all"}, player=player)
