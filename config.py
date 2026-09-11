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
# track. Too low -> false positives; ~0.5 / 0.4 / 0.4 is a practical balance.
# ---------------------------------------------------------------------------
NUM_HANDS = 1
MIN_HAND_DETECTION_CONFIDENCE = 0.5
MIN_HAND_PRESENCE_CONFIDENCE = 0.4
MIN_TRACKING_CONFIDENCE = 0.4

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

# Motion anchor = centroid of these landmarks (the palm). Unlike fingertips,
# the palm barely moves when fingers open/close, so pinching never shakes the
# cursor; the whole hand drives it.
MOTION_ANCHOR_POINTS = (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)

# ---------------------------------------------------------------------------
# Cursor mapping & smoothing
# ---------------------------------------------------------------------------
# Fraction of frame edges ignored; only used for the HUD guide box now.
FRAME_MARGIN = 0.06

# --- Relative cursor control (palm motion) ---------------------------------
# The cursor is driven by PALM MOTION only, like a real mouse: the hand's
# position in the camera frame never matters, so every screen edge is
# reachable while the hand stays comfortably in frame. A closed fist is the
# clutch: it releases the cursor until the hand opens again.
# Screen px per full-frame-width of palm travel.
RELATIVE_GAIN_X = 1.6
# Screen px per full-frame-height of palm travel.
RELATIVE_GAIN_Y = 1.9
# Palm motion (fraction of frame) below which the cursor holds still; smaller
# leftovers accumulate as residue so slow precise aiming still works.
MOTION_DEADZONE = 0.0025
# Per-frame palm jump (fraction of frame) above this is a tracking glitch:
# re-anchor and ignore it (never applied as cursor motion).
MOTION_JUMP = 0.085

# Distance-invariant gain: palm deltas are scaled by reference/current hand
# size, so leaning toward or away from the camera does not change cursor
# speed. Clamped for safety.
REFERENCE_HAND_SIZE = 0.18
MOTION_DEPTH_MIN = 0.65
MOTION_DEPTH_MAX = 1.6
# EMA for the hand size used above (raw per-frame size jitters).
HAND_SIZE_EMA = 0.25

# --- Palm anchor filter (velocity-adaptive EMA) ----------------------------
# Still hand -> ANCHOR_ALPHA_SLOW (jitter killed: steady cursor at rest);
# moving hand -> ANCHOR_ALPHA_FAST (responsive: no rubber-band lag). This is
# what keeps the cursor stable while aiming a click without adding lag.
ANCHOR_ALPHA_SLOW = 0.22
ANCHOR_ALPHA_FAST = 0.75
# Per-frame anchor speed (fraction of frame) counted as "fast".
ANCHOR_SPEED_REF = 0.012
# EMA for the speed estimate itself.
ANCHOR_SPEED_EMA = 0.35
# Per-frame anchor jump (fraction of frame) treated as a tracking glitch:
# the filter snaps to the new position; the main loop's jump guard drops
# the resulting delta so the cursor never teleports.
ANCHOR_SNAP = 0.22

# --- Final screen-space smoothing (MouseController) ------------------------
# 0 = instant (jittery), closer to 1 = smoother/laggier.
SMOOTHING = 0.22
# Velocity (screen px/frame) above which smoothing eases toward SMOOTHING_FAST.
SMOOTHING_VELOCITY_REF = 45.0
SMOOTHING_FAST = 0.06
# Ignore sub-pixel jitter below this screen-pixel distance (comfort).
CURSOR_DEADZONE_PX = 1.0

# Depth scale is HUD/debug only now (motion is purely relative).
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
# A pinch shorter than this is tracking noise, not a click gesture.
PINCH_MIN_HOLD = 0.05

# ---------------------------------------------------------------------------
# Scroll gesture (continuous, speed-proportional -- like a real wheel)
# ---------------------------------------------------------------------------
# Palm travel (fraction of frame height, depth-normalized) per wheel notch.
# One Windows wheel notch scrolls ~3 lines by default.
SCROLL_TICK_TRAVEL = 0.0065
# Consecutive frames of scroll pose required before scroll activates.
SCROLL_CONFIRM_FRAMES = 2
# Frames a broken scroll pose is remembered: pose flicker while the hand
# moves must not zero the scroll -- the gap motion still counts when the
# pose returns.
SCROLL_POSE_GRACE_FRAMES = 12
# Windows wheel detents per notch (pyautogui sends raw detents on win32).
WHEEL_DELTA = 120

# ---------------------------------------------------------------------------
# Closed-fist / clutch pose
# ---------------------------------------------------------------------------
# Consecutive frames of fist before the clutch engages (avoids flicker).
FIST_CONFIRM_FRAMES = 2

# ---------------------------------------------------------------------------
# Finger-up heuristics (tip vs PIP / MCP in image coords; y grows downward)
# ---------------------------------------------------------------------------
FINGER_UP_MARGIN = 0.07
THUMB_EXTENDED_MARGIN = 0.09

# ---------------------------------------------------------------------------
# HUD / status
# ---------------------------------------------------------------------------
WINDOW_NAME = "Air Gesture Mouse - Q / Esc to quit"
STATUS_PRINT_INTERVAL = 1.0
SHOW_GESTURE_LEGEND = True
# Compact debug lines (TIMRP / pinch ratios). Keep True for tuning.
SHOW_DEBUG_HUD = True

# pyautogui
FAILSAFE = True
PAUSE = 0.0
