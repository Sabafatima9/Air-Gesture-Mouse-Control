"""
Air Gesture Mouse Control -- entry point.

Webcam -> MediaPipe Hand Landmarker -> gestures -> pyautogui mouse actions.
Front-facing (selfie) camera: preview is mirrored so left=left.
Press Q or Esc to quit.
"""

from __future__ import annotations

import time
import urllib.request
from typing import Optional, Tuple

import cv2
import mediapipe as mp
import pyautogui

import config as cfg
from gestures import GestureDetector, Mode
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
    """Anchor motion, pinch timing for clicks/drags, and scroll state."""

    def __init__(self) -> None:
        self.mode = Mode.IDLE
        self.prev_pinch: Optional[str] = None
        # Left click / double click / drag
        self.left_pinch_start: Optional[float] = None
        self.left_held_for_drag = False
        self.last_left_click_time = 0.0
        self.pending_single_click = False
        self.pending_click_time = 0.0
        # Right click (fires on pinch RELEASE, exactly like the left click)
        self.right_pinch_start: Optional[float] = None
        self.last_action_time = 0.0
        # Scroll: its own anchor + accumulator so it never disturbs the cursor
        self.scroll_prev_y: Optional[float] = None
        self.scroll_accum = 0.0
        self.scroll_gap = 0
        # Relative cursor motion (palm anchor)
        self.anchor_prev: Optional[Tuple[float, float]] = None
        self.motion_resid: Tuple[float, float] = (0.0, 0.0)
        # HUD / status echo
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
        self.scroll_accum = 0.0
        self.scroll_gap = 0

    def reset_tracking(self) -> None:
        self.anchor_prev = None
        self.motion_resid = (0.0, 0.0)


