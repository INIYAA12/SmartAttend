"""
Live attendance.

AttendanceProcessor runs inside the camera worker. Every frame uses the
cheap detection-only path to feed the centroid tracker; the heavier
detection+recognition call runs only when a tracked face is new or due for
a periodic re-check (config.RECOGNIZE_EVERY_N_FRAMES). Duplicate marks are
prevented twice: an in-memory set, and the database UNIQUE constraint
(see services/attendance_service.py).
"""

import os
import sys

import cv2

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from face_reco.embedder import largest_face_fast, largest_face
from face_reco.recognizer import recognize_embedding, NoTrainingDataError
from face_reco.tracker import CentroidTracker
from face_reco.camera_worker import CameraSession, get_manager
from services.attendance_service import mark_attendance


class AttendanceProcessor:
    kind = "attendance"

    def __init__(self, subject_id):
        self.subject_id = subject_id
        self.finished = False
        self.error = None
        self.marked = set()
        self.last_recognized = None
        self._tracker = CentroidTracker(max_distance=80)
        self._since = {}

    def status(self):
        return {"subject_id": self.subject_id, "marked_count": len(self.marked),
                "marked_students": sorted(self.marked), "last_recognized": self.last_recognized,
                "error": self.error}

    def process(self, frame):
        fast = largest_face_fast(frame)
        bbox = None
        if fast is not None:
            x1, y1, x2, y2 = fast.bbox.astype(int)
            bbox = (int(x1), int(y1), int(x2 - x1), int(y2 - y1))

        track_id = self._tracker.update(bbox)
        if bbox is None or track_id is None:
            cv2.putText(frame, "No face detected", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 220), 2)
            return frame

        x, y, w, h = bbox
        self._since.setdefault(track_id, config.RECOGNIZE_EVERY_N_FRAMES)
        needs = (self._tracker.get_identity(track_id) is None
                 or self._since[track_id] >= config.RECOGNIZE_EVERY_N_FRAMES)

        similarity = None
        if needs:
            student_id = None
            full = largest_face(frame)  # heavier call, only here
            if full is not None:
                try:
                    student_id, similarity = recognize_embedding(full.normed_embedding)
                except NoTrainingDataError as exc:
                    self.error = str(exc)
            self._tracker.set_identity(track_id, student_id)
            self._since[track_id] = 0
        else:
            student_id = self._tracker.get_identity(track_id)
            self._since[track_id] += 1

        if student_id:
            label = student_id + (f" ({similarity:.2f})" if similarity is not None else "")
            color = (0, 200, 0)
            if student_id not in self.marked:
                newly = mark_attendance(student_id, self.subject_id)
                self.marked.add(student_id)
                self.last_recognized = student_id
                if newly:
                    label = f"MARKED: {label}"
        else:
            label, color = "Unknown", (0, 0, 220)

        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, label, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return frame


_processor = None


def start(subject_id):
    global _processor
    _processor = AttendanceProcessor(subject_id)
    get_manager().start(CameraSession("attendance", _processor))
    return _processor


def get_session_status():
    if _processor is None:
        return {"subject_id": None, "marked_count": 0, "marked_students": [], "last_recognized": None, "error": None}
    status = _processor.status()
    session = get_manager().current
    if session is not None and session.kind == "attendance" and session.error and not status["error"]:
        status["error"] = session.error
    return status


def stop():
    get_manager().stop()
