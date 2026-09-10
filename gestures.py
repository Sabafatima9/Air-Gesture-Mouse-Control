"""Finger-up, pinch, and scroll-state detection from MediaPipe hand landmarks."""

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
    MIDDLE_CLICK = auto()
    DOUBLE_CLICK = auto()
    DRAG = auto()
    SCROLL = auto()


@dataclass
class FingerState:
    """Which fingers are extended (True) vs curled (False)."""

    thumb: bool = False
    index: bool = False
    middle: bool = False
    ring: bool = False
    pinky: bool = False

    def count_up(self) -> int:
        return sum(
            (self.thumb, self.index, self.middle, self.ring, self.pinky)
        )

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
    ring: float = 1.0

    def as_dict(self) -> dict:
        return {
            "idx": self.index,
            "mid": self.middle,
            "rng": self.ring,
        }


@dataclass
class GestureFrame:
    """Per-frame gesture snapshot derived from landmarks."""

    fingers: FingerState = field(default_factory=FingerState)
    pinches: PinchRatios = field(default_factory=PinchRatios)
    hand_size: float = 1.0
    # Depth scale vs REFERENCE_HAND_SIZE (>1 when farther / smaller silhouette).
    depth_scale: float = 1.0
    index_tip_norm: Tuple[float, float] = (0.5, 0.5)
    # Depth-compensated tip used for cursor mapping (still 0..1 frame space).
    cursor_norm: Tuple[float, float] = (0.5, 0.5)
    scroll_anchor_norm: Tuple[float, float] = (0.5, 0.5)
    # True when index+middle extended and ring+pinky curled (scroll pose).
    scroll_pose: bool = False
    # Which pinch is currently "on" (hysteresis applied externally via detector).
    active_pinch: Optional[str] = None  # "index" | "middle" | "ring" | None


def _lm_xy(landmarks: Sequence, idx: int) -> np.ndarray:
    lm = landmarks[idx]
    return np.array([lm.x, lm.y], dtype=np.float64)


def _lm_xyz(landmarks: Sequence, idx: int) -> np.ndarray:
    lm = landmarks[idx]
    z = getattr(lm, "z", 0.0)
    return np.array([lm.x, lm.y, float(z)], dtype=np.float64)


def hand_size(landmarks: Sequence) -> float:
    """Wrist → middle MCP distance in normalized image coords (depth proxy)."""
    a = _lm_xy(landmarks, cfg.HAND_SIZE_A)
    b = _lm_xy(landmarks, cfg.HAND_SIZE_B)
    size = float(np.linalg.norm(a - b))
    return max(size, 1e-6)


def depth_scale_from_hand_size(size: float) -> float:
    """Amplify tip deviation from frame center when the hand is farther (smaller)."""
    raw = cfg.REFERENCE_HAND_SIZE / max(size, 1e-6)
    return float(np.clip(raw, cfg.DEPTH_SCALE_MIN, cfg.DEPTH_SCALE_MAX))


def depth_compensate_norm(
    norm_x: float,
    norm_y: float,
    scale: float,
) -> Tuple[float, float]:
    """
    Expand/contract tip position around frame center by depth scale so near/far
    hand motion maps to a similar usable screen region.
    """
    cx, cy = 0.5, 0.5
    x = cx + (norm_x - cx) * scale
    y = cy + (norm_y - cy) * scale
    return float(x), float(y)


def fingers_up(landmarks: Sequence, size: float) -> FingerState:
    """Heuristic finger-up detection using landmark ratios (distance-invariant).

    Soft image-space checks only — no hard palm-facing / yaw / pitch gate.
    """
    margin = cfg.FINGER_UP_MARGIN * size

    def tip_above_pip(tip_i: int, pip_i: int) -> bool:
        # Image y grows downward; "up" means tip.y < pip.y - margin.
        tip = _lm_xy(landmarks, tip_i)
        pip = _lm_xy(landmarks, pip_i)
        return tip[1] < pip[1] - margin

    # Thumb: extended if tip is farther from palm center (wrist→middle MCP mid)
    # than IP joint (works for mirrored selfie view and mild angle changes).
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
        ring=float(np.linalg.norm(thumb - _lm_xy(landmarks, cfg.RING_TIP)) / size),
    )


