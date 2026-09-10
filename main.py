"""
Air Gesture Mouse Control — entry point.

Webcam → MediaPipe Hand Landmarker → gestures → pyautogui mouse actions.
Front-facing (selfie) camera: preview is mirrored so left=left.
Press Q or Esc to quit.
"""

from __future__ import annotations

import time
import urllib.request
from typing import Optional

import cv2
import mediapipe as mp
import pyautogui

import config as cfg
from gestures import GestureDetector, Mode, map_to_screen
from mouse_controller import MouseController


def ensure_model() -> str:
    """Return path to hand_landmarker.task, downloading if missing."""
    path = cfg.MODEL_PATH
    if not path.exists():
        print(f"Model file not found. Downloading {cfg.MODEL_FILENAME} ...")
        urllib.request.urlretrieve(cfg.MODEL_URL, str(path))
        print("Model downloaded successfully!")
    return str(path)


def create_landmarker():
    model_path = ensure_model()
    base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=base_options,
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=cfg.NUM_HANDS,
        min_hand_detection_confidence=cfg.MIN_HAND_DETECTION_CONFIDENCE,
        min_hand_presence_confidence=cfg.MIN_HAND_PRESENCE_CONFIDENCE,
        min_tracking_confidence=cfg.MIN_TRACKING_CONFIDENCE,
    )
    return mp.tasks.vision.HandLandmarker.create_from_options(options)


class ActionState:
    """Tracks pinch timing for click / double-click / drag."""

    def __init__(self) -> None:
        self.mode = Mode.IDLE
        self.prev_pinch: Optional[str] = None
        self.left_pinch_start: Optional[float] = None
        self.left_held_for_drag = False
        self.last_left_click_time = 0.0
        self.pending_single_click = False
        self.pending_click_time = 0.0
        self.last_action_time = 0.0
        self.scroll_prev_y: Optional[float] = None
        self.last_status = ""
        self.last_status_t = 0.0

    def reset_pinch(self) -> None:
        self.left_pinch_start = None
        self.left_held_for_drag = False

    def reset_scroll(self) -> None:
        self.scroll_prev_y = None


