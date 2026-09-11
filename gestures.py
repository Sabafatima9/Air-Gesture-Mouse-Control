"""Finger-up, pinch, fist, and scroll-state detection from MediaPipe landmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Sequence, Tuple

import numpy as np

import config as cfg


class Mode(Enum):
    """Current interaction mode shown on the HUD."""

    IDLE = auto()
    MOVE = auto()
    LEFT_CLICK = auto()
    RIGHT_CLICK = auto()
    DOUBLE_CLICK = auto()
    DRAG = auto()
    SCROLL = auto()
    SAFE = auto()


@dataclass
class FingerState:
    """Which fingers are extended (True) vs curled (False)."""

    thumb: bool = False
    index: bool = False
    middle: bool = False
    ring: bool = False
    pinky: bool = False

    def count_up(self) -> int:
        return sum((self.thumb, self.index, self.middle, self.ring, self.pinky))

    def label(self) -> str:
        bits = [
            "T" if self.thumb else "-",
            "I" if self.index else "-",
            "M" if self.middle else "-",
            "R" if self.ring else "-",
            "P" if self.pinky else "-",
        ]
        return "".join(bits)


@dataclass
class PinchRatios:
    index: float = 1.0
    middle: float = 1.0

    def as_dict(self) -> dict:
        return {
            "idx": self.index,
            "mid": self.middle,
        }


@dataclass
class GestureFrame:
    """Per-frame gesture snapshot derived from landmarks."""

    fingers: FingerState = field(default_factory=FingerState)
    pinches: PinchRatios = field(default_factory=PinchRatios)
    hand_size: float = 1.0
    # EMA of hand size: stable depth estimate for gain normalization.
    hand_size_smooth: float = 1.0
    # HUD/debug only (motion is purely relative now).
    depth_scale: float = 1.0
    # Filtered palm centroid -- THE cursor motion anchor.
    motion_anchor: Tuple[float, float] = (0.5, 0.5)
    scroll_pose: bool = False
    closed_fist: bool = False
    # "index" | "middle" | None
    active_pinch: Optional[str] = None


def _lm_xy(landmarks: Sequence, idx: int) -> np.ndarray:
    lm = landmarks[idx]
    return np.array([lm.x, lm.y], dtype=np.float64)


def palm_anchor(landmarks: Sequence) -> Tuple[float, float]:
    """Motion anchor: centroid of wrist + the four finger MCP joints.

    This point barely moves when fingers open or close (unlike any fingertip),
    so pinching cannot shake the cursor; it is the most stable place to drive
    relative motion from.
    """
    pts = np.mean([_lm_xy(landmarks, i) for i in cfg.MOTION_ANCHOR_POINTS], axis=0)
    return float(pts[0]), float(pts[1])


class AnchorFilter:
    """Velocity-adaptive exponential filter on the palm anchor.

    Still hand -> strong smoothing (steady cursor, jitter killed); moving
    hand -> weak smoothing (responsive, no rubber-band lag). Keeps the cursor
    stable while aiming a click without feeling laggy.
    """

    def __init__(self) -> None:
        self._x: Optional[float] = None
        self._y: Optional[float] = None
        self._speed: float = 0.0

    def reset(self) -> None:
        self._x = None
        self._y = None
        self._speed = 0.0

    def update(self, x: float, y: float) -> Tuple[float, float]:
        if self._x is None:
            self._x, self._y = float(x), float(y)
            self._speed = 0.0
            return self._x, self._y
        dx = x - self._x
        dy = y - self._y
        step = float(np.hypot(dx, dy))
        if step > cfg.ANCHOR_SNAP:
            # Tracking glitch / re-detection: snap to the new position instead
            # of gliding there (the main loop's jump guard drops that delta).
            self._x, self._y = float(x), float(y)
            return self._x, self._y
        # Smoothed speed estimate -> gentle alpha adaptation across frames.
        self._speed += cfg.ANCHOR_SPEED_EMA * (step - self._speed)
        t = min(1.0, self._speed / max(cfg.ANCHOR_SPEED_REF, 1e-6))
        alpha = cfg.ANCHOR_ALPHA_SLOW + (
            cfg.ANCHOR_ALPHA_FAST - cfg.ANCHOR_ALPHA_SLOW
        ) * t
        self._x += dx * alpha
        self._y += dy * alpha
        return self._x, self._y


def hand_size(landmarks: Sequence) -> float:
    """Wrist -> middle MCP distance in normalized image coords (depth proxy)."""
    a = _lm_xy(landmarks, cfg.HAND_SIZE_A)
    b = _lm_xy(landmarks, cfg.HAND_SIZE_B)
    size = float(np.linalg.norm(a - b))
    return max(size, 1e-6)


def depth_scale_from_hand_size(size: float) -> float:
    """HUD/debug value: how much farther than reference the hand is."""
    raw = cfg.REFERENCE_HAND_SIZE / max(size, 1e-6)
    return float(np.clip(raw, cfg.DEPTH_SCALE_MIN, cfg.DEPTH_SCALE_MAX))


def fingers_up(landmarks: Sequence, size: float) -> FingerState:
    """Soft finger-up heuristics -- no hard palm-facing / orientation gate."""
    margin = cfg.FINGER_UP_MARGIN * size

    def tip_above_pip(tip_i: int, pip_i: int) -> bool:
        tip = _lm_xy(landmarks, tip_i)
        pip = _lm_xy(landmarks, pip_i)
        return tip[1] < pip[1] - margin

    wrist = _lm_xy(landmarks, cfg.WRIST)
    mid_mcp = _lm_xy(landmarks, cfg.MIDDLE_MCP)
    palm = (wrist + mid_mcp) / 2.0
    thumb_tip = _lm_xy(landmarks, cfg.THUMB_TIP)
    thumb_ip = _lm_xy(landmarks, cfg.THUMB_IP)
    thumb_extended = (
        np.linalg.norm(thumb_tip - palm)
        > np.linalg.norm(thumb_ip - palm) + cfg.THUMB_EXTENDED_MARGIN * size
    )

    return FingerState(
        thumb=bool(thumb_extended),
        index=bool(tip_above_pip(cfg.INDEX_TIP, cfg.INDEX_PIP)),
        middle=bool(tip_above_pip(cfg.MIDDLE_TIP, cfg.MIDDLE_PIP)),
        ring=bool(tip_above_pip(cfg.RING_TIP, cfg.RING_PIP)),
        pinky=bool(tip_above_pip(cfg.PINKY_TIP, cfg.PINKY_PIP)),
    )


def pinch_ratios(landmarks: Sequence, size: float) -> PinchRatios:
    thumb = _lm_xy(landmarks, cfg.THUMB_TIP)
    return PinchRatios(
        index=float(np.linalg.norm(thumb - _lm_xy(landmarks, cfg.INDEX_TIP)) / size),
        middle=float(np.linalg.norm(thumb - _lm_xy(landmarks, cfg.MIDDLE_TIP)) / size),
    )


def is_scroll_pose(fingers: FingerState) -> bool:
    """Index + middle up, pinky curled. Ring is ignored: keeping ring curled
    while index+middle are extended is hard on low-quality cameras, which made
    scroll unreliable. Closed fist is checked separately and wins anyway."""
    return fingers.index and fingers.middle and (not fingers.pinky)


def is_closed_fist(fingers: FingerState) -> bool:
    """Index-pinky all curled = clutch / release pose.

    Thumb may be tucked or lightly out; resting comfort matters more than a
    perfect boxing fist.
    """
    return (
        (not fingers.index)
        and (not fingers.middle)
        and (not fingers.ring)
        and (not fingers.pinky)
    )


class GestureDetector:
    """Stateful detector: pinch hysteresis, fist/scroll confirm, priority."""

    # Prefer index (left click) over middle (right) when both close.
    PINCH_PRIORITY: Tuple[str, ...] = ("index", "middle")

    def __init__(self) -> None:
        self._active: Optional[str] = None
        self._scroll_streak = 0
        self._fist_streak = 0
        self._dragging = False
        self._pinch_rearm = False
        self._anchor = AnchorFilter()
        self._size_ema: Optional[float] = None

    def reset(self) -> None:
        self._active = None
        self._scroll_streak = 0
        self._fist_streak = 0
        self._dragging = False
        self._pinch_rearm = False
        self._anchor.reset()
        self._size_ema = None

    def set_dragging(self, dragging: bool) -> None:
        """Allow main loop to widen pinch-off tolerance while dragging."""
        self._dragging = bool(dragging)

    def update(self, landmarks: Sequence) -> GestureFrame:
        size = hand_size(landmarks)
        if self._size_ema is None:
            self._size_ema = size
        else:
            self._size_ema += cfg.HAND_SIZE_EMA * (size - self._size_ema)
        dscale = depth_scale_from_hand_size(size)
        fingers = fingers_up(landmarks, size)
        pinches = pinch_ratios(landmarks, size)

        raw_scroll = is_scroll_pose(fingers)
        raw_fist = is_closed_fist(fingers)

        # Temporal confirm for scroll / fist (avoid single-frame flicker).
        if raw_scroll and not raw_fist:
            self._scroll_streak += 1
        else:
            self._scroll_streak = 0
        scroll_pose = self._scroll_streak >= cfg.SCROLL_CONFIRM_FRAMES

        if raw_fist and not raw_scroll:
            self._fist_streak += 1
        else:
            self._fist_streak = 0
        closed_fist = self._fist_streak >= cfg.FIST_CONFIRM_FRAMES

        # Fist and confirmed scroll suppress pinches. After suppression, wait
        # for one fully-open frame before allowing a NEW pinch to engage, so
        # the thumb sweeping past the middle finger on fist->point cannot
        # register as a phantom right-click.
        if closed_fist or scroll_pose:
            self._active = None
            self._pinch_rearm = True
            active = None
        else:
            active = self._update_pinch(pinches)

        ax, ay = palm_anchor(landmarks)
        motion_anchor = self._anchor.update(ax, ay)

        return GestureFrame(
            fingers=fingers,
            pinches=pinches,
            hand_size=size,
            hand_size_smooth=self._size_ema,
            depth_scale=dscale,
            motion_anchor=motion_anchor,
            scroll_pose=scroll_pose,
            closed_fist=closed_fist,
            active_pinch=active,
        )

    def _update_pinch(self, pinches: PinchRatios) -> Optional[str]:
        ratios = {
            "index": pinches.index,
            "middle": pinches.middle,
        }
        off = cfg.DRAG_PINCH_OFF_RATIO if self._dragging else cfg.PINCH_OFF_RATIO

        if self._active is not None:
            if ratios[self._active] > off:
                self._active = None
            return self._active

        if self._pinch_rearm:
            # Require all ratios clearly open before re-arming pinch engage.
            if all(r > off for r in ratios.values()):
                self._pinch_rearm = False
            else:
                return None

        candidates: List[Tuple[str, float]] = [
            (name, ratios[name])
            for name in self.PINCH_PRIORITY
            if ratios[name] < cfg.PINCH_ON_RATIO
        ]
        if not candidates:
            return None
        # Prefer strongest (smallest ratio); index wins ties via priority order.
        candidates.sort(key=lambda t: (t[1], self.PINCH_PRIORITY.index(t[0])))
        self._active = candidates[0][0]
        return self._active
