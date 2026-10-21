"""
Camera worker.

Previously each browser request opened the camera and ran the whole
detect/recognise loop inside a streaming response -- capture speed was tied
to one HTTP connection, a page refresh restarted the camera, and two
viewers would fight over the device.

Now a single background thread owns the camera. It reads frames, hands
each to a *processor* (registration or attendance logic), and publishes the
latest annotated JPEG. The HTTP stream just serves that JPEG, so any number
of viewers can watch, refreshing the page doesn't touch the camera, and
capture runs at its own pace.
"""

import threading
import time

import cv2
import numpy as np

from face_reco import camera as camera_module
from core.logging_setup import get_logger

log = get_logger("camera")


def _message_jpeg(message):
    img = np.zeros((480, 640, 3), dtype="uint8")
    cv2.putText(img, message[:60], (15, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    ok, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


class CameraSession:
    """One capture thread bound to one processor object that exposes
    process(frame) -> annotated frame, plus optional `finished` / on_stop()."""

    def __init__(self, kind, processor, jpeg_quality=80):
        self.kind = kind
        self.processor = processor
        self.error = None
        self.running = False
        self.frames = 0
        self.started_at = None
        self._quality = jpeg_quality
        self._latest = _message_jpeg("Starting camera...")
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self.running = True
        self.started_at = time.time()
        self._thread = threading.Thread(target=self._run, name=f"camera-{self.kind}", daemon=True)
        self._thread.start()

    def stop(self, join=True):
        self._stop.set()
        if join and self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def latest_jpeg(self):
        with self._lock:
            return self._latest

    def _publish(self, jpeg):
        with self._lock:
            self._latest = jpeg
            self.frames += 1

    def _run(self):
        cap = None
        try:
            cap = camera_module.open_camera()
            if cap is None:
                self.error = ("Could not access the webcam. Close other apps using it, check Windows camera "
                              "privacy settings, or try a different CAMERA_INDEX in config.py.")
                self._publish(_message_jpeg("Camera unavailable"))
                log.error(self.error)
                return
            log.info("Camera session started: %s", self.kind)
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    self.error = "Webcam stopped returning frames."
                    break
                annotated = self.processor.process(frame)
                ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
                if ok:
                    self._publish(buf.tobytes())
                if getattr(self.processor, "finished", False):
                    break
                time.sleep(0.005)  # yield the GIL; detection dominates frame time anyway
        except Exception as exc:  # a processor bug must not leave a zombie session
            log.exception("Camera session %s crashed", self.kind)
            self.error = f"Camera session crashed: {exc}"
        finally:
            if cap is not None:
                cap.release()
            self.running = False
            on_stop = getattr(self.processor, "on_stop", None)
            if on_stop:
                try:
                    on_stop()
                except Exception:
                    log.exception("Processor on_stop failed")
            log.info("Camera session ended: %s", self.kind)


class SessionManager:
    """Only one physical camera exists, so only one session runs at a time:
    starting a new one cleanly stops the previous."""

    def __init__(self):
        self._lock = threading.RLock()
        self.current = None

    def start(self, session):
        with self._lock:
            if self.current is not None and self.current.running:
                self.current.stop()
            self.current = session
            session.start()
            return session

    def stop(self):
        with self._lock:
            if self.current is not None:
                self.current.stop()

    def is_running(self, kind=None):
        cur = self.current
        return bool(cur and cur.running and (kind is None or cur.kind == kind))


_manager = SessionManager()


def get_manager():
    return _manager


def stream_frames(manager=None, fps=15):
    """MJPEG generator: serves the worker's latest frame to one HTTP client."""
    manager = manager or _manager
    session = manager.current
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    if session is None:
        yield boundary + _message_jpeg("No active camera session") + b"\r\n"
        return
    last = -1
    delay = 1.0 / fps
    while True:
        if session.frames != last:
            last = session.frames
            yield boundary + session.latest_jpeg() + b"\r\n"
        if not session.running:
            yield boundary + session.latest_jpeg() + b"\r\n"  # final frame
            return
        time.sleep(delay)
