"""backup_manager.py — Gestiona backups del proyecto.

Crea, lista, restaura y elimina backups. Usa tar.gz para comprimir.
Backups se guardan en ~/Backups/ o en una ruta configurada.
"""
import os
import shutil
import subprocess
import time
from pathlib import Path
from datetime import datetime

_REPO = Path(__file__).resolve().parent.parent
_DEFAULT_BACKUP_DIR = Path.home() / "Backups"


def _get_backup_dir(custom=None):
    if custom:
        d = Path(custom).expanduser()
    else:
        d = _DEFAULT_BACKUP_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def _list_backups(backup_dir):
    """Lista backups existentes."""
    backups = []
    for f in sorted(backup_dir.glob("nia_backup_*.tar.gz")):
        stat = f.stat()
        backups.append({
            "name": f.name,
            "path": str(f),
            "size": stat.st_size,
            "time": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        })
    return backups


def _create_backup(backup_dir, name=None):
    """Crea un backup del proyecto."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = name or f"nia_backup_{ts}.tar.gz"
    if not backup_name.endswith(".tar.gz"):
        backup_name += ".tar.gz"
    backup_path = backup_dir / backup_name

    # Directorios y archivos a excluir
    excludes = [
        ".venv", "__pycache__", ".git", ".tmp", ".backups",
        "logs", "node_modules", ".env", "config/api_keys.json",
    ]

    cmd = ["tar", "-czf", str(backup_path), "-C", str(_REPO.parent), _REPO.name]
    for ex in excludes:
        cmd.insert(3, f"--exclude={_REPO.name}/{ex}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode == 0 and backup_path.exists():
        size = backup_path.stat().st_size
        return True, backup_path, size
    else:
        return False, None, result.stderr[:500]


def _restore_backup(backup_path, target_dir):
    """Restaura un backup."""
    if not os.path.exists(backup_path):
        return False, f"Backup no encontrado: {backup_path}"

    cmd = ["tar", "-xzf", str(backup_path), "-C", str(target_dir)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode == 0:
        return True, f"Backup restaurado en {target_dir}"
    else:
        return False, f"Error: {result.stderr[:500]}"


def backup_manager(parameters: dict, player=None) -> str:
    """Gestiona backups: crear, listar, restaurar, eliminar."""
    action = str(parameters.get("action", "list")).lower().strip()
    backup_dir = str(parameters.get("backup_dir", "")).strip()
    name = str(parameters.get("name", "")).strip()

    bd = _get_backup_dir(backup_dir)

    if action in ("create", "crear", "backup", "c"):
        if player:
            player.write_log("💾 Creando backup del proyecto...")
        ok, path, size = _create_backup(bd, name)
        if ok:
            return (f"✅ Backup creado: {path.name}\n"
                    f"   Tamaño: {size:,} bytes\n"
                    f"   Ubicación: {bd}")
        return f"❌ Error creando backup: {path}"

    if action in ("list", "ls", "ver"):
        backups = _list_backups(bd)
        if not backups:
            return f"No hay backups en {bd}"
        lines = [f"💾 {len(backups)} backup(s) en {bd}:\n"]
        for b in backups:
            lines.append(f"  📦 {b['name']} — {b['size']:,} bytes — {b['time']}")
        return "\n".join(lines)

    if action in ("restore", "restaurar", "r"):
        if name:
            # Buscar por nombre
            backup_path = bd / name
            if not backup_path.exists():
                return f"Backup '{name}' no encontrado."
        else:
            # Usar el más reciente
            backups = _list_backups(bd)
            if not backups:
                return "No hay backups para restaurar."
            backup_path = Path(backups[-1]["path"])

        if player:
            player.write_log(f"💾 Restaurando {backup_path.name}...")
        ok, msg = _restore_backup(backup_path, str(_REPO.parent))
        return f"{'✅' if ok else '❌'} {msg}"

    if action in ("delete", "eliminar", "del", "rm"):
        if not name:
            return "Necesito el nombre del backup a eliminar."
        backup_path = bd / name
        if not backup_path.exists():
            return f"Backup '{name}' no encontrado."
        backup_path.unlink()
        return f"✅ Backup '{name}' eliminado."

    if action in ("info",):
        backups = _list_backups(bd)
        if not backups:
            return "No hay backups."
        total_size = sum(b["size"] for b in backups)
        return (f"💾 Info de backups:\n"
                f"  Total: {len(backups)} backups\n"
                f"  Tamaño total: {total_size:,} bytes\n"
                f"  Ubicación: {bd}\n"
                f"  Más reciente: {backups[-1]['name']}\n"
                f"  Más antiguo: {backups[0]['name']}")

    return ("Acciones: create/crear/backup, list/ls, restore/restaurar, "
            "delete/eliminar, info.")
