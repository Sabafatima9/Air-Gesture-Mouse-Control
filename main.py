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
        self.hold_frames_left = 0
        self.last_hand_size = 0.0
        self.last_depth_scale = 1.0
        self.last_fingers_label = "-----"
        self.last_pinch_dict = {"idx": 1.0, "mid": 1.0}

    def reset_pinch(self) -> None:
        self.left_pinch_start = None
        self.left_held_for_drag = False

    def reset_scroll(self) -> None:
        self.scroll_prev_y = None


# Short on-screen legend (simplified gesture → mouse action).
_LEGEND_LINES = [
    "Move: index tip",
    "L-click: thumb+index",
    "Dbl: 2x quick pinch",
    "Drag: pinch + hold",
    "Safe: closed fist",
    "Scroll: index+middle",
    "R-click: thumb+middle",
]


def _mode_label(mode: Mode, hand_found: bool, holding: bool) -> str:
    """Human-friendly HUD status (matches prompt feedback list)."""
    if holding:
        return "HOLD (tracking grace)"
    if not hand_found:
        return "No Hand Detected"
    return {
        Mode.IDLE: "Hand Detected",
        Mode.MOVE: "Cursor Active",
        Mode.LEFT_CLICK: "LEFT CLICK",
        Mode.RIGHT_CLICK: "RIGHT CLICK",
        Mode.DOUBLE_CLICK: "DOUBLE CLICK",
        Mode.DRAG: "DRAGGING",
        Mode.SCROLL: "SCROLL",
        Mode.SAFE: "SAFE / NO ACTION",
    }.get(mode, mode.name.replace("_", " "))


