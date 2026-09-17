# -*- coding: utf-8 -*-
"""descargar_yt.py — Descarga audio o video de YouTube por voz.

Usa yt-dlp (pip install yt-dlp) en un hilo daemon; cuando termina avisa por
voz con player.speak. Sin ffmpeg detectado descarga en formato nativo
(audio bestaudio m4a/webm; video best[ext=mp4]); con ffmpeg además puede
extraer mp3. Solo acepta URLs de youtube.com / youtu.be.
"""
import os
import shutil
import threading
import urllib.parse

_MUSICA = os.path.join(os.path.expanduser("~"), "Music", "NiaDescargas")
_VIDEO = os.path.join(os.path.expanduser("~"), "Downloads", "NiaDescargas")
_player = None
_ultimo = {}


def _host_valido(url):
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https"):
        return False
    host = (u.netloc or "").lower()
    host = host.split(":")[0].lstrip("www.")
    return host in ("youtube.com", "youtu.be")


def _tiene_ffmpeg():
    return shutil.which("ffmpeg") is not None


def _worker(url, tipo, carpeta):
    import yt_dlp
    global _ultimo
    try:
        if tipo == "video":
            formato = "best[ext=mp4]/best"
            destino = carpeta or _VIDEO
        else:
            formato = "bestaudio"
            destino = carpeta or _MUSICA
        os.makedirs(destino, exist_ok=True)
        opts = {
            "format": formato,
            "outtmpl": os.path.join(destino, "%(title)s.%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "retries": 2,
        }
        if tipo == "audio" and _tiene_ffmpeg():
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }]
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        titulo = info.get("title", "el video")
        encontrado = None
        if os.path.isdir(destino):
            archs = sorted(os.listdir(destino), key=lambda f: os.path.getmtime(os.path.join(destino, f)))
            if archs:
                encontrado = os.path.join(destino, archs[-1])
        _ultimo.update({"url": url, "ok": True, "titulo": titulo, "ruta": encontrado})
        if _player is not None:
            try:
                _player.speak(f"Listo, descargué {titulo} en {destino}.")
            except Exception:
                pass
    except Exception as e:
        _ultimo.update({"url": url, "ok": False, "error": str(e), "ruta": None})
        if _player is not None:
            try:
                _player.speak(f"No pude descargar eso, me dio: {str(e)[:120]}.")
            except Exception:
                pass


def descargar_yt(parameters: dict, player=None, speak=None) -> str:
    """Descarga audio o video de YouTube en background y avisa por voz."""
    global _player
    action = str(parameters.get("action", "descargar")).strip().lower()
    if player is not None:
        _player = player

    if action in ("test", "chequear"):
        try:
            import yt_dlp  # noqa: F401
            return "El descargador de YouTube funciona (yt-dlp " + __import__("yt_dlp").version.__version__ + ")."
        except Exception:
            return "Falta instalar yt-dlp (pip install yt-dlp)."

    if action in ("estado", "ultima"):
        if not _ultimo:
            return "Todavía no descargué nada en esta sesión."
        u = _ultimo
        if u.get("ok"):
            return f"La última descarga fue '{u['titulo']}' → {u['ruta'] or 'ok'}."
        return f"La última descarga falló: {u.get('error', '')[:160]}."

    if action not in ("descargar", "bajar", "audio"):
        return "Acciones: descargar (audio por default) | video | estado | test. Pasame el parámetro url."

    url = str(parameters.get("url", "") or parameters.get("link", "") or "").strip()
    if not url:
        return "Decime el link de YouTube a descargar, por ejemplo url='https://youtu.be/...'."
    if not _host_valido(url):
        return "Solo descargo links de YouTube (youtube.com o youtu.be)."

    tipo = str(parameters.get("tipo", "audio")).strip().lower()
    if action == "video":
        tipo = "video"
    if tipo not in ("audio", "video"):
        tipo = "audio"
    carpeta = str(parameters.get("carpeta", "")).strip() or None
    if carpeta:
        carpeta = os.path.expanduser(carpeta.strip('"'))

    threading.Thread(target=_worker, args=(url, tipo, carpeta), daemon=True).start()
    destino = carpeta or (_MUSICA if tipo == "audio" else _VIDEO)
    if player:
        player.write_log(f"📥 Descargando {tipo} desde {url} → {destino}")
    return (f"Arrancó la descarga del {tipo} de YouTube. Te aviso por voz cuando termine "
            f"(va a {destino}).")