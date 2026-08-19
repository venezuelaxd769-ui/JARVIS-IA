"""web_crawler.py — Crawling web en tiempo real.

A diferencia de web_fetch (una URL), este crawl emula Googlebot:
descubre links, sigue la estructura del sitio, extrae contenido
de múltiples páginas. Puede limitar profundidad, dominio, y max páginas.
"""
import re
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from collections import deque

_USER_AGENT = ("Mozilla/5.0 (compatible; NiaBot/1.0; "
               "+https://github.com/nia-bot)")
_MAX_PAGES = 20
_MAX_DEPTH = 3
_TIMEOUT = 15

_LINK_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.DOTALL)
_TEXT_EXTRACT = re.compile(
    r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<[^>]+>",
    re.DOTALL | re.IGNORECASE,
)
_MULTI_NL = re.compile(r"\n{3,}")


class _LinkExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.title = ""
        self._in_title = False
        self._skip = False
        self._text_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._in_title = True
        if tag in ("script", "style", "noscript"):
            self._skip = True
        if tag == "a":
            for attr, val in attrs:
                if attr == "href" and val:
                    self.links.append(val)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if not self._skip:
            self._text_parts.append(data)

    def get_text(self):
        text = " ".join(self._text_parts)
        text = re.sub(r"\s+", " ", text).strip()
        return text


def _normalize_url(url, base):
    """Normaliza URLs relativas y fragmentos."""
    url = url.split("#")[0].split("?")[0]
    if not url:
        return None
    if url.startswith(("mailto:", "tel:", "javascript:", "#")):
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        parsed = urllib.parse.urlparse(base)
        url = f"{parsed.scheme}://{parsed.netloc}{url}"
    elif not url.startswith("http"):
        base_parsed = urllib.parse.urlparse(base)
        url = f"{base_parsed.scheme}://{base_parsed.netloc}/{url}"
    # Quitar trailing slash para consistencia
    url = url.rstrip("/")
    return url


def web_crawler(parameters: dict, player=None) -> str:
    """Crawlea un sitio web: descubre links, extrae contenido de múltiples páginas."""
    start_url = str(parameters.get("url", "")).strip()
    max_pages = min(int(parameters.get("max_pages", _MAX_PAGES)), 50)
    max_depth = min(int(parameters.get("max_depth", _MAX_DEPTH)), 5)
    same_domain = str(parameters.get("same_domain", "true")).lower() != "false"
    max_chars = int(parameters.get("max_chars", 30000))

    if not start_url:
        return "Necesito una URL para crawlear."
    if not start_url.startswith(("http://", "https://")):
        start_url = "https://" + start_url

    if player:
        player.write_log(f"🕷️ Crawleando: {start_url}...")

    parsed_start = urllib.parse.urlparse(start_url)
    start_domain = parsed_start.netloc

    visited = set()
    queue = deque([(start_url, 0)])
    pages_data = []

    while queue and len(pages_data) < max_pages:
        url, depth = queue.popleft()
        normalized = _normalize_url(url, start_url)
        if not normalized or normalized in visited:
            continue
        if depth > max_depth:
            continue
        if same_domain:
            if urllib.parse.urlparse(normalized).netloc != start_domain:
                continue

        visited.add(normalized)

        try:
            req = urllib.request.Request(normalized, headers={
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,*/*",
            })
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "text" not in content_type and "html" not in content_type:
                    continue
                raw = resp.read(2_000_000)
                html = raw.decode("utf-8", errors="replace")
        except Exception:
            continue

        extractor = _LinkExtractor()
        try:
            extractor.feed(html)
        except Exception:
            continue

        text = re.sub(_TEXT_EXTRACT, " ", html)
        text = re.sub(r"\s+", " ", text).strip()

        pages_data.append({
            "url": normalized,
            "title": extractor.title.strip() or "(sin título)",
            "text": text[:5000],
            "depth": depth,
        })

        if player:
            player.write_log(f"  📄 [{len(pages_data)}/{max_pages}] {extractor.title.strip()[:50]}")

        for link in extractor.links:
            norm = _normalize_url(link, normalized)
            if norm and norm not in visited:
                queue.append((norm, depth + 1))

    if not pages_data:
        return f"No se pudo crawlear {start_url}."

    # Construir resultado
    total_chars = 0
    lines = [f"🕷️ Crawling de {start_url} — {len(pages_data)} páginas\n"]

    for i, page in enumerate(pages_data):
        chunk = f"\n📄 [{i+1}] {page['title']}\n   🔗 {page['url']}\n   {page['text'][:2000]}\n"
        if total_chars + len(chunk) > max_chars:
            lines.append(f"\n... (truncado, {len(pages_data) - i} páginas restantes)")
            break
        lines.append(chunk)
        total_chars += len(chunk)

    return "\n".join(lines)
