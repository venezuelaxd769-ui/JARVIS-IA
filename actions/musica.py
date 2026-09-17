# -*- coding: utf-8 -*-
"""musica.py — Música local por voz.

Prefiere VLC (con su interfaz HTTP) para controlar pausa/siguiente/volumen.
Si no hay VLC, reproduce WAV con winsound; otros formatos requieren instalar
VLC ('instalar_vlc'). Busca en la carpeta de Música del usuario.
"""
import base64
import glob
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import winsound

_VLC_PATHS = [r"C:\Program Files\VideoLAN\VLC\vlc.exe",
              r"C:\Program Files (x86)\VideoLAN\VLC\vlc.exe",
              "vlc"]
_HOST = "127.0.0.1"
_PORT = 8080
_PASS = "nia-musica"
_EXT = ("*.mp3", "*.wav", "*.m4a", "*.ogg", "*.flac", "*.opus", "*.aac", "*.wma")
_STATE = {"vlc": None, "waiting": False}


def _vlc():
    for c in _VLC_PATHS:
        if os.path.exists(c) or shutil.which(c):
            return c if os.path.exists(c) else shutil.which(c)
    return None


def _music_dir():
    for k in ("USERPROFILE", "HOMEDRIVE"):
        pass
    home = os.environ.get("USERPROFILE", "")
    cands = [os.path.join(os.environ.get("USERPROFILE", ""), "Music"),
             os.path.join(home, "Música"),
             os.path.join(home, "Downloads")]
    for c in cands:
        if os.path.isdir(c):
            return c
    return home


def _http(cmd, params=None):
    base = f"http://{_HOST}:{_PORT}/requests/status.json"
    url = base if params is None else base + "?command=" + urllib.parse.quote(cmd)
    if params:
        for k, v in params.items():
            url += f"&{k}={urllib.parse.quote(str(v))}"
    elif cmd != "":
        url = f"{base}?command={urllib.parse.quote(cmd)}"
    req = urllib.request.Request(url)
    auth = "Basic " + base64.b64encode(f":{_PASS}".encode()).decode()
    req.add_header("Authorization", auth)
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _state_vlc():
    return _http("")


def _lanzar_vlc(files):
    vlc = _vlc()
    if not vlc:
        return False
    args = [vlc, f"--intf=http", f"--http-password={_PASS}",
            f"--http-port={_PORT}", "--http-host=127.0.0.1", "--extraintf=logger",
            "--no-video-title-show"]
    base = urllib.parse.quote("\\".join(files)[:40].replace("\\", "/"))
    _STATE["vlc"] = subprocess.Popen([*args, *files], creationflags=0x08000000)
    _STATE["waiting"] = True
    return True


def _esperar_http(retries=25):
    for _ in range(retries):
        time.sleep(0.5)
        if _http("") is not None:
            _STATE["waiting"] = False
            return True
    return False


def _cancelar_vlc():
    try:
        if _STATE.get("vlc") and _STATE["vlc"].poll() is None:
            _STATE["vlc"].terminate()
    except Exception:
        pass
    _STATE["vlc"] = None
    _STATE["waiting"] = False


def _buscar(nombre):
    raiz = _music_dir()
    hits = []
    for ext in _EXT:
        hits += glob.glob(os.path.join(raiz, "**", ext), recursive=True)
    hits = [h for h in hits if nombre.lower() in os.path.basename(h).lower()]
    return hits, raiz


def _bg_winget(msgdone):
    def job():
        try:
            r = subprocess.run(["winget", "install", "VideoLAN.VLC", "--silent", "--exact",
                                "--accept-source-agreements", "--accept-package-agreements"],
                               capture_output=True, text=True, timeout=900,
                               creationflags=0x08000000)
            m = ("VLC instalado: reinicia y decime 'poné música'."
                 if r.returncode == 0 else f"VLC no se instaló ({r.returncode}).")
        except Exception as e:
            m = f"Fallo instalando VLC: {e}"
        try:
            msgdone(m)
        except Exception:
            pass
    threading.Thread(target=job, daemon=True).start()