def _draw_hud(
    frame,
    mode: Mode,
    fingers_label: str,
    pinches: dict,
    hand_found: bool,
    hand_size: float = 0.0,
    depth_scale: float = 1.0,
    holding: bool = False,
) -> None:
    h, w = frame.shape[:2]
    top_h = 110 if cfg.SHOW_DEBUG_HUD else 56
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, top_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    mode_color = {
        Mode.IDLE: (180, 180, 180),
        Mode.MOVE: (80, 220, 80),
        Mode.LEFT_CLICK: (80, 180, 255),
        Mode.RIGHT_CLICK: (80, 80, 255),
        Mode.DOUBLE_CLICK: (255, 255, 80),
        Mode.DRAG: (255, 80, 200),
        Mode.SCROLL: (200, 255, 80),
        Mode.SAFE: (160, 160, 255),
    }.get(mode, (200, 200, 200))
    if holding:
        mode_color = (180, 180, 100)
    if not hand_found and not holding:
        mode_color = (120, 120, 120)

    status = _mode_label(mode, hand_found, holding)
    cv2.putText(
        frame, status, (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX, 0.72, mode_color, 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, "Q/Esc quit", (w - 130, 26),
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (160, 160, 160), 1, cv2.LINE_AA,
    )

    if cfg.SHOW_DEBUG_HUD:
        cv2.putText(
            frame, f"Fingers TIMRP: {fingers_label}", (12, 54),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1, cv2.LINE_AA,
        )
        pinch_txt = (
            f"Pinch  idx={pinches.get('idx', 1):.2f}  "
            f"mid={pinches.get('mid', 1):.2f}"
        )
        cv2.putText(
            frame, pinch_txt, (12, 76),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 255, 180), 1, cv2.LINE_AA,
        )
        depth_txt = f"HandSize={hand_size:.3f}  DepthScale={depth_scale:.2f}"
        cv2.putText(
            frame, depth_txt, (12, 98),
            cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 200, 255), 1, cv2.LINE_AA,
        )

    if cfg.SHOW_GESTURE_LEGEND:
        legend_x = w - 230
        legend_y0 = top_h + 16
        box_h = 18 * len(_LEGEND_LINES) + 12
        overlay2 = frame.copy()
        cv2.rectangle(
            overlay2,
            (legend_x - 8, legend_y0 - 14),
            (w - 4, legend_y0 - 14 + box_h),
            (20, 20, 20),
            -1,
        )
        cv2.addWeighted(overlay2, 0.45, frame, 0.55, 0, frame)
        for i, line in enumerate(_LEGEND_LINES):
            cv2.putText(
                frame, line, (legend_x, legend_y0 + i * 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1, cv2.LINE_AA,
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

    cv2.line(frame, px(cfg.WRIST), px(cfg.MIDDLE_MCP), (100, 180, 255), 2, cv2.LINE_AA)
    cv2.circle(frame, px(cfg.WRIST), 5, (100, 180, 255), -1, cv2.LINE_AA)

    if active_pinch == "index":
        cv2.line(frame, px(cfg.THUMB_TIP), px(cfg.INDEX_TIP), (0, 255, 0), 2)
    elif active_pinch == "middle":
        cv2.line(frame, px(cfg.THUMB_TIP), px(cfg.MIDDLE_TIP), (0, 80, 255), 2)

    m = cfg.FRAME_MARGIN
    x0, y0 = int(m * w), int(m * h)
    x1, y1 = int((1.0 - m) * w), int((1.0 - m) * h)
    cv2.rectangle(frame, (x0, y0), (x1, y1), (50, 50, 80), 1, cv2.LINE_AA)


def process_actions(
    gframe,
    state: ActionState,
    mouse: MouseController,
    detector: GestureDetector,
    now: float,
) -> Mode:
    """Apply mouse actions from gesture frame. Returns display mode."""
    # --- Closed fist: SAFE / NO ACTION (highest comfort priority) -----------
    if gframe.closed_fist:
        mouse.ensure_released()
        detector.set_dragging(False)
        state.reset_pinch()
        state.reset_scroll()
        state.pending_single_click = False
        state.prev_pinch = None
        state.mode = Mode.SAFE
        return Mode.SAFE

    pinch = gframe.active_pinch
    pinch_engaged = pinch is not None and pinch != state.prev_pinch

    # --- Scroll pose (confirmed) --------------------------------------------
    if gframe.scroll_pose:
        mouse.ensure_released()
        detector.set_dragging(False)
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
                state.scroll_prev_y = 0.85 * state.scroll_prev_y + 0.15 * ay
        state.mode = Mode.SCROLL
        return Mode.SCROLL

    state.reset_scroll()

    # --- Cursor move (depth-compensated tip → screen) -----------------------
    sx, sy = map_to_screen(
        gframe.cursor_norm[0],
        gframe.cursor_norm[1],
        mouse.screen_w,
        mouse.screen_h,
    )
    mouse.move_to_smoothed(sx, sy)

    # --- Right click: thumb–middle pinch (optional, rising edge) ------------
    if pinch == "middle":
        mouse.ensure_released()
        detector.set_dragging(False)
        state.reset_pinch()
        state.pending_single_click = False
        if pinch_engaged and (now - state.last_action_time >= cfg.CLICK_COOLDOWN):
            mouse.right_click()
            state.last_action_time = now
        state.prev_pinch = pinch
        state.mode = Mode.RIGHT_CLICK
        return Mode.RIGHT_CLICK

    # --- Left pinch: click / double / drag ----------------------------------
    if pinch == "index":
        if state.left_pinch_start is None:
            # Ignore a re-pinch that is too soon after the previous release.
            if now - state.last_action_time < cfg.PINCH_MIN_RELEASE_GAP:
                state.prev_pinch = pinch
                state.mode = Mode.MOVE
                return Mode.MOVE
            state.left_pinch_start = now
            state.left_held_for_drag = False

        held = now - state.left_pinch_start
        if held >= cfg.DRAG_HOLD_TIME:
            if not state.left_held_for_drag:
                state.pending_single_click = False
                mouse.mouse_down()
                state.left_held_for_drag = True
                detector.set_dragging(True)
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
        detector.set_dragging(False)
        state.prev_pinch = None

        if was_drag:
            mouse.mouse_up()
            state.mode = Mode.MOVE
            return Mode.MOVE

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
    print(
        "Gestures: Move=index | L/Dbl/Drag=thumb+index | "
        "Safe=fist | Scroll=index+middle | R=thumb+middle (optional)"
    )

    landmarker = create_landmarker()
    detector = GestureDetector()
    state = ActionState()

    camera = cv2.VideoCapture(cfg.CAMERA_INDEX)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.FRAME_HEIGHT)
    # Prefer MJPEG when available — often higher effective FPS on USB cams.
    try:
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    if not camera.isOpened():
        print(
            "ERROR: Could not open the webcam. "
            "Try changing CAMERA_INDEX in config.py."
        )
        landmarker.close()
        return

    cv2.namedWindow(cfg.WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(cfg.WINDOW_NAME, cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT)

    t0 = time.time()

    try:
        while True:
            ok, frame = camera.read()
            if not ok:
                print("ERROR: Failed to read a frame from the camera.")
                break

            frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # Real elapsed ms keeps MediaPipe VIDEO timestamps monotonic & accurate.
            frame_timestamp_ms = max(1, int((time.time() - t0) * 1000))
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = landmarker.detect_for_video(mp_image, frame_timestamp_ms)

            hand_found = bool(result and result.hand_landmarks)
            fingers_label = "-----"
            pinch_dict = {"idx": 1.0, "mid": 1.0}
            hand_size_v = 0.0
            depth_scale_v = 1.0
            mode = Mode.IDLE
            holding = False
            now = time.time()

            if hand_found:
                landmarks = result.hand_landmarks[0]
                gframe = detector.update(landmarks)
                fingers_label = gframe.fingers.label()
                pinch_dict = gframe.pinches.as_dict()
                hand_size_v = gframe.hand_size
                depth_scale_v = gframe.depth_scale
                state.last_hand_size = hand_size_v
                state.last_depth_scale = depth_scale_v
                state.last_fingers_label = fingers_label
                state.last_pinch_dict = pinch_dict
                state.hold_frames_left = cfg.TRACKING_HOLD_FRAMES
                mode = process_actions(gframe, state, mouse, detector, now)
                _draw_landmarks(frame, landmarks, gframe.active_pinch)
            elif state.hold_frames_left > 0:
                state.hold_frames_left -= 1
                holding = True
                fingers_label = state.last_fingers_label
                pinch_dict = state.last_pinch_dict
                hand_size_v = state.last_hand_size
                depth_scale_v = state.last_depth_scale
                # Do not advance clicks/drags during grace — only hold cursor.
                if state.mode == Mode.SAFE:
                    mode = Mode.SAFE
                else:
                    mode = state.mode if state.mode != Mode.IDLE else Mode.MOVE
                if mode != Mode.SAFE:
                    mouse.hold_smoothed_position()
            else:
                # Hand lost past grace: flush a pending single click first so a
                # completed pinch is not silently swallowed by a tracking blip.
                if state.pending_single_click:
                    if now - state.last_left_click_time >= cfg.CLICK_COOLDOWN:
                        mouse.left_click()
                        state.last_left_click_time = now
                        state.last_action_time = now
                    state.pending_single_click = False
                detector.reset()
                mouse.ensure_released()
                mouse.reset_smoothing()
                state.reset_pinch()
                state.reset_scroll()
                state.prev_pinch = None
                state.mode = Mode.IDLE

            _draw_hud(
                frame,
                mode,
                fingers_label,
                pinch_dict,
                hand_found,
                hand_size=hand_size_v,
                depth_scale=depth_scale_v,
                holding=holding,
            )

            status = _mode_label(mode, hand_found, holding)
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
