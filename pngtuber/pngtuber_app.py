# -*- coding: utf-8 -*-
"""pngtuber_app.py — Modelo PNGtuber de Nia en la esquina inferior derecha.

Ventana sin bordes, transparente, siempre encima. Animaciones con los
frames VT1-VT4:
  VT1 = boca cerrada (neutral / reposo)
  VT2 = boca abierta (hablando)
  VT3 = parpadeo / ojos cerrados
  VT4 = expresión alternativa

Servidor TCP local 127.0.0.1:8791 (protocolo: comandos separados por \n):
  show        → mostrar el modelo (Nia minimizada a bandeja)
  hide        → ocultarlo (ventana de Nia restaurada)
  talk_start  → animar la boca
  talk_end    → volver al reposo
  emote       → mostrar VT4 unos segundos
  quit        → cerrar la app
  ping        → respuesta "pong"
  reopen      → el usuario hizo clic en el modelo (para Nia: restaurar ventana)

Uso:
  python pngtuber_app.py          # arranca oculto (lo muestra Nia)
  python pngtuber_app.py --visible  # arranca visible (prueba manual)
"""
import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QRectF, pyqtSignal
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8791
DISPLAY_SIZE = 260        # px de ancho del modelo en pantalla
MARGIN = 14               # separación del borde de pantalla
FRAME_TALK_MS = 170       # cadencia de la boca al hablar
BLINK_MS = 160            # duración del parpadeo
TICK_MS = 120             # refresco de animaciones (parpadeo)

# Sincronía de la boca con la energía real del audio que Nia reproduce.
# Nia envía "vol:<rms>" (0..1) continuamente mientras habla; la boca se abre
# con la voz y se cierra en las pausas, siguiendo el ritmo real.
VOL_TIMEOUT = 0.7         # s sin mensajes vol → caer al modo mecánico de respaldo
VOL_PEAK_DECAY = 0.96     # decaimiento del pico de referencia por tick
VOL_OPEN_RATIO = 0.35     # abrir si energía >= 35% del pico reciente
VOL_CLOSE_RATIO = 0.12    # cerrar si energía <= 12% del pico reciente

FILES = {
    "neutral": "VT1.png",
    "talking": "VT2.png",
    "blink": "VT3.png",
    "emote": "VT4.png",
}

import shutil
_HYPRCTL = shutil.which("hyprctl")


