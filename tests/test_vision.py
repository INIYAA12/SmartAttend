"""Vector index, recognizer, camera worker, and the registration/attendance processors."""
import os, sys, time, threading, unittest
import numpy as np
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tests.helpers import isolate


class FakeFace:
    def __init__(self, emb=None, det=0.9, bbox=(100, 100, 220, 240)):
        self.bbox = np.array(bbox, dtype=float)
        self.det_score = det
        self.normed_embedding = emb


def unit(seed, dim=512):
    v = np.random.default_rng(seed).normal(size=dim).astype("float32")
    return v / np.linalg.norm(v)


BLANK = np.zeros((480, 640, 3), dtype="uint8")


class VectorIndexTests(unittest.TestCase):
    def test_backends_agree_and_round_trip(self):
        from face_reco.vector_index import VectorIndex, faiss_available
        base = np.stack([unit(i) for i in range(6)])
        labels = list("ABCDEF")
        backends = ["numpy"] + (["faiss"] if faiss_available() else [])
        for backend in backends:
            idx = VectorIndex(backend).build(base, labels)
            noisy = base[3] + np.random.default_rng(9).normal(scale=0.005, size=512).astype("float32")
            label, sim = idx.search(noisy)
            self.assertEqual(label, "D")
            self.assertGreater(sim, 0.95)
            import tempfile
            path = os.path.join(tempfile.mkdtemp(), "g.npz")
            idx.save(path)
            self.assertEqual(VectorIndex.load(path, backend).search(noisy)[0], "D")

    def test_unnormalised_input_is_normalised(self):
        from face_reco.vector_index import VectorIndex
        idx = VectorIndex("numpy").build(np.stack([unit(1) * 7.5, unit(2) * 0.2]), ["X", "Y"])
        label, sim = idx.search(unit(1) * 3)
        self.assertEqual(label, "X")
        self.assertAlmostEqual(sim, 1.0, places=4)

    def test_empty_index_and_bad_backend(self):
        from face_reco.vector_index import VectorIndex
        with self.assertRaises(ValueError):
            VectorIndex("numpy").search(unit(1))
        with self.assertRaises(ValueError):
            VectorIndex("bogus")


class RecognizerTests(unittest.TestCase):
    def setUp(self):
        isolate()
        for sid, seed in (("S1", 1), ("S2", 2)):
            d = os.path.join(config.FACES_DIR, sid)
            os.makedirs(d)
            for k in range(3):
                np.save(os.path.join(d, f"{k:03d}.npy"), unit(seed) + np.random.default_rng(k).normal(scale=0.01, size=512).astype("float32"))

    def test_train_and_recognize_known_and_unknown(self):
        from face_reco import recognizer
        info = recognizer.train_recognizer()
        self.assertEqual((info["students_trained"], info["total_samples"]), (2, 6))
        self.assertEqual(recognizer.recognize_embedding(unit(2))[0], "S2")
        label, sim = recognizer.recognize_embedding(unit(99))   # stranger
        self.assertIsNone(label)
        self.assertLess(sim, config.ARCFACE_SIMILARITY_THRESHOLD)

    def test_rebuilding_gallery_invalidates_cache(self):
        from face_reco import recognizer
        recognizer.train_recognizer()
        self.assertEqual(recognizer.recognize_embedding(unit(1))[0], "S1")
        import shutil
        shutil.rmtree(os.path.join(config.FACES_DIR, "S1"))
        time.sleep(0.01)
        recognizer.train_recognizer()
        self.assertIsNone(recognizer.recognize_embedding(unit(1))[0])  # S1 gone after rebuild

    def test_errors_without_data(self):
        from face_reco import recognizer
        import shutil
        shutil.rmtree(config.FACES_DIR)
        with self.assertRaises(recognizer.NoTrainingDataError):
            recognizer.train_recognizer()
        with self.assertRaises(recognizer.NoTrainingDataError):
            recognizer.recognize_embedding(unit(1))


class FakeCap:
    def __init__(self, frames=None):
        self.remaining = frames
        self.released = False

    def read(self):
        if self.remaining is not None:
            if self.remaining <= 0:
                return False, None
            self.remaining -= 1
        time.sleep(0.002)
        return True, BLANK.copy()

    def release(self):
        self.released = True


