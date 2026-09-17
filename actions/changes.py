# -*- coding: utf-8 -*-
"""changes.py — Diario de cambios por carpeta (git automático local).

Mira carpetas de trabajo tuyas (las que vas visitando con 'ver') y te
resume qué cambió usando git en local: iniciar repo, ver estado, resumen
de todas, y commit automático opcional (autocommit con confirm='SÍ').
"""
import json
import os
import subprocess
from datetime import datetime

_MEM = os.path.join(os.path.dirname(__file__), "..", "memory", "changes_state.json")
_CONFIRM = ("sí", "si", "yes", "confirmar", "confirmo", "1", "dale")


def _git(carpeta, *args):
    try:
        r = subprocess.run(
            ["git", "-C", carpeta, *args],
            capture_output=True, text=True, cwd=carpeta, timeout=30,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except FileNotFoundError:
        return -1, "", "git no está instalado"
    except Exception as e:
        return -1, "", str(e)


def _estado():
    if not os.path.exists(_MEM):
        return {"carpetas": []}
    try:
        with open(_MEM, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {"carpetas": []}
    except Exception:
        return {"carpetas": []}


def _guardar(d):
    os.makedirs(os.path.dirname(_MEM), exist_ok=True)
    tmp = _MEM + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _MEM)


def _registrar(ruta):
    d = _estado()
    ruta = os.path.abspath(ruta)
    if ruta not in d["carpetas"]:
        d["carpetas"].append(ruta)
        _guardar(d)


def _es_repo(ruta):
    rc, _, _ = _git(ruta, "rev-parse", "--is-inside-work-tree")
    return rc == 0


def _conteo(rc, out):
    if rc != 0:
        return None
    lineas = [l.strip() for l in out.splitlines() if l.strip()]
    from collections import Counter
    cont = Counter()
    for l in lineas:
        for pref in ("M", "A", "D", "R", "C", "?", "!!"):
            if l.startswith(pref):
                cont[pref] += 1
                break
        else:
            cont["~"] += 1
    return lineas, cont


def _corto(out, limite):
    lineas = [l.strip() for l in out.splitlines() if l.strip()]
    if len(lineas) <= limite:
        return "; ".join(lineas) or "sin cambios"
    return "; ".join(lineas[:limite]) + f" (+{len(lineas) - limite} más)"


def _tipo_archivo(lin):
    nombre = re_split(lin)
    if nombre.lower().endswith((".py", ".pyc")):
        return "código"
    if nombre.lower().endswith((".md", ".txt", ".rst")):
        return "documento"
    if nombre.lower().endswith(("json", "yaml", "yml", "toml", "cfg", "ini")):
        return "config"
    return "archivo"


def re_split(lin):
    lin = lin[2:].strip()
    if lin.endswith('"') or lin.endswith("'"):
        lin = lin[1:-1]
    return os.path.basename(lin)


def _pl(n):
    return "cambio" if n == 1 else "cambios"


def changes(parameters: dict, player=None, speak=None) -> str:
    """Diario de cambios de una carpeta con git automático local."""
    action = str(parameters.get("action", "ver")).strip().lower()
    carpeta = str(parameters.get("carpeta", "") or parameters.get("ruta", "")).strip()
    mensaje = str(parameters.get("mensaje", "")).strip()
    limite = max(3, min(20, int(parameters.get("limite") or 8)))
    confirm = str(parameters.get("confirm", "")).strip().lower()

    if action in ("test", "chequear"):
        return "El diario de cambios funciona si git está instalado en el equipo."

    if action in ("resumen", "todas"):
        d = _estado()
        carpetas = d.get("carpetas", [])
        if not carpetas:
            return "No tengo carpetas registradas. Usá action='ver' con una carpeta la primera vez."
        filas = []
        for c in carpetas:
            if not os.path.isdir(c):
                continue
            if not _es_repo(c):
                filas.append(f"{os.path.basename(c)}: sin repo")
                continue
            rc, out, _ = _git(c, "status", "--porcelain")
            n = len([l for l in out.splitlines() if l.strip()]) if rc == 0 else 0
            rc2, out2, _ = _git(c, "log", "-1", "--format=%cr")
            ultimo = out2.splitlines()[0] if rc2 == 0 and out2 else "sin commits"
            filas.append(f"{os.path.basename(c)}: {n} {_pl(n)}, último commit {ultimo}")
        if player:
            player.write_log("📊 Diario de cambios: " + " | ".join(filas))
        return "Tus carpetas registradas: " + ". ".join(filas) + "."

    if not carpeta:
        return "Decime sobre qué carpeta, por ejemplo carpeta='C:\\Users\\venez\\proyectos\\foo'."

    carpeta = os.path.abspath(carpeta)
    if not os.path.isdir(carpeta):
        return f"No existe la carpeta '{carpeta}'."

    if action in ("iniciar", "git_init"):
        if confirm not in _CONFIRM:
            return f"Para crear el repo git en '{carpeta}' y hacer el primer commit, confirmá con 'SÍ'."
        rc, _, err = _git(carpeta, "init")
        if rc != 0 and "reinitialized" not in (err or "").lower():
            return f"No pude inicializar git: {err}"
        rc2, _, err2 = _git(carpeta, "add", "-A")
        if rc2 != 0:
            return f"No pude agregar archivos: {err2}"
        rc3, _, err3 = _git(carpeta, "commit", "-m", "inicio del diario de cambios")
        _registrar(carpeta)
        if rc3 != 0:
            bajo = (err3 or "").lower()
            if (not err3) or "nothing to commit" in bajo or "no changes" in bajo:
                if player:
                    player.write_log(f"📁 Repo iniciado en {carpeta} (sin archivos)")
                return f"Listo, creé el repo git en {carpeta}. Todavía no hay archivos para el commit inicial."
            return f"Inicié el repo pero el commit inicial falló: {err3}"
        if player:
            player.write_log(f"📁 Repo iniciado en {carpeta}")
        return f"Listo, creé el repo git en {carpeta} con un commit inicial."

    if action in ("autocommit", "commit", "guardar_cambios"):
        if confirm not in _CONFIRM:
            return f"Para commitear todos los cambios de '{carpeta}' confirmá con 'SÍ'."
        if not _es_repo(carpeta):
            return f"'{carpeta}' todavía no es un repo git. Usá action='iniciar' con confirm='SÍ' para crearlo."
        rc, _, err = _git(carpeta, "add", "-A")
        if rc != 0:
            return f"No pude agregar los cambios: {err}"
        msg = f"auto: {datetime.now().strftime('%d/%m %H:%M')}"
        if mensaje:
            msg += f" – {mensaje[:120]}"
        rc2, _, err2 = _git(carpeta, "commit", "-m", msg)
        if rc2 != 0:
            if "nothing to commit" in (err2 or "").lower() or "no changes" in (err2 or "").lower():
                _registrar(carpeta)
                return f"No hay cambios nuevos para commitear en {os.path.basename(carpeta)}."
            return f"El commit falló: {err2}"
        _registrar(carpeta)
        if player:
            player.write_log(f"📦 Commit en {carpeta}: {msg}")
        return f"Listo, committeé todo en {os.path.basename(carpeta)} ({msg})."

    if action in ("resumen", "todas"):
        d = _estado()
        carpetas = d.get("carpetas", [])
        if not carpetas:
            return "No tengo carpetas registradas. Usá action='ver' con una carpeta la primera vez."
        filas = []
        for c in carpetas:
            if not os.path.isdir(c):
                continue
            if not _es_repo(c):
                filas.append(f"{os.path.basename(c)}: sin repo")
                continue
            rc, out, _ = _git(c, "status", "--porcelain")
            n = len([l for l in out.splitlines() if l.strip()]) if rc == 0 else 0
            rc2, out2, _ = _git(c, "log", "-1", "--format=%cr")
            ultimo = out2.splitlines()[0] if rc2 == 0 and out2 else "sin commits"
            filas.append(f"{os.path.basename(c)}: {n} {_pl(n)}, último commit {ultimo}")
        if player:
            player.write_log("📊 Diario de cambios: " + " | ".join(filas))
        return "Tus carpetas registradas: " + ". ".join(filas) + "."

    # ver (default)
    _registrar(carpeta)
    if not _es_repo(carpeta):
        return (f"'{carpeta}' no tiene repo git todavía. Si querés, con action='iniciar' "
                f"y confirm='SÍ' lo creo y hago un commit inicial.")
    rc, out, _ = _git(carpeta, "status", "--porcelain")
    rc2, out2, _ = _git(carpeta, "log", "-3", "--format=%h %ad %s", "--date=format:%d/%m %H:%M")
    res = _conteo(rc, out)
    if res is None:
        return f"No pude leer el estado de git en {carpeta}."
    lineas, cont = res
    if not lineas:
        return f"En {os.path.basename(carpeta)} no hay cambios: todo está committeado."
    det = _corto(out, limite)
    detalle = det.replace(";", "\n   ") if len(lineas) <= limite else "\n   " + det.replace("; ", "\n   ")
    if player:
        player.write_log(f"🔄 {os.path.basename(carpeta)}: {len(lineas)} cambios")
    historial = []
    for h in (out2 or "").splitlines():
        if h.strip():
            historial.append(h.strip())
    hist = ", ".join(historial[:3]) if historial else "sin commits"
    base = f"En {os.path.basename(carpeta)} hay {len(lineas)} {_pl(len(lineas))}:{detalle}."
    if hist != "sin commits":
        base += f" Últimos commits: {hist}."
    base += " Si querés, commitear todo con action='autocommit' y confirm='SÍ'."
    return base