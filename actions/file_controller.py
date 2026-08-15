# -*- coding: utf-8 -*-
"""
file_controller.py — Pure Python robust file and directory operations manager for JARVIS.
"""
import os
import shutil
import traceback
from pathlib import Path
from datetime import datetime

def resolve_path(p: str) -> str:
    if not p:
        return os.path.expanduser("~/Desktop")
    
    p_lower = p.lower().strip()
    home = os.path.expanduser("~")
    
    # Keyword short-circuits
    if p_lower == "desktop" or p_lower.startswith("desktop\\") or p_lower.startswith("desktop/"):
        rel = p[7:].lstrip("\\/")
        return os.path.join(home, "Desktop", rel)
    elif p_lower == "downloads" or p_lower.startswith("downloads\\") or p_lower.startswith("downloads/"):
        rel = p[9:].lstrip("\\/")
        return os.path.join(home, "Downloads", rel)
    elif p_lower == "documents" or p_lower.startswith("documents\\") or p_lower.startswith("documents/"):
        rel = p[9:].lstrip("\\/")
        return os.path.join(home, "Documents", rel)
    elif p_lower == "home" or p_lower.startswith("home\\") or p_lower.startswith("home/"):
        rel = p[4:].lstrip("\\/")
        return os.path.join(home, rel)
        
    return os.path.abspath(p)

