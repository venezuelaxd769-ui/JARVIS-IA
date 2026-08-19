"""skill_manager.py — Sistema de skills cargables para Nia.

Los skills son archivos JSON con instrucciones y contexto que Nia
puede cargar para especializarse en tareas específicas. Se almacenan
en config/skills/ y se cargan bajo demanda.
"""
import json
import os
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
SKILLS_DIR = _REPO / "config" / "skills"


def _ensure_dir():
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)


def _list_skills():
    _ensure_dir()
    skills = []
    for f in sorted(SKILLS_DIR.glob("*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            skills.append({
                "name": data.get("name", f.stem),
                "description": data.get("description", "(sin descripción)"),
                "file": f.name,
                "tags": data.get("tags", []),
            })
        except Exception:
            skills.append({"name": f.stem, "description": "(error al leer)",
                           "file": f.name, "tags": []})
    return skills


def _load_skill(name):
    _ensure_dir()
    for f in SKILLS_DIR.glob("*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("name", f.stem).lower() == name.lower():
                return data
        except Exception:
            continue
    return None


def _create_skill(name, description, instructions, tags=None):
    _ensure_dir()
    slug = name.lower().replace(" ", "_").replace("/", "_")
    data = {
        "name": name,
        "description": description,
        "tags": tags or [],
        "instructions": instructions,
    }
    path = SKILLS_DIR / f"{slug}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(path)


def skill_manager(parameters: dict, player=None) -> str:
    """Gestiona skills: listar, cargar, crear y eliminar."""
    action = str(parameters.get("action", "list")).lower().strip()

    if action in ("list", "ls", "ver"):
        skills = _list_skills()
        if not skills:
            return ("No hay skills instalados. "
                    "Podés crear uno con action=create.")
        lines = [f"📦 {len(skills)} skill(s) disponible(s):"]
        for s in skills:
            tags = f" [{', '.join(s['tags'])}]" if s.get("tags") else ""
            lines.append(f"  • {s['name']} — {s['description'][:80]}{tags}")
        return "\n".join(lines)

    if action in ("load", "cargar", "usar"):
        name = str(parameters.get("name", "")).strip()
        if not name:
            return "Decime el nombre del skill que querés cargar."
        skill = _load_skill(name)
        if not skill:
            available = [s["name"] for s in _list_skills()]
            return (f"Skill '{name}' no encontrado. "
                    f"Disponibles: {', '.join(available) or 'ninguno'}.")
        if player:
            player.write_log(f"📦 Skill cargado: {skill['name']}")
        instructions = skill.get("instructions", "(sin instrucciones)")
        tags = skill.get("tags", [])
        return (f"📦 Skill: {skill['name']}\n"
                f"Descripción: {skill.get('description', '')}\n"
                f"Tags: {', '.join(tags) if tags else 'ninguno'}\n\n"
                f"Instrucciones:\n{instructions[:3000]}")

    if action in ("create", "crear", "nuevo"):
        name = str(parameters.get("name", "")).strip()
        desc = str(parameters.get("description", "")).strip()
        instructions = str(parameters.get("instructions", "")).strip()
        tags_raw = str(parameters.get("tags", "")).strip()
        if not name or not instructions:
            return "Necesito name e instructions para crear un skill."
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []
        path = _create_skill(name, desc or name, instructions, tags)
        if player:
            player.write_log(f"📦 Skill creado: {name}")
        return f"Skill '{name}' creado en {path}."

    if action in ("delete", "eliminar", "borrar"):
        name = str(parameters.get("name", "")).strip()
        if not name:
            return "Decime qué skill querés eliminar."
        _ensure_dir()
        slug = name.lower().replace(" ", "_")
        for f in SKILLS_DIR.glob("*.json"):
            if f.stem == slug:
                f.unlink()
                if player:
                    player.write_log(f"📦 Skill eliminado: {name}")
                return f"Skill '{name}' eliminado."
        return f"Skill '{name}' no encontrado."

    return "Acciones: list/ls, load/cargar, create/crear, delete/eliminar."
