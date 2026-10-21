from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify

from database.db import query_all
from routes.auth import login_required, roles_required
from core import jobs
from core.tasks import train_model_task, predict_all_task
from ml import registry, drift
from services import audit
from services.prediction_service import predict_student, MissingFeaturesError, ModelNotTrainedError

predictions_bp = Blueprint("predictions", __name__)


@predictions_bp.route("/ml/train", methods=["GET"])
@login_required
def ml_training():
    return render_template(
        "ml_training.html",
        metrics=registry.get_current_version_info(),   # always show the LIVE model's results
        versions=registry.list_versions(),
        drift_report=drift.check_drift(),
        active_job=jobs.active("train_model"),
    )


@predictions_bp.route("/ml/train", methods=["POST"])
@roles_required("admin")
def ml_train_start():
    existing = jobs.active("train_model")
    if existing:
        flash("A training run is already in progress.", "warning")
        return redirect(url_for("predictions.ml_training"))
    from flask import session
    job_id = jobs.submit("train_model", train_model_task, submitted_by=session.get("username"))
    audit.log_event("model.train_requested", "job", job_id)
    flash("Training started in the background — progress is shown below.", "info")
    return redirect(url_for("predictions.ml_training"))


@predictions_bp.route("/ml/rollback/<version>", methods=["POST"])
@roles_required("admin")
def ml_rollback(version):
    try:
        registry.rollback_to(version)
        audit.log_event("model.rollback", "model", version)
        flash(f"Rolled back — {version} is now the live model.", "info")
    except FileNotFoundError as e:
        flash(str(e), "danger")
    return redirect(url_for("predictions.ml_training"))


@predictions_bp.route("/jobs/<job_id>")
@login_required
def job_status(job_id):
    job = jobs.get(job_id)
    if job is None:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)


@predictions_bp.route("/prediction", methods=["GET", "POST"])
@login_required
def prediction_page():
    students = query_all("SELECT student_id, name FROM students ORDER BY name")
    result = None
    selected_student = None

    if request.method == "POST":
        selected_student = request.form.get("student_id", "").strip()
        try:
            result = predict_student(selected_student)
            audit.log_event("prediction.run", "student", selected_student, details={"score": result["predicted_score"]})
        except MissingFeaturesError as e:
            flash(f"Can't predict for {selected_student} yet — missing: {', '.join(e.missing_fields)}.", "danger")
        except ModelNotTrainedError as e:
            flash(str(e), "danger")

    return render_template("prediction.html", students=students, result=result,
                           selected_student=selected_student, active_job=jobs.active("predict_all"))


@predictions_bp.route("/prediction/run_all", methods=["POST"])
@login_required
def prediction_run_all():
    from flask import session
    existing = jobs.active("predict_all")
    if existing:
        flash("A bulk prediction run is already in progress.", "warning")
    else:
        jobs.submit("predict_all", predict_all_task, submitted_by=session.get("username"))
        audit.log_event("prediction.run_all_requested")
        flash("Predicting for all students in the background.", "info")
    return redirect(url_for("predictions.prediction_page"))
