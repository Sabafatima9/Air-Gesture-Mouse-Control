# Air Gesture Mouse Control — agent prompt

Living brief for assistants working on this repo. Keep this file accurate when the code changes.

## Project

Cross-platform **hand-gesture mouse** for a **front-facing webcam** (selfie / ~90° face-on view).

- **Stack:** OpenCV · MediaPipe Hand Landmarker (Tasks API) · pyautogui · numpy
- **Entry:** `python main.py` (or `python hand.py`)
- **OS:** Linux, macOS, Windows (see README for OS-specific install / permissions)
- **Remote:** https://github.com/Sabafatima9/Air-Gesture-Mouse-Control

## Layout

| File | Role |
|------|------|
| `main.py` | Camera loop, HUD, click/double/drag state machine |
| `gestures.py` | Finger-up, pinch hysteresis, scroll pose, frame→screen map |
| `mouse_controller.py` | pyautogui wrapper (move, click, drag, scroll, FAILSAFE) |
| `config.py` | Tunable thresholds and landmark indexes |
| `hand.py` | Thin wrapper → `main.main()` |
| `hand_landmarker.task` | MediaPipe model (auto-download if missing) |
| `requirements.txt` | Dependencies |
| `README.md` | User-facing install + gesture cheat-sheet |

## Gestures (mirrored preview)

| Gesture | How | Action |
|---------|-----|--------|
| Move | Index tip | Cursor follows (margins + smoothing) |
| Left click | Thumb + index pinch, quick release | Left click |
| Double click | Two quick thumb–index pinches | Double-click |
| Drag | Thumb + index hold ≥ ~0.45s, then move | mouseDown → move → mouseUp |
| Right click | Thumb + middle pinch | Right click |
| Middle click | Thumb + ring pinch | Middle click |
| Scroll | Index+middle up, ring+pinky down; move vertically | Vertical scroll |

**Priority:** scroll pose > pinches; among pinches ring → middle → index (exclusive).

## Safety & convenience

- pyautogui **FAILSAFE**: corner fling (top-left) aborts.
- Quit: **Q** / **Esc**; always release camera / landmarker / mouse buttons on exit.
- Pinch distances normalized by hand size (distance-stable).
- Do **not** commit secrets, tokens, or personal paths into this repo.
- Prefer not re-committing the large `.task` binary if it can be downloaded; keep auto-download.
- Camera + Accessibility (macOS) / input permissions (Linux Wayland) are required on the host — document, don’t hardcode machine paths.

## When this file is wrong

Update it to match the real gesture map, modules, and safety behavior. Prefer clarity over marketing. Flag security issues (credential leaks, unsafe shell, unbounded network) in the same change.
