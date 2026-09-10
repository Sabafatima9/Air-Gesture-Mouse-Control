"""Tunable constants for Air Gesture Mouse Control."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths / model
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
MODEL_FILENAME = "hand_landmarker.task"
MODEL_PATH = PROJECT_DIR / MODEL_FILENAME
MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# ---------------------------------------------------------------------------
# MediaPipe Hand Landmarker
# Lower thresholds so hands farther from the camera (or slightly angled) still
# track. Too low → false positives; ~0.5 / 0.4 / 0.4 is a practical balance.
# ---------------------------------------------------------------------------
NUM_HANDS = 1
MIN_HAND_DETECTION_CONFIDENCE = 0.5
MIN_HAND_PRESENCE_CONFIDENCE = 0.4
MIN_TRACKING_CONFIDENCE = 0.4

# ---------------------------------------------------------------------------
# Cursor mapping & smoothing
# ---------------------------------------------------------------------------
# Fraction of frame edges ignored; only used for the HUD guide box now.
FRAME_MARGIN = 0.06
# --- Relative cursor control ------------------------------------------------
# The cursor is driven by hand MOTION (like a real mouse), never by the
# hand's position in the camera frame. Closing the fist releases the cursor;
# reopening re-anchors with no jump.
# Screen px per full-frame-width of hand travel.
RELATIVE_GAIN_X = 1.6
# Screen px per full-frame-height of hand travel.
RELATIVE_GAIN_Y = 1.9
# Hand-motion (fraction of frame) below which the cursor holds still.
MOTION_DEADZONE = 0.0035
# Per-frame hand jump (fraction of frame) above this is treated as a tracking
# glitch (camera stutter / hand re-detection) and re-anchored, NOT applied as
# cursor motion. Guards the low-quality-camera case.
MOTION_JUMP = 0.10
# Base exponential smoothing: 0 = instant (jittery), closer to 1 = smoother/laggier.
SMOOTHING = 0.38
# Velocity (screen px/frame) above which smoothing eases toward SMOOTHING_FAST.
SMOOTHING_VELOCITY_REF = 45.0
SMOOTHING_FAST = 0.10
# Ignore sub-pixel jitter below this screen-pixel distance (comfort).
CURSOR_DEADZONE_PX = 1.5
# Reference hand size (wrist→middle MCP, normalized 0..1) at a comfortable
# working distance. Used to depth-compensate absolute tip→screen mapping.
REFERENCE_HAND_SIZE = 0.18
DEPTH_SCALE_MIN = 0.55
DEPTH_SCALE_MAX = 2.4

# ---------------------------------------------------------------------------
# Tracking hold / grace
# ---------------------------------------------------------------------------
TRACKING_HOLD_FRAMES = 10

# ---------------------------------------------------------------------------
# Pinch detection (distance / hand_size). Forgiving for comfort.
# ---------------------------------------------------------------------------
PINCH_ON_RATIO = 0.34
PINCH_OFF_RATIO = 0.50
# While dragging, stay latched until pinch opens further (tolerance).
DRAG_PINCH_OFF_RATIO = 0.62

# ---------------------------------------------------------------------------
# Click / drag timing (seconds)
# ---------------------------------------------------------------------------
CLICK_COOLDOWN = 0.30
DRAG_HOLD_TIME = 0.48
DOUBLE_CLICK_WINDOW = 0.42
PINCH_MIN_RELEASE_GAP = 0.08

# ---------------------------------------------------------------------------
# Scroll gesture (continuous, speed-proportional -- like a real wheel)
# ---------------------------------------------------------------------------
# Accumulated hand travel (fraction of frame height) per scroll tick.
# ~0.012 = one wheel notch per ~1.2% of frame height of hand travel.
SCROLL_SPEED = 0.012
# Consecutive frames of scroll pose required before scroll activates.
SCROLL_CONFIRM_FRAMES = 2

# ---------------------------------------------------------------------------
# Closed-fist / safe pose
# ---------------------------------------------------------------------------
# Consecutive frames of fist before SAFE engages (avoids flicker).
FIST_CONFIRM_FRAMES = 2

# ---------------------------------------------------------------------------
# Finger-up heuristics (tip vs PIP / MCP in image coords; y grows downward)
# ---------------------------------------------------------------------------
FINGER_UP_MARGIN = 0.07
THUMB_EXTENDED_MARGIN = 0.09

# ---------------------------------------------------------------------------
# Landmark indexes (MediaPipe hand)
# ---------------------------------------------------------------------------
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

HAND_SIZE_A = WRIST
HAND_SIZE_B = MIDDLE_MCP

# ---------------------------------------------------------------------------
# HUD / status
# ---------------------------------------------------------------------------
WINDOW_NAME = "Air Gesture Mouse — Q / Esc to quit"
STATUS_PRINT_INTERVAL = 1.0
SHOW_GESTURE_LEGEND = True
# Compact debug lines (TIMRP / pinch ratios). Keep True for tuning.
SHOW_DEBUG_HUD = True

# pyautogui
FAILSAFE = True
PAUSE = 0.0
