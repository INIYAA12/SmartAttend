"""Prediction use-cases shared by the web routes and background jobs."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import execute, query_all
from academic.marks import compute_features_for_student, MissingFeaturesError
from ml.predict import predict_for_features, ModelNotTrainedError

__all__ = ["predict_student", "predict_all_students", "refresh_student_prediction", "MissingFeaturesError", "ModelNotTrainedError"]


def refresh_student_prediction(student_id):
    """
    Called when student marks, attendance, or profile GPA changes.
    Recomputes features and refreshes the student's prediction using the currently live model.
    If required features are incomplete, removes any existing prediction from the predictions
    table so profile/dashboard/reports never show contradictory stale states.
    """
    try:
        predict_student(student_id, persist=True)
    except MissingFeaturesError:
        # Features are incomplete: remove any stale prediction
        execute("DELETE FROM predictions WHERE student_id = ?", (student_id,))
    except ModelNotTrainedError:
        pass



def predict_student(student_id, persist=True):
    """Raises MissingFeaturesError / ModelNotTrainedError with a precise reason."""
    features = compute_features_for_student(student_id)
    result = predict_for_features(features)
    result["features_used"] = features
    if persist:
        _store(student_id, result)
    return result


def _store(student_id, result):
    execute(
        "INSERT INTO predictions (student_id, predicted_score, performance_category, risk_level, model_version) "
        "VALUES (?, ?, ?, ?, ?)",
        (student_id, result["predicted_score"], result["performance_category"],
         result["risk_level"], result["model_version"]),
    )


def predict_all_students(progress=None):
    """Predict for every student with complete data; report who was skipped
    and exactly why."""
    progress = progress or (lambda *a, **k: None)
    students = query_all("SELECT student_id FROM students ORDER BY student_id")
    risk_counts = {"Low": 0, "Medium": 0, "High": 0}
    skipped = []
    predicted = 0
    total = max(len(students), 1)
    for i, s in enumerate(students):
        sid = s["student_id"]
        try:
            result = predict_student(sid)
            predicted += 1
            risk_counts[result["risk_level"]] += 1
        except MissingFeaturesError as e:
            skipped.append({"student_id": sid, "missing": e.missing_fields})
        progress(int((i + 1) / total * 100), f"Predicted {predicted} of {len(students)} students")
    return {"predicted": predicted, "skipped": skipped, "risk_counts": risk_counts}
