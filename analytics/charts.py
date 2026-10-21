import io
import os
import sys
import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import query_all, query_one

COLOR_PRIMARY = "#2f5d8c"
COLOR_RISK = {"Low": "#2e7d32", "Medium": "#ef6c00", "High": "#c62828"}
COLOR_PURPLE = "#6a4c93"


def _fig_to_png_bytes(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _empty_state_figure(message, figsize=(7, 4)):
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=13, color="#666")
    return fig


def attendance_trend_figure(days=7, section=None, subject_id=None):
    trend = []
    for i in range(days - 1, -1, -1):
        day = (datetime.date.today() - datetime.timedelta(days=i)).isoformat()
        query = "SELECT COUNT(DISTINCT a.student_id) AS c FROM attendance a JOIN students s ON a.student_id = s.student_id WHERE a.date = ?"
        params = [day]
        if section:
            query += " AND s.section = ?"
            params.append(section)
        if subject_id:
            query += " AND a.subject_id = ?"
            params.append(subject_id)
        count = query_one(query, tuple(params))["c"]
        trend.append((day, count))
    dates = [d for d, _ in trend]
    counts = [c for _, c in trend]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(dates, counts, marker="o", color=COLOR_PRIMARY, linewidth=2)
    ax.fill_between(range(len(dates)), counts, alpha=0.15, color=COLOR_PRIMARY)
    title = f"Attendance — last {days} days"
    if section:
        title += f" (Section {section})"
    ax.set_title(title)
    ax.set_ylabel("Students present")
    ax.set_ylim(bottom=0)
    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels(dates, rotation=40, ha="right")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return fig


def risk_distribution_figure(section=None):
    query = """
        SELECT p.risk_level, COUNT(*) AS c
        FROM latest_predictions p
        JOIN students s ON p.student_id = s.student_id
    """
    params = []
    if section:
        query += " WHERE s.section = ?"
        params.append(section)
    query += " GROUP BY p.risk_level"
    rows = query_all(query, tuple(params))

    counts = {"Low": 0, "Medium": 0, "High": 0}
    for r in rows:
        counts[r["risk_level"]] = r["c"]
    total = sum(counts.values())
    if total == 0:
        return _empty_state_figure("No predictions yet for selected criteria.", figsize=(5, 5))

    labels = [k for k, v in counts.items() if v > 0]
    values = [counts[k] for k in labels]
    colors = [COLOR_RISK[l] for l in labels]

    fig, ax = plt.subplots(figsize=(5, 5))
    ax.pie(values, labels=labels, autopct="%1.0f%%", colors=colors, startangle=90,
           wedgeprops={"edgecolor": "white", "linewidth": 1.5})
    title = "Student Risk Distribution"
    if section:
        title += f" (Section {section})"
    ax.set_title(title)
    fig.tight_layout()
    return fig


