import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from ml.preprocessing import category_for_score, risk_for_score
from ml import registry

import pandas as pd


class ModelNotTrainedError(Exception):
    pass


def predict_for_features(features: dict):
    pipeline, version = registry.load_current_model()
    if pipeline is None:
        raise ModelNotTrainedError(
            "No trained model found. Go to ML Training and click "
            "'Train / Retrain Model' first."
        )

    row = pd.DataFrame([{col: features[col] for col in config.ML_FEATURE_COLUMNS}])
    predicted_score = float(pipeline.predict(row)[0])
    predicted_score = max(0.0, min(100.0, predicted_score))

    return {
        "predicted_score": round(predicted_score, 2),
        "performance_category": category_for_score(predicted_score),
        "risk_level": risk_for_score(predicted_score),
        "model_version": version,
    }
