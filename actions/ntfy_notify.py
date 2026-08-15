# -*- coding: utf-8 -*-
"""ntfy_notify.py — envía notificaciones push al celular vía ntfy.sh.

Config en config/api_keys.json:
    "ntfy_topic":  tema (default "nia-notif")
    "ntfy_server": servidor (default "https://ntfy.sh")
    "ntfy_token":  token si el tema tiene auth
"""

import json
from pathlib import Path

import httpx

BASE_DIR = Path(__file__).resolve().parent.parent
API_FILE = BASE_DIR / "config" / "api_keys.json"


def _config() -> dict:
    try:
        return json.loads(API_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ntfy_notify(parameters: dict, player=None) -> str:
    cfg = _config()
    topic = cfg.get("ntfy_topic", "nia-notif")
    server = cfg.get("ntfy_server", "https://ntfy.sh").rstrip("/")
    token = cfg.get("ntfy_token", "")

    message = str(parameters.get("message", "")).strip()
    if not message:
        return "Error: falta el mensaje."

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    title = str(parameters.get("title") or "Nia").strip()
    if title:
        headers["Title"] = title
    priority = int(parameters.get("priority") or 3)
    if priority in range(1, 6):
        headers["Priority"] = str(priority)
    tags = str(parameters.get("tags") or "").strip()
    if tags:
        headers["Tags"] = tags

    try:
        r = httpx.post(f"{server}/{topic}", content=message,
                       headers=headers, timeout=30)
        r.raise_for_status()
        return "Notificación enviada a tu teléfono."
    except Exception as e:
        return f"Error enviando la notificación: {e}"
