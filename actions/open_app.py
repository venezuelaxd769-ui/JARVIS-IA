import os
import subprocess
import webbrowser
import traceback
import shutil
from pathlib import Path


def _open_with_default(path):
    """Abre un archivo/carpeta con la aplicación por defecto del sistema.
    Windows → os.startfile; Linux → xdg-open."""
    return os.startfile(str(path)) if os.name == "nt" else subprocess.Popen(
        ["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def _find_windows_app(app_name: str) -> str | None:
    """Localiza el ejecutable de una app instalada en Windows.
    1) PATH (shutil.which)  2) App Paths del registro."""
    if os.name != "nt":
        return None
    try:
        exe = shutil.which(app_name) or shutil.which(app_name + ".exe")
        if exe:
            return exe
    except Exception:
        pass
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
        for branch in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                k = winreg.OpenKey(branch, key_path)
            except OSError:
                continue
            idx = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, idx)
                except OSError:
                    break
                idx += 1
                if sub.lower() == f"{Path(app_name).stem.lower()}.exe":
                    try:
                        subk = winreg.OpenKey(branch, key_path + "\\" + sub)
                        val, _ = winreg.QueryValueEx(subk, "")
                        if val and os.path.exists(val):
                            return val
                    except OSError:
                        pass
    except Exception:
        pass
    return None

COMMON_PATHS = [
    "/usr/bin", "/usr/local/bin", "/usr/sbin", "/snap/bin",
    str(Path.home() / ".local/bin"),
    str(Path.home() / ".cargo/bin"),
    str(Path.home() / "Applications"),
    str(Path.home() / "AppImages"),
]

DESKTOP_DIRS = [
    Path("/usr/share/applications"),
    Path("/usr/local/share/applications"),
    Path.home() / ".local/share/applications",
    Path("/var/lib/flatpak/exports/share/applications"),
    Path.home() / ".local/share/flatpak/exports/share/applications",
]

FLATPAK_APP_DIRS = [
    Path("/var/lib/flatpak/app"),
    Path.home() / ".local/share/flatpak/app",
]

_SKIP_WRAPPERS = {"env", "sh", "bash", "dbus-launch", "gtk-launch", "kioclient",
                  "exo-open", "gio", "gapplication", "snap"}


def _parse_exec(exec_line: str) -> str | None:
    """Extract the real executable from a desktop file Exec= line.
    Handles wrappers like 'env VAR=val /usr/bin/app', 'sh -c ...', etc."""
    parts = exec_line.split("%")[0].strip().split()
    if not parts:
        return None

    candidate = parts[0].strip('"').strip("'")
    if candidate.lower() in _SKIP_WRAPPERS:
        for p in parts[1:]:
            p = p.strip('"').strip("'")
            if not p.startswith("-") and "=" not in p and not p.startswith("$"):
                candidate = p
                break

    return shutil.which(candidate) or candidate if shutil.which(candidate.split("/")[-1]) else None


_parsed_exec_cache: dict[str, str | None] = {}


def _find_desktop_files(name: str) -> list[tuple[str, str, str]]:
    """Search ALL desktop dirs for apps matching name.
    Returns list of (executable, desktop_name, desktop_class)."""
    name_lower = name.lower().strip()
    results = []
    seen_execs = set()
    for ddir in DESKTOP_DIRS:
        if not ddir.exists():
            continue
        for df in ddir.glob("*.desktop"):
            try:
                content = df.read_text(encoding="utf-8", errors="replace")
                exec_raw = ""
                desktop_name = ""
                no_display = False
                for line in content.splitlines():
                    ls = line.strip()
                    if ls.startswith("Exec="):
                        exec_raw = ls.split("=", 1)[1].strip()
                    elif ls.startswith("Name=") and not desktop_name:
                        desktop_name = ls.split("=", 1)[1].strip()
                    elif ls.startswith("NoDisplay="):
                        no_display = ls.split("=", 1)[1].strip() == "true"

                if no_display:
                    continue
                if not exec_raw:
                    continue

                cache_key = f"{df}:{exec_raw}"
                if cache_key not in _parsed_exec_cache:
                    _parsed_exec_cache[cache_key] = _parse_exec(exec_raw)
                exec_val = _parsed_exec_cache[cache_key]

                if not exec_val or exec_val in seen_execs:
                    continue

                entry_name = desktop_name.lower()
                if name_lower == entry_name or name_lower in entry_name:
                    seen_execs.add(exec_val)
                    cls = df.stem
                    results.append((exec_val, desktop_name, cls))
            except Exception:
                continue

    if results:
        return results

    for ddir in DESKTOP_DIRS:
        if not ddir.exists():
            continue
        for df in ddir.glob("*.desktop"):
            try:
                content = df.read_text(encoding="utf-8", errors="replace")
                exec_raw = ""
                desktop_name = ""
                generic_name = ""
                categories = ""
                no_display = False
                for line in content.splitlines():
                    ls = line.strip()
                    if ls.startswith("Exec="):
                        exec_raw = ls.split("=", 1)[1].strip()
                    elif ls.startswith("Name=") and not desktop_name:
                        desktop_name = ls.split("=", 1)[1].strip()
                    elif ls.startswith("GenericName=") and not generic_name:
                        generic_name = ls.split("=", 1)[1].strip()
                    elif ls.startswith("Categories="):
                        categories = ls.split("=", 1)[1].strip().lower()
                    elif ls.startswith("NoDisplay="):
                        no_display = ls.split("=", 1)[1].strip() == "true"

                if no_display or not exec_raw:
                    continue

                cache_key = f"{df}:{exec_raw}"
                if cache_key not in _parsed_exec_cache:
                    _parsed_exec_cache[cache_key] = _parse_exec(exec_raw)
                exec_val = _parsed_exec_cache[cache_key]

                if not exec_val or exec_val in seen_execs:
                    continue

                match = False
                for text in [desktop_name, generic_name, df.stem]:
                    if name_lower in text.lower():
                        match = True
                        break
                words = set(name_lower.split())
                for text in [desktop_name, generic_name, categories]:
                    if words & set(text.lower().split()):
                        match = True
                        break

                if match:
                    seen_execs.add(exec_val)
                    cls = df.stem
                    results.append((exec_val, desktop_name, cls))
            except Exception:
                continue

    return results


def _find_flatpak(name: str) -> str | None:
    """Find a flatpak app by partial name match."""
    name_lower = name.lower().strip()
    try:
        r = subprocess.run(["flatpak", "list", "--columns=application", "--app"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            for app_id in r.stdout.splitlines():
                app_id = app_id.strip()
                app_short = app_id.split(".")[-1].lower()
                if name_lower == app_short or name_lower in app_short:
                    return app_id
    except Exception:
        pass

    for app_dir in FLATPAK_APP_DIRS:
        if not app_dir.exists():
            continue
        for d in app_dir.iterdir():
            if d.is_dir():
                app_short = d.name.lower()
                app_short2 = d.name.split(".")[-1].lower()
                if name_lower == app_short or name_lower == app_short2 or name_lower in app_short:
                    return d.name
                if name_lower in app_short:
                    return d.name
    return None


def _find_appimage(name: str) -> str | None:
    """Search common AppImage locations."""
    name_lower = name.lower().strip()
    appimage_dirs = [
        Path.home() / "Applications",
        Path.home() / "AppImages",
        Path.home() / ".local/bin",
        Path("/opt"),
    ]
    for d in appimage_dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.name.endswith(".AppImage") or f.name.endswith(".appimage"):
                fname = f.name.replace(".AppImage", "").replace(".appimage", "").lower()
                if name_lower == fname or name_lower in fname:
                    os.chmod(str(f), 0o755)
                    return str(f)
    return None


def _find_in_path(name: str) -> str | None:
    """Search PATH including extra common Linux paths."""
    exe = shutil.which(name)
    if exe:
        return exe
    for p in COMMON_PATHS:
        candidate = Path(p) / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _find_best_executable(name: str) -> tuple[str, str, str] | None:
    """Try every method to find the app. Returns (executable_or_desktop, source_description, desktop_class)."""
    name_lower = name.lower().strip()

    desktop_results = _find_desktop_files(name)
    if desktop_results:
        exe, display_name, cls = desktop_results[0]
        return exe, f"desktop:{display_name}", cls

    exe = _find_in_path(name)
    if exe:
        return exe, "path", ""

    appimage = _find_appimage(name)
    if appimage:
        return appimage, "appimage", ""

    flatpak_app = _find_flatpak(name)
    if flatpak_app:
        return flatpak_app, "flatpak", ""

    return None


def _launch(executable: str, source: str, desktop_class: str = "", folder_path: str = "") -> bool:
    """Launch an app. Handles desktop files (via gtk-launch), flatpak, AppImage, and normal binaries."""
    try:
        if source.startswith("desktop:") and desktop_class:
            try:
                args = ["gtk-launch", desktop_class]
                if folder_path:
                    subprocess.Popen(args + [folder_path],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(args,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass

        if source == "flatpak":
            args = ["flatpak", "run", executable]
            if folder_path:
                args.extend(["--", folder_path])
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True

        if executable.endswith(".AppImage") or executable.endswith(".appimage"):
            os.chmod(executable, 0o755)
            args = [executable]
            if folder_path:
                args.append(folder_path)
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True

        file_managers = {"nautilus", "dolphin", "thunar", "pcmanfm", "nemo", "caja", "ranger"}
        args = [executable]
        if folder_path and any(fm in executable.lower() for fm in file_managers):
            expanded = Path(folder_path).expanduser().resolve()
            if expanded.exists() and expanded.is_dir():
                args.append(str(expanded))
            else:
                args.append(folder_path)

        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        try:
            subprocess.Popen(executable + (" " + folder_path if folder_path else ""),
                           shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False


def open_app(parameters: dict, response=None, player=None) -> str:
    app_name = parameters.get("app_name", "").strip()
    folder_path = parameters.get("path", "").strip()
    if not app_name:
        return "Error: Se requiere el parámetro 'app_name'."

    app_lower = app_name.lower().strip()
    home = str(Path.home())

    try:
        if app_lower.startswith("http://") or app_lower.startswith("https://") or any(app_lower.endswith(tld) for tld in [".com", ".org", ".net", ".es", ".cl"]):
            url = app_name if app_lower.startswith("http") else f"https://{app_name}"
            webbrowser.open(url)
            msg = f"Abriendo el sitio web: '{url}'."
            if player:
                player.write_log(f"🌐 {msg}")
            return msg

        path_obj = Path(app_name)
        if path_obj.exists():
            _open_with_default(str(path_obj.resolve()))
            kind = "carpeta" if path_obj.is_dir() else "archivo"
            msg = f"Abriendo {kind} local: '{app_name}'."
            if player:
                player.write_log(f"📁 {msg}")
            return msg

        virtual_folders = {
            "desktop": os.path.join(home, "Desktop"),
            "escritorio": os.path.join(home, "Desktop"),
            "downloads": os.path.join(home, "Downloads"),
            "descargas": os.path.join(home, "Downloads"),
            "documents": os.path.join(home, "Documents"),
            "documentos": os.path.join(home, "Documents"),
            "pictures": os.path.join(home, "Pictures"),
            "imagenes": os.path.join(home, "Pictures"),
            "music": os.path.join(home, "Music"),
            "musica": os.path.join(home, "Music"),
            "videos": os.path.join(home, "Videos"),
            "home": home,
            "inicio": home,
        }
        if app_lower in virtual_folders:
            folder_path = virtual_folders[app_lower]
            _open_with_default(folder_path)
            msg = f"Abriendo carpeta del sistema: '{app_lower}'."
            if player:
                player.write_log(f"📁 {msg}")
            return msg

        # ── Windows: buscar la app por PATH o App Paths del registro ──────
        if os.name == "nt":
            exe = _find_windows_app(app_name)
            if exe:
                subprocess.Popen([exe] + ([folder_path] if folder_path else []),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                msg = f"Abriendo '{app_name}'."
                if folder_path:
                    msg = f"Abriendo '{app_name}' con: '{folder_path}'."
                if player:
                    player.write_log(f"🚀 {msg}")
                return msg

        result = _find_best_executable(app_name)
        if result:
            executable, source, desktop_class = result
            if _launch(executable, source, desktop_class, folder_path):
                msg = f"Abriendo '{app_name}'."
                if source == "flatpak":
                    msg = f"Abriendo '{app_name}' (Flatpak)."
                elif source == "appimage":
                    msg = f"Abriendo '{app_name}' (AppImage)."
                if folder_path:
                    msg = f"Abriendo '{app_name}' en: '{folder_path}'."
                if player:
                    player.write_log(f"🚀 {msg}")
                return msg

        doc_path = _find_document(app_name)
        if doc_path:
            _open_with_default(doc_path)
            msg = f"Abriendo documento: '{Path(doc_path).name}'."
            if player:
                player.write_log(f"📄 {msg}")
            return msg

        try:
            subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            msg = f"Abriendo '{app_name}'."
            if player:
                player.write_log(f"🚀 {msg}")
            return msg
        except Exception:
            return f"No pude encontrar '{app_name}' en el sistema."

    except Exception as e:
        traceback.print_exc()
        return f"Error intentando abrir '{app_name}': {str(e)}"


def _find_document(app_name: str) -> str | None:
    home = Path.home()
    search_dirs = [
        home / "Desktop", home / "Escritorio",
        home / "Documents", home / "Documentos",
        home / "Downloads", home / "Descargas",
        home / "Pictures", home / "Imágenes",
        home / "Music", home / "Música",
        home / "Videos",
    ]
    doc_extensions = {".docx", ".xlsx", ".pptx", ".pdf", ".txt", ".csv",
                      ".zip", ".png", ".jpg", ".jpeg", ".gif", ".md",
                      ".py", ".sh", ".mp4", ".mp3", ".wav", ".flac",
                      ".ods", ".odt", ".odp", ".epub", ".html"}
    app_lower = app_name.lower().strip()
    for base_dir in search_dirs:
        if not base_dir.exists():
            continue
        for root, dirs, files in os.walk(base_dir):
            depth = root.count(os.sep) - str(base_dir).count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in doc_extensions:
                    file_name_no_ext = os.path.splitext(file)[0].lower()
                    if app_lower == file_name_no_ext or app_lower in file_name_no_ext:
                        return os.path.join(root, file)
    return None
