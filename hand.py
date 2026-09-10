"""
Air Gesture Mouse Control
=========================
Control the computer mouse with hand gestures, detected through the webcam.

How it works (simple overview):
  1. OpenCV captures the live webcam feed.
  2. MediaPipe Hands (Tasks API) finds 21 hand landmarks each frame.
  3. The index finger tip position is mapped to the screen and moves the
     mouse cursor with pyautogui.
  4. When the thumb tip and index finger tip come close together (a "pinch"),
     a mouse click is performed.
  5. Press 'q' in the camera window to quit safely.

NOTE: pyautogui has a built-in FAILSAFE: if the cursor is flung into the
top-left corner of the screen, the script raises an exception and stops.
This is a safety feature, not a bug.
"""

import os
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
import pyautogui

# ==============================================================================
# SETTINGS (tweak these values to fine-tune the behavior)
# ==============================================================================

CAMERA_INDEX = 0          # 0 = default webcam, try 1 or 2 if you have more
FRAME_WIDTH = 640         # camera frame size (small = faster processing)
FRAME_HEIGHT = 480

SMOOTHING = 0.4           # 0 = cursor follows instantly, 1 = very smooth but laggy

# Pinch detection uses a ratio (finger distance / hand size), so it works
# no matter how close or far your hand is from the camera.
PINCH_ON_RATIO = 0.30     # below this ratio  -> pinch started  -> click
PINCH_OFF_RATIO = 0.45    # above this ratio -> pinch released (hysteresis,
                          # so one pinch never fires multiple clicks)

CLICK_COOLDOWN = 0.5      # seconds to wait between two clicks

# Console status messages are printed at most once per second so the
# terminal does not get flooded with thousands of lines per minute.
STATUS_PRINT_INTERVAL = 1.0

# Hand landmark indexes used here (MediaPipe hand model has 21 points):
THUMB_TIP = 4
INDEX_TIP = 8
WRIST = 0
MIDDLE_FINGER_MCP = 9     # base of the middle finger, used as "hand size"

# The hand_landmarker model file. It is downloaded automatically the first
# time if it is not already in this folder.
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")
MODEL_FILENAME = "hand_landmarker.task"

# ==============================================================================
# SETUP
# ==============================================================================

pyautogui.FAILSAFE = True   # fling cursor to top-left corner to emergency-stop
pyautogui.PAUSE = 0         # no artificial delay between mouse moves

screen_width, screen_height = pyautogui.size()
print(f"Screen resolution detected: {screen_width}x{screen_height}")