# Short on-screen legend (simplified gesture -> mouse action).
_LEGEND_LINES = [
    "Move: move your hand (relative)",
    "Clutch: closed fist = release",
    "L-click: pinch thumb+index,",
    "   cursor follows, release = click",
    "Dbl: two quick pinches",
    "Drag: pinch, hold 0.5s, move",
    "R-click: pinch thumb+middle,",
    "   cursor follows, release = click",
    "Scroll: index+middle up, move",
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

    # Palm anchor: the point that drives the cursor.
    ax = sum(landmarks[i].x for i in cfg.MOTION_ANCHOR_POINTS) / len(
        cfg.MOTION_ANCHOR_POINTS
    )
    ay = sum(landmarks[i].y for i in cfg.MOTION_ANCHOR_POINTS) / len(
        cfg.MOTION_ANCHOR_POINTS
    )
    cv2.circle(frame, (int(ax * w), int(ay * h)), 9, (255, 255, 255), 2, cv2.LINE_AA)
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


def _depth_gain(gframe) -> float:
    """Scale palm deltas so cursor speed does not depend on hand distance."""
    gain = cfg.REFERENCE_HAND_SIZE / max(gframe.hand_size_smooth, 1e-6)
    return min(cfg.MOTION_DEPTH_MAX, max(cfg.MOTION_DEPTH_MIN, gain))


def _apply_relative_motion(gframe, state: ActionState, mouse: MouseController) -> None:
    """Move the cursor by palm motion only (relative, position-free).

    Runs on every non-fist, non-scroll frame -- including while a pinch is
    held, so the cursor keeps following the hand while aiming a click; the
    pinch RELEASE is what clicks. Sub-deadzone motion is accumulated as
    residue (slow precise aiming still moves; alternating jitter cancels).
    The anchor is re-set every frame, so fist exits, scroll exits and
    tracking glitches never jump the cursor.
    """
    ax, ay = gframe.motion_anchor
    if state.anchor_prev is None:
        state.anchor_prev = (ax, ay)
        state.motion_resid = (0.0, 0.0)
        return
    rx, ry = state.motion_resid
    dxn = ax - state.anchor_prev[0] + rx
    dyn = ay - state.anchor_prev[1] + ry
    state.motion_resid = (0.0, 0.0)
    if abs(dxn) > cfg.MOTION_JUMP or abs(dyn) > cfg.MOTION_JUMP:
        # Tracking glitch: drop the delta; never carried as residue either.
        state.anchor_prev = (ax, ay)
        return
    if abs(dxn) < cfg.MOTION_DEADZONE and abs(dyn) < cfg.MOTION_DEADZONE:
        # Below the deadzone: remember it, do not move yet.
        state.motion_resid = (dxn, dyn)
        state.anchor_prev = (ax, ay)
        return
    gain = _depth_gain(gframe)
    mouse.move_by(
        dxn * gain * mouse.screen_w * cfg.RELATIVE_GAIN_X,
        dyn * gain * mouse.screen_h * cfg.RELATIVE_GAIN_Y,
    )
    state.anchor_prev = (ax, ay)


def process_actions(
    gframe,
    state: ActionState,
    mouse: MouseController,
    detector: GestureDetector,
    now: float,
) -> Mode:
    """Apply mouse actions from gesture frame. Returns display mode."""
    # --- Closed fist: CLUTCH. The cursor is released: no motion, no clicks.
    # Re-anchoring on every fist frame means accumulated fist motion is
    # discarded: reopening the hand anywhere never jumps the cursor.
    if gframe.closed_fist:
        mouse.ensure_released()
        detector.set_dragging(False)
        state.reset_pinch()
        state.reset_scroll()
        state.pending_single_click = False
        state.right_pinch_start = None
        state.prev_pinch = None
        state.anchor_prev = gframe.motion_anchor
        state.motion_resid = (0.0, 0.0)
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
        state.right_pinch_start = None
        state.prev_pinch = None
        ay = gframe.motion_anchor[1]
        if state.scroll_prev_y is None:
            state.scroll_prev_y = ay
        else:
            dy = state.scroll_prev_y - ay  # positive when hand moves up
            state.scroll_prev_y = ay
            state.scroll_accum += dy * _depth_gain(gframe)
            ticks = int(state.scroll_accum / cfg.SCROLL_TICK_TRAVEL)
            if ticks != 0:
                state.scroll_accum -= ticks * cfg.SCROLL_TICK_TRAVEL
                mouse.scroll(ticks)
                state.last_action_time = now
        state.scroll_gap = 0
        # Re-anchor so leaving scroll never jumps the cursor.
        state.anchor_prev = gframe.motion_anchor
        state.motion_resid = (0.0, 0.0)
        state.mode = Mode.SCROLL
        return Mode.SCROLL

    # Scroll pose momentarily lost: keep the anchor frozen for a few frames so
    # pose flicker while the hand moves does not zero the scroll -- the gap
    # motion still counts when the pose returns.
    if state.scroll_prev_y is not None:
        state.scroll_gap += 1
        if state.scroll_gap > cfg.SCROLL_POSE_GRACE_FRAMES:
            state.reset_scroll()

    # --- Cursor motion: relative, from palm motion ---------------------------
    # Applies in MOVE *and* while pinches are held (aiming a click): the
    # cursor follows the hand until the pinch is released; release clicks.
    _apply_relative_motion(gframe, state, mouse)

    # --- Right pinch: hold to aim; RELEASE fires the right click -------------
    if pinch == "middle":
        state.reset_pinch()
        state.pending_single_click = False
        if pinch_engaged:
            mouse.ensure_released()
            detector.set_dragging(False)
            if state.right_pinch_start is None:
                if now - state.last_action_time < cfg.PINCH_MIN_RELEASE_GAP:
                    state.prev_pinch = pinch
                    state.mode = Mode.MOVE
                    return Mode.MOVE
                state.right_pinch_start = now
        state.prev_pinch = pinch
        state.mode = Mode.RIGHT_CLICK
        return Mode.RIGHT_CLICK

    if state.prev_pinch == "middle":
        # Right pinch released -> right click now (not on engage).
        if (
            state.right_pinch_start is not None
            and now - state.right_pinch_start >= cfg.PINCH_MIN_HOLD
            and now - state.last_action_time >= cfg.CLICK_COOLDOWN
        ):
            mouse.right_click()
            state.last_action_time = now
        state.right_pinch_start = None
        state.prev_pinch = None

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

    # --- Left pinch released -------------------------------------------------
    if state.left_pinch_start is not None:
        was_drag = state.left_held_for_drag
        held = now - state.left_pinch_start
        state.reset_pinch()
        detector.set_dragging(False)
        state.prev_pinch = None

        if was_drag:
            mouse.mouse_up()
            state.mode = Mode.MOVE
            return Mode.MOVE

        if held < cfg.PINCH_MIN_HOLD:
            # Too brief to be a deliberate click: tracking noise.
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
        "Gestures: hand motion = cursor (relative, palm-driven) | "
        "fist = release/clutch | "
        "pinch thumb+index = aim (cursor follows), release = left click, "
        "hold = drag | pinch thumb+middle, release = right click | "
        "index+middle up + move hand = scroll"
    )

    landmarker = create_landmarker()
    detector = GestureDetector()
    state = ActionState()

    camera = cv2.VideoCapture(cfg.CAMERA_INDEX)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.FRAME_HEIGHT)
    # Prefer MJPG when available -- often higher effective FPS on USB cams.
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
                # Do not advance clicks/drags during grace -- only hold cursor.
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
                state.reset_tracking()
                state.right_pinch_start = None
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
