from flask import Blueprint, render_template, request, redirect, url_for, flash
from database.db import query_all, query_one, execute
from routes.auth import login_required, roles_required
from services import audit

students_bp = Blueprint("students", __name__)


@students_bp.route("/students")
@login_required
def list_students():
    search = request.args.get("q", "").strip()
    if search:
        like = f"%{search}%"
        rows = query_all(
            "SELECT * FROM students WHERE name LIKE ? OR student_id LIKE ? OR roll_number LIKE ? ORDER BY name",
            (like, like, like),
        )
    else:
        rows = query_all("SELECT * FROM students ORDER BY name")
    return render_template("students.html", students=rows, search=search)


@students_bp.route("/students/add", methods=["GET", "POST"])
@roles_required("admin")
def add_student():
    if request.method == "POST":
        data = _read_student_form()
        if not data["student_id"] or not data["name"]:
            flash("Student ID and Name are required.", "danger")
            return render_template("student_form.html", student=data, mode="add")

        if query_one("SELECT id FROM students WHERE student_id = ?", (data["student_id"],)):
            flash("A student with that Student ID already exists.", "danger")
            return render_template("student_form.html", student=data, mode="add")

        previous_gpa = None
        if data["previous_gpa"]:
            try:
                previous_gpa = float(data["previous_gpa"])
                if not (0 <= previous_gpa <= 10):
                    raise ValueError()
            except ValueError:
                flash("Previous GPA must be a number between 0 and 10.", "danger")
                return render_template("student_form.html", student=data, mode="add")

        execute(
            """INSERT INTO students
               (student_id, roll_number, name, department, year, section, semester, email, previous_gpa)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (data["student_id"], data["roll_number"], data["name"], data["department"],
             data["year"], data["section"], data["semester"], data["email"], previous_gpa),
        )
        audit.log_event("student.create", "student", data["student_id"])
        flash(f"Student {data['name']} added.", "success")
        return redirect(url_for("students.list_students"))

    return render_template("student_form.html", student={}, mode="add")


@students_bp.route("/students/<student_id>/edit", methods=["GET", "POST"])
@roles_required("admin")
def edit_student(student_id):
    student = query_one("SELECT * FROM students WHERE student_id = ?", (student_id,))
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students.list_students"))

    if request.method == "POST":
        data = _read_student_form()
        previous_gpa = None
        if data["previous_gpa"]:
            try:
                previous_gpa = float(data["previous_gpa"])
                if not (0 <= previous_gpa <= 10):
                    raise ValueError()
            except ValueError:
                flash("Previous GPA must be a number between 0 and 10.", "danger")
                return render_template("student_form.html", student=student, mode="edit")

        execute(
            """UPDATE students SET roll_number=?, name=?, department=?, year=?,
               section=?, semester=?, email=?, previous_gpa=? WHERE student_id=?""",
            (data["roll_number"], data["name"], data["department"], data["year"],
             data["section"], data["semester"], data["email"], previous_gpa, student_id),
        )
        audit.log_event("student.update", "student", student_id)
        # Refresh prediction if GPA or profile changed
        try:
            from services.prediction_service import refresh_student_prediction
            refresh_student_prediction(student_id)
        except Exception:
            pass
        flash("Student updated.", "success")
        return redirect(url_for("students.list_students"))

    return render_template("student_form.html", student=student, mode="edit")


@students_bp.route("/students/<student_id>/delete", methods=["POST"])
@roles_required("admin")
def delete_student(student_id):
    # Safe biometric face cleanup: remove embeddings on disk and rebuild/clear gallery
    try:
        from face_reco.recognizer import remove_student_face_data
        remove_student_face_data(student_id)
    except Exception:
        pass

    execute("DELETE FROM students WHERE student_id = ?", (student_id,))
    audit.log_event("student.delete", "student", student_id)
    flash("Student deleted.", "info")
    return redirect(url_for("students.list_students"))


@students_bp.route("/students/<student_id>")
@login_required
def student_detail(student_id):
    student = query_one("SELECT * FROM students WHERE student_id = ?", (student_id,))
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("students.list_students"))

    attendance_rows = query_all(
        """SELECT a.date, a.time, a.status, s.subject_name
           FROM attendance a JOIN subjects s ON a.subject_id = s.id
           WHERE a.student_id = ? ORDER BY a.date DESC, a.time DESC LIMIT 20""",
        (student_id,),
    )
    total_sessions = query_one("SELECT COUNT(*) AS c FROM attendance WHERE student_id = ?", (student_id,))["c"]

    marks_rows = query_all(
        """SELECT m.*, s.subject_name FROM marks m
           JOIN subjects s ON m.subject_id = s.id
           WHERE m.student_id = ? ORDER BY m.updated_at DESC""",
        (student_id,),
    )

    prediction = query_one(
        "SELECT * FROM predictions WHERE student_id = ? ORDER BY id DESC LIMIT 1",
        (student_id,),
    )

    from academic.marks import compute_features_for_student, MissingFeaturesError
    features = None
    missing = None
    try:
        features = compute_features_for_student(student_id)
    except MissingFeaturesError as e:
        missing = e.missing_fields

    return render_template(
        "student_detail.html", student=student, attendance_rows=attendance_rows,
        total_sessions=total_sessions, marks_rows=marks_rows, prediction=prediction,
        features=features, missing=missing,
    )


def _read_student_form():
    return {
        "student_id": request.form.get("student_id", "").strip(),
        "roll_number": request.form.get("roll_number", "").strip(),
        "name": request.form.get("name", "").strip(),
        "department": request.form.get("department", "").strip(),
        "year": request.form.get("year", "").strip(),
        "section": request.form.get("section", "").strip(),
        "semester": request.form.get("semester", "").strip(),
        "email": request.form.get("email", "").strip(),
        "previous_gpa": request.form.get("previous_gpa", "").strip(),
    }
