# -*- coding: utf-8 -*-
"""
gesture_engine.py — High-fidelity webcam hand tracking and mouse gesture controller.
"""
import os
import cv2
import time
import random
import urllib.request
import numpy as np
import pyautogui
import subprocess
import shutil
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

# Configure PyAutoGUI for high performance / low latency
pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = True

# ── Linux/Wayland mouse backend ──────────────────────────────────────────
_HAS_HYPRCTL = shutil.which("hyprctl") is not None
_HAS_YDOTOOL = shutil.which("ydotool") is not None or (Path.home() / ".local/bin/ydotool").exists()

def _ydotool_bin() -> str:
    path = shutil.which("ydotool")
    if path:
        return path
    home_bin = Path.home() / ".local/bin/ydotool"
    if home_bin.exists():
        return str(home_bin)
    return "ydotool"

def _ensure_ydotoold():
    if not _HAS_YDOTOOL:
        return False
    try:
        r = subprocess.run(["ydotool", "click", "0"], capture_output=True, timeout=2)
        if r.returncode == 0:
            return True
    except Exception:
        pass
    # Start daemon as persistent session leader
    daemon = str(Path(_ydotool_bin()).parent / "ydotoold")
    if not Path(daemon).exists():
        daemon = shutil.which("ydotoold") or ""
    if daemon:
        subprocess.Popen([daemon], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True)
        # Wait up to 3s for daemon to be ready
        for _ in range(6):
            time.sleep(0.5)
            try:
                r = subprocess.run(["ydotool", "click", "0"], capture_output=True, timeout=1)
                if r.returncode == 0:
                    return True
            except Exception:
                continue
    return False

def _get_cursor_pos() -> tuple[int, int]:
    """Obtiene la posición actual del cursor."""
    if _HAS_HYPRCTL:
        try:
            r = subprocess.run(["hyprctl", "cursorpos"], capture_output=True, text=True, timeout=2)
            parts = r.stdout.strip().split(",")
            return int(parts[0]), int(parts[1])
        except:
            pass
    return pyautogui.position()

def _bezier_point(t: float, p0: tuple, p1: tuple, p2: tuple, p3: tuple) -> tuple:
    """Cubic bezier interpolation."""
    u = 1 - t
    x = u*u*u*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t*t*t*p3[0]
    y = u*u*u*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t*t*t*p3[1]
    return (x, y)

def _ease_in_out(t: float) -> float:
    """Smooth acceleration and deceleration."""
    if t < 0.5:
        return 2 * t * t
    return -1 + (4 - 2 * t) * t

def _natural_mouse_path(x: int, y: int) -> list[tuple[int, int]]:
    """Genera una trayectoria natural de mouse con curva bezier, aceleración suave y micro- vibración humana."""
    cx, cy = _get_cursor_pos()
    dx = x - cx
    dy = y - cy
    dist = (dx*dx + dy*dy) ** 0.5
    if dist < 20:
        return [(x, y)]

    steps = max(10, min(int(dist / 8), 60))

    perp_x = -dy / (dist + 1) * dist * 0.3
    perp_y = dx / (dist + 1) * dist * 0.3
    r1 = random.uniform(-dist*0.12, dist*0.12)
    r2 = random.uniform(-dist*0.12, dist*0.12)

    p0 = (cx, cy)
    p1 = (cx + dx*0.25 + perp_x + r1, cy + dy*0.25 + perp_y + r1)
    p2 = (cx + dx*0.75 + perp_x + r2, cy + dy*0.75 + perp_y + r2)
    p3 = (x, y)

    path = []
    for i in range(steps + 1):
        t = _ease_in_out(i / steps)
        point = _bezier_point(t, p0, p1, p2, p3)
        jx = random.uniform(-1.5, 1.5) if 0 < i < steps else 0
        jy = random.uniform(-1.5, 1.5) if 0 < i < steps else 0
        path.append((int(point[0] + jx), int(point[1] + jy)))
    return path

