import os
import sys
import unittest
import tempfile
import csv
import random

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PredictionTestCase(unittest.TestCase):
    def setUp(self):
        import config
        self.tmp_dir = tempfile.mkdtemp()
        config.ML_DATASET_PATH = os.path.join(self.tmp_dir, "dataset.csv")
        config.MODEL_REGISTRY_DIR = os.path.join(self.tmp_dir, "registry")
        config.CURRENT_VERSION_POINTER = os.path.join(config.MODEL_REGISTRY_DIR, "current_version.txt")
        config.BASELINE_STATS_PATH = os.path.join(config.MODEL_REGISTRY_DIR, "training_baseline_stats.json")
        config.DATABASE_PATH = os.path.join(self.tmp_dir, "test.db")
        config.RF_PARAM_GRID = {"model__n_estimators": [50], "model__max_depth": [4, None]}

        from database.db import init_db
        init_db()

        random.seed(1)
        rows = []
        for i in range(60):
            attendance = random.uniform(50, 100)
            marks_avg = random.uniform(40, 100)
            gpa = random.uniform(5, 10)
            score = min(100, max(0, attendance * 0.35 + marks_avg * 0.45 + gpa * 2))
            rows.append([f"S{i}", attendance, marks_avg, gpa, score])

        with open(config.ML_DATASET_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["student_id", "attendance_percentage", "marks_average_percentage", "previous_gpa", "final_score"])
            writer.writerows(rows)

    def test_training_produces_model_with_three_features(self):
        from ml.train import train_model
        metrics = train_model()
        self.assertIn("mae", metrics)
        self.assertEqual(set(metrics["cv_comparison"].keys()),
                          {"linear_regression", "decision_tree", "random_forest"})
        self.assertTrue(metrics["registry"]["promoted"])

    def test_prediction_without_trained_model_raises(self):
        from ml.predict import predict_for_features, ModelNotTrainedError
        with self.assertRaises(ModelNotTrainedError):
            predict_for_features({"attendance_percentage": 80, "marks_average_percentage": 80, "previous_gpa": 8})

    def test_prediction_uses_exactly_three_features(self):
        from ml.train import train_model
        from ml.predict import predict_for_features
        train_model()
        result = predict_for_features({
            "attendance_percentage": 82, "marks_average_percentage": 78, "previous_gpa": 8.1,
        })
        self.assertTrue(0 <= result["predicted_score"] <= 100)
        self.assertIn(result["performance_category"], ["Excellent", "Very Good", "Good", "Average", "Poor"])
        self.assertIn(result["risk_level"], ["Low", "Medium", "High"])

    def test_config_feature_columns_are_exactly_three(self):
        import config
        self.assertEqual(config.ML_FEATURE_COLUMNS,
                          ["attendance_percentage", "marks_average_percentage", "previous_gpa"])

    def test_training_fails_with_too_few_rows(self):
        import config
        with open(config.ML_DATASET_PATH, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["student_id", "attendance_percentage", "marks_average_percentage", "previous_gpa", "final_score"])
            writer.writerow(["S1", 80, 80, 8, 80])
        from ml.train import train_model
        with self.assertRaises(ValueError):
            train_model()

    def test_worse_retrain_is_not_promoted(self):
        from ml.train import train_model
        from ml import registry
        first = train_model()
        first_version = registry.get_current_version()

        from sklearn.pipeline import Pipeline
        from sklearn.dummy import DummyRegressor
        from ml.preprocessing import load_dataset, clean_dataset, get_features_and_target
        df = clean_dataset(load_dataset())
        X, y = get_features_and_target(df)
        bad_pipeline = Pipeline([("model", DummyRegressor())])
        bad_pipeline.fit(X, y)
        bad_metrics = {
            "selected_model": "dummy", "mae": first["mae"] + 100, "r2_score": -5.0,
            "cv_comparison": {}, "best_params": {}, "n_train": 1, "n_test": 1,
            "feature_importances": {}, "coefficients": {},
        }
        baseline = {col: {"mean": 1.0, "std": 1.0} for col in
                    ["attendance_percentage", "marks_average_percentage", "previous_gpa"]}
        result = registry.save_version(bad_pipeline, bad_metrics, baseline)
        self.assertFalse(result["promoted"])
        self.assertEqual(registry.get_current_version(), first_version)


if __name__ == "__main__":
    unittest.main()
