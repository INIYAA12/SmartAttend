from flask import Blueprint, render_template, redirect, url_for, flash, Response, jsonify, request

from database.db import query_all, query_one
from routes.auth import login_required
from face_reco import registration, recognizer, attendance_camera
from face_reco.camera_worker import stream_frames, get_manager
from face_reco.recognizer import NoTrainingDataError
from services import audit

face_bp = Blueprint("face", __name__)


@face_bp.route("/face/register")
@login_required
def register_page():
    students = query_all("SELECT * FROM students ORDER BY name")
    return render_template("face_registration.html", students=students)


@face_bp.route("/face/register/start", methods=["POST"])
@login_required
def register_start():
    student_id = request.form.get("student_id", "").strip()
    if not query_one("SELECT 1 FROM students WHERE student_id = ?", (student_id,)):
        return jsonify({"ok": False, "error": "Student not found."}), 404
    registration.start(student_id)
    audit.log_event("face.register_start", "student", student_id)
    return jsonify({"ok": True})


@face_bp.route("/face/stream")
@login_required
def stream():
    """MJPEG view of whichever camera session is active."""
    resp = Response(stream_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Accel-Buffering"] = "no"  # keep nginx from buffering the stream
    return resp


@face_bp.route("/face/stop", methods=["POST"])
@login_required
def stop():
    get_manager().stop()
    return jsonify({"ok": True})


@face_bp.route("/face/registration_status")
@login_required
def registration_status():
    return jsonify(registration.get_status())


@face_bp.route("/face/train", methods=["POST"])
@login_required
def train_recognizer_route():
    try:
        result = recognizer.train_recognizer()
        audit.log_event("face.gallery_build", details=result)
        flash(f"Face gallery rebuilt: {result['total_samples']} samples across "
              f"{result['students_trained']} students ({result['backend']} index).", "success")
    except NoTrainingDataError as e:
        flash(str(e), "danger")
    return redirect(url_for("face.register_page"))


@face_bp.route("/face/live_attendance")
@face_bp.route("/face/attendance")
@login_required
def live_attendance_page():
    subjects = query_all("SELECT * FROM subjects ORDER BY subject_name")
    return render_template("live_attendance.html", subjects=subjects)


@face_bp.route("/face/attendance/start", methods=["POST"])
@login_required
def attendance_start():
    subject_id = request.form.get("subject_id", type=int)
    if not subject_id or not query_one("SELECT 1 FROM subjects WHERE id = ?", (subject_id,)):
        return jsonify({"ok": False, "error": "Choose a valid subject."}), 400
    attendance_camera.start(subject_id)
    audit.log_event("attendance.session_start", "subject", subject_id)
    return jsonify({"ok": True})


@face_bp.route("/face/attendance_status")
@login_required
def attendance_status():
    return jsonify(attendance_camera.get_session_status())
