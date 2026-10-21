"""
Face registration.

RegistrationProcessor holds the per-frame logic (run by the camera worker).
The every-frame check uses the cheap detection-only path; the heavier
detection+recognition call runs only when a sample is actually saved
(about 3x per second). Samples are 512-d embeddings, never face images.
When the target count is reached, the student is marked as registered and
the recognition gallery is rebuilt automatically.
"""

import os
import sys
import time

import cv2
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from face_reco.embedder import get_faces_fast, largest_face
from face_reco.camera_worker import CameraSession, get_manager
from core.logging_setup import get_logger

log = get_logger("registration")
SAVE_INTERVAL = 0.3  # seconds between saved samples (variety of pose/expression)


def _student_dir(student_id):
    d = os.path.join(config.FACES_DIR, student_id)
    os.makedirs(d, exist_ok=True)
    return d


def finalize_registration(student_id, count):
    """Marks the student registered and rebuilds the recognition gallery."""
    from database.db import execute
    from face_reco import recognizer
    execute("UPDATE students SET face_registered = 1 WHERE student_id = ?", (student_id,))
    execute("INSERT INTO face_embeddings (student_id, sample_count) VALUES (?, ?)", (student_id, count))
    try:
        recognizer.train_recognizer()
    except recognizer.NoTrainingDataError:
        log.warning("Gallery rebuild skipped: no samples")


class RegistrationProcessor:
    kind = "registration"

    def __init__(self, student_id, target=None, on_complete=finalize_registration):
        self.student_id = student_id
        self.target = target or config.FACE_SAMPLES_PER_STUDENT
        self.count = 0
        self.finished = False
        self.error = None
        self.last_det_score = None
        self._on_complete = on_complete
        self._last_save = 0.0
        self._dir = _student_dir(student_id)

    def status(self):
        return {"student_id": self.student_id, "count": self.count, "target": self.target,
                "done": self.finished and self.error is None, "error": self.error,
                "last_det_score": self.last_det_score}

    def process(self, frame):
        if self.finished:  # never save past the target, even if called again
            return frame
        faces = get_faces_fast(frame)
        best = faces[0] if faces else None
        self.last_det_score = round(float(best.det_score), 3) if best is not None else None

        if best is not None and best.det_score >= config.ARCFACE_MIN_DET_SCORE:
            x1, y1, x2, y2 = best.bbox.astype(int)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)
            now = time.time()
            if now - self._last_save > SAVE_INTERVAL:
                full = largest_face(frame)  # heavier call, only when saving
                if full is not None:
                    try:
                        np.save(os.path.join(self._dir, f"{self.count:03d}.npy"), full.normed_embedding)
                        self.count += 1
                        self._last_save = now
                    except OSError as exc:
                        self.error = f"Could not save sample to disk: {exc}"
                        self.finished = True
            text, color = f"Face detected: {self.count}/{self.target}", (0, 200, 0)
        elif best is not None:
            x1, y1, x2, y2 = best.bbox.astype(int)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 165, 255), 2)
            text = f"Face too unclear (score {best.det_score:.2f}, need {config.ARCFACE_MIN_DET_SCORE:.2f})"
            color = (0, 165, 255)
        else:
            text, color = "No face detected - center your face in frame", (0, 0, 220)

        if self.count >= self.target and not self.finished:
            self.finished = True
            if self._on_complete:
                self._on_complete(self.student_id, self.count)
            text, color = "Registration complete", (0, 200, 0)

        cv2.putText(frame, text, (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        return frame


_processor = None


def start(student_id, target=None, on_complete=finalize_registration):
    global _processor
    _processor = RegistrationProcessor(student_id, target, on_complete)
    get_manager().start(CameraSession("registration", _processor))
    return _processor


def get_status():
    if _processor is None:
        return {"student_id": None, "count": 0, "target": config.FACE_SAMPLES_PER_STUDENT,
                "done": False, "error": None, "last_det_score": None}
    status = _processor.status()
    session = get_manager().current
    if session is not None and session.kind == "registration" and session.error and not status["error"]:
        status["error"] = session.error  # e.g. camera could not be opened
    return status


def stop():
    get_manager().stop()