def _draw_hud(
    frame,
    mode: Mode,
    fingers_label: str,
    pinches: dict,
    hand_found: bool,
) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 110), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    mode_color = {
        Mode.IDLE: (180, 180, 180),
        Mode.MOVE: (80, 220, 80),
        Mode.LEFT_CLICK: (80, 180, 255),
        Mode.RIGHT_CLICK: (80, 80, 255),
        Mode.MIDDLE_CLICK: (255, 180, 80),
        Mode.DOUBLE_CLICK: (255, 255, 80),
        Mode.DRAG: (255, 80, 200),
        Mode.SCROLL: (200, 255, 80),
    }.get(mode, (200, 200, 200))

    status = "No hand" if not hand_found else mode.name.replace("_", " ")
    cv2.putText(
        frame, f"Mode: {status}", (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.75, mode_color, 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, f"Fingers: {fingers_label}", (12, 58),
        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1, cv2.LINE_AA,
    )
    pinch_txt = (
        f"Pinch  idx={pinches.get('idx', 1):.2f}  "
        f"mid={pinches.get('mid', 1):.2f}  "
        f"rng={pinches.get('rng', 1):.2f}"
    )
    cv2.putText(
        frame, pinch_txt, (12, 88),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 255, 180), 1, cv2.LINE_AA,
    )
    cv2.putText(
        frame, "Q/Esc quit", (w - 130, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1, cv2.LINE_AA,
    )


def _draw_landmarks(frame, landmarks, active_pinch: Optional[str]) -> None:
    h, w = frame.shape[:2]

    def px(idx: int):
        lm = landmarks[idx]
        return int(lm.x * w), int(lm.y * h)

    connections = [
        (0, 1), (1, 2), (2, 3), (3, 4),
        (0, 5), (5, 6), (6, 7), (7, 8),
        (0, 9), (9, 10), (10, 11), (11, 12),
        (0, 13), (13, 14), (14, 15), (15, 16),
        (0, 17), (17, 18), (18, 19), (19, 20),
        (5, 9), (9, 13), (13, 17),
    ]
    for a, b in connections:
        cv2.line(frame, px(a), px(b), (60, 60, 60), 1, cv2.LINE_AA)

    tip_colors = {
        cfg.THUMB_TIP: (255, 0, 255),
        cfg.INDEX_TIP: (0, 255, 255),
        cfg.MIDDLE_TIP: (0, 200, 255),
        cfg.RING_TIP: (255, 200, 0),
        cfg.PINKY_TIP: (200, 200, 200),
    }
    for idx, color in tip_colors.items():
        cv2.circle(frame, px(idx), 7, color, -1, cv2.LINE_AA)

    if active_pinch == "index":
        cv2.line(frame, px(cfg.THUMB_TIP), px(cfg.INDEX_TIP), (0, 255, 0), 2)
    elif active_pinch == "middle":
        cv2.line(frame, px(cfg.THUMB_TIP), px(cfg.MIDDLE_TIP), (0, 80, 255), 2)
    elif active_pinch == "ring":
        cv2.line(frame, px(cfg.THUMB_TIP), px(cfg.RING_TIP), (255, 160, 0), 2)


def process_actions(
    gframe,
    state: ActionState,
    mouse: MouseController,
    now: float,
) -> Mode:
    """Apply mouse actions from gesture frame. Returns display mode."""
    pinch = gframe.active_pinch
    pinch_engaged = pinch is not None and pinch != state.prev_pinch

    # --- Scroll pose (priority over pinches) --------------------------------
    if gframe.scroll_pose:
        mouse.ensure_released()
        state.reset_pinch()
        state.pending_single_click = False
        state.prev_pinch = None
        ay = gframe.scroll_anchor_norm[1]
        if state.scroll_prev_y is None:
            state.scroll_prev_y = ay
        else:
            dy = state.scroll_prev_y - ay  # positive when hand moves up
            scaled = dy / max(gframe.hand_size, 1e-6)
            if abs(scaled) >= cfg.SCROLL_DEADZONE:
                ticks = int(scaled / cfg.SCROLL_SENSITIVITY)
                if ticks != 0:
                    mouse.scroll(ticks)
                    state.scroll_prev_y = ay
                    state.last_action_time = now
            else:
                # Soft follow so small jitter does not accumulate.
                state.scroll_prev_y = 0.85 * state.scroll_prev_y + 0.15 * ay
        state.mode = Mode.SCROLL
        return Mode.SCROLL

    state.reset_scroll()

    # --- Cursor move (always when not scrolling) ----------------------------
    sx, sy = map_to_screen(
        gframe.index_tip_norm[0],
        gframe.index_tip_norm[1],
        mouse.screen_w,
        mouse.screen_h,
    )
    mouse.move_to_smoothed(sx, sy)

    # --- Right click: thumb–middle pinch (rising edge) ----------------------
    if pinch == "middle":
        mouse.ensure_released()
        state.reset_pinch()
        state.pending_single_click = False
        if pinch_engaged and (now - state.last_action_time >= cfg.CLICK_COOLDOWN):
            mouse.right_click()
            state.last_action_time = now
        state.prev_pinch = pinch
        state.mode = Mode.RIGHT_CLICK
        return Mode.RIGHT_CLICK

    # --- Middle click: thumb–ring pinch (rising edge) -----------------------
    if pinch == "ring":
        mouse.ensure_released()
        state.reset_pinch()
        state.pending_single_click = False
        if pinch_engaged and (now - state.last_action_time >= cfg.CLICK_COOLDOWN):
            mouse.middle_click()
            state.last_action_time = now
        state.prev_pinch = pinch
        state.mode = Mode.MIDDLE_CLICK
        return Mode.MIDDLE_CLICK

    # --- Left pinch: click / double / drag ----------------------------------
    if pinch == "index":
        if state.left_pinch_start is None:
            state.left_pinch_start = now
            state.left_held_for_drag = False

        held = now - state.left_pinch_start
        if held >= cfg.DRAG_HOLD_TIME:
            if not state.left_held_for_drag:
                state.pending_single_click = False
                mouse.mouse_down()
                state.left_held_for_drag = True
                state.last_action_time = now
            state.prev_pinch = pinch
            state.mode = Mode.DRAG
            return Mode.DRAG

        state.prev_pinch = pinch
        state.mode = Mode.LEFT_CLICK
        return Mode.LEFT_CLICK

    # --- Pinch released -----------------------------------------------------
    if state.left_pinch_start is not None:
        was_drag = state.left_held_for_drag
        state.reset_pinch()
        state.prev_pinch = None

        if was_drag:
            mouse.mouse_up()
            state.mode = Mode.MOVE
            return Mode.MOVE

        # Short pinch → schedule single click, or promote to double-click.
        if (
            state.pending_single_click
            and (now - state.pending_click_time) <= cfg.DOUBLE_CLICK_WINDOW
        ):
            state.pending_single_click = False
            mouse.double_click()
            state.last_left_click_time = now
            state.last_action_time = now
            state.mode = Mode.DOUBLE_CLICK
            return Mode.DOUBLE_CLICK

        state.pending_single_click = True
        state.pending_click_time = now
        state.mode = Mode.LEFT_CLICK
        return Mode.LEFT_CLICK

    state.prev_pinch = pinch

    # Flush deferred single click after the double-click window expires.
    if state.pending_single_click and (
        now - state.pending_click_time > cfg.DOUBLE_CLICK_WINDOW
    ):
        if now - state.last_left_click_time >= cfg.CLICK_COOLDOWN:
            mouse.left_click()
            state.last_left_click_time = now
            state.last_action_time = now
        state.pending_single_click = False
        state.mode = Mode.LEFT_CLICK
        return Mode.LEFT_CLICK

    if state.pending_single_click:
        state.mode = Mode.LEFT_CLICK
        return Mode.LEFT_CLICK

    state.mode = Mode.MOVE
    return Mode.MOVE


def main() -> None:
    mouse = MouseController()
    print(
        f"Screen: {mouse.screen_w}x{mouse.screen_h}  "
        f"platform={mouse.platform_hint()}"
    )
    print("FAILSAFE: fling cursor to top-left corner to emergency-stop.")

    landmarker = create_landmarker()
    detector = GestureDetector()
    state = ActionState()

    camera = cv2.VideoCapture(cfg.CAMERA_INDEX)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.FRAME_HEIGHT)

    if not camera.isOpened():
        print(
            "ERROR: Could not open the webcam. "
            "Try changing CAMERA_INDEX in config.py."
        )
        landmarker.close()
        return

    cv2.namedWindow(cfg.WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(cfg.WINDOW_NAME, cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT)

    frame_timestamp_ms = 0

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("ERROR: Failed to read a frame from the camera.")
                break

            # Mirror for natural selfie mapping (user's left ↔ screen left).
            frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_timestamp_ms += int(1000 / 30)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(mp_image, frame_timestamp_ms)

            hand_found = bool(result and result.hand_landmarks)
            fingers_label = "-----"
            pinch_dict = {"idx": 1.0, "mid": 1.0, "rng": 1.0}
            mode = Mode.IDLE
            now = time.time()

            if hand_found:
                landmarks = result.hand_landmarks[0]
                gframe = detector.update(landmarks)
                fingers_label = gframe.fingers.label()
                pinch_dict = gframe.pinches.as_dict()
                mode = process_actions(gframe, state, mouse, now)
                _draw_landmarks(frame, landmarks, gframe.active_pinch)
            else:
                detector.reset()
                mouse.ensure_released()
                mouse.reset_smoothing()
                state.reset_pinch()
                state.reset_scroll()
                state.pending_single_click = False
                state.prev_pinch = None
                state.mode = Mode.IDLE

            _draw_hud(frame, mode, fingers_label, pinch_dict, hand_found)

            status = mode.name if hand_found else "NO_HAND"
            if (
                status != state.last_status
                or now - state.last_status_t > cfg.STATUS_PRINT_INTERVAL
            ):
                print(status)
                state.last_status = status
                state.last_status_t = now

            cv2.imshow(cfg.WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), ord("Q"), 27):
                print("Quit key pressed. Exiting...")
                break

    except pyautogui.FailSafeException:
        print("FAILSAFE triggered (cursor in top-left). Exiting...")
    finally:
        mouse.ensure_released()
        camera.release()
        cv2.destroyAllWindows()
        landmarker.close()
        print("Camera released. Goodbye!")


if __name__ == "__main__":
    main()
