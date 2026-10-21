import csv
import io
import datetime
from flask import Blueprint, render_template, request, Response
from database.db import query_all, query_one
from routes.auth import login_required
from analytics import charts

reports_bp = Blueprint("reports", __name__)


def _parse_report_filters():
    section = request.args.get("section", "").strip()
    subject_id_raw = request.args.get("subject_id", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    subject_id = None
    if subject_id_raw:
        try:
            subject_id = int(subject_id_raw)
        except ValueError:
            pass

    # Date range validation
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    return {
        "section": section,
        "subject_id": subject_id,
        "start_date": start_date,
        "end_date": end_date,
    }


def _get_filtered_at_risk(filters):
    query = """
        SELECT p.student_id, st.name, st.section, p.predicted_score, p.risk_level, p.created_at
        FROM latest_predictions p JOIN students st ON p.student_id = st.student_id
        WHERE p.risk_level IN ('High', 'Medium')
    """
    params = []
    if filters["section"]:
        query += " AND st.section = ?"
        params.append(filters["section"])
    query += " ORDER BY p.predicted_score ASC"
    return query_all(query, tuple(params))


def _get_filtered_student_attendance(filters):
    query = """
        SELECT st.student_id, st.name, st.section, COUNT(a.id) AS sessions_attended
        FROM students st
        LEFT JOIN attendance a ON a.student_id = st.student_id
    """
    join_clauses = []
    params = []
    if filters["subject_id"]:
        join_clauses.append("a.subject_id = ?")
        params.append(filters["subject_id"])
    if filters["start_date"]:
        join_clauses.append("a.date >= ?")
        params.append(filters["start_date"])
    if filters["end_date"]:
        join_clauses.append("a.date <= ?")
        params.append(filters["end_date"])

    if join_clauses:
        query += " AND " + " AND ".join(join_clauses)

    if filters["section"]:
        query += " WHERE st.section = ?"
        params.append(filters["section"])

    query += " GROUP BY st.student_id, st.name, st.section ORDER BY st.name"
    return query_all(query, tuple(params))


def _get_filtered_subject_attendance(filters):
    query = """
        SELECT sub.id, sub.subject_code, sub.subject_name, COUNT(a.id) AS total_marked
        FROM subjects sub
        LEFT JOIN attendance a ON a.subject_id = sub.id
    """
    join_clauses = []
    params = []
    if filters["start_date"]:
        join_clauses.append("a.date >= ?")
        params.append(filters["start_date"])
    if filters["end_date"]:
        join_clauses.append("a.date <= ?")
        params.append(filters["end_date"])
    if filters["section"]:
        query += " LEFT JOIN students st ON a.student_id = st.student_id"
        join_clauses.append("st.section = ?")
        params.append(filters["section"])

    if join_clauses:
        query += " AND " + " AND ".join(join_clauses)

    if filters["subject_id"]:
        query += " WHERE sub.id = ?"
        params.append(filters["subject_id"])

    query += " GROUP BY sub.id, sub.subject_code, sub.subject_name ORDER BY sub.subject_name"
    return query_all(query, tuple(params))


@reports_bp.route("/reports")
@login_required
def reports_page():
    filters = _parse_report_filters()
    at_risk = _get_filtered_at_risk(filters)
    attendance_by_student = _get_filtered_student_attendance(filters)
    attendance_by_subject = _get_filtered_subject_attendance(filters)

    sections = [r["section"] for r in query_all("SELECT DISTINCT section FROM students WHERE section IS NOT NULL ORDER BY section")]
    subjects = query_all("SELECT id, subject_code, subject_name FROM subjects ORDER BY subject_name")

    return render_template(
        "reports.html", at_risk=at_risk, attendance_by_student=attendance_by_student,
        attendance_by_subject=attendance_by_subject, sections=sections, subjects=subjects,
        filters=filters,
    )


@reports_bp.route("/reports/at_risk.csv")
@login_required
def export_at_risk_csv():
    filters = _parse_report_filters()
    rows = _get_filtered_at_risk(filters)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Student ID", "Name", "Section", "Predicted Score", "Risk Level", "Predicted On"])
    for r in rows:
        writer.writerow([r["student_id"], r["name"], r["section"] or "", r["predicted_score"], r["risk_level"], r["created_at"]])
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=at_risk_students.csv"},
    )


@reports_bp.route("/reports/chart/<chart_name>.png")
@login_required
def chart_png(chart_name):
    filters = _parse_report_filters()
    try:
        png = charts.png_bytes_for(chart_name, filters)
    except ValueError:
        return "Unknown chart", 404
    return Response(png, mimetype="image/png", headers={"Cache-Control": "no-store"})


@reports_bp.route("/reports/pdf")
@login_required
def download_pdf():
    filters = _parse_report_filters()
    pdf_bytes = charts.generate_pdf_report(filters)
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=attendance_performance_report.pdf"},
    )

