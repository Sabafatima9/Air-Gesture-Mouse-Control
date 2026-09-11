"""Offline tests for the gesture -> mouse state machine (no camera, no mouse).

Synthetic MediaPipe-style landmarks drive GestureDetector + process_actions with
a MockMouse, so every rule of the interaction model is verified deterministically:

  - cursor motion is RELATIVE to palm motion, position-in-frame independent
  - cursor keeps following the hand while a pinch is held (aiming)
  - left click fires on pinch RELEASE (double click on two quick pinches)
  - right click fires on pinch RELEASE (not on engage)
  - closed fist = clutch: motion blocked, no jump on reopen
  - scroll: palm-driven, right direction, decent speed, survives pose flicker
  - tracking glitches never jump the cursor

Run with the project venv from the repo root:

    venv\\Scripts\\python.exe tests\\test_logic.py
"""

from __future__ import annotations

import platform
import sys
import types as pytypes
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pyautogui  # noqa: E402

import config as cfg  # noqa: E402
from gestures import GestureDetector  # noqa: E402
from main import ActionState, process_actions  # noqa: E402
from mouse_controller import MouseController  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic hand (normalized image coords, right hand, palm to camera)
# ---------------------------------------------------------------------------
OPEN_HAND = {
    0: (0.50, 0.70),
    1: (0.455, 0.675), 2: (0.400, 0.635), 3: (0.375, 0.590), 4: (0.370, 0.545),
    5: (0.435, 0.545), 6: (0.435, 0.455), 7: (0.435, 0.375), 8: (0.435, 0.300),
    9: (0.500, 0.540), 10: (0.500, 0.450), 11: (0.500, 0.370), 12: (0.500, 0.295),
    13: (0.565, 0.545), 14: (0.565, 0.455), 15: (0.565, 0.380), 16: (0.565, 0.305),
    17: (0.625, 0.560), 18: (0.625, 0.475), 19: (0.625, 0.400), 20: (0.625, 0.330),
}

_MCP = {"index": 5, "middle": 9, "ring": 13, "pinky": 17}


def _curl(pts: dict, finger: str) -> None:
    m = _MCP[finger]
    x, y = pts[m]
    pts[m + 1] = (x, y - 0.02)   # PIP
    pts[m + 2] = (x, y + 0.02)    # DIP
    pts[m + 3] = (x, y + 0.07)    # TIP below PIP -> reads as curled


def make_hand(*, pose: str = "open", pinch: str = "", dx: float = 0.0, dy: float = 0.0) -> dict:
    pts = dict(OPEN_HAND)
    if pose == "fist":
        for f in ("index", "middle", "ring", "pinky"):
            _curl(pts, f)
        pts[4] = (0.47, 0.63)     # thumb tucked near the palm
    elif pose == "scroll":
        for f in ("ring", "pinky"):
            _curl(pts, f)
    if pinch == "index":
        pts[4] = (pts[8][0], pts[8][1] + 0.002)
    elif pinch == "middle":
        pts[4] = (pts[12][0], pts[12][1] + 0.002)
    return {i: (x + dx, y + dy) for i, (x, y) in pts.items()}


def to_landmarks(pts: dict):
    return [pytypes.SimpleNamespace(x=x, y=y, z=0.0) for x, y in pts.values()]


class MockMouse(MouseController):
    """Records instead of touching the real mouse."""

    def __init__(self):
        self.screen_w = 1920
        self.screen_h = 1080
        self.moves = []
        self.actions = []
        self._down = False

    def move_by(self, dx, dy):
        self.moves.append((dx, dy))
        return 0.0, 0.0

    def left_click(self):
        self.actions.append("left")

    def right_click(self):
        self.actions.append("right")

    def double_click(self):
        self.actions.append("double")

    def mouse_down(self):
        self._down = True
        self.actions.append("down")

    def mouse_up(self):
        if self._down:
            self._down = False
            self.actions.append("up")

    def ensure_released(self):
        self.mouse_up()

    def scroll(self, amount):
        if amount:
            self.actions.append(("scroll", int(amount)))


class Harness:
    def __init__(self):
        self.detector = GestureDetector()
        self.state = ActionState()
        self.mouse = MockMouse()
        self.t = 10.0

    def feed(self, pts, dt=1.0 / 30.0):
        gframe = self.detector.update(to_landmarks(pts))
        mode = process_actions(gframe, self.state, self.mouse, self.detector, self.t)
        self.t += dt
        return mode

    def total_dx(self):
        return sum(m[0] for m in self.mouse.moves)

    def scrolls(self):
        return [a[1] for a in self.mouse.actions if isinstance(a, tuple) and a[0] == "scroll"]


