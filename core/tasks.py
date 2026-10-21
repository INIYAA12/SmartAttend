"""Job bodies run by core.jobs. Each receives a `progress(pct, msg)` callable first."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services import audit
from services.prediction_service import predict_all_students


def train_model_task(progress):
    from ml.train import train_model
    metrics = train_model(progress=lambda p, m=None: progress(p * 0.9, m))
    registry_info = metrics["registry"]
    audit.log_event("model.trained", "model", registry_info["version"],
                    details={"model": metrics["selected_model"], "mae": metrics["mae"],
                             "promoted": registry_info["promoted"]}, username="system")
    summary = {"selected_model": metrics["selected_model"], "mae": metrics["mae"],
               "r2_score": metrics["r2_score"], "version": registry_info["version"],
               "promoted": registry_info["promoted"], "reason": registry_info["reason"]}
    if registry_info["promoted"]:
        # A new live model makes old predictions stale -- refresh them.
        progress(92, "Refreshing predictions with the new model")
        summary["predictions"] = predict_all_students()
    return summary


def predict_all_task(progress):
    summary = predict_all_students(progress)
    audit.log_event("prediction.run_all", details={"predicted": summary["predicted"]}, username="system")
    return summary
