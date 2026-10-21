"""
End-to-end check with the REAL ArcFace model (insightface buffalo_l), a real
photo, a fake camera, the background camera worker, and the real database.
Skipped automatically if insightface or its model weights are unavailable
(first run needs internet to download ~280 MB).
"""
import os, sys, time, unittest
import numpy as np
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tests.helpers import isolate

try:
    import cv2
    import insightface
    from face_reco.embedder import get_faces
    _PHOTO = cv2.imread(os.path.join(os.path.dirname(insightface.__file__), "data", "images", "t1.jpg"))
    _FACES = get_faces(_PHOTO)          # loads/downloads the model once
    AVAILABLE = _PHOTO is not None and len(_FACES) >= 3
except Exception:
    AVAILABLE = False


class PhotoCam:
    """Replays a crop around one detected face, forever."""
    def __init__(self, frame):
        self.frame = frame
    def read(self):
        time.sleep(0.01)
        return True, self.frame.copy()
    def release(self):
        pass


def crop_around(face, pad=70):
    x1, y1, x2, y2 = [int(v) for v in face.bbox]
    h, w = _PHOTO.shape[:2]
    return _PHOTO[max(0, y1 - pad):min(h, y2 + pad), max(0, x1 - pad):min(w, x2 + pad)]


@unittest.skipUnless(AVAILABLE, "insightface model not available")
class RealModelEndToEnd(unittest.TestCase):
    def setUp(self):
        isolate()
        from database.db import execute
        for sid in ("PERSON_A", "PERSON_B", "PERSON_C"):
            execute("INSERT INTO students (student_id, name) VALUES (?, ?)", (sid, sid))
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES ('C1', 'Subj')")
        import face_reco.camera as cam
        self.cam, self._open = cam, cam.open_camera
        self._interval = config.FACE_SAMPLES_PER_STUDENT

    def tearDown(self):
        self.cam.open_camera = self._open
        config.FACE_SAMPLES_PER_STUDENT = self._interval

    def _register(self, student_id, face):
        import face_reco.registration as reg
        from face_reco.camera_worker import CameraSession
        reg.SAVE_INTERVAL = 0
        self.cam.open_camera = lambda: PhotoCam(crop_around(face))
        proc = reg.RegistrationProcessor(student_id, target=2)
        session = CameraSession("registration", proc)
        session.start()
        session._thread.join(120)
        self.assertTrue(proc.status()["done"], proc.status())

    def test_register_two_people_then_recognise_each_and_reject_a_third(self):
        from face_reco import recognizer
        from face_reco.camera_worker import CameraSession
        import face_reco.attendance_camera as ac
        from database.db import query_all, query_one

        self._register("PERSON_A", _FACES[0])
        self._register("PERSON_B", _FACES[1])
        # registration finalised: DB flag set and gallery rebuilt automatically
        self.assertEqual(query_one("SELECT face_registered FROM students WHERE student_id='PERSON_A'")[0], 1)
        info = recognizer.gallery_info()
        self.assertEqual((info["students"], info["samples"]), (2, 4))

        def watch(face):
            self.cam.open_camera = lambda: PhotoCam(crop_around(face))
            proc = ac.AttendanceProcessor(1)
            s = CameraSession("attendance", proc)
            s.start()
            deadline = time.time() + 60
            while time.time() < deadline and not (proc.marked or proc.error):
                time.sleep(0.1)
            s.stop()
            return proc

        a = watch(_FACES[0]); self.assertEqual(a.marked, {"PERSON_A"})
        b = watch(_FACES[1]); self.assertEqual(b.marked, {"PERSON_B"})

        # a third, unregistered person must NOT be marked
        self.cam.open_camera = lambda: PhotoCam(crop_around(_FACES[2]))
        stranger = ac.AttendanceProcessor(1)
        s = CameraSession("attendance", stranger)
        s.start(); time.sleep(8); s.stop()
        self.assertEqual(stranger.marked, set())

        rows = query_all("SELECT student_id FROM attendance ORDER BY student_id")
        self.assertEqual([r["student_id"] for r in rows], ["PERSON_A", "PERSON_B"])


if __name__ == "__main__":
    unittest.main()