class FakeProcessor:
    def __init__(self, finish_after=None, boom_at=None):
        self.n, self.finish_after, self.boom_at = 0, finish_after, boom_at
        self.finished, self.stopped = False, False

    def process(self, frame):
        self.n += 1
        if self.boom_at and self.n == self.boom_at:
            raise RuntimeError("processor bug")
        if self.finish_after and self.n >= self.finish_after:
            self.finished = True
        return frame

    def on_stop(self):
        self.stopped = True


class CameraWorkerTests(unittest.TestCase):
    def setUp(self):
        import face_reco.camera as cam
        self.cam = cam
        self._orig = cam.open_camera

    def tearDown(self):
        self.cam.open_camera = self._orig

    def _run(self, proc, cap):
        from face_reco.camera_worker import CameraSession
        self.cam.open_camera = lambda: cap
        s = CameraSession("test", proc)
        s.start()
        s._thread.join(5)
        return s

    def test_session_publishes_jpeg_frames_and_stops_when_processor_finishes(self):
        proc, cap = FakeProcessor(finish_after=5), FakeCap()
        s = self._run(proc, cap)
        self.assertFalse(s.running)
        self.assertGreaterEqual(s.frames, 5)
        self.assertTrue(s.latest_jpeg().startswith(b"\xff\xd8"))
        self.assertTrue(cap.released)
        self.assertTrue(proc.stopped)

    def test_camera_unavailable_sets_clear_error(self):
        s = self._run(FakeProcessor(), None)
        self.assertIn("Could not access the webcam", s.error)
        self.assertFalse(s.running)

    def test_processor_crash_is_contained_and_camera_released(self):
        cap = FakeCap()
        s = self._run(FakeProcessor(boom_at=3), cap)
        self.assertIn("crashed", s.error)
        self.assertTrue(cap.released)
        self.assertFalse(s.running)

    def test_dead_camera_stops_session(self):
        s = self._run(FakeProcessor(), FakeCap(frames=3))
        self.assertIn("stopped returning frames", s.error)

    def test_manager_runs_one_session_at_a_time_and_stop_works(self):
        from face_reco.camera_worker import CameraSession, SessionManager
        self.cam.open_camera = lambda: FakeCap()
        mgr = SessionManager()
        first = mgr.start(CameraSession("registration", FakeProcessor()))
        time.sleep(0.05)
        self.assertTrue(first.running)
        second = mgr.start(CameraSession("attendance", FakeProcessor()))
        time.sleep(0.05)
        self.assertFalse(first.running)
        self.assertTrue(mgr.is_running("attendance"))
        mgr.stop()
        time.sleep(0.05)
        self.assertFalse(mgr.is_running())

    def test_stream_serves_multipart_frames_to_multiple_viewers(self):
        from face_reco.camera_worker import CameraSession, SessionManager, stream_frames
        self.cam.open_camera = lambda: FakeCap()
        mgr = SessionManager()
        mgr.start(CameraSession("t", FakeProcessor(finish_after=30)))
        results = []
        def viewer():
            chunks = list(stream_frames(mgr, fps=200))
            results.append(chunks)
        threads = [threading.Thread(target=viewer) for _ in range(2)]
        [t.start() for t in threads]; [t.join(10) for t in threads]
        self.assertEqual(len(results), 2)
        for chunks in results:
            self.assertTrue(chunks and chunks[0].startswith(b"--frame\r\nContent-Type: image/jpeg"))

    def test_stream_with_no_session_returns_placeholder(self):
        from face_reco.camera_worker import SessionManager, stream_frames
        chunks = list(stream_frames(SessionManager()))
        self.assertEqual(len(chunks), 1)