def musica(parameters: dict, player=None, speak=None) -> str:
    """Música local. Acciones: reproducir (ruta/carpeta/nombre), pausa, reanudar,
    siguiente, anterior, parar, volumen (valor, 0-100), instalar_vlc."""
    action = str(parameters.get("action", "estado")).strip().lower()
    ruta = str(parameters.get("ruta", "") or parameters.get("path", "")).strip()
    valor = parameters.get("valor")
    if player:
        player.write_log(f"🎵 musica: {action} {ruta}")

    vlc = _vlc()
    if not vlc and action not in ("instalar_vlc", "instalar"):
        return ("No está instalado VLC (reproduce de todo). Decime 'instalar_vlc' "
                "para que use winget, o probá con un archivo WAV directamente.")

    if action in ("instalar_vlc", "instalar", "install"):
        if vlc:
            return "VLC ya está instalado."
        if speak:
            _bg_winget(speak)
            return "Arranqué a instalar VLC en segundo plano; te aviso."
        _bg_winget(lambda m: None)
        return "Instalando VLC en segundo plano."

    if action in ("reproducir", "play", "poner", "start"):
        archivos = []
        if not ruta:
            return "Decime qué reproducir: ruta a archivo/carpeta o nombre de tema."
        if os.path.isfile(ruta):
            archivos = [ruta]
        elif os.path.isdir(ruta):
            archivos = [g for ext in _EXT for g in glob.glob(os.path.join(ruta, "**", ext), recursive=True)]
        else:
            hits, raiz = _buscar(ruta)
            archivos = hits[:20]
            if not archivos:
                return f"No encontré '{ruta}' en {raiz}. Probá otro nombre."
        if not archivos:
            return "No hay archivos de música en esa ruta."
        if not archivos[0].lower().endswith(".wav") and not vlc:
            return "Para ese formato necesito VLC. Decime 'instalar_vlc'."
        if vlc and not archivos[0].lower().endswith(".wav"):
            _cancelar_vlc()
            _lanzar_vlc(archivos)
            if _esperar_http():
                _http("pl_play")
                return f"🎵 Sonando {len(archivos)} tema(s), empezando por {os.path.basename(archivos[0])}."
            return "Arranqué VLC pero no pude conectarme; revisá el puerto 8080."
        try:
            winsound.PlaySound(archivos[0], winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
            return f"🎵 Sonando en bucle: {os.path.basename(archivos[0])}."
        except Exception as e:
            return f"No pude reproducir: {e}"

    if not vlc and action != "parar":
        return "Sin VLC solo puedo pausar audio reproducido por Nia. Decime 'instalar_vlc'."

    if action in ("estado", "info"):
        st = _state_vlc()
        if not st:
            return "No está sonando nada por ahora."
        cur = st.get("info", {}).get("current", {})
        nombre = None
        for k in ("url", "filename", "title"):
            if cur.get(k):
                nombre = cur[k]
                break
        return f"🎵 {nombre} — {st.get('state', '')} — volumen {st.get('volume', '?')}%"

    if action in ("pausa", "pausar", "pause"):
        _state_vlc() and _http("pl_pause")
        return "Pausado. ⏸️"

    if action in ("reanudar", "sigue", "resume"):
        _state_vlc() and _http("pl_pause")
        return "Reanudando. ▶️"

    if action in ("siguiente", "next"):
        _state_vlc() and _http("pl_next")
        return "Siguiente tema. ⏭️"

    if action in ("anterior", "prev"):
        _state_vlc() and _http("pl_previous")
        return "Tema anterior. ⏮️"

    if action in ("detener", "parar", "stop"):
        _state_vlc() and _http("pl_stop")
        _cancelar_vlc()
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass
        return "Detuve la música. 🛑"

    if action in ("volumen", "vol", "volumen_") and valor is not None:
        n = max(0, min(100, int(valor)))
        _http("volume", {"val": n})
        return f"Volumen en {n}%."

    return ("Acciones: reproducir (ruta o nombre) | pausa | reanudar | siguiente | "
            "anterior | detener | volumen (valor) | estado | instalar_vlc.")


if __name__ == "__main__":
    import sys
    p = {"action": sys.argv[1] if len(sys.argv) > 1 else "estado"}
    if len(sys.argv) > 2:
        p["ruta"] = sys.argv[2]
    print(musica(p))