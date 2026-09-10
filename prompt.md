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

Please simplify the gesture system and also prioritize **smooth, comfortable, and responsive performance**. The application should feel natural enough that a user can comfortably work with it for an extended period without frustration or hand fatigue.

### Simplified Gesture Design

**1. Cursor Movement**

* Use the **index finger tip** to control the cursor.
* When the index finger is pointing/up, its position should control the cursor.
* Apply good cursor smoothing to eliminate shaking/jitter.
* Cursor movement should be responsive but not overly sensitive.
* The user should be able to move the cursor slowly for precision and quickly for larger movements.
* Use appropriate coordinate mapping and, if useful, depth compensation to make movement feel natural.

**2. Left Click**

* Use a simple **thumb + index finger pinch**.
* A quick pinch and release = one left click.
* Make the pinch detection forgiving and reliable.
* The user should not need to make an exaggerated or perfectly precise pinch.

**3. Double Click**

* DO NOT require a special double-click gesture.
* Two normal thumb + index pinches performed quickly should be interpreted as a double click.
* The user should be able to double-click naturally without struggling to perform two perfect pinches.
* Use appropriate timing/debounce logic to distinguish:

  * One pinch → single click
  * Two quick pinches → double click

**4. Drag**

* Keep drag simple:

  * Thumb + index pinch
  * Hold the pinch for approximately **0.45–0.5 seconds**
  * Enter drag mode
  * Move the hand while maintaining the pinch → drag
  * Release the pinch → drop
* A normal quick pinch must remain a click and should not accidentally trigger drag.
* Add appropriate tolerance so small finger movements during dragging do not cause the drag to break.

**5. Closed Fist = Safe / No Action**

* When the user's hand forms a **closed fist**, perform **NO mouse action**.
* Do not move the cursor.
* Do not click.
* Do not drag.
* Do not scroll.
* Treat the closed fist as a neutral/safe/resting state.
* This should allow the user to comfortably rest their hand without accidental actions.

**6. Scrolling**

* Use a simple two-finger gesture:

  * Index + middle fingers up
  * Ring + pinky curled
* Move hand upward → scroll up.
* Move hand downward → scroll down.
* Scrolling should only activate when the gesture is clearly detected.
* Do not accidentally trigger scrolling during normal cursor movement.

**7. Right Click — Optional**

* If implemented, use **thumb + middle finger pinch** for right click.
* Ensure it does not interfere with thumb + index left click.
* If reliability becomes an issue, prioritize the core gestures instead of making the system unnecessarily complicated.

---

# VERY IMPORTANT: Smooth & Comfortable User Experience

The application must run **very smoothly in real time**.

The objective is not just to make the gestures technically work — the application should feel **comfortable, stable, responsive, and natural for the user**.

Please optimize for:

### Performance

* Maintain a high and stable webcam processing FPS.
* Avoid unnecessary processing inside the main loop.
* Keep CPU usage reasonable.
* Avoid memory leaks.
* Avoid unnecessary delays or blocking operations.
* Make mouse control responsive with minimal latency.
* Process frames efficiently.

### Cursor Smoothness

* Implement an appropriate smoothing/filtering technique for cursor movement.
* Prevent visible cursor shaking caused by small landmark movements.
* Do not over-smooth the cursor because excessive smoothing creates noticeable lag.
* Find a good balance between **stability and responsiveness**.
* The cursor should follow the user's finger naturally.

### Gesture Stability

* Do not trigger gestures from a single noisy frame.
* Use appropriate thresholds, state tracking, and temporal consistency.
* Avoid accidental clicks caused by small movements.
* Avoid repeated clicks while a pinch is being held.
* Avoid accidental transitions between click, drag, scroll, and movement.
* Gesture states should transition smoothly.

### User Comfort

The user should be able to use the application **without constantly holding their hand in an uncomfortable position**.

* Do not require exaggerated finger movements.
* Do not require extreme pinching.
* Keep gesture thresholds tolerant.
* Allow the hand to rest in the neutral/closed-fist state.
* Avoid requiring the user to keep their fingers perfectly positioned at all times.
* Make cursor movement usable for both small precise movements and larger movements.
* Minimize false detections and accidental mouse actions.

### Camera & Tracking

* Handle temporary hand-tracking loss gracefully.
* If the hand disappears for a short time, do not perform unexpected mouse actions.
* If no hand is detected, safely pause mouse control.
* Handle different lighting conditions as reasonably as possible.
* Keep tracking stable when the hand moves at different speeds.

### Clear Visual Feedback

Display useful information on the webcam window, for example:

* `Hand Detected`
* `Cursor Active`
* `LEFT CLICK`
* `DOUBLE CLICK`
* `DRAGGING`
* `SCROLL`
* `SAFE / NO ACTION`
* `No Hand Detected`

Keep the visual interface simple and non-distracting.

---

# Gesture Priority

Prioritize reliability in this order:

1. ☝️ **Index → Cursor movement**
2. 👌 **Thumb + Index pinch → Left click**
3. 👌 **Two quick pinches → Double click**
4. 👌 **Pinch + hold → Drag**
5. ✊ **Closed fist → Safe / No action**
6. ✌️ **Two fingers → Scroll**
7. 🤏 **Right click (optional)**

If two gestures conflict, **prioritize the simpler and more reliable gesture** rather than adding complicated detection rules.

---

# Testing & Optimization — 

Do not just generate the code and assume it works.

After implementation:

1. Install all dependencies.
2. Run the application using a real webcam.
3. Verify hand tracking.
4. Test cursor movement.
5. Test single click.
6. Test double click.
7. Test drag and drop.
8. Test closed fist as the safe/no-action state.
9. Test scrolling.
10. Test optional right click.
11. Test switching between gestures.
12. Check for accidental clicks.
13. Check for accidental dragging.
14. Check for cursor jitter.
15. Check for noticeable input latency.
16. Check CPU/memory usage and optimize if necessary.
17. Test the application continuously for several minutes to identify stability issues.
18. Fix any errors, crashes, lag, jitter, false gestures, or performance problems.
19. Run the tests again after making fixes.

### Definition of Done

The project is complete only when it is:

**Working + Smooth + Responsive + Stable + Comfortable + Tested**

The user should be able to sit comfortably in front of the webcam and control the mouse naturally without constantly fighting the gesture system.

Do not sacrifice usability just to add more gestures. **A small number of reliable and smooth gestures is better than many complicated gestures.**

