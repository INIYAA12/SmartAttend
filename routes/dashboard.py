import datetime
from flask import Blueprint, render_template
from database.db import query_all, query_one
from routes.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@dashboard_bp.route("/dashboard")
@login_required
def index():
    today = datetime.date.today().isoformat()
    total_students = query_one("SELECT COUNT(*) AS c FROM students")["c"]

    # Check if sessions occurred today
    sessions_today = query_one("SELECT COUNT(DISTINCT subject_id) AS c FROM attendance WHERE date = ?", (today,))["c"]
    if sessions_today > 0:
        session_held_today = True
        present_today = query_one("SELECT COUNT(DISTINCT student_id) AS c FROM attendance WHERE date = ?", (today,))["c"]
        expected_today = query_one(
            """
            SELECT COUNT(DISTINCT s.student_id) AS c FROM students s
            WHERE s.section IN (
                SELECT DISTINCT s2.section FROM attendance a
                JOIN students s2 ON a.student_id = s2.student_id
                WHERE a.date = ?
            )
            """, (today,)
        )["c"]
        if expected_today == 0:
            expected_today = total_students
        absent_today = max(expected_today - present_today, 0)
        today_attendance_pct = round((present_today / expected_today) * 100, 1) if expected_today else 0.0
    else:
        session_held_today = False
        present_today = 0
        absent_today = 0
        today_attendance_pct = 0.0

    # Overall Institutional Attendance % across all active students
    from academic.marks import compute_attendance_percentage, compute_marks_average_percentage
    all_students = query_all("SELECT student_id FROM students")
    valid_pcts = [
        p for p in (compute_attendance_percentage(s["student_id"]) for s in all_students)
        if p is not None
    ]
    overall_attendance_pct = round(sum(valid_pcts) / len(valid_pcts), 1) if valid_pcts else 0.0

    # Risk counts
    risk_rows = query_all("SELECT risk_level, COUNT(*) AS c FROM latest_predictions GROUP BY risk_level")
    risk_counts = {"Low": 0, "Medium": 0, "High": 0}
    for row in risk_rows:
        risk_counts[row["risk_level"]] = row["c"]

    # 7-day attendance trend
    trend = []
    for i in range(6, -1, -1):
        day = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        count = query_one("SELECT COUNT(DISTINCT student_id) AS c FROM attendance WHERE date = ?", (day,))["c"]
        trend.append({"date": day, "count": count})

    # Section-wise performance comparison (Phase 9)
    sections_raw = query_all("SELECT DISTINCT section FROM students WHERE section IS NOT NULL AND section != '' ORDER BY section")
    section_stats = []
    for sec_row in sections_raw:
        sec = sec_row["section"]
        sec_students = query_all("SELECT student_id FROM students WHERE section = ?", (sec,))
        sec_student_ids = [s["student_id"] for s in sec_students]

        sec_att = [compute_attendance_percentage(sid) for sid in sec_student_ids]
        valid_att = [p for p in sec_att if p is not None]
        avg_att = round(sum(valid_att) / len(valid_att), 1) if valid_att else 0.0

        sec_marks = [compute_marks_average_percentage(sid) for sid in sec_student_ids]
        valid_marks = [m for m in sec_marks if m is not None]
        avg_marks = round(sum(valid_marks) / len(valid_marks), 1) if valid_marks else 0.0

        high_risk_c = query_one(
            """
            SELECT COUNT(*) AS c FROM latest_predictions p
            JOIN students s ON p.student_id = s.student_id
            WHERE s.section = ? AND p.risk_level = 'High'
            """, (sec,)
        )["c"]

        section_stats.append({
            "section": sec,
            "student_count": len(sec_students),
            "avg_attendance": avg_att,
            "avg_marks": avg_marks,
            "high_risk_count": high_risk_c,
        })

    at_risk = query_all(
        """SELECT p.student_id, s.name, s.section, p.predicted_score, p.risk_level
           FROM latest_predictions p JOIN students s ON s.student_id = p.student_id
           WHERE p.risk_level IN ('High', 'Medium') ORDER BY p.predicted_score ASC LIMIT 6"""
    )
    from ml import registry
    model_info = registry.get_current_version_info()

    return render_template(
        "dashboard.html", at_risk=at_risk, model_info=model_info, total_students=total_students,
        present_today=present_today, absent_today=absent_today, session_held_today=session_held_today,
        today_attendance_pct=today_attendance_pct, overall_attendance_pct=overall_attendance_pct,
        risk_counts=risk_counts, trend=trend, section_stats=section_stats,
    )

