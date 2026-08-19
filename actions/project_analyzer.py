"""project_analyzer.py — Analiza la estructura y tipo de un proyecto.

Detecta el lenguaje/framework, dependencias, archivos de entrada,
tests y estructura general. Útil para que Nia entienda un proyecto
antes de modificarlo.
"""
import os
from pathlib import Path

_MAX_FILES = 500

_MARKERS = {
    "Python": {
        "files": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
                   "Pipfile", "poetry.lock", "conda.yaml", "environment.yml"],
        "exts": [".py"],
    },
    "JavaScript": {
        "files": ["package.json", "tsconfig.json", "webpack.config.js",
                   "vite.config.js", "next.config.js", ".babelrc",
                   "jest.config.js", "eslint.config.js"],
        "exts": [".js", ".mjs", ".cjs"],
    },
    "TypeScript": {
        "files": ["tsconfig.json", "package.json"],
        "exts": [".ts", ".tsx"],
    },
    "Rust": {
        "files": ["Cargo.toml", "Cargo.lock"],
        "exts": [".rs"],
    },
    "Go": {
        "files": ["go.mod", "go.sum"],
        "exts": [".go"],
    },
    "C": {
        "files": ["Makefile", "CMakeLists.txt", "meson.build", "configure.ac"],
        "exts": [".c", ".h"],
    },
    "C++": {
        "files": ["CMakeLists.txt", "meson.build", "Makefile", "conanfile.txt"],
        "exts": [".cpp", ".hpp", ".cc", ".hh"],
    },
    "C#": {
        "files": ["*.csproj", "*.sln", "Directory.Build.props"],
        "exts": [".cs"],
    },
    "Java": {
        "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "exts": [".java"],
    },
    "GDScript": {
        "files": ["project.godot", "export_presets.cfg"],
        "exts": [".gd", ".tscn", ".tres"],
    },
    "Swift": {
        "files": ["Package.swift", "*.xcodeproj", "*.xcworkspace"],
        "exts": [".swift"],
    },
    "Kotlin": {
        "files": ["build.gradle.kts", "gradlew"],
        "exts": [".kt", ".kts"],
    },
}


def _scan(base):
    """Escaneo ligero: solo primer nivel + contadores globales."""
    base = Path(base).resolve()
    stats = {
        "ext_count": {},
        "files_total": 0,
        "dirs_total": 0,
        "markers_found": [],
        "test_files": [],
        "entry_points": [],
    }
    try:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if d not in {".git", ".venv", "node_modules", "__pycache__",
                                    "dist", "build", ".tox", ".mypy_cache", "env"}]
            depth = len(Path(root).relative_to(base).parts)
            if depth > 4:
                continue
            rel_root = Path(root).relative_to(base)
            stats["dirs_total"] += 1
            for f in files:
                stats["files_total"] += 1
                if stats["files_total"] > _MAX_FILES:
                    return stats
                ext = Path(f).suffix.lower()
                stats["ext_count"][ext] = stats["ext_count"].get(ext, 0) + 1
                rel = str(rel_root / f)
                fl = f.lower()
                if "test" in fl or "spec" in fl:
                    stats["test_files"].append(rel)
                if fl in ("main.py", "app.py", "index.js", "index.ts",
                          "main.go", "main.rs", "main.cpp", "main.c",
                          "program.cs", "program.fsx", "server.py",
                          "__main__.py"):
                    stats["entry_points"].append(rel)
    except Exception:
        pass
    return stats


def _detect_lang(stats, base):
    base = Path(base)
    for lang, cfg in _MARKERS.items():
        for marker in cfg["files"]:
            if list(base.glob(marker)):
                return lang
    exts = stats["ext_count"]
    top = sorted(exts.items(), key=lambda x: -x[1])
    ext_map = {".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
               ".rs": "Rust", ".go": "Go", ".c": "C", ".cpp": "C++",
               ".cs": "C#", ".java": "Java", ".gd": "GDScript",
               ".swift": "Swift", ".kt": "Kotlin"}
    if top:
        main_ext = top[0][0]
        if main_ext in ext_map:
            return ext_map[main_ext]
    return None


def _dep_files(base):
    """Lista archivos de dependencias."""
    dep_names = ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile",
                 "package.json", "Cargo.toml", "go.mod", "pom.xml",
                 "build.gradle", "Gemfile", "composer.json"]
    found = []
    for name in dep_names:
        p = base / name
        if p.exists():
            found.append(name)
    return found


def project_analyzer(parameters: dict, player=None) -> str:
    """Analiza un proyecto: tipo, estructura, dependencias y entry points."""
    path = str(parameters.get("path", ".")).strip()
    base = Path(path).expanduser().resolve()

    if not base.exists():
        return f"Ruta no encontrada: {base}"
    if not base.is_dir():
        return f"No es un directorio: {base}"

    if player:
        player.write_log(f"🔍 Analizando proyecto: {base.name}...")

    stats = _scan(base)
    lang = _detect_lang(stats, base)
    deps = _dep_files(base)

    lines = [f"📁 Proyecto: {base.name}"]
    lines.append(f"   Ruta: {base}")
    if lang:
        lines.append(f"   Lenguaje/Framework detectado: {lang}")

    lines.append(f"   Archivos: {stats['files_total']} | Directorios: {stats['dirs_total']}")

    if deps:
        lines.append(f"   Dependencias: {', '.join(deps)}")

    exts = stats["ext_count"]
    if exts:
        top_exts = sorted(exts.items(), key=lambda x: -x[1])[:8]
        ext_str = ", ".join(f"{e}({n})" for e, n in top_exts)
        lines.append(f"   Extensiones principales: {ext_str}")

    if stats["entry_points"]:
        lines.append(f"   Entry points: {', '.join(stats['entry_points'][:5])}")

    if stats["test_files"]:
        lines.append(f"   Tests encontrados: {len(stats['test_files'])}")

    # Estructura de primer nivel
    try:
        entries = sorted(base.iterdir(), key=lambda x: (x.is_file(), x.name))
        lines.append("   Estructura:")
        shown = 0
        for e in entries:
            if e.name.startswith(".") or e.name in {".git", "__pycache__",
                                                     "node_modules", ".venv"}:
                continue
            prefix = "  📁" if e.is_dir() else "  📄"
            lines.append(f"    {prefix} {e.name}")
            shown += 1
            if shown > 15:
                lines.append("    ... (más elementos)")
                break
    except Exception:
        pass

    return "\n".join(lines)
