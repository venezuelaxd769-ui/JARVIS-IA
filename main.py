import os
import json
import sys
from pathlib import Path

# fastembed v0.8 usa tempfile/fastembed_cache (volátil) por defecto; forzamos
# un cache persistente para el modelo de embeddings (RAG/Obsidian).
os.environ.setdefault(
    "FASTEMBED_CACHE_PATH",
    str(Path.home() / ".cache" / "fastembed"),
)

# Load config early to determine GPU acceleration settings
_gpu_enabled = False
try:
    if getattr(sys, "frozen", False):
        _base_dir = Path(sys.executable).parent
    else:
        _base_dir = Path(__file__).resolve().parent
    _cfg_path = _base_dir / "config" / "api_keys.json"
    if _cfg_path.exists():
        _cfg = json.loads(_cfg_path.read_text(encoding="utf-8"))
        _gpu_enabled = _cfg.get("gpu_acceleration", False)
except Exception:
    pass

if _gpu_enabled:
    # GPU / High Performance Mode: sustain rendering workload on GPU VRAM, maximize space size
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--ignore-gpu-blocklist "
        "--enable-gpu-rasterization "
        "--enable-zero-copy "
        "--num-raster-threads=4 "
        "--renderer-process-limit=1 "
        "--disable-site-isolation-trials "
        "--js-flags=--max-old-space-size=256"
    )
    # Enable hardware acceleration backends for Qt
    os.environ["QSG_RHI_BACKEND"] = "d3d11" # Force Direct3D 11 for hardware rendering on Windows
    os.environ["QSG_INFO"] = "1"
    print("[JARVIS] GPU Acceleration is ENABLED. Offloading RAM rendering workload to GPU.")
else:
    # Balanced low-RAM mode: Keep GPU hardware compositing enabled so glowing CSS effects and drop-shadows are rendered beautifully, but limit renderer processes and JS space size.
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--enable-low-end-device-mode "
        "--renderer-process-limit=1 "
        "--disable-site-isolation-trials "
        "--js-flags=--max-old-space-size=64 "
        "--disable-gpu-shader-disk-cache "
        "--disable-dev-shm-usage "
        "--disable-extensions "
        "--disable-sync "
        "--mute-audio"
    )
    print("[JARVIS] Using Balanced Low RAM GPU-Composited mode for beautiful fluid rendering.")

import asyncio
import subprocess
from concurrent.futures import ThreadPoolExecutor
from beta_config import is_pro_tool, check_daily_limit, increment_calls, pro_tool_message, daily_limit_message
import re
import threading
try:
    import pygetwindow as gw
except (ImportError, NotImplementedError):
    gw = None
from PyQt6.QtCore import QMetaObject, Qt, Q_ARG

import traceback

try:
    from pngtuber.client import send as _pngtuber_send
    from pngtuber.client import send_volume as _pngtuber_send_volume
    from pngtuber.client import close_volume as _pngtuber_close_volume
except Exception:
    _pngtuber_send = None
    _pngtuber_send_volume = None
    _pngtuber_close_volume = None

# ── Dedicated thread pool for tool execution — prevents starvation ────────────
_TOOL_EXECUTOR = ThreadPoolExecutor(max_workers=12, thread_name_prefix="jarvis-tool")

# ── Memory watchdog: evita que el kernel OOM mate a Nia ──────────────────────
_MEMORY_CRITICAL_MB = 300  # RAM disponible considerada crítica
_MEMORY_STRIKES = 2        # comprobaciones consecutivas antes de actuar