SETTLE = 30  # frames for the anchor filter to converge on a still hand


class PoseDetectionTests(unittest.TestCase):
    def test_open_fist_scroll_pinch_poses(self):
        d = GestureDetector()
        g = d.update(to_landmarks(make_hand()))
        self.assertTrue(g.fingers.index and g.fingers.middle and g.fingers.ring and g.fingers.pinky)
        self.assertFalse(g.scroll_pose)
        self.assertFalse(g.closed_fist)
        self.assertIsNone(g.active_pinch)

        d2 = GestureDetector()
        for _ in range(3):
            g = d2.update(to_landmarks(make_hand(pose="fist")))
        self.assertTrue(g.closed_fist)

        d3 = GestureDetector()
        for _ in range(3):
            g = d3.update(to_landmarks(make_hand(pose="scroll")))
        self.assertTrue(g.scroll_pose)

        d4 = GestureDetector()
        g = d4.update(to_landmarks(make_hand(pinch="index")))
        self.assertEqual(g.active_pinch, "index")

        d5 = GestureDetector()
        g = d5.update(to_landmarks(make_hand(pinch="middle")))
        self.assertEqual(g.active_pinch, "middle")


class MotionTests(unittest.TestCase):
    def test_relative_motion_position_independent(self):
        """Same palm sweep from two different positions in frame -> same cursor
        motion. Position in the camera frame must not matter."""
        totals = []
        for base_dx in (0.0, -0.20):
            h = Harness()
            for _ in range(SETTLE):
                h.feed(make_hand(dx=base_dx))
            x = base_dx
            for _ in range(10):
                x += 0.04
                h.feed(make_hand(dx=x))
            totals.append(h.total_dx())
        # ~0.4 sweep * depth gain 1.125 * 1920 * 1.6 ~= 1380 px
        self.assertGreater(totals[0], 900.0)
        self.assertLess(totals[0], 1600.0)
        self.assertAlmostEqual(totals[0], totals[1], delta=abs(totals[0]) * 0.15)

    def test_cursor_follows_while_index_pinch_held(self):
        """Pinching must not freeze or shake the cursor: it keeps following
        the palm, and the RELEASE performs the click."""
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        for _ in range(5):
            h.feed(make_hand(pinch="index"))
        before = len(h.mouse.moves)
        for i in range(10):
            h.feed(make_hand(pinch="index", dx=0.03 * (i + 1)))
        self.assertGreaterEqual(len(h.mouse.moves), before + 6)
        self.assertGreater(h.total_dx(), 500.0)
        # release -> exactly one left click at the aimed position
        for _ in range(SETTLE):
            h.feed(make_hand(dx=0.30))
        self.assertEqual(h.mouse.actions.count("left"), 1)
        self.assertNotIn("double", h.mouse.actions)

    def test_deadzone_residual_accumulates(self):
        """Slow sub-deadzone motion still moves the cursor (accumulates)."""
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        for i in range(20):
            h.feed(make_hand(dx=0.001 * (i + 1)))
        self.assertGreater(h.total_dx(), 20.0)
        self.assertLess(h.total_dx(), 120.0)

    def test_tracking_glitch_does_not_jump_cursor(self):
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        base = len(h.mouse.moves)
        h.feed(make_hand(dx=0.50))          # implausible teleport
        for _ in range(10):
            h.feed(make_hand(dx=0.50))      # stays there, still
        self.assertEqual(len(h.mouse.moves), base)

    def test_fist_clutch(self):
        """Fist = clutch: motion blocked while fisted, no jump on reopen."""
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        base = len(h.mouse.moves)
        for _ in range(4):                  # form the fist (confirm frames)
            h.feed(make_hand(pose="fist"))
        self.assertEqual(len(h.mouse.moves), base)
        for i in range(6):                  # move while fisted
            h.feed(make_hand(pose="fist", dx=0.05 * (i + 1)))
        self.assertEqual(len(h.mouse.moves), base)
        self.assertEqual(h.mouse.actions, [])
        for _ in range(6):                  # hold fist still at the new spot
            h.feed(make_hand(pose="fist", dx=0.30))
        for _ in range(SETTLE):             # reopen the hand, still
            h.feed(make_hand(dx=0.30))
        self.assertEqual(len(h.mouse.moves), base)   # no jump on reopen
        self.assertEqual(h.mouse.actions, [])


