# -*- coding: utf-8 -*-
"""leer_pdf.py — Lectura de PDFs por voz.

Extrae texto de un PDF (pypdf) para que Nia lo resuma, lea páginas o
busque palabras dentro del documento.
"""
import os

_MAX_TEXT = 4200


def _cargar(ruta):
    from pypdf import PdfReader
    if not ruta:
        return None, "Decime la ruta del PDF (ruta). Ej: 'leéme el PDF del contrato'."
    try:
        reader = PdfReader(ruta)
    except Exception as e:
        return None, f"No pude abrir ese PDF: {e}"
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception:
            return None, "Ese PDF tiene contraseña y no pude abrirlo."
    return reader, None


def _paginas(reader, rango):
    try:
        if not rango:
            return list(range(len(reader.pages)))
        if isinstance(rango, int) or rango.isdigit():
            return [min(int(rango) - 1, len(reader.pages) - 1)]
        if "-" in rango:
            a, b = rango.split("-", 1)
            a = max(1, int(a.strip()));
            b = min(int(b.strip()), len(reader.pages))
            return list(range(a - 1, b))
    except Exception:
        pass
    return list(range(len(reader.pages)))


def _texto_pagina(reader, idx):
    try:
        txt = reader.pages[idx].extract_text() or ""
    except Exception:
        txt = ""
    return " ".join(txt.split())


def leer_pdf(parameters: dict, player=None, speak=None) -> str:
    """Leé y resumí PDFs: extrae texto, páginas o encuentra términos."""
    action = str(parameters.get("action", "resumen")).strip().lower()
    ruta = str(parameters.get("ruta", "")).strip()
    query = str(parameters.get("query", "")).strip()
    paginas = str(parameters.get("paginas", "") or parameters.get("pagina", "")).strip()
    if player:
        player.write_log(f"📄 leer_pdf: {action}")
    if ruta and not os.path.isabs(ruta):
        cand = os.path.join(os.path.expanduser("~"), ruta)
        if os.path.exists(cand):
            ruta = cand
    if ruta and not os.path.exists(ruta):
        from actions.buscar import _roots, _buscar as _f
        found, _ = _f(os.path.splitext(os.path.basename(ruta))[0], "",
                      _roots(""), 3)
        pdfs = [p for p, _ in found if p.lower().endswith(".pdf")]
        if pdfs:
            ruta = pdfs[0]
        else:
            return f"No encontré el archivo '{ruta}'."

    reader, err = _cargar(ruta)
    if err:
        return err
    total = len(reader.pages)

    if action in ("resumen", "resumir", "leer"):
        idxs = _paginas(reader, paginas)
        excerpt = []
        largo = 0
        salida = []
        for i in idxs:
            t = _texto_pagina(reader, i)
            if not t:
                continue
            salida.append(f"[Página {i + 1}] {t}")
            largo += len(t)
            if largo >= _MAX_TEXT:
                break
        texto = " ".join(salida)[: _MAX_TEXT].strip()
        if not texto:
            texto = "No pude extraer texto de esas páginas (¿PDF escaneado o con imágenes?)."
        from_page = idxs[0] + 1 if idxs else 1
        return (f"📄 {os.path.basename(ruta)} — {total} páginas. "
                f"Texto extraído (desde la página {from_page}, {len(texto)} caracteres):\n"
                f"{texto}\n(Para leer más, usá paginas='2-5' o '6'.)")

    if action in ("paginas", "pagina", "texto"):
        idxs = _paginas(reader, paginas or "1")
        bloques = []
        largo = 0
        for i in idxs:
            t = _texto_pagina(reader, i)
            if t:
                bloques.append(f"[Página {i + 1}]\n{t[: _MAX_TEXT - largo]}")
                largo += len(t)
            if largo >= _MAX_TEXT:
                break
        if not bloques:
            return "No pude extraer texto de esa página."
        return "\n\n".join(bloques)[: _MAX_TEXT]

    if action in ("buscar", "find", "encontrar"):
        if not query:
            return "Decime qué buscar dentro del PDF (query)."
        q = query.lower()
        hits = []
        for i in range(total):
            t = _texto_pagina(reader, i).lower()
            if q in t:
                hits.append(i + 1)
            if len(hits) >= 15:
                break
        if not hits:
            return f"No encontré '{query}' en el PDF."
        return f"🔍 '{query}' aparece en las páginas: {', '.join(map(str, hits))}."

    return "Acciones: resumen (ruta, paginas) | paginas (ruta, paginas) | buscar (ruta, query)."