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


Please simplify the gesture system and also prioritize **smooth, comfortable, and responsive performance**. The application should feel natural enough that a user can comfortably work with it for an extended period without frustration or hand fatigue.

### Simplified Gesture Design

**1. Cursor Movement**

* Use the **index finger tip** to control the cursor.
* When the index finger is pointing/up, its position should control the cursor.
* Apply good cursor smoothing to eliminate shaking/jitter.
* Cursor movement should be responsive but not overly sensitive.
* The user should be able to move the cursor slowly for precision and quickly for larger movements.
* Use appropriate coordinate mapping and, if useful, depth compensation to make movement feel natural.

**2. Left Click**

* Use a simple **thumb + index finger pinch**.
* A quick pinch and release = one left click.
* Make the pinch detection forgiving and reliable.
* The user should not need to make an exaggerated or perfectly precise pinch.

**3. Double Click**

* DO NOT require a special double-click gesture.
* Two normal thumb + index pinches performed quickly should be interpreted as a double click.
* The user should be able to double-click naturally without struggling to perform two perfect pinches.
* Use appropriate timing/debounce logic to distinguish:

  * One pinch → single click
  * Two quick pinches → double click

**4. Drag**

* Keep drag simple:

  * Thumb + index pinch
  * Hold the pinch for approximately **0.45–0.5 seconds**
  * Enter drag mode
  * Move the hand while maintaining the pinch → drag
  * Release the pinch → drop
* A normal quick pinch must remain a click and should not accidentally trigger drag.
* Add appropriate tolerance so small finger movements during dragging do not cause the drag to break.

**5. Closed Fist = Safe / No Action**

* When the user's hand forms a **closed fist**, perform **NO mouse action**.
* Do not move the cursor.
* Do not click.
* Do not drag.
* Do not scroll.
* Treat the closed fist as a neutral/safe/resting state.
* This should allow the user to comfortably rest their hand without accidental actions.

**6. Scrolling**

* Use a simple two-finger gesture:

  * Index + middle fingers up
  * Ring + pinky curled
* Move hand upward → scroll up.
* Move hand downward → scroll down.
* Scrolling should only activate when the gesture is clearly detected.
* Do not accidentally trigger scrolling during normal cursor movement.

**7. Right Click — Optional**

* If implemented, use **thumb + middle finger pinch** for right click.
* Ensure it does not interfere with thumb + index left click.
* If reliability becomes an issue, prioritize the core gestures instead of making the system unnecessarily complicated.

---

# VERY IMPORTANT: Smooth & Comfortable User Experience

The application must run **very smoothly in real time**.

The objective is not just to make the gestures technically work — the application should feel **comfortable, stable, responsive, and natural for the user**.

Please optimize for:

### Performance

* Maintain a high and stable webcam processing FPS.
* Avoid unnecessary processing inside the main loop.
* Keep CPU usage reasonable.
* Avoid memory leaks.
* Avoid unnecessary delays or blocking operations.
* Make mouse control responsive with minimal latency.
* Process frames efficiently.

### Cursor Smoothness

* Implement an appropriate smoothing/filtering technique for cursor movement.
* Prevent visible cursor shaking caused by small landmark movements.
* Do not over-smooth the cursor because excessive smoothing creates noticeable lag.
* Find a good balance between **stability and responsiveness**.
* The cursor should follow the user's finger naturally.

### Gesture Stability

* Do not trigger gestures from a single noisy frame.
* Use appropriate thresholds, state tracking, and temporal consistency.
* Avoid accidental clicks caused by small movements.
* Avoid repeated clicks while a pinch is being held.
* Avoid accidental transitions between click, drag, scroll, and movement.
* Gesture states should transition smoothly.

### User Comfort

The user should be able to use the application **without constantly holding their hand in an uncomfortable position**.

* Do not require exaggerated finger movements.
* Do not require extreme pinching.
* Keep gesture thresholds tolerant.
* Allow the hand to rest in the neutral/closed-fist state.
* Avoid requiring the user to keep their fingers perfectly positioned at all times.
* Make cursor movement usable for both small precise movements and larger movements.
* Minimize false detections and accidental mouse actions.

### Camera & Tracking

* Handle temporary hand-tracking loss gracefully.
* If the hand disappears for a short time, do not perform unexpected mouse actions.
* If no hand is detected, safely pause mouse control.
* Handle different lighting conditions as reasonably as possible.
* Keep tracking stable when the hand moves at different speeds.

### Clear Visual Feedback

Display useful information on the webcam window, for example:

* `Hand Detected`
* `Cursor Active`
* `LEFT CLICK`
* `DOUBLE CLICK`
* `DRAGGING`
* `SCROLL`
* `SAFE / NO ACTION`
* `No Hand Detected`

Keep the visual interface simple and non-distracting.

---

# Gesture Priority

Prioritize reliability in this order:

1. ☝️ **Index → Cursor movement**
2. 👌 **Thumb + Index pinch → Left click**
3. 👌 **Two quick pinches → Double click**
4. 👌 **Pinch + hold → Drag**
5. ✊ **Closed fist → Safe / No action**
6. ✌️ **Two fingers → Scroll**
7. 🤏 **Right click (optional)**

If two gestures conflict, **prioritize the simpler and more reliable gesture** rather than adding complicated detection rules.

---

# Testing & Optimization — 

Do not just generate the code and assume it works.

After implementation:

1. Install all dependencies.
2. Run the application using a real webcam.
3. Verify hand tracking.
4. Test cursor movement.
5. Test single click.
6. Test double click.
7. Test drag and drop.
8. Test closed fist as the safe/no-action state.
9. Test scrolling.
10. Test optional right click.
11. Test switching between gestures.
12. Check for accidental clicks.
13. Check for accidental dragging.
14. Check for cursor jitter.
15. Check for noticeable input latency.
16. Check CPU/memory usage and optimize if necessary.
17. Test the application continuously for several minutes to identify stability issues.
18. Fix any errors, crashes, lag, jitter, false gestures, or performance problems.
19. Run the tests again after making fixes.

### Definition of Done

The project is complete only when it is:

**Working + Smooth + Responsive + Stable + Comfortable + Tested**

The user should be able to sit comfortably in front of the webcam and control the mouse naturally without constantly fighting the gesture system.

Do not sacrifice usability just to add more gestures. **A small number of reliable and smooth gestures is better than many complicated gestures.**

