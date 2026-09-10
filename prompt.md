# Air Gesture Mouse Control — agent prompt

Living brief for assistants working on this repo. Keep this file accurate when the code changes.

## Project

Cross-platform **hand-gesture mouse** for a **front-facing webcam** (selfie view; mild angles OK — no hard ~90° palm gate).

- **Stack:** OpenCV · MediaPipe Hand Landmarker (Tasks API) · pyautogui · numpy
- **Entry:** `python main.py` (or `python hand.py`)
- **OS:** Linux, macOS, Windows (see README for OS-specific install / permissions)
- **Remote:** https://github.com/Sabafatima9/Air-Gesture-Mouse-Control

## Layout

| File | Role |
|------|------|
| `main.py` | Camera loop, HUD, click/double/drag state machine, tracking-hold grace |
| `gestures.py` | Finger-up, pinch hysteresis, scroll pose, depth-compensated frame→screen map |
| `mouse_controller.py` | pyautogui wrapper (move, click, drag, scroll, adaptive smoothing, FAILSAFE) |
| `config.py` | Tunable thresholds, depth/smoothing/hold constants, landmark indexes |
| `hand.py` | Thin wrapper → `main.main()` |
| `hand_landmarker.task` | MediaPipe model (auto-download if missing) |
| `requirements.txt` | Dependencies |
| `README.md` | User-facing install + gesture cheat-sheet |

## Gestures (mirrored preview) — finger → mouse map

| Gesture | How | Action |
|---------|-----|--------|
| Move | Index tip (depth-compensated via hand size) | Cursor follows |
| Left click | Thumb + index pinch, quick release | Left click |
| Double click | Two quick thumb–index pinches | Double-click |
| Drag | Thumb + index hold ≥ ~0.45s, then move | mouseDown → move → mouseUp |
| Right click | Thumb + middle pinch | Right click |
| Middle click | Thumb + ring pinch | Middle click |
| Scroll | Index+middle up, ring+pinky down; move vertically | Vertical scroll |

**Priority:** scroll pose > pinches; among pinches ring → middle → index (exclusive).

**HUD TIMRP:** Thumb · Index · Middle · Ring · Pinky (`-` = curled). Pinch ratios + HandSize/DepthScale shown for debug. On-screen legend lists the map above.

## Tracking design (keep when editing)

- Confidence: detection ~0.5, presence/tracking ~0.4 (`config.py`).
- `FRAME_MARGIN` small (~0.06) so edges are reachable.
- Cursor uses `cursor_norm` = tip position expanded around frame center by `depth_scale = REFERENCE_HAND_SIZE / hand_size` (clamped).
- Velocity-adaptive smoothing in `MouseController` (`SMOOTHING` ↔ `SMOOTHING_FAST`).
- `TRACKING_HOLD_FRAMES` (~10): on brief hand loss, hold last smoothed position; only then reset.
- No hard orientation/angle gates — soft finger-up heuristics only.

## Safety & convenience

- pyautogui **FAILSAFE**: corner fling (top-left) aborts.
- Quit: **Q** / **Esc**; always release camera / landmarker / mouse buttons on exit.
- Pinch distances normalized by hand size (distance-stable).
- Do **not** commit secrets, tokens, or personal paths into this repo.
- Prefer not re-committing the large `.task` binary if it can be downloaded; keep auto-download.
- Camera + Accessibility (macOS) / input permissions (Linux Wayland) are required on the host — document, don’t hardcode machine paths.

## When this file is wrong

Update it to match the real gesture map, modules, and safety behavior. Prefer clarity over marketing. Flag security issues (credential leaks, unsafe shell, unbounded network) in the same change.
