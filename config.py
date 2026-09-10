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
# Fraction of frame edges ignored so the fingertip can reach screen edges.
# Smaller = wider usable band (easier to hit corners); keep a little margin.
FRAME_MARGIN = 0.06
# Base exponential smoothing: 0 = instant (jittery), closer to 1 = smoother/laggier.
# Adaptive smoothing in MouseController reduces this when the hand moves fast.
SMOOTHING = 0.35
# Velocity (screen px/frame) above which smoothing eases toward SMOOTHING_FAST.
SMOOTHING_VELOCITY_REF = 40.0
SMOOTHING_FAST = 0.12
# Reference hand size (wrist→middle MCP, normalized 0..1) at a comfortable
# working distance. Used to depth-compensate absolute tip→screen mapping so
# moving nearer/farther does not collapse or explode the cursor range.
REFERENCE_HAND_SIZE = 0.18
# Clamp on depth scale = REFERENCE_HAND_SIZE / hand_size.
DEPTH_SCALE_MIN = 0.55
DEPTH_SCALE_MAX = 2.4

# ---------------------------------------------------------------------------
# Tracking hold / grace
# If the hand is briefly lost, keep the last smoothed cursor for this many
# frames instead of resetting (avoids jumps from depth/angle blips).
# ---------------------------------------------------------------------------
TRACKING_HOLD_FRAMES = 10

# ---------------------------------------------------------------------------
# Pinch detection (distance / hand_size). Works at any camera distance.
# ---------------------------------------------------------------------------
PINCH_ON_RATIO = 0.28
PINCH_OFF_RATIO = 0.42

# ---------------------------------------------------------------------------
# Click / drag timing (seconds)
# ---------------------------------------------------------------------------
CLICK_COOLDOWN = 0.35
# Hold a left pinch this long to start drag instead of a click.
DRAG_HOLD_TIME = 0.45
# Two left pinches within this window (and each shorter than DRAG_HOLD_TIME)
# register as a double-click.
DOUBLE_CLICK_WINDOW = 0.40
# Ignore a second pinch that is too close in time to the previous release.
PINCH_MIN_RELEASE_GAP = 0.08

# ---------------------------------------------------------------------------
# Scroll gesture
# ---------------------------------------------------------------------------
# Vertical tip motion (normalized by hand size) per scroll "tick".
SCROLL_SENSITIVITY = 0.08
# pyautogui scroll units per tick (positive = up).
SCROLL_AMOUNT = 2
# Minimum |delta| in hand-size units before scrolling fires.
SCROLL_DEADZONE = 0.04

# ---------------------------------------------------------------------------
# Finger-up heuristics (tip vs PIP / MCP in image coords; y grows downward)
# Soft quality signals only — no hard palm-facing / orientation gate.
# ---------------------------------------------------------------------------
# Tip must be above (smaller y than) joint by this fraction of hand size.
FINGER_UP_MARGIN = 0.08
# Thumb "up/extended" uses x-distance from IP toward tip relative to hand size.
THUMB_EXTENDED_MARGIN = 0.10

# ---------------------------------------------------------------------------
# Landmark indexes (MediaPipe hand)
# ---------------------------------------------------------------------------
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

# Hand-size reference: wrist → middle MCP (depth proxy).
HAND_SIZE_A = WRIST
HAND_SIZE_B = MIDDLE_MCP

# ---------------------------------------------------------------------------
# HUD / status
# ---------------------------------------------------------------------------
WINDOW_NAME = "Air Gesture Mouse — Q / Esc to quit"
STATUS_PRINT_INTERVAL = 1.0
# Draw on-screen gesture→action legend.
SHOW_GESTURE_LEGEND = True

# pyautogui
FAILSAFE = True
PAUSE = 0.0
