"""spotify_control.py — Clean Spotify/Media controller using Windows API hooks & Web API."""
import time
import json
from pathlib import Path

def spotify_control(parameters: dict, player=None) -> str:
    """Control Spotify using Spotify Web API (via spotipy) or generic active media playback using Windows API commands."""
    action = parameters.get("action", "").lower().strip()
    query = parameters.get("query", "").strip()
    search_type = parameters.get("type", "track").lower().strip()
    value = parameters.get("value", "")

    if not action:
        return "Action parameter is required."

    if search_type not in ["track", "album", "playlist", "artist"]:
        search_type = "track"

    try:
        # 1. Intento usar la API de Spotify mediante spotipy
        from memory.config_manager import load_api_keys, BASE_DIR
        cfg = load_api_keys()
        client_id = cfg.get("spotify_client_id")
        client_secret = cfg.get("spotify_client_secret")
        
        if client_id and client_secret:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            
            cache_path = BASE_DIR / ".spotify_cache"
            sp_oauth = SpotifyOAuth(
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=cfg.get("spotify_redirect_uri", "http://127.0.0.1:8765/callback"),
                scope="user-modify-playback-state user-read-playback-state user-read-currently-playing user-library-read user-library-modify",
                open_browser=False,
                cache_path=str(cache_path)
            )
            token_info = sp_oauth.get_cached_token()
            
            if token_info:
                sp = spotipy.Spotify(auth=token_info['access_token'])
                
                # Obtener dispositivo activo o disponible
                devices = sp.devices().get("devices", [])
                active_device = None
                for d in devices:
                    if d["is_active"]:
                        active_device = d["id"]
                        break
                if not active_device and devices:
                    active_device = devices[0]["id"]
                
                if action in ("play", "resume"):
                    if query:
                        # Buscar la canción / playlist / artista / álbum
                        results = sp.search(q=query, limit=1, type=search_type)
                        items = results.get(f"{search_type}s", {}).get("items", [])
                        if not items:
                            return f"No se encontró ningún {search_type} para '{query}' en Spotify."
                        
                        item = items[0]
                        item_uri = item["uri"]
                        item_name = item["name"]
                        
                        # Si es pista, pasar uris=[uri], si es artista/album/playlist pasar context_uri=uri
                        if search_type == "track":
                            sp.start_playback(device_id=active_device, uris=[item_uri])
                            artist_name = item["artists"][0]["name"]
                            msg = f"Reproduciendo: {item_name} - {artist_name}"
                        else:
                            sp.start_playback(device_id=active_device, context_uri=item_uri)
                            msg = f"Reproduciendo {search_type}: {item_name}"
                    else:
                        sp.start_playback(device_id=active_device)
                        msg = "Reproducción de Spotify reanudada."
                        
                elif action == "pause":
                    sp.pause_playback(device_id=active_device)
                    msg = "Reproducción de Spotify pausada."
                    
                elif action == "toggle":
                    curr = sp.current_playback()
                    if curr and curr["is_playing"]:
                        sp.pause_playback(device_id=active_device)
                        msg = "Reproducción pausada."
                    else:
                        sp.start_playback(device_id=active_device)
                        msg = "Reproducción reanudada."
                        
                elif action in ("next", "skip"):
                    sp.next_track(device_id=active_device)
                    msg = "Siguiente pista."
                    
                elif action in ("prev", "previous", "back"):
                    sp.previous_track(device_id=active_device)
                    msg = "Pista anterior."
                    
                elif action == "volume":
                    try:
                        # Si value es algo como "up" o "down"
                        if "up" in str(value).lower() or "down" in str(value).lower():
                            curr = sp.current_playback()
                            current_vol = curr["device"]["volume_percent"] if curr else 50
                            step = 10 if "up" in str(value).lower() else -10
                            new_vol = max(0, min(100, current_vol + step))
                            sp.volume(volume_percent=new_vol, device_id=active_device)
                            msg = f"Volumen ajustado a {new_vol}%."
                        else:
                            vol = int(value)
                            sp.volume(volume_percent=vol, device_id=active_device)
                            msg = f"Volumen de Spotify establecido en {vol}%."
                    except Exception as ve:
                        msg = f"Error al ajustar volumen: {ve}"
                        
                elif action == "shuffle":
                    # shuffle toggle or state
                    shuffle_state = True
                    if str(value).lower() in ("false", "off", "no"):
                        shuffle_state = False
                    elif str(value).lower() in ("true", "on", "yes", ""):
                        curr = sp.current_playback()
                        shuffle_state = not curr["shuffle_state"] if curr else True
                    sp.shuffle(state=shuffle_state, device_id=active_device)
                    msg = f"Aleatorio establecido en {'activado' if shuffle_state else 'desactivado'}."
                    
                elif action == "repeat":
                    repeat_state = str(value).lower()
                    if repeat_state not in ("off", "track", "context"):
                        repeat_state = "track"
                    sp.repeat(state=repeat_state, device_id=active_device)
                    msg = f"Repetición establecida en '{repeat_state}'."
                    
                elif action == "current":
                    curr = sp.current_playback()
                    if curr and curr.get("item"):
                        item = curr["item"]
                        return f"Sonando ahora en Spotify: {item['name']} - {item['artists'][0]['name']}."
                    return "No está sonando nada en Spotify en este momento."
                    
                elif action == "like":
                    curr = sp.current_playback()
                    if curr and curr.get("item"):
                        track_id = curr["item"]["id"]
                        track_name = curr["item"]["name"]
                        sp.current_user_saved_tracks_add(tracks=[track_id])
                        msg = f"Canción '{track_name}' agregada a tus favoritos."
                    else:
                        msg = "No se está reproduciendo ninguna canción para dar Me Gusta."
                        
                elif action == "devices":
                    devs = sp.devices().get("devices", [])
                    if devs:
                        msg = "Dispositivos disponibles: " + ", ".join([d["name"] for d in devs])
                    else:
                        msg = "No se detectaron dispositivos de Spotify activos."
                        
                elif action == "playlist":
                    if query:
                        results = sp.search(q=query, limit=1, type="playlist")
                        playlists = results.get("playlists", {}).get("items", [])
                        if playlists:
                            pl = playlists[0]
                            sp.start_playback(device_id=active_device, context_uri=pl["uri"])
                            msg = f"Reproduciendo la playlist '{pl['name']}'."
                        else:
                            msg = f"No se encontró la playlist '{query}'."
                    else:
                        msg = "Por favor, especifica el nombre de la playlist."
                        
                else:
                    msg = f"Acción '{action}' no reconocida en el controlador API."
                
                if player:
                    player.write_log(f"🎵 Spotify API: {msg}")
                return msg

        # 2. Si no hay credenciales API o falla la sesión de spotipy, hacemos Fallback con pyautogui
    except Exception as e:
        # Fallback silencioso a pyautogui si la API falla
        pass

    try:
        import pyautogui
        
        if action in ("play", "pause", "toggle", "resume"):
            pyautogui.press("playpause")
            msg = "Media playback toggled (teclado)."
        elif action in ("next", "skip"):
            pyautogui.press("nexttrack")
            msg = "Skipped to next track (teclado)."
        elif action in ("prev", "previous", "back"):
            pyautogui.press("prevtrack")
            msg = "Returned to previous track (teclado)."
        elif action == "volume":
            if "up" in str(value).lower():
                pyautogui.press("volumeup", presses=5)
                msg = "Volume increased (teclado)."
            elif "down" in str(value).lower():
                pyautogui.press("volumedown", presses=5)
                msg = "Volume decreased (teclado)."
            else:
                msg = f"Volume adjust requires relative direction: {value}"
        else:
            msg = f"Action '{action}' not recognized or search requires API configured, sir."
            
        if player:
            player.write_log(f"🎵 Spotify (Teclado): {msg}")
        return msg
    except Exception as e:
        return f"Error executing media control action: {e}"
