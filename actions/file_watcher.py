"""file_watcher.py — Vigila cambios en archivos/directorios.

Detecta creación, modificación y eliminación de archivos.
Puede vigilar un directorio o un archivo específico. Útil para
detectar cambios en código, configuraciones, etc.
"""
import os
import time
import hashlib
from pathlib import Path
from collections import defaultdict


def _hash_file(path, chunk=8192):
    """Hash MD5 de un archivo."""
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            while True:
                data = f.read(chunk)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()
    except Exception:
        return None


def _snapshot_dir(path, exclude=None):
    """Toma snapshot de archivos: {ruta: (hash, size, mtime)."""
    exclude = exclude or {".git", "__pycache__", ".venv", "node_modules",
                          ".tmp", "logs", ".backups"}
    snap = {}
    try:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in exclude]
            for f in files:
                fp = os.path.join(root, f)
                try:
                    stat = os.stat(fp)
                    snap[fp] = {
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "hash": _hash_file(fp),
                    }
                except Exception:
                    continue
    except Exception:
        pass
    return snap


def file_watcher(parameters: dict, player=None) -> str:
    """Vigila cambios en archivos: snapshot, diff, y watch continuo."""
    action = str(parameters.get("action", "snapshot")).lower().strip()
    path = str(parameters.get("path", ".")).strip()
    path = os.path.expanduser(path)
    state_file = str(parameters.get("state_file", "")).strip()
    duration = int(parameters.get("duration", 10))
    interval = int(parameters.get("interval", 2))

    if action in ("snapshot", "snap", "s"):
        """Toma snapshot del estado actual de archivos."""
        if player:
            player.write_log(f"📸 Tomando snapshot de {path}...")
        snap = _snapshot_dir(path)
        if not snap:
            return f"No se encontraron archivos en {path}"

        # Guardar snapshot
        if not state_file:
            state_file = os.path.join(str(Path.home()), ".nia_watcher_state.json")
        import json
        Path(state_file).parent.mkdir(parents=True, exist_ok=True)
        with open(state_file, "w") as f:
            json.dump(snap, f, indent=2)

        total_size = sum(s["size"] for s in snap.values())
        return (f"📸 Snapshot guardado: {len(snap)} archivos, "
                f"{total_size:,} bytes totales\n"
                f"📁 {path}\n"
                f"💾 Estado: {state_file}")

    if action in ("diff", "cambios", "d"):
        """Compara estado actual con snapshot previo."""
        if not state_file:
            state_file = os.path.join(str(Path.home()), ".nia_watcher_state.json")

        import json
        if not os.path.exists(state_file):
            return "No hay snapshot previo. Usá action=snapshot primero."

        with open(state_file) as f:
            old_snap = json.load(f)

        new_snap = _snapshot_dir(path)

        created = [p for p in new_snap if p not in old_snap]
        deleted = [p for p in old_snap if p not in new_snap]
        modified = []
        for p in new_snap:
            if p in old_snap:
                if new_snap[p]["hash"] != old_snap[p]["hash"]:
                    modified.append(p)

        if not created and not deleted and not modified:
            return "✅ Sin cambios desde el último snapshot."

        lines = [f"🔄 Cambios detectados en {path}:\n"]
        if created:
            lines.append(f"📄 Nuevos ({len(created)}):")
            for p in created[:10]:
                lines.append(f"  + {os.path.relpath(p, path)}")
        if deleted:
            lines.append(f"🗑️ Eliminados ({len(deleted)}):")
            for p in deleted[:10]:
                lines.append(f"  - {os.path.relpath(p, path)}")
        if modified:
            lines.append(f"✏️ Modificados ({len(modified)}):")
            for p in modified[:10]:
                lines.append(f"  ~ {os.path.relpath(p, path)}")

        return "\n".join(lines)

    if action in ("watch", "vigilar", "w"):
        """Vigila cambios en tiempo real por duration segundos."""
        if player:
            player.write_log(f"👁️ Vigilando {path} por {duration}s...")

        old_snap = _snapshot_dir(path)
        time.sleep(interval)
        changes = []

        elapsed = 0
        while elapsed < duration:
            new_snap = _snapshot_dir(path)
            for p in new_snap:
                if p not in old_snap:
                    changes.append(f"+ {os.path.relpath(p, path)}")
                elif new_snap[p]["hash"] != old_snap[p]["hash"]:
                    changes.append(f"~ {os.path.relpath(p, path)}")
            for p in old_snap:
                if p not in new_snap:
                    changes.append(f"- {os.path.relpath(p, path)}")

            old_snap = new_snap
            elapsed += interval
            if elapsed < duration:
                time.sleep(interval)

        if not changes:
            return f"👁️ Sin cambios en {duration}s en {path}"

        return f"👁️ {len(changes)} cambios detectados en {duration}s:\n" + "\n".join(changes[:20])

    return "Acciones: snapshot/snap (guardar estado), diff/cambios (comparar), watch/vigilar (monitoreo continuo)."
