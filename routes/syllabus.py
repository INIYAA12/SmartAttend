"""
Syllabus Management: add/list/delete subjects ONCE, globally. Every other
place a subject is needed (Marks entry, Live Attendance, Reports) reads
from this same global list -- no more per-section subject duplication.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from database.db import query_all, query_one, execute
from routes.auth import login_required, roles_required
from services import audit

syllabus_bp = Blueprint("syllabus", __name__)


@syllabus_bp.route("/syllabus")
@login_required
def syllabus_list():
    subjects = query_all("SELECT * FROM subjects ORDER BY subject_name")
    return render_template("syllabus.html", subjects=subjects)


@syllabus_bp.route("/syllabus/add", methods=["POST"])
@roles_required("admin")
def add_subject():
    code = request.form.get("subject_code", "").strip()
    name = request.form.get("subject_name", "").strip()

    if not code or not name:
        flash("Subject Code and Subject Name are both required.", "danger")
        return redirect(url_for("syllabus.syllabus_list"))

    existing = query_one("SELECT id FROM subjects WHERE subject_code = ?", (code,))
    if existing:
        flash(f"A subject with code '{code}' already exists.", "danger")
        return redirect(url_for("syllabus.syllabus_list"))

    execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)", (code, name))
    audit.log_event("subject.add", "subject", code, details={"name": name})
    flash(f"Subject '{name}' added — it's now available everywhere a subject is needed.", "success")
    return redirect(url_for("syllabus.syllabus_list"))


@syllabus_bp.route("/syllabus/<int:subject_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_subject(subject_id):
    in_use_marks = query_one("SELECT COUNT(*) AS c FROM marks WHERE subject_id = ?", (subject_id,))["c"]
    in_use_attendance = query_one("SELECT COUNT(*) AS c FROM attendance WHERE subject_id = ?", (subject_id,))["c"]

    if in_use_marks or in_use_attendance:
        flash(
            f"Can't delete this subject — it has {in_use_marks} mark record(s) and "
            f"{in_use_attendance} attendance record(s) already tied to it. Remove those first "
            "if you really need to delete it.",
            "danger",
        )
        return redirect(url_for("syllabus.syllabus_list"))

    execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    audit.log_event("subject.delete", "subject", subject_id)
    flash("Subject deleted.", "info")
    return redirect(url_for("syllabus.syllabus_list"))
