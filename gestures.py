"""Finger-up, pinch, fist, scroll-state and speed-gear detection from landmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Sequence, Tuple

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
    SHORTCUT = auto()
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
    pinky: float = 1.0

    def as_dict(self) -> dict:
        return {
            "idx": self.index,
            "mid": self.middle,
            "pky": self.pinky,
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
    # Cursor speed gear (EMA-smoothed finger count).
    gear: float = 1.0
    scroll_pose: bool = False
    closed_fist: bool = False
    # "index" (left) | "index_middle" (right) | "middle" (right)
    # | "pinky" (shortcut) | None
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
        pinky=float(np.linalg.norm(thumb - _lm_xy(landmarks, cfg.PINKY_TIP)) / size),
    )


def is_scroll_pose(fingers: FingerState, pinches: PinchRatios) -> bool:
    """Strict V-sign: index+middle up, ring+pinky curled, thumb tucked AWAY
    from the pinky (thumb-to-pinky is the shortcut gesture).

    Strict on purpose: "pinky down" is the slow cursor gear and "pinky+ring
    down" is the precision gear, so only the tucked thumb separates the
    scroll pose from the precision gears.
    """
    return (
        fingers.index
        and fingers.middle
        and (not fingers.ring)
        and (not fingers.pinky)
        and (not fingers.thumb)
        and pinches.pinky > cfg.PINKY_PINCH_ON_RATIO
    )


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


def _gear_target(fingers: FingerState) -> float:
    """Cursor speed gear from extended-finger count (index/middle/ring/pinky).

    4 up = open hand = fast, 3 up = pinky down = slow, 2 or fewer = precision.
    The thumb is not counted (unreliable on front-facing cameras).
    """
    up = sum((fingers.index, fingers.middle, fingers.ring, fingers.pinky))
    if up >= 4:
        return cfg.GEAR_FULL
    if up == 3:
        return cfg.GEAR_FOUR
    return cfg.GEAR_THREE


class GestureDetector:
    """Stateful detector: pinch hysteresis + 4-way classification, fist/scroll
    confirm with sticky scroll, and the EMA-smoothed speed gear."""

    def __init__(self) -> None:
        self._active: Optional[str] = None
        self._scroll_on = False
        self._scroll_streak = 0
        self._scroll_exit = 0
        self._fist_streak = 0
        self._dragging = False
        self._pinch_rearm = False
        self._anchor = AnchorFilter()
        self._size_ema: Optional[float] = None
        self._gear: Optional[float] = None

    def reset(self) -> None:
        self._active = None
        self._scroll_on = False
        self._scroll_streak = 0
        self._scroll_exit = 0
        self._fist_streak = 0
        self._dragging = False
        self._pinch_rearm = False
        self._anchor.reset()
        self._size_ema = None
        self._gear = None

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

        # EMA-smoothed speed gear (finger flicker never jerks the speed).
        target_gear = _gear_target(fingers)
        if self._gear is None:
            self._gear = target_gear
        else:
            self._gear += cfg.GEAR_EMA * (target_gear - self._gear)

        raw_scroll = is_scroll_pose(fingers, pinches)
        raw_fist = is_closed_fist(fingers)

        # Scroll: confirm to engage, sticky for SCROLL_EXIT_FRAMES to release,
        # so pose flicker while the hand moves never interrupts scrolling.
        if not self._scroll_on:
            if raw_scroll and not raw_fist:
                self._scroll_streak += 1
            else:
                self._scroll_streak = 0
            scroll_pose = self._scroll_streak >= cfg.SCROLL_CONFIRM_FRAMES
            if scroll_pose:
                self._scroll_on = True
                self._scroll_exit = 0
        else:
            if raw_scroll and not raw_fist:
                self._scroll_exit = 0
            else:
                self._scroll_exit += 1
            scroll_pose = self._scroll_exit < cfg.SCROLL_EXIT_FRAMES
            if not scroll_pose:
                self._scroll_on = False
                self._scroll_streak = 0

        # Temporal confirm for the fist (avoid single-frame flicker).
        if raw_fist and not raw_scroll:
            self._fist_streak += 1
        else:
            self._fist_streak = 0
        closed_fist = self._fist_streak >= cfg.FIST_CONFIRM_FRAMES

        # Fist and confirmed scroll suppress pinches. After suppression, wait
        # for all ratios clearly open before allowing a NEW pinch to engage,
        # so the thumb sweeping past fingers on fist->point cannot register as
        # a phantom click.
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
            gear=self._gear,
            scroll_pose=scroll_pose,
            closed_fist=closed_fist,
            active_pinch=active,
        )

    def _update_pinch(self, pinches: PinchRatios) -> Optional[str]:
        """Classify the pinch ONCE at engage; the class is latched until the
        hand clearly opens. Priority:
          index+middle both -> right click (easy: no need to keep the index
                              away from the thumb -- that was the hard part)
          pinky             -> shortcut combo
          index only        -> left click / double / drag
          middle only       -> right click (single-finger variant)
        """
        idx, mid, pky = pinches.index, pinches.middle, pinches.pinky

        if self._active is not None:
            off = cfg.DRAG_PINCH_OFF_RATIO if self._dragging else cfg.PINCH_OFF_RATIO
            if self._active == "index":
                if idx > off:
                    self._active = None
            elif self._active in ("index_middle", "middle"):
                # The combined pinch ends only when BOTH fingers open.
                if idx > cfg.PINCH_OFF_RATIO and mid > cfg.PINCH_OFF_RATIO:
                    self._active = None
            elif self._active == "pinky":
                if pky > cfg.PINKY_PINCH_OFF_RATIO:
                    self._active = None
            return self._active

        if self._pinch_rearm:
            if (
                idx > cfg.PINCH_OFF_RATIO
                and mid > cfg.PINCH_OFF_RATIO
                and pky > cfg.PINKY_PINCH_OFF_RATIO
            ):
                self._pinch_rearm = False
            else:
                return None

        idx_on = idx < cfg.PINCH_ON_RATIO
        mid_on = mid < cfg.PINCH_ON_RATIO
        pky_on = pky < cfg.PINKY_PINCH_ON_RATIO

        if idx_on and mid_on:
            self._active = "index_middle"
        elif pky_on:
            self._active = "pinky"
        elif idx_on:
            self._active = "index"
        elif mid_on:
            self._active = "middle"
        return self._active
