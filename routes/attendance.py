import csv, io
from flask import Blueprint, render_template, request, Response
from database.db import query_all
from routes.auth import login_required

attendance_bp = Blueprint("attendance", __name__)


def _filtered_rows():
    date = request.args.get("date", "").strip()
    student_id = request.args.get("student_id", "").strip()
    subject_id = request.args.get("subject_id", "").strip()
    section = request.args.get("section", "").strip()

    query = """
        SELECT a.id, a.student_id, st.name AS student_name, sub.subject_name,
               a.date, a.time, a.status, st.section
        FROM attendance a
        JOIN students st ON a.student_id = st.student_id
        JOIN subjects sub ON a.subject_id = sub.id
        WHERE 1=1
    """
    params = []
    if date:
        query += " AND a.date = ?"; params.append(date)
    if student_id:
        query += " AND a.student_id = ?"; params.append(student_id)
    if subject_id:
        query += " AND a.subject_id = ?"; params.append(subject_id)
    if section:
        query += " AND st.section = ?"; params.append(section)
    query += " ORDER BY a.date DESC, a.time DESC"
    return query_all(query, tuple(params))


@attendance_bp.route("/attendance")
@login_required
def records():
    rows = _filtered_rows()
    students = query_all("SELECT student_id, name FROM students ORDER BY name")
    subjects = query_all("SELECT id, subject_name FROM subjects ORDER BY subject_name")
    return render_template("attendance.html", rows=rows, students=students, subjects=subjects, filters=request.args)


@attendance_bp.route("/attendance/export.csv")
@login_required
def export_csv():
    rows = _filtered_rows()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Student ID", "Student Name", "Subject", "Date", "Time", "Status"])
    for r in rows:
        writer.writerow([r["student_id"], r["student_name"], r["subject_name"], r["date"], r["time"], r["status"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=attendance_export.csv"})