def _hypr_dispatch(args):
    """Envía un `hyprctl dispatch` sin esperar respuesta. Robustecido para
    entornos sin WAYLAND_DISPLAY (p. ej. user units de systemd)."""
    if not _HYPRCTL:
        return
    try:
        subprocess.Popen(
            [_HYPRCTL, "dispatch"] + args,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def _active_workspace_id():
    """Id del workspace activo (int) o None. Vía `hyprctl activeworkspace -j`."""
    if not _HYPRCTL:
        return None
    try:
        out = subprocess.run(
            [_HYPRCTL, "activeworkspace", "-j"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        return json.loads(out).get("id")
    except Exception:
        return None


def _hypr_socket2_path():
    """Ruta del socket de eventos de Hyprland (.socket2.sock)."""
    try:
        out = subprocess.run(
            [_HYPRCTL, "-j", "instances"],
            capture_output=True, text=True, timeout=5,
        ).stdout
        instances = json.loads(out)
        if not instances:
            return None
        sig = instances[0]["instance"]
        xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        return f"{xdg}/hypr/{sig}/.socket2.sock"
    except Exception:
        return None


def _hypr_follow_thread(widget: "AvatarWidget", q: queue.Queue):
    """Se suscribe a `workspacev2` y encola el workspace activo cada vez que
    cambia, para que el modelo te siga al escritorio donde vayas."""
    path = _hypr_socket2_path()
    if not path:
        return
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(path)
        sock.sendall(b"workspacev2\n")
        sock.settimeout(1.0)
    except Exception:
        try:
            sock.close()
        except Exception:
            pass
        return
    try:
        while True:
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except Exception:
                break
            if not data:
                break
            for line in data.decode("utf-8", "replace").splitlines():
                if line.startswith("workspacev2>>"):
                    ws = line.split(">>", 1)[1].split(",", 1)[0].strip()
                    if ws.isdigit():
                        q.put(f"__ws:{ws}")
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass


class AvatarWidget(QWidget):
    def __init__(self, start_visible: bool):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setWindowTitle("Nia PNGtuber")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(DISPLAY_SIZE, DISPLAY_SIZE)

        self.frames = {}
        for key, fname in FILES.items():
            pix = QPixmap(str(BASE_DIR / fname))
            if not pix.isNull():
                self.frames[key] = pix.scaled(
                    DISPLAY_SIZE, DISPLAY_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

        self.mode = "idle"
        self.talk_tick = 0
        self.mouth_open = False
        self.next_blink = time.time() + 2.5
        self.blink_until = 0.0
        self.emote_until = 0.0
        self.visible_default = start_visible
        self._energy = 0.0        # último RMS recibido de Nia (0..1)
        self._last_vol = 0.0      # marca de tiempo del último vol: recibido
        self._peak = 0.001        # pico de referencia adaptativo (histéresis)
        self._last_raise = 0.0    # marca de tiempo del último raise_ (primer plano)

        # posicionar abajo a la derecha
        self._place()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(TICK_MS)

        if not start_visible:
            self.hide()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_workspace()
        self._place(3)

    # ── geometría ─────────────────────────────────────────────────────
    def _set_pos(self, x: int, y: int):
        """Posiciona la ventana. En Wayland el cliente no puede auto-colocarse,
        así que además se usa hyprctl (el compositor decide la posición real)."""
        self.move(x, y)
        _hypr_dispatch(["movewindowpixel", f"exact {x} {y}, title:Nia PNGtuber"])

    def _move_to_workspace(self, ws_id):
        """Mueve el modelo al workspace dado (lo sigue cuando cambias de escritorio).
        La posición en pantalla se conserva, así que no hay que reposicionar."""
        if not self.isVisible():
            return
        if _HYPRCTL:
            _hypr_dispatch([f"movetoworkspacesilent {ws_id}, title:Nia PNGtuber"])

    def _sync_workspace(self):
        """Al mostrarse, garantiza que el modelo aparezca en el workspace activo
        (puede haberse ocultado mientras estaba en otro escritorio)."""
        ws = _active_workspace_id()
        if ws is not None and _HYPRCTL:
            _hypr_dispatch([f"movetoworkspacesilent {ws}, title:Nia PNGtuber"])

    def _place(self, tries: int = 3):
        screen = self.screen() or QApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        if geo is not None:
            x = int(geo.right() - self.width() - MARGIN)
            y = int(geo.bottom() - self.height() - MARGIN)
            x = max(int(geo.left()), x)
            y = max(int(geo.top()), y)
        else:
            x, y = 120, 120
        self._set_pos(x, y)
        # reintenta: Hyprland puede no tener aún el título de la ventana recién mapeada
        if tries > 0:
            QTimer.singleShot(600, lambda: self._place(tries - 1))

    def _on_tick(self):
        if not self.isVisible():
            return
        now = time.time()
        if now - self._last_raise >= 3.0:
            # Mantener el modelo en primer plano (WindowStaysOnTopHint es
            # fuerte, pero con raise_ periódico se garantiza que ninguna app
            # maximizada o la barra de tareas lo cubra).
            self.raise_()
            self._last_raise = now

        if self.mode == "talking":
            self.talk_tick += 1
            if now - self._last_vol <= VOL_TIMEOUT:
                # Seguimiento por energía real: el pico se adapta al volumen
                # de la voz para que la boca siga el ritmo (abre con voz,
                # cierra en pausas) sin importar cuán fuerte hable Nia.
                e = self._energy
                self._peak = max(e, self._peak * VOL_PEAK_DECAY)
                if e >= VOL_OPEN_RATIO * self._peak:
                    self.mouth_open = True
                elif e <= VOL_CLOSE_RATIO * self._peak:
                    self.mouth_open = False
                # entre ambos umbrales se conserva el estado (histéresis)
            elif self.talk_tick % 2 == 0 and now >= self.blink_until:
                # respaldo: sin stream de volumen → toggle mecánico
                self.mouth_open = not self.mouth_open

        self.setPixmap(self._current_frame(now))

    def _current_frame(self, now):
        if self.mode == "emote":
            if now < self.emote_until:
                return self.frames.get("emote", self.frames.get("neutral"))
            self.mode = "idle"
        if self.mode == "talking":
            if now < self.blink_until:
                return self.frames.get("blink")
            return self.frames.get("talking" if self.mouth_open else "neutral")
        # idle
        if now >= self.next_blink:
            self.blink_until = now + BLINK_MS / 1000.0
            self.next_blink = now + (2.5 + __import__("random").random() * 4.5)
        if now < self.blink_until:
            return self.frames.get("blink")
        return self.frames.get("neutral")

    # ── render ────────────────────────────────────────────────────────
    def setPixmap(self, pixmap):
        if not pixmap or pixmap.isNull():
            return
        self._current_pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pm = getattr(self, "_current_pixmap", None)
        if pm:
            bx = (self.width() - pm.width()) // 2
            by = (self.height() - pm.height()) // 2
            painter.drawPixmap(bx, by, pm)

    # ── comandos desde Nia ────────────────────────────────────────────
    def set_energy(self, value: float):
        """Recibe el RMS del audio que Nia está reproduciendo (0..1).
        Se llama desde el hilo del socket; solo escribe dos floats (seguro)."""
        self._energy = value
        self._last_vol = time.time()

    def handle_command(self, cmd: str):
        cmd = cmd.strip().lower()
        if cmd == "show":
            self.show()
            self.raise_()
        elif cmd == "hide":
            self.hide()
        elif cmd == "talk_start":
            # idempotente: si ya estamos hablando no reiniciamos el estado de
            # energía (Nia puede reenviarlo; no debe romper el seguimiento)
            if self.mode != "talking":
                self.mode = "talking"
                self.mouth_open = False
                self.talk_tick = 0
                self._peak = 0.001
                self._energy = 0.0
                self._last_vol = 0.0
        elif cmd == "talk_end":
            if self.mode == "talking":
                self.mode = "idle"
        elif cmd == "emote":
            self.emote_until = time.time() + 4.0
            self.mode = "emote"
        elif cmd == "ping":
            pass
        elif cmd.startswith("__ws:"):
            ws = cmd.split(":", 1)[1]
            if ws.isdigit():
                self._move_to_workspace(ws)
        elif cmd == "quit":
            QApplication.quit()

    def _broadcast_reopen(self):
        _broadcast("reopen\n")

    # ── clic / arrastre ───────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False
            event.accept()

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_pos", None) is not None and event.buttons() & Qt.MouseButton.LeftButton:
            x = event.globalPosition().toPoint().x() - self._drag_pos.x()
            y = event.globalPosition().toPoint().y() - self._drag_pos.y()
            self._set_pos(x, y)
            self._moved = True
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not getattr(self, "_moved", False):
            # clic sin arrastre → pedir a Nia que se restaure
            self._broadcast_reopen()
            self.emote_until = time.time() + 1.5
            self.mode = "emote"
        self._drag_pos = None
        event.accept()


_connections = []
_conn_lock = threading.Lock()


def _broadcast(msg: str):
    with _conn_lock:
        conns = list(_connections)
    for c in conns:
        try:
            c.sendall(msg.encode("utf-8"))
        except Exception:
            pass


def _handle_conn(widget: "AvatarWidget", q: queue.Queue, conn: socket.socket):
    with _conn_lock:
        _connections.append(conn)
    try:
        conn.settimeout(0.2)
        buf = b""
        while True:
            try:
                data = conn.recv(512)
            except socket.timeout:
                data = b""
            except Exception:
                break
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                cmd = line.decode("utf-8", "replace").strip()
                if not cmd:
                    continue
                if cmd == "ping":
                    try:
                        conn.sendall(b"pong\n")
                    except Exception:
                        pass
                elif cmd.startswith("vol:"):
                    # energía del audio en directo → la usa _on_tick (Qt)
                    try:
                        widget.set_energy(float(cmd[4:]))
                    except Exception:
                        pass
                else:
                    q.put(cmd)
    finally:
        with _conn_lock:
            if conn in _connections:
                _connections.remove(conn)
        try:
            conn.close()
        except Exception:
            pass


def _bind_server():
    """Abre el socket TCP. Devuelve el socket si el puerto quedó libre, o
    None si ya hay otra instancia escuchando (para que el proceso salga
    limpio en vez de quedarse huérfano e invisible)."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((HOST, PORT))
        srv.listen(8)
        srv.settimeout(1.0)
        return srv
    except OSError as e:
        print(f"[PNGTUBER] No pude abrir el puerto {PORT} ({e}). ¿Ya hay otra instancia?")
        return None


def _socket_server(srv: socket.socket, widget: AvatarWidget, q: queue.Queue):
    while True:
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        except Exception:
            break
        threading.Thread(target=_handle_conn, args=(widget, q, conn),
                         daemon=True, name="pngtuber-conn").start()


def main():
    start_visible = "--visible" in sys.argv
    app = QApplication(sys.argv)

    # Single-instance por puerto: si ya hay otro escuchando, salir limpio.
    # Antes este proceso seguía vivo en app.exec() sin ventana, acumulando
    # huérfanos con la boca congelada (main.py:139-140 lo daba por hecho).
    srv = _bind_server()
    if srv is None:
        print("[PNGTUBER] Abandonando: otra instancia ya está activa.")
        sys.exit(0)

    widget = AvatarWidget(start_visible)
    if start_visible:
        widget.show()

    cmd_queue = queue.Queue()
    threading.Thread(target=_socket_server, args=(srv, widget, cmd_queue),
                     daemon=True, name="pngtuber-server").start()
    threading.Thread(target=_hypr_follow_thread, args=(widget, cmd_queue),
                     daemon=True, name="pngtuber-follow").start()

    def _poll():
        try:
            while True:
                widget.handle_command(cmd_queue.get_nowait())
        except queue.Empty:
            pass

    poller = QTimer(app)
    poller.timeout.connect(_poll)
    poller.start(80)

    app.exec()


if __name__ == "__main__":
    main()
