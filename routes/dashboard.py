import datetime
from flask import Blueprint, render_template, request, jsonify
from database.db import query_all, query_one
from routes.auth import login_required

dashboard_bp = Blueprint("dashboard", __name__)


def get_attendance_trend_data(start_str=None, end_str=None):
    """
    Computes daily distinct student attendance counts for any specified date range.
    Uses actual attendance records from the database.
    Returns: (trend_list, has_data, error_message, resolved_start_str, resolved_end_str)
    """
    today = datetime.date.today()

    if not end_str or not end_str.strip():
        end_date = today
        resolved_end = end_date.isoformat()
    else:
        try:
            end_date = datetime.date.fromisoformat(end_str.strip())
            resolved_end = end_date.isoformat()
        except ValueError:
            return [], False, "Invalid End Date format (expected YYYY-MM-DD).", start_str, end_str

    if not start_str or not start_str.strip():
        start_date = end_date - datetime.timedelta(days=6)
        resolved_start = start_date.isoformat()
    else:
        try:
            start_date = datetime.date.fromisoformat(start_str.strip())
            resolved_start = start_date.isoformat()
        except ValueError:
            return [], False, "Invalid Start Date format (expected YYYY-MM-DD).", start_str, end_str

    if start_date > end_date:
        return [], False, "Start Date cannot be after End Date.", resolved_start, resolved_end

    # Query attendance grouped by date for the selected date range
    rows = query_all(
        """
        SELECT date, COUNT(DISTINCT student_id) AS c
        FROM attendance
        WHERE date >= ? AND date <= ?
        GROUP BY date
        ORDER BY date ASC
        """,
        (resolved_start, resolved_end),
    )
    date_map = {r["date"]: r["c"] for r in rows}

    trend = []
    has_data = False
    cur = start_date
    while cur <= end_date:
        d_str = cur.isoformat()
        c = date_map.get(d_str, 0)
        if c > 0:
            has_data = True
        trend.append({"date": d_str, "count": c})
        cur += datetime.timedelta(days=1)

    return trend, has_data, None, resolved_start, resolved_end


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

    # Date-range attendance trend (defaults to recent 7 days, supports any custom range)
    req_start = request.args.get("start_date")
    req_end = request.args.get("end_date")
    trend, has_trend_data, trend_error, start_date, end_date = get_attendance_trend_data(req_start, req_end)

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

    db_bounds = query_one("SELECT MIN(date) AS min_d, MAX(date) AS max_d FROM attendance")
    min_available_date = db_bounds["min_d"] if db_bounds and db_bounds["min_d"] else (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    max_available_date = db_bounds["max_d"] if db_bounds and db_bounds["max_d"] else today

    return render_template(
        "dashboard.html", at_risk=at_risk, model_info=model_info, total_students=total_students,
        present_today=present_today, absent_today=absent_today, session_held_today=session_held_today,
        today_attendance_pct=today_attendance_pct, overall_attendance_pct=overall_attendance_pct,
        risk_counts=risk_counts, trend=trend, section_stats=section_stats,
        start_date=start_date, end_date=end_date, has_trend_data=has_trend_data, trend_error=trend_error,
        min_available_date=min_available_date, max_available_date=max_available_date,
    )


@dashboard_bp.route("/dashboard/attendance-trend")
@login_required
def attendance_trend_api():
    """Dynamic JSON endpoint for asynchronous date-range attendance chart updates."""
    req_start = request.args.get("start_date")
    req_end = request.args.get("end_date")
    trend, has_data, err_msg, resolved_start, resolved_end = get_attendance_trend_data(req_start, req_end)

    if err_msg:
        return jsonify({"ok": False, "error": err_msg}), 400

    total_attendance = sum(t["count"] for t in trend)
    avg_daily = round(total_attendance / len(trend), 1) if trend else 0.0
    peak_count = max((t["count"] for t in trend), default=0)

    return jsonify({
        "ok": True,
        "labels": [t["date"] for t in trend],
        "counts": [t["count"] for t in trend],
        "has_data": has_data,
        "start_date": resolved_start,
        "end_date": resolved_end,
        "total_days": len(trend),
        "total_attendance": total_attendance,
        "avg_daily": avg_daily,
        "peak_count": peak_count,
    })

