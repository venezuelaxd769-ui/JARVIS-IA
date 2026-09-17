# -*- coding: utf-8 -*-
"""traductor.py — Traduce frases por voz y las pronuncia.

Traducción con el endpoint gratuito de Google Translate (client=gtx, sin
claves) y respaldo en MyMemory. La pronunciación usa las voces de Windows
(System.Speech) en un proceso aparte, sin bloquear la respuesta.
"""
import json
import os
import subprocess
import urllib.parse
import urllib.request

_IDIOMAS = {
    # nombre/dialecto -> código Google
    "ingles": "en",
    "inglés": "en",
    "ingles de estados unidos": "en",
    "ingles de españa": "en",
    "español": "es",
    "español de argentina": "es",
    "espanol": "es",
    "espanol de argentina": "es",
    "castellano": "es",
    "frances": "fr",
    "francés": "fr",
    "italiano": "it",
    "portugues": "pt",
    "portugués": "pt",
    "aleman": "de",
    "alemán": "de",
    "japones": "ja",
    "japonés": "ja",
    "chino": "zh-CN",
    "chino mandarin": "zh-CN",
    "coreano": "ko",
    "ruso": "ru",
    "arabe": "ar",
    "árabe": "ar",
    "griego": "el",
    "turco": "tr",
    "latin": "la",
    "latín": "la",
    "hebreo": "he",
    "hindi": "hi",
}

# voces instaladas típicas de Windows 11 por idioma (para elegir cultura)
_VOZ_CULTURA = {
    "en": "en-US", "es": "es-ES", "fr": "fr-FR", "it": "it-IT", "de": "de-DE",
    "pt": "pt-BR", "zh-CN": "zh-CN", "ja": "ja-JP", "ko": "ko-KR", "ru": "ru-RU",
    "ar": "ar-SA", "el": "el-GR", "tr": "tr-TR", "hi": "hi-IN",
}


def _google(texto, origen, destino):
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
           f"&sl={origen}&tl={destino}&dt=t&q={urllib.parse.quote(texto)}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    partes = [p[0] for p in data[0] if p and p[0]]
    return "".join(partes)


def _mymemory(texto, origen, destino):
    url = ("https://api.mymemory.translated.net/get"
           f"?q={urllib.parse.quote(texto)}&langpair={origen}|{destino}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    res = data.get("responseData", {}).get("translatedText", "")
    return res if res and res != texto else None


def _clave(idiota):
    if not idiota:
        return None
    idiota = str(idiota).strip().lower()
    if idiota in ("auto", "automático", "automatico", "detectar"):
        return "auto"
    return _IDIOMAS.get(idiota, idiota)  # si ya es código, se usa directo


_NOMBRES = {}
for _k, _v in _IDIOMAS.items():
    if " " not in _k and _v not in _NOMBRES:
        _NOMBRES[_v] = _k.title()


def _nombre(codigo):
    if codigo in ("auto", "en", "es", "fr", "it", "de", "pt", "zh-CN", "ja",
                  "ko", "ru", "ar", "el", "tr", "hi", "he", "la"):
        return _NOMBRES.get(codigo, codigo)
    return codigo


def _autodetect(texto):
    try:
        url = ("https://translate.googleapis.com/translate_a/single?client=gtx"
               f"&sl=auto&tl=en&dt=t&q={urllib.parse.quote(texto[:400])}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data[2] or "es"
    except Exception:
        return "es"


def _pronunciar(texto, destino):
    """Habla el texto con una voz de Windows del idioma destino (SAPI)."""
    cultura = _VOZ_CULTURA.get(destino, "")
    patron = repr(cultura + "*")
    frase = repr(texto.replace("'", ""))
    ps = "".join([
        "$ErrorActionPreference='SilentlyContinue';",
        "Add-Type -AssemblyName System.Speech;",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;",
        "$s.Rate = -1;",
        "$sel = $null;",
        "foreach ($v in $s.GetInstalledVoices()) {",
        "   if ($v.VoiceInfo.Culture.Name -like " + patron + ") { $sel = $v; break }",
        "};",
        "if ($sel) { $s.SelectVoice($sel.VoiceInfo.Name) };",
        "try { $s.Speak(" + frase + ") } catch { }",
    ])
    try:
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                          "-Command", ps],
                         creationflags=0x08000000 if os.name == "nt" else 0)
        return True
    except Exception:
        return False


def traductor(parameters: dict, player=None, speak=None) -> str:
    """Traduce frases a otro idioma y opcionalmente las pronuncia."""
    texto = str(parameters.get("texto", "") or parameters.get("frase", "")).strip()
    destino = _clave(parameters.get("a", "") or parameters.get("destino", "ingles"))
    origen = _clave(parameters.get("de", ""))
    pronuncia = str(parameters.get("pronunciar", "no")).strip().lower() in ("si", "sí", "s")

    action = str(parameters.get("action", "traducir")).strip().lower()
    if action in ("test",):
        return "El traductor funciona (Google gtx + respaldo MyMemory, sin claves)."
    if action in ("idiomas", "ayuda"):
        nombres = ", ".join(sorted(set(k for k in _IDIOMAS if " " not in k)))
        return f"Idiomas disponibles: {nombres}."

    if not texto:
        return "Decime qué frase traducir, por ejemplo texto='buen día' y a='ingles'."
    if not destino or destino == "auto":
        return "Decime a qué idioma, por ejemplo a='ingles' o a='frances'."

    if origen == "auto" or origen is None:
        origen = _autodetect(texto)

    # MyMemory primero (Google gtx da 429 con frecuencia desde esta IP)
    try:
        traducido = _mymemory(texto, origen, destino)
    except Exception:
        traducido = None
    if not traducido:
        for intento in range(2):
            try:
                traducido = _google(texto, origen, destino)
                if traducido:
                    break
            except Exception:
                traducido = None
    if traducido:
        traducido = traducido.strip().rstrip(",.;")
    else:
        return "No pude conectar con el traductor ahora. Probá de nuevo en un momento."

    if player:
        player.write_log("🌐 " + f"({destino}) “{texto}” → “{traducido}”")
    salida = f"En {_nombre(destino)} se dice así: {traducido}."
    if pronuncia:
        if _pronunciar(traducido, destino):
            salida += " Ya te lo pronuncié por el parlante."
        else:
            salida += " No hay voz instalada para ese idioma, pero te lo leo yo."
    return salida