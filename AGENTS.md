# AGENTS.md

JARVIS-IA / "Nia": desktop voice AI assistant (Google Gemini Live + PyQt6/tkinter UI, PNGtuber avatar, 80+ tools). **All user-facing output is Argentine Spanish** — persona in `core/prompt.txt`, tool messages, logs, and commit messages. Never "fix" the Spanish or the persona (e.g. Nia must never use parentheses for emotion; never delete user files without confirmation).

## Run & verify

- Launch (background, survives terminal close): `./run_jarvis.sh` → logs in `logs/nia_run.log`.
- Foreground: `.venv/bin/python main.py` (Python 3.14.5 venv; **must run from repo root**).
- Single-instance `fcntl` flock at `/tmp/.jarvis_single_instance.lock` (main.py:4798): a second instance exits silently. To restart, kill the running process; deleting the lock file does NOT release the held flock and allows a duplicate.
- Requires `config/api_keys.json` (`gemini_api_key`; gitignored — template: `config/api_keys.example.json`). Missing key → setup dialog at startup. Offline STT needs `config/vosk_model/` (gitignored; `download_vosk.py` fetches it).
- There are **no tests, no linter, no CI** (README's `tests/smoke_tools.py` and `nia_watchdog.sh` don't exist). Verify by importing modules (`python -c "import actions.xxx"`) or running the app.

## `.pyc`-only modules (critical)

`sitecustomize.py` installs a sourceless importer so `.pyc` files are importable without `.py` sources. It only loads because scripts run from repo root — always run from repo root.

These modules have **no `.py` source; behavior lives in committed Python 3.14 bytecode** (matches `.venv`):
`actions/{daily_summary, desktop_kb, dev_agent, file_processor, game_kb, game_updater, mouse_kb, mouse_keyboard, obs_control, obsidian_bridge, recall_memory, rgb_control, screen_capture, _self_agent_core, send_message, tts_local, usage_stats, web_kb, youtube_kb}` and `memory/semantic_memory`. `actions/self_agent.py` (source) imports the pyc-only `_self_agent_core`.

To change one of these: write a `.py` with the same module name (source takes precedence over `.pyc`; keep/delete the old `.pyc`), or recompile a new `.pyc` for 3.14. Don't delete `sitecustomize.py`.

Some action `.py` files are intentional "NOT IMPLEMENTED" stubs (`arca_invoice`, `codebase`, `git_control`, `gmail_control`, `google_calendar`, `google_drive`, `google_maps`, `flight_finder`, `image_generation`, `knowledge_base`, `smart_home`, `social_media`, `tiktok_analyzer`) so Nia doesn't fabricate results — not bugs.

## Architecture

- `main.py` (~5k lines): Live loop/reconnect, tool dispatch in `JarvisLive._execute_tool` (main.py:3400), tool schemas in `TOOL_DECLARATIONS` (main.py:692).
- `actions/`: tool modules, convention `fn(parameters: dict, player=None, speak=None) -> str`. `player` is the `JarvisUI` (`ui.py`) — has `.write_log()`, `.set_state()`, `.muted`.
- `ui.py` (~2.4k lines): `JarvisUI` + glassmorphic PyQt6 window + `assets/sphere.html` (WebEngine orb). `gpu_acceleration` in `api_keys.json` toggles the Chromium flags set at the top of main.py (affects rendering/RAM).
- `agent/`: subagent system (researcher/coder/organizer/computer), configured in `config/subagents.json` (OpenRouter or Gemini backends). Its schemas load from `agent/tool_schemas.json`, hand-extracted from `TOOL_DECLARATIONS` (no generator — keep in sync when changing tool schemas).
- `pngtuber/`: separate avatar process; main.py talks to it over TCP 127.0.0.1:8791 (`pngtuber/client.py`).
- `beta_config.py`: pro-tool gating, currently everything allowed/unlimited.

## Platform quirks

- Windows heritage: `install.py`, `launchers/`, `.bat`/`.vbs`, `run_debug.py` (hot-reload watcher), Windows paths in `api_keys.example.json` are stale. The app now runs on Linux/Hyprland; some actions (`windows_settings`, parts of `computer_settings`, `mouse_keyboard`) are Windows-only and no-op/fail on Linux.
- The `~/` directory at repo root (contains `Desktop/Registro_Problemas_Nia.txt`) is accidental junk, not part of the app.
