"""tts_local.py — Voz local de Nia (respaldo local de la voz de la Nube).

Reemplazo con fuente del módulo .pyc original (Linux/Piper):
- Windows: síntesis por PowerShell System.Speech (SAPI) — voz del sistema
  (en español si el idioma está instalado), sin dependencias externas.
- Linux: usa Piper tal como el .pyc original (modelo es_ES-davefx-medium).

API compatible: tts_local(parameters, player=None) y speak_local(text).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VOICE_DIR = Path.home() / ".local" / "share" / "piper"
VOICE = VOICE_DIR / "es_ES-davefx-medium.onnx"
VOICE_CFG = {
    "sampling_rate": 22050,
    "language": "es",
    "voice": "davefx-medium",
}


def _is_windows():
    return os.name == "nt"


def available():
    if _is_windows():
        return True
    return VOICE.exists() or subprocess.run(["which", "piper"],
                                            capture_output=True).returncode == 0


def synthesize(text: str) -> bytes | None:
    if _is_windows():
        return None
    try:
        if not VOICE.exists():
            return None
        return subprocess.run(
            ["piper", "--model", str(VOICE), "--output-raw"],
            input=text.encode("utf-8"), capture_output=True,
        ).stdout
    except Exception:
        return None


def _speak_windows(text: str):
    import tempfile
    text = (text or "").strip()
    if not text:
        return
    safe = text.replace("'", "''")
    ps = (
        "$ErrorActionPreference='SilentlyContinue';"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$es=[System.Globalization.CultureInfo]::GetCultures([System.Globalization.CultureTypes]::InstalledCultures) | "
        "Where-Object {$_.TwoLetterISOLanguageName -eq 'es'} | Select-Object -First 1;"
        "if($es){$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female)};"
        f"$s.Speak('{safe}')"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", ps],
            timeout=60,
        )
    except Exception:
        pass


def speak_local(text: str):
    text = str(text or "")[:400]
    if _is_windows():
        _speak_windows(text)
        return
    try:
        raw = synthesize(text)
        if raw:
            import tempfile as _tf
            import threading
            with _tf.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(raw)
                tmp = f.name
            threading.Thread(
                target=lambda: subprocess.run(
                    ["ffplay", "-nodisp", "-autoexit", tmp],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ), daemon=True,
            ).start()
    except Exception:
        pass


def tts_local(parameters: dict, player=None) -> str:
    text = str(parameters.get("text", "")).strip()
    if text:
        speak_local(text)
        return f"Voz local: {text[:60]}"
    return "Falta el parámetro 'text'."