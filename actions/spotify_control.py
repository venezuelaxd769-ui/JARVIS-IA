"""spotify_control.py — Spotify control via MPRIS (playerctl) + Web API."""
import subprocess
import shutil
import json
import urllib.request
import urllib.parse

_HAS_PLAYERCTL = shutil.which("playerctl") is not None
_HAS_SPOTIFY_CLI = shutil.which("spotify") is not None
_SPOTIFY_PLAYER = "spotify"

_DEFAULT_CLIENT_ID = "455d312ba37a4e0c8be373b53f6305a4"
_DEFAULT_CLIENT_SECRET = "5a075d9e504c4f3cb4cc6c5e533d1b4a"


def _creds() -> tuple[str, str, str]:
    """Devuelve (client_id, client_secret, redirect_uri) leyendo la config
    y cayendo a las credenciales embebidas de Nia si el usuario no tiene las suyas."""
    try:
        from memory.config_manager import load_api_keys
        cfg = load_api_keys()
        return (
            str(cfg.get("spotify_client_id", "")).strip() or _DEFAULT_CLIENT_ID,
            str(cfg.get("spotify_client_secret", "")).strip() or _DEFAULT_CLIENT_SECRET,
            str(cfg.get("spotify_redirect_uri", "http://127.0.0.1:8888/callback")).strip(),
        )
    except Exception:
        return (_DEFAULT_CLIENT_ID, _DEFAULT_CLIENT_SECRET, "http://127.0.0.1:8888/callback")


def _get_token_info() -> dict | None:
    """Devuelve el token de Spotify cacheado (sin refrescar)."""
    try:
        from memory.config_manager import BASE_DIR
        from spotipy.oauth2 import SpotifyOAuth
        client_id, client_secret, redirect_uri = _creds()
        sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-library-read user-library-modify",
            open_browser=False,
            cache_path=str(BASE_DIR / ".spotify_cache"),
        )
        token_info = sp_oauth.get_cached_token()
        return token_info
    except Exception:
        return None


def _is_connected() -> bool:
    return bool(_get_token_info())

def _playerctl(args: list[str]) -> str:
    try:
        return subprocess.run(
            ["playerctl", "--player=" + _SPOTIFY_PLAYER] + args,
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ""

def _spotify_running() -> bool:
    if not _HAS_PLAYERCTL:
        return False
    players = subprocess.run(
        ["playerctl", "-l"], capture_output=True, text=True, timeout=3
    ).stdout.strip()
    return _SPOTIFY_PLAYER in players

def _launch_spotify():
    if _HAS_SPOTIFY_CLI:
        subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def _play_spotipy(action: str, query: str = "", search_type: str = "track", value: str = "") -> str | None:
    try:
        from memory.config_manager import BASE_DIR
        client_id, client_secret, redirect_uri = _creds()
        if not client_id or not client_secret:
            return None

        import spotipy
        from spotipy.oauth2 import SpotifyOAuth

        cache_path = BASE_DIR / ".spotify_cache"
        sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-library-read user-library-modify",
            open_browser=False,
            cache_path=str(cache_path)
        )
        token_info = sp_oauth.get_cached_token()
        if not token_info:
            return None
        sp = spotipy.Spotify(auth=token_info['access_token'])

        devices = sp.devices().get("devices", [])
        active_device = None
        for d in devices:
            if d["is_active"]:
                active_device = d["id"]
                break
        if not active_device and devices:
            active_device = devices[0]["id"]

        if action == "play":
            if query:
                results = sp.search(q=query, limit=1, type=search_type)
                items = results.get(f"{search_type}s", {}).get("items", [])
                if not items:
                    return f"No encontré '{query}' en Spotify."
                item = items[0]
                item_uri = item["uri"]
                item_name = item["name"]
                if search_type == "track":
                    sp.start_playback(device_id=active_device, uris=[item_uri])
                    artist = item["artists"][0]["name"]
                    return f"Reproduciendo {item_name} - {artist}."
                else:
                    sp.start_playback(device_id=active_device, context_uri=item_uri)
                    return f"Reproduciendo {search_type}: {item_name}."
            else:
                sp.start_playback(device_id=active_device)
                return "Reanudando Spotify."
        elif action == "pause":
            sp.pause_playback(device_id=active_device)
            return "Pausado."
        elif action == "next":
            sp.next_track(device_id=active_device)
            return "Siguiente pista."
        elif action == "previous":
            sp.previous_track(device_id=active_device)
            return "Pista anterior."
    except Exception:
        return None

