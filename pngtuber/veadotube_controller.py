"""veadotube_controller.py — Controla Veadotube Mini por WebSocket desde Nia.

Protocolo (docs: https://veado.tube/docs/tech/api/):
  - Servidor WebSocket, cliente debe pasar ?n=<nombre>
  - Mensajes con prefijo de canal:  nodes: {...}
  - nodes boolean "mini"       → push-to-talk (activa/desactiva el mic)
  - nodes stateEvents "mini"    → estado del avatar (set/push/pop/toggle)

Uso:
    from pngtuber.veadotube_controller import VeadotubeController
    v = VeadotubeController()
    v.start()
    v.set_ptt(True)          # Nia hablando → boca se mueve
    v.set_ptt(False)         # Nia callada → boca cerrada
    v.set_state("Normal")    # cambiar expresión

Todos los métodos son seguros: nunca lanzan excepciones hacia Nia.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path

_INSTANCE_DIR = Path.home() / ".veadotube" / "instances"
_DEFAULT_PORT = 2424
_CONN_NAME = "Nia"


def _find_server() -> str | None:
    """Auto-detecta la dirección del servidor de Veadotube desde ~/.veadotube/instances/."""
    if not _INSTANCE_DIR.is_dir():
        return None
    now = time.time()
    best: str | None = None
    best_ts = 0.0
    for f in _INSTANCE_DIR.iterdir():
        if not f.is_file():
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ts = data.get("time", 0.0)
            if now - ts > 10:
                continue
            server = data.get("server")
            if server and ts > best_ts:
                best, best_ts = server, ts
        except Exception:
            continue
    return best


class VeadotubeController:
    """Cliente WebSocket para Veadotube Mini que corre en su propio hilo."""

    def __init__(self, port: int | None = None, name: str = _CONN_NAME):
        self.port = port
        self.name = name
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None
        self._thread: threading.Thread | None = None
        self._stopping = False
        self._connected = False
        self._states: list[str] = []
        self._last_port_error = 0.0

    # ── ciclo de vida ────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stopping = False
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception:
            pass

    async def _main(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        endpoint = self._endpoint()

        while not self._stopping:
            try:
                async with await _connect(endpoint + f"?n={self.name}") as ws:
                    self._connected = True
                    await self._send(ws, "stateEvents", "mini", {"event": "list"})
                    while not self._stopping:
                        cmd = await self._next_command()
                        if cmd is not None:
                            try:
                                await self._dispatch(ws, cmd)
                            except Exception:
                                await self._send(ws, "stateEvents", "mini", {"event": "list"})
                        try:
                            raw = await asyncio.wait_for(ws.recv(), timeout=0.2)
                            self._handle_message(raw)
                        except asyncio.TimeoutError:
                            continue
                        except Exception:
                            break
            except Exception:
                pass
            finally:
                self._connected = False
                endpoint = self._endpoint()
            await asyncio.sleep(1.0)

    async def _next_command(self):
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=0.05)
        except asyncio.TimeoutError:
            return None

    def _handle_message(self, raw) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        text = str(raw)
        if not text.startswith("nodes:"):
            return
        try:
            data = json.loads(text[len("nodes:"):].strip())
        except Exception:
            return
        if data.get("event") != "payload":
            return
        payload = data.get("payload") or {}
        if data.get("type") == "stateEvents" and payload.get("event") == "list":
            self._states = [s.get("name") or s.get("id", "") for s in payload.get("states", [])]

    def _endpoint(self) -> str:
        server = _find_server()
        if server:
            return "ws://" + server
        host = "127.0.0.1"
        port = self.port or _DEFAULT_PORT
        return f"ws://{host}:{port}"

    # ── API pública (segura, nunca lanza) ────────────────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    def list_states(self) -> list[str]:
        return list(self._states)

    def set_ptt(self, on: bool) -> None:
        self._submit("boolean", "mini", {"event": "set", "value": bool(on)})

    def set_state(self, state: str) -> None:
        sid = self._resolve(state)
        if sid:
            self._submit("stateEvents", "mini", {"event": "set", "state": sid})

    def push_state(self, state: str) -> None:
        sid = self._resolve(state)
        if sid:
            self._submit("stateEvents", "mini", {"event": "push", "state": sid})

    def pop_state(self, state: str) -> None:
        sid = self._resolve(state)
        if sid:
            self._submit("stateEvents", "mini", {"event": "pop", "state": sid})

    def toggle_state(self, state: str) -> None:
        sid = self._resolve(state)
        if sid:
            self._submit("stateEvents", "mini", {"event": "toggle", "state": sid})

    # ── internals ────────────────────────────────────────────────────────────

    def _submit(self, ctype: str, cid: str, payload: dict) -> None:
        if not self._queue or not self._loop or self._stopping:
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (ctype, cid, payload))
        except Exception:
            pass

    def _resolve(self, state: str) -> str | None:
        state = state.strip()
        if not state:
            return None
        if state in self._states:
            return state
        for s in self._states:
            if s.lower() == state.lower():
                return s
        if state.startswith("#") or state in self._states:
            return state
        return state if not self._states else None

    async def _dispatch(self, ws, cmd) -> None:
        ctype, cid, payload = cmd
        await self._send(ws, ctype, cid, payload)

    async def _send(self, ws, ctype: str, cid: str, payload: dict) -> None:
        msg = json.dumps({"event": "payload", "type": ctype, "id": cid, "payload": payload})
        await ws.send("nodes: " + msg)


async def _connect(uri: str):
    from websockets.asyncio.client import connect
    return await connect(uri)
