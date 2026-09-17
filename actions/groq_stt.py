# -*- coding: utf-8 -*-
"""groq_stt.py — Transcribe audio a texto con Whisper de Groq (rapidísimo).

Nia puede transcribir un archivo de audio (wav/mp3/m4a/ogg...) en segundos
usando whisper-large-v3-turbo de Groq. Útil para notas de voz, audios
recibidos o para pasar a texto cualquier grabación.
"""
import os


def groq_stt(parameters: dict, player=None, speak=None) -> str:
    """Transcribir un archivo de audio a texto con Whisper (Groq)."""
    file = str(parameters.get("file", "")).strip()
    language = str(parameters.get("language", "es")).strip().lower() or "es"
    if player:
        player.write_log(f"🎙 groq_stt: {os.path.basename(file)}")
    if not file or not os.path.exists(file):
        return "Necesito la ruta de un audio para transcribir (file)."
    try:
        import httpx
    except ImportError:
        return "Falta la librería httpx para transcribir."
    import json

    try:
        key = json.load(open(
            os.path.join(os.path.dirname(__file__), os.pardir, "config", "api_keys.json"),
            encoding="utf-8")).get("groq_api_key", "")
    except Exception:
        key = ""
    if not key:
        return "No hay clave de Groq en config/api_keys.json."

    ext = os.path.splitext(file)[1].lstrip(".") or "audio"
    mime = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4",
            "ogg": "audio/ogg", "webm": "audio/webm", "flac": "audio/flac",
            "mp4": "audio/mp4"}.get(ext.lower(), "audio/wav")
    try:
        with open(file, "rb") as f:
            files = {"file": (os.path.basename(file), f.read(), mime)}
        data = {"model": "whisper-large-v3-turbo", "language": language,
                "response_format": "text"}
        with httpx.Client(timeout=180) as http:
            resp = http.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {key}",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                },
                data=data, files=files)
        if resp.status_code != 200:
            return f"Groq devolvió error {resp.status_code}: {resp.text[:150]}"
        text = resp.text.strip()
        if not text:
            return "No pude entender nada del audio."
        return f"Transcripción ({os.path.basename(file)}): {text[:800]}"
    except Exception as e:
        return f"No pude transcribir: {e}"