def load_hand_landmarker():
    """Creates the MediaPipe HandLandmarker (Tasks API).

    Downloads the .task model file first if it is missing from this folder.
    """
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              MODEL_FILENAME)
    if not os.path.exists(model_path):
        print(f"Model file not found. Downloading {MODEL_FILENAME} ...")
        urllib.request.urlretrieve(MODEL_URL, model_path)
        print("Model downloaded successfully!")

    base_options = mp.tasks.BaseOptions(model_asset_path=model_path)
    options = mp.tasks.vision.HandLandmarkerOptions(
        base_options=base_options,
        # VIDEO mode gives smoother tracking between consecutive frames.
        running_mode=mp.tasks.vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.7,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return mp.tasks.vision.HandLandmarker.create_from_options(options)


def main():
    landmarker = load_hand_landmarker()

    camera = cv2.VideoCapture(CAMERA_INDEX)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not camera.isOpened():
        print("ERROR: Could not open the webcam. "
              "Try changing CAMERA_INDEX at the top of the file.")
        return

    window_name = "Air Gesture Mouse - press Q to quit"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, FRAME_WIDTH, FRAME_HEIGHT)

    smoothed_x, smoothed_y = None, None   # last smoothed cursor position
    pinch_active = False                  # is a pinch currently held?
    last_click_time = 0.0
    last_status_time = 0.0
    last_status_text = ""
    frame_timestamp_ms = 0                # increasing timestamps for VIDEO mode

    try:
        while True:
            success, frame = camera.read()
            if not success:
                print("ERROR: Failed to read a frame from the camera.")
                break

            # Mirror the image so moving your hand right moves the cursor
            # right (selfie view), which feels natural.
            frame = cv2.flip(frame, 1)

            frame_height, frame_width = frame.shape[:2]

            # MediaPipe wants RGB images, OpenCV gives BGR.
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # VIDEO mode requires a strictly increasing timestamp per frame.
            frame_timestamp_ms += int(1000 / 30)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                                data=rgb_frame)
            result = landmarker.detect_for_video(mp_image, frame_timestamp_ms)

            hand_found = False
            if result and result.hand_landmarks:
                hand_found = True
                landmarks = result.hand_landmarks[0]

                # Landmarks are normalized (0..1). Convert to pixels.
                def to_pixels(landmark):
                    return np.array([landmark.x * frame_width,
                                     landmark.y * frame_height])

                thumb_tip = to_pixels(landmarks[THUMB_TIP])
                index_tip = to_pixels(landmarks[INDEX_TIP])

                # "Hand size" = distance from wrist to middle-finger base.
                # Used to normalize the pinch distance, so the gesture works
                # at any distance from the camera.
                hand_size = np.linalg.norm(
                    to_pixels(landmarks[MIDDLE_FINGER_MCP]) -
                    to_pixels(landmarks[WRIST]))
                pinch_ratio = np.linalg.norm(thumb_tip - index_tip) / hand_size

                # --- Cursor movement -------------------------------------
                # Map the index fingertip from the camera frame onto the
                # whole screen. The fingertip can be anywhere in the frame.
                target_x = index_tip[0] / frame_width * screen_width
                target_y = index_tip[1] / frame_height * screen_height

                # Smoothing: average with the previous target position to
                # remove jitter from the hand tracking.
                if smoothed_x is None:
                    smoothed_x, smoothed_y = target_x, target_y
                else:
                    smoothed_x += (target_x - smoothed_x) * (1 - SMOOTHING)
                    smoothed_y += (target_y - smoothed_y) * (1 - SMOOTHING)

                pyautogui.moveTo(smoothed_x, smoothed_y)

                # --- Pinch = mouse click (with hysteresis + cooldown) -----
                now = time.time()
                if not pinch_active and pinch_ratio < PINCH_ON_RATIO:
                    pinch_active = True
                    if now - last_click_time > CLICK_COOLDOWN:
                        pyautogui.click()
                        last_click_time = now
                        print("Click Detected")
                elif pinch_active and pinch_ratio > PINCH_OFF_RATIO:
                    pinch_active = False   # fingers separated, ready again

                # --- Small on-screen reference overlay --------------------
                cv2.circle(frame, tuple(thumb_tip.astype(int)), 8,
                           (255, 0, 255), -1)   # thumb tip: magenta
                cv2.circle(frame, tuple(index_tip.astype(int)), 8,
                           (0, 255, 255), -1)   # index tip: yellow
                cv2.line(frame, tuple(thumb_tip.astype(int)),
                         tuple(index_tip.astype(int)), (0, 255, 0), 2)
                cv2.putText(frame, f"pinch {pinch_ratio:.2f}",
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 255, 0), 2)
            else:
                # Reset smoothing so the cursor does not "fly" from an old
                # position when the hand re-appears somewhere else.
                smoothed_x, smoothed_y = None, None

            # --- Throttled console status ------------------------------
            now = time.time()
            status = "Cursor Moving" if hand_found else "No Hand Detected"
            if status != last_status_text or now - last_status_time > STATUS_PRINT_INTERVAL:
                print(status)
                last_status_time = now
                last_status_text = status

            cv2.imshow(window_name, frame)

            # Press 'q' (or Escape) to quit.
            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), 27):
                print("Quit key pressed. Exiting...")
                break
    finally:
        # Always release the camera and close windows, even after an error
        # (including the pyautogui FAILSAFE exception).
        camera.release()
        cv2.destroyAllWindows()
        landmarker.close()
        print("Camera released. Goodbye!")


if __name__ == "__main__":
    main()
