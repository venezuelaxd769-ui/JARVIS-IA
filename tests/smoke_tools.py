#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/smoke_tools.py — Smoke test de Nia.

Importa TODAS las actions (incluidas las .pyc-only) y verifica la convención
    fn(parameters: dict, player=None, speak=None) -> str
además de validar agent/tool_schemas.json y correr un puñado de dry-runs seguros
(sin red, sin efectos destructivos, sin audio).

Uso (siempre desde la raíz del repo):
    .venv\\Scripts\\python.exe tests\\smoke_tools.py

Exit code:
    0 = todo importa y los dry-run pasan
    1 = hay módulos que no importan (FAIL)
"""
import importlib
import inspect
import io
import json
import pathlib
import sys

# Salida UTF-8 robusta (las tools devuelven emojis/acentos que cp1252 no imprime)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ACTION_DIR = ROOT / "actions"
SKIP_FILES = {"__init__.py", "custom_tools.py"}

# Módulos .pyc-only (sin fuente .py) que llegan via sitecustomize.
PYC_ONLY = [
    "daily_summary", "desktop_kb", "dev_agent", "file_processor", "game_kb",
    "game_updater", "mouse_kb", "mouse_keyboard", "obs_control",
    "obsidian_bridge", "recall_memory", "rgb_control", "screen_capture",
    "_self_agent_core", "send_message", "tts_local", "usage_stats", "web_kb",
    "youtube_kb",
]

# Dry-runs seguros: solo lecturas/estado, sin side-effects.
SAFE_DRYRUNS = [
    ("screen_pointer", {"action": "window"}),
    ("process_manager", {"action": "list"}),
    ("auto_programmer", {"action": "list_tools"}),
]


def _list_action_modules():
    mods = []
    for f in sorted(ACTION_DIR.glob("*.py")):
        if f.name in SKIP_FILES or f.name.startswith("_"):
            continue
        mods.append(f.stem)
    return mods


def _find_convention_fn(mod, base):
    for cand in (base, "handle", "run", "execute"):
        fn = getattr(mod, cand, None)
        if callable(fn):
            return cand
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name, None)
        if inspect.isfunction(obj):
            return name
    return None


def main():
    fail_lines = []
    warn_lines = []

    # Tier 1: import de actions/*.py + convención
    modules = _list_action_modules()
    print(f"Actions detectadas: {len(modules)}")
    for base in modules:
        try:
            mod = importlib.import_module(f"actions.{base}")
        except Exception as e:
            fail_lines.append(f"IMPORT {base}: {type(e).__name__}: {e}")
            continue
        fn = _find_convention_fn(mod, base)
        tag = f"conv={fn}" if fn else "conv=?"
        if fn is None:
            warn_lines.append(f"CONV {base}: sin función de convención detectada")
        print(f"  OK  {base:28s} {tag}")

    # Tier 1b: pyc-only (bytecode vía sitecustomize)
    pyc_fail = 0
    for base in PYC_ONLY:
        try:
            mod = importlib.import_module(f"actions.{base}")
            fn = _find_convention_fn(mod, base)
            print(f"  OK  {base:28s} pyc-only conv={fn}")
        except Exception as e:
            pyc_fail += 1
            fail_lines.append(f"IMPORT {base} (pyc-only): {type(e).__name__}: {e}")
            print(f"  FAIL {base:28s} pyc-only: {type(e).__name__}: {e}")

    # Tier 2: dry-runs seguros
    print("\nDry-runs seguros:")
    for base, args in SAFE_DRYRUNS:
        try:
            mod = importlib.import_module(f"actions.{base}")
            fn = getattr(mod, base, None) or getattr(mod, "handle", None) or getattr(mod, "run", None)
            if fn is None:
                warn_lines.append(f"DRYRUN {base}: sin función invocable")
                print(f"  WARN {base}: sin función invocable")
                continue
            result = fn(parameters=dict(args), player=None)
            ok = isinstance(result, str)
            snippet = (result or "")[:60].replace("\n", " ")
            if ok:
                print(f"  OK  {base}: {snippet!r}")
            else:
                warn_lines.append(f"DRYRUN {base}: resultado no-string ({type(result).__name__})")
                print(f"  WARN {base}: resultado no-string ({type(result).__name__})")
        except Exception as e:
            fail_lines.append(f"DRYRUN {base}: {type(e).__name__}: {e}")
            print(f"  FAIL {base}: {type(e).__name__}: {e}")

    # Tier 3: agent/tool_schemas.json
    print("\nagent/tool_schemas.json:")
    schemas_path = ROOT / "agent" / "tool_schemas.json"
    try:
        data = json.loads(schemas_path.read_text(encoding="utf-8"))
        names = list(data.keys())
        dupes = sorted({n for n in names if names.count(n) > 1})
        missing = [n for n in names if not (n and data[n].get("description"))]
        print(f"  OK  {len(names)} tools; duplicados: {len(dupes)}; sin descripción: {len(missing)}")
        if dupes:
            fail_lines.append(f"SCHEMA: names duplicados: {dupes}")
        if missing:
            fail_lines.append(f"SCHEMA: entradas sin descripción: {missing}")
    except Exception as e:
        fail_lines.append(f"SCHEMA: {type(e).__name__}: {e}")
        print(f"  FAIL schema: {type(e).__name__}: {e}")

    # Resumen
    print("\n" + "=" * 60)
    for line in fail_lines:
        print("FAIL:", line)
    for line in warn_lines:
        print("WARN:", line)
    n_fail = len(fail_lines)
    n_warn = len(warn_lines)
    print(f"Total: {len(modules)} actions + {len(PYC_ONLY)} pyc-only | FAIL: {n_fail} | WARN: {n_warn}")
    if n_fail:
        print("VEREDICTO: HAY FALLOS")
        return 1
    print("VEREDICTO: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())