def attendance_by_subject_figure(section=None, start_date=None, end_date=None):
    query = """
        SELECT sub.subject_name, COUNT(a.id) AS total
        FROM subjects sub
        LEFT JOIN attendance a ON a.subject_id = sub.id
    """
    joins = []
    params = []
    if start_date:
        joins.append("a.date >= ?")
        params.append(start_date)
    if end_date:
        joins.append("a.date <= ?")
        params.append(end_date)
    if section:
        query += " LEFT JOIN students s ON a.student_id = s.student_id"
        joins.append("s.section = ?")
        params.append(section)

    if joins:
        query += " AND " + " AND ".join(joins)

    query += " GROUP BY sub.subject_name ORDER BY sub.subject_name"
    rows = query_all(query, tuple(params))
    if not rows:
        return _empty_state_figure("No subject attendance found for criteria.", figsize=(8, 4.5))

    names = [r["subject_name"] for r in rows]
    totals = [r["total"] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(names, totals, color=COLOR_PRIMARY)
    title = "Attendance Sessions Marked per Subject"
    if section:
        title += f" (Section {section})"
    ax.set_title(title)
    ax.set_ylabel("Sessions marked")
    plt.setp(ax.get_xticklabels(), rotation=40, ha="right")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    return fig


def feature_importance_figure():
    from ml import registry
    info = registry.get_current_version_info()
    if not info:
        return _empty_state_figure("No trained model yet.\nTrain a model under ML Training first.")

    if info.get("feature_importances"):
        items = sorted(info["feature_importances"].items(), key=lambda kv: kv[1])
        labels = [k.replace("_", " ").title() for k, _ in items]
        values = [v * 100 for _, v in items]
        xlabel = "Importance (%)"
        title_prefix = "Feature Importance"
    elif info.get("coefficients"):
        items = sorted(info["coefficients"].items(), key=lambda kv: abs(kv[1]))
        labels = [k.replace("_", " ").title() for k, _ in items]
        values = [v for _, v in items]
        xlabel = "Coefficient (standardized)"
        title_prefix = "Feature Coefficients"
    else:
        return _empty_state_figure("This model type doesn't expose per-feature weights.")

    fig, ax = plt.subplots(figsize=(7, 3.5))
    colors = [COLOR_PURPLE if v >= 0 else "#c62828" for v in values]
    ax.barh(labels, values, color=colors)
    ax.set_xlabel(xlabel)
    ax.axvline(0, color="#333", linewidth=0.8)
    ax.set_title(f"{title_prefix} — {info.get('selected_model', '').replace('_', ' ').title()} ({info['version']})")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    return fig


def png_bytes_for(chart_name, filters=None):
    filters = filters or {}
    sec = filters.get("section")
    sub_id = filters.get("subject_id")
    start = filters.get("start_date")
    end = filters.get("end_date")

    if chart_name == "attendance_trend":
        fig = attendance_trend_figure(days=7, section=sec, subject_id=sub_id)
    elif chart_name == "risk_distribution":
        fig = risk_distribution_figure(section=sec)
    elif chart_name == "attendance_by_subject":
        fig = attendance_by_subject_figure(section=sec, start_date=start, end_date=end)
    elif chart_name == "feature_importance":
        fig = feature_importance_figure()
    else:
        raise ValueError(f"Unknown chart: {chart_name}")

    return _fig_to_png_bytes(fig)


def _summary_page_figure(filters=None):
    filters = filters or {}
    sec = filters.get("section")
    sub_id = filters.get("subject_id")
    start = filters.get("start_date")
    end = filters.get("end_date")

    if sec:
        total_students = query_one("SELECT COUNT(*) AS c FROM students WHERE section = ?", (sec,))["c"]
    else:
        total_students = query_one("SELECT COUNT(*) AS c FROM students")["c"]

    att_q = "SELECT COUNT(*) AS c FROM attendance a JOIN students s ON a.student_id = s.student_id WHERE 1=1"
    att_p = []
    if sec:
        att_q += " AND s.section = ?"; att_p.append(sec)
    if sub_id:
        att_q += " AND a.subject_id = ?"; att_p.append(sub_id)
    if start:
        att_q += " AND a.date >= ?"; att_p.append(start)
    if end:
        att_q += " AND a.date <= ?"; att_p.append(end)
    total_att = query_one(att_q, tuple(att_p))["c"]

    fig, ax = plt.subplots(figsize=(8.5, 11))
    ax.axis("off")
    filter_strs = []
    if sec: filter_strs.append(f"Section: {sec}")
    if sub_id:
        sub_name_row = query_one("SELECT subject_name FROM subjects WHERE id = ?", (sub_id,))
        sub_name = sub_name_row["subject_name"] if sub_name_row else str(sub_id)
        filter_strs.append(f"Subject: {sub_name}")
    if start or end: filter_strs.append(f"Date Range: {start or 'earliest'} to {end or 'latest'}")
    active_filters_text = ", ".join(filter_strs) if filter_strs else "None (All institutional records)"

    lines = [
        "Smart Attendance & Academic Performance Report",
        "=" * 55,
        f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Filters: {active_filters_text}",
        "",
        f"Total students matching criteria: {total_students}",
        f"Attendance sessions recorded: {total_att}",
        "",
        "Generated directly from the live application database.",
    ]
    ax.text(0.05, 0.95, "\n".join(lines), va="top", ha="left", fontsize=12, family="monospace")
    return fig


def generate_pdf_report(filters=None):
    filters = filters or {}
    sec = filters.get("section")
    sub_id = filters.get("subject_id")
    start = filters.get("start_date")
    end = filters.get("end_date")

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        pdf.savefig(_summary_page_figure(filters))
        plt.close("all")

        f1 = attendance_trend_figure(days=7, section=sec, subject_id=sub_id)
        pdf.savefig(f1); plt.close(f1)

        f2 = risk_distribution_figure(section=sec)
        pdf.savefig(f2); plt.close(f2)

        f3 = attendance_by_subject_figure(section=sec, start_date=start, end_date=end)
        pdf.savefig(f3); plt.close(f3)

        f4 = feature_importance_figure()
        pdf.savefig(f4); plt.close(f4)

    buf.seek(0)
    return buf.getvalue()

