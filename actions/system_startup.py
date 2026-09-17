# -*- coding: utf-8 -*-
"""system_startup.py — Programas de inicio de Windows por voz.

Listar qué arranca con la sesión (registry Run/RunOnce + carpeta Inicio),
agregar, quitar o deshabilitar/habilitar entradas.
"""
import os
import winreg

_IS_WIN = os.name == "nt"

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUNONCE_KEY = r"Software\Microsoft\Windows\CurrentVersion\RunOnce"
_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


def _startup_folder():
    return os.path.join(os.environ.get("APPDATA", ""),
                        r"Microsoft\Windows\Start Menu\Programs\Startup")


def _iter_registry():
    entries = {}
    hives = [(winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM")]
    for hive, prefix in hives:
        for key, sub in ((_RUN_KEY, "Run"), (_RUNONCE_KEY, "RunOnce")):
            try:
                k = winreg.OpenKey(hive, key)
            except OSError:
                continue
            try:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    if name != "Default":
                        entries[(name, prefix, sub)] = value
                    i += 1
            finally:
                winreg.CloseKey(k)
    return entries


def _iter_folder():
    folder, out = _startup_folder(), []
    try:
        for fn in sorted(os.listdir(folder)):
            if not fn.startswith("."):
                out.append((fn, folder))
    except OSError:
        pass
    allusers = r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Startup"
    try:
        for fn in sorted(os.listdir(allusers)):
            if not fn.startswith("."):
                out.append((fn, allusers))
    except OSError:
        pass
    return out


def _find(name, entries, folder_items):
    low = name.lower()
    for (en, prefix, sub), val in entries.items():
        if low in en.lower():
            return en, prefix, sub, val
    for (fn, folder) in folder_items:
        if low in fn.lower():
            return fn, folder, None, fn
    return None


def _list_startup():
    entries = _iter_registry()
    folder_items = _iter_folder()
    lines = [f"🚀 Programas de inicio ({len(entries) + len(folder_items)} entradas):"]
    for (en, prefix, sub), val in sorted(entries.items()):
        lines.append(f"   • {en} [{prefix}/{sub}] → {str(val)[:70]}")
    folder_items = _iter_folder()
    for (fn, folder) in folder_items:
        lines.append(f"   • {fn} [carpeta: {os.path.basename(folder)}]")
    return "\n".join(lines)


def system_startup(parameters: dict, player=None, speak=None) -> str:
    """Programas de inicio: listar, agregar, quitar, deshabilitar o habilitar."""
    action = str(parameters.get("action", "listar")).strip().lower()
    name = str(parameters.get("name", "")).strip()
    path = str(parameters.get("path", "")).strip()
    if player:
        player.write_log(f"🚀 system_startup: {action} {name}")
    if not _IS_WIN:
        return "Solo en Windows gestiono los programas de inicio."

    if action in ("listar", "list", "ls", "ver"):
        return _list_startup()

    if action in ("agregar", "add", "poner"):
        if not name or not path:
            return "Necesito name (nombre visible) y path (ruta del programa), ej. 'agregar' con name='Steam', path='C:\\\\Program Files\\\\Steam\\\\steam.exe'."
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, path)
            winreg.CloseKey(k)
            return f"Listo, '{name}' ahora arranca con la sesión."
        except OSError as e:
            return f"No pude agregar '{name}': {e}"

    if action in ("quitar", "remove", "delete", "borrar"):
        entries = _iter_registry()
        folder_items = _iter_folder()
        hit = _find(name, entries, folder_items)
        if not hit:
            return f"No encontré '{name}' entre los programas de inicio."
        en, where, sub, _val = hit
        if sub is None:
            try:
                os.remove(os.path.join(where, en))
                return f"Quité '{en}' de la carpeta Inicio."
            except OSError as e:
                return f"No pude quitar '{en}': {e}"
        hive = winreg.HKEY_CURRENT_USER if where == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        key_path = _RUNONCE_KEY if sub == "RunOnce" else _RUN_KEY
        try:
            k = winreg.OpenKey(hive, key_path, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(k, en)
            winreg.CloseKey(k)
            return f"Quité '{en}' del inicio ({where}/{sub})."
        except OSError as e:
            return f"No pude quitar '{en}': {e}"

    if action in ("deshabilitar", "disable"):
        entries = _iter_registry()
        hit = _find(name, entries, _iter_folder())
        if not hit or hit[2] is None:
            return f"No encontré '{name}' en el registro de inicio (las carpetas no se deshabilitan)."
        en, _w, _s, _v = hit
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APPROVED_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(k, en, 0, winreg.REG_BINARY, b"\x02\x00\x00\x00\x03\x00\x00\x00")
            winreg.CloseKey(k)
            return f"'{en}' deshabilitado (no arrancará con la sesión por ahora)."
        except OSError as e:
            return f"No pude deshabilitar '{en}': {e}"

    if action in ("habilitar", "enable"):
        entries = _iter_registry()
        hit = _find(name, entries, _iter_folder())
        if not hit or hit[2] is None:
            return f"No encontré '{name}' en el registro de inicio."
        en, _w, _s, _v = hit
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _APPROVED_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(k, en, 0, winreg.REG_BINARY, b"\x02\x00\x00\x00\x00\x00\x00\x00")
            winreg.CloseKey(k)
            return f"'{en}' habilitado de nuevo."
        except OSError as e:
            return f"No pude habilitar '{en}': {e}"

    return "Acciones: listar | agregar (name+path) | quitar (name) | deshabilitar (name) | habilitar (name)."


if __name__ == "__main__":
    import sys
    print(system_startup({"action": sys.argv[1] if len(sys.argv) > 1 else "listar",
                          "name": sys.argv[2] if len(sys.argv) > 2 else "",
                          "path": sys.argv[3] if len(sys.argv) > 3 else ""}))