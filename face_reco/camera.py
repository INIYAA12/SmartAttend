import cv2, platform, time, os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def open_camera():
    index = config.CAMERA_INDEX
    if platform.system() == "Windows":
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    else:
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        return None
    for _ in range(config.CAMERA_WARMUP_FRAMES):
        ok, frame = cap.read()
        if ok and frame is not None:
            return cap
        time.sleep(0.05)
    cap.release()
    return None