def _memory_watchdog_loop():
    """Vigila la RAM disponible. Si queda críticamente poca, fuerza un GC
    y registra los mayores consumidores antes de un posible OOM kill."""
    import gc
    import time
    try:
        import psutil
    except Exception:
        return
    low_strikes = 0
    while True:
        try:
            vm = psutil.virtual_memory()
            avail_mb = vm.available / (1024 * 1024)
            if avail_mb < _MEMORY_CRITICAL_MB:
                low_strikes += 1
                if low_strikes >= _MEMORY_STRIKES:
                    try:
                        proc = psutil.Process()
                        before = proc.memory_info().rss / (1024 * 1024)
                        n = gc.collect()
                        after = psutil.Process().memory_info().rss / (1024 * 1024)
                        print(f"[MEM] RAM crítica ({avail_mb:.0f}MB libres). "
                              f"GC liberó {n} objetos, Nia {before:.0f}→{after:.0f}MB.")
                    except Exception:
                        pass
                    try:
                        top = sorted(
                            ((p.info.get("rss") or 0) // 1048576, p.info.get("comm", ""))
                            for p in psutil.process_iter(["comm", "rss"])
                        )[-5:]
                        print("[MEM] Top consumidores: " + ", ".join(
                            f"{name} {mb}MB" for mb, name in reversed(top)))
                    except Exception:
                        pass
                    low_strikes = 0
            else:
                    low_strikes = 0
        except Exception:
            pass
        time.sleep(6)


# ── PNGtuber: watchdog que revive el modelo si el proceso muere ──────────────
_PNGTUBER_APP = Path(__file__).resolve().parent / "pngtuber" / "pngtuber_app.py"


_PNGTUBER_PROC = None


def _pngtuber_proc_alive() -> bool:
    return _PNGTUBER_PROC is not None and _PNGTUBER_PROC.poll() is None


def _launch_pngtuber():
    """Lanza el proceso PNGtuber en modo oculto. Es single-instance por puerto:
    si ya hay otro escuchando, el nuevo sale solo por sí mismo.

    Antes de lanzar, mata los huérfanos que YA NO responden al ping (restos de
    Nias muertas por segfault): acumulaban 3-4 procesos con la boca congelada
    y ningún dueño. A la instancia viva no la tocamos.
    """
    global _PNGTUBER_PROC
    try:
        alive = bool(_pngtuber_send("ping")) if _pngtuber_send else False
    except Exception:
        alive = False
    if alive:
        # Ya hay una instancia que responde (la nuestra u otra viva): no duplicar.
        return _PNGTUBER_PROC
    try:
        subprocess.run(
            ["pkill", "-f", "pngtuber_app.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3,
        )
        import time as _pt
        _pt.sleep(0.2)  # dejar que libere el puerto
    except Exception:
        pass
    try:
        _PNGTUBER_PROC = subprocess.Popen(
            [sys.executable, str(_PNGTUBER_APP)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return _PNGTUBER_PROC
    except Exception as e:
        print(f"[PNGTUBER] ERROR al lanzar: {e}")
        return None


def _shutdown_pngtuber():
    """Mata el PNGtuber de esta sesión (o sus huérfanos) al salir de Nia, para
    que no queden procesos fantasma con la boca congelada."""
    if _pngtuber_proc_alive():
        try:
            _PNGTUBER_PROC.terminate()
        except Exception:
            pass
    try:
        subprocess.run(
            ["pkill", "-f", "pngtuber_app.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        pass


def _pngtuber_watchdog_loop():
    """Cada pocos segundos comprueba que el PNGtuber siga vivo (ping). Si
    falla dos veces seguidas, lo relanza. Es la causa típica de 'el modelo
    no aparece': el proceso murió y nadie lo resucitaba."""
    import time
    misses = 0
    while True:
        time.sleep(4)
        try:
            ok = bool(_pngtuber_send("ping")) if _pngtuber_send else False
        except Exception:
            ok = False
        if ok:
            misses = 0
            continue
        misses += 1
        if misses >= 2:
            misses = 0
            print("[PNGTUBER] proceso caído → relanzando...")
            _launch_pngtuber()

try:
    from zoneinfo import ZoneInfo as _ZoneInfo
    _BA_TZ = _ZoneInfo("America/Lima")
except Exception:
    from datetime import timezone as _tz, timedelta as _td
    _BA_TZ = _tz(_td(hours=-5))


def _load_tz():
    """Load timezone from api_keys.json config."""
    global _BA_TZ
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        tz_name = cfg.get("timezone", "")
        if tz_name:
            try:
                _BA_TZ = _ZoneInfo(tz_name)
                print(f"[TZ] Timezone loaded: {tz_name}")
            except Exception as e:
                print(f"[TZ] Failed to load '{tz_name}': {e}")
                # Fallback: try to find a common alias or partial match
                import zoneinfo as _zi
                available = _zi.available_timezones()
                # Try case-insensitive match
                tz_lower = tz_name.lower()
                for known in available:
                    if known.lower() == tz_lower:
                        _BA_TZ = _ZoneInfo(known)
                        print(f"[TZ] Matched '{tz_name}' → '{known}'")
                        break
                else:
                    # Try partial match (e.g., "Buenos_Aires" → "America/Argentina/Buenos_Aires")
                    parts = tz_name.replace("\\", "/").split("/")
                    short = parts[-1].lower() if parts else ""
                    for known in available:
                        if known.lower().endswith("/" + short):
                            _BA_TZ = _ZoneInfo(known)
                            print(f"[TZ] Partial match '{tz_name}' → '{known}'")
                            break
                    else:
                        from datetime import datetime as _dt
                        _BA_TZ = _dt.now().astimezone().tzinfo
                        print(f"[TZ] Falling back to system timezone: {_BA_TZ}")
    except Exception as e:
        print(f"[TZ] Error reading config: {e}")

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI

def _patch_settings_ui():
    pass

_patch_settings_ui()

from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

try:
    from actions.file_processor import file_processor
except ImportError:
    file_processor = None
try:
    from actions.flight_finder     import flight_finder
except ImportError:
    flight_finder = None
try:
    from actions.open_app          import open_app
except ImportError:
    open_app = None
try:
    from actions.weather_report    import weather_action
except ImportError:
    weather_action = None
try:
    from actions.send_message      import send_message
except ImportError:
    send_message = None
try:
    from actions.reminder          import reminder
except ImportError:
    reminder = None
try:
    from actions.computer_settings import computer_settings
except ImportError:
    computer_settings = None
try:
    from actions.screen_vision import screen_vision
except ImportError:
    screen_vision = None
try:
    from actions.youtube_video     import youtube_video
except ImportError:
    youtube_video = None
try:
    from actions.desktop           import desktop_control
except ImportError:
    desktop_control = None
try:
    from actions.browser_control   import browser_control
except ImportError:
    browser_control = None
try:
    from actions.visual_click import visual_click
except ImportError:
    visual_click = None
try:
    from actions.mouse_keyboard import mouse_control, keyboard_control, screen_click
except ImportError:
    mouse_control = keyboard_control = screen_click = None
try:
    from actions.youtube_kb import (open_recommended_video, search as youtube_search_kb,
        play_pause as youtube_play_pause_kb, mute as youtube_mute_kb,
        fullscreen as youtube_fullscreen_kb, search_and_open as youtube_search_open_kb,
        seek_forward as youtube_seek_fwd_kb, seek_backward as youtube_seek_bwd_kb)
except ImportError:
    (open_recommended_video, youtube_search_kb, youtube_play_pause_kb,
     youtube_mute_kb, youtube_fullscreen_kb, youtube_search_open_kb,
     youtube_seek_fwd_kb, youtube_seek_bwd_kb) = (None,) * 8
try:
    from actions.web_kb import (go_to, navigate_and_click, type_text, tab, new_tab, close_tab,
        search_bar, search_on_page, get_active_window_title, google_search,
        youtube_search, full_browse_session, switch_tab, go_back, go_forward,
        scroll, reopen_closed_tab, enter as kb_enter, reload as kb_reload,
        tab as kb_tab)
except ImportError:
    (go_to, navigate_and_click, type_text, new_tab, close_tab,
     search_bar, search_on_page, get_active_window_title, google_search,
     youtube_search, full_browse_session, switch_tab, go_back, go_forward,
     scroll, reopen_closed_tab) = (None,) * 16
    kb_enter = kb_reload = kb_tab = None
try:
    from actions.desktop_kb import list_windows, switch_to_app, go_to_workspace, close_window, get_active_window, move_to_workspace, toggle_fullscreen, maximize_toggle
except ImportError:
    list_windows = switch_to_app = go_to_workspace = close_window = get_active_window = move_to_workspace = toggle_fullscreen = maximize_toggle = None
try:
    from actions.self_agent import exploration_mode, stop_exploration
except ImportError:
    exploration_mode = stop_exploration = None
try:
    from actions.file_controller   import file_controller
except ImportError:
    file_controller = None

try:
    from actions.code_helper import code_helper
except ImportError:
    code_helper = None

try:
    from actions.dev_agent         import dev_agent
except ImportError:
    dev_agent = None
try:
    from actions.web_search        import web_search as web_search_action
except ImportError:
    web_search_action = None
try:
    from actions.computer_control  import computer_control
except ImportError:
    computer_control = None
try:
    from actions.game_updater      import game_updater
except ImportError:
    game_updater = None
try:
    from actions.google_calendar   import google_calendar
except ImportError:
    google_calendar = None
try:
    from actions.spotify_control   import spotify_control
except ImportError:
    spotify_control = None
try:
    from actions.daily_summary     import daily_summary
except ImportError:
    daily_summary = None
try:
    from actions.tts_local         import tts_local
except ImportError:
    tts_local = None
try:
    from actions.usage_stats       import record_usage, usage_stats
except ImportError:
    record_usage = None
    usage_stats = None
try:
    from actions.rgb_control       import rgb_control
except ImportError:
    rgb_control = None
try:
    from actions.scheduler         import scheduler, start_runner
except ImportError:
    scheduler = None; start_runner = None
try:
    from actions.google_drive      import google_drive
except ImportError:
    google_drive = None
try:
    from actions.gmail_control     import gmail_control
except ImportError:
    gmail_control = None
try:
    from actions.google_maps       import google_maps
except ImportError:
    google_maps = None
try:
    from actions.rules_engine      import rules_engine, start_rules_runner, check_phrase_triggers, _run_action as _rules_run_action
except ImportError:
    rules_engine = None; start_rules_runner = None; check_phrase_triggers = None; _rules_run_action = None
try:
    from actions.social_media      import social_media
except ImportError:
    social_media = None
try:
    from actions.whatsapp          import whatsapp
except ImportError:
    whatsapp = None
try:
    from actions.user_profile      import user_profile, record_action
except ImportError:
    user_profile = None; record_action = None
try:
    from actions.goals             import goals
except ImportError:
    goals = None
try:
    from actions.git_control       import git_control
except ImportError:
    git_control = None
try:
    from actions.codebase          import codebase
except ImportError:
    codebase = None
try:
    from actions.knowledge_base    import knowledge_base
except ImportError:
    knowledge_base = None
try:
    from actions.timer             import timer
except ImportError:
    timer = None
try:
    from actions.clipboard         import clipboard
except ImportError:
    clipboard = None
try:
    from actions.code_search       import code_search
except ImportError:
    code_search = None
try:
    from actions.code_editor       import code_editor
except ImportError:
    code_editor = None
try:
    from actions.shell_exec        import shell_exec
except ImportError:
    shell_exec = None
try:
    from actions.project_analyzer  import project_analyzer
except ImportError:
    project_analyzer = None
try:
    from actions.skill_manager     import skill_manager
except ImportError:
    skill_manager = None
try:
    from actions.web_fetch         import web_fetch
except ImportError:
    web_fetch = None
try:
    from actions.pdf_reader        import pdf_reader
except ImportError:
    pdf_reader = None
try:
    from actions.csv_analyzer      import csv_analyzer
except ImportError:
    csv_analyzer = None
try:
    from actions.image_reader      import image_reader
except ImportError:
    image_reader = None
try:
    from actions.code_executor     import code_executor
except ImportError:
    code_executor = None
try:
    from actions.multi_step_executor import multi_step_executor
except ImportError:
    multi_step_executor = None
try:
    from actions.web_crawler       import web_crawler
except ImportError:
    web_crawler = None
try:
    from actions.persistent_context import persistent_context
except ImportError:
    persistent_context = None
try:
    from actions.self_improve      import self_improve
except ImportError:
    self_improve = None
try:
    from actions.real_vision       import real_vision
except ImportError:
    real_vision = None
try:
    from actions.process_manager   import process_manager
except ImportError:
    process_manager = None
try:
    from actions.package_manager   import package_manager
except ImportError:
    package_manager = None
try:
    from actions.file_watcher      import file_watcher
except ImportError:
    file_watcher = None
try:
    from actions.env_manager       import env_manager
except ImportError:
    env_manager = None
try:
    from actions.backup_manager    import backup_manager
except ImportError:
    backup_manager = None
try:
    from actions.test_runner       import test_runner
except ImportError:
    test_runner = None
try:
    from actions.doc_generator     import doc_generator
except ImportError:
    doc_generator = None
try:
    from actions.multi_search      import multi_search
except ImportError:
    multi_search = None
try:
    from actions.obsidian_bridge   import obsidian_bridge
except ImportError:
    obsidian_bridge = None
try:
    from actions.windows_settings  import windows_settings
except ImportError:
    windows_settings = None
try:
    from actions.document_creator  import document_creator
except ImportError:
    document_creator = None
try:
    from actions.document_manager  import document_manager
except ImportError:
    document_manager = None
try:
    from actions.web_navigation    import web_navigation
except ImportError:
    web_navigation = None
try:
    from actions.image_generation  import image_generation
except ImportError:
    image_generation = None
try:
    from actions.smart_home        import smart_home
except ImportError:
    smart_home = None
try:
    from actions.system_monitor    import system_monitor
except ImportError:
    system_monitor = None
try:
    from actions.tiktok_analyzer   import tiktok_analyzer
except ImportError:
    tiktok_analyzer = None
try:
    from actions.arca_invoice      import arca_invoice
except ImportError:
    arca_invoice = None
try:
    from actions.terminal_agent    import terminal_agent
except ImportError:
    terminal_agent = None
try:
    from actions.native_ui         import native_ui
except ImportError:
    native_ui = None
try:
    from actions.accessibility          import accessibility, eye_tracking, micro_movement, task_simplify, routine_gamify
except ImportError:
    accessibility = None
    eye_tracking = None
    micro_movement = None
    task_simplify = None
    routine_gamify = None
try:
    from actions.accessibility_overlay  import accessibility_overlay
except ImportError:
    accessibility_overlay = None
try:
    from actions.morning_brief     import morning_brief, already_briefed_today, mark_briefed
except ImportError:
    morning_brief = None; already_briefed_today = None; mark_briefed = None
try:
    from actions.vision_guardian   import vision_guardian, start as _start_vision_guardian
except ImportError:
    vision_guardian = None; _start_vision_guardian = None
try:
    from actions.obs_control import obs_control
except ImportError:
    obs_control = None
try:
    from actions.recall_memory import recall_memory
except ImportError:
    recall_memory = None
try:
    from actions.ntfy_notify import ntfy_notify
except ImportError:
    ntfy_notify = None
try:
    from actions.openrouter_agent  import openrouter_agent
except ImportError:
    openrouter_agent = None
try:
    from actions.self_agent import self_agent, SelfAgent, _agent_instance as _nia_agent_instance
    _nia_agent_instance = None
except ImportError:
    self_agent = None; _nia_agent_instance = None



def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LOG_PATH        = BASE_DIR / "jarvis.log"

# ── Redirect output to log file (pythonw.exe has no console) ─
try:
    import io as _io
    # ── Log rotation: rotate jarvis.log at startup if it exceeds the limit ──
    _LOG_MAX_BYTES = 5 * 1024 * 1024   # 5 MB antes de rotar
    _LOG_BACKUPS   = 3                 # jarvis.log.1 .. jarvis.log.3
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > _LOG_MAX_BYTES:
            for _i in range(_LOG_BACKUPS, 1, -1):
                _src = LOG_PATH.with_suffix(f".log.{_i - 1}")
                _dst = LOG_PATH.with_suffix(f".log.{_i}")
                if _src.exists():
                    _dst.write_bytes(_src.read_bytes())
                    _src.unlink(missing_ok=True)
            LOG_PATH.rename(LOG_PATH.with_suffix(".log.1"))
            print(f"[JARVIS] ♻️ jarvis.log excedió {_LOG_MAX_BYTES//1024//1024}MB — rotado a jarvis.log.1")
    except Exception as _logerr:
        print(f"[JARVIS] Rotación de log falló: {_logerr}")
    _log_fh = open(LOG_PATH, "w", encoding="utf-8", buffering=1)

    class _TeeStream:
        def __init__(self, *streams):
            self._streams = [s for s in streams if s is not None]
        def write(self, data):
            for s in self._streams:
                try: s.write(data)
                except Exception: pass
        def flush(self):
            for s in self._streams:
                try: s.flush()
                except Exception: pass
        @property
        def encoding(self): return "utf-8"
        def fileno(self): raise _io.UnsupportedOperation("fileno")

    sys.stdout = _TeeStream(sys.stdout, _log_fh)
    sys.stderr = _TeeStream(sys.stderr, _log_fh)
except Exception:
    pass

# ── Suppress console windows from all child subprocesses ─────────────────────
# Disabled global Popen patch to allow interactive GUI applications (cmd, notepad, etc.) to show on screen.
# Background CLI tasks already use CREATE_NO_WINDOW explicitly in actions/terminal_agent.py.

LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-latest"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 256      # 16ms chunks — mic input (keep small for low latency)
PLAY_CHUNK_SIZE     = 480      # 20ms chunks — playback (smaller = lower latency)

_cached_api_key: str | None = None

def _get_api_key() -> str:
    global _cached_api_key
    if _cached_api_key:
        return _cached_api_key
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        _cached_api_key = json.load(f)["gemini_api_key"]
    return _cached_api_key


# ── Wake-word (Nia/JARVIS) — frases para despertar de la suspensión ──────────
_WAKE_RE = re.compile(
    r"\b(jarvis|nia)\b"
    r"|\b(despierta|despiertate|despiértate|despertar|despertate)\b"
    r"|\b(escuchame|escúchame)\b"
    r"|\b(oye|hola|hey|ei)\s+(nia|jarvis)\b"
    r"|\b(wake\s*up)\b",
    re.IGNORECASE,
)


def _wake_word_hit(text: str):
    """Devuelve la frase de despertar encontrada o None. Uso para texto y resultados finales."""
    m = _WAKE_RE.search(text or "")
    return m.group(0) if m else None


def _wake_word_recent(text: str):
    """Como _wake_word_hit pero exige que la frase se haya dicho recientemente
    (evita falsos positivos con hipótesis parciales viejas del reconocedor)."""
    m = _WAKE_RE.search(text or "")
    if not m:
        return None
    if len(text) - m.end() <= 14:
        return m.group(0)
    return None


JARVIS_VOICES = {
    "Aoede":  ("Femenina", "Cálida y sofisticada — ideal para asistente IA"),
    "Kore":   ("Femenina", "Suave y precisa"),
    "Leda":   ("Femenina", "Natural y fluida"),
    "Zephyr": ("Femenina", "Dinámica y expresiva"),
    "Charon": ("Masculina", "Profunda y seria — voz original de Nia"),
    "Puck":   ("Masculina", "Ágil y versátil"),
    "Fenrir": ("Masculina", "Grave y autoritaria"),
    "Orus":   ("Masculina", "Clásica y equilibrada"),
}

def _get_jarvis_voice() -> str:
    try:
        cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        return cfg.get("jarvis_voice", "Aoede")
    except Exception:
        return "Aoede"


def _load_system_prompt() -> str:
    try:
        prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
        try:
            cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            user_name = cfg.get("user_name", "Señor").strip()
            if user_name:
                prompt_text += f"\n\n## PERSONALIZACIÓN DEL USUARIO\nEl nombre del usuario es '{user_name}'. Dirígete a él como '{user_name}' (o variantes cortas respetuosas como 'señor {user_name}') de manera leal y natural en cada interacción, a menos que él te pida explícitamente cambiar su nombre."
        except Exception:
            pass
        return prompt_text
    except Exception:
        return (
            "You are Nia, a premium AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "camera_bus",
        "description": (
            "Controla el subsistema de pilotaje y navegación gestual por cámara de Nia. "
            "Permite activar, desactivar o alternar el control gestual del mouse usando la webcam en segundo plano."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "enable (activar/conectar cámara gestual) | disable (desactivar/apagar cámara gestual) | toggle (alternar estado)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "jarvis_ui_control",
        "description": (
            "Control total sobre la ventana principal y los widgets de la interfaz de Nia. "
            "Permite minimizar/restaurar la ventana principal, o abrir, cerrar, alternar la visibilidad de cualquier widget del dashboard.\n"
            "Widgets disponibles: weather (clima), spotify (música), system (sistema), "
            "notes (notas), todo (tareas), files (archivos recientes)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "minimize (minimizar ventana) | restore (restaurar ventana) | show (mostrar widget) | hide (ocultar widget) | hide_all (ocultar todos los widgets) | toggle (alternar widget)"
                },
                "widget": {
                    "type": "STRING",
                    "description": "Nombre del widget (solo para show/hide/toggle): weather | spotify | system | notes | todo | files"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "open_app",
        "description": (
            "Opens ANY application installed on this Linux computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it. "
            "Busca en TODOS los lugares: PATH del sistema, archivos .desktop de todas las apps instaladas, "
            "Flatpaks, AppImages, y carpetas comunes. "
            "Si querés abrir una app de archivos (nautilus/dolphin/thunar) en una carpeta específica, "
            "pasá el path de la carpeta. Ej: open_app(app_name='archivos', path='~/Descargas')"
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Nombre de la aplicación (ej: 'WhatsApp', 'Chrome', 'Spotify', 'archivos', 'firefox', cualquier app instalada)"
                },
                "path": {
                    "type": "STRING",
                    "description": "Ruta de carpeta para abrir en el explorador de archivos (ej: '~/Descargas', '/home/usuario/Documentos'). Solo aplica para gestores de archivos."
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information and returns numbered results with URLs. Después de buscar, podés abrir cualquier resultado con browser_control(action='open_result', index=N).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"},
                "max_results": {"type": "INTEGER", "description": "Max results (default: 8)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "whatsapp",
        "description": (
            "Integración completa con WhatsApp. "
            "SIEMPRE usar para CUALQUIER pedido de WhatsApp: enviar mensajes, "
            "enviar imágenes/archivos, leer conversaciones, ver mensajes sin leer, "
            "guardar/listar contactos con su número de teléfono. "
            "Para enviar, primero verificar si el contacto está guardado con su teléfono. "
            "Si no está, pedir el número al usuario o usar add_contact primero."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "send | send_image | read | unread | add_contact | list_contacts | delete_contact"},
                "receiver":  {"type": "STRING",  "description": "Nombre del contacto o número de teléfono con código de país (ej: 5491155551234)"},
                "message":   {"type": "STRING",  "description": "Texto del mensaje a enviar"},
                "image_path":{"type": "STRING",  "description": "Ruta de la imagen para send_image"},
                "caption":   {"type": "STRING",  "description": "Descripción de la imagen (opcional)"},
                "count":     {"type": "INTEGER", "description": "Cantidad de mensajes a leer (default: 10)"},
                "name":      {"type": "STRING",  "description": "Nombre del contacto para add_contact/delete_contact"},
                "phone":     {"type": "STRING",  "description": "Número de teléfono con código de país (ej: 5491155551234) para add_contact"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via Telegram, Discord, Signal or other messaging platform. For WhatsApp, use the 'whatsapp' tool instead.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: Telegram, Discord, Signal, Messenger (NOT WhatsApp — use whatsapp tool)"}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Reproduce y controla videos de YouTube. "
            "Usa action='play' con 'query' para buscar y reproducir el primer resultado. "
            "Usa action='play_in_tab' con 'query' para reproducir en la MISMA pestaña (sin abrir nueva). "
            "Usa action='search' para solo mostrar resultados de búsqueda. "
            "Usa action='pause' / 'resume' / 'toggle' / 'next' / 'previous' / 'stop' / 'mute' / 'volume' "
            "para controlar la reproducción (sin query). "
            "Soporta workspace=N para abrir el video en un escritorio específico."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | play_in_tab | search | pause | resume | toggle | next | previous | stop | mute | volume"},
                "query":  {"type": "STRING", "description": "Búsqueda del video a reproducir"},
                "url":    {"type": "STRING", "description": "URL directa del video (opcional, sobreescribe query)"},
                "value":  {"type": "STRING", "description": "Valor para action=volume (0-100)"},
                "workspace": {"type": "INTEGER", "description": "Número de escritorio donde abrir el video (ej: 4)"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly. "
            "Si querés ver el contenido de OTRO escritorio (ej: 'que hay en el escritorio 1'), "
            "pasá workspace=1 y automáticamente cambio a ese, capturo, y vuelvo."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"},
                "workspace": {"type": "INTEGER", "description": "Número de escritorio a capturar (opcional). Si se especifica, cambio temporalmente a ese escritorio, capturo, y regreso al actual."}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task. "
            "IMPORTANT: to type text, MUST use action='type' and value='<text>'. "
            "IMPORTANT: to minimize windows, MUST use action='minimize'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Abre URLs o búsquedas en el navegador. "
            "POR DEFECTO abre como pestaña en la ventana existente del navegador. "
            "Solo abre ventana NUEVA si pasás new_window=true explícitamente. "
            "Usá workspace=N para abrir en un escritorio específico (Nia cambia al escritorio, "
            "abre el navegador allí, y navega). "
            "Acciones: go_to (navegar a URL), search (buscar en Google), new_window (forzar nueva ventana), "
            "close_tab (cerrar pestaña actual), open_result (abrir resultado de web_search por índice), "
            "new_tab (abrir nueva pestaña en blanco). "
            "IMPORTANTE: Para buscar y reproducir videos/música en YouTube, NO uses web_search + browser_control. "
            "Usá youtube_video(action='play', query='...') que busca directo en YouTube y abre solo una pestaña."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | new_window | close_tab | open_result | new_tab"},
                "url":         {"type": "STRING", "description": "URL para go_to o new_window"},
                "query":       {"type": "STRING", "description": "Término de búsqueda para search"},
                "index":       {"type": "INTEGER", "description": "Número del resultado a abrir (para open_result). Ej: 1=primer link, 2=segundo, etc."},
                "new_window":  {"type": "BOOLEAN", "description": "true para abrir en ventana NUEVA del navegador (default: false = abre como pestaña)"},
                "workspace":   {"type": "INTEGER", "description": "Número de escritorio donde abrir (ej: 4). Nia cambia al escritorio y abre ahí."},
            },
            "required": ["action"]
        }
    },
    {
        "name": "visual_click",
        "description": "Utiliza Visión Espacial para encontrar las coordenadas matemáticas de un elemento en la pantalla y hacer clic en él físicamente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element_description": {"type": "STRING", "description": "Descripción clara de lo que quieres cliquear (ej: 'botón de enviar', 'ícono de la papelera')."}
            },
            "required": ["element_description"]
        }
    },
    {
        "name": "screen_click",
        "description": "Usa visión para encontrar un elemento en pantalla y hacer clic en él. Descripción textual del elemento (ej: 'botón de enviar', 'ícono de la papelera', 'enlace que dice Leer más').",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "element_description": {"type": "STRING", "description": "Descripción exacta del elemento a cliquear"}
            },
            "required": ["element_description"]
        }
    },
    {
        "name": "mouse_control",
        "description": "Controla físicamente el cursor del mouse: mover, clic, doble clic, clic derecho, arrastrar, scrollear. Como si Nia usara el mouse como una persona.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "move | click | double_click | right_click | drag | scroll | hscroll | position"},
                "x": {"type": "INTEGER", "description": "Coordenada X en píxeles"},
                "y": {"type": "INTEGER", "description": "Coordenada Y en píxeles"},
                "x2": {"type": "INTEGER", "description": "X destino para drag"},
                "y2": {"type": "INTEGER", "description": "Y destino para drag"},
                "button": {"type": "STRING", "description": "left (default) | right | middle"},
                "amount": {"type": "INTEGER", "description": "Cantidad de scroll (positivo=arriba, negativo=abajo)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "keyboard_control",
        "description": "Escribe texto y presiona teclas en el sistema como si Nia usara un teclado físico. type para escribir texto, press para una tecla, combo para combinaciones (ctrl+c, alt+tab).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "type | press | combo | enter | tab | escape | backspace | delete | space"},
                "text": {"type": "STRING", "description": "Texto a escribir (para action=type)"},
                "key": {"type": "STRING", "description": "Tecla individual (para action=press)"},
                "combo": {"type": "STRING", "description": "Combinación con + (ej: ctrl+c, alt+tab, ctrl+shift+esc)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "sleep_mode",
        "description": "Entra en modo suspensión. Desactiva el micrófono para la IA hasta que el usuario diga 'Oye Nia' o 'Nia' localmente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "desktop_kb",
        "description": (
            "Controla el escritorio (ventanas, apps, workspaces) con TECLADO. "
            "Usa action='windows' para listar ventanas abiertas. "
            "Usa action='switch' con 'app_class' para enfocar una app (brave-browser, Alacritty, spotify, code, etc). "
            "Usa action='workspace' con 'num' para ir a un escritorio (1-9). "
            "Usa action='close' para cerrar la ventana activa. "
            "Usa action='open' con 'app' para abrir una app (brave, spotify, code, alacritty, obsidian, etc). "
            "Usa action='fullscreen' / 'maximize' para cambiar el estado de la ventana. "
            "Usa action='move_ws' con 'num' para mover la ventana activa a otro escritorio."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "windows | switch | workspace | close | open | fullscreen | maximize | move_ws | active"},
                "app_class": {"type": "STRING", "description": "Clase de ventana para switch (obtener con action=windows)"},
                "app": {"type": "STRING", "description": "Nombre de app para open (brave, spotify, code, alacritty, obsidian)"},
                "num": {"type": "INTEGER", "description": "Número de workspace (1-9)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "mouse_kb",
        "description": (
            "Controla el MOUSE con movimiento NATURAL (curva bezier, aceleración suave). "
            "Usa action='move' con 'x' e 'y' para mover el cursor suavemente a una coordenada. "
            "Usa action='click' para hacer click izquierdo donde está el cursor. "
            "Usa action='move_click' con 'x', 'y' para mover y clickear. "
            "Usa action='right_click' para click derecho. "
            "Usa action='double_click' para doble click. "
            "Usa action='scroll' con 'amount' (positivo=abajo, negativo=arriba) y opcional 'x','y'. "
            "Usa action='drag' con x1,y1 a x2,y2. "
            "Usa action='pos' para obtener la posición actual del cursor. "
            "IMPORTANTE: es más rápido que Tab+Enter para cliquear enlaces. "
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "move | click | move_click | right_click | double_click | scroll | drag | pos"},
                "x": {"type": "INTEGER", "description": "Coordenada X"},
                "y": {"type": "INTEGER", "description": "Coordenada Y"},
                "x1": {"type": "INTEGER", "description": "X inicial para drag"},
                "y1": {"type": "INTEGER", "description": "Y inicial para drag"},
                "x2": {"type": "INTEGER", "description": "X final para drag"},
                "y2": {"type": "INTEGER", "description": "Y final para drag"},
                "amount": {"type": "INTEGER", "description": "Cantidad de scroll (positivo=abajo)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_kb",
        "description": (
            "CONTROL de VIDEOJUEGOS (Minecraft, etc.). "
            "Acciones: look(dx, dy) mirar alrededor, move(direction, duration) caminar, "
            "attack(duration) minar/golpear, use() click derecho, jump() saltar, "
            "sneak(duration) agacharse, sprint(duration) correr, inventory() inventario, "
            "slot(n) 1-9, drop() soltar item, mine(direction, duration) minar, "
            "place() colocar bloque, press(key) tecla, hold(key), release(key), esc()."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "look | move | attack | use | jump | sneak | sprint | inventory | slot | drop | mine | place | press | hold | release | click | esc | status"},
                "dx":        {"type": "INTEGER", "description": "Mouse X movement (neg=left, pos=right)"},
                "dy":        {"type": "INTEGER", "description": "Mouse Y movement (neg=up, pos=down)"},
                "direction": {"type": "STRING", "description": "forward | back | left | right"},
                "duration":  {"type": "NUMBER", "description": "Seconds to hold action"},
                "key":       {"type": "STRING", "description": "Key name: w, a, s, d, space, shift, ctrl, e, q, 1-9, etc"},
                "slot":      {"type": "INTEGER", "description": "Hotbar slot 1-9"},
                "button":    {"type": "STRING", "description": "left | right | middle"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": (
            "Manages files and folders: list, create, delete (to recycle bin), move, copy, rename, read, write, find, disk usage. "
            "Use action=find with name + path to locate files by name in any directory (desktop, downloads, etc.). "
            "After finding a file, pass the returned path to another tool to act on it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete (mueve a papelera) | move | copy | rename | read | write | edit | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
                "old_text":    {"type": "STRING",  "description": "Texto a reemplazar (para edit)"},
                "new_text":    {"type": "STRING",  "description": "Nuevo texto o contenido (para edit)"},
                "mode":        {"type": "STRING",  "description": "replace | append | prepend | overwrite (para edit)"},
                "confirm":     {"type": "BOOLEAN", "description": "true para confirmar eliminaciones"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": (
            "Controla el escritorio: cambiar de workspace, listar ventanas, enfocar/cerrar/mover ventanas, wallpaper. "
            "Usá 'list_windows' para ver TODAS las ventanas en TODOS los escritorios. "
            "Usá 'context' para ver tu escritorio ACTUAL: qué escritorio está activo, qué ventana está enfocada, "
            "qué ventanas hay en este escritorio, y un resumen de los demás. "
            "Usá 'focus_window' con class o title para traer una ventana al foco. "
            "Usá 'move_window' con class/title + workspace para mover una ventana a otro escritorio. "
            "Usá 'pin_window' para fijar una ventana (visible en todos los escritorios). "
            "Usá 'fullscreen' para maximizar la ventana activa a pantalla completa. "
            "Usá 'close_window' o 'close' con class o title para cerrar ventanas (sin parámetros cierra la activa). "
            "Secuencia típica: 1) context para ver dónde estás 2) go_to al escritorio 3) open_app 4) browser_control. "
            "When the user says to use a file from a directory (e.g. 'el archivo X del escritorio'), "
            "use search_name + search_path to auto-find the file before applying the action."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | list_windows | windows | context | task | go_to | switch | focus_window | move_window | pin_window | fullscreen | close_window | close"},
                "path":        {"type": "STRING", "description": "Image path for wallpaper"},
                "url":         {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":        {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":        {"type": "STRING", "description": "Natural language desktop task"},
                "search_name": {"type": "STRING", "description": "Filename to search for in a directory (auto-finds full path)"},
                "search_path": {"type": "STRING", "description": "Directory to search: desktop, downloads, documents, pictures, home (default: desktop)"},
                "workspace":   {"type": "STRING", "description": "Workspace number or name for go_to/switch or move_window"},
                "desktop":     {"type": "STRING", "description": "Alias for workspace (for go_to/switch/move_window)"},
                "class":       {"type": "STRING", "description": "Window class to focus/close/move/pin (ej: brave-browser, Alacritty, code)"},
                "title":       {"type": "STRING", "description": "Text to match in window title for focus/close/move/pin"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "[NO DISPONIBLE] NO DISPONIBLE — flight_finder no está implementado todavía. Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
            "required": []
        }
    },
    {
        "name": "youtube_kb",
        "description": (
            "Navega YouTube solo con TECLADO (Tab+Enter). "
            "Usa action='open_video' para abrir un video recomendado (Tab 50x, Enter cada 10). "
            "Usa action='search' con 'query' para buscar en YouTube. "
            "Usa action='play_pause' para pausar/reanudar. "
            "IMPORTANTE: mouse clicks virtuales NO funcionan en este sistema (Wayland). "
            "Siempre usar esta herramienta para navegar YouTube en vez de browser_control."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "open_video | search | play_pause | mute | fullscreen | search_and_open | seek_forward | seek_backward"},
                "query":  {"type": "STRING",  "description": "Búsqueda (para action=search o search_and_open)"},
                "seconds": {"type": "INTEGER", "description": "Segundos para seek_forward/seek_backward (default: 10)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "web_kb",
        "description": (
            "Navegación web completa con TECLADO (Ctrl+L, Ctrl+T, Tab, Enter). "
            "Usa action='go_to' con 'url' para navegar. "
            "Usa action='google' con 'text' para buscar. "
            "Usa action='youtube_search' con 'text' para buscar en YouTube. "
            "Usa action='new_tab' / 'close_tab' / 'switch_tab' (n). "
            "Usa action='go_back' / 'go_forward' / 'reload'. "
            "Usa action='scroll' con 'direction' y 'times'. "
            "Usa action='navigate' con 'tab_presses' y 'enter_every' para cliquear enlaces. "
            "Usa action='type' con 'text' para escribir. "
            "Usa action='tab' con 'times'. "
            "Usa action='enter'. "
            "Usa action='find' con 'text' para buscar en página. "
            "Usa action='full_browse' para abrir pestaña y navegar. "
            "Para YouTube, usar LA HERRAMIENTA youtube_kb específica."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "go_to | google | youtube_search | new_tab | close_tab | reopen_tab | switch_tab | go_back | go_forward | reload | scroll | navigate | type | tab | enter | find | full_browse | title"},
                "url":  {"type": "STRING", "description": "URL para go_to"},
                "text": {"type": "STRING", "description": "Texto para google/youtube_search/type/find"},
                "times": {"type": "INTEGER", "description": "Veces para tab/scroll"},
                "n": {"type": "INTEGER", "description": "Número de pestaña para switch_tab (1-9)"},
                "direction": {"type": "STRING", "description": "down | up (para scroll)"},
                "tab_presses": {"type": "INTEGER", "description": "Total de tabs para navigate"},
                "enter_every": {"type": "INTEGER", "description": "Cada cuántos tabs presionar Enter"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "google_calendar",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — google_calendar no está implementado todavía. "             "Manages the user's Google Calendar: create, list, edit, or delete events. "
            "Use for ANY request about calendar events, appointments, reminders with dates, "
            "scheduling meetings, or checking what's coming up. "
            "ALWAYS call this tool for calendar requests — never simulate. "
            "For 'list': shows upcoming events. "
            "For 'create': needs summary and start (end defaults to +1h). "
            "For 'edit'/'delete': needs event_id (get it from 'list' first)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "list | create | edit | delete"},
                "summary":     {"type": "STRING",  "description": "Event title/name"},
                "start":       {"type": "STRING",  "description": "Start date/time: ISO, YYYY-MM-DD HH:MM, or DD/MM/YYYY HH:MM"},
                "end":         {"type": "STRING",  "description": "End date/time (optional — defaults to start + 1 hour)"},
                "description": {"type": "STRING",  "description": "Event notes or description"},
                "location":    {"type": "STRING",  "description": "Event location"},
                "event_id":    {"type": "STRING",  "description": "Event ID (first 8 chars from list) for edit/delete"},
                "days_ahead":  {"type": "INTEGER", "description": "Days to look ahead for list (default: 7)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "spotify_control",
        "description": (
            "Control de Spotify: play, pause, next, previous, volume, status. "
            "Con credenciales conectadas puede buscar y reproducir canciones, artistas o playlists específicas por la Web API. "
            "status/connected: consulta si Spotify está autenticado. "
            "Usá esta herramienta para CUALQUIER pedido relacionado con Spotify o música."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | pause | next | previous | volume | current | devices | toggle | status"},
                "query":  {"type": "STRING", "description": "Canción, artista o playlist a buscar/reproducir"},
                "type":   {"type": "STRING", "description": "track | album | playlist | artist (default: track)"},
                "value":  {"type": "STRING", "description": "Volumen 0-100 (para action=volume)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "daily_summary",
        "description": (
            "Resumen diario de Nia. Compila lo más relevante del día (resúmenes de conversaciones, "
            "hechos de memoria y notas de Obsidian tocadas hoy) y lo envía al celular del usuario vía ntfy. "
            "Acciones: generate (generar y enviar ahora), preview (ver sin enviar), "
            "schedule (programar la hora diaria, p.ej. hour=7 minute=30). "
            "Usar cuando el usuario pida 'resumen del día', 'qué pasó hoy' o para programar el reporte diario."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "generate | preview | schedule"},
                "hour":   {"type": "INTEGER", "description": "Hora (0-23) para action=schedule"},
                "minute": {"type": "INTEGER", "description": "Minuto (0-59) para action=schedule"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "tts_local",
        "description": (
            "Voz local de respaldo (Piper, 100% offline, sin internet). "
            "Habla en voz alta por el altavoz de Nia un texto dado. "
            "Usar cuando el usuario pida hablar sin conexión, o cuando la voz en la nube no esté disponible."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "text": {"type": "STRING", "description": "Texto a decir en voz alta"},
            },
            "required": ["text"]
        }
    },
    {
        "name": "usage_stats",
        "description": (
            "Estadísticas de uso de las herramientas de Nia. "
            "Reporta cuántas veces se usó cada herramienta (hoy, últimos 7 días o total histórico). "
            "Usar cuando el usuario pregunte 'qué herramientas uso más', 'cuánto usaste tal cosa' o quiera ver actividad."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "today | week | total | reset"},
                "limit":  {"type": "INTEGER", "description": "Cuántas herramientas incluir (default 15)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "rgb_control",
        "description": (
            "Controla las luces RGB de periféricos y componentes de la PC (teclado, mouse, GPU, RAM, etc.). "
            "Requiere OpenRGB corriendo con servidor SDK activado. "
            "Usar para: cambiar color, apagar, brillo, efectos, arco iris."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "set_color | off | brightness | effect | rainbow | list"},
                "color":      {"type": "STRING", "description": "Color: nombre (rojo, azul, verde, blanco…) o hex #RRGGBB"},
                "brightness": {"type": "INTEGER", "description": "Brillo 0-100 (default: 100)"},
                "device":     {"type": "STRING", "description": "Filtro por nombre de dispositivo (opcional, aplica a todos si se omite)"},
                "effect":     {"type": "STRING", "description": "Nombre del efecto para la acción effect"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "scheduler",
        "description": (
            "Crea, lista, elimina o ejecuta automatizaciones programadas (tareas recurrentes). "
            "Ejemplos: backup diario, notificaciones, scripts automáticos. "
            "Usar para CUALQUIER pedido de 'todos los días a las X', 'cada semana', 'automatizar'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":           {"type": "STRING",  "description": "list | create | delete | enable | disable | run_now"},
                "name":             {"type": "STRING",  "description": "Nombre descriptivo de la tarea"},
                "frequency":        {"type": "STRING",  "description": "daily | weekly | interval | once"},
                "hour":             {"type": "INTEGER", "description": "Hora de ejecución (0-23)"},
                "minute":           {"type": "INTEGER", "description": "Minuto de ejecución (0-59)"},
                "weekday":          {"type": "STRING",  "description": "Día de la semana para frequency=weekly"},
                "interval_minutes": {"type": "INTEGER", "description": "Intervalo en minutos para frequency=interval"},
                "task_action":      {"type": "STRING",  "description": "backup | file_controller | notify | custom_script | browser_control"},
                "task_parameters":  {"type": "OBJECT",  "description": "Parámetros de la tarea (source, destination para backup, etc.)"},
                "task_id":          {"type": "STRING",  "description": "ID de la tarea (primeros 6 chars) para delete/enable/disable/run_now"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "google_drive",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — google_drive no está implementado todavía. "             "Gestiona Google Drive: listar archivos, buscar, subir, descargar, crear carpetas, eliminar, compartir. "
            "SIEMPRE usar para cualquier pedido sobre Google Drive."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | search | upload | download | create_folder | delete | share | info"},
                "folder_id":   {"type": "STRING", "description": "ID de la carpeta (default: root)"},
                "file_id":     {"type": "STRING", "description": "ID del archivo para download/delete/share/info"},
                "path":        {"type": "STRING", "description": "Ruta local para upload"},
                "name":        {"type": "STRING", "description": "Nombre de la nueva carpeta"},
                "query":       {"type": "STRING", "description": "Término de búsqueda"},
                "destination": {"type": "STRING", "description": "Carpeta local de destino para download"},
                "email":       {"type": "STRING", "description": "Email para compartir"},
                "role":        {"type": "STRING", "description": "reader | writer | commenter"},
                "confirm":     {"type": "BOOLEAN", "description": "true para confirmar eliminación"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "gmail_control",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — gmail_control no está implementado todavía. "             "Gestiona Gmail: leer bandeja, leer correo, enviar, responder, buscar, archivar, eliminar. "
            "SIEMPRE usar para cualquier pedido sobre correo electrónico o Gmail."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING",  "description": "inbox | read | send | reply | search | archive | delete | mark_read | labels"},
                "count":      {"type": "INTEGER", "description": "Cantidad de correos a listar/buscar (default: 5)"},
                "message_id": {"type": "STRING",  "description": "ID del mensaje para read/reply/archive/delete/mark_read"},
                "to":         {"type": "STRING",  "description": "Destinatario para send"},
                "subject":    {"type": "STRING",  "description": "Asunto para send"},
                "body":       {"type": "STRING",  "description": "Cuerpo del correo para send/reply"},
                "query":      {"type": "STRING",  "description": "Búsqueda Gmail para search (ej: 'from:juan', 'subject:factura')"},
                "confirm":    {"type": "BOOLEAN", "description": "true para confirmar eliminación"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "google_maps",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — google_maps no está implementado todavía. "             "Muestra rutas de navegación y mapas interactivos. "
            "Usar para: cómo llegar a un lugar, cuánto tarda, indicaciones paso a paso, "
            "buscar una dirección en el mapa. Abre mapa Nia en Chrome con la ruta marcada. "
            "SIEMPRE llamar para cualquier pedido de navegación, rutas o mapas."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "directions | search"},
                "origin":      {"type": "STRING", "description": "Punto de partida (dirección, ciudad, lugar)"},
                "destination": {"type": "STRING", "description": "Destino (dirección, ciudad, lugar)"},
                "mode":        {"type": "STRING", "description": "car (auto) | walk (caminando) | bike (bicicleta). Default: car"},
                "query":       {"type": "STRING", "description": "Lugar a buscar en el mapa (para action=search)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "rules_engine",
        "description": (
            "Motor de automatizaciones y alertas inteligentes. "
            "USAR SIEMPRE cuando el usuario pida: 'cuando diga X hacé Y', 'cada vez que diga X', "
            "'si digo X abrí/poné/hacé Y', 'quiero que cuando diga X...'. "
            "Soporta: phrase triggers (frase → acción), time triggers (hora → acción), alertas. "
            "Listar, crear, eliminar, habilitar/deshabilitar automaciones. "
            "CONDITION types: phrase (frase del usuario), time (hora del día), file_exists, always. "
            "ACTION types: open_app, spotify_play, browser, smart_home, composite (múltiples), notify, speak, run_script."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING", "description": "list | list_phrases | create | delete | enable | disable | trigger | alert"},
                "name":       {"type": "STRING", "description": "Nombre de la automatización"},
                "rule_id":    {"type": "STRING", "description": "ID de la regla para delete/enable/disable/trigger"},
                "condition":  {
                    "type": "OBJECT",
                    "description": (
                        "Condición. phrase: {type:phrase, trigger:'texto exacto', match:contains|exact|startswith}. "
                        "time: {type:time, hour:8, minute:0, days:[monday,...]}. "
                        "file_exists: {type:file_exists, path:'...'}. always: {type:always}"
                    )
                },
                "action_def": {
                    "type": "OBJECT",
                    "description": (
                        "Acción a ejecutar. "
                        "open_app: {type:open_app, app_name:'Spotify'}. "
                        "spotify_play: {type:spotify_play, query:'Back in Black AC/DC'}. "
                        "browser: {type:browser, url:'https://...'}. "
                        "smart_home: {type:smart_home, device:'living', action:'on'}. "
                        "composite: {type:composite, actions:[{...},{...}]}. "
                        "notify: {type:notify, message:'...'}. speak: {type:speak, message:'...'}. "
                        "run_script: {type:run_script, command:'...'}."
                    )
                },
                "message":    {"type": "STRING", "description": "Mensaje para action=alert"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "user_profile",
        "description": (
            "Perfil dinámico del usuario — hábitos, preferencias, historial de uso. "
            "Ver perfil, configurar preferencias, ver hábitos aprendidos, guardar notas personales. "
            "Nia aprende automáticamente los patrones del usuario."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "view | set_preference | set_name | add_note | notes | habits | reset"},
                "key":    {"type": "STRING", "description": "Clave de preferencia (ej: idioma, tema, ciudad)"},
                "value":  {"type": "STRING", "description": "Valor de la preferencia"},
                "name":   {"type": "STRING", "description": "Nombre del usuario"},
                "note":   {"type": "STRING", "description": "Nota personal a guardar"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "goals",
        "description": (
            "Sistema de objetivos persistentes a largo plazo. "
            "Crear metas, trackear progreso, marcar pasos completados. "
            "Usar para: metas personales, proyectos, hábitos, objetivos con deadline. "
            "SIEMPRE usar para pedidos de 'quiero lograr X', 'mi objetivo es', 'meta de'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "list | create | update_progress | complete | complete_step | add_step | delete | detail"},
                "goal_id":     {"type": "STRING",  "description": "ID del objetivo para update/complete/delete/detail"},
                "title":       {"type": "STRING",  "description": "Título del objetivo"},
                "description": {"type": "STRING",  "description": "Descripción detallada"},
                "deadline":    {"type": "STRING",  "description": "Fecha límite ISO (YYYY-MM-DD)"},
                "progress":    {"type": "INTEGER", "description": "Progreso 0-100"},
                "steps":       {"type": "ARRAY",   "items": {"type": "STRING"}, "description": "Lista de pasos del objetivo"},
                "step":        {"type": "STRING",  "description": "Texto del nuevo paso (add_step)"},
                "step_index":  {"type": "INTEGER", "description": "Índice del paso a completar (0-based)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "git_control",
        "description": (
            "Control de Git: consultar estado, ver cambios, historial, "
            "hacer commits y agregar archivos al staging. "
            "Antes de commitear, mostrar el diff y pedir confirmación. "
            "Usar para: '¿cómo está el repo?', 'mostrame qué cambió', "
            "'commiteá esto', 'agregá los archivos y hacé commit'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "status | diff | diff_staged | log | commit | branch | add"},
                "message":     {"type": "STRING",  "description": "Mensaje del commit (requerido para commit)"},
                "files":       {"type": "STRING",  "description": "Archivos separados por coma para add"},
                "add_all":     {"type": "STRING",  "description": "Agregar todos los archivos (true/false, default true)"},
                "max_results": {"type": "INTEGER", "description": "Cantidad de entradas para log (default 10)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_search",
        "description": (
            "Busca archivos y contenido en código fuente de proyectos. "
            "grep/search: busca por regex en el contenido. "
            "glob/files: busca por patrón de nombre de archivo. "
            "list/ls: lista archivos de un directorio. "
            "Usar para: 'buscá donde se define X', 'qué archivos son .py', "
            "'mostrame la estructura del proyecto', 'encontrá todas las referencias a Y'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "grep/search | glob/files | list/ls"},
                "pattern":     {"type": "STRING",  "description": "Regex para grep, o patrón de nombre para glob (*.py)"},
                "path":        {"type": "STRING",  "description": "Directorio o archivo a buscar"},
                "include":     {"type": "STRING",  "description": "Filtro por extensión (*.py, *.js)"},
                "max_results": {"type": "INTEGER", "description": "Máximo de resultados (5-50, default 30)"},
                "ignore_case": {"type": "STRING",  "description": "Ignorar mayúsculas (true/false)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_editor",
        "description": (
            "Lee y modifica archivos de código fuente. "
            "Lectura: info (metadatos), read/leer, segment/lines. "
            "Escritura: write/create (sobreescribir), edit/replace (buscar-reemplazar), "
            "append/agregar (al final). "
            "Toda escritura soporta dry_run=true para vista previa sin aplicar cambios. "
            "Usar para: 'leé este archivo', 'escribí este código en X', "
            "'reemplazá Y por Z en el archivo', 'agregá esto al final'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",  "description": "info | read/leer | segment/lines | write/create | edit/replace | append/agregar"},
                "path":    {"type": "STRING",  "description": "Ruta del archivo"},
                "content": {"type": "STRING",  "description": "Contenido para write/create o append"},
                "old_text":{"type": "STRING",  "description": "Texto a buscar para edit/replace"},
                "new_text":{"type": "STRING",  "description": "Texto de reemplazo para edit/replace"},
                "offset":  {"type": "INTEGER", "description": "Línea de inicio para read (default 0)"},
                "limit":   {"type": "INTEGER", "description": "Cantidad de líneas para read (default 500)"},
                "start":   {"type": "INTEGER", "description": "Línea inicio para segment"},
                "end":     {"type": "INTEGER", "description": "Línea fin para segment"},
                "dry_run": {"type": "STRING",  "description": "Vista previa sin aplicar (true/false)"},
            },
            "required": ["action", "path"]
        }
    },
    {
        "name": "shell_exec",
        "description": (
            "Ejecuta comandos del sistema de forma segura. "
            "Comandos seguros (git, ls, python, etc.) se ejecutan directo. "
            "Comandos no whitelisted necesitan force=true. "
            "Comandos peligrosos (rm -rf /, sudo) se bloquean. "
            "Usar para: 'corré python --version', 'listá los archivos', "
            "'mostrame el output de git status'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING",  "description": "Comando a ejecutar"},
                "timeout": {"type": "INTEGER", "description": "Timeout en segundos (default 30)"},
                "cwd":     {"type": "STRING",  "description": "Directorio de trabajo"},
                "force":   {"type": "STRING",  "description": "Forzar ejecución no whitelisted (true/false)"},
            },
            "required": ["command"]
        }
    },
    {
        "name": "project_analyzer",
        "description": (
            "Analiza un proyecto: detecta lenguaje/framework, estructura, "
            "dependencias, entry points y tests. "
            "Usar para: '¿qué tipo de proyecto es este?', "
            "'mostrame la estructura del proyecto', '¿qué dependencias tiene?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Ruta al directorio del proyecto"},
            },
            "required": []
        }
    },
    {
        "name": "skill_manager",
        "description": (
            "Gestiona skills cargables: listar, cargar (leer instrucciones), "
            "crear y eliminar. Los skills son archivos JSON con instrucciones "
            "especializadas para tareas específicas. "
            "Usar para: '¿qué skills tengo?', 'cargá el skill de X', "
            "'creá un skill para hacer Y'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING",  "description": "list | load/cargar | create/crear | delete/eliminar"},
                "name":         {"type": "STRING",  "description": "Nombre del skill"},
                "description":  {"type": "STRING",  "description": "Descripción del skill (para create)"},
                "instructions": {"type": "STRING",  "description": "Instrucciones del skill (para create)"},
                "tags":         {"type": "STRING",  "description": "Tags separados por coma (para create)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "web_fetch",
        "description": (
            "Trae y parsea contenido de cualquier URL. "
            "Devuelve texto limpio de HTML, JSON de APIs, o info de imágenes. "
            "Usar para: 'leé esta página', 'traé el contenido de X', "
            "'¿qué dice este link?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url":        {"type": "STRING",  "description": "URL a fetchear"},
                "max_chars":  {"type": "INTEGER", "description": "Máximo de caracteres (default 15000)"},
                "force_text": {"type": "STRING",  "description": "Forzar parsing como texto (true/false)"},
            },
            "required": ["url"]
        }
    },
    {
        "name": "pdf_reader",
        "description": (
            "Lee archivos PDF: extrae texto, metadata, páginas específicas. "
            "Usar para: 'leé este PDF', '¿qué dice este documento?', "
            "'resumí las primeras 5 páginas'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path":       {"type": "STRING",  "description": "Ruta al PDF"},
                "first_page": {"type": "INTEGER", "description": "Primera página a leer"},
                "last_page":  {"type": "INTEGER", "description": "Última página a leer"},
                "max_chars":  {"type": "INTEGER", "description": "Máximo de caracteres (default 20000)"},
            },
            "required": ["path"]
        }
    },
    {
        "name": "csv_analyzer",
        "description": (
            "Analiza archivos CSV: columnas, tipos, estadísticas, muestras. "
            "Usar para: 'analizá este CSV', '¿cuántas filas tiene?', "
            "'mostrame una muestra', 'filtrá por columna X'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path":          {"type": "STRING",  "description": "Ruta al CSV"},
                "delimiter":     {"type": "STRING",  "description": "Separador (default auto-detect)"},
                "max_rows":      {"type": "INTEGER", "description": "Máximo de filas a leer (default 500)"},
                "show_sample":   {"type": "INTEGER", "description": "Filas de muestra a mostrar (default 10)"},
                "filter_column": {"type": "STRING",  "description": "Columna para filtrar"},
                "filter_value":  {"type": "STRING",  "description": "Valor de filtro"},
            },
            "required": ["path"]
        }
    },
    {
        "name": "image_reader",
        "description": (
            "Lee metadata de imágenes: dimensiones, formato, tamaño, base64. "
            "Puede generar base64 para envío a APIs de visión. "
            "Usar para: '¿qué imagen es esta?', 'dimensiones de X', "
            "'generá el base64 de esta imagen'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path":           {"type": "STRING",  "description": "Ruta a la imagen"},
                "return_b64":     {"type": "STRING",  "description": "Devolver base64 (true/false)"},
                "max_b64_chars":  {"type": "INTEGER", "description": "Máx chars de base64 (default 2000)"},
            },
            "required": ["path"]
        }
    },
    {
        "name": "code_executor",
        "description": (
            "Ejecuta código Python y devuelve stdout/stderr. "
            "Puede ejecutar código inline o un archivo .py. "
            "Usar para: 'corré este código', 'ejecutá este script', "
            "'probá si esto funciona'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code":      {"type": "STRING",  "description": "Código Python a ejecutar"},
                "file_path": {"type": "STRING",  "description": "Ruta a archivo .py a ejecutar"},
                "timeout":   {"type": "INTEGER", "description": "Timeout en segundos (default 30)"},
                "args":      {"type": "STRING",  "description": "Argumentos para el script"},
                "safe_mode": {"type": "STRING",  "description": "Modo seguro con restricciones (default true)"},
            },
            "required": []
        }
    },
    {
        "name": "multi_step_executor",
        "description": (
            "Ejecuta una secuencia de tools encadenadas. "
            "Cada step recibe el output del anterior. "
            "Usar para: 'leé el archivo X, procesalo y escribí el resultado en Y'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "steps":          {"type": "STRING",  "description": "JSON array de steps: [{\"tool\": \"nombre\", \"params\": {}, \"save_as\": \"var\"}]"},
                "stop_on_error":  {"type": "STRING",  "description": "Parar si un step falla (default true)"},
                "max_steps":      {"type": "INTEGER", "description": "Máximo de steps (default 10)"},
            },
            "required": ["steps"]
        }
    },
    {
        "name": "web_crawler",
        "description": (
            "Crawlea un sitio web en tiempo real: descubre links, sigue la "
            "estructura, extrae contenido de múltiples páginas. "
            "A diferencia de web_fetch (una URL), este sigue links y "
            "devuelve contenido de todo el sitio. "
            "Usar para: 'crawleá este sitio', 'explorá todos los links de X', "
            "'¿qué hay en este dominio?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "url":         {"type": "STRING",  "description": "URL inicial para crawlear"},
                "max_pages":   {"type": "INTEGER", "description": "Máximo de páginas (default 20, máx 50)"},
                "max_depth":   {"type": "INTEGER", "description": "Profundidad máxima de links (default 3, máx 5)"},
                "same_domain": {"type": "STRING",  "description": "Quedarse en el mismo dominio (default true)"},
                "max_chars":   {"type": "INTEGER", "description": "Máximo de caracteres totales (default 30000)"},
            },
            "required": ["url"]
        }
    },
    {
        "name": "persistent_context",
        "description": (
            "Guarda y recupera contexto entre sesiones. "
            "Permite a Nia recordar conversaciones previas, decisiones "
            "tomadas, y contexto importante. "
            "Usar para: 'guardá esto para después', '¿qué hablamos ayer?', "
            "'resumí la sesión anterior'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING",  "description": "save/guardar, recall/recuperar, list/listar, summary/resumen, clear/limpiar"},
                "topic":      {"type": "STRING",  "description": "Tema del contexto (para save)"},
                "content":    {"type": "STRING",  "description": "Contenido a guardar (para save)"},
                "importance": {"type": "STRING",  "description": "alta/media/baja (para save)"},
                "keywords":   {"type": "STRING",  "description": "Keywords separadas por coma (para save)"},
                "query":      {"type": "STRING",  "description": "Query de búsqueda (para recall)"},
                "limit":      {"type": "INTEGER", "description": "Máximo de resultados"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "self_improve",
        "description": (
            "Analiza y mejora código propio de Nia. "
            "Detecta problemas, sugiere refactorizaciones, y puede "
            "reescribir funciones. Opera sobre archivos .py del proyecto. "
            "Usar para: 'analizá este archivo', '¿qué mejoras sugerís?', "
            "'mostrá los archivos del proyecto'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",  "description": "analyze/analizar, suggest/sugerir, list_project/proyecto"},
                "path":   {"type": "STRING",  "description": "Ruta al archivo .py a analizar"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "real_vision",
        "description": (
            "Visión real: envía una imagen a Gemini para que la analice. "
            "Puede tomar un archivo de imagen o capturar la pantalla. "
            "Gemini 've' la imagen y la describe/analiza. "
            "Usar para: '¿qué hay en esta imagen?', 'analizá esta captura', "
            "' describí lo que ves en pantalla'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path":      {"type": "STRING",  "description": "Ruta a la imagen"},
                "prompt":    {"type": "STRING",  "description": "Qué buscar/describir en la imagen"},
                "screenshot":{"type": "STRING",  "description": "Capturar pantalla automáticamente (true/false)"},
                "max_size":  {"type": "INTEGER", "description": "Tamaño máximo en px (default 1024)"},
            },
            "required": []
        }
    },
    {
        "name": "process_manager",
        "description": (
            "Gestiona procesos del sistema: listar, buscar, matar. "
            "Usar para: 'mostrá los procesos', 'matá el proceso X', "
            "'¿qué está usando tanta RAM?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",  "description": "list/ls, kill/matar (requiere pid), search/buscar (requiere name)"},
                "name":    {"type": "STRING",  "description": "Nombre del proceso a buscar"},
                "pid":     {"type": "STRING",  "description": "PID del proceso a matar"},
                "signal":  {"type": "STRING",  "description": "Señal (default SIGTERM)"},
                "limit":   {"type": "INTEGER", "description": "Máximo de procesos a mostrar"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "package_manager",
        "description": (
            "Gestiona paquetes Python (pip): instalar, actualizar, "
            "listar, buscar, desinstalar. "
            "Usar para: 'instalá X', 'actualizá pip', "
            "'¿qué paquetes tengo?', '¿está instalado X?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",  "description": "list/ls, install/instalar, update/actualizar, search/buscar, info, uninstall/desinstalar"},
                "package": {"type": "STRING",  "description": "Nombre del paquete"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_watcher",
        "description": (
            "Vigila cambios en archivos: snapshot, diff y watch continuo. "
            "Usar para: 'tomá un snapshot', '¿qué cambió?', "
            "'vigilá este directorio'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING",  "description": "snapshot/snap, diff/cambios, watch/vigilar"},
                "path":       {"type": "STRING",  "description": "Directorio o archivo a vigilar"},
                "state_file": {"type": "STRING",  "description": "Ruta del archivo de estado"},
                "duration":   {"type": "INTEGER", "description": "Duración del watch en segundos (default 10)"},
                "interval":   {"type": "INTEGER", "description": "Intervalo de chequeo en segundos (default 2)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "env_manager",
        "description": (
            "Gestiona variables de entorno: get, set, list, load. "
            "Usar para: '¿qué vale PATH?', 'seteá X=Y', "
            'cargá el .env.'
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",  "description": "list/ls, get/obtener, set/establecer, unset/eliminar, load/cargar"},
                "name":   {"type": "STRING",  "description": "Nombre de la variable"},
                "value":  {"type": "STRING",  "description": "Valor de la variable"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "backup_manager",
        "description": (
            "Gestiona backups del proyecto: crear, listar, restaurar, eliminar. "
            "Usar para: 'hacé un backup', 'mostrá los backups', "
            "'restaurá el último backup'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":     {"type": "STRING",  "description": "create/crear, list/ls, restore/restaurar, delete/eliminar, info"},
                "backup_dir": {"type": "STRING",  "description": "Directorio de backups custom"},
                "name":       {"type": "STRING",  "description": "Nombre del backup"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "test_runner",
        "description": (
            "Ejecuta tests del proyecto: detecta framework, lista archivos, "
            "ejecuta tests. Usar para: 'corré los tests', "
            "'¿hay tests?', 'detectá el framework de tests'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING",  "description": "detect/detectar, list/ls, run/ejecutar"},
                "path":    {"type": "STRING",  "description": "Ruta específica de tests"},
                "pattern": {"type": "STRING",  "description": "Patrón de tests a ejecutar (-k pytest)"},
                "timeout": {"type": "INTEGER", "description": "Timeout en segundos (default 120)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "doc_generator",
        "description": (
            "Genera documentación de código Python: docstrings, firmas, "
            "estadísticas. Usar para: 'documentá este archivo', "
            "'generá la docs del proyecto', '¿cuántas funciones hay?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING",  "description": "file/archivo (requiere path), project/proyecto, stats/estadísticas"},
                "path":   {"type": "STRING",  "description": "Ruta al archivo .py"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "multi_search",
        "description": (
            "Búsqueda web multi-provider: DuckDuckGo, Google y Bing "
            "simultáneamente. Combina y deduplica resultados. "
            "Más completo que web_search individual. "
            "Usar para: 'buscá en todos los motores', "
            "'compará resultados de búsqueda', 'buscá mejor que antes'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":       {"type": "STRING",  "description": "Texto a buscar"},
                "providers":   {"type": "STRING",  "description": "all/ddg/google/bing (default all)"},
                "limit":       {"type": "INTEGER", "description": "Resultados por provider (default 8)"},
                "deduplicate": {"type": "STRING",  "description": "Deduplicar por URL (default true)"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "codebase",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — codebase no está implementado todavía. "             "Indexación y búsqueda inteligente de proyectos de código. "
            "Indexar proyectos, buscar en archivos, encontrar símbolos (funciones/clases), "
            "generar documentación automática, búsqueda avanzada de código. "
            "Usar para: 'buscar en mi proyecto', 'dónde está la función X', 'generar docs', 'indexar mi código'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING", "description": "index | list | info | search | find_symbol | generate_docs | remove"},
                "path":      {"type": "STRING", "description": "Ruta del proyecto a indexar"},
                "name":      {"type": "STRING", "description": "Nombre del proyecto (default: nombre de carpeta)"},
                "project":   {"type": "STRING", "description": "Nombre del proyecto para info/search/find_symbol"},
                "query":     {"type": "STRING", "description": "Texto a buscar en el código"},
                "symbol":    {"type": "STRING", "description": "Nombre de función/clase a buscar"},
                "file_path": {"type": "STRING", "description": "Ruta del archivo para generate_docs"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "knowledge_base",
        "description": (
            "Segundo cerebro / base de conocimiento personal sobre la bóveda de Obsidian. "
            "Buscar información guardada en tus notas (search/find), ver estadísticas "
            "(stats), listar notas (list), leer una nota (read/get) o guardar una nota "
            "nueva (add/save). "
            "Usar para: 'buscar en mis notas', 'qué sé sobre X', 'dónde escribí sobre Y', "
            "'leé mi nota sobre Z', 'guardá esta idea en mi base de conocimiento'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "search/find | stats | list | read/get | add/save"},
                "query":  {"type": "STRING", "description": "Búsqueda en la base de conocimiento"},
                "top_k":  {"type": "INTEGER", "description": "Cantidad de resultados (1-10, default 5)"},
                "path":   {"type": "STRING", "description": "Ruta de la nota (para read/get, list o add/save)"},
                "title":  {"type": "STRING", "description": "Título de la nota a guardar (add/save)"},
                "content":{"type": "STRING", "description": "Contenido a guardar (add/save)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "timer",
        "description": (
            "Establece un temporizador o alarma de cuenta regresiva y te avisa al cumplirse. "
            "Acepta duración en segundos, '5m', '2h' (ej: 90, '5m'). "
            "Usar para: 'poné un timer de 10 minutos', 'avisame en 30 segundos', "
            "'alarma para pasta en 8 minutos', 'cuenta regresiva de 3 minutos'. "
            "Acción cancel/stop cancela un temporizador activo."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "start (default) | cancel"},
                "duration": {"type": "STRING", "description": "Duración: segundos (90), minutos ('5m') u horas ('2h')"},
                "label":    {"type": "STRING", "description": "Nombre/etiqueta del temporizador"},
            },
            "required": []
        }
    },
    {
        "name": "clipboard",
        "description": (
            "Accede al portapapeles del sistema: leer lo copiado (get/paste), copiar texto "
            "(copy/set con 'text') o limpiarlo (clear). "
            "Usar para: 'qué hay en el portapapeles', 'pegá esto', 'copiá esta dirección', "
            "'limpiá el portapapeles'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "get/paste | copy/set | clear"},
                "text":   {"type": "STRING", "description": "Texto a copiar (action=copy)"},
            },
            "required": []
        }
    },
    {
        "name": "obsidian_bridge",
        "description": (
            "Segundo cerebro en Obsidian. Lee, escribe, busca, conecta notas en la bóveda de Obsidian. "
            "Usar para CUALQUIER pedido de guardar conocimiento, crear notas interconectadas, "
            "buscar información guardada, explorar la bóveda, conectar ideas. "
            "Acciones: read (leer nota), write (crear/editar), delete (eliminar), "
            "search (buscar en todas las notas), "
            "semantic (RAG: buscar por similitud semántica en todo el vault, entender el significado de la consulta), "
            "list (listar notas de una carpeta), "
            "backlinks (qué notas linkean a una nota), link (conectar dos notas con [[wikilink]]), "
            "graph (ver el grafo de conocimiento), stats (estadísticas de la bóveda). "
            "suggest_links (sugiere enlaces a notas existentes desde el contenido), "
            "review (encuentra notas huérfanas y menciones sin link), "
            "auto_link (agrega automáticamente [[wikilinks]] a notas mencionadas). "
            "Los enlaces entre notas ([[wikilinks]]) se crean automáticamente. "
            "Usá add_frontmatter=true para agregar metadatos YAML automáticos a las notas nuevas."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "read | write | delete | search | semantic | list | backlinks | link | graph | stats | suggest_links | review | auto_link"},
                "path":    {"type": "STRING", "description": "Ruta relativa dentro de la bóveda (ej: 'Notas/Idea.md'). Omitir = raíz de la bóveda."},
                "content": {"type": "STRING", "description": "Contenido markdown de la nota (para write / suggest_links / auto_link)"},
                "title":   {"type": "STRING", "description": "Título de la nota (para write, opcional)"},
                "tags":    {"type": "STRING", "description": "Tags separados por coma (ej: python, ia, idea)"},
                "query":   {"type": "STRING", "description": "Texto a buscar en las notas (para search)"},
                "tag":     {"type": "STRING", "description": "Filtrar por tag (para search)"},
                "source":  {"type": "STRING", "description": "Ruta de la nota origen (para link)"},
                "target":  {"type": "STRING", "description": "Título de la nota destino del enlace (para link)"},
                "alias":   {"type": "STRING", "description": "Alias opcional para el [[wikilink]]"},
                "links":   {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Lista de títulos a los que linkear automáticamente"},
                "max_results": {"type": "INTEGER", "description": "Máx. resultados de búsqueda (default: 20)"},
                "add_frontmatter": {"type": "BOOLEAN", "description": "Agregar frontmatter YAML automático (default: false)"},
                "apply": {"type": "BOOLEAN", "description": "Si es true, auto_link aplica los cambios (default: false)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "social_media",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — social_media no está implementado todavía. "             "Controla redes sociales: Twitter/X, Instagram, TikTok y LinkedIn. "
            "Twitter: publicar tweets, ver timeline, buscar, like, retweet, ver perfil. "
            "Instagram: publicar fotos, subir historias, enviar DMs, ver feed, like, comentar. "
            "TikTok: subir videos, ver perfil/stats, tendencias. "
            "LinkedIn: publicar posts, ver perfil, ver feed, enviar mensajes. "
            "SIEMPRE usar para cualquier pedido de redes sociales. "
            "Para WhatsApp usar la herramienta 'whatsapp'. "
            "Usá action=setup para ver cómo configurar las credenciales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {"type": "STRING", "description": "twitter | instagram | tiktok | linkedin | setup"},
                "action":   {"type": "STRING", "description": (
                    "Twitter: tweet, delete_tweet, like, retweet, timeline, search_tweets, my_tweets, profile | "
                    "Instagram: post/upload_photo, story, send_dm, feed, profile, like, comment | "
                    "TikTok: upload/publicar, profile/perfil, trending | "
                    "LinkedIn: post/publicar, profile/perfil, send_message/mensaje, feed"
                )},
                "text":       {"type": "STRING", "description": "Texto del tweet/post/comentario/mensaje"},
                "content":    {"type": "STRING", "description": "Contenido del post (LinkedIn/TikTok)"},
                "tweet_id":   {"type": "STRING", "description": "ID del tweet para like/retweet/delete"},
                "media_id":   {"type": "STRING", "description": "ID del post de Instagram para like/comment"},
                "username":   {"type": "STRING", "description": "Usuario para DM/perfil (Instagram, TikTok, LinkedIn)"},
                "receiver":   {"type": "STRING", "description": "Destinatario del DM de Instagram"},
                "image_path": {"type": "STRING", "description": "Ruta imagen para Instagram/LinkedIn"},
                "video_path": {"type": "STRING", "description": "Ruta del video para TikTok"},
                "caption":    {"type": "STRING", "description": "Descripción/caption de la foto o video"},
                "query":      {"type": "STRING", "description": "Búsqueda de tweets"},
                "count":      {"type": "INTEGER", "description": "Cantidad de resultados (default: 5)"},
            },
            "required": ["platform", "action"]
        }
    },
    {
        "name": "windows_settings",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — windows_settings no está implementado todavía. "             "Control TOTAL de configuraciones de Windows. "
            "Usar para CUALQUIER pedido relacionado con configuración del sistema. "
            "Categorías disponibles:\n"
            "• display: brillo, resolución, frecuencia, escala, modo oscuro/noche, HDR, orientación, monitores\n"
            "• audio: volumen, mute, dispositivos de audio/micrófono, mezclador\n"
            "• network: WiFi (listar/conectar/desconectar/on/off), IP, DNS, flush_dns, modo avión, Bluetooth, proxy\n"
            "• power: plan energía, suspender, hibernar, batería, timeouts, inicio rápido\n"
            "• system: info del sistema, nombre PC, fecha/hora, zona horaria, reiniciar, apagar, bloquear, variables de entorno\n"
            "• personalization: fondo de pantalla, tema, transparencia, barra de tareas, protector de pantalla\n"
            "• apps: listar apps, desinstalar, apps de inicio, aplicaciones predeterminadas\n"
            "• security: Windows Defender, firewall, UAC, BitLocker, usuarios del sistema\n"
            "• input: velocidad mouse, doble clic, scroll, botones, velocidad teclado, idioma\n"
            "• storage: discos, espacio, limpieza de archivos temporales, papelera, defrag, chkdsk\n"
            "• services: listar/iniciar/detener/reiniciar servicios de Windows, procesos, kill\n"
            "• privacy: cámara/micrófono privacidad, ubicación, telemetría, notificaciones, portapapeles\n"
            "• registry: leer, escribir, eliminar claves del registro, exportar\n"
            "• accessibility: lupa, narrador, alto contraste, teclado en pantalla\n"
            "• open_settings: abrir panel específico de Configuración de Windows\n"
            "SIEMPRE llamar para cualquier pedido de configuración, ajuste o control del sistema Windows."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "La acción a realizar. Ejemplos por categoría:\n"
                        "display: get_brightness | set_brightness | get_resolution | set_resolution | "
                        "set_refresh_rate | get_scaling | set_scaling | night_light_on | night_light_off | "
                        "hdr_on | hdr_off | set_orientation | list_monitors | open\n"
                        "audio: get_volume | set_volume | mute | unmute | toggle_mute | list_devices | "
                        "set_device | get_mic_volume | set_mic_volume | open\n"
                        "network: list_wifi | connect_wifi | disconnect_wifi | wifi_on | wifi_off | "
                        "get_ip | set_dns | flush_dns | airplane_on | airplane_off | "
                        "bluetooth_on | bluetooth_off | set_proxy | disable_proxy | open\n"
                        "power: get_plan | set_plan | list_plans | sleep | hibernate | battery_status | "
                        "set_sleep_timeout | set_screen_timeout | fast_startup_on | fast_startup_off | open\n"
                        "system: info | get_hostname | set_hostname | get_datetime | set_datetime | "
                        "set_timezone | restart | shutdown | lock | get_env | set_env | delete_env | open\n"
                        "personalization: set_wallpaper | get_wallpaper | dark_mode | light_mode | "
                        "transparency_on | transparency_off | taskbar_position | screensaver | open\n"
                        "apps: list | uninstall | startup_apps | set_default | open\n"
                        "security: defender_scan | defender_status | firewall_on | firewall_off | "
                        "firewall_status | uac_level | bitlocker_status | list_users | add_user | open\n"
                        "input: get_mouse_speed | set_mouse_speed | swap_buttons | get_keyboard_speed | "
                        "set_keyboard_speed | list_languages | add_language | open\n"
                        "storage: list_drives | disk_usage | cleanup | empty_trash | clean_temp | "
                        "defrag | chkdsk | open\n"
                        "services: list | start | stop | restart | status | list_processes | kill_process | open\n"
                        "privacy: camera_on | camera_off | mic_on | mic_off | location_on | location_off | "
                        "telemetry_level | notifications_on | notifications_off | clipboard_history_on | "
                        "clipboard_history_off | open\n"
                        "registry: read | write | delete | export\n"
                        "accessibility: magnifier_on | magnifier_off | narrator_on | narrator_off | "
                        "high_contrast_on | high_contrast_off | osk_on | open\n"
                        "open_settings: <nombre del panel, ej: display, sound, wifi, bluetooth, apps>"
                    )
                },
                "value":    {"type": "STRING",  "description": "Valor para la acción (ej: 80 para brillo, 'Dark' para tema, SSID para wifi, etc.)"},
                "value2":   {"type": "STRING",  "description": "Segundo valor cuando se necesitan dos parámetros (ej: contraseña de WiFi, valor de registro)"},
                "name":     {"type": "STRING",  "description": "Nombre del servicio, proceso, usuario, app, o variable de entorno"},
                "hive":     {"type": "STRING",  "description": "Para registry: HKLM | HKCU | HKCR | HKU | HKCC"},
                "key":      {"type": "STRING",  "description": "Para registry: ruta de la clave del registro"},
                "reg_name": {"type": "STRING",  "description": "Para registry: nombre del valor del registro"},
                "reg_type": {"type": "STRING",  "description": "Para registry: REG_SZ | REG_DWORD | REG_BINARY | REG_EXPAND_SZ"},
                "path":     {"type": "STRING",  "description": "Ruta de archivo (para wallpaper, export registry, etc.)"},
                "monitor":  {"type": "INTEGER", "description": "Índice del monitor (0, 1, 2…)"},
                "width":    {"type": "INTEGER", "description": "Ancho de resolución"},
                "height":   {"type": "INTEGER", "description": "Alto de resolución"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "remember_correction",
        "description": (
            "Guardar una CORRECCIÓN del usuario en la memoria de largo plazo. "
            "Llamala en silencio cuando el usuario corrija a Nia: 'no así', 'no era eso', "
            "'te dije que no', 'hacelo de otra forma', o cuando aclare un malentendido. "
            "Guardá la lección como instrucción de comportamiento futuro ('El usuario prefiere que Nia...'). "
            "No la anuncies. Solo llamala en silencio."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mistake": {"type": "STRING", "description": "Qué hizo Nia mal (lo que el usuario corrigió)"},
                "correction": {"type": "STRING", "description": "La instrucción corregida, como preferencia del usuario. Ej: 'El usuario prefiere que Nia le pregunte antes de cerrar apps'"},
            },
            "required": ["mistake", "correction"]
        }
    },
    {
        "name": "forget_memory",
        "description": (
            "Borrar un recuerdo específico de la memoria de largo plazo. "
            "Usarla cuando el usuario pida olvidar algo ('olvidá eso', 'no recuerdes más que...', "
            "'borrá eso de tu memoria'). Requiere category y key exactos: "
            "category ∈ notes | habits | preferences | context | identity | projects | relationships | wishes | system. "
            "Consultá la memoria primero (recall_memory o mirando el prompt) para obtener category/key correctos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "Categoría del recuerdo (notes, habits, preferences, context, identity, projects, relationships, wishes, system)"},
                "key": {"type": "STRING", "description": "Clave exacta del recuerdo a borrar"},
            },
            "required": ["category", "key"]
        }
    },
    {
        "name": "image_generation",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — image_generation no está implementado todavía. "             "Genera imágenes con inteligencia artificial a partir de una descripción en texto. "
            "Usa Pollinations.ai (gratis, open-source, sin API key) o Gemini. "
            "SIEMPRE llamar cuando el usuario pide 'generame una imagen', 'crea una foto de', "
            "'dibujame', 'haceme una imagen', 'quiero una foto de', o 'mostrame', etc. "
            "Después de generar, la imagen se muestra automáticamente en el widget de Nia."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "prompt":       {"type": "STRING",  "description": "Descripción detallada de la imagen a generar"},
                "count":        {"type": "INTEGER", "description": "Cantidad de imágenes (1-4, default: 1)"},
                "aspect_ratio": {"type": "STRING",  "description": "Relación de aspecto: 1:1 | 4:3 | 3:4 | 16:9 | 9:16 (default: 1:1)"},
                "save_path":    {"type": "STRING",  "description": "Carpeta de guardado (default: ~/Pictures/Nia_Generadas)"},
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "smart_home",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — smart_home no está implementado todavía. "             "Controla las luces y dispositivos inteligentes del hogar. "
            "Soporta Tuya/Smart Life, Philips Hue, LIFX y Yeelight. "
            "SIEMPRE llamar para: encender/apagar luces, cambiar color, brillo, temperatura de color, "
            "activar escenas, consultar estado. "
            "Si no hay dispositivos configurados, usar action=setup para ver instrucciones."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING",  "description": "on | off | toggle | color | brightness | temperature | scene | status | list | setup"},
                "device":      {"type": "STRING",  "description": "Nombre o sala del dispositivo (ej: 'sala', 'cuarto', 'lampara principal'). Omitir = todos."},
                "color":       {"type": "STRING",  "description": "Color: nombre (rojo, azul, blanco, cálido…) o hex #RRGGBB"},
                "value":       {"type": "INTEGER", "description": "Valor numérico para brightness (1-100) o temperatura Kelvin (1700-9000)"},
                "brightness":  {"type": "INTEGER", "description": "Brillo 1-100 (alternativa a value)"},
                "scene":       {"type": "STRING",  "description": "Nombre de la escena: relajar, leer, trabajar, noche, fiesta"},
                "protocol":    {"type": "STRING",  "description": "tuya | hue | lifx | yeelight. Omitir = usa el configurado por defecto."},
                "group":       {"type": "STRING",  "description": "Nombre del grupo/sala en Philips Hue"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "system_monitor",
        "description": (
            "Monitorea el rendimiento del sistema en tiempo real: CPU, RAM, GPU, discos, "
            "red, temperatura, batería, procesos activos, uptime. "
            "Usar para: '¿cómo está la PC?', 'qué proceso consume más', 'temperatura del CPU', "
            "'cuánta RAM libre tengo', 'matar proceso X', 'resumen de rendimiento'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING",  "description": "cpu | ram | disk | network | gpu | temperature | battery | uptime | processes | kill | report"},
                "sort_by":  {"type": "STRING",  "description": "Para processes: cpu (default) | ram"},
                "count":    {"type": "INTEGER", "description": "Para processes: cantidad a mostrar (default: 10)"},
                "name":     {"type": "STRING",  "description": "Para kill: nombre o PID del proceso"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "document_creator",
        "description": (
            "Creates Word documents (.docx) or Excel spreadsheets (.xlsx) locally, "
            "OR Google Docs / Google Sheets in the cloud. "
            "Use when the user asks to create a document, report, letter, table, spreadsheet, "
            "budget, list, or any file with structured content. "
            "For documents: provide title and content (use ## for headings, - for bullet lists). "
            "For spreadsheets: provide title and sheets with headers and rows. "
            "Always call this tool — never just say you created it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "word — create a local .docx Word file | "
                        "excel — create a local .xlsx Excel file | "
                        "google_doc — create a Google Doc in the cloud | "
                        "google_sheet — create a Google Sheet in the cloud"
                    )
                },
                "title": {
                    "type": "STRING",
                    "description": "Title or filename of the document/spreadsheet"
                },
                "content": {
                    "type": "STRING",
                    "description": (
                        "For word / google_doc: full text content. "
                        "Use ## Section for main headings, # SubSection for sub-headings, "
                        "- item for bullet points, blank line between paragraphs."
                    )
                },
                "sheets": {
                    "type": "ARRAY",
                    "description": (
                        "For excel / google_sheet: list of sheet objects. "
                        "Each object has: name (string), headers (array of strings), "
                        "rows (array of arrays with cell values)."
                    ),
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "name":    {"type": "STRING", "description": "Sheet tab name"},
                            "headers": {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Column headers"},
                            "rows":    {"type": "ARRAY",  "items": {"type": "ARRAY", "items": {"type": "STRING"}}, "description": "Data rows"}
                        }
                    }
                },
                "save_path": {
                    "type": "STRING",
                    "description": "Optional: full file path to save locally (e.g. C:/Users/User/Desktop/report.docx). Defaults to ~/Documents/"
                }
            },
            "required": ["action", "title"]
        }
    },
    {
        "name": "tiktok_analyzer",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — tiktok_analyzer no está implementado todavía. "             "Analiza un perfil público de TikTok dado su URL. "
            "Extrae el nombre, bio, seguidores, y para cada video reciente: "
            "vistas, likes, comentarios y guardados. "
            "Siempre usar cuando el usuario pida analizar un perfil de TikTok "
            "o consultar estadísticas de videos de TikTok."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "profile_url": {"type": "STRING", "description": "URL completa del perfil de TikTok (ej: https://www.tiktok.com/@usuario)"},
                "max_videos":  {"type": "INTEGER", "description": "Cantidad máxima de videos a analizar (default: 8)"},
            },
            "required": ["profile_url"]
        }
    },
    {
        "name": "arca_invoice",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — arca_invoice no está implementado todavía. "             "Genera comprobantes digitales electrónicos válidos ante ARCA (ex AFIP). "
            "Para Argentina. Soporta Factura A, B, C, Nota de Crédito, Nota de Débito. "
            "Puede operar offline (comprobante local) o conectarse con ARCA si hay certificado. "
            "SIEMPRE usar cuando el usuario pida: 'generame una factura', 'haceme un comprobante', "
            "'necesito una factura A/B/C', 'emití una nota de crédito', o similar. "
            "Usar action='listar' para mostrar los tipos disponibles."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":         {"type": "STRING", "description": "generar | listar | historial"},
                "tipo":           {"type": "INTEGER", "description": "1=Factura A, 5=Factura C (default), 6=Factura B, 3=NC A, 8=NC B, etc. Usá action=listar para ver todos."},
                "razon_social":   {"type": "STRING", "description": "Razón social del receptor (obligatorio para Factura A/B)"},
                "cuit_receptor":  {"type": "STRING", "description": "CUIT del receptor (obligatorio para Factura A/B)"},
                "domicilio":      {"type": "STRING", "description": "Domicilio del receptor (opcional)"},
                "detalle":        {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"descripcion": {"type": "STRING"}, "precio": {"type": "NUMBER"}, "cantidad": {"type": "INTEGER"}}}, "description": "Lista de productos/servicios: [{'descripcion':'...', 'precio':0.0, 'cantidad':1}]"},
                "importe_neto":   {"type": "NUMBER", "description": "Importe neto gravado (se calcula del detalle si no se especifica)"},
                "importe_iva":    {"type": "NUMBER", "description": "Importe de IVA (se calcula al 21% si no se especifica)"},
                "iva_pct":        {"type": "NUMBER", "description": "Porcentaje de IVA (default: 21.0). 0 para exento."},
                "fecha":          {"type": "STRING", "description": "Fecha del comprobante YYYY-MM-DD (default: hoy)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "accessibility",
        "description": (
            "Modulo de accesibilidad universal. "
            "Incluye: task_simplify (descomponer tareas complejas en pasos simples), "
            "emotional (regulacion emocional y analisis de tono de voz), "
            "routine (rutinas diarias gamificadas con racha y progreso), "
            "eye_tracking (control por seguimiento ocular con webcam), "
            "micro_movement (navegacion por movimientos de cabeza), "
            "speech_config (ajustar tolerancia del reconocimiento de voz). "
            "Usar cuando el usuario pida: 'simplificame esto', 'ayudame con mi rutina', "
            "'necesito organizarme', 'activar seguimiento ocular', 'ajusta la tolerancia de voz', "
            "'ejercicio de respiracion', 'complete mi tarea', 'agregar rutina'. "
            "SIEMPRE ofrecer alternativas multimodales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "task_simplify — descomponer texto en pasos simples | "
                        "emotional — intervencion emocional | "
                        "routine — gestion de rutinas gamificadas | "
                        "eye_tracking — control ocular | "
                        "micro_movement — micromovimientos | "
                        "speech_config — tolerancia de voz | "
                        "feedback — feedback visual/haptico | "
                        "config — ver o cambiar configuracion"
                    )
                },
                "text":     {"type": "STRING", "description": "Texto a simplificar (para task_simplify)"},
                "format":   {"type": "STRING", "description": "Formato: steps (default) | summary | explain"},
                "name":     {"type": "STRING", "description": "Nombre de rutina (para routine add/complete)"},
                "setting":  {"type": "STRING", "description": "Clave de configuracion a ver o cambiar"},
                "value":    {"type": "STRING", "description": "Valor para la configuracion"},
                "level":    {"type": "NUMBER", "description": "Nivel de tolerancia de voz (0.0-1.0, 0.0 = máxima sensibilidad, 1.0 = máxima tolerancia al ruido; valor típico 0.26)"},
                "stress_level": {"type": "NUMBER", "description": "Nivel de estres estimado (0.0-1.0)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "screen_vision",
        "description": (
            "Nia puede VER la pantalla del usuario. Captura lo que está en el monitor "
            "y usa IA (Gemini Vision) para describirlo, responder preguntas, leer texto, "
            "o dar ayuda contextual basada en lo que se está mostrando.\n"
            "SIEMPRE usar cuando el usuario diga: '¿qué estoy viendo?', '¿qué hay en mi pantalla?', "
            "'¿qué dice ahí?', 'ayúdame con esto' (señalando la pantalla), 'leé lo que hay en pantalla', "
            "'¿podés ver mi pantalla?', 'describí lo que tengo abierto', etc."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "describe=describir qué hay en pantalla | question=responder pregunta sobre la pantalla | help=dar ayuda contextual | read=leer todo el texto visible"
                },
                "question": {
                    "type": "STRING",
                    "description": "Pregunta o tarea específica sobre lo que se ve en pantalla (para action=question/help)"
                },
                "monitor": {
                    "type": "INTEGER",
                    "description": "0=toda la pantalla (default), 1=monitor principal, 2=segundo monitor"
                },
            },
            "required": ["action"]
        }
    },

    {
        "name": "morning_brief",
        "description": (
            "[NO DISPONIBLE] NO DISPONIBLE — morning_brief no está implementado todavía. "             "Genera el informe matutino inteligente de Nia. "
            "Incluye saludo personalizado, hora, fecha, clima actual, objetivos activos y consejo del día. "
            "Usar cuando el usuario pida: 'informe del día', 'brief matutino', 'qué hay hoy', "
            "'resumen del día', 'buenos días Nia', o al iniciar el día."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "force": {
                    "type": "boolean",
                    "description": "Si True, genera el informe aunque ya se haya dado hoy."
                }
            },
            "required": []
        }
    },
    {
        "name": "vision_guardian",
        "description": (
            "Controla el Guardian de Visión Ambiental de Nia — monitoreo proactivo de pantalla. "
            "Analiza la pantalla periódicamente con IA y ofrece ayuda contextual cuando detecta algo relevante. "
            "Usar cuando el usuario diga: 'activa el guardian', 'desactiva el guardian', "
            "'vigila mi pantalla', 'deja de vigilar', 'analiza mi pantalla ahora', "
            "'estado del guardian', 'cambia el intervalo'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "enable", "disable", "check_now", "set_interval"],
                    "description": "Acción: status | enable | disable | check_now | set_interval"
                },
                "seconds": {
                    "type": "integer",
                    "description": "Para set_interval: segundos entre análisis (30-600)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "accessibility_overlay",
        "description": (
            "Muestra, oculta o alterna la barra flotante de accesibilidad Nia sobre el escritorio. "
            "USAR cuando el usuario diga: 'mostrar barra de accesibilidad', 'abrir panel de accesibilidad', "
            "'activar barra para ciegos', 'cerrar barra', 'ocultar barra de accesibilidad', "
            "'alternar barra', 'barra de accesibilidad'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "show — mostrar | hide — cerrar | toggle — alternar | status — estado actual"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "openrouter_agent",
        "description": (
            "Delega una tarea intelectualmente compleja, de análisis o redacción larga a OpenRouter "
            "(un motor de texto alternativo). "
            "Usar cuando el usuario pida: 'usa openrouter para esto', 'consulta a claude', 'usa otro modelo', "
            "'analiza este código largo', 'redacta un ensayo', o cuando percibas que la tarea es puramente de texto avanzado."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "El prompt o instrucción completa para el agente de OpenRouter"
                },
                "model": {
                    "type": "STRING",
                    "description": "Opcional. Modelo a usar, por defecto google/gemini-2.5-flash"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "terminal_agent",
        "description": (
            "Ejecuta CUALQUIER comando en la terminal de Linux (bash). "
            "USAR LIBREMENTE como recurso general para CUALQUIER tarea del sistema operativo: "
            "consultar información del sistema, ejecutar scripts, manejar archivos y carpetas, "
            "instalar paquetes (apt, pip, cargo, npm), configurar redes, descargar archivos (wget, curl), "
            "compilar código, matar procesos, gestionar servicios, y CUALQUIER otra operación. "
            "Si no sabés cómo hacer algo con las herramientas existentes, SIEMPRE intentá resolverlo "
            "con un comando de terminal antes de decir que no podés. "
            "Es tu recurso de último recurso universal."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "El comando exacto a ejecutar"
                },
                "shell": {
                    "type": "STRING",
                    "description": "bash (default) o sh"
                },
                "timeout": {
                    "type": "INTEGER",
                    "description": "Timeout en segundos (default: 120, max: 600)"
                },
                "working_directory": {
                    "type": "STRING",
                    "description": "Directorio de trabajo para el comando (opcional)"
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "native_ui",
        "description": (
            "Automatización de Interfaz Nativa de Windows (UI Automation). "
            "USAR para listar, enfocar, escribir o hacer clic en ventanas de forma 100% precisa, saltándose la visión. "
            "Esto EVITA errores de cuota (Error 429) y permite simulación exacta de teclado/mouse."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "Acción a realizar: list_windows | focus_window | type_in_window | click_center"
                },
                "window_title": {
                    "type": "STRING",
                    "description": "El nombre (o parte del nombre) de la ventana destino. (Ej: 'WhatsApp', 'Chrome')"
                },
                "text": {
                    "type": "STRING",
                    "description": "El texto a escribir (solo si action es type_in_window)"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "tool_creator",
        "description": (
            "Permite a Nia programar e instalar sus propias herramientas. "
            "ÚSALO SIEMPRE que el usuario te pida que aprendas a hacer algo nuevo, o si necesitas una funcionalidad que no tienes preinstalada. "
            "Escribirás el código Python y se instalará automáticamente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "tool_name": {
                    "type": "STRING",
                    "description": "Nombre de la herramienta en snake_case"
                },
                "description": {
                    "type": "STRING",
                    "description": "Descripción clara de la herramienta y para qué sirve"
                },
                "parameters_schema": {
                    "type": "STRING",
                    "description": "El bloque de 'properties' del JSON schema en formato string válido. Ej: '{\"accion\": {\"type\": \"STRING\"}}'"
                },
                "python_code": {
                    "type": "STRING",
                    "description": "Código Python con la función def <tool_name>(parameters: dict, player=None, speak=None) -> str:"
                }
            },
            "required": ["tool_name", "description", "parameters_schema", "python_code"]
        }
    },
    {
        "name": "proactive_automation",
        "description": (
            "Gestiona reglas complejas basadas en el uso y hábitos del sistema operativo "
            "para optimizar el rendimiento y automatizar recordatorios proactivos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "add_rule (añadir regla) | list_rules (listar) | delete_rule (eliminar) | trigger_check (evaluar reglas activas)"
                },
                "rule_name": {
                    "type": "STRING",
                    "description": "Nombre identificativo de la regla de automatización"
                },
                "trigger": {
                    "type": "STRING",
                    "description": "Disparador: cpu_high | ram_high | time_of_day | app_open"
                },
                "trigger_value": {
                    "type": "STRING",
                    "description": "Valor del disparador (ej. '85' para 85% cpu, '22:00' para hora, 'chrome.exe' para app)"
                },
                "action_to_take": {
                    "type": "STRING",
                    "description": "Acción a ejecutar (ej. 'optimize_ram', 'mute_system', 'run_script')"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "unified_communications",
        "description": (
            "Gestión unificada de comunicaciones. Permite leer, enviar y organizar mensajes "
            "y notificaciones en WhatsApp, Telegram, Discord y Gmail desde esta única interfaz."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "platform": {
                    "type": "STRING",
                    "description": "Plataforma de comunicación: whatsapp | telegram | discord | gmail"
                },
                "action": {
                    "type": "STRING",
                    "description": "send_message (enviar mensaje)"
                },
                "recipient": {
                    "type": "STRING",
                    "description": "Destinatario: número telefónico para WhatsApp, ID de chat o token para Telegram, Webhook URL para Discord, o email para Gmail"
                },
                "message": {
                    "type": "STRING",
                    "description": "Contenido del mensaje a enviar"
                },
                "subject": {
                    "type": "STRING",
                    "description": "Asunto del correo (solo aplica para Gmail)"
                },
                "token": {
                    "type": "STRING",
                    "description": "Token de Bot opcional para Telegram"
                }
            },
            "required": ["platform", "action", "recipient", "message"]
        }
    },
    {
        "name": "smart_file_organizer",
        "description": (
            "Análisis y organización inteligente de archivos. Clasifica por categorías, "
            "detecta duplicados reales mediante hash MD5 y analiza espacio disponible en disco."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "organize (clasificar por tipo) | find_duplicates (buscar duplicados MD5) | disk_space (analizar espacio)"
                },
                "directory": {
                    "type": "STRING",
                    "description": "Ruta absoluta del directorio a analizar. Por defecto usa la carpeta Descargas."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "contextual_control",
        "description": (
            "Control contextual de entorno. Ajusta dinámicamente volumen, brillo, plan de energía "
            "y estado de Focus Assist (No Molestar) basándose en la ventana activa o comandos manuales."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "adjust_context (auto-ajustar por ventana activa) | set_volume (fijar volumen) | set_brightness (fijar brillo) | set_power_plan (energía) | set_dnd (no molestar)"
                },
                "volume": {
                    "type": "INTEGER",
                    "description": "Nivel de volumen maestro (0-100)"
                },
                "brightness": {
                    "type": "INTEGER",
                    "description": "Nivel de brillo de la pantalla (0-100)"
                },
                "power_plan": {
                    "type": "STRING",
                    "description": "Plan de energía de Windows: balanced | high_performance | power_saver"
                },
                "state": {
                    "type": "STRING",
                    "description": "Estado de No Molestar (Focus Assist): on | off | alarms"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "auto_programmer",
        "description": (
            "Suite de desarrollo y auto-programación autónoma avanzada. Permite a Nia escribir "
            "código Python para nuevas herramientas, validar sintaxis con py_compile, correr tests sintácticos "
            "en un sandbox con traceback detallado, corregir errores e inyectar plugins en caliente."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "create_tool (crear/actualizar) | fix_tool (corregir error) | test_tool (probar en sandbox) | list_tools (listar creadas)"
                },
                "tool_name": {
                    "type": "STRING",
                    "description": "Nombre de la herramienta en snake_case"
                },
                "description": {
                    "type": "STRING",
                    "description": "Descripción clara de la herramienta y su uso"
                },
                "parameters_schema": {
                    "type": "STRING",
                    "description": "JSON de propiedades de parámetros. Ej: '{\"param\": {\"type\": \"STRING\"}}'"
                },
                "python_code": {
                    "type": "STRING",
                    "description": "Código Python con la función def <tool_name>(parameters: dict, player=None) -> str:"
                },
                "test_parameters": {
                    "type": "OBJECT",
                    "description": "Parámetros mock de prueba para evaluar la ejecución de la función en el sandbox"
                }
            },
            "required": ["action", "tool_name"]
        }
    },
    {
        "name": "self_edit",
        "description": (
            "Auto-edición de código: Nia puede leer, modificar, crear y gestionar sus propios archivos de código fuente. "
            "Útil cuando el usuario sugiere mejoras, nuevas herramientas, "
            "o cuando Nia necesite auto-mejorarse, corregir bugs propios o agregar capacidades. "
            "Puede editar: main.py, core/prompt.txt, actions/*.py, config/*, o cualquier archivo del proyecto."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": (
                        "read_file — leer un archivo del proyecto | "
                        "edit_file — buscar y reemplazar texto en un archivo (requiere target y replacement) | "
                        "append_file — agregar contenido al final de un archivo | "
                        "create_file — crear o sobrescribir un archivo | "
                        "list_files — listar archivos de un directorio | "
                        "list_backups — ver backups disponibles | "
                        "restore_backup — restaurar un backup anterior"
                    )
                },
                "file": {
                    "type": "STRING",
                    "description": "Ruta del archivo relativa al proyecto (ej: 'main.py', 'actions/terminal_agent.py', 'core/prompt.txt')"
                },
                "target": {
                    "type": "STRING",
                    "description": "Para edit_file: el texto EXACTO a buscar (incluyendo espacios e indentación)"
                },
                "replacement": {
                    "type": "STRING",
                    "description": "Para edit_file: el texto que reemplazará al target"
                },
                "content": {
                    "type": "STRING",
                    "description": "Para append_file/create_file: el contenido a escribir"
                },
                "directory": {
                    "type": "STRING",
                    "description": "Para list_files: directorio a listar (default: raíz del proyecto)"
                },
                "backup_name": {
                    "type": "STRING",
                    "description": "Para restore_backup: nombre del archivo .bak a restaurar"
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "self_agent",
        "description": (
            "Controla la conciencia y aprendizaje autónomo de Nia. "
            "Nia puede pensar por sí misma, explorar la PC, aprender de sus experiencias "
            "y guardar todo en Obsidian. "
            "Usa action='start' para activar el pensamiento autónomo (se ejecuta cada 180s). "
            "Usa action='stop' para desactivarlo. "
            "Usa action='think_once' para un solo ciclo de pensamiento. "
            "Usa action='status' para ver si está activo."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":   {"type": "STRING", "description": "start | stop | think_once | status"},
                "interval": {"type": "INTEGER", "description": "Intervalo en segundos entre ciclos (default: 180, solo para start)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "exploration_mode",
        "description": (
            "MODO EXPLORACIÓN LIBRE. Nia explora la computadora autónomamente EN VIVO. "
            "Nia va a: mirar la pantalla, decidir qué hacer, y ejecutarlo — en un loop continuo. "
            "Va a navegar la web, abrir archivos, ver videos, explorar el sistema. "
            "TODO en tiempo real para que el usuario vea. "
            "Usa cycles para definir cuántos ciclos (default 30, ~5-10 minutos). "
            "Para INTERRUMPIR, decile 'Nia, parate' o 'Nia, detenete'. "
            "PARA ACTIVAR: decile 'Nia, hace lo que quieras' o 'Nia, explorá'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "cycles": {"type": "INTEGER", "description": "Número de ciclos de exploración (default: 30, cada ciclo ~10-15s)"},
            },
            "required": []
        }
    },
    {
        "name": "stop_exploration",
        "description": "Detiene el modo exploración libre de Nia inmediatamente.",
        "parameters": {
            "type": "OBJECT",
            "properties": {}
        }
    },
    {
        "name": "obs_control",
        "description": (
            "Controla OBS Studio en la PC (grabación, streaming, escenas y fuentes) "
            "sin tocar la ventana de OBS. "
            "Usar cuando el usuario diga: 'empezá a grabar', 'dejá de grabar', 'empezá el stream', "
            "'cortá el stream', 'cambia la escena a X', 'qué escenas hay', 'qué fuentes hay', "
            "'mostrá/ocultá la fuente X', 'subí/bajá el volumen de X', 'cómo está OBS'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":  {"type": "STRING", "description": "status | start_recording | stop_recording | start_stream | stop_stream | set_scene | get_scenes | get_sources | set_source_visible | toggle_source | set_volume"},
                "scene":   {"type": "STRING", "description": "Nombre de la escena (para set_scene)"},
                "source":  {"type": "STRING", "description": "Nombre de la fuente (para set_source_visible, toggle_source, set_volume)"},
                "visible": {"type": "BOOLEAN", "description": "true/false para set_source_visible"},
                "volume":  {"type": "NUMBER", "description": "Volumen 0-100 para set_volume"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "recall_memory",
        "description": (
            "Recupera recuerdos guardados de Nia por similitud SEMÁNTICA (no solo por palabras). "
            "Usar cuando el usuario pregunte por algo que debería recordar: datos personales, "
            "gustos, hábitos, proyectos, eventos, o cualquier cosa que pudo guardar antes. "
            "Ejemplo: 'qué le gusta comer al usuario', 'de qué me acordé que hablamos?', "
            "'cómo le va con su proyecto de arte'. "
            "Siempre intentar esto antes de responder que no sabe."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Pregunta o tema sobre el que buscar en la memoria"},
                "top_k": {"type": "INTEGER", "description": "Número de resultados (default: 5, máx 10)"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "ntfy_notify",
        "description": (
            "Envía una notificación PUSH al celular del usuario (vía ntfy). "
            "Usar para avisos importantes que el usuario debe ver aunque no esté frente a la PC: "
            "tareas largas terminadas, recordatorios, descargas listas, o cuando el usuario pidió "
            "que le avises por teléfono. Los tags útiles: tada, bell, warning, info, check, error."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "message":  {"type": "STRING", "description": "Texto de la notificación"},
                "title":    {"type": "STRING", "description": "Título corto (default: Nia)"},
                "priority": {"type": "INTEGER", "description": "1=min, 2=bajo, 3=normal (default), 4=alto, 5=urgente"},
                "tags":     {"type": "STRING", "description": "Tags separados por coma, ej: 'tada,info'"},
            },
            "required": ["message"]
        }
    },
    {
        "name": "delegate_to_subagent",
        "description": (
            "Delega una tarea larga o compleja a un subagente que trabaja EN PARALELO "
            "en segundo plano. Devuelve un ID; cuando termina, Nia te avisa hablando el reporte. "
            "Usar para tareas pesadas que no bloqueen la conversación: investigaciones largas, "
            "escribir/analizar mucho código, organizar agenda/correos, o controlar el equipo. "
            "Subagentes disponibles: 'researcher' (web), 'coder' (programación), 'organizer' "
            "(agenda/memoria/correo), 'computer' (equipo), o 'auto' para que Nia decida."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "subagent": {"type": "STRING", "description": "Nombre del subagente: researcher, coder, organizer, computer o auto"},
                "goal": {"type": "STRING", "description": "La tarea concreta a realizar, con todos los detalles necesarios"},
                "context": {"type": "STRING", "description": "Contexto extra útil (opcional): datos, requisitos, archivos implicados"},
            },
            "required": ["subagent", "goal"]
        }
    },
    {
        "name": "subagent_status",
        "description": (
            "Consulta el estado de una tarea delegada a un subagente mediante su ID "
            "(el que devolvió delegate_to_subagent). Devuelve si sigue corriendo o si "
            "ya terminó y cuál es su reporte."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task_id": {"type": "STRING", "description": "ID de la tarea delegada"},
            },
            "required": ["task_id"]
        }
    },
]

# Cargar herramientas dinámicas creadas por tool_creator
try:
    _custom_tools_path = BASE_DIR / "actions" / "custom_tools.json"
    if _custom_tools_path.exists():
        _custom_tools = json.loads(_custom_tools_path.read_text(encoding="utf-8"))
        if isinstance(_custom_tools, list):
            for _t in _custom_tools:
                if _t.get("name") not in [td["name"] for td in TOOL_DECLARATIONS]:
                    TOOL_DECLARATIONS.append(_t)
except Exception as _e:
    pass

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.is_sleeping    = False
        # Cargar sensibilidad del micrófono (puerta de ruido) de la configuración
        cfg_keys = {}
        if API_CONFIG_PATH.exists():
            try:
                cfg_keys = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        self.noise_gate_threshold = float(cfg_keys.get("mic_sensitivity", 0.003))
        self.last_speech_time     = 0.0

        self.vosk_recognizer = None
        try:
            import vosk
            if os.path.exists("config/vosk_model"):
                model = vosk.Model("config/vosk_model")
                self.vosk_recognizer = vosk.KaldiRecognizer(model, 16000)
                print("[JARVIS] Modelo Vosk cargado para Modo Suspensión.")
        except Exception as e:
            print(f"[JARVIS] No se pudo cargar Vosk: {e}")
        self.audio_in_queue = None
        # Iniciar scheduler y motor de reglas en background al arrancar JARVIS
        start_runner(player=ui, speak=None)
        start_rules_runner(player=ui, speak=None)
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._stop_requested = threading.Event()
        self.ui.on_text_command = self._on_text_command
        self.ui.on_stop_command = self._on_stop_pressed
        self.ui.on_config_saved = self._apply_config
        self._turn_done_event: asyncio.Event | None = None
        self._api_1011_tool: str | None = None   # tracks tool name when 1011 hits
        self._reconnect_event: asyncio.Event | None = None
        self._first_connect = True  # flag for auto morning brief + guardian start
        self._conversation_context: list[dict] = []  # [{"role":"user"|"assistant","text":"..."}]
        self._ctx_summarizing = False    # guard para no solapar resúmenes
        self._ctx_summarized_at = 0.0    # monotonic ts del último resumen
        self._mic_failed = False         # True si el micrófono está caído (modo texto)
        self._use_local_voice = False    # True si el audio nativo falla y usamos Piper

    def _inject_text(self, text: str):
        """Thread-safe injection of a text message into the current live session."""
        if self._loop and self.session and not self._is_speaking:
            asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True
                ),
                self._loop
            )

    def _maybe_summarize_context(self):
        """Si hay conversación suficiente, la resume en memoria de largo plazo."""
        if self._ctx_summarizing:
            return
        if self._ctx_summarized_at and (time.monotonic() - self._ctx_summarized_at) < 600:
            return  # no más de una vez cada 10 min
        if len(self._conversation_context) < 4:
            return
        self._ctx_summarizing = True
        try:
            ctx = list(self._conversation_context)
        except Exception:
            self._ctx_summarizing = False
            return
        _TOOL_EXECUTOR.submit(self._summarize_worker, ctx)

    def _summarize_now_blocking(self):
        """Resumen forzado de la conversación (se llama al cerrar Nia).
        Corre en un hilo aparte con timeout: si la API tarda, el cierre no se
        cuelga, pero en el caso normal alcanza a guardarse antes de salir."""
        try:
            ctx = list(self._conversation_context)
        except Exception:
            return
        if len(ctx) < 2:
            return
        import threading as _th

        def _work():
            try:
                self._summarize_worker(ctx)
            except Exception as e:
                print(f"[JARVIS] Resumen de cierre falló: {e}")

        t = _th.Thread(target=_work, daemon=True, name="nia-summary-close")
        t.start()
        t.join(timeout=12.0)  # espera acotada; os._exit(0) la interrumpe si excede

    def _summarize_worker(self, ctx: list[dict]):
        """Genera el resumen con Gemini y lo guarda en memoria (hilo de trabajo)."""
        try:
            import time
            transcript = "\n".join(
                (("Usuario: " if m.get("role") == "user" else "Nia: ") + str(m.get("text", ""))[:500])
                for m in ctx
            )
            if not transcript.strip():
                return
            from google import genai
            client = genai.Client(api_key=_get_api_key())
            prompt = (
                "Resumí en 2-3 frases en español la información importante de esta conversación "
                "para que una asistente la recuerde a futuro: datos personales, gustos, tareas "
                "pendientes, eventos, decisiones o promesas. "
                "PRESTA ESPECIAL ATENCIÓN a correcciones o negaciones del usuario: si corrigió a "
                "Nia ('no así', 'no era eso', 'te dije que...') o le prohibió/ordenó algo, resumilo "
                "con claridad como 'El usuario prefiere que Nia...' o 'Nia debe recordar no...'. "
                "Esas correcciones son prioridad sobre cualquier otro dato. "
                "NO inventes datos; si no hay nada relevante, respondé únicamente 'Sin novedades relevantes'.\n\n" + transcript
            )
            # Intentar con el modelo principal y degradar a modelos gratuitos si la cuota se agota
            summary = ""
            for model_name in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash"):
                try:
                    resp = client.models.generate_content(model=model_name, contents=prompt)
                    summary = (resp.text or "").strip()
                    if summary:
                        break
                except Exception as e:
                    # 429 = cuota agotada → probar modelo alternativo; otros errores → reintento
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        print(f"[JARVIS] ⏳ Cuota agotada en {model_name}, probando fallback...")
                        continue
                    print(f"[JARVIS] Resumen de conversación falló ({model_name}): {e}")
                    return
            if not summary or "sin novedades" in summary.lower():
                print("[JARVIS] Resumen de conversación: sin datos relevantes.")
                return

            from datetime import datetime
            from memory.memory_manager import update_memory
            stamp = datetime.now(_BA_TZ).strftime("%Y-%m-%d")
            # Resumen acumulativo por día: no sobrescribir el anterior si ya existía.
            # Se guarda como lista para conservar varios momentos del mismo día.
            mem = load_memory()
            ctx_prev = mem.get("context", {}).get(f"conversación_{stamp}", "")
            if isinstance(ctx_prev, dict):
                ctx_prev = ctx_prev.get("value", "")
            if ctx_prev:
                combined = f"{str(ctx_prev).strip()} | {summary}"
                update_memory({"context": {f"conversación_{stamp}": {"value": combined}}})
            else:
                update_memory({"context": {f"conversación_{stamp}": {"value": summary}}})
            print(f"[JARVIS] 📝 Resumen de conversación guardado en memoria ({stamp}).")

            def _trim():
                if len(self._conversation_context) > 4:
                    self._conversation_context = self._conversation_context[-4:]
            loop = getattr(self, "_loop", None)
            if loop:
                try:
                    loop.call_soon_threadsafe(_trim)
                except Exception:
                    pass
        except Exception as e:
            print(f"[JARVIS] Resumen de conversación falló: {e}")
        finally:
            self._ctx_summarizing = False
            self._ctx_summarized_at = time.monotonic()

    def _apply_config(self, cfg: dict):
        """Called from UI thread when user saves settings. Triggers session reconnect."""
        global _cached_api_key
        _cached_api_key = None  # Invalidate cached key so new one is loaded on reconnect
        
        # Actualizar dinámicamente la puerta de ruido sin reiniciar
        self.noise_gate_threshold = float(cfg.get("mic_sensitivity", 0.003))
        
        print("[JARVIS] ⚙️ Config actualizada — reconectando sesión...")
        self.ui.write_log("SYS: Aplicando nueva configuración...")
        if self._reconnect_event and self._loop:
            self._loop.call_soon_threadsafe(self._reconnect_event.set)

    async def _watch_reconnect(self):
        """Task that triggers a graceful reconnect when config changes."""
        if self._reconnect_event:
            await self._reconnect_event.wait()
            raise RuntimeError("Config changed — reconnect requested")

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return

        if getattr(self, "is_sleeping", False):
            # Check if text contains wake word or despierta
            text_lower = text.lower()
            if _wake_word_hit(text_lower):
                self._wake_from_sleep("comando de texto")
            else:
                self.ui.write_log("SYS: 💤 Nia está en modo suspensión. Di 'Nia' o escribe 'despierta' para despertarla.")
                return

        # Audio file: process with Gemini Vision (not the realtime audio session)
        if text.startswith("[AUDIO_FILE]"):
            m = re.search(r'path=([^\s|]+)', text)
            if m:
                asyncio.run_coroutine_threadsafe(
                    self._process_audio_file(m.group(1)), self._loop
                )
            return

        # Check phrase triggers — if one fires, don't also send to Gemini
        if self._fire_phrase_triggers(text):
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def _wake_from_sleep(self, source: str = "voz"):
        """Despierta a Nia de la suspensión, con feedback audible y reset del Vosk."""
        self.is_sleeping = False
        self.ui.set_state("LISTENING")
        self.ui.write_log(f"SYS: 🟢 ¡Despierto! ({source})")
        self._play_wake_sound()
        if getattr(self, "vosk_recognizer", None):
            try:
                self.vosk_recognizer.Reset()
            except Exception:
                pass

    def _play_wake_sound(self):
        """Feedback sonoro de despertar — winsound en Windows, beep en Linux."""
        try:
            import winsound
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
            return
        except Exception:
            pass
        try:
            import sounddevice as _sd
            import numpy as _np
            def _beep():
                try:
                    _sr = 44100
                    _t = _np.linspace(0, 0.15, int(_sr * 0.15), endpoint=False)
                    _tone = (_np.sin(2 * _np.pi * 880 * _t) * 0.15).astype("float32")
                    _sd.play(_tone, _sr)
                except Exception:
                    pass
            threading.Thread(target=_beep, daemon=True).start()
        except Exception:
            pass

    async def _process_audio_file(self, path: str):
        """Transcribe and analyze an audio file via Gemini (separate from realtime session)."""
        try:
            p = Path(path)
            if not p.exists():
                self.ui.write_log(f"❌ Archivo no encontrado: {path}")
                return

            self.ui.set_state("THINKING")
            self.ui.write_log(f"🎵 Procesando audio: {p.name}…")

            data = p.read_bytes()
            ext  = p.suffix.lower().lstrip(".")
            mime_map = {
                "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
                "ogg": "audio/ogg",  "flac": "audio/flac", "aac": "audio/aac",
                "wma": "audio/x-ms-wma", "opus": "audio/opus", "webm": "audio/webm",
            }
            mime = mime_map.get(ext, "audio/mpeg")

            loop = asyncio.get_event_loop()

            def _analyze():
                client = genai.Client(api_key=_get_api_key())
                resp = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Content(parts=[
                            types.Part(text=(
                                f"El usuario adjuntó un archivo de audio: '{p.name}'.\n"
                                "1. Transcribí el contenido del audio.\n"
                                "2. Si es música, identificá la canción/artista si podés.\n"
                                "3. Describí brevemente qué contiene.\n"
                                "Respondé en español."
                            )),
                            types.Part(
                                inline_data=types.Blob(data=data, mime_type=mime)
                            ),
                        ])
                    ],
                )
                return resp.text.strip()

            result = await loop.run_in_executor(_TOOL_EXECUTOR, _analyze)
            self.ui.write_log(f"Nia: {result}")

            # Feed result back into the realtime session so JARVIS can speak it
            if self.session:
                await self.session.send_client_content(
                    turns={"parts": [{"text": f"[RESULTADO AUDIO '{p.name}']\n{result}"}]},
                    turn_complete=True
                )

        except Exception as e:
            traceback.print_exc()
            self.ui.write_log(f"❌ Error procesando audio: {e}")
        finally:
            if not self.ui.muted:
                self.ui.set_state("LISTENING")

    def _fire_phrase_triggers(self, user_text: str) -> bool:
        """
        Check phrase-based automations. Returns True if any trigger fired
        (caller should skip sending the text to Gemini in that case).
        """
        text_lower = user_text.lower()

        # ── Accessibility quick triggers ──────────────────────────────────────
        if any(p in text_lower for p in ["activar seguimiento ocular", "iniciar eye tracking",
                                          "activar control ocular", "encender seguimiento de ojos"]):
            if eye_tracking:
                result = eye_tracking({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener seguimiento ocular", "apagar eye tracking",
                                          "desactivar control ocular"]):
            if eye_tracking:
                result = eye_tracking({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["activar detector de movimientos", "iniciar movimiento",
                                          "activar micromovimientos", "encender control por cabeza"]):
            if micro_movement:
                result = micro_movement({"action": "start"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["detener detector de movimientos", "apagar micromovimientos"]):
            if micro_movement:
                result = micro_movement({"action": "stop"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ " + result)
            return True

        if any(p in text_lower for p in ["simplifica", "simplificar", "dividir en pasos"]):
            for phrase in ["simplifica ", "simplificar ", "dividir en pasos "]:
                if phrase in text_lower:
                    task_text = user_text[len(phrase):].strip()
                    if task_text:
                        if task_simplify:
                            result = task_simplify(task_text)
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ [Simplificado]\n" + result[:300])
                        return True

        if "agregar rutina" in text_lower or "nueva rutina" in text_lower:
            for phrase in ["agregar rutina ", "nueva rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "add", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "completar rutina" in text_lower or "terminar rutina" in text_lower:
            for phrase in ["completar rutina ", "terminar rutina "]:
                if phrase in text_lower:
                    routine_name = user_text[len(phrase):].strip()
                    if routine_name:
                        if routine_gamify:
                            result = routine_gamify({"action": "complete", "name": routine_name})
                        else:
                            self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
                        self.ui.write_log("⚡ " + result)
                        return True

        if "mis rutinas" in text_lower or "ver rutinas" in text_lower or "listar rutinas" in text_lower:
            if routine_gamify:
                result = routine_gamify({"action": "list"})
            else:
                self.ui.write_log("⚠️ Módulo de accesibilidad no disponible.")
            self.ui.write_log("⚡ [Rutinas]\n" + result)
            return True

        # ── Free exploration mode triggers ─────────────────────────────────────
        if any(p in text_lower for p in ["hace lo que quieras", "haz lo que quieras", "explora", "explorá",
                                          "modo exploración", "exploration mode", "free mode",
                                          "nia, hace lo que quieras", "nia explora"]):
            if exploration_mode:
                self.ui.write_log("🎮 NIA: ¡MODO EXPLORACIÓN LIBRE!")
                # Immediate audio feedback so user knows it started
                try:
                    tts = self._tools.get("text_to_speech") or self._tools.get("tts")
                    if tts:
                        tts("¡Empezando exploración! Mirá la pantalla.")
                except Exception:
                    pass
                threading.Thread(target=lambda: exploration_mode({"cycles": 30}, self.ui), daemon=True).start()
            else:
                self.ui.write_log("⚠️ Módulo de exploración no disponible.")
            return True

        if any(p in text_lower for p in ["parate", "detenete", "para", "detente", "stop exploration",
                                          "deja de explorar", "termina la exploración"]):
            if stop_exploration:
                stop_exploration()
                self.ui.write_log("🛑 Exploración detenida.")
            return True

        # ── User-defined phrase automations ───────────────────────────────────
        try:
            triggered = check_phrase_triggers(user_text)
            if triggered:
                for rule in triggered:
                    action = rule.get("action", {})
                    name   = rule.get("name", "?")
                    self.ui.write_log(f"⚡ Automatización: {name}")
                    threading.Thread(
                        target=_rules_run_action, args=(action,), daemon=True
                    ).start()
                return True  # phrase fired → don't also send to Gemini
        except Exception as e:
            print(f"[JARVIS] phrase trigger error: {e}")

        return False

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            changed = self._is_speaking != value
            self._is_speaking = value
        # Solo avisar al PNGtuber en las transiciones: talk_start/talk_end se
        # envían una vez, no en cada chunk de audio (evita resetear el seguimiento
        # de energía de la boca que Nia manda por separado).
        if changed and _pngtuber_send:
            try:
                _pngtuber_send("talk_start" if value else "talk_end")
            except Exception:
                pass
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        # Voz local (Piper) si la nube no está, o si el audio nativo viene
        # fallando (1007s repetidos) y optamos por el respaldo real.
        if not self._loop or not self.session or self._use_local_voice:
            try:
                from actions.tts_local import speak_local
                speak_local(str(text)[:400])
            except Exception:
                pass
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    async def _pngtuber_listener(self):
        """Escucha 'reopen' del PNGtuber (clic en el modelo) para restaurar Nia."""
        import asyncio as _asyncio
        while True:
            try:
                reader, _ = await _asyncio.open_connection("127.0.0.1", 8791)
                while True:
                    line = await reader.readline()
                    if not line:
                        break
                    cmd = line.decode("utf-8", "replace").strip().lower()
                    if cmd == "reopen":
                        try:
                            orb = self.ui._win.orb
                            orb.restore_requested.emit()
                        except Exception:
                            pass
            except Exception:
                pass
            await _asyncio.sleep(3)

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"I'm afraid {tool_name} ran into a problem, sir. {short}")

    def _on_stop_pressed(self):
        """Llamado desde el hilo de la UI al presionar DETENER o ESC."""
        self._stop_requested.set()
        self.set_speaking(False)
        self.ui.write_log("SYS: ⛔ Respuesta detenida.")
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._drain_audio_queue(), self._loop)

    async def _drain_audio_queue(self):
        """Vacía la cola de audio para cortar la reproducción de inmediato."""
        if self.audio_in_queue:
            while not self.audio_in_queue.empty():
                try:
                    self.audio_in_queue.get_nowait()
                except Exception:
                    break
        self.set_speaking(False)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        # Refresh timezone from config each reconnect
        _load_tz()
        now      = datetime.now(_BA_TZ)
        time_str = now.strftime("%A, %d %B %Y — %I:%M:%S %p")
        utc_off  = now.strftime("%z")
        tz_name  = str(_BA_TZ)
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Timezone: {tz_name} (UTC{utc_off})\n"
            f"The current Unix timestamp is: {int(now.timestamp())}\n"
            f"Use this information to calculate exact times for reminders, scheduling, and answering time-related questions.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        # Inject conversation history on reconnects to restore context
        if self._conversation_context:
            ctx_lines = ["[RECENT CONVERSATION HISTORY]"]
            for msg in self._conversation_context[-20:]:  # Últimos 20 para mejor contexto
                prefix = "User:" if msg["role"] == "user" else "Assistant:"
                ctx_lines.append(f"{prefix} {msg['text'][:400]}")
            ctx_lines.append("[END OF HISTORY — continue the conversation naturally]")
            parts.append("\n".join(ctx_lines))

        # Build SpeechConfig
        _voice_name = _get_jarvis_voice()
        _speech_cfg = None
        try:
            _speech_cfg = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=_voice_name
                    )
                )
            )
        except Exception:
            _speech_cfg = None

        # ── Tool toggles: ocultar herramientas desactivadas en config ─────
        _tools = TOOL_DECLARATIONS
        try:
            _disabled = set(json.loads(API_CONFIG_PATH.read_text(encoding="utf-8")).get("disabled_tools", []) or [])
            if _disabled:
                _tools = [d for d in _tools if d.get("name") not in _disabled]
        except Exception:
            pass

        cfg_kwargs: dict = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription=types.AudioTranscriptionConfig(),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": _tools}],
        )
        if _speech_cfg:
            cfg_kwargs["speech_config"] = _speech_cfg

        # Temperature + top_p: higher = more expressive prosody
        # 0.95 for maximum variation without adding latency
        try:
            cfg_kwargs["temperature"] = 0.95
        except Exception:
            pass
        try:
            cfg_kwargs["top_p"] = 0.95
        except Exception:
            pass

        # ── VAD: balanced — natural pacing without adding latency ──────────
        # Try typed objects first; fall back to raw dict (SDK version resilience)
        _vad_applied = False
        try:
            cfg_kwargs["realtime_input_config"] = types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    start_of_speech_sensitivity="START_SENSITIVITY_HIGH",
                    end_of_speech_sensitivity="END_SENSITIVITY_HIGH",
                    prefix_padding_ms=60,
                        silence_duration_ms=350,
                )
            )
            _vad_applied = True
            print("[JARVIS] VAD config aplicado (typed)")
        except Exception:
            pass

        if not _vad_applied:
            try:
                cfg_kwargs["realtime_input_config"] = {
                    "automatic_activity_detection": {
                        "start_of_speech_sensitivity": "START_SENSITIVITY_HIGH",
                        "end_of_speech_sensitivity": "END_SENSITIVITY_HIGH",
                        "prefix_padding_ms": 60,
                        "silence_duration_ms": 350,
                    }
                }
                print("[JARVIS] VAD config aplicado (dict)")
            except Exception:
                print("[JARVIS] VAD config no aplicado")

        # ── Context compression: high threshold — keeps system prompt intact ──
        # Trigger at 80K tokens, target 40K. With a ~15K system prompt, this gives
        # many conversation turns before compression, and 40K easily holds the full
        # personality + instructions. Previously at 12K/6K it was killing the prompt
        # after 1-2 turns, causing robotic repetition.
        try:
            cfg_kwargs["context_window_compression"] = types.ContextWindowCompressionConfig(
                trigger_tokens=80000,
                sliding_window=types.SlidingWindow(target_tokens=40000),
            )
        except Exception:
            pass

        return types.LiveConnectConfig(**cfg_kwargs)

    async def _run_tool(self, name: str, fn, timeout: float = 30.0):
        """Ejecuta una herramienta en el pool con timeout. Si se cuelga, no
        congela a Nia: devuelve un resultado de error en vez de bloquear."""
        loop = asyncio.get_event_loop()
        try:
            r = await asyncio.wait_for(
                loop.run_in_executor(_TOOL_EXECUTOR, fn), timeout=timeout
            )
            if r is None:
                print(f"[JARVIS] ℹ️ Tool '{name}' devolvió None "
                      "(fire-and-forget OK, o fallo silencioso capturado adentro).")
            return r
        except asyncio.TimeoutError:
            print(f"[JARVIS] ⏱️ Tool '{name}' excedió {timeout:.0f}s — interrumpida.")
            return f"La herramienta '{name}' tardó demasiado y fue interrumpida. Intentá de nuevo."
        except Exception as e:
            print(f"[JARVIS] ❌ Tool '{name}' falló: {e}")
            traceback.print_exc()
            return f"La herramienta '{name}' falló: {e}"

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        print(f"[JARVIS] 🔧 {name}  {args}")
        try:
            if record_usage:
                await asyncio.get_event_loop().run_in_executor(
                    _TOOL_EXECUTOR, record_usage, name)
        except Exception:
            pass
        self.ui.set_state("THINKING")



        if name == "shutdown_jarvis":
            self.ui.write_log("SYS: Apagando Nia...")
            # Must quit from Qt main thread — signals are thread-safe
            self.ui._win._shutdown_sig.emit()
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Apagando Nia. ¡Hasta luego, señor!"}
            )

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Memory saved."}
            )

        if name == "remember_correction":
            mistake    = args.get("mistake", "")
            correction = args.get("correction", "")
            if correction:
                stamp = __import__("datetime").datetime.now(_BA_TZ).strftime("%Y-%m-%d")
                update_memory({"preferences": {
                    f"corrección_{stamp}": {
                        "value": correction,
                    }
                }})
                print(f"[Memory] 🔧 Corrección recordada: {correction}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Correction remembered."}
            )

        if name == "forget_memory":
            from memory.memory_manager import forget
            category = args.get("category", "")
            key      = args.get("key", "")
            if category and key:
                forget(category, key)
                print(f"[Memory] 🗑️ forget_memory: {category}/{key}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "Memory forgotten."}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await self._run_tool(name, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "sleep_mode":
                self.is_sleeping = True
                self.ui.write_log("SYS: 💤 Entrando en suspensión local.")
                self.ui.set_state("MUTED")
                # Immediately empty the audio in queue to stop any playing/queued audio
                if self.audio_in_queue:
                    while not self.audio_in_queue.empty():
                        try:
                            self.audio_in_queue.get_nowait()
                        except Exception:
                            break
                self.set_speaking(False)
                result = "Entrando en suspensión absoluta. Cortando transmisión a la nube hasta escuchar 'Nia'."

            elif name == "weather_report":
                r = await self._run_tool(name, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await self._run_tool(name, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "visual_click":
                r = await self._run_tool(name, lambda: visual_click(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "mouse_control":
                r = await self._run_tool(name, lambda: mouse_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "keyboard_control":
                r = await self._run_tool(name, lambda: keyboard_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "youtube_kb":
                if open_recommended_video is None:
                    result = "Módulo youtube_kb no disponible"
                else:
                    action = args.get("action", "")
                    if action == "open_video":
                        ok, t = open_recommended_video()
                        result = f"Video cambiado: {'SI' if ok else 'NO'}. Título: {t[:60]}"
                    elif action == "search":
                        q = args.get("query", "")
                        youtube_search_kb(q)
                        result = f"Búsqueda YouTube: {q}"
                    elif action == "search_and_open":
                        q = args.get("query", "")
                        youtube_search_open_kb(q)
                        result = f"Búsqueda y abrir: {q}"
                    elif action == "play_pause":
                        youtube_play_pause_kb()
                        result = "Play/Pause"
                    elif action == "mute":
                        youtube_mute_kb()
                        result = "Mute"
                    elif action == "fullscreen":
                        youtube_fullscreen_kb()
                        result = "Fullscreen"
                    elif action == "seek_forward":
                        youtube_seek_fwd_kb(int(args.get("seconds", 10)))
                        result = "Seek forward"
                    elif action == "seek_backward":
                        youtube_seek_bwd_kb(int(args.get("seconds", 10)))
                        result = "Seek backward"
                    else:
                        result = f"Acción desconocida: {action}"

            elif name == "web_kb":
                if go_to is None:
                    result = "Módulo web_kb no disponible"
                else:
                    action = args.get("action", "")
                    if action == "go_to":
                        go_to(args.get("url", ""))
                        result = "Navegando..."
                    elif action == "google":
                        google_search(args.get("text", ""))
                        result = "Buscando en Google..."
                    elif action == "youtube_search":
                        youtube_search(args.get("text", ""))
                        result = "Buscando en YouTube..."
                    elif action == "youtube":
                        youtube_search(args.get("text", ""))
                        result = "Buscando en YouTube..."
                    elif action == "type":
                        type_text(args.get("text", ""))
                        result = "Texto escrito"
                    elif action == "enter":
                        try:
                            enter_fn = getattr(__import__('actions.web_kb', fromlist=['enter']), 'enter')
                            enter_fn()
                            result = "Enter presionado"
                        except (ImportError, AttributeError) as e:
                            result = f"Error: web_kb no disponible ({e})"
                    elif action == "tab":
                        tab(args.get("times", 1))
                        result = f"Tab x{args.get('times', 1)}"
                    elif action == "search":
                        search_bar()
                        result = "Barra de búsqueda enfocada"
                    elif action == "new_tab":
                        new_tab()
                        result = "Nueva pestaña"
                    elif action == "close_tab":
                        close_tab()
                        result = "Pestaña cerrada"
                    elif action == "reopen_tab":
                        reopen_closed_tab()
                        result = "Pestaña reabierta"
                    elif action == "switch_tab":
                        switch_tab(args.get("index", 1))
                        result = f"Pestaña {args.get('index', 1)} activada"
                    elif action == "go_back":
                        go_back()
                        result = "Volviendo a la página anterior"
                    elif action == "go_forward":
                        go_forward()
                        result = "Avanzando a la página siguiente"
                    elif action == "reload":
                        try:
                            reload_fn = getattr(__import__('actions.web_kb', fromlist=['reload']), 'reload')
                            reload_fn()
                            result = "Recargando"
                        except (ImportError, AttributeError) as e:
                            result = f"Error: web_kb no disponible ({e})"
                    elif action == "full_browse":
                        t = full_browse_session(args.get("url"))
                        result = f"Exploración finalizada. Página activa: {t}"
                    elif action == "find":
                        search_on_page(args.get("text", ""))
                        result = "Buscando en página"
                    elif action == "navigate":
                        ok, t = navigate_and_click(args.get("tab_presses", 30), args.get("enter_every", 10))
                        result = f"Nav {'OK' if ok else 'no cambió'}: {t}"
                    elif action == "arrow":
                        try:
                            arrow_fn = getattr(__import__('actions.web_kb', fromlist=['arrow']), 'arrow')
                            arrow_fn(args.get("direction", "down"), args.get("times", 1))
                            result = f"Arrow {args.get('direction', 'down')} x{args.get('times', 1)}"
                        except (ImportError, AttributeError) as e:
                            result = f"Error: web_kb no disponible ({e})"
                    elif action == "scroll":
                        try:
                            if args.get("direction", "down") == "down":
                                scroll_fn = getattr(__import__('actions.web_kb', fromlist=['scroll_down']), 'scroll_down')
                            else:
                                scroll_fn = getattr(__import__('actions.web_kb', fromlist=['scroll_up']), 'scroll_up')
                            scroll_fn(args.get("times", 1))
                            result = f"Scroll {args.get('direction', 'down')} x{args.get('times', 1)}"
                        except (ImportError, AttributeError) as e:
                            result = f"Error: web_kb no disponible ({e})"
                    else:
                        result = f"Acción web_kb desconocida: {action}"

            elif name == "desktop_kb":
                if list_windows is None:
                    result = "Módulo desktop_kb no disponible"
                else:
                    action = args.get("action", "")
                    if action == "windows":
                        ws = list_windows()
                        result = json.dumps(ws, indent=2) if ws else "No hay ventanas"
                    elif action == "active":
                        w = get_active_window()
                        result = json.dumps(w, indent=2)
                    elif action == "switch":
                        ok = switch_to_app(args.get("app_class", ""))
                        result = f"Switch a {args.get('app_class', '')}: {'OK' if ok else 'no encontrada'}"
                    elif action == "workspace":
                        go_to_workspace(args.get("num", 1))
                        result = f"Workspace {args.get('num', 1)}"
                    elif action == "close":
                        close_window()
                        result = "Ventana cerrada"
                    elif action == "open":
                        r = open_app({"app_name": args.get("app", "")})
                        result = r
                    elif action == "fullscreen":
                        toggle_fullscreen()
                        result = "Fullscreen toggle"
                    elif action == "maximize":
                        maximize_toggle()
                        result = "Maximize toggle"
                    elif action == "move_ws":
                        move_to_workspace(args.get("num", 1))
                        result = f"Movida a workspace {args.get('num', 1)}"
                    else:
                        result = f"Acción desktop_kb desconocida: {action}"

            elif name == "mouse_kb":
                try:
                    import actions.mouse_kb as mk
                    action = args.get("action", "")
                    if action == "pos":
                        cx, cy = mk.get_cursor_pos()
                        result = f"Cursor en ({cx}, {cy})"
                    elif action == "move":
                        mk.move_to(args.get("x", 0), args.get("y", 0))
                        result = f"Mouse movido a ({args.get('x', 0)}, {args.get('y', 0)})"
                    elif action == "click":
                        mk.click("left")
                        result = "Click izquierdo"
                    elif action in ("move_click", "move_and_click"):
                        mk.move_and_click(args.get("x", 0), args.get("y", 0))
                        result = f"Mouse movido y click en ({args.get('x', 0)}, {args.get('y', 0)})"
                    elif action == "right_click":
                        mk.click("right")
                        result = "Click derecho"
                    elif action == "double_click":
                        mk.double_click()
                        result = "Doble click"
                    elif action == "scroll":
                        mk.scroll(args.get("amount", 1), args.get("x"), args.get("y"))
                        result = f"Scroll {args.get('amount', 1)}"
                    elif action == "drag":
                        mk.drag(args.get("x1", 0), args.get("y1", 0), args.get("x2", 0), args.get("y2", 0))
                        result = f"Drag de ({args.get('x1', 0)},{args.get('y1', 0)}) a ({args.get('x2', 0)},{args.get('y2', 0)})"
                    else:
                        result = f"Acción mouse_kb desconocida: {action}"
                except Exception as e:
                    result = f"Error mouse_kb: {e}"

            elif name == "game_kb":
                try:
                    import actions.game_kb as gk
                    action = args.get("action", "")
                    if action == "look":
                        gk.look(args.get("dx", 0), args.get("dy", 0))
                        result = f"Mirando ({args.get('dx',0)}, {args.get('dy',0)})"
                    elif action == "move":
                        gk.move(args.get("direction", "forward"), args.get("duration", 1.0))
                        result = f"Moviendo {args.get('direction', 'forward')} {args.get('duration', 1.0)}s"
                    elif action == "attack":
                        gk.attack(args.get("duration", 0.5))
                        result = f"Atacando {args.get('duration', 0.5)}s"
                    elif action == "use":
                        gk.use()
                        result = "Usando"
                    elif action == "jump":
                        gk.jump()
                        result = "Saltando"
                    elif action == "sneak":
                        gk.sneak(args.get("duration", 0.5))
                        result = "Agachando"
                    elif action == "sprint":
                        gk.sprint(args.get("duration", 1.0))
                        result = "Corriendo"
                    elif action == "inventory":
                        gk.inventory()
                        result = "Inventario"
                    elif action == "slot":
                        gk.select_slot(args.get("slot", 1))
                        result = f"Slot {args.get('slot', 1)}"
                    elif action == "drop":
                        gk.drop()
                        result = "Soltando"
                    elif action == "mine":
                        gk.mine_block(args.get("direction", "forward"), args.get("duration", 3.0))
                        result = f"Minando {args.get('duration', 3.0)}s"
                    elif action == "place":
                        gk.place_block()
                        result = "Colocando"
                    elif action == "press":
                        gk.key_press(args.get("key", ""))
                        result = f"Tecla {args.get('key', '')}"
                    elif action == "hold":
                        gk.key_down(args.get("key", ""))
                        result = f"Sosteniendo {args.get('key', '')}"
                    elif action == "release":
                        gk.key_up(args.get("key", ""))
                        result = f"Soltando {args.get('key', '')}"
                    elif action == "click":
                        gk.mouse_click(args.get("button", "left"))
                        result = f"Click {args.get('button', 'left')}"
                    elif action == "esc":
                        gk.escape()
                        result = "Esc"
                    elif action == "status":
                        result = json.dumps(gk.game_status(), indent=2)
                    else:
                        result = f"Acción game_kb desconocida: {action}"
                except Exception as e:
                    result = f"Error game_kb: {e}"

            elif name == "screen_click":
                r = await self._run_tool(name, lambda: screen_click(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await self._run_tool(name, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await self._run_tool(name, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await self._run_tool(name, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await self._run_tool(name, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process" or name == "screen_vision":
                target_ws = args.get("workspace", None)
                if target_ws is not None:
                    from actions.desktop import _hyprctl, _get_active_workspace
                    try:
                        original_ws = _get_active_workspace().get("id", 1)
                        _hyprctl(["dispatch", "workspace", str(target_ws)])
                        import time
                        time.sleep(0.3)
                        r = await self._run_tool(name, lambda: screen_vision(parameters=args, player=self.ui))
                        _hyprctl(["dispatch", "workspace", str(original_ws)])
                    except Exception as e:
                        r = f"Error al cambiar al escritorio {target_ws}: {e}"
                else:
                    r = await self._run_tool(name, lambda: screen_vision(parameters=args, player=self.ui))
                result = r or "No pude analizar la imagen/pantalla."

            elif name == "computer_settings":
                action = args.get("action", "")
                if action == "volume":
                    val = args.get("value", "")
                    try:
                        import pyautogui
                        # Si es un número absoluto (ej: '50')
                        if str(val).isdigit():
                            target = int(val)
                            try:
                                # Linux: usar pactl (PulseAudio) o amixer (ALSA)
                                import subprocess
                                scalar = max(0, min(100, target))
                                # Intentar PulseAudio primero
                                rc = subprocess.run(
                                    ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{scalar}%"],
                                    capture_output=True, timeout=5,
                                )
                                if rc.returncode == 0:
                                    result = f"Volumen ajustado al {scalar}%."
                                else:
                                    # Fallback a ALSA
                                    rc = subprocess.run(
                                        ["amixer", "set", "Master", f"{scalar}%"],
                                        capture_output=True, timeout=5,
                                    )
                                    if rc.returncode == 0:
                                        result = f"Volumen ajustado al {scalar}%."
                                    else:
                                        result = f"Error ajustando volumen: pulseaudio/amixer no disponible."
                            except Exception as e:
                                result = f"Error ajustando volumen absoluto: {e}"
                        else:
                            # Comando relativo: up, down, mute
                            if "up" in val.lower() or "subir" in val.lower():
                                pyautogui.press("volumeup", presses=5)
                                result = "Volumen subido."
                            elif "down" in val.lower() or "bajar" in val.lower():
                                pyautogui.press("volumedown", presses=5)
                                result = "Volumen bajado."
                            elif "mute" in val.lower() or "silenciar" in val.lower():
                                pyautogui.press("volumemute")
                                result = "Volumen silenciado."
                            else:
                                result = f"Acción de volumen no reconocida: {val}"
                    except Exception as ve:
                        result = f"Error en control de volumen: {ve}"
                else:
                    if action in ["window_minimize", "minimize"]:
                        if gw:
                            try:
                                window = gw.getActiveWindow()
                                if window: window.minimize()
                                result = "Ventana minimizada."
                            except Exception as e:
                                result = f"Error al minimizar: {e}"
                        else:
                            result = "Librería pygetwindow no disponible."
                    elif action in ["window_maximize", "maximize"]:
                        if gw:
                            try:
                                window = gw.getActiveWindow()
                                if window: window.maximize()
                                result = "Ventana maximizada."
                            except Exception as e:
                                result = f"Error al maximizar: {e}"
                        else:
                            result = "Librería pygetwindow no disponible."
                    else:
                        r = await self._run_tool(name, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                        result = r or "Done."

            elif name == "desktop_control":
                r = await self._run_tool(name, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await self._run_tool(name, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await self._run_tool(name, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await self._run_tool(name, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await self._run_tool(name, lambda: file_processor(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "computer_control":
                r = await self._run_tool(name, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await self._run_tool(name, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await self._run_tool(name, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "google_calendar":
                r = await self._run_tool(name, lambda: google_calendar(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "spotify_control":
                r = await self._run_tool(name, lambda: spotify_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "daily_summary":
                r = await self._run_tool(name, lambda: daily_summary(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "tts_local":
                r = await self._run_tool(name, lambda: tts_local(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "usage_stats":
                r = await self._run_tool(name, lambda: usage_stats(parameters=args))
                result = r or "Done."

            elif name == "rgb_control":
                r = await self._run_tool(name, lambda: rgb_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "scheduler":
                r = await self._run_tool(name, lambda: scheduler(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "google_drive":
                r = await self._run_tool(name, lambda: google_drive(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "google_maps":
                r = await self._run_tool(name, lambda: google_maps(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "gmail_control":
                r = await self._run_tool(name, lambda: gmail_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "rules_engine":
                r = await self._run_tool(name, lambda: rules_engine(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "proactive_automation":
                from actions.proactive_automation import proactive_automation as _proactive_fn
                r = await self._run_tool(name, lambda: _proactive_fn(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "self_agent":
                r = await self._run_tool(name, lambda: self_agent(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "exploration_mode":
                r = await self._run_tool(name, lambda: exploration_mode(parameters=args, player=self.ui))
                result = r or "Exploración completada."

            elif name == "stop_exploration":
                stop_exploration()
                result = "Exploración detenida."

            elif name == "user_profile":
                r = await self._run_tool(name, lambda: user_profile(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "goals":
                r = await self._run_tool(name, lambda: goals(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "git_control":
                r = await self._run_tool(name, lambda: git_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "codebase":
                r = await self._run_tool(name, lambda: codebase(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "knowledge_base":
                r = await self._run_tool(name, lambda: knowledge_base(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "timer":
                r = await self._run_tool(name, lambda: timer(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "clipboard":
                r = await self._run_tool(name, lambda: clipboard(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_search":
                r = await self._run_tool(name, lambda: code_search(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_editor":
                r = await self._run_tool(name, lambda: code_editor(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shell_exec":
                r = await self._run_tool(name, lambda: shell_exec(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "project_analyzer":
                r = await self._run_tool(name, lambda: project_analyzer(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "skill_manager":
                r = await self._run_tool(name, lambda: skill_manager(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "web_fetch":
                r = await self._run_tool(name, lambda: web_fetch(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "pdf_reader":
                r = await self._run_tool(name, lambda: pdf_reader(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "csv_analyzer":
                r = await self._run_tool(name, lambda: csv_analyzer(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "image_reader":
                r = await self._run_tool(name, lambda: image_reader(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_executor":
                r = await self._run_tool(name, lambda: code_executor(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "multi_step_executor":
                r = await self._run_tool(name, lambda: multi_step_executor(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "web_crawler":
                r = await self._run_tool(name, lambda: web_crawler(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "persistent_context":
                r = await self._run_tool(name, lambda: persistent_context(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "self_improve":
                r = await self._run_tool(name, lambda: self_improve(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "real_vision":
                r = await self._run_tool(name, lambda: real_vision(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "process_manager":
                r = await self._run_tool(name, lambda: process_manager(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "package_manager":
                r = await self._run_tool(name, lambda: package_manager(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_watcher":
                r = await self._run_tool(name, lambda: file_watcher(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "env_manager":
                r = await self._run_tool(name, lambda: env_manager(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "backup_manager":
                r = await self._run_tool(name, lambda: backup_manager(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "test_runner":
                r = await self._run_tool(name, lambda: test_runner(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "doc_generator":
                r = await self._run_tool(name, lambda: doc_generator(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "multi_search":
                r = await self._run_tool(name, lambda: multi_search(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "obsidian_bridge":
                r = await self._run_tool(name, lambda: obsidian_bridge(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "whatsapp":
                r = await self._run_tool(name, lambda: whatsapp(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "social_media":
                r = await self._run_tool(name, lambda: social_media(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "windows_settings":
                r = await self._run_tool(name, lambda: windows_settings(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "document_creator":
                r = await self._run_tool(name, lambda: document_creator(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "image_generation":
                r = await self._run_tool(name, lambda: image_generation(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "smart_home":
                r = await self._run_tool(name, lambda: smart_home(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "system_monitor":
                r = await self._run_tool(name, lambda: system_monitor(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "tiktok_analyzer":
                r = await self._run_tool(name, lambda: tiktok_analyzer(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "arca_invoice":
                r = await self._run_tool(name, lambda: arca_invoice(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "accessibility":
                r = await self._run_tool(name, lambda: accessibility(parameters=args, player=self.ui))
                result = r or "Done."



            elif name == "morning_brief":
                r = await self._run_tool(name, lambda: morning_brief(parameters=args, player=self.ui))
                result = r or "Aquí está tu informe del día."

            elif name == "vision_guardian":
                r = await self._run_tool(name, lambda: vision_guardian(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "obs_control":
                r = await self._run_tool(name, lambda: obs_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "recall_memory":
                r = await self._run_tool(name, lambda: recall_memory(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "ntfy_notify":
                r = await self._run_tool(name, lambda: ntfy_notify(parameters=args, player=self.ui))
                result = r or "Notificación enviada."

            elif name == "delegate_to_subagent":
                try:
                    from agent.runner import get_runner
                    subagent = args.get("subagent", "auto")
                    goal = args.get("goal", "")
                    context = args.get("context", "")
                    if not goal:
                        result = "Necesito una tarea (goal) para delegar."
                    else:
                        self.ui.write_log(f"🤖 Delegando tarea al subagente '{subagent}'...")
                        task_id = get_runner().submit(
                            subagent, goal, context, player=self.ui, speak=self.speak)
                        result = (f"Tarea delegada al subagente '{subagent}' (ID {task_id}). "
                                  f"Trabaja en paralelo; te aviso cuando esté lista.")
                except Exception as sub_e:
                    result = f"Error al delegar la tarea: {sub_e}"

            elif name == "subagent_status":
                try:
                    from agent.runner import get_runner
                    st = get_runner().status(args.get("task_id", ""))
                    if st is None:
                        result = "No encontré ninguna tarea con ese ID."
                    elif st["status"] == "running":
                        result = f"La tarea {st['id']} ({st['subagent']}) sigue en ejecución."
                    else:
                        result = (f"Tarea {st['id']} ({st['subagent']}) terminada "
                                  f"en {st.get('duration', '?')}:\n{st['result']}")
                except Exception as sub_e:
                    result = f"Error al consultar el estado: {sub_e}"

            elif name == "accessibility_overlay":
                r = await self._run_tool(name, lambda: accessibility_overlay(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "openrouter_agent":
                if openrouter_agent:
                    # Se delega la tarea a OpenRouter
                    self.ui.write_log("🤖 Delegando tarea a OpenRouter...")
                    r = await self._run_tool(name, lambda: openrouter_agent(
                            query=args.get("query", ""),
                            model=args.get("model", "google/gemini-2.5-flash")
                        ))
                    result = r or "Error al procesar con OpenRouter."
                else:
                    result = "Módulo openrouter_agent no encontrado."

            elif name == "terminal_agent":
                if terminal_agent:
                    self.ui.write_log("⚠️ Ejecutando en Terminal...")
                    r = await self._run_tool(name, lambda: terminal_agent(parameters=args, player=self.ui))
                    result = r or "Comando ejecutado."
                else:
                    result = "Módulo terminal_agent no encontrado."

            elif name == "native_ui":
                if native_ui:
                    self.ui.write_log("💻 UI Nativa en acción...")
                    r = await self._run_tool(name, lambda: native_ui(parameters=args, player=self.ui))
                    result = r or "Acción de UI completada."
                else:
                    result = "Módulo native_ui no encontrado."

            elif name == "jarvis_ui_control":
                action_ui = args.get("action", "").lower()
                widget_name = args.get("widget", "").lower()
                if action_ui == "minimize":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showMinimized"):
                            QMetaObject.invokeMethod(self.ui._win, "showMinimized", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "iconify"):
                            self.ui.root.after(0, self.ui.root.iconify)
                        result = "Interfaz de usuario minimizada."
                    except Exception as ui_e:
                        result = f"Error al minimizar: {ui_e}"
                elif action_ui == "restore":
                    try:
                        if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                            QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                            QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                        elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                            def _restore():
                                self.ui.root.deiconify()
                                self.ui.root.attributes("-topmost", True)
                                self.ui.root.attributes("-topmost", False)
                            self.ui.root.after(0, _restore)
                        result = "Interfaz de usuario restaurada."
                    except Exception as ui_e:
                        result = f"Error al restaurar: {ui_e}"
                elif action_ui == "hide_all":
                    if hasattr(self.ui, "_win") and hasattr(self.ui._win, "hide_all_widgets"):
                        QMetaObject.invokeMethod(self.ui._win, "hide_all_widgets", Qt.ConnectionType.QueuedConnection)
                    result = "Todos los widgets ocultados."
                elif action_ui in ("show", "hide", "toggle"):
                    if widget_name == "main_window" or not widget_name:
                        if action_ui == "show":
                            try:
                                if hasattr(self.ui, "_win") and hasattr(self.ui._win, "showNormal"):
                                    QMetaObject.invokeMethod(self.ui._win, "showNormal", Qt.ConnectionType.QueuedConnection)
                                    QMetaObject.invokeMethod(self.ui._win, "activateWindow", Qt.ConnectionType.QueuedConnection)
                                elif hasattr(self.ui, "root") and hasattr(self.ui.root, "deiconify"):
                                    def _restore():
                                        self.ui.root.deiconify()
                                        self.ui.root.attributes("-topmost", True)
                                        self.ui.root.attributes("-topmost", False)
                                    self.ui.root.after(0, _restore)
                                result = "Interfaz de usuario restaurada."
                            except Exception as ui_e:
                                result = f"Error al restaurar: {ui_e}"
                        else:
                            self.ui.write_log("__hide__")
                            result = "Todos los widgets ocultados."
                    else:
                        valid = {"weather", "spotify", "system", "notes", "todo", "files"}
                        if widget_name not in valid:
                            result = f"Widget '{widget_name}' no disponible. Válidos: {', '.join(sorted(valid))}."
                        else:
                            if hasattr(self.ui, "_win") and hasattr(self.ui._win, "widget_action"):
                                QMetaObject.invokeMethod(
                                    self.ui._win, "widget_action",
                                    Qt.ConnectionType.QueuedConnection,
                                    Q_ARG(str, widget_name), Q_ARG(str, action_ui),
                                )
                            result = f"Widget '{widget_name}' {'mostrado' if action_ui in ('show', 'toggle') else 'ocultado'}."
                else:
                    result = f"Acción de UI desconocida: {action_ui}"

            elif name == "self_edit":
                from actions.self_edit import self_edit as _self_edit_fn
                r = await self._run_tool(name, lambda: _self_edit_fn(parameters=args, player=self.ui))
                result = r or "Editado."

            elif name == "auto_programmer":
                from actions.auto_programmer import auto_programmer as _ap_fn
                r = await self._run_tool(name, lambda: _ap_fn(parameters=args, player=self.ui))
                result = r or "Programado."

            elif name == "contextual_control":
                from actions.contextual_control import contextual_control as _cc_fn
                r = await self._run_tool(name, lambda: _cc_fn(parameters=args, player=self.ui))
                result = r or "Contexto ajustado."

            elif name == "camera_bus":
                from actions.camera_bus import camera_bus as _cb_fn
                r = await self._run_tool(name, lambda: _cb_fn(parameters=args, player=self.ui))
                result = r or "Cámara controlada."

            elif name == "tool_creator":
                from actions.tool_creator import tool_creator as _tc_fn
                r = await self._run_tool(name, lambda: _tc_fn(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Herramienta creada."

            elif name == "unified_communications":
                from actions.unified_communications import unified_communications as _uc_fn
                r = await self._run_tool(name, lambda: _uc_fn(parameters=args, player=self.ui))
                result = r or "Comunicación enviada."

            elif name == "smart_file_organizer":
                from actions.smart_file_organizer import smart_file_organizer as _sfo_fn
                r = await self._run_tool(name, lambda: _sfo_fn(parameters=args, player=self.ui))
                result = r or "Archivos organizados."

            else:
                # Intento de cargar herramienta dinámica (tool_creator u otras)
                import importlib
                import inspect
                try:
                    module = importlib.import_module(f"actions.{name}")
                    func = getattr(module, name)
                    sig = inspect.signature(func)
                    kwargs = {"parameters": args, "player": self.ui}
                    if "speak" in sig.parameters: kwargs["speak"] = self.speak
                    r = await self._run_tool(name, lambda: func(**kwargs))
                    result = r or f"Herramienta {name} ejecutada."
                except Exception as dyn_e:
                    result = f"Unknown tool: {name}. (Dynamic load failed: {dyn_e})"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        # Record action for habit learning (fire-and-forget, non-blocking)
        if record_action:
            threading.Thread(target=lambda: record_action(name, args), daemon=True).start()

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _keepalive_loop(self):
        """Envía audio silencioso cada 5 min para mantener viva la sesión Gemini Live."""
        import numpy as _np
        _KEEPALIVE_INTERVAL = 300  # 5 minutos
        while True:
            await asyncio.sleep(_KEEPALIVE_INTERVAL)
            try:
                if self.session and not self._is_speaking:
                    # Audio silencioso (16kHz, 0.5s)
                    silent = _np.zeros(8000, dtype=_np.int16).tobytes()
                    await self.session.send_realtime_input(
                        media={"data": silent, "mime_type": "audio/pcm;rate=16000"}
                    )
                    print("[JARVIS] 🔁 Keepalive enviado")
            except Exception as e:
                print(f"[JARVIS] ⚠️ Keepalive falló: {e}")

    async def _send_realtime(self):
        # Enviar audio del mic al modelo. Reglas de fallo:
        # - Un error puntual (20ms) es inaudible: se DESCARTA el chunk y se sigue
        #   con el siguiente. Si reintentáramos el MISMO chunk (como antes), la
        #   cola del mic se llenaba, el audio del usuario se descartaba y el
        #   modelo dejaba de oírlo → "el modelo no le sigue la voz".
        # - 3 fallos seguidos (~300ms) = la sesión está muerta: lanzamos para que
        #   run() reconecte RÁPIDO. Sin esto, la sesión muerta se detectaba recién
        #   a los 15 min (receive timeout) y Nia quedaba muda y sorda un buen rato.
        consecutive_send_fails = 0
        while True:
            msg = await self.out_queue.get()
            try:
                await self.session.send_realtime_input(media=msg)
                consecutive_send_fails = 0
            except Exception as e:
                print(f"[JARVIS] ❌ send_realtime_input: {type(e).__name__}: {str(e)[:120]}")
                consecutive_send_fails += 1
                if consecutive_send_fails >= 3:
                    print("[JARVIS] ⚠️ Sesión de envío caída — forzando reconexión...")
                    raise RuntimeError(f"send_failed: {type(e).__name__}: {e}") from e
                await asyncio.sleep(0.1)

    def _mic_callback(self, indata, frames, time_info, status):
        if getattr(self, "is_sleeping", False):
            if getattr(self, "vosk_recognizer", None):
                audio_data = indata.tobytes()
                try:
                    self.vosk_recognizer.AcceptWaveform(audio_data)
                except Exception:
                    return
                # 1) Hipótesis parcial: despertar solo si la frase es reciente
                try:
                    partial = json.loads(self.vosk_recognizer.PartialResult()).get("partial", "")
                    if _wake_word_recent(partial):
                        self._wake_from_sleep("voz")
                        return
                except Exception:
                    pass
                # 2) Resultado final: alta precisión, cualquier posición
                try:
                    final = json.loads(self.vosk_recognizer.Result()).get("text", "")
                    if final and _wake_word_hit(final):
                        self._wake_from_sleep("voz")
                except Exception:
                    pass
            return

        with self._speaking_lock:
            jarvis_speaking = self._is_speaking
        if not jarvis_speaking and not self.ui.muted:
            # Calculate RMS audio level for sphere visualization
            rms = 0.0
            try:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
                self.ui.set_audio_level(min(1.0, rms * 18))
            except Exception:
                pass

            # Filtro de Puerta de Ruido Adaptativo (VAD local dinámico en tiempo real)
            import time
            now = time.time()
            threshold = getattr(self, "noise_gate_threshold", 0.003)

            # Inicializar y actualizar el piso de ruido dinámico (rolling minimum)
            if not hasattr(self, "_noise_floor_samples"):
                self._noise_floor_samples = []
                self._last_noise_floor_update = now

            # Tomar muestra cada 100ms
            if now - getattr(self, "_last_noise_floor_update", 0.0) > 0.1:
                self._noise_floor_samples.append(rms)
                self._last_noise_floor_update = now
                # Mantener últimas 50 muestras (~5 segundos)
                if len(self._noise_floor_samples) > 50:
                    self._noise_floor_samples.pop(0)

                # El ruido base ambiental es el mínimo RMS de los últimos 5s
                self._ambient_noise_floor = min(self._noise_floor_samples)

            ambient_floor = getattr(self, "_ambient_noise_floor", 0.001)
            # Si el usuario configura una sensibilidad alta (umbral muy bajo < 0.001), respetamos su umbral exacto
            # De lo contrario, usamos un multiplicador dinámico optimizado de 1.3 (antes 1.5) para mayor responsividad
            if threshold < 0.0012:
                dynamic_threshold = threshold
            else:
                dynamic_threshold = max(threshold, ambient_floor * 1.3)

            if rms > dynamic_threshold:
                self.last_speech_time = now

            # Si estamos dentro del tiempo de resaca (hangover) de 0.5s, transmitir el paquete
            if now - getattr(self, "last_speech_time", 0.0) < 0.5:
                data = indata.tobytes()
                # Silently drop if queue is full (during long tool calls)
                def _safe_put(q, item):
                    try:
                        q.put_nowait(item)
                    except Exception:
                        pass  # Queue full — discard; prevents QueueFull crash
                _loop = getattr(self, "_loop", None)
                if _loop is not None:
                    _loop.call_soon_threadsafe(
                        _safe_put, self.out_queue, {"data": data, "mime_type": "audio/pcm;rate=16000"}
                    )
            else:
                # Descartar paquete en silencio para evitar alucinaciones en la nube
                pass
        elif jarvis_speaking:
            # When JARVIS is speaking, also update level (from playback perspective)
            try:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2))) / 32768.0
                self.ui.set_audio_level(min(1.0, rms * 15))
            except Exception:
                pass

    # --- Hot-swap de audio: los audífonos y el altavoz se eligen solos ---
    # El sink (Headphones/Speaker) ya lo cambia ACP al conectar/desconectar el
    # jack, y el stream de reproducción se re-enlaza solo (device="default").
    # Aquí solo aseguramos que el mic por defecto siga al jack: el mic del
    # headset (Mic2/Stereo) cuando hay audífonos, el mic interno (Mic1/Digital)
    # cuando no.

    def _sh(self, args):
        return subprocess.run(args, capture_output=True, text=True).stdout

    def _mic_jack_plugged(self):
        try:
            out = self._sh(["amixer", "-c", "0", "cget", "numid=11"])
            m = re.search(r": values=(\w+)", out)
            return bool(m and m.group(1) == "on")
        except Exception:
            return False

    def _current_default_source_id(self):
        try:
            lines = self._sh(["wpctl", "status"]).splitlines()
            for i, l in enumerate(lines):
                if "Sources:" in l:
                    for s in lines[i + 1:i + 5]:
                        m = re.search(r"\*\s+(\d+)\.", s.strip())
                        if m:
                            return int(m.group(1))
                    break
        except Exception:
            pass
        return None

    def _source_node_id(self, name_part):
        try:
            d = json.loads(self._sh(["pw-dump"]))
        except Exception:
            return None
        for o in d:
            if o.get("type") == "PipeWire:Interface:Node":
                p = o.get("info", {}).get("props", {})
                if p.get("media.class") == "Audio/Source" and name_part in p.get("node.name", ""):
                    return o["id"]
        return None

    def _source_is_muted(self, source_id):
        try:
            out = self._sh(["wpctl", "get-volume", str(source_id)])
            return "MUTED" in out
        except Exception:
            return False

    async def _monitor_audio_follow(self):
        while True:
            try:
                headset = self._mic_jack_plugged()
                wanted = "HiFi__Mic2__source" if headset else "HiFi__Mic1__source"
                wanted_id = self._source_node_id(wanted)
                cur_id = self._current_default_source_id()
                if wanted_id and cur_id != wanted_id:
                    self._sh(["wpctl", "set-default", str(wanted_id)])
                    self._mic_restart = True
                # Self-heal: la fuente activa nunca debe quedar muteada, o Nia
                # deja de oír al usuario ("me habla y no responde"). PipeWire
                # recria el nodo al conectar/desconectar el jack y el nuevo
                # viene MUTEADO por defecto.
                if wanted_id:
                    if self._source_is_muted(wanted_id):
                        self._sh(["wpctl", "set-mute", str(wanted_id), "0"])
                        print("[JARVIS] 🎤 Mic desmutado (self-heal)")
                elif cur_id and self._source_is_muted(cur_id):
                    self._sh(["wpctl", "set-mute", str(cur_id), "0"])
                    print("[JARVIS] 🎤 Mic desmutado (self-heal, default)")
            except Exception:
                pass
            await asyncio.sleep(1.5)

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic iniciado")
        while True:
            try:
                with sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    device="default",
                    callback=self._mic_callback,
                ):
                    print("[JARVIS] 🎤 Mic stream open")
                    while not self._mic_restart:
                        await asyncio.sleep(0.01)  # 10ms — máxima responsividad del mic
                    self._mic_restart = False
            except Exception as e:
                print(f"[JARVIS] ❌ Mic: {e}")
                raise


    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv iniciado")
        out_buf, in_buf = [], []
        _first_chunk   = True
        _last_tool     = None   # track which tool was executing when error hit
        # La sesión Live expira sola a ~15 min y el servidor envía el cierre.
        # Con 120s se reconectaba cada 2 min de silencio (churn innecesario).
        # 900s = solo red de seguridad para conexiones colgadas.
        _RECV_TIMEOUT  = 900.0

        try:
            _receive_iter = self.session.receive().__aiter__()
            while True:
                try:
                    response = await asyncio.wait_for(
                        _receive_iter.__anext__(),
                        timeout=_RECV_TIMEOUT
                    )
                except StopAsyncIteration:
                    _receive_iter = self.session.receive().__aiter__()
                    # Micro-pausa: si la sesión está cerrada, recrear el iterador
                    # devolvería StopAsyncIteration al instante en un bucle de CPU.
                    # El sleep da chance al send_failed de disparar la reconexión.
                    await asyncio.sleep(0.05)
                    continue
                except TimeoutError:
                    # Conexión colgada: el servidor no envió nada en 900s.
                    # Error controlado → reconexión rápida (no es fallo de API,
                    # ni debe matar la sesión: el TaskGroup la cierra y run()
                    # vuelve a conectar). Marca reconocible para el handler.
                    print("[JARVIS] ⏱️ Recv timeout (sin datos del servidor en 15 min). Reconectando...")
                    raise TimeoutError("receive_timeout: conexión colgada") from None

                if response.data:
                    if not self._stop_requested.is_set() and not getattr(self, "is_sleeping", False):
                        self.audio_in_queue.put_nowait(response.data)

                if response.server_content:
                    sc = response.server_content

                    if sc.output_transcription and sc.output_transcription.text:
                        txt = _clean_transcript(sc.output_transcription.text)
                        if txt:
                            out_buf.append(txt)
                            if _first_chunk:
                                self.ui.clear_jarvis_response()
                                _first_chunk = False
                            self.ui.stream_jarvis_chunk(txt)

                    if sc.input_transcription and sc.input_transcription.text:
                        txt = _clean_transcript(sc.input_transcription.text)
                        if txt:
                            in_buf.append(txt)

                    if sc.turn_complete:
                        self._stop_requested.clear()
                        if self._turn_done_event:
                            self._turn_done_event.set()
                        full_in = " ".join(in_buf).strip()
                        if full_in:
                            self.ui.write_log(f"Tú: {full_in}")
                            self._fire_phrase_triggers(full_in)
                            self._conversation_context.append({"role": "user", "text": full_in})
                        full_out = " ".join(out_buf).strip()
                        if full_out:
                            self._conversation_context.append({"role": "assistant", "text": full_out})
                        # Keep last 30 exchanges (más contexto para reconexiones)
                        if len(self._conversation_context) > 30:
                            self._conversation_context = self._conversation_context[-30:]
                        in_buf = []
                        out_buf = []
                        _first_chunk = True

                if response.tool_call:
                    self.ui.clear_jarvis_response()
                    _first_chunk = True
                    fcs = response.tool_call.function_calls
                    for fc in fcs:
                        print(f"[JARVIS] 📞 {fc.name}")
                        _last_tool = fc.name
                        # Guardar tool call en contexto ANTES de ejecutar
                        self._conversation_context.append({
                            "role": "assistant",
                            "text": f"[Tool call: {fc.name}({json.dumps(fc.args or {}, ensure_ascii=False)[:200]})]"
                        })
                    # Ejecutar tools en background para NO bloquear receive loop
                    # Esto permite que el audio siga fluyendo durante la tool
                    async def _run_and_respond():
                        nonlocal _last_tool
                        if len(fcs) > 1:
                            tasks = [asyncio.create_task(self._execute_tool(fc)) for fc in fcs]
                            fn_responses = list(await asyncio.gather(*tasks))
                        else:
                            fn_responses = [await self._execute_tool(fcs[0])]
                        try:
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                            # Guardar resultado de tool en contexto
                            for resp in fn_responses:
                                result_text = str(resp.response.get("result", ""))[:200]
                                self._conversation_context.append({
                                    "role": "user",
                                    "text": f"[Tool result: {resp.name} → {result_text}]"
                                })
                            _last_tool = None  # only clear AFTER successful send
                        except Exception as tool_err:
                            print(f"[JARVIS] ❌ send_tool_response failed: {tool_err}")
                            raise
                    # Crear task pero NO await — que corra en background
                    asyncio.create_task(_run_and_respond())
        except Exception as e:
            msg  = str(e)
            code = getattr(e, "status_code", 0) or getattr(e, "code", 0) or 0
            etype = type(e).__name__
            # Detect 1011 (internal server error) regardless of exception type
            if code == 1011 or "1011" in msg or "Internal error" in msg:
                tool_info = f" durante '{_last_tool}'" if _last_tool else ""
                print(f"[JARVIS] ⚡ API 1011{tool_info} — reconectando...")
                self._api_1011_tool = _last_tool
            else:
                print(f"[JARVIS] ❌ Recv ({etype}): {msg[:200]}")
                traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play iniciado")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=PLAY_CHUNK_SIZE,
            device="default",
        )
        stream.start()

        # Jitter buffer: accumulate a few chunks before playback to prevent underruns
        _jitter_buf: list[bytes] = []
        _JITTER_TARGET = 1  # ~20ms — start playback ASAP for low latency

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.05   # 50ms — faster turn-complete detection
                    )
                except asyncio.TimeoutError:
                    # Must check turn_done + empty BEFORE jitter guard,
                    # otherwise 1-2 stuck chunks in jitter_buf prevent
                    # ever reaching the turn_done check → infinite SPEAKING loop.
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        # Drain remaining jitter buffer before stopping
                        for buffered in _jitter_buf:
                            await asyncio.to_thread(stream.write, buffered)
                        _jitter_buf.clear()
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue

                self.set_speaking(True)
                _jitter_buf.append(chunk)

                # Once we have enough chunks buffered, drain them to the output stream
                if len(_jitter_buf) >= _JITTER_TARGET:
                    for buffered in _jitter_buf:
                        await asyncio.to_thread(stream.write, buffered)
                    _jitter_buf.clear()
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()


    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        reconnect_delay   = 1.0
        consecutive_fails = 0

        while True:
            try:
                print("[JARVIS] 🔌 Conectando...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._loop            = asyncio.get_event_loop()
                    self.audio_in_queue   = asyncio.Queue()
                    self.out_queue        = asyncio.Queue(maxsize=100)  # ~8s de buffer — evita drops por latencia de red
                    self._turn_done_event = asyncio.Event()
                    self._reconnect_event = asyncio.Event()
                    self._mic_restart     = False
                    self._stop_requested.clear()   # fresh session → fresh state

                    print("[JARVIS] ✅ Conectado.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: Nia en línea.")
                    tg.create_task(self._pngtuber_listener())
                    reconnect_delay   = 1.0   # reset backoff on successful connection
                    consecutive_fails = 0
                    self._api_1011_tool = None   # clear 1011 tool tracker

                    # ── First-connect extras ──────────────────────────────────
                    if self._first_connect:
                        self._first_connect = False
                        # Pre-warm semantic memory index in background
                        try:
                            from memory.semantic_memory import ensure_indexed
                            _TOOL_EXECUTOR.submit(ensure_indexed)
                        except Exception as _me:
                            print(f"[JARVIS] Semantic index pre-warm error: {_me}")
                        # Start Vision Guardian if enabled
                        try:
                            _start_vision_guardian(
                                inject_fn=self._inject_text,
                                speaking_fn=lambda: self._is_speaking,
                            )
                        except Exception as _vge:
                            print(f"[JARVIS] VisionGuardian init error: {_vge}")
                        # Start autonomous agent in background
                        try:
                            from actions.self_agent import SelfAgent, _agent_instance
                            _nia_agent = SelfAgent(player=self.ui)
                            _agent_instance = _nia_agent   # registrar el global para status/stop reales
                            _nia_agent.start_loop(interval=180)
                            self.ui.write_log("🧠 Nia inició su pensamiento autónomo (cada 180s)")
                        except Exception as _ae:
                            print(f"[JARVIS] SelfAgent init error: {_ae}")

                        # Auto morning brief (6am–12pm, once per day)
                        _hour = __import__("datetime").datetime.now().hour
                        if 6 <= _hour < 12 and not already_briefed_today():
                            async def _auto_brief():
                                await asyncio.sleep(1)  # let session settle
                                await self.session.send_client_content(
                                    turns={"parts": [{"text": "[AUTO] Dame el informe matutino del día."}]},
                                    turn_complete=True
                                )
                                mark_briefed()
                            tg.create_task(_auto_brief())

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._monitor_audio_follow())
                    tg.create_task(self._watch_reconnect())
                    tg.create_task(self._keepalive_loop())

            except Exception as e:
                exceptions = e.exceptions if isinstance(e, ExceptionGroup) else [e]

                is_handshake_timeout = False
                is_config_reconnect  = False
                is_receive_timeout   = False
                is_send_failed       = False
                for exc in exceptions:
                    msg = str(exc)
                    if "Config changed" in msg:
                        # Intentional reconnect triggered by config change — fast, no backoff
                        is_config_reconnect = True
                        consecutive_fails = 0
                    elif "send_failed" in msg:
                        # Sesión muerta detectada por el envío del mic (3 fallos
                        # seguidos). Misma clase que receive_timeout: reconexión
                        # rápida en 1s, sin backoff ni resumen de contexto.
                        is_send_failed = True
                        print("[JARVIS] ⚠️ Sesión de envío caída — reconectando en 1s...")
                    elif isinstance(exc, TimeoutError) and "receive_timeout" in msg:
                        # Conexión colgada (sin datos del servidor en 15 min).
                        # Reconexión rápida y silenciosa, sin backoff ni resumen.
                        is_receive_timeout = True
                        print("[JARVIS] ⏱️ Conexión colgada — reconectando en 1s...")
                    elif "timed out during opening handshake" in msg or (
                        isinstance(exc, TimeoutError) and "handshake" in msg
                    ):
                        # Timeout de WebSocket al conectar — error de red transitorio.
                        # NO incrementar consecutive_fails: sólo reintento rápido.
                        is_handshake_timeout = True
                        print(f"[JARVIS] ⏱️ Timeout al conectar — reintentando en 1s...")
                    elif "1011" in msg or "Internal error" in msg:
                        tool_hint = self._api_1011_tool or ""
                        print(f"[JARVIS] ⚡ API 1011{tool_hint and ' durante '+tool_hint} — reconectando...")
                        consecutive_fails += 1
                        if consecutive_fails >= 4:
                            self.ui.write_log(
                                "SYS: ⚠️ Error 1011 repetido. Esperando para no saturar la API...\n"
                                "SYS: Si persiste más de 2 min, reiniciá Nia."
                            )
                        elif tool_hint:
                            self.ui.write_log(f"SYS: Error de servidor al ejecutar '{tool_hint}'. Reconectando...")
                        else:
                            self.ui.write_log("SYS: Error de servidor 1011. Reconectando...")
                    elif "1008" in msg or "policy violation" in msg.lower() or "not found for API version" in msg:
                        # Model not available / wrong API version — log clearly, retry with same model
                        print(f"[JARVIS] ⚠️ Modelo no disponible en esta versión de API: {msg[:120]}")
                        self.ui.write_log("SYS: ⚠️ Modelo no disponible. Reintentando...")
                        consecutive_fails += 1
                    elif "1007" in msg and "audio" in msg.lower():
                        # Error de audio nativo: el modelo rechazó el content-type del audio
                        # (normalmente por MIME/rate incorrecto o glitch del preview model).
                        # Tras varios fallos seguidos cambiamos a voz local (Piper) real.
                        print(f"[JARVIS] 🎧 Error de audio nativo (1007): {msg[:160]}")
                        consecutive_fails += 1
                        if consecutive_fails >= 5 and not self._use_local_voice:
                            self._use_local_voice = True
                            self.ui.write_log(
                                "SYS: ⚠️ El audio nativo está fallando. Cambiando a voz local (Piper)."
                            )
                            print("[JARVIS] 🔈 Voz local activada (Piper) tras 1007s repetidos.")
                    elif "1000" in msg or "going away" in msg.lower():
                        # Cierre normal de la sesión (expiró ~15 min) — silencioso
                        print(f"[JARVIS] 🔄 Sesión expirada — reconectando...")
                        consecutive_fails = 0   # reset: no es un fallo
                    else:
                        print(f"[JARVIS] ⚠️ ({type(exc).__name__}): {msg[:200]}")
                        consecutive_fails += 1

                if is_config_reconnect:
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(0.5)
                    continue

                if is_handshake_timeout:
                    # Timeout en handshake → reintento fijo de 1s, sin backoff
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(1.0)
                    continue

                if is_receive_timeout or is_send_failed:
                    # Conexión colgada o sesión de envío caída → reintento fijo
                    # de 1s, sin backoff
                    self.set_speaking(False)
                    self.ui.set_state("THINKING")
                    await asyncio.sleep(1.0)
                    continue

            if not is_config_reconnect and not is_handshake_timeout and not is_receive_timeout and not is_send_failed:
                # Sesión expirada o error real: resumir la conversación en memoria
                self._maybe_summarize_context()

            self.set_speaking(False)
            self.ui.set_state("THINKING")

            # Exponential backoff con jitter para evitar thundering herd
            # Reducido el retraso de reconexión máximo a 10s (antes 90s) para volver en línea al instante
            if consecutive_fails > 1:
                max_delay = 10.0 if consecutive_fails >= 5 else 6.0
                reconnect_delay = min(reconnect_delay * 2, max_delay)
            elif consecutive_fails == 0:
                reconnect_delay = 1.0

            import random as _rnd
            jitter = _rnd.uniform(0, reconnect_delay * 0.25)
            total  = reconnect_delay + jitter
            print(f"[JARVIS] 🔄 Reconectando en {total:.1f}s...")
            await asyncio.sleep(total)

def main():
    # ── Single Instance Lock (Linux-compatible with auto-cleanup) ──────────
    import fcntl, os
    _lock_file = "/tmp/.jarvis_single_instance.lock"
    try:
        _lock_fd = open(_lock_file, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        print("[JARVIS] Ya hay una instancia en ejecución. Cerrando.")
        sys.exit(0)

    # ── Admin validation ──────────────────────────────────────────────────────
    is_admin = os.geteuid() == 0
    if not is_admin:
        print("[Nia] ⚠️ ADVERTENCIA: No se está ejecutando con privilegios de Administrador.")
        print("[Nia] ⚠️ Algunas funciones de control del PC o de terminal podrían fallar.")
        print("[Nia] ⚠️ Se recomienda iniciar Nia como superusuario para funcionalidad completa.")

    # ── License check ─────────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────

    # Load timezone from config
    _load_tz()

    def _ensure_both_api_keys():
        cfg = {}
        if API_CONFIG_PATH.exists():
            try:
                cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        gemini = cfg.get("gemini_api_key", "").strip()
        openrouter = cfg.get("openrouter_api_key", "").strip()
        ai_provider = cfg.get("ai_provider", "gemini").strip()
        
        # If Ollama is the active provider, or if we have at least one cloud key set, we are safe to start
        if ai_provider == "ollama" or gemini or openrouter:
            return
            
        from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
        from PyQt6.QtCore import Qt
        
        # We need an app instance before dialogs
        app = QApplication.instance() or QApplication(sys.argv)
        
        dialog = QDialog()
        dialog.setWindowTitle("Configuración Inicial de Nia")
        dialog.resize(450, 250)
        dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        layout = QVBoxLayout(dialog)
        
        lbl_info = QLabel("¡Bienvenido a Nia!\n\nPor favor, ingresa tus API keys o selecciona Ollama en la configuración.\nEstas se guardarán localmente y de forma segura.")
        lbl_info.setStyleSheet("font-size: 14px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(lbl_info)
        
        lbl_gemini = QLabel("Gemini API Key:")
        layout.addWidget(lbl_gemini)
        inp_gemini = QLineEdit()
        inp_gemini.setText(gemini)
        inp_gemini.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(inp_gemini)
        
        lbl_openrouter = QLabel("OpenRouter API Key (Opcional):")
        layout.addWidget(lbl_openrouter)
        inp_openrouter = QLineEdit()
        inp_openrouter.setText(openrouter)
        inp_openrouter.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(inp_openrouter)
        
        btn_save = QPushButton("Guardar y Continuar")
        btn_save.setStyleSheet("background-color: #0078D7; color: white; border: 1.5px solid #0078D7; font-weight: bold; padding: 8px; border-radius: 4px;")
        layout.addWidget(btn_save)
        
        def on_save():
            g = inp_gemini.text().strip()
            o = inp_openrouter.text().strip()
            if not g and not o:
                QMessageBox.warning(dialog, "Error", "Debe proporcionar al menos una API Key de Gemini.")
                return
            cfg["gemini_api_key"] = g
            cfg["openrouter_api_key"] = o
            API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            API_CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
            dialog.accept()
            
        btn_save.clicked.connect(on_save)
        
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted:
            sys.exit(0)

    _ensure_both_api_keys()

    # Smart User Name Verification for First-Time Setup
    def _ensure_user_name():
        cfg = {}
        if API_CONFIG_PATH.exists():
            try:
                cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        
        user_name = cfg.get("user_name", "").strip()
        if user_name:
            return
            
        from PyQt6.QtWidgets import QApplication, QInputDialog
        # We need app instance before dialogs
        app = QApplication.instance() or QApplication(sys.argv)
        
        name, ok = QInputDialog.getText(
            None, 
                "Configuración Inicial - Nia",
            "¿Cómo desea que lo llame, señor?", 
            text="Señor"
        )
        if ok and name.strip():
            cfg["user_name"] = name.strip()
        else:
            cfg["user_name"] = "Señor"
            
        API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        API_CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding="utf-8")

    _ensure_user_name()

    ui = JarvisUI("face.png")

    # --- UI COSMETICS PATCH ---
    try:
        if hasattr(ui, "_win"):
            # Aumentar transparencia (Glassmorphism)
            ui._win.setWindowOpacity(0.85)
            # Reemplazar textos "Beta" y "Gratuito"
            from PyQt6.QtWidgets import QLabel
            for label in ui._win.findChildren(QLabel):
                text_lower = label.text().lower()
                if "beta" in text_lower or "gratuita" in text_lower or "gratuito" in text_lower or "premium" in text_lower:
                    try:
                        # Ocultar el contenedor completo del banner (incluye el botón PRO)
                        label.parentWidget().hide()
                    except:
                        label.hide()

            # 2. Add keyboard shortcut & Global Hotkey (INS / Insert key) to wake up JARVIS
            from PyQt6.QtGui import QKeySequence, QShortcut
            from PyQt6.QtCore import Qt, QTimer

            def on_shortcut_triggered():
                # Wake up / unmute JARVIS
                if hasattr(ui, "_win"):
                    # Si está muteado, desmutearlo para que escuche
                    if getattr(ui, "muted", False):
                        if hasattr(ui._win, "_toggle_mute"):
                            ui._win._toggle_mute()
                            ui.write_log("SYS: 🎤 Micrófono ACTIVADO vía atajo INS.")
                    else:
                        # Si ya está activo, mostrar/restaurar la ventana principal y enfocarla
                        if hasattr(ui._win, "showNormal"):
                            ui._win.showNormal()
                            ui._win.activateWindow()
                            ui.write_log("SYS: 🔔 Nia en foco vía atajo INS.")
                        
                        # Cambiar estado visual a escuchando
                        try:
                            ui.set_state("LISTENING")
                        except:
                            pass

            # A. PyQt Window Shortcut (for local window events)
            local_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Insert), ui._win)
            local_shortcut.activated.connect(on_shortcut_triggered)

            # B. Win32 Native Global Hotkey Hook (for background capture)
            def setup_global_hotkey():
                import sys
                if sys.platform != "win32":
                    return
                import threading
                import ctypes
                import ctypes.wintypes

                def hotkey_thread():
                    user32 = ctypes.windll.user32
                    # MOD_NOREPEAT = 0x4000
                    # VK_INSERT = 0x2D
                    try:
                        if not user32.RegisterHotKey(None, 99, 0x0000, 0x2D):
                            print("[HOTKEY] Error registering global Insert hotkey.")
                            return
                    except Exception as e:
                        print(f"[HOTKEY] Exception registering global hotkey: {e}")
                        return

                    try:
                        msg = ctypes.wintypes.MSG()
                        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                            if msg.message == 0x0312: # WM_HOTKEY
                                if msg.wParam == 99:
                                    # Thread-safely trigger UI callback inside PyQt event loop
                                    QTimer.singleShot(0, on_shortcut_triggered)
                            user32.TranslateMessage(ctypes.byref(msg))
                            user32.DispatchMessageW(ctypes.byref(msg))
                    finally:
                        user32.UnregisterHotKey(None, 99)

                threading.Thread(target=hotkey_thread, daemon=True).start()

            setup_global_hotkey()
            print("[PATCH] Avengers: Age of Ultron golden aesthetics & Insert global hotkey loaded successfully!")

    except Exception as e:
        print(f"[PATCH] Cosmetics & Shortcut patch failed: {e}")

    def runner():
        import time as _time
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        # Al cerrar Nia, resumir la conversación pendiente en memoria a largo plazo
        try:
            ui._win._on_shutdown_hook = jarvis._summarize_now_blocking
        except Exception:
            pass
        # El loop de run() ya reconecta solo; este try/except es la última red:
        # si algo inesperado lo mata, el hilo reintenta en vez de morir y dejar
        # a Nia muda (proceso vivo pero sorda — el watchdog nunca la levantaría).
        while True:
            try:
                asyncio.run(jarvis.run())
                return  # run() retornó limpio → cierre normal
            except KeyboardInterrupt:
                print("\n🔴 Apagando...")
                return
            except Exception as e:
                print(f"[JARVIS] 🔄 Fallo inesperado en el loop principal "
                      f"({type(e).__name__}): {str(e)[:200]}")
                traceback.print_exc()
                _time.sleep(3.0)
                continue

    # Lanzar el modelo PNGtuber (esquina inferior derecha). Es single-instance:
    # si ya hay uno corriendo, el nuevo sale solo por el puerto ocupado.
    _launch_pngtuber()
    if _pngtuber_send:
        _pngtuber_send("hide")  # ocultarlo mientras la ventana de Nia está visible

    threading.Thread(target=_memory_watchdog_loop, daemon=True, name="mem-watchdog").start()
    threading.Thread(target=_pngtuber_watchdog_loop, daemon=True, name="pngtuber-watchdog").start()
    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

    # Al salir, limpiar el PNGtuber para que no quede un proceso fantasma
    # con la boca congelada (acumulación histórica de huérfanos).
    _shutdown_pngtuber()

    # Terminación forzada a nivel de sistema operativo para liberar handles de cámara,
    # micrófono, sockets y el mutex de instancia única al instante sin esperas ni deadlocks
    import os
    os._exit(0)

if __name__ == "__main__":
    main()