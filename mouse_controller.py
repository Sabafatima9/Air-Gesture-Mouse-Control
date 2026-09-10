"""Cross-platform mouse actions via pyautogui.

Works on Linux, macOS, and Windows. No OS-specific APIs are used.

Linux extras (install as needed for your desktop):
  - python3-tk / python3-dev (Tk for some pyautogui backends)
  - scrot or gnome-screenshot (screenshots; not required for mouse control)
  - python3-xlib (X11); Wayland may need extra permissions or XWayland

macOS: grant Camera + Accessibility (mouse control) to the Terminal/Python
app in System Settings → Privacy & Security.

Windows: usually works out of the box after pip install.

FAILSAFE: moving the cursor into the extreme top-left corner raises
FailSafeException and stops the script — intentional emergency stop.
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
        self._dragging = False

    @property
    def dragging(self) -> bool:
        return self._dragging

    def reset_smoothing(self) -> None:
        self._smoothed = None

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

        Fast hand motion → less smoothing (responsive); slow motion → more
        smoothing (stable). Avoids the laggy feel of a high fixed SMOOTHING.
        """
        if self._smoothed is None:
            self._smoothed = (target_x, target_y)
        else:
            sx, sy = self._smoothed
            dist = math.hypot(target_x - sx, target_y - sy)
            # Blend base ↔ fast smoothing by how far the target jumped this frame.
            t = min(1.0, dist / max(cfg.SMOOTHING_VELOCITY_REF, 1e-6))
            smooth = cfg.SMOOTHING + (cfg.SMOOTHING_FAST - cfg.SMOOTHING) * t
            alpha = 1.0 - smooth  # higher smooth → smaller alpha
            sx += (target_x - sx) * alpha
            sy += (target_y - sy) * alpha
            self._smoothed = (sx, sy)

        x, y = self._smoothed
        # Keep slightly inside screen edges so FAILSAFE corner is not hit by jitter.
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

    def middle_click(self) -> None:
        pyautogui.click(button="middle")

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

    def scroll(self, ticks: int) -> None:
        """Scroll vertically. Positive ticks = scroll up."""
        if ticks == 0:
            return
        # pyautogui.scroll: positive = up on Windows/macOS; Linux may invert
        # depending on desktop — amount is configurable in config.SCROLL_AMOUNT.
        pyautogui.scroll(int(ticks) * cfg.SCROLL_AMOUNT)

    def platform_hint(self) -> str:
        return sys.platform
