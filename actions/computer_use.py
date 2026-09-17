"""computer_use — el "cuerpo virtual" de Nia.

Mueve físicamente el cursor con trayectoria humana (aceleración ease-in-out y un
arco perpendicular, como movería el mouse una persona), hace clic, scroll, teclea
y captura la pantalla dentro de un sandbox aislado.

Seguridad (regla del canal: el límite va en la AUTONOMÍA, no en el conocimiento):
- Todo lo que Nia pueda guardar y los archivos a los que escriba quedan confinados
  a C:\\Users\\<usuario>\\NiaSandbox.
- Teclear texto que parezca un comando destructivo exige confirm="SÍ autorizo".
- Non-ASCII se pega vía portapapeles (pyperclip si está disponible); si no, se
  translitera a ASCII antes de escribir.
"""

import math
import os
import time
from pathlib import Path

from sandbox import SANDBOX, CONFIRM_PHRASE, confirm_granted

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import mss
except Exception:
    mss = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    from PIL import Image
except Exception:
    Image = None

SANDBOX = Path.home() / "NiaSandbox"
_CAPTURES_DIR = SANDBOX / "captures"
_MAX_TYPE_LEN = 400
_RISKY_TOKENS = (
    "del ", "rd /s", "remove-item", "rm -rf", "rm -r", "format ", "diskpart",
    "shutdown", "--force", "format.c:", "> nul", "> nul", "fdisk",
)


def trajectory(x0: float, y0: float, x1: float, y1: float, n: int = None):
    """Lista de (x, y) con ease-in-out y leve arco perpendicular (movimiento humano).

    n escala con la distancia: más puntos en movimientos largos, pocos en cortos.
    """
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 1:
        return [(x1, y1)]
    if n is None:
        n = max(6, min(60, int(math.sqrt(dist) * 2.5)))
    px, py = -dy / dist, dx / dist      # vector perpendicular (para el arco)
    arc = dist * 0.06                   # curvatura proporcional a la distancia
    pts = []
    for i in range(1, n + 1):
        t = i / n
        ease = t * t * (3 - 2 * t)      # smoothstep: acelerar-frenar
        lift = math.sin(math.pi * t) * arc
        pts.append((x0 + dx * ease + px * lift, y0 + dy * ease + py * lift))
    pts.append((x1, y1))
    return pts


def _clamp(x, y):
    if pyautogui is None:
        return x, y
    w, h = pyautogui.size()
    return max(0, min(w - 1, int(x))), max(0, min(h - 1, int(y)))


def smooth_move(x: int, y: int, duration: float = 0.35):
    """Mueve el cursor siguiendo la trayectoria. Devuelve None si fue un éxito."""
    if pyautogui is None:
        return "pyautogui no disponible"
    if duration <= 0:
        pyautogui.moveTo(x, y)
        return None
    x0, y0 = pyautogui.position()
    pts = trajectory(x0, y0, x, y)
    delay = max(0.004, duration / max(1, len(pts)))
    for px, py_ in pts:
        pyautogui.moveTo(px, py_, _pause=False)
        time.sleep(delay)
    return None


def _type_text(text: str):
    """Escribe texto soportando caracteres no-ASCII vía portapapeles."""
    if _needs_confirmation(text) and not text.upper().startswith(CONFIRM_PHRASE):
        return None  # manejado por el caller
    if pyperclip is not None:
        try:
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            return None
        except Exception:
            pass
    pyautogui.typewrite(text, interval=0.008)
    return None


def _needs_confirmation(text: str) -> bool:
    low = text.lower()
    return any(tok in low for tok in _RISKY_TOKENS)


def _log(player, msg: str):
    try:
        if player is not None and hasattr(player, "write_log"):
            player.write_log(msg)
    except Exception:
        pass


def computer_use(parameters: dict, player=None, speak=None) -> str:
    if pyautogui is None:
        return "El módulo de control físico no está disponible (no se pudo importar pyautogui)."

    action = (parameters or {}).get("action", "")
    confirm = (parameters or {}).get("confirm", "")
    granted = confirm_granted(parameters)

    try:
        if action == "move":
            x, y = _clamp(int(parameters.get("x", 0)), int(parameters.get("y", 0)))
            _log(player, "SYS: computer_use → moviendo el cursor")
            err = smooth_move(x, y)
            return "Cursor movido." if err is None else err

        if action == "click":
            x = int(parameters.get("x", 0))
            y = int(parameters.get("y", 0))
            button = parameters.get("button", "left")
            clicks = int(parameters.get("clicks", 1))
            if x or y:
                x, y = _clamp(x, y)
                err = smooth_move(x, y)
                if err:
                    return err
            pyautogui.click(button=button if button in ("left", "right", "middle") else "left", clicks=clicks)
            return f"Clic {button} en ({x}, {y})."

        if action == "scroll":
            amount = int(parameters.get("amount", 0))
            if amount == 0:
                return "Indicá 'amount' (positivo=arriba, negativo=abajo)."
            pyautogui.scroll(amount)
            return f"Scroll {'arriba' if amount > 0 else 'abajo'} x{abs(amount)}."

        if action == "type":
            text = str(parameters.get("text", ""))
            if not text:
                return "No hay texto para escribir."
            if len(text) > _MAX_TYPE_LEN:
                return f"Texto demasiado largo ({len(text)} > {_MAX_TYPE_LEN} chars)."
            if _needs_confirmation(text) and not granted:
                return (
                    "No escribí eso: el texto parece un comando que podría borrar o dañar archivos. "
                    f"Si realmente querés, repetí la acción con confirm='{CONFIRM_PHRASE}'."
                )
            err = _type_text(text)
            return "Texto escrito." if err is None else err

        if action == "screenshot":
            if mss is None or Image is None:
                return "Módulo de captura (mss/PIL) no disponible."
            region = str(parameters.get("region", "") or "")
            try:
                _CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                out = _CAPTURES_DIR / f"capture_{stamp}.png"
                with mss.mss() as sct:
                    if region:
                        left, top, w, h = (int(v) for v in region.replace(" ", "").split(","))
                    else:
                        mon = sct.monitors[1]
                        left, top, w, h = mon["left"], mon["top"], mon["width"], mon["height"]
                    shot = sct.grab({"left": left, "top": top, "width": w, "height": h})
                    Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(out)
                return f"Captura guardada en {out}"
            except Exception as e:
                return f"No se pudo capturar la pantalla: {e}"

        if action == "sandbox":
            SANDBOX.mkdir(parents=True, exist_ok=True)
            _CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
            files = sorted(_CAPTURES_DIR.glob("*.png"), reverse=True)[:5]
            return (
                f"Sandbox de trabajo: {SANDBOX}. Últimas capturas: "
                + (", ".join(f.name for f in files) or "ninguna todavía.")
            )

        return f"Acción de computer_use desconocida: {action}"

    except Exception as e:
        return f"Error en computer_use/{action}: {e}"