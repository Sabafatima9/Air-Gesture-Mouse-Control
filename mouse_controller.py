"""Cross-platform mouse actions via pyautogui.

Works on Linux, macOS, and Windows. No OS-specific APIs are used.

Linux extras (install as needed for your desktop):
  - python3-tk / python3-dev (Tk for some pyautogui backends)
  - scrot or gnome-screenshot (screenshots; not required for mouse control)
  - python3-xlib (X11); Wayland may need extra permissions or XWayland

macOS: grant Camera + Accessibility (mouse control) to the Terminal/Python
app in System Settings -> Privacy & Security.

Windows: usually works out of the box after pip install.

FAILSAFE: moving the cursor into the extreme top-left corner raises
FailSafeException and stops the script -- intentional emergency stop.
"""

from __future__ import annotations

import math
import sys
from typing import Optional, Tuple

import pyautogui

import config as cfg


class MouseController:
    """Thin wrapper around pyautogui with adaptive smoothing helpers."""

    def __init__(self) -> None:
        pyautogui.FAILSAFE = cfg.FAILSAFE
        pyautogui.PAUSE = cfg.PAUSE
        self.screen_w, self.screen_h = pyautogui.size()
        self._smoothed: Optional[Tuple[float, float]] = None
        self._residual: Tuple[float, float] = (0.0, 0.0)
        self._scroll_carry = 0.0
        self._dragging = False

    @property
    def dragging(self) -> bool:
        return self._dragging

    def reset_smoothing(self) -> None:
        self._smoothed = None
        self._residual = (0.0, 0.0)

    def hold_smoothed_position(self) -> Optional[Tuple[float, float]]:
        """Re-apply last smoothed cursor without advancing (tracking-hold grace)."""
        if self._smoothed is None:
            return None
        x, y = self._smoothed
        x = max(1.0, min(float(self.screen_w - 2), x))
        y = max(1.0, min(float(self.screen_h - 2), y))
        try:
            pyautogui.moveTo(x, y, _pause=False)
        except pyautogui.FailSafeException:
            raise
        return x, y

    def move_to_smoothed(self, target_x: float, target_y: float) -> Tuple[float, float]:
        """Move cursor toward target with velocity-adaptive exponential smoothing.

        Fast hand motion -> less smoothing (responsive); slow motion -> more
        smoothing (stable). Sub-pixel deadzone skips tiny jitter moves.
        """
        if self._smoothed is None:
            self._smoothed = (target_x, target_y)
            self._residual = (0.0, 0.0)
        else:
            sx, sy = self._smoothed
            rx, ry = self._residual
            dx = target_x - sx + rx
            dy = target_y - sy + ry
            dist = math.hypot(dx, dy)
            if dist < cfg.CURSOR_DEADZONE_PX:
                # Accumulate tiny motions so slow precise aiming does not drift.
                self._residual = (dx, dy)
                x = max(1.0, min(float(self.screen_w - 2), sx))
                y = max(1.0, min(float(self.screen_h - 2), sy))
                return x, y
            self._residual = (0.0, 0.0)
            t = min(1.0, dist / max(cfg.SMOOTHING_VELOCITY_REF, 1e-6))
            smooth = cfg.SMOOTHING + (cfg.SMOOTHING_FAST - cfg.SMOOTHING) * t
            alpha = 1.0 - smooth
            sx += dx * alpha
            sy += dy * alpha
            self._smoothed = (sx, sy)

        x, y = self._smoothed
        x = max(1.0, min(float(self.screen_w - 2), x))
        y = max(1.0, min(float(self.screen_h - 2), y))
        try:
            pyautogui.moveTo(x, y, _pause=False)
        except pyautogui.FailSafeException:
            raise
        return x, y

    def left_click(self) -> None:
        pyautogui.click(button="left")

    def right_click(self) -> None:
        pyautogui.click(button="right")

    def double_click(self) -> None:
        pyautogui.doubleClick(button="left")

    def mouse_down(self) -> None:
        if not self._dragging:
            pyautogui.mouseDown(button="left")
            self._dragging = True

    def mouse_up(self) -> None:
        if self._dragging:
            pyautogui.mouseUp(button="left")
            self._dragging = False

    def ensure_released(self) -> None:
        """Release any held drag (e.g. hand lost past hold grace)."""
        self.mouse_up()

    def scroll(self, amount: float) -> None:
        """Scroll vertically in wheel notches. Positive = up.

        Fractional notches accumulate so slow scrolling is smooth, not lossy.

        Windows quirk: pyautogui passes the value straight into mouse_event's
        wheel dwData, which Windows counts in DETENTS (WHEEL_DELTA = 120 per
        notch). pyautogui.scroll(1) therefore scrolls only 1/120 of a notch --
        effectively nothing. Convert notches -> detents on win32; Linux/macOS
        expect notches directly.
        """
        self._scroll_carry += float(amount)
        notches = int(self._scroll_carry)
        if notches == 0:
            return
        self._scroll_carry -= notches
        if sys.platform == "win32":
            pyautogui.scroll(notches * cfg.WHEEL_DELTA)
        else:
            pyautogui.scroll(notches)

    def move_by(self, dx: float, dy: float) -> Tuple[float, float]:
        """Relative move: shift the smoothed cursor target by (dx, dy) px."""
        if self._smoothed is None:
            self._smoothed = (
                float(self.screen_w) / 2.0,
                float(self.screen_h) / 2.0,
            )
        sx, sy = self._smoothed
        return self.move_to_smoothed(sx + dx, sy + dy)

    @property
    def smoothed(self) -> Optional[Tuple[float, float]]:
        return self._smoothed

    def platform_hint(self) -> str:
        return sys.platform
