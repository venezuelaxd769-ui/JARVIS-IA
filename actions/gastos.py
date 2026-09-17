# -*- coding: utf-8 -*-
"""gastos.py — Presupuesto y gastos personales por voz (100% local).

Nia registra gastos hablados y responde resúmenes: cuánto gasté hoy/esta
semana/este mes, por categoría, y cuánto va del presupuesto. Todo queda en
memory/gastos.json y memory/presupuesto.json (sin cuentas ni nube).
"""
import json
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
GASTOS_FILE = BASE_DIR / "memory" / "gastos.json"
_PRES_FILE = BASE_DIR / "memory" / "presupuesto.json"

_CATEGORIAS_KEYWORDS = {
    "super": ["super", "mercado", "compras", "pan", "leche", "verduras",
              "fruta", "arroz", "fideos", "carne", "almacen", "dia", "changomas"],
    "comida": ["restaurant", "restaurante", "comida", "delivery", "rappi",
               "pedidosya", "pizza", "hamburguesa", "general", "kiosco"],
    "transporte": ["taxi", "uber", "cabify", "colectivo", "subte", "bondi",
                   "nafta", "combustible", "peaje", "estacionar"],
    "casa": ["alquiler", "expensas", "luz", "agua", "gas", "internet", "wifi",
             "cable", "supermercado", "hogar", "mueble"],
    "servicios": ["luz", "agua", "gas", "internet", "wifi", "celular", "movil",
                  "telefono", "netflix", "spotify", "suscripcion", "streaming"],
    "salud": ["farmacia", "medico", "medicina", "dentista", "hospital",
              "analisis", "therapy", "terapia"],
    "ocio": ["cine", "salida", "bar", "juego", "diversion", "regalo",
             "recreacion", "vino", "cerveza"],
    "educacion": ["curso", "libro", "facultad", "universidad", "online",
                  "correccion", "capacitacion"],
    "otros": [],
}

_DEFAULT_CATEGORIA = "otros"
_CATS = list(_CATEGORIAS_KEYWORDS.keys())


def _load(path, default):
    try:
        if path.exists():
            return json.loads(path.read_text("utf-8"))
    except Exception:
        pass
    return default


def _save(path, data):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _gastos():
    return _load(GASTOS_FILE, {"transacciones": []})


def _pres():
    return _load(_PRES_FILE, {"global": None, "por_categoria": {}})


def _auto_categoria(concepto):
    tok = (concepto or "").lower()
    for cat, keys in _CATEGORIAS_KEYWORDS.items():
        if any(k in tok for k in keys):
            return cat
    return _DEFAULT_CATEGORIA


def _parse_monto(texto):
    t = str(texto or "").replace(",", ".").strip()
    m = re.search(r"(\d+(?:\.\d+)?)", t)
    if not m:
        return None
    return round(float(m.group(1)), 2)


def _fmt(monto):
    return f"${monto:,.0f}".replace(",", ".")


def _periodo_filtro(trans, periodo):
    from datetime import timedelta
    hoy = datetime.now().date()
    if periodo in ("hoy", "dia", "today"):
        return [t for t in trans if t["fecha"] == hoy.isoformat()]
    if periodo in ("semana", "week", "7"):
        inicio = hoy - timedelta(days=hoy.weekday())
        return [t for t in trans if t["fecha"] >= str(inicio)]
    if periodo in ("mes", "month", "meses"):
        return [t for t in trans if t["fecha"].startswith(f"{hoy.year}-{hoy.month:02d}")] if True else trans
    return trans


def _registrar(params):
    monto = _parse_monto(params.get("monto", ""))
    if monto is None or monto <= 0:
        return "Decime un monto válido para registrar el gasto."
    concepto = str(params.get("concepto", "")).strip()
    cat = str(params.get("categoria", "")).strip().lower()
    if cat and cat not in _CATS:
        for c in _CATS:
            if c in cat:
                cat = c
                break
        if cat not in _CATS:
            cat = _auto_categoria(f"{cat} {concepto}" if concepto else cat)
    if not cat:
        cat = _auto_categoria(concepto)
    data = _gastos()
    tx = {
        "id": int(datetime.now().timestamp() * 1000),
        "fecha": datetime.now().strftime("%Y-%m-%d"),
        "hora": datetime.now().strftime("%H:%M"),
        "monto": monto,
        "categoria": cat,
        "concepto": concepto or cat,
    }
    data["transacciones"].append(tx)
    data["transacciones"] = data["transacciones"][-800:]
    _save(GASTOS_FILE, data)
    return (f"Anoté {_fmt(monto)} en {cat}"
            + (f" ({concepto})" if concepto else "")
            + ". ¿Algo más?")


