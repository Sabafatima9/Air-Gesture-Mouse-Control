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

## How clicks work (finger → mouse map)

Preview is **mirrored** so moving your hand left moves the cursor left.  
Fingers on the HUD are labeled **TIMRP** = Thumb · Index · Middle · Ring · Pinky (`-` = curled).

| Gesture | Fingers / how | Mouse action |
|--------|----------------|--------------|
| **Move** | Point with **index** tip (other fingers can be down) | Cursor follows (depth-compensated) |
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

Pinch distances are **normalized by hand size** (wrist → middle-finger base). Cursor mapping is **depth-compensated** using that same hand-size metric so moving nearer/farther does not collapse the usable range or drop tracking as easily.

---

## Tracking improvements (real-world use)

- **Lower MediaPipe thresholds** (detection ~0.5, presence/tracking ~0.4) so hands farther from the camera still track.
- **Wider usable frame** (`FRAME_MARGIN` ~0.06) — cursor is not stuck in a tiny central band.
- **Depth-aware tip→screen mapping** — hand size (wrist→MCP) scales motion around frame center.
- **Velocity-adaptive smoothing** — responsive when you move fast, steadier when slow.
- **Tracking hold / grace** (~10 frames) — brief loss (angle/depth blip) keeps the last cursor instead of resetting.
- **No hard palm-facing gate** — soft finger heuristics only; mild angles are OK.
- **HUD debug**: skeleton + fingertips, hand-size / depth-scale, TIMRP flags, pinch ratios, and an on-screen gesture legend.

Tune in `config.py`: `MIN_HAND_*_CONFIDENCE`, `FRAME_MARGIN`, `SMOOTHING`, `REFERENCE_HAND_SIZE`, `TRACKING_HOLD_FRAMES`, pinch/scroll timings.

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

- **Mode**: MOVE / LEFT CLICK / RIGHT CLICK / MIDDLE CLICK / DOUBLE CLICK / DRAG / SCROLL / HOLD
- **Fingers TIMRP**: `T`=thumb … `P`=pinky; `-` = curled
- **Pinch ratios**: thumb–index / thumb–middle / thumb–ring (lower = closer; click when below ON threshold)
- **HandSize / DepthScale**: depth proxy used for stable cursor mapping
- **Legend** (right side): short gesture → action cheat-sheet
- **Cyan line** wrist→middle MCP: hand-size reference; colored tips = fingertips

---

## Project layout

| File | Role |
|------|------|
| `main.py` | Camera loop, HUD, action state machine, tracking hold |
| `gestures.py` | Finger-up / pinch / scroll-pose / depth-compensated map |
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
| Loses hand when slightly far / angled | Thresholds are already lowered; improve lighting; raise hand into frame; tweak `MIN_HAND_*` in `config.py`. |
| Cursor jumps when moving nearer/farther | Adjust `REFERENCE_HAND_SIZE` / `DEPTH_SCALE_*` in `config.py`. |
| Clicks too sensitive / not enough | Adjust `PINCH_ON_RATIO` / `PINCH_OFF_RATIO` in `config.py`. |
| Cursor laggy | Lower `SMOOTHING` or raise `SMOOTHING_VELOCITY_REF`. |
| Cursor jittery | Increase `SMOOTHING` (e.g. `0.5`). |
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