class ClickTests(unittest.TestCase):
    def test_left_click_single_and_double(self):
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        for _ in range(4):                  # quick pinch ~0.13 s
            h.feed(make_hand(pinch="index"))
        for _ in range(SETTLE):             # release; window expires -> click
            h.feed(make_hand())
        self.assertEqual(h.mouse.actions.count("left"), 1)
        self.assertNotIn("double", h.mouse.actions)

        h2 = Harness()
        for _ in range(SETTLE):
            h2.feed(make_hand())
        for _ in range(4):
            h2.feed(make_hand(pinch="index"))
        for _ in range(5):
            h2.feed(make_hand())            # short gap
        for _ in range(4):
            h2.feed(make_hand(pinch="index"))
        for _ in range(SETTLE):
            h2.feed(make_hand())
        self.assertIn("double", h2.mouse.actions)
        self.assertNotIn("left", h2.mouse.actions)

    def test_short_pinch_is_noise(self):
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        h.feed(make_hand(pinch="index"))    # 1 frame < PINCH_MIN_HOLD
        for _ in range(SETTLE):
            h.feed(make_hand())
        self.assertNotIn("left", h.mouse.actions)
        self.assertNotIn("double", h.mouse.actions)

    def test_right_click_on_release_not_engage(self):
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        for _ in range(6):                  # hold ~0.2 s
            h.feed(make_hand(pinch="middle"))
        self.assertNotIn("right", h.mouse.actions)   # nothing on engage
        for _ in range(SETTLE):             # release -> right click
            h.feed(make_hand())
        self.assertEqual(h.mouse.actions.count("right"), 1)

    def test_drag(self):
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        for _ in range(16):                 # hold ~0.53 s > DRAG_HOLD_TIME
            h.feed(make_hand(pinch="index"))
        self.assertEqual(h.mouse.actions.count("down"), 1)
        for i in range(8):                  # drag: cursor follows with button held
            h.feed(make_hand(pinch="index", dx=0.02 * (i + 1)))
        self.assertGreater(h.total_dx(), 100.0)
        for _ in range(SETTLE):
            h.feed(make_hand(dx=0.16))       # release -> mouse up, no click
        self.assertIn("up", h.mouse.actions)
        self.assertNotIn("left", h.mouse.actions)
        self.assertNotIn("double", h.mouse.actions)


class ScrollTests(unittest.TestCase):
    def test_scroll_speed_direction_and_flicker_grace(self):
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        for _ in range(3):                   # confirm scroll pose, still hand
            h.feed(make_hand(pose="scroll"))
        self.assertEqual(h.scrolls(), [])
        y = 0.0
        for i in range(10):                 # move hand DOWN 0.02/frame
            y += 0.02
            h.feed(make_hand(pose="scroll", dy=y))
        total = sum(h.scrolls())
        self.assertLess(total, -20)          # clearly scrolling DOWN, useful speed
        self.assertTrue(all(s < 0 for s in h.scrolls()))
        for i in range(5):                   # pose flickers open, hand keeps moving
            y += 0.02
            h.feed(make_hand(dy=y))
        self.assertEqual(sum(h.scrolls()), total)   # no scroll while pose lost
        for i in range(5):                   # pose returns
            y += 0.02
            h.feed(make_hand(pose="scroll", dy=y))
        self.assertLess(sum(h.scrolls()), -40)       # gap motion preserved

    def test_scroll_resets_after_long_gap(self):
        h = Harness()
        for _ in range(SETTLE):
            h.feed(make_hand())
        for _ in range(3):
            h.feed(make_hand(pose="scroll"))
        y = 0.0
        for i in range(5):
            y += 0.02
            h.feed(make_hand(pose="scroll", dy=y))
        partial = sum(h.scrolls())
        for i in range(16):                  # gap longer than grace
            y += 0.02
            h.feed(make_hand(dy=y))
        for i in range(5):                   # pose returns: fresh anchor, no burst
            y += 0.02
            h.feed(make_hand(pose="scroll", dy=y))
        after = sum(h.scrolls()) - partial
        self.assertLess(after, -5)           # keeps scrolling from the return point
        self.assertGreater(after, -30)      # but no giant catch-up burst


class WindowsScrollFixTests(unittest.TestCase):
    def test_scroll_converts_notches_to_detents_on_windows(self):
        """pyautogui on win32 passes raw wheel detents (120 per notch); the
        controller must convert so one notch here is one real wheel notch."""
        real = MouseController.__new__(MouseController)
        real._scroll_carry = 0.0
        sent = []
        orig = pyautogui.scroll
        pyautogui.scroll = lambda n: sent.append(n)
        try:
            real.scroll(2)
            real.scroll(0.6)                # accumulates, sends nothing
            real.scroll(0.6)                # reaches 1.2 -> one more notch
        finally:
            pyautogui.scroll = orig
        if platform.system() == "Windows":
            self.assertEqual(sent, [240, 120])
        else:
            self.assertEqual(sent, [2, 1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