def _resumen(params):
    periodo = str(params.get("periodo", "mes")).strip().lower()
    data = _gastos()
    filt = _periodo_filtro(data["transacciones"], periodo)
    if not filt:
        n = {"hoy": "hoy", "semana": "en esta semana", "mes": "en este mes", "todos": "registrado"} \
            .get(periodo, "en el período")
        return f"No hay gastos {n} todavía."
    total = sum(t["monto"] for t in filt)
    por_cat = {}
    for t in filt:
        por_cat[t["categoria"]] = por_cat.get(t["categoria"], 0) + t["monto"]
    etiqueta = {"hoy": "hoy", "semana": "en la semana", "mes": "en el mes",
                "todos": "en total"}.get(periodo, "en el período")
    lineas = [f"📊 Gastos {etiqueta}: {_fmt(total)}"]
    pres = _pres()
    if pres.get("global"):
        usado = int(total / pres["global"] * 100)
        lineas.append(
            f"   De tu presupuesto mensual {_fmt(pres['global'])}: {usado}% usado."
        )
    for cat, monto in sorted(por_cat.items(), key=lambda x: -x[1]):
        extra = ""
        if pres.get("por_categoria", {}).get(cat):
            lim = pres["por_categoria"][cat]
            extra = f" (de {_fmt(lim)})"
        lineas.append(f"   • {cat}: {_fmt(monto)}{extra}")
    lineas.append("   Últimas:")
    for t in filt[-5:]:
        lineas.append(
            f"     {t['fecha'][5:]} {t['hora']} · {_fmt(t['monto'])} · {t['categoria']} · {t.get('concepto', '')[:40]}"
        )
    return "\n".join(lineas)


def _presupuesto(params):
    monto = _parse_monto(params.get("monto", ""))
    cat = str(params.get("categoria", "")).strip().lower() or None
    pres = _pres()
    if monto is None:
        partes = []
        if pres.get("global"):
            partes.append(f"Presupuesto mensual global: {_fmt(pres['global'])}")
        if pres.get("por_categoria"):
            partes.append(
                "Por categoría: "
                + ", ".join(f"{c} {_fmt(m)}" for c, m in pres["por_categoria"].items())
            )
        if not partes:
            return "Todavía no definiste presupuesto. Decime: 'presupuesto 500000' o 'presupuesto 80000 para super'."
        return "\n".join(partes)
    if cat:
        pres["por_categoria"][cat] = monto
    else:
        pres["global"] = monto
    _save(_PRES_FILE, pres)
    return (f"Presupuesto {cat or 'mensual'} fijado en {_fmt(monto)}."
            " Lo tengo en cuenta para el resumen.")


def _borrar(params):
    ref = str(params.get("id", "")).strip().lower()
    data = _gastos()
    if ref in ("ultimo", "last", "el ultimo"):
        if data["transacciones"]:
            t = data["transacciones"].pop()
            _save(GASTOS_FILE, data)
            return f"Borrado {_fmt(t['monto'])} · {t['categoria']} · {t.get('concepto', '')[:40]}. Listo."
        return "No hay gastos para borrar."
    if ref:
        try:
            fid = int(ref)
        except ValueError:
            return "Para borrar decime: 'borrá el último' o el número de id."
        n0 = len(data["transacciones"])
        data["transacciones"] = [t for t in data["transacciones"] if t["id"] != fid]
        if len(data["transacciones"]) == n0:
            return f"No encontré el gasto con id {fid}."
        _save(GASTOS_FILE, data)
        return f"Gasto {fid} borrado."
    return "Decime qué borrar: 'borrá el último' o el número de id."


def gastos(parameters: dict, player=None, speak=None) -> str:
    """Presupuesto personal: registrar gastos, resumirlos, fijar presupuesto
    y borrar registros. Todo local, sin cuentas."""
    action = str(parameters.get("action", "resumen")).strip().lower()
    if player:
        player.write_log(f"💰 gastos: {action}")
    if action in ("registrar", "add", "agregar", "anotar", "nuevo", "anotá"):
        return _registrar(parameters)
    if action in ("resumen", "revisar", "ver", "status", "estado", "cuantos"):
        return _resumen(parameters)
    if action in ("presupuesto", "budget", "limite"):
        return _presupuesto(parameters)
    if action in ("borrar", "delete", "remove"):
        return _borrar(parameters)
    return ("Uso: action='registrar' (monto, concepto, categoria), "
            "'resumen' (periodo: hoy/semana/mes), 'presupuesto' (monto, categoria), "
            "o 'borrar' (id / último).")