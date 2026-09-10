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

## How gestures work (simplified)

Preview is **mirrored** so moving your hand left moves the cursor left.  
Fingers on the HUD are labeled **TIMRP** = Thumb · Index · Middle · Ring · Pinky (`-` = curled).

| Gesture | Fingers / how | Mouse action |
|--------|----------------|--------------|
| **Move** | **Index** tip | Cursor follows (depth-compensated, smoothed) |
| **Left click** | Pinch **thumb + index**, release quickly | Left click |
| **Double click** | Two quick **thumb + index** pinches | Double-click |
| **Drag** | Pinch **thumb + index** and **hold** (~0.45–0.5s), then move; release to drop | Click-and-drag |
| **Safe / rest** | **Closed fist** (index–pinky curled) | **No mouse action** — rest without accidents |
| **Scroll** | **Index + middle** up, **ring + pinky** curled. Move hand **up/down** | Vertical scroll |
| **Right click** *(optional)* | Pinch **thumb + middle** | Right click |

### Priority (reliability first)

1. **Closed fist** → SAFE / NO ACTION (no move, click, drag, or scroll).
2. **Scroll pose** (confirmed over a few frames) → scroll; suppresses pinches.
3. **Thumb + index** → left click / double / drag (by timing).
4. **Thumb + middle** → optional right click (index pinch preferred if both close).

Pinch distances are **normalized by hand size**. Cursor mapping is **depth-compensated**. Drag uses a **wider pinch-off tolerance** so small finger wobble does not drop the drag.

---

## Comfort & smoothness

- **Forgiving pinches** — no exaggerated pinch needed.
- **Velocity-adaptive smoothing** + small deadzone — stable when slow, responsive when fast.
- **Tracking hold / grace** — brief hand loss keeps the last cursor instead of jumping.
- **Scroll / fist confirm frames** — avoid single-frame false triggers.
- **HUD status**: `Cursor Active`, `LEFT CLICK`, `DOUBLE CLICK`, `DRAGGING`, `SCROLL`, `SAFE / NO ACTION`, `No Hand Detected`.

Tune in `config.py`: pinch ratios, `DRAG_HOLD_TIME`, `SMOOTHING`, `SCROLL_CONFIRM_FRAMES`, `FIST_CONFIRM_FRAMES`, etc.

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

- **Status**: Cursor Active / LEFT CLICK / DOUBLE CLICK / DRAGGING / SCROLL / SAFE / NO ACTION / No Hand Detected
- **Fingers TIMRP** (debug): `T`=thumb … `P`=pinky; `-` = curled
- **Pinch ratios** (debug): thumb–index / thumb–middle
- **HandSize / DepthScale**: depth proxy for stable cursor mapping
- **Legend** (right side): short gesture → action cheat-sheet

---

## Project layout

| File | Role |
|------|------|
| `main.py` | Camera loop, HUD, action state machine, tracking hold |
| `gestures.py` | Finger-up / pinch / fist / scroll-pose / depth map |
| `mouse_controller.py` | Cross-platform mouse + adaptive smoothing |
| `config.py` | Tunable constants |
| `hand.py` | Thin wrapper → `main.main()` |
| `hand_landmarker.task` | MediaPipe model (kept / auto-downloaded) |
| `requirements.txt` | Python dependencies |
| `prompt.md` | Living brief for agents working on this repo |

---

## Troubleshooting

| Problem | What to try |
|---------|-------------|
| Camera won’t open | Change `CAMERA_INDEX` in `config.py` (try `1`). Close other apps using the webcam. |
| Cursor doesn’t move (macOS) | Grant **Accessibility** + Camera; restart the terminal. |
| Cursor doesn’t move (Linux Wayland) | Use X11/XWayland; install `python3-xlib`. |
| Fist not recognized as safe | Curl index–pinky clearly; tweak `FINGER_UP_MARGIN` / `FIST_CONFIRM_FRAMES`. |
| Scroll triggers while moving | Raise `SCROLL_CONFIRM_FRAMES` or keep ring/pinky more curled. |
| Clicks too sensitive / not enough | Adjust `PINCH_ON_RATIO` / `PINCH_OFF_RATIO` in `config.py`. |
| Drag drops too easily | Raise `DRAG_PINCH_OFF_RATIO`. |
| Cursor laggy | Lower `SMOOTHING` or raise `SMOOTHING_VELOCITY_REF`. |
| Cursor jittery | Increase `SMOOTHING` or `CURSOR_DEADZONE_PX`. |
| Can’t reach screen edges | Decrease `FRAME_MARGIN` (e.g. `0.04`). |
| Scroll inverted / too fast | Flip sign via negative `SCROLL_AMOUNT`, or change `SCROLL_SENSITIVITY`. |
| Brief flicker loses cursor | Increase `TRACKING_HOLD_FRAMES` (e.g. `15`). |
| Script dies suddenly | You hit **FAILSAFE** (cursor in top-left). Re-run; avoid slamming the cursor into that corner. |
| Model missing | Check network; delete a corrupt `hand_landmarker.task` and re-run to re-download. |

---

## Limitations

- Designed for **one hand**, front camera (selfie-style). Mild angles are OK; extreme side views still struggle.
- Lighting and busy backgrounds can reduce tracking quality.
- Very fast gestures may be missed; pinches need a clear open→close→open.
- Headless / CI environments usually have **no webcam** — run on a desktop with a camera.
- A small set of **reliable** gestures is intentional — middle-click (thumb+ring) was removed for simplicity.
