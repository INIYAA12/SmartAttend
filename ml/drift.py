"""
Drift monitoring against LIVE data.

Compares the training baseline (feature means captured when the live model
was trained) with the current feature values of real students, computed
from actual attendance and marks. A large relative shift means the people
the model is being used on no longer look like the data it learned from.

(An earlier version compared the training CSV against itself, which can
never show drift -- this version looks at the real student population.)
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from ml import registry

MIN_STUDENTS_FOR_DRIFT = 5


def live_feature_frame():
    """DataFrame of the computed feature row of every student with complete data."""
    import pandas as pd
    from database.db import query_all
    from academic.marks import compute_features_for_student, MissingFeaturesError
    rows = []
    for s in query_all("SELECT student_id FROM students"):
        try:
            rows.append(compute_features_for_student(s["student_id"]))
        except MissingFeaturesError:
            continue
    return pd.DataFrame(rows, columns=config.ML_FEATURE_COLUMNS)


def check_drift(recent_df=None):
    baseline = registry.load_baseline_stats()
    if baseline is None:
        return None

    if recent_df is None:
        recent_df = live_feature_frame()

    if len(recent_df) < MIN_STUDENTS_FOR_DRIFT:
        return {"features": {}, "any_drift": False, "insufficient_data": True, "n_students": len(recent_df)}

    report = {}
    any_drift = False
    for col, stats in baseline.items():
        if col not in recent_df.columns or recent_df[col].dropna().empty:
            continue
        current_mean = float(recent_df[col].mean())
        baseline_mean = stats["mean"]
        if baseline_mean == 0:
            continue
        relative_shift = abs(current_mean - baseline_mean) / abs(baseline_mean)
        drifted = relative_shift > config.DRIFT_RELATIVE_THRESHOLD
        any_drift = any_drift or drifted
        report[col] = {
            "mean_now": round(current_mean, 3),
            "mean_baseline": baseline_mean,
            "relative_shift_pct": round(relative_shift * 100, 1),
            "drifted": drifted,
        }
    return {"features": report, "any_drift": any_drift, "insufficient_data": False, "n_students": len(recent_df)}