def spotify_control(parameters: dict, player=None) -> str:
    action = parameters.get("action", "").lower().strip()
    query = parameters.get("query", "").strip()
    search_type = parameters.get("type", "track").lower().strip()
    value = parameters.get("value", "")

    if not action:
        return "Parámetro 'action' requerido."

    # 0. Estado de conexión / autenticación (no requiere Spotify abierto)
    if action in ("status", "connected", "auth", "check"):
        info = _get_token_info()
        if not info:
            return "Spotify no conectado: falta autorización. Pedile al usuario que vaya a Configuración → Spotify → 'Conectar con Spotify'."
        try:
            from memory.config_manager import BASE_DIR
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            client_id, client_secret, redirect_uri = _creds()
            sp = spotipy.Spotify(auth=info["access_token"])
            me = sp.current_user()
            name = me.get("display_name") or me.get("id", "usuario")
            return f"Spotify conectado como {name} (Web API disponible)."
        except Exception:
            return "Spotify conectado pero el token expiró; pedí reconectar en Configuración → Spotify."

    # 1. Try Spotify Web API (spotipy) — needs client_id/secret
    if action in ("play", "pause", "next", "previous"):
        api_result = _play_spotipy(action, query, search_type, value)
        if api_result:
            if player:
                player.write_log(f"🎵 {api_result}")
            return api_result

    # 2. MPRIS via playerctl — for transport when Spotify is running
    if _spotify_running() and _HAS_PLAYERCTL:
        if action == "play" or action == "resume":
            _playerctl(["play"])
            return "Reproducción reanudada."
        elif action == "pause":
            _playerctl(["pause"])
            return "Pausado."
        elif action == "toggle":
            _playerctl(["play-pause"])
            return "Toggle."
        elif action in ("next", "skip"):
            _playerctl(["next"])
            return "Siguiente pista."
        elif action in ("prev", "previous", "back"):
            _playerctl(["previous"])
            return "Pista anterior."
        elif action == "volume":
            try:
                # playerctl doesn't have volume, use pactl
                vol = int(value)
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"], timeout=3)
                return f"Volumen ajustado a {vol}%."
            except Exception:
                return "No se pudo ajustar el volumen."
        elif action == "current":
            meta = _playerctl(["metadata", "--format", "{{artist}} - {{title}}"])
            if meta:
                return f"Sonando ahora: {meta}."
            return "No está sonando nada."
        elif action == "devices":
            return "Spotify corriendo en este equipo (MPRIS)."

    # 3. Launch Spotify if not running + create a search URI
    if action == "play" and query:
        _launch_spotify()
        search_uri = f"spotify:search:{urllib.parse.quote(query)}"
        subprocess.Popen(["xdg-open", search_uri],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Buscando '{query}' en Spotify."

    # 4. Start Spotify with no query
    if action == "play" or action == "resume":
        _launch_spotify()
        return "Abriendo Spotify."

    # 5. Basic volume control without Spotify
    if action == "volume":
        try:
            vol = int(value)
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"], timeout=3)
            return f"Volumen del sistema a {vol}%."
        except Exception:
            return "No se pudo ajustar el volumen."

    # 6. Nothing worked
    msg = f"Spotify no está instalado o no se pudo ejecutar '{action}'."
    if player:
        player.write_log(f"🎵 {msg}")
    return msg
