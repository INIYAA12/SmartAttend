"""
Marks entry: pick a Subject (from Syllabus Management) + type any Exam
Name + set one Total Mark for the whole sheet, then a spreadsheet-style
grid to enter each student's obtained mark (percentage auto-calculated).
No "Exam Type" category anywhere.
"""

import io

from flask import Blueprint, render_template, request, redirect, url_for, flash, Response

from database.db import query_all, query_one
from routes.auth import login_required
from services import audit
from academic.marks import upsert_mark, get_marks_for_sheet, export_sheet_csv

academic_bp = Blueprint("academic", __name__)


@academic_bp.route("/academic")
@login_required
def academic_list():
    subjects = query_all("SELECT * FROM subjects ORDER BY subject_name")
    sections = [r["section"] for r in query_all("SELECT DISTINCT section FROM students WHERE section IS NOT NULL ORDER BY section")]

    subject_id = request.args.get("subject_id", type=int)
    exam_name = request.args.get("exam_name", "").strip()
    section = request.args.get("section", "").strip()
    total_marks = request.args.get("total_marks", "").strip()

    sheet_students = []
    existing_total = None

    if subject_id and exam_name:
        students, marks_by_student = get_marks_for_sheet(subject_id, section or None)
        for s in students:
            existing = marks_by_student.get(s["student_id"])
            existing_row = None
            if existing:
                for m in existing:
                    if m["exam_name"] == exam_name:
                        existing_row = m
                        break
            sheet_students.append({
                "student_id": s["student_id"],
                "name": s["name"],
                "roll_number": s["roll_number"],
                "obtained_marks": existing_row["obtained_marks"] if existing_row else "",
                "percentage": existing_row["percentage"] if existing_row else None,
            })
            if existing_row and existing_total is None:
                existing_total = existing_row["total_marks"]

    # Recently used exam names per subject, so the teacher can jump back
    # into a sheet they already started without retyping the exact name.
    recent_exams = []
    if subject_id:
        recent_exams = [
            r["exam_name"] for r in query_all(
                "SELECT DISTINCT exam_name FROM marks WHERE subject_id = ? ORDER BY exam_name",
                (subject_id,),
            )
        ]

    return render_template(
        "academic.html", subjects=subjects, sections=sections,
        selected_subject_id=subject_id, selected_exam_name=exam_name,
        selected_section=section, selected_total_marks=total_marks or existing_total,
        sheet_students=sheet_students, recent_exams=recent_exams,
    )


@academic_bp.route("/academic/save_sheet", methods=["POST"])
@login_required
def save_sheet():
    subject_id = request.form.get("subject_id", type=int)
    exam_name = request.form.get("exam_name", "").strip()
    total_marks_raw = request.form.get("total_marks", "").strip()
    section = request.form.get("section", "").strip()

    if not subject_id or not exam_name or not total_marks_raw:
        flash("Subject, Exam Name, and Total Mark are all required.", "danger")
        return redirect(url_for("academic.academic_list"))

    try:
        total_marks = float(total_marks_raw)
        if total_marks <= 0:
            raise ValueError()
    except ValueError:
        flash("Total Mark must be a positive number.", "danger")
        return redirect(url_for("academic.academic_list"))

    student_ids = request.form.getlist("student_id")
    obtained_values = request.form.getlist("obtained_marks")

    saved_count = 0
    errors = []
    for student_id, obtained_raw in zip(student_ids, obtained_values):
        obtained_raw = obtained_raw.strip()
        if not obtained_raw:
            continue  # blank cell -- skip, don't overwrite with a zero
        try:
            obtained = float(obtained_raw)
            if not (0 <= obtained <= total_marks):
                errors.append(f"{student_id}: {obtained} is out of range (0–{total_marks})")
                continue
        except ValueError:
            errors.append(f"{student_id}: '{obtained_raw}' is not a number")
            continue

        upsert_mark(student_id, subject_id, exam_name, total_marks, obtained)
        saved_count += 1

    audit.log_event("marks.save", "marks", f"{subject_id}:{exam_name}", details={"saved": saved_count, "skipped": len(errors)})
    if errors:
        flash(f"Saved {saved_count} — but skipped some rows: {'; '.join(errors[:5])}"
              + (f" (+{len(errors)-5} more)" if len(errors) > 5 else ""), "warning")
    else:
        flash(f"Saved {saved_count} mark(s) for '{exam_name}'.", "success")

    return redirect(url_for(
        "academic.academic_list", subject_id=subject_id, exam_name=exam_name,
        section=section, total_marks=total_marks_raw,
    ))


@academic_bp.route("/academic/export.csv")
@login_required
def export_csv():
    subject_id = request.args.get("subject_id", type=int)
    exam_name = request.args.get("exam_name", "").strip()
    if not subject_id or not exam_name:
        flash("Select a subject and exam first.", "danger")
        return redirect(url_for("academic.academic_list"))

    csv_text = export_sheet_csv(subject_id, exam_name)
    safe_name = "".join(c if c.isalnum() else "_" for c in exam_name)
    return Response(
        csv_text, mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename=marks_{safe_name}.csv"},
    )


@academic_bp.route("/academic/import.csv", methods=["POST"])
@login_required
def import_csv():
    subject_id = request.form.get("subject_id", type=int)
    exam_name = request.form.get("exam_name", "").strip()
    total_marks_raw = request.form.get("total_marks", "").strip()

    if not subject_id or not exam_name or not total_marks_raw:
        flash("Select Subject, Exam Name, and Total Mark before importing a CSV.", "danger")
        return redirect(url_for("academic.academic_list"))

    file = request.files.get("csv_file")
    if not file or file.filename == "":
        flash("Choose a CSV file to import.", "danger")
        return redirect(url_for("academic.academic_list"))

    try:
        total_marks = float(total_marks_raw)
    except ValueError:
        flash("Total Mark must be a number.", "danger")
        return redirect(url_for("academic.academic_list"))

    import csv as csv_module
    stream = io.StringIO(file.stream.read().decode("utf-8-sig"))
    reader = csv_module.DictReader(stream)

    saved = 0
    errors = []
    for row in reader:
        student_id = (row.get("student_id") or "").strip()
        obtained_raw = (row.get("obtained_marks") or "").strip()
        if not student_id or not obtained_raw:
            continue
        try:
            obtained = float(obtained_raw)
            if not (0 <= obtained <= total_marks):
                errors.append(f"{student_id}: out of range")
                continue
        except ValueError:
            errors.append(f"{student_id}: invalid number '{obtained_raw}'")
            continue
        upsert_mark(student_id, subject_id, exam_name, total_marks, obtained)
        saved += 1

    audit.log_event("marks.import", "marks", f"{subject_id}:{exam_name}", details={"saved": saved, "skipped": len(errors)})
    if errors:
        flash(f"Imported {saved} rows — {len(errors)} skipped: {'; '.join(errors[:5])}", "warning")
    else:
        flash(f"Imported {saved} marks for '{exam_name}'.", "success")

    return redirect(url_for("academic.academic_list", subject_id=subject_id, exam_name=exam_name, total_marks=total_marks_raw))