class RegistrationProcessorTests(unittest.TestCase):
    def setUp(self):
        isolate()
        import face_reco.registration as reg
        self.reg = reg
        self._saved = (reg.get_faces_fast, reg.largest_face, reg.SAVE_INTERVAL)
        reg.SAVE_INTERVAL = 0

    def tearDown(self):
        self.reg.get_faces_fast, self.reg.largest_face, self.reg.SAVE_INTERVAL = self._saved

    def test_saves_embeddings_only_and_completes_once(self):
        reg = self.reg
        reg.get_faces_fast = lambda f: [FakeFace()]
        reg.largest_face = lambda f: FakeFace(emb=unit(5))
        done = []
        p = reg.RegistrationProcessor("S1", target=3, on_complete=lambda sid, n: done.append((sid, n)))
        for _ in range(6):
            p.process(BLANK.copy())
        self.assertTrue(p.finished)
        self.assertEqual(done, [("S1", 3)])
        files = sorted(os.listdir(os.path.join(config.FACES_DIR, "S1")))
        self.assertEqual(files, ["000.npy", "001.npy", "002.npy"])   # embeddings, never images
        self.assertEqual(p.status()["done"], True)

    def test_no_face_and_low_confidence_save_nothing(self):
        reg = self.reg
        p = reg.RegistrationProcessor("S2", target=3, on_complete=None)
        reg.get_faces_fast = lambda f: []
        p.process(BLANK.copy())
        reg.get_faces_fast = lambda f: [FakeFace(det=0.2)]
        p.process(BLANK.copy())
        self.assertEqual(p.count, 0)
        self.assertEqual(p.last_det_score, 0.2)

    def test_expensive_path_runs_only_when_saving(self):
        reg = self.reg
        calls = {"fast": 0, "full": 0}
        def fast(f): calls["fast"] += 1; return [FakeFace()]
        def full(f): calls["full"] += 1; return FakeFace(emb=unit(1))
        reg.get_faces_fast, reg.largest_face = fast, full
        reg.SAVE_INTERVAL = 3600  # after the first save, no more saves due
        p = reg.RegistrationProcessor("S3", target=50, on_complete=None)
        for _ in range(10):
            p.process(BLANK.copy())
        self.assertEqual(calls["fast"], 10)
        self.assertEqual(calls["full"], 1)

    def test_finalize_marks_student_and_rebuilds_gallery(self):
        from database.db import execute, query_one
        execute("INSERT INTO students (student_id, name) VALUES ('S1', 'One')")
        d = os.path.join(config.FACES_DIR, "S1"); os.makedirs(d)
        np.save(os.path.join(d, "000.npy"), unit(1))
        self.reg.finalize_registration("S1", 1)
        self.assertEqual(query_one("SELECT face_registered FROM students WHERE student_id='S1'")[0], 1)
        self.assertTrue(os.path.exists(config.FACE_GALLERY_PATH))


class AttendanceProcessorTests(unittest.TestCase):
    def setUp(self):
        isolate()
        from database.db import execute
        execute("INSERT INTO students (student_id, name) VALUES ('S1', 'One')")
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES ('C1', 'Subj')")
        import face_reco.attendance_camera as ac
        self.ac = ac
        self._saved = (ac.largest_face_fast, ac.largest_face, ac.recognize_embedding, config.RECOGNIZE_EVERY_N_FRAMES)
        config.RECOGNIZE_EVERY_N_FRAMES = 5

    def tearDown(self):
        ac = self.ac
        ac.largest_face_fast, ac.largest_face, ac.recognize_embedding, config.RECOGNIZE_EVERY_N_FRAMES = self._saved

    def test_marks_recognised_student_once_and_skips_heavy_path_between_checks(self):
        ac = self.ac
        full_calls = {"n": 0}
        ac.largest_face_fast = lambda f: FakeFace()
        def full(f): full_calls["n"] += 1; return FakeFace(emb=unit(1))
        ac.largest_face = full
        ac.recognize_embedding = lambda e: ("S1", 0.93)
        p = ac.AttendanceProcessor(1)
        for _ in range(30):
            p.process(BLANK.copy())
        from database.db import query_all
        self.assertEqual(len(query_all("SELECT * FROM attendance")), 1)      # no duplicates
        self.assertEqual(p.status()["marked_students"], ["S1"])
        self.assertLess(full_calls["n"], 10)                                  # ~1 per 5 frames, not 30

    def test_unknown_face_is_never_marked(self):
        ac = self.ac
        ac.largest_face_fast = lambda f: FakeFace()
        ac.largest_face = lambda f: FakeFace(emb=unit(9))
        ac.recognize_embedding = lambda e: (None, 0.12)
        p = ac.AttendanceProcessor(1)
        for _ in range(8):
            p.process(BLANK.copy())
        from database.db import query_all
        self.assertEqual(query_all("SELECT * FROM attendance"), [])
        self.assertEqual(p.status()["marked_count"], 0)

    def test_missing_gallery_reported_not_crashed(self):
        ac = self.ac
        from face_reco.recognizer import NoTrainingDataError
        ac.largest_face_fast = lambda f: FakeFace()
        ac.largest_face = lambda f: FakeFace(emb=unit(1))
        def raiser(e): raise NoTrainingDataError("gallery not built")
        ac.recognize_embedding = raiser
        p = ac.AttendanceProcessor(1)
        p.process(BLANK.copy())
        self.assertIn("gallery not built", p.status()["error"])


if __name__ == "__main__":
    unittest.main()
