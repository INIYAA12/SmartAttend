"""
Training pipeline. Trains on the SYNTHETIC baseline dataset only
(data/academic_dataset.csv) -- real student marks are used for
INFERENCE (see academic/marks.py + ml/predict.py), not for retraining,
because the redesigned generic marks model has no reliable "true final
outcome" label to train a regression target against. This is a
deliberate, documented trade-off: the model learns the general
relationship between attendance/marks/GPA and outcomes from the
synthetic data, then applies that learned relationship to real students'
current numbers to forecast their likely result.

Still runs the full pro-level pipeline: cross-validated comparison of
Linear Regression / Decision Tree / Random Forest, hyperparameter tuning
on the winner, held-out evaluation, and a versioned model registry.
"""

import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from ml.preprocessing import load_dataset, clean_dataset, get_features_and_target
from ml import registry

from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.metrics import mean_absolute_error, r2_score


def _build_pipeline(estimator):
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", estimator),
    ])


def _candidate_estimators():
    return {
        "linear_regression": LinearRegression(),
        "decision_tree": DecisionTreeRegressor(max_depth=6, random_state=42),
        "random_forest": RandomForestRegressor(n_estimators=200, random_state=42, n_jobs=-1),
    }


def compare_models_cv(X, y):
    results = {}
    for name, estimator in _candidate_estimators().items():
        pipeline = _build_pipeline(estimator)
        mae_scores = -cross_val_score(pipeline, X, y, cv=config.CV_FOLDS, scoring="neg_mean_absolute_error", n_jobs=-1)
        r2_scores = cross_val_score(pipeline, X, y, cv=config.CV_FOLDS, scoring="r2", n_jobs=-1)
        results[name] = {
            "mae_mean": round(float(mae_scores.mean()), 3),
            "mae_std": round(float(mae_scores.std()), 3),
            "r2_mean": round(float(r2_scores.mean()), 3),
            "r2_std": round(float(r2_scores.std()), 3),
        }
    return dict(sorted(results.items(), key=lambda kv: kv[1]["mae_mean"]))


def tune_best_model(best_name, X_train, y_train):
    if best_name == "random_forest":
        pipeline = _build_pipeline(RandomForestRegressor(random_state=42, n_jobs=-1))
        search = GridSearchCV(pipeline, config.RF_PARAM_GRID, cv=config.CV_FOLDS,
                               scoring="neg_mean_absolute_error", n_jobs=-1)
        search.fit(X_train, y_train)
        return search.best_estimator_, search.best_params_
    else:
        pipeline = _build_pipeline(_candidate_estimators()[best_name])
        pipeline.fit(X_train, y_train)
        return pipeline, {}


def train_model(dataset_path=None, progress=None):
    progress = progress or (lambda *a, **k: None)
    progress(5, "Loading dataset")
    df = load_dataset(dataset_path)
    df = clean_dataset(df)

    if len(df) < 20:
        raise ValueError(
            f"Only {len(df)} usable rows found — need at least 20 to train a "
            "reasonably stable model."
        )

    X, y = get_features_and_target(df)

    progress(15, "Cross-validating candidate models")
    comparison = compare_models_cv(X, y)
    best_name = next(iter(comparison))
    progress(55, f"Tuning {best_name.replace('_', ' ')}")

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    best_pipeline, best_params = tune_best_model(best_name, X_train, y_train)

    progress(80, "Evaluating on held-out data")
    y_pred = best_pipeline.predict(X_test)
    mae = round(float(mean_absolute_error(y_test, y_pred)), 3)
    r2 = round(float(r2_score(y_test, y_pred)), 3)

    feature_importances = {}
    coefficients = {}
    fitted_model = best_pipeline.named_steps["model"]
    if hasattr(fitted_model, "feature_importances_"):
        feature_importances = {
            col: round(float(imp), 4)
            for col, imp in zip(config.ML_FEATURE_COLUMNS, fitted_model.feature_importances_)
        }
    elif hasattr(fitted_model, "coef_"):
        coefficients = {
            col: round(float(c), 4)
            for col, c in zip(config.ML_FEATURE_COLUMNS, fitted_model.coef_)
        }

    metrics = {
        "selected_model": best_name,
        "cv_comparison": comparison,
        "best_params": best_params,
        "mae": mae,
        "r2_score": r2,
        "n_train": len(X_train),
        "n_test": len(X_test),
        "feature_importances": feature_importances,
        "coefficients": coefficients,
    }

    baseline_stats = {
        col: {"mean": round(float(X[col].mean()), 3), "std": round(float(X[col].std()), 3)}
        for col in config.ML_FEATURE_COLUMNS
    }

    progress(90, "Saving to model registry")
    registry_result = registry.save_version(best_pipeline, metrics, baseline_stats)
    return {**metrics, "registry": registry_result}


if __name__ == "__main__":
    result = train_model()
    print(json.dumps(result, indent=2))
