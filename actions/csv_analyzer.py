"""csv_analyzer.py — Lee, analiza y resume archivos CSV.

Estadísticas automáticas: columnas, tipos, filas, nulos, duplicados.
Puede mostrar muestras, filtrar y exportar. Sin dependencias externas
(módulo csv estándar de Python).
"""
import csv
import os
from pathlib import Path
from collections import Counter

_MAX_SAMPLE = 10


def _detect_type(values):
    """Detecta el tipo predominante de una columna."""
    int_count = 0
    float_count = 0
    date_count = 0
    for v in values:
        v = v.strip()
        if not v:
            continue
        try:
            int(v)
            int_count += 1
            continue
        except ValueError:
            pass
        try:
            float(v)
            float_count += 1
            continue
        except ValueError:
            pass
        if len(v) >= 8 and v[4] == "-" and v[7] == "-":
            date_count += 1
    total = int_count + float_count + date_count
    if total == 0:
        return "texto"
    if int_count / total > 0.8:
        return "entero"
    if (int_count + float_count) / total > 0.8:
        return "decimal"
    if date_count / total > 0.8:
        return "fecha"
    return "texto"


def csv_analyzer(parameters: dict, player=None) -> str:
    """Analiza un CSV: estadísticas, muestras y resumen."""
    path = str(parameters.get("path", "")).strip()
    delimiter = str(parameters.get("delimiter", ",")).strip() or ","
    max_rows = int(parameters.get("max_rows", 500))
    show_sample = int(parameters.get("show_sample", _MAX_SAMPLE))
    filter_col = str(parameters.get("filter_column", "")).strip()
    filter_val = str(parameters.get("filter_value", "")).strip()

    if not path:
        return "Necesito la ruta del CSV."

    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        return f"Archivo no encontrado: {path}"

    if player:
        player.write_log(f"📊 Analizando CSV: {os.path.basename(path)}...")

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            sample = f.read(4096)
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except Exception:
        pass

    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=delimiter)
            headers = reader.fieldnames or []
            rows = []
            null_counts = Counter()
            col_values = {h: [] for h in headers}
            duplicates = 0
            seen = set()
            total = 0

            for row in reader:
                total += 1
                if total > max_rows:
                    break
                row_key = tuple(row.get(h, "") for h in headers)
                if row_key in seen:
                    duplicates += 1
                seen.add(row_key)
                rows.append(row)
                for h in headers:
                    val = row.get(h, "")
                    if not val or val.strip() == "":
                        null_counts[h] += 1
                    else:
                        col_values[h].append(val)
    except Exception as e:
        return f"Error leyendo CSV: {e}"

    if not headers:
        return f"El archivo no tiene columnas detectables: {path}"

    # Estadísticas por columna
    lines = [f"📊 {os.path.basename(path)}"]
    lines.append(f"   Columnas: {len(headers)} | Filas leídas: {total}")
    lines.append(f"   Duplicados: {duplicates}")
    lines.append(f"   Separador: '{delimiter}'")
    lines.append("")
    lines.append("Columnas:")
    for h in headers:
        vals = col_values[h]
        dtype = _detect_type(vals) if vals else "texto"
        nulls = null_counts.get(h, 0)
        unique = len(set(vals))
        sample_vals = list(set(vals))[:5]
        preview = ", ".join(sample_vals[:4])
        if unique > 4:
            preview += f" ... (+{unique - 4} más)"
        lines.append(f"  • {h} ({dtype}) — {unique} únicos, {nulls} nulos")
        if preview:
            lines.append(f"    Ejemplos: {preview}")

    # Muestra
    if show_sample > 0 and rows:
        lines.append(f"\nMuestra (primeras {min(show_sample, len(rows))} filas):")
        header_line = " | ".join(headers)
        lines.append(f"  {header_line}")
        lines.append(f"  {'─' * len(header_line)}")
        for row in rows[:show_sample]:
            vals = " | ".join(row.get(h, "")[:30] for h in headers)
            lines.append(f"  {vals}")

    # Filtro
    if filter_col and filter_val and rows:
        filtered = [r for r in rows if filter_val.lower() in r.get(filter_col, "").lower()]
        lines.append(f"\nFiltro '{filter_col}' contains '{filter_val}': {len(filtered)} filas")
        for row in filtered[:5]:
            vals = " | ".join(row.get(h, "")[:30] for h in headers)
            lines.append(f"  {vals}")

    # Resumen numérico para columnas numéricas
    for h in headers:
        vals = col_values[h]
        nums = []
        for v in vals:
            try:
                nums.append(float(v))
            except ValueError:
                continue
        if len(nums) > 2:
            lines.append(f"\n📊 {h}: min={min(nums):.2f} max={max(nums):.2f} "
                         f"prom={sum(nums)/len(nums):.2f}")

    return "\n".join(lines)
