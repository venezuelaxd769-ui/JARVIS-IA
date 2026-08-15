"""sync_tool_schemas.py — regenera agent/tool_schemas.json.

Reconstruye el archivo a partir de dos fuentes:
  * main.py → TOOL_DECLARATIONS (las tools del loop principal de Nia), y
  * agent/subagents.py → _TOOLS (las whitelists de cada subagente).

Solo entran las tools que los subagentes usan realmente, más las tools
internas del agente (agent/toolbox.py: remember_info, recall_memory,
current_time) que no existen en main.py.

Uso:
  python agent/sync_tool_schemas.py   # regenera y muestra el diff
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MAIN_PY = BASE_DIR / "main.py"
SUBAGENTS_PY = BASE_DIR / "agent" / "subagents.py"
OUT = BASE_DIR / "agent" / "tool_schemas.json"

# Tools internas del agente (definidas en agent/toolbox.py). Sus schemas no
# existen en main.py porque no son tools del loop principal de Nia.
INTERNAL_SCHEMAS = {
    "current_time": {
        "name": "current_time",
        "description": "Devuelve la fecha y hora actuales del sistema.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    },
    "remember_info": {
        "name": "remember_info",
        "description": "Guarda un dato en la memoria a largo plazo de Nia.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "identity | preferences | projects | relationships | wishes | notes",
                },
                "key": {"type": "STRING", "description": "Clave corta en snake_case (ej: favorite_color)"},
                "value": {"type": "STRING", "description": "Valor breve a recordar"},
            },
            "required": ["category", "key", "value"],
        },
    },
    "recall_memory": {
        "name": "recall_memory",
        "description": "Lee la memoria a largo plazo de Nia. Sin categoría devuelve todo.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": "Filtrar por categoría (identity, preferences, projects, relationships, wishes, notes, context, system). Vacío = todo.",
                }
            },
            "required": [],
        },
    },
    "web_navigation": {
        "name": "web_navigation",
        "description": "Maneja la navegación web, en especial reproducir música en YouTube u otras páginas. Usá play_youtube con una consulta y abre/reproduce el primer resultado en el navegador.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play_youtube | youtube"},
                "query": {"type": "STRING", "description": "Canción, artista o búsqueda a reproducir"},
            },
            "required": ["action", "query"],
        },
    },
}


def _extract_tool_declarations() -> dict:
    tree = ast.parse(MAIN_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "TOOL_DECLARATIONS":
                    return {d["name"]: d for d in ast.literal_eval(node.value)}
    raise SystemExit("TOOL_DECLARATIONS no encontrado en main.py")


def _extract_subagent_whitelists() -> set:
    tree = ast.parse(SUBAGENTS_PY.read_text(encoding="utf-8"))
    tools = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_TOOLS":
                    # _TOOLS = {"researcher": [...], "coder": [...], ...}
                    # solo interesan los elementos de las LISTAS (los valores),
                    # no las keys ("researcher", "coder", ...).
                    if isinstance(node.value, ast.Dict):
                        for val in node.value.values:
                            if isinstance(val, ast.List):
                                for el in ast.walk(val):
                                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                                        tools.add(el.value)
    return tools


def main():
    decls = _extract_tool_declarations()
    whitelist = _extract_subagent_whitelists()

    schemas = {}
    missing = []
    for name in sorted(whitelist):
        if name in INTERNAL_SCHEMAS:
            schemas[name] = INTERNAL_SCHEMAS[name]
        elif name in decls:
            schemas[name] = decls[name]
        else:
            missing.append(name)

    old = {}
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))

    added = sorted(set(schemas) - set(old))
    removed = sorted(set(old) - set(schemas))
    changed = sorted(n for n in set(schemas) & set(old) if schemas[n] != old[n])

    OUT.write_text(json.dumps(schemas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"tool_schemas.json regenerado: {len(schemas)} tools.")
    if added:
        print("AGREGADAS:", ", ".join(added))
    if removed:
        print("ELIMINADAS:", ", ".join(removed))
    if changed:
        print("CAMBIARON:", ", ".join(changed))
    if missing:
        print("SIN SCHEMA (no existen en main.py ni como internas):", ", ".join(missing))
    if not (added or removed or changed or missing):
        print("Sin cambios — todo en sync.")


if __name__ == "__main__":
    main()