def is_scroll_pose(fingers: FingerState) -> bool:
    """Index + middle up, ring + pinky down. Thumb may be either."""
    return (
        fingers.index
        and fingers.middle
        and (not fingers.ring)
        and (not fingers.pinky)
    )


class GestureDetector:
    """Stateful detector: pinch hysteresis, priority, and scroll pose."""

    # Priority when multiple pinches could fire (exclusive).
    PINCH_PRIORITY: Tuple[str, ...] = ("ring", "middle", "index")

    def __init__(self) -> None:
        self._active: Optional[str] = None  # which pinch is latched on

    def reset(self) -> None:
        self._active = None

    def update(self, landmarks: Sequence) -> GestureFrame:
        size = hand_size(landmarks)
        dscale = depth_scale_from_hand_size(size)
        fingers = fingers_up(landmarks, size)
        pinches = pinch_ratios(landmarks, size)
        scroll_pose = is_scroll_pose(fingers)

        # Scroll pose suppresses pinch clicks (finger tips are apart by design).
        if scroll_pose:
            self._active = None
            active = None
        else:
            active = self._update_pinch(pinches)

        index_tip = _lm_xy(landmarks, cfg.INDEX_TIP)
        mid_tip = _lm_xy(landmarks, cfg.MIDDLE_TIP)
        scroll_anchor = (index_tip + mid_tip) / 2.0
        tip_x, tip_y = float(index_tip[0]), float(index_tip[1])
        cursor = depth_compensate_norm(tip_x, tip_y, dscale)

        return GestureFrame(
            fingers=fingers,
            pinches=pinches,
            hand_size=size,
            depth_scale=dscale,
            index_tip_norm=(tip_x, tip_y),
            cursor_norm=cursor,
            scroll_anchor_norm=(float(scroll_anchor[0]), float(scroll_anchor[1])),
            scroll_pose=scroll_pose,
            active_pinch=active,
        )

    def _update_pinch(self, pinches: PinchRatios) -> Optional[str]:
        ratios = {
            "index": pinches.index,
            "middle": pinches.middle,
            "ring": pinches.ring,
        }

        if self._active is not None:
            # Stay latched until that pinch releases past OFF threshold.
            if ratios[self._active] > cfg.PINCH_OFF_RATIO:
                self._active = None
            return self._active

        # Engage the highest-priority pinch that is below ON threshold.
        # Prefer the closest finger if several are below threshold.
        candidates: List[Tuple[str, float]] = [
            (name, ratios[name])
            for name in self.PINCH_PRIORITY
            if ratios[name] < cfg.PINCH_ON_RATIO
        ]
        if not candidates:
            return None
        # Among candidates, pick smallest ratio (strongest pinch); then priority.
        candidates.sort(key=lambda t: (t[1], self.PINCH_PRIORITY.index(t[0])))
        self._active = candidates[0][0]
        return self._active


def map_to_screen(
    norm_x: float,
    norm_y: float,
    screen_w: int,
    screen_h: int,
    margin: float = cfg.FRAME_MARGIN,
) -> Tuple[float, float]:
    """Map normalized frame coords (0..1) to screen pixels with edge margins."""
    # After horizontal flip, x=0 is left of mirrored preview (= user's left).
    m = margin
    # Clamp into the usable inner region, then stretch to full screen.
    x = (norm_x - m) / max(1e-6, (1.0 - 2.0 * m))
    y = (norm_y - m) / max(1e-6, (1.0 - 2.0 * m))
    x = float(np.clip(x, 0.0, 1.0))
    y = float(np.clip(y, 0.0, 1.0))
    return x * screen_w, y * screen_h

