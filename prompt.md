# Air Gesture Mouse Control -- agent prompt

Living brief for assistants working on this repo. Keep this file accurate when the code changes.

## Project

Cross-platform **hand-gesture mouse** for a **front-facing webcam** (selfie view; mild angles OK -- no hard ~90-degree palm gate).

- **Stack:** OpenCV + MediaPipe Hand Landmarker (Tasks API) + pyautogui + numpy
- **Entry:** `python main.py` (or `python hand.py`); Windows users double-click `run.bat`
- **OS:** Linux, macOS, Windows (see README for OS-specific install / permissions)
- **Remote:** https://github.com/Sabafatima9/Air-Gesture-Mouse-Control

## Interaction model (do not regress these)

- **Relative motion only.** The cursor is driven by PALM MOTION (centroid of wrist + the four MCPs), never by hand position in the camera frame and never by a fingertip (pinching moves fingertips and would shake the cursor). Hand position in frame is irrelevant; any screen edge is reachable with the hand in frame.
- **Closed fist = clutch.** No motion, no clicks; re-anchor every fist frame so reopening anywhere never jumps the cursor.
- **Pinch thumb+index:** cursor keeps following the hand while the pinch is held (aiming); the RELEASE performs the left click at the cursor's final position. Two quick pinches = double click. Hold >= DRAG_HOLD_TIME then move = drag (mouse_down, follow, release to mouse_up).
- **Pinch thumb+middle:** same pattern -- aim while held, RELEASE performs the right click. It must NOT fire on engage.
- **Scroll pose** (index+middle up, pinky curled, ring ignored): vertical scroll driven by PALM y motion, speed-proportional like a real wheel. Survives pose flicker via SCROLL_POSE_GRACE_FRAMES (anchor frozen across short gaps, gap motion still counts; full reset only after the grace expires).
- **Priority:** closed fist > confirmed scroll pose > pinches; among pinches index > middle (exclusive).

## Tracking design (keep when editing)

- `gestures.py`: `AnchorFilter` = velocity-adaptive EMA on the palm anchor (calm when still, loose when moving; snaps on > ANCHOR_SNAP glitches). Hand size is EMA'd for distance-invariant gain (REFERENCE_HAND_SIZE / size, clamped).
- `main.py`: `_apply_relative_motion` computes per-frame palm deltas: MOTION_JUMP guard drops tracking glitches; sub-MOTION_DEADZONE motion accumulates as residue so slow aiming works and jitter cancels. Called on every non-fist, non-scroll frame, including while pinches are held.
- Scroll has its OWN anchor (`scroll_prev_y` + accumulator) -- never shared with cursor motion, so entering/leaving scroll cannot jump the cursor.
- `mouse_controller.py`: velocity-adaptive screen-space smoothing + residual pixel deadzone. **Windows scroll quirk:** pyautogui passes raw wheel detents (WHEEL_DELTA = 120 per notch), so `scroll()` multiplies notches by 120 on win32. Do not remove this or scroll silently dies on Windows.
- Pinch hysteresis: on < PINCH_ON_RATIO, off > PINCH_OFF_RATIO (wider while dragging); re-arm requires all ratios open after fist/scroll suppress pinches.
- Temporal confirm: SCROLL_CONFIRM_FRAMES / FIST_CONFIRM_FRAMES; PINCH_MIN_HOLD filters sub-50 ms noise pinches; CLICK_COOLDOWN spaces actions.
- VIDEO timestamps use real elapsed ms (not a fixed fake FPS). TRACKING_HOLD_FRAMES (~10) holds the cursor during brief hand loss.

## Environment / install policy

- Dependencies live ONLY in the project venv (`venv/`). Never install project deps into the system Python.
- Windows launcher: `run.bat` (uses `venv\Scripts\python.exe`, no activation).
- `hand_landmarker.task` (7.8 MB) is auto-downloaded; it is NOT tracked in git (.gitignore lists it). Keep it that way.
- Offline tests: `venv\Scripts\python tests\test_logic.py` -- synthetic landmarks drive the whole state machine with a mock mouse (no camera). Extend when changing gesture logic; keep green.

## Safety & convenience

- pyautogui **FAILSAFE**: corner fling (top-left) aborts.
- Quit: **Q** / **Esc**; always release camera / landmarker / mouse buttons on exit.
- Pinch distances normalized by hand size (distance-stable).
- Do **not** commit secrets, tokens, or personal paths into this repo.

## When this file is wrong

Update it to match the real gesture map, modules, and safety behavior. Prefer clarity over marketing. Flag security issues (credential leaks, unsafe shell, unbounded network) in the same change.

Do not sacrifice usability just to add more gestures. **A small number of reliable and smooth gestures is better than many complicated gestures.**
