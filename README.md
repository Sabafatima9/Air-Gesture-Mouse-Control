# Air Gesture Mouse Control

Control your mouse with hand gestures from a **front-facing webcam** (laptop / selfie view).
Built with **OpenCV** + **MediaPipe Hand Landmarker (Tasks API)** + **pyautogui**.

Works on **Linux**, **macOS**, and **Windows**.

**Windows:** double-click **`run.bat`** (uses the project venv, no activation needed).

```bash
pip install -r requirements.txt
python main.py
```

Press **Q** or **Esc** in the camera window to quit.
**Emergency stop:** fling the cursor into the extreme **top-left** corner (pyautogui FAILSAFE).

---

## How gestures work

Preview is **mirrored** so moving your hand left moves the cursor left.
Fingers on the HUD are labeled **TIMRP** = Thumb, Index, Middle, Ring, Pinky (`-` = curled).

| Gesture | Fingers / how | Mouse action |
|--------|----------------|--------------|
| **Move** | Open hand; **move your hand** in any direction | Cursor moves with the hand's *motion* (relative, like a real mouse) -- position in the camera frame never matters |
| **Clutch / release** | **Closed fist** | Releases the cursor: no motion, no clicks. Reopen anywhere and keep going -- no jump |
| **Left click** | Pinch **thumb + index**, aim (cursor **keeps following** your hand), **release** the pinch | Left click at the cursor's final position |
| **Double click** | Two quick **thumb + index** pinches | Double-click |
| **Drag** | Pinch **thumb + index**, **hold** ~0.5s, move; release to drop | Click-and-drag |
| **Right click** | Pinch **thumb + middle**, aim, **release** the pinch | Right click at the cursor's final position |
| **Scroll** | **Index + middle** up (ring ignored), move hand **up/down** | Vertical scroll, speed-proportional, like a real wheel |
| **Safe / rest** | **Closed fist** | No mouse action -- rest without accidents |

### How it stays stable

- **Palm anchor** -- cursor motion comes from the *palm centroid* (wrist + finger MCPs),
  never a fingertip, so opening/closing fingers cannot shake the cursor while you aim.
- **Velocity-adaptive anchor filter** -- strong smoothing when the hand is still
  (rock-steady cursor), light smoothing when it moves (responsive, not laggy).
- **Distance-normalized gain** -- leaning toward/away from the camera does not change cursor speed.
- **Residual deadzone** -- sub-threshold motion accumulates (slow precise aiming works);
  alternating jitter cancels itself out.
- **Glitch guard** -- implausible per-frame jumps (tracking glitches) are dropped, never applied.
- Pinch distances are normalized by hand size; drag uses a wider pinch-off tolerance.

### Priority (reliability first)

1. **Closed fist** -> clutch / NO ACTION (no move, click, drag, or scroll).
2. **Scroll pose** (confirmed over a few frames) -> scroll; suppresses pinches.
3. **Thumb + index** -> left click / double / drag (by timing).
4. **Thumb + middle** -> right click (index pinch preferred if both close).

---

## Install

### 1. Python + venv

Python **3.10 - 3.13** recommended. Always use a project venv -- do **not** install
into the system Python:

```bash
py -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Run

Windows: double-click **`run.bat`**, or:

```bash
venv\Scripts\python main.py
```

Linux/macOS:

```bash
venv/bin/python main.py
```

### 3. Model file

`hand_landmarker.task` (~8 MB) should already be in this folder.
If it is missing, the app **downloads it automatically** on first run.
(It is intentionally not stored in git.)

### 4. OS-specific notes

#### Linux

```bash
# Debian/Ubuntu examples -- names vary by distro
sudo apt update
sudo apt install python3-tk python3-dev
# X11 helper (often needed under X11):
sudo apt install python3-xlib
```

- **X11**: usually works after the packages above.
- **Wayland**: mouse control can be restricted; try an XWayland session, or grant input permissions for your compositor.

#### macOS

1. **Camera**: System Settings -> Privacy & Security -> Camera -> allow Terminal / your IDE / Python.
2. **Accessibility** (required for mouse control): Privacy & Security -> Accessibility -> enable the same app that runs `main.py`.
3. If the cursor does not move, quit and relaunch the terminal after granting Accessibility.

#### Windows

- Usually works after `pip install -r requirements.txt` in the venv.
- Allow camera access if Windows prompts you.

---

## On-screen HUD

- **Status**: Cursor Active / LEFT CLICK / RIGHT CLICK / DOUBLE CLICK / DRAGGING / SCROLL / SAFE / NO ACTION / No Hand Detected
- **Fingers TIMRP** (debug): `T`=thumb ... `P`=pinky; `-` = curled
- **Pinch ratios** (debug): thumb-index / thumb-middle
- **White circle**: the palm anchor that drives the cursor
- **Legend** (right side): gesture -> action cheat-sheet

---

## Project layout

| File | Role |
|------|------|
| `main.py` | Camera loop, HUD, action state machine (relative motion, clicks, scroll), tracking hold |
| `gestures.py` | Palm anchor + filter, finger-up / pinch / fist / scroll-pose detection |
| `mouse_controller.py` | Cross-platform mouse actions + adaptive smoothing (incl. Windows wheel-notch fix) |
| `config.py` | Tunable constants |
| `hand.py` | Thin wrapper -> `main.main()` |
| `tests/test_logic.py` | Offline tests of the whole gesture->mouse state machine (no camera needed) |
| `run.bat` | Windows launcher using the venv |
| `hand_landmarker.task` | MediaPipe model (auto-downloaded; not committed) |
| `requirements.txt` | Python dependencies |
| `prompt.md` | Living brief for agents working on this repo |

Run the tests any time:

```bash
venv\Scripts\python tests\test_logic.py
```

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| `ModuleNotFoundError` when running `python main.py` | You are using the system Python. Use `run.bat` or `venv\Scripts\python main.py`. |
| Camera won't open | Change `CAMERA_INDEX` in `config.py` (try `1`). Close other apps using the webcam. |
| Cursor doesn't move (macOS) | Grant **Accessibility** + Camera; restart the terminal. |
| Cursor doesn't move (Linux Wayland) | Use X11/XWayland; install `python3-xlib`. |
| Cursor too slow / fast | Tune `RELATIVE_GAIN_X` / `RELATIVE_GAIN_Y` in `config.py`. |
| Cursor jittery | Raise `ANCHOR_ALPHA_SLOW` toward 0.3, or lower `ANCHOR_ALPHA_FAST`. |
| Cursor laggy | Lower `ANCHOR_ALPHA_SLOW` / `ANCHOR_ALPHA_FAST`, or lower `SMOOTHING`. |
| Fist not recognized as clutch | Curl index-pinky clearly; tweak `FINGER_UP_MARGIN` / `FIST_CONFIRM_FRAMES`. |
| Scroll triggers while moving | Raise `SCROLL_CONFIRM_FRAMES` or keep pinky more curled. |
| Scroll too slow / fast | Lower / raise `SCROLL_TICK_TRAVEL` (one notch ~ 3 lines on Windows default). |
| Scroll lost while moving | Raise `SCROLL_POSE_GRACE_FRAMES` (tolerates pose flicker). |
| Clicks too sensitive / not enough | Adjust `PINCH_ON_RATIO` / `PINCH_OFF_RATIO` in `config.py`. |
| Drag drops too easily | Raise `DRAG_PINCH_OFF_RATIO`. |
| Brief flicker loses cursor | Increase `TRACKING_HOLD_FRAMES` (e.g. `15`). |
| Script dies suddenly | You hit **FAILSAFE** (cursor in top-left). Re-run; avoid slamming the cursor into that corner. |
| Model missing | Check network; delete a corrupt `hand_landmarker.task` and re-run to re-download. |

---

## Limitations

- Designed for **one hand**, front camera (selfie-style). Mild angles are OK; extreme side views still struggle.
- Lighting and busy backgrounds can reduce tracking quality.
- Very fast gestures may be missed; pinches need a clear open -> close -> open.
- A small set of **reliable** gestures is intentional -- middle-click was removed for simplicity.
