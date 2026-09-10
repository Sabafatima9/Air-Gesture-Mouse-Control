# Air Gesture Mouse Control

Control your mouse with hand gestures from a **front-facing webcam** (laptop / selfie view).  
Built with **OpenCV** + **MediaPipe Hand Landmarker (Tasks API)** + **pyautogui**.

Works on **Linux**, **macOS**, and **Windows**.

```bash
pip install -r requirements.txt
python main.py
```

Press **Q** or **Esc** in the camera window to quit.  
**Emergency stop:** fling the cursor into the extreme **top-left** corner (pyautogui FAILSAFE).

---

## Gesture cheat-sheet

Preview is **mirrored** so moving your hand left moves the cursor left.

| Gesture | How to do it | Mouse action |
|--------|----------------|--------------|
| **Move** | Point with index finger (tip tracked) | Cursor follows fingertip |
| **Left click** | Pinch **thumb + index**, release quickly | Left click |
| **Double click** | Two quick **thumb + index** pinches | Double-click |
| **Drag** | Pinch **thumb + index** and **hold** (~0.45s), then move; release to drop | Click-and-drag |
| **Right click** | Pinch **thumb + middle** | Right click |
| **Middle click** | Pinch **thumb + ring** | Middle click |
| **Scroll** | Hold **index + middle** up, **ring + pinky** curled (“peace” / two-finger). Move hand **up/down** | Vertical scroll |

### Priority rules (no ambiguous overlap)

1. **Scroll pose** wins over pinches while index+middle are up and ring+pinky are down.
2. Among pinches, only one is active at a time. Priority if several are close: **ring → middle → index** (strongest/closest pinch among candidates).
3. Left pinch timing: **short release** → click (or double if a second short pinch follows); **hold** past the drag threshold → drag.

Pinch distances are **normalized by hand size** (wrist → middle-finger base), so they stay stable at different distances from the camera.

---

## Install

### 1. Python

Python **3.9+** recommended. Create a venv if you like:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows (cmd):
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Model file

`hand_landmarker.task` (~8 MB) should already be in this folder.  
If it is missing, the app **downloads it automatically** on first run.

### 3. OS-specific notes

#### Linux

```bash
# Debian/Ubuntu examples — names vary by distro
sudo apt update
sudo apt install python3-tk python3-dev
# Screenshots (optional; pyautogui may want one):
sudo apt install scrot
# or: sudo apt install gnome-screenshot
# X11 helper (often needed under X11):
sudo apt install python3-xlib
```

- **X11**: usually works after the packages above.
- **Wayland**: mouse control can be restricted; try an XWayland session, or grant input permissions for your compositor. Camera access via OpenCV/`/dev/video*` must be allowed for your user (often in the `video` group).

#### macOS

1. **Camera**: System Settings → Privacy & Security → Camera → allow Terminal / your IDE / Python.
2. **Accessibility** (required for mouse control): Privacy & Security → Accessibility → enable the same app that runs `python main.py`.
3. If the cursor does not move, quit and relaunch the terminal after granting Accessibility.

#### Windows

- Usually works after `pip install -r requirements.txt`.
- Allow camera access if Windows prompts you.
- Run from a normal user session (not a headless service).

---

## Run

```bash
python main.py
```

Legacy wrapper (same entry point):

```bash
python hand.py
```

### On-screen HUD

- **Mode**: MOVE / LEFT CLICK / RIGHT CLICK / MIDDLE CLICK / DOUBLE CLICK / DRAG / SCROLL
- **Fingers**: `TIMRP` flags (`T`=thumb … `P`=pinky; `-` = curled)
- **Pinch ratios**: thumb–index / thumb–middle / thumb–ring (lower = closer)

Tune thresholds in `config.py` (`PINCH_ON_RATIO`, `SMOOTHING`, `DRAG_HOLD_TIME`, `SCROLL_SENSITIVITY`, `FRAME_MARGIN`, …).

---

## Project layout

| File | Role |
|------|------|
| `main.py` | Camera loop, HUD, action state machine |
| `gestures.py` | Finger-up / pinch / scroll-pose detection |
| `mouse_controller.py` | Cross-platform mouse via pyautogui |
| `config.py` | Tunable constants |
| `hand.py` | Thin wrapper → `main.main()` |
| `hand_landmarker.task` | MediaPipe model (kept / auto-downloaded) |
| `requirements.txt` | Python dependencies |

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Camera won’t open | Change `CAMERA_INDEX` in `config.py` (try `1`). Close other apps using the webcam. |
| Cursor doesn’t move (macOS) | Grant **Accessibility** + Camera; restart the terminal. |
| Cursor doesn’t move (Linux Wayland) | Use X11/XWayland; install `python3-xlib`. |
| Clicks too sensitive / not enough | Adjust `PINCH_ON_RATIO` / `PINCH_OFF_RATIO` in `config.py`. |
| Cursor jittery | Increase `SMOOTHING` (e.g. `0.65`). |
| Can’t reach screen edges | Decrease `FRAME_MARGIN` (e.g. `0.08`). |
| Scroll inverted / too fast | Flip sign via negative `SCROLL_AMOUNT`, or change `SCROLL_SENSITIVITY`. |
| Script dies suddenly | You hit **FAILSAFE** (cursor in top-left). Re-run; avoid slamming the cursor into that corner. |
| Model missing | Check network; delete a corrupt `hand_landmarker.task` and re-run to re-download. |

---

## Limitations

- Designed for **one hand**, front camera aimed roughly at the user’s face (~vertical 90° / selfie).
- Lighting and busy backgrounds can reduce tracking quality.
- Very fast gestures may be missed; pinches need a clear open→close→open.
- Headless / CI environments usually have **no webcam** — run on a desktop with a camera.