def _mouse_move_raw(px: int, py: int):
    """Move cursor to exact pixel instantly (for drag steps)."""
    if _HAS_HYPRCTL:
        subprocess.run(["hyprctl", "dispatch", "movecursor", str(px), str(py)],
                       capture_output=True, timeout=1)
    elif _HAS_YDOTOOL:
        _ensure_ydotoold()
        subprocess.run([_ydotool_bin(), "mousemove", "--absolute", "-x", str(px), "-y", str(py)],
                       capture_output=True, timeout=1)
    else:
        pyautogui.moveTo(px, py)

def _mouse_move_to(x: int, y: int):
    """Move cursor naturally like a human — bezier curve, easing, micro-jitter, human-like speed."""
    path = _natural_mouse_path(x, y)
    steps = len(path)
    if steps < 3:
        for px, py in path:
            _mouse_move_raw(px, py)
        return
    # Human-like timing proportional to distance
    duration = max(0.1, min(0.7, steps * 0.012))
    gap = duration / steps
    for px, py in path:
        _mouse_move_raw(px, py)
        if gap > 0.003:
            time.sleep(gap)

def _mouse_down(button: str = "left"):
    if _HAS_YDOTOOL:
        _ensure_ydotoold()
        btn = "0" if button == "left" else "2"
        cx, cy = _get_cursor_pos()
        if cx > 0 or cy > 0:
            subprocess.run([_ydotool_bin(), "mousemove", "--absolute",
                           "-x", str(cx // 2), "-y", str(cy // 2)],
                          capture_output=True, timeout=1)
            time.sleep(0.05)
        subprocess.run([_ydotool_bin(), "mousedown", btn], capture_output=True, timeout=2)
    else:
        pyautogui.mouseDown(button=button)

def _mouse_up(button: str = "left"):
    if _HAS_YDOTOOL:
        btn = "0" if button == "left" else "2"
        subprocess.run([_ydotool_bin(), "mouseup", btn], capture_output=True, timeout=2)
    else:
        pyautogui.mouseUp(button=button)

def _click(button: str = "left"):
    if _HAS_YDOTOOL:
        _ensure_ydotoold()
        btn = "1" if button == "left" else "3"
        # Sync ydotool's internal position at current cursor location.
        # ydotool's absolute coords are 2x physical pixels on this system.
        cx, cy = _get_cursor_pos()
        if cx > 0 or cy > 0:
            subprocess.run([_ydotool_bin(), "mousemove", "--absolute",
                           "-x", str(cx // 2), "-y", str(cy // 2)],
                          capture_output=True, timeout=1)
            time.sleep(0.05)
        r = subprocess.run([_ydotool_bin(), "click", btn], capture_output=True, timeout=2)
        if r.returncode != 0:
            # Fallback: try pyautogui
            pyautogui.click(button=button)
    else:
        pyautogui.click(button=button)

def _scroll(amount: int):
    if _HAS_YDOTOOL:
        _ensure_ydotoold()
        btn = "4" if amount < 0 else "5"
        for _ in range(abs(amount)):
            subprocess.run([_ydotool_bin(), "click", btn], capture_output=True, timeout=1)
    else:
        pyautogui.scroll(amount)

def _hscroll(amount: int):
    if _HAS_YDOTOOL:
        btn = "6" if amount > 0 else "7"
        for _ in range(abs(amount)):
            subprocess.run([_ydotool_bin(), "click", btn], capture_output=True, timeout=1)
    else:
        pyautogui.hscroll(amount)

# ── Keyboard helpers ─────────────────────────────────────────────────────
_HAS_WTYPE = shutil.which("wtype") is not None

_YDOTOOL_KEYS = {
    "enter": "28", "tab": "15", "escape": "1", "backspace": "14",
    "space": "57", "delete": "111", "up": "103", "down": "108",
    "left": "105", "right": "106", "home": "102", "end": "107",
    "pageup": "104", "pagedown": "109",
    "ctrl": "29", "alt": "56", "shift": "42", "meta": "125",
    "f1": "59","f2":"60","f3":"61","f4":"62","f5":"63","f6":"64",
    "f7":"65","f8":"66","f9":"67","f10":"68","f11":"87","f12":"88",
}

_YDOTOOL_ALPHA = {chr(97+i): str(30+i) for i in range(26)}
_YDOTOOL_KEYS.update(_YDOTOOL_ALPHA)

def _type_text(text: str):
    if _HAS_WTYPE:
        subprocess.run(["wtype", text], capture_output=True, timeout=5)
    elif _HAS_YDOTOOL:
        subprocess.run([_ydotool_bin(), "type", text], capture_output=True, timeout=10)
    else:
        pyautogui.write(text, interval=0.01)

def _key_press(key: str):
    key_lower = key.lower().strip()
    if _HAS_WTYPE:
        subprocess.run(["wtype", "-k", key_lower], capture_output=True, timeout=3)
    elif _HAS_YDOTOOL:
        kc = _YDOTOOL_KEYS.get(key_lower)
        if kc:
            subprocess.run([_ydotool_bin(), "key", kc], capture_output=True, timeout=2)
        else:
            _type_text(key)
    else:
        pyautogui.press(key_lower)

def _key_combo(keys: list[str]):
    if _HAS_WTYPE:
        wtype_keys = "+".join(k.lower() for k in keys)
        subprocess.run(["wtype", "-k", wtype_keys], capture_output=True, timeout=3)
    elif _HAS_YDOTOOL:
        kcs = [_YDOTOOL_KEYS.get(k.lower(), "") for k in keys]
        kcs = [k for k in kcs if k]
        if kcs:
            combo = "+".join(kcs)
            subprocess.run([_ydotool_bin(), "key", combo], capture_output=True, timeout=2)
    else:
        pyautogui.hotkey(*keys)


# Connection mapping for custom premium hand skeleton drawing
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # Thumb
    (0, 5), (5, 6), (6, 7), (7, 8),           # Index
    (9, 10), (10, 11), (11, 12),              # Middle
    (13, 14), (14, 15), (15, 16),             # Ring
    (0, 17), (17, 18), (18, 19), (19, 20),    # Pinky
    (5, 9), (9, 13), (13, 17),                # Palm base joints
]


class GestureTrackingThread(QThread):
    """
    Background QThread that captures webcam video frames, runs the modern MediaPipe Tasks
    HandLandmarker model in VIDEO mode, executes smoothed OS mouse movements / clicks /
    scrolls, and emits processed frames to the Qt UI.
    """
    frame_signal = pyqtSignal(QImage, str)   # (processed holographic frame, status label)
    active_signal = pyqtSignal(bool)          # active state changes

    # ──────────────────────────────────────────────────────────────────────────
    def __init__(self, camera_index=0, theme_bgr=(11, 158, 245), text_bgr=(138, 230, 253), parent=None):
        super().__init__(parent)
        self.camera_index = camera_index
        self.theme_bgr    = theme_bgr
        self.text_bgr     = text_bgr
        self._running     = False

        # Model path
        self.model_path = Path("config/hand_landmarker.task")

        # Cursor smoothing (EMA — Exponential Moving Average)
        self.prev_x, self.prev_y = 0, 0
        try:
            self.prev_x, self.prev_y = pyautogui.position()
        except Exception:
            pass
        self.smoothing = 0.25

        # Screen dimensions
        self.screen_width, self.screen_height = 1920, 1080
        try:
            self.screen_width, self.screen_height = pyautogui.size()
        except Exception:
            pass

        # Mouse Drag & Click States
        self.mouse_pressed = False
        self.last_right_click_time = 0.0
        self.last_pinch_release_time = 0.0
        self.click_sequence_coords = None
        self.pinch_start_time = 0.0

        # Scroll state
        self.prev_palm_x   = None
        self.prev_palm_y   = None
        self.last_scroll_time = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    def stop(self):
        """Safely stops the tracking thread."""
        self._running = False
        # Esperar como máximo 1000ms para evitar que cuelgue la UI principal si el controlador de la cámara se bloquea
        if not self.wait(1000):
            print("[Gesture Engine] El hilo no finalizó en 1s. Forzando terminación...")
            self.terminate()
            self.wait(500)

    # ──────────────────────────────────────────────────────────────────────────
    def _ensure_model_file(self):
        """Ensures the hand_landmarker.task file is downloaded and cached."""
        if not self.model_path.exists():
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            url = (
                "https://storage.googleapis.com/mediapipe-models/"
                "hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
            )
            print(f"[Gesture Engine] Downloading model from {url}...")
            urllib.request.urlretrieve(url, str(self.model_path.absolute()))
            print("[Gesture Engine] Model download complete.")

    # ──────────────────────────────────────────────────────────────────────────
    def run(self):
        print("[Thread] run() entered.", flush=True)
        _ensure_ydotoold()
        self._ensure_model_file()

        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        print("[Thread] mediapipe tasks imported.", flush=True)

        self._running = True

        # ── Open video capture ────────────────────────────────────────────────
        print(f"[Thread] Opening camera {self.camera_index}...", flush=True)
        cap = None
        if isinstance(self.camera_index, int):
            cap = cv2.VideoCapture(self.camera_index)
            if not cap.isOpened():
                print(
                    f"[Gesture Engine] Default backend failed, "
                    f"trying DSHOW for camera {self.camera_index}...", flush=True
                )
                cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        else:
            cap = cv2.VideoCapture(self.camera_index)

        if cap is None or not cap.isOpened():
            print(f"[Gesture Engine] Error: Could not open camera {self.camera_index}", flush=True)
            self.active_signal.emit(False)
            return

        self.active_signal.emit(True)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # ── Build HandLandmarker ──────────────────────────────────────────────
        print("[Thread] Instantiating HandLandmarker...", flush=True)
        base_options = python.BaseOptions(model_asset_path=str(self.model_path.resolve()))
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            num_hands=1,
            min_hand_detection_confidence=0.7,
            min_hand_presence_confidence=0.7,
            min_tracking_confidence=0.7,
            running_mode=vision.RunningMode.VIDEO,
        )
        detector = vision.HandLandmarker.create_from_options(options)
        print("[Thread] HandLandmarker successfully initialized.", flush=True)

        # ── Main capture loop ─────────────────────────────────────────────────
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            h, w, c = frame.shape

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image  = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            timestamp_ms = int(time.time() * 1000)
            result       = detector.detect_for_video(mp_image, timestamp_ms)

            status_text = "Buscando mano..."

            # HUD border & title
            cv2.rectangle(frame, (10, 10), (w - 10, h - 10), self.theme_bgr, 1)
            cv2.putText(
                frame, "JARVIS GESTURE PILOT", (20, 35),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.theme_bgr, 1, cv2.LINE_AA,
            )

            if result.hand_landmarks:
                for hand_landmarks in result.hand_landmarks:

                    # ── Draw holographic skeleton ─────────────────────────────
                    for conn in HAND_CONNECTIONS:
                        pt1 = hand_landmarks[conn[0]]
                        pt2 = hand_landmarks[conn[1]]
                        cv2.line(
                            frame,
                            (int(pt1.x * w), int(pt1.y * h)),
                            (int(pt2.x * w), int(pt2.y * h)),
                            self.theme_bgr, 1, cv2.LINE_AA,
                        )

                    # Joint nodes
                    for lm_id, lm in enumerate(hand_landmarks):
                        cx, cy = int(lm.x * w), int(lm.y * h)
                        if lm_id in (4, 8, 12, 16, 20):
                            cv2.circle(frame, (cx, cy), 5, self.text_bgr,   -1, cv2.LINE_AA)
                        else:
                            cv2.circle(frame, (cx, cy), 3, self.theme_bgr, -1, cv2.LINE_AA)

                    # ── Landmark references ───────────────────────────────────
                    index_tip  = hand_landmarks[8]
                    middle_tip = hand_landmarks[12]
                    ring_tip   = hand_landmarks[16]
                    pinky_tip  = hand_landmarks[20]

                    # Finger extension flags (tip Y < pip Y  →  extended)
                    index_up  = index_tip.y  < hand_landmarks[6].y
                    middle_up = middle_tip.y < hand_landmarks[10].y
                    ring_up   = ring_tip.y   < hand_landmarks[14].y
                    pinky_up  = pinky_tip.y  < hand_landmarks[18].y

                    todos_up     = index_up and middle_up and ring_up and pinky_up
                    cursor_mode  = index_up and middle_up and (not ring_up) and (not pinky_up)

                    curr_time = time.time()

                    # ── Calculate pinch distance (Thumb tip 4 to index landmarks 8, 7, 6) ────
                    thumb_tip = hand_landmarks[4]
                    d8 = ((thumb_tip.x - hand_landmarks[8].x)**2 + (thumb_tip.y - hand_landmarks[8].y)**2)**0.5
                    d7 = ((thumb_tip.x - hand_landmarks[7].x)**2 + (thumb_tip.y - hand_landmarks[7].y)**2)**0.5
                    d6 = ((thumb_tip.x - hand_landmarks[6].x)**2 + (thumb_tip.y - hand_landmarks[6].y)**2)**0.5
                    dist_thumb_index = min(d8, d7, d6)

                    curr_time = time.time()

                    # Define gesture states based on user specifications
                    # Umbral de contacto flexible (0.042) para mayor comodidad ergonómica lateral
                    is_right_click_gesture = todos_up and dist_thumb_index < 0.042
                    is_scroll_gesture = todos_up and dist_thumb_index >= 0.052
                    is_cursor_or_drag = cursor_mode or self.mouse_pressed

                    # ══════════════════════════════════════════════════════════
                    # MODO CLICK DERECHO — 4 dedos extendidos + pulgar apegado al índice
                    # ══════════════════════════════════════════════════════════
                    if is_right_click_gesture:
                        # Release left click if it was active
                        if self.mouse_pressed:
                            _mouse_up('left')
                            self.mouse_pressed = False
                            print("[Gesture Engine] Left click released before right click.")

                        # Reset scroll state
                        self.prev_palm_x = None
                        self.prev_palm_y = None

                        # Click right with cooldown
                        if curr_time - self.last_right_click_time > 0.8:
                            _click('right')
                            self.last_right_click_time = curr_time
                            status_text = "Click Derecho"
                            print("[Gesture Engine] Right click.")
                        else:
                            status_text = "Click Derecho (Cooldown)"

                    # ══════════════════════════════════════════════════════════
                    # MODO SCROLL — 4 dedos extendidos, pulgar libre (no apegado)
                    # ══════════════════════════════════════════════════════════
                    elif is_scroll_gesture:
                        # Release left click if it was active
                        if self.mouse_pressed:
                            _mouse_up('left')
                            self.mouse_pressed = False
                            print("[Gesture Engine] Left click released before scrolling.")

                        status_text = "Scroll Activo ↕↔"

                        # Centroid across all 21 landmarks
                        palm_x = float(np.mean([lm.x for lm in hand_landmarks]))
                        palm_y = float(np.mean([lm.y for lm in hand_landmarks]))

                        if self.prev_palm_x is not None and self.prev_palm_y is not None:
                            dx = palm_x - self.prev_palm_x
                            dy = palm_y - self.prev_palm_y
                            scroll_threshold = 0.018

                            if curr_time - self.last_scroll_time > 0.06:
                                if abs(dy) >= scroll_threshold or abs(dx) >= scroll_threshold:
                                    if abs(dy) >= abs(dx):
                                        # Vertical scroll
                                        if dy > 0:
                                            _scroll(-5)
                                        else:
                                            _scroll(5)
                                    else:
                                        # Horizontal scroll
                                        if dx > 0:
                                            _hscroll(5)
                                        else:
                                            _hscroll(-5)
                                    self.last_scroll_time = curr_time

                        self.prev_palm_x = palm_x
                        self.prev_palm_y = palm_y

                    # ══════════════════════════════════════════════════════════
                    # MODO CURSOR / ARRASTRE — índice y medio extendidos (o arrastre en curso)
                    # ══════════════════════════════════════════════════════════
                    elif is_cursor_or_drag:
                        # Reset scroll state
                        self.prev_palm_x = None
                        self.prev_palm_y = None

                        # Move cursor based on index finger knuckle (landmark 5) for total stability during pinch
                        ref_pt = hand_landmarks[5]

                        # Map normalized coords [0.25, 0.75] -> screen size
                        mapped_x = np.interp(ref_pt.x, (0.25, 0.75), (0, self.screen_width))
                        mapped_y = np.interp(ref_pt.y, (0.25, 0.75), (0, self.screen_height))

                        # EMA smoothing
                        target_x = self.prev_x + (mapped_x - self.prev_x) * self.smoothing
                        target_y = self.prev_y + (mapped_y - self.prev_y) * self.smoothing
                        target_x = max(0, min(self.screen_width  - 1, target_x))
                        target_y = max(0, min(self.screen_height - 1, target_y))

                        # Pinch (thumb-index) detection for left click and drag
                        is_pinched = dist_thumb_index < 0.042

                        if is_pinched:
                            if not self.mouse_pressed:
                                self.mouse_pressed = True
                                self.pinch_start_time = curr_time
                                
                                # Check if this is a rapid consecutive click in a multi-click sequence (< 0.45s)
                                time_since_release = curr_time - self.last_pinch_release_time
                                if time_since_release < 0.45 and self.click_sequence_coords is not None:
                                    # Use the exact same coordinates as the previous click to ensure Windows registers a perfect double-click!
                                    self.prev_x, self.prev_y = self.click_sequence_coords
                                else:
                                    # Start a new click sequence
                                    self.click_sequence_coords = (int(target_x), int(target_y))
                                    self.prev_x, self.prev_y = target_x, target_y

                                _mouse_move_to(int(self.prev_x), int(self.prev_y))
                                _mouse_down('left')
                                print(f"[Gesture Engine] Left click down at {self.click_sequence_coords}")
                            
                            # Freeze / Hold coordinate system during the first 0.3s of a pinch to prevent micro-movements/shaking!
                            pinch_duration = curr_time - self.pinch_start_time
                            if pinch_duration >= 0.3:
                                # After 0.3s, treat as an intentional click & drag
                                self.prev_x = target_x
                                self.prev_y = target_y
                                _mouse_move_to(int(self.prev_x), int(self.prev_y))
                                status_text = "Arrastrando..."
                            else:
                                # Keep cursor frozen during quick tap
                                _mouse_move_to(int(self.prev_x), int(self.prev_y))
                                status_text = "Click / Selección (Frozen)"
                        else:
                            if self.mouse_pressed and dist_thumb_index > 0.052:
                                _mouse_up('left')
                                self.mouse_pressed = False
                                self.last_pinch_release_time = curr_time
                                print("[Gesture Engine] Left click up (drag release).")
                            
                            # In cursor mode (not pinched), move mouse freely
                            self.prev_x = target_x
                            self.prev_y = target_y
                            _mouse_move_to(int(self.prev_x), int(self.prev_y))
                            status_text = "Modo Cursor"

                    # ══════════════════════════════════════════════════════════
                    # SIN GESTO RECONOCIDO
                    # ══════════════════════════════════════════════════════════
                    else:
                        self.prev_palm_x = None
                        self.prev_palm_y = None
                        if self.mouse_pressed:
                            _mouse_up('left')
                            self.mouse_pressed = False
                            print("[Gesture Engine] Gesture lost. Left click released.")
                        status_text = "Mano Detectada"

            else:
                # No hand detected — release mouse drag and reset scroll state
                self.prev_palm_x = None
                self.prev_palm_y = None
                if self.mouse_pressed:
                    _mouse_up('left')
                    self.mouse_pressed = False
                    print("[Gesture Engine] Hand lost. Left click released.")

            # ── Build and emit QImage ─────────────────────────────────────────
            hud_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            q_img   = QImage(hud_rgb.data, w, h, w * c, QImage.Format.Format_RGB888).copy()
            self.frame_signal.emit(q_img, status_text)

            time.sleep(0.015)

        # ── Cleanup ───────────────────────────────────────────────────────────
        cap.release()
        detector.close()
        self.active_signal.emit(False)
        print("[Gesture Engine] Hand tracking thread stopped safely.")
