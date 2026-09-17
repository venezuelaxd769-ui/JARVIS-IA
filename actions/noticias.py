# -*- coding: utf-8 -*-
"""noticias.py — Titulares de noticias por voz (RSS, sin APIs ni cuentas).

Nia puede contar titulares de la Argentina, del mundo o de tecnología y
leer el detalle de una nota que elijas. Usa RSS públicos: sin costos,
sin keys, con timeouts y caché de 5 minutos.
"""
import html
import re
import time
import urllib.request

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124 Safari/537.36")
_TIMEOUT = 8

_FEEDS = {
    "portada": [
        ("La Nación", "https://www.lanacion.com.ar/arc/outboundfeeds/rss/?outputType=xml"),
        ("Clarín", "https://www.clarin.com/rss/"),
    ],
    "argentina": [
        ("Perfil", "https://www.perfil.com/feed/"),
        ("TN", "https://tn.com.ar/feed/"),
    ],
    "tech": [
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
    ],
    "mundo": [
        ("BBC Mundo", "https://feeds.bbci.co.uk/mundo/rss.xml"),
        ("El País", "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"),
    ],
}

_BACKUP_FEED = "https://news.google.com/rss?hl=es-419&gl=AR&ceid=AR:es-419"

_CACHE = {}


def _fetch(url, tries=3):
    now = time.monotonic()
    got = _CACHE.get(url)
    if got and now - got[0] < 300:
        return got[1]
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": _UA, "Accept-Encoding": "identity"},
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
                data = r.read(2 * 1024 * 1024).decode("utf-8", "replace")
            _CACHE[url] = (now, data)
            return data
        except Exception:
            if attempt < tries - 1:
                time.sleep(1.0 + attempt)
    return None


def _clean(text):
    if not text:
        return ""
    text = html.unescape(text)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def _parse_items(xml_data):
    items = []
    for block in re.finditer(r"<item\b.*?</item>", xml_data, re.S | re.I):
        m = _extract_block(block.group(0), options=("title", "link", "description"))
        if m and m.get("title"):
            items.append(m)
    if items:
        return items
    for block in re.finditer(r"<entry\b.*?</entry>", xml_data, re.S | re.I):
        m = _extract_block(block.group(0), kind="atom")
        if m and m.get("title"):
            items.append(m)
    return items


def _extract_block(block, kind="rss", options=("title", "link", "description")):
    if kind == "atom":
        m = re.search(r"<title[^>]*>(.*?)</title>", block, re.S | re.I)
        title = _clean(m.group(1)) if m else ""
        link = re.search(r'<link[^>]*\bhref="([^"]*)"', block, re.S | re.I)
        return {"title": title, "link": link.group(1) if link else "", "desc": ""}
    out = {}
    for opt in options:
        m = re.search(rf"<{opt}[^>]*>(.*?)</{opt}>", block, re.S | re.I)
        out[opt] = _clean(m.group(1)) if m else ""
    if not out.get("link", "").startswith("http"):
        m = re.search(r'<link[^>]*\bhref="([^"]*)"', block, re.S | re.I)
        if m:
            out["link"] = m.group(1)
    return out


def _portada(cat, top=6):
    lineas = []
    con_titulares = 0
    for source, url in _fuentes(cat):
        data = _fetch(url)
        if not data:
            lineas.append(f"• {source}: no pude conectarme, probá más tarde.")
            continue
        items = _parse_items(data)[:top]
        if not items:
            lineas.append(f"• {source}: sin titulares por ahora.")
            continue
        con_titulares += len(items)
        lineas.append(f"📰 {source}:")
        for it in items:
            lineas.append(f"   • {it['title'][:150]}")
    if con_titulares == 0:
        return "No pude obtener noticias en este momento."
    return "\n".join(lineas)


def _fuentes(cat):
    fuentes = list(_FEEDS.get(cat, _FEEDS["portada"]))
    fuentes.append(("Google Noticias", _BACKUP_FEED))
    return fuentes


def _leer(params):
    cat = str(params.get("categoria", "")).strip().lower()
    idx = params.get("indice")
    try:
        n = int(idx)
    except (TypeError, ValueError):
        return "Decime el número de la noticia (ej: action='leer', indice=3)."
    top = 8
    for source, url in _fuentes(cat):
        data = _fetch(url)
        if not data:
            continue
        items = _parse_items(data)[:top]
        if 1 <= n <= len(items):
            it = items[n - 1]
            desc = it.get("desc") or ""
            if len(desc) > 500:
                desc = desc[:500] + "…"
            return f"{it['title']}\n{desc}\nFuente: {source}\n{it.get('link', '')}"
        n -= len(items)
    return "No encontré esa noticia en los titulares."


def noticias(parameters: dict, player=None, speak=None) -> str:
    """Titulares de noticias por voz: arrancá el día (portada), tecnología
    (tech), Argentina (argentina), mundo (mundo) o leé la nota (leer)."""
    action = str(parameters.get("action", "portada")).strip().lower()
    if player:
        player.write_log(f"📰 noticias: {action}")
    if action in ("leer", "nota", "detail"):
        return _leer(parameters)
    cat = action if action in _FEEDS else "portada"
    return _portada(cat)