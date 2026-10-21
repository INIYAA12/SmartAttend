import os, sys, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from face_reco.camera import open_camera
import cv2


def main():
    print(f"Trying to open camera index {config.CAMERA_INDEX}...")
    cap = open_camera()
    if cap is None:
        print("FAILED to open the camera or get a usable frame.")
        print("  1. Close other apps using the webcam (Zoom/Teams/Camera app).")
        print("  2. Windows Settings > Privacy & security > Camera -> allow desktop apps.")
        print("  3. Try a different CAMERA_INDEX in config.py.")
        sys.exit(1)
    print("Camera opened. Showing live preview -- press 'q' to quit.\n")
    frame_count = 0
    start = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_count += 1
        elapsed = time.time() - start
        fps = frame_count / elapsed if elapsed > 0 else 0
        cv2.putText(frame, f"FPS: {fps:.1f}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imshow("Camera Test - press q to quit", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    print(f"Captured {frame_count} frames (~{fps:.1f} FPS).")


if __name__ == "__main__":
    main()