def file_controller(parameters: dict, player=None) -> str:
    """
    Manages files and folders: list, create, delete, move, copy, rename, read, write, edit, find, largest, disk_usage, organize_desktop.
    """
    action = parameters.get("action", "").lower().strip()
    path_raw = parameters.get("path", "")
    destination_raw = parameters.get("destination", "")
    new_name = parameters.get("new_name", "")
    content = parameters.get("content", "")
    search_name = parameters.get("name", "")
    extension = parameters.get("extension", "")
    count = int(parameters.get("count", 10))
    old_text = parameters.get("old_text", "")
    new_text = parameters.get("new_text", "")
    mode = parameters.get("mode", "replace").lower().strip()
    confirm = parameters.get("confirm", False)

    if not action:
        return "Error: Se requiere el parámetro 'action'."

    try:
        resolved_path = resolve_path(path_raw)

        # 1. LIST DIRECTORY
        if action == "list":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."
            if not os.path.isdir(resolved_path):
                return f"Error: '{path_raw}' no es una carpeta."
            
            items = sorted(os.listdir(resolved_path))
            if not items:
                return f"La carpeta '{os.path.basename(resolved_path)}' está vacía."
                
            lines = [f"Contenido de '{os.path.basename(resolved_path)}' ({len(items)} elementos):"]
            for item in items:
                full_item = os.path.join(resolved_path, item)
                if os.path.isdir(full_item):
                    lines.append(f"  📁 {item}/")
                else:
                    sz_kb = os.path.getsize(full_item) / 1024
                    lines.append(f"  📄 {item} ({sz_kb:.1f} KB)")
            return "\n".join(lines)

        # 2. CREATE FILE
        elif action in ("create_file", "write"):
            # Ensure folder exists
            os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(content or "")
            msg = f"Archivo creado exitosamente: '{os.path.basename(resolved_path)}'."
            if player:
                player.write_log(f"📄 {msg}")
            return msg

        # 3. CREATE FOLDER
        elif action == "create_folder":
            os.makedirs(resolved_path, exist_ok=True)
            msg = f"Carpeta creada exitosamente: '{resolved_path}'."
            if player:
                player.write_log(f"📁 {msg}")
            return msg

        # 4. DELETE (Send to Recycle Bin)
        elif action == "delete":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."

            # Requiere confirmación explícita del usuario.
            if not confirm:
                return (f"⛔ Necesito tu confirmación para eliminar '{os.path.basename(resolved_path)}'. "
                        f"Volvé a llamar con confirm=true.")

            # Use send2trash for safety if possible
            try:
                import send2trash
                send2trash.send2trash(resolved_path)
                msg = f"'{os.path.basename(resolved_path)}' movido a la Papelera de Reciclaje exitosamente."
            except ImportError:
                if os.path.isdir(resolved_path):
                    shutil.rmtree(resolved_path)
                else:
                    os.remove(resolved_path)
                msg = f"'{os.path.basename(resolved_path)}' eliminado físicamente con éxito (send2trash no disponible)."
                
            if player:
                player.write_log(f"🗑️ {msg}")
            return msg

        # 5. MOVE
        elif action == "move":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta origen '{path_raw}' no existe."
            resolved_dest = resolve_path(destination_raw)
            os.makedirs(os.path.dirname(resolved_dest), exist_ok=True)
            shutil.move(resolved_path, resolved_dest)
            msg = f"Movido de '{path_raw}' a '{destination_raw}' correctamente."
            if player:
                player.write_log(f"🚚 {msg}")
            return msg

        # 6. COPY
        elif action == "copy":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta origen '{path_raw}' no existe."
            resolved_dest = resolve_path(destination_raw)
            if os.path.isdir(resolved_path):
                shutil.copytree(resolved_path, resolved_dest)
            else:
                os.makedirs(os.path.dirname(resolved_dest), exist_ok=True)
                shutil.copy2(resolved_path, resolved_dest)
            msg = f"Copiado de '{path_raw}' a '{destination_raw}' correctamente."
            if player:
                player.write_log(f"👥 {msg}")
            return msg

        # 7. RENAME
        elif action == "rename":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."
            if not new_name:
                return "Error: Se requiere 'new_name' para renombrar."
            new_path = os.path.join(os.path.dirname(resolved_path), new_name)
            os.rename(resolved_path, new_path)
            msg = f"Renombrado de '{os.path.basename(resolved_path)}' a '{new_name}' correctamente."
            if player:
                player.write_log(f"✏️ {msg}")
            return msg

        # 8. READ FILE
        elif action == "read":
            if not os.path.exists(resolved_path):
                return f"Error: El archivo '{path_raw}' no existe."
            if os.path.isdir(resolved_path):
                return f"Error: '{path_raw}' es una carpeta. Utilice action='list'."
                
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            if len(text) > 2000:
                return f"Mostrando primeros 2000 caracteres de '{os.path.basename(resolved_path)}':\n\n{text[:2000]}\n...[Truncado]"
            return text

        # 9. EDIT (Search and Replace/Append/Prepend/Overwrite)
        elif action == "edit":
            if not os.path.exists(resolved_path):
                return f"Error: El archivo '{path_raw}' no existe."
            
            with open(resolved_path, "r", encoding="utf-8", errors="replace") as f:
                orig = f.read()
                
            if mode == "append":
                updated = orig + "\n" + new_text
            elif mode == "prepend":
                updated = new_text + "\n" + orig
            elif mode == "overwrite":
                updated = new_text
            else: # replace mode
                if not old_text:
                    return "Error: Se requiere 'old_text' para reemplazar en modo 'replace'."
                if old_text not in orig:
                    return f"Error: No se encontró el fragmento '{old_text}' en el archivo."
                updated = orig.replace(old_text, new_text, 1)
                
            with open(resolved_path, "w", encoding="utf-8") as f:
                f.write(updated)
            return f"Archivo '{os.path.basename(resolved_path)}' editado exitosamente en modo '{mode}'."

        # 10. FIND RECURSIVELY
        elif action == "find":
            results = []
            target_name = search_name.lower().strip()
            target_ext = extension.lower().strip()
            
            if not target_name and not target_ext:
                return "Error: Proporcione un 'name' o una 'extension' para buscar."
                
            for root, _, files in os.walk(resolved_path):
                for file in files:
                    file_lower = file.lower()
                    match_name = not target_name or target_name in file_lower
                    match_ext = not target_ext or file_lower.endswith(target_ext)
                    if match_name and match_ext:
                        results.append(os.path.join(root, file))
                        if len(results) >= 20: # limit output size
                            break
                if len(results) >= 20:
                    break
                    
            if not results:
                return "No se encontró ningún archivo coincidente."
                
            lines = [f"Resultados de búsqueda en '{path_raw}':"]
            for r in results:
                lines.append(f"  🔍 {r}")
            return "\n".join(lines)

        # 11. LARGEST FILES
        elif action == "largest":
            file_list = []
            for root, _, files in os.walk(resolved_path):
                for file in files:
                    fp = os.path.join(root, file)
                    try:
                        sz = os.path.getsize(fp)
                        file_list.append((fp, sz))
                    except: pass
            
            file_list.sort(key=lambda x: x[1], reverse=True)
            top = file_list[:count]
            if not top:
                return "No se encontraron archivos."
                
            lines = [f"Top {len(top)} archivos más grandes en '{path_raw}':"]
            for fp, sz in top:
                sz_mb = sz / (1024 * 1024)
                lines.append(f"  ⚖️ {sz_mb:.1f} MB — {fp}")
            return "\n".join(lines)

        # 12. DISK USAGE
        elif action == "disk_usage":
            total, used, free = shutil.disk_usage(resolved_path)
            gb = 1024 * 1024 * 1024
            return (
                f"Estadísticas del disco para '{path_raw}':\n"
                f"  💿 Capacidad Total: {total/gb:.1f} GB\n"
                f"  💾 Espacio Usado: {used/gb:.1f} GB\n"
                f"  🟢 Espacio Libre: {free/gb:.1f} GB"
            )

        # 13. INFO METADATA
        elif action == "info":
            if not os.path.exists(resolved_path):
                return f"Error: La ruta '{path_raw}' no existe."
            
            is_dir = os.path.isdir(resolved_path)
            stat = os.stat(resolved_path)
            created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            lines = [
                f"Metadatos para '{os.path.basename(resolved_path)}':",
                f"  Tipo: {'Carpeta 📁' if is_dir else 'Archivo 📄'}",
                f"  Ruta completa: {resolved_path}",
                f"  Creado el: {created}",
                f"  Modificado el: {modified}"
            ]
            if not is_dir:
                lines.append(f"  Tamaño: {stat.st_size / 1024:.1f} KB")
            return "\n".join(lines)

        # 14. ORGANIZE DESKTOP
        elif action == "organize_desktop":
            desktop = resolve_path("desktop")
            cats = {
                "Documentos": [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".txt", ".md"],
                "Imagenes": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".ico"],
                "Zips": [".zip", ".rar", ".7z", ".tar", ".gz"],
                "Ejecutables": [".exe", ".msi", ".bat", ".vbs"]
            }
            
            moved_count = 0
            for item in os.listdir(desktop):
                item_path = os.path.join(desktop, item)
                if os.path.isdir(item_path) or item.startswith("."):
                    continue
                
                ext = os.path.splitext(item)[1].lower()
                for cat_name, extensions in cats.items():
                    if ext in extensions:
                        dest_folder = os.path.join(desktop, cat_name)
                        os.makedirs(dest_folder, exist_ok=True)
                        shutil.move(item_path, os.path.join(dest_folder, item))
                        moved_count += 1
                        break
            
            msg = f"Organización del Escritorio completada. Se ordenaron {moved_count} archivos en carpetas categóricas."
            if player:
                player.write_log(f"🧹 {msg}")
            return msg

        else:
            return f"Acción '{action}' no soportada en file_controller."

    except Exception as e:
        traceback.print_exc()
        return f"Error ejecutando la operación de archivo: {str(e)}"
