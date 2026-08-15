# -*- coding: utf-8 -*-
"""accessibility_overlay.py — barra flotante de accesibilidad de Nia.

Widget frameless siempre al frente con accesos rápidos: lupa, narrador,
alto contraste, teclado en pantalla, seguimiento ocular, micromovimientos
y cierre. Las acciones de Windows se delegan a windows_settings / subproceso;
el resto se gestiona vía el módulo de accesibilidad.

Se crea en el hilo principal de Qt (los tools corren en threads): por eso
las operaciones de UI se marcialan con QTimer.singleShot.
"""

import threading
from pathlib import Path

try:
    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                                 QWidget)
except Exception:  # pragma: no cover — entorno sin Qt
    QWidget = QLabel = QPushButton = None

BASE_DIR = Path(__file__).resolve().parent.parent

_overlay = None
_overlay_lock = threading.Lock()
_overlay_visible = False


def _build_overlay() -> QWidget:
    """Construye la barra flotante (debe correr en el hilo principal)."""
    w = QWidget()
    w.setWindowFlags(Qt.WindowType.FramelessWindowHint
                     | Qt.WindowType.WindowStaysOnTopHint
                     | Qt.WindowType.Tool)
    w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    w.setObjectName("accessibilityOverlay")

    title = QLabel("♿ Nia · Accesibilidad")
    title.setStyleSheet("color: #e8f4ff; font-weight: bold; padding: 4px 6px;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)

    btns = []

    def _make(text, tooltip, callback):
        b = QPushButton(text)
        b.setToolTip(tooltip)
        b.setStyleSheet(
            "QPushButton { background: rgba(0,180,255,0.15); color: #e8f4ff;"
            " border: 1px solid rgba(0,180,255,0.5); border-radius: 8px;"
            " padding: 6px 10px; font-size: 12px; }"
            "QPushButton:hover { background: rgba(0,180,255,0.35); }")
        b.clicked.connect(callback)
        btns.append(b)
        return b

    status = QLabel("Listo")
    status.setStyleSheet("color: #9fd8ff; font-size: 10px; padding: 0 6px;")
    status.setAlignment(Qt.AlignmentFlag.AlignCenter)

    def _start_eye():
        from actions.accessibility import eye_tracking
        status.setText(eye_tracking({"action": "start"})[:40])

    def _stop_eye():
        from actions.accessibility import eye_tracking
        status.setText(eye_tracking({"action": "stop"})[:40])

    def _toggle_contrast():
        from actions.accessibility import _load_config, _save_config
        cfg = _load_config()
        cfg["high_contrast_mode"] = not cfg.get("high_contrast_mode", False)
        _save_config(cfg)
        status.setText("Alto contraste: " + ("ON" if cfg["high_contrast_mode"] else "OFF"))

    def _windows_setting(kind: str):
        try:
            import subprocess
            maps = {
                "magnifier": "ms-settings:easeofaccess-magnifier",
                "narrator": "ms-settings:easeofaccess-narrator",
                "osk": "ms-settings:easeofaccess-keyboard",
            }
            uri = maps.get(kind)
            if uri:
                subprocess.Popen(["cmd", "/c", f"start {uri}"])
                status.setText(f"Abriendo ajustes: {kind}")
            else:
                status.setText(f"No configurado: {kind}")
        except Exception as e:
            status.setText(f"Error: {str(e)[:40]}")

    row1 = QHBoxLayout()
    row1.addWidget(_make("🔍 Lupa", "Abrir configuración de la lupa",
                         lambda: _windows_setting("magnifier")))
    row1.addWidget(_make("🗣️ Narrador", "Abrir configuración del narrador",
                         lambda: _windows_setting("narrator")))
    row1.addWidget(_make("🌓 Contraste", "Alternar alto contraste", _toggle_contrast))
    row1.addWidget(_make("⌨️ Teclado", "Teclado en pantalla",
                         lambda: _windows_setting("osk")))

    def _close():
        w.hide()
        global _overlay_visible
        _overlay_visible = False

    row2 = QHBoxLayout()
    row2.addWidget(_make("👀 Ojos ON", "Iniciar seguimiento ocular", _start_eye))
    row2.addWidget(_make("👀 Ojos OFF", "Detener seguimiento ocular", _stop_eye))
    row2.addWidget(_make("✖", "Cerrar barra", _close))
    row2.addWidget(status)

    layout = QVBoxLayout()
    layout.setContentsMargins(8, 6, 8, 6)
    layout.addWidget(title)
    layout.addLayout(row1)
    layout.addLayout(row2)
    w.setLayout(layout)
    w.adjustSize()
    w.setStyleSheet(
        "QWidget#accessibilityOverlay { background: rgba(10,14,26,0.92);"
        " border: 1px solid rgba(0,180,255,0.6); border-radius: 12px; }")
    return w


def _ensure_overlay():
    """Crea la barra si no existe (debe correr en el hilo principal)."""
    global _overlay, _overlay_visible
    if _overlay is None:
        _overlay = _build_overlay()
    _overlay.move(_overlay.screen().availableGeometry().center() -
                  _overlay.rect().center())
    return _overlay


def _run_in_main(fn) -> None:
    """Marca fn para ejecutarse en el hilo principal de Qt."""
    if QTimer is None:
        return
    try:
        QTimer.singleShot(0, fn)
    except Exception:
        pass


def accessibility_overlay(parameters: dict, player=None) -> str:
    """Muestra, oculta o alterna la barra flotante de accesibilidad."""
    action = str(parameters.get("action", "toggle")).lower()
    global _overlay_visible

    if action == "status":
        return ("visible" if _overlay_visible else "oculta")

    if action == "show":
        _run_in_main(_ensure_and_show)
        return "♿ Barra de accesibilidad mostrada."
    if action == "hide":
        _run_in_main(_ensure_and_hide)
        return "♿ Barra de accesibilidad cerrada."
    if action == "toggle":
        _run_in_main(_ensure_toggle)
        return "♿ Barra de accesibilidad alternada."

    return "Acción inválida. Usá show, hide, toggle o status."


def _ensure_and_show():
    global _overlay_visible
    if QWidget is None:
        return
    _ensure_overlay()
    _overlay.show()
    _overlay.raise_()
    _overlay_visible = True


def _ensure_and_hide():
    global _overlay_visible
    if _overlay is not None:
        _overlay.hide()
    _overlay_visible = False


def _ensure_toggle():
    if _overlay_visible:
        _ensure_and_hide()
    else:
        _ensure_and_show()
