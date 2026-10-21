import os, sys, time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from face_reco.camera import open_camera
from face_reco.embedder import get_faces_fast
import cv2
import numpy as np


def main():
    print(f"Opening camera index {config.CAMERA_INDEX}...")
    cap = open_camera()
    if cap is None:
        print("FAILED to open the camera -- run tools/test_camera.py first.")
        sys.exit(1)
    print("Camera opened. Loading ArcFace detector... this can take a few seconds.\n")

    frame_count = 0
    last_report = time.time()

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            print("Camera stopped returning frames.")
            break
        frame_count += 1
        mean_brightness = float(np.mean(frame))
        faces = get_faces_fast(frame)

        if faces:
            best = faces[0]
            x1, y1, x2, y2 = best.bbox.astype(int)
            color = (0, 200, 0) if best.det_score >= config.ARCFACE_MIN_DET_SCORE else (0, 165, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"score={best.det_score:.3f}", (x1, max(y1 - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        cv2.putText(frame, f"Brightness: {mean_brightness:.1f}  Faces: {len(faces)}", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.imshow("Face Detection Test - press q to quit", frame)

        if time.time() - last_report > 1.0:
            if faces:
                print(f"[frame {frame_count}] brightness={mean_brightness:.1f}  faces={len(faces)}  best_score={faces[0].det_score:.3f}")
            else:
                extra = "  <-- BLANK/DARK frame, likely a camera/driver issue" if mean_brightness < 15 else ""
                print(f"[frame {frame_count}] brightness={mean_brightness:.1f}  faces=0{extra}")
            last_report = time.time()

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
