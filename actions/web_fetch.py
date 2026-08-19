"""web_fetch.py — Trae y parsea contenido de cualquier URL.

Soporta: páginas web (HTML→texto limpio), APIs JSON, imágenes (base64),
archivos de texto plano. Timeout configurable. User-Agent realista.
"""
import json
import re
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser

_USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_TEXT_EXTRACT = re.compile(
    r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>|<[^>]+>",
    re.DOTALL | re.IGNORECASE,
)
_MULTI_NL = re.compile(r"\n{3,}")
_SPACES = re.compile(r"[ \t]+")
_IMG_EXT = re.compile(r"\.(png|jpe?g|gif|webp|bmp|svg|ico)(\?.*)?$", re.I)


class _HTMLStripper(HTMLParser):
    """Extrae texto plano de HTML."""

    def __init__(self):
        super().__init__()
        self._parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._parts.append(data)

    def get_text(self):
        text = " ".join(self._parts)
        text = _SPACES.sub(" ", text).strip()
        return text


def _html_to_text(html: str) -> str:
    s = _HTMLStripper()
    s.feed(html)
    text = s.get_text()
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def web_fetch(parameters: dict, player=None) -> str:
    """Trae contenido de una URL. Devuelve texto limpio, JSON o base64."""
    url = str(parameters.get("url", "")).strip()
    max_chars = int(parameters.get("max_chars", 15000))
    force_text = str(parameters.get("force_text", "")).lower() == "true"

    if not url:
        return "Necesito una URL para buscar."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    if player:
        player.write_log(f"🌐 Buscando: {url[:80]}...")

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _USER_AGENT,
            "Accept": ("text/html,application/xhtml+xml,application/xml;"
                       "q=0.9,*/*;q=0.8"),
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(5_000_000)  # 5 MB max

    except urllib.error.HTTPError as e:
        return f"Error HTTP {e.code}: {e.reason} — {url}"
    except urllib.error.URLError as e:
        return f"Error de conexión: {e.reason} — {url}"
    except Exception as e:
        return f"Error al acceder a la URL: {e}"

    # JSON
    if "json" in content_type or force_text:
        try:
            data = json.loads(raw)
            text = json.dumps(data, ensure_ascii=False, indent=2)
            if len(text) > max_chars:
                text = text[:max_chars] + f"\n\n... (truncado, total {len(text)} chars)"
            return f"📋 JSON de {url}:\n{text}"
        except Exception:
            pass

    # Imagen
    if _IMG_EXT.search(url) or "image" in content_type:
        import base64
        b64 = base64.b64encode(raw).decode()
        ext = "png"
        m = _IMG_EXT.search(url)
        if m:
            ext = m.group(1).lower()
            if ext == "jpg":
                ext = "jpeg"
        return (f"🖼️ Imagen descargada: {url}\n"
                f"Tipo: {content_type}\n"
                f"Tamaño: {len(raw):,} bytes\n"
                f"Formato: {ext}\n"
                f"Base64 (primeros 100 chars): {b64[:100]}...")

    # HTML → texto
    try:
        html = raw.decode("utf-8", errors="replace")
    except Exception:
        html = raw.decode("latin-1", errors="replace")

    text = _html_to_text(html)

    # Título
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    if len(text) > max_chars:
        text = text[:max_chars] + f"\n\n... (truncado, total {len(text)} chars)"

    header = f"🌐 {title}\n🔗 {url}" if title else f"🌐 {url}"
    return f"{header}\n\n{text}"
