import datetime, os, sys, unittest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tests.helpers import isolate, make_client, login


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        isolate()
        from database import seed
        cls.summary = seed.run(log=lambda *a: None)

    def test_expected_volume_of_demo_data(self):
        from database.db import query_one
        count = lambda t: query_one(f"SELECT COUNT(*) c FROM {t}")["c"]
        self.assertEqual((count("users"), count("subjects"), count("students")), (4, 8, 45))
        self.assertGreater(count("attendance"), 2000)
        self.assertGreater(count("marks"), 1000)
        self.assertEqual(query_one("SELECT value FROM app_meta WHERE key='demo_data'")["value"], "1")

    def test_attendance_is_weekdays_only_and_in_the_past(self):
        from database.db import query_all
        today = datetime.date.today()
        for r in query_all("SELECT DISTINCT date FROM attendance"):
            d = datetime.date.fromisoformat(r["date"])
            self.assertLess(d.weekday(), 5)
            self.assertLess(d, today)

    def test_marks_are_valid(self):
        from database.db import query_all
        for r in query_all("SELECT * FROM marks"):
            self.assertLessEqual(r["obtained_marks"], r["total_marks"])
            self.assertTrue(0 <= r["percentage"] <= 100)

    def test_model_trained_and_predictions_cover_all_complete_students_with_every_risk_level(self):
        from database.db import query_all
        from ml import registry
        self.assertIsNotNone(registry.get_current_version())
        levels = {r["risk_level"] for r in query_all("SELECT risk_level FROM latest_predictions")}
        self.assertEqual(levels, {"Low", "Medium", "High"})
        self.assertEqual(self.summary["predictions"]["predicted"], 42)

    def test_new_admissions_are_skipped_with_a_specific_reason(self):
        from academic.marks import compute_features_for_student, MissingFeaturesError
        for sid in ("STU043", "STU044", "STU045"):
            with self.assertRaises(MissingFeaturesError) as ctx:
                compute_features_for_student(sid)
            self.assertTrue(len(ctx.exception.missing_fields) >= 2)
        skipped = {s["student_id"] for s in self.summary["predictions"]["skipped"]}
        self.assertEqual(skipped, {"STU043", "STU044", "STU045"})

    def test_seeding_again_changes_nothing(self):
        from database import seed
        from database.db import query_one
        before = query_one("SELECT COUNT(*) c FROM attendance")["c"], query_one("SELECT COUNT(*) c FROM marks")["c"]
        again = seed.run(log=lambda *a: None)
        after = query_one("SELECT COUNT(*) c FROM attendance")["c"], query_one("SELECT COUNT(*) c FROM marks")["c"]
        self.assertEqual(before, after)
        self.assertEqual(again["students"], 0)


class SeedVariantTests(unittest.TestCase):
    def test_no_history_seeds_people_only_and_is_not_flagged_demo(self):
        isolate()
        from database import seed
        from database.db import query_one
        seed.run(history=False, train=False, log=lambda *a: None)
        self.assertEqual(query_one("SELECT COUNT(*) c FROM students")["c"], 45)
        self.assertEqual(query_one("SELECT COUNT(*) c FROM attendance")["c"], 0)
        self.assertIsNone(query_one("SELECT 1 FROM app_meta WHERE key='demo_data'"))

    def test_seed_is_reproducible(self):
        from database import seed
        from database.db import query_one
        counts = []
        for _ in range(2):
            isolate()
            seed.run(train=False, log=lambda *a: None)
            counts.append((query_one("SELECT COUNT(*) c FROM attendance")["c"], query_one("SELECT SUM(obtained_marks) s FROM marks")["s"]))
        self.assertEqual(counts[0], counts[1])


class BootstrapTests(unittest.TestCase):
    def test_empty_database_auto_seeds_demo(self):
        isolate()
        from core.bootstrap import ensure_ready
        from database.db import query_one
        config.AUTO_SEED_DEMO = True
        ensure_ready()
        self.assertEqual(query_one("SELECT COUNT(*) c FROM students")["c"], 45)
        ensure_ready()  # second start must not duplicate anything
        self.assertEqual(query_one("SELECT COUNT(*) c FROM users")["c"], 4)

    def test_auto_seed_disabled_creates_only_an_admin_with_given_password(self):
        isolate()
        from core.bootstrap import ensure_ready
        from database.db import query_one
        config.AUTO_SEED_DEMO = False
        os.environ["INITIAL_ADMIN_PASSWORD"] = "S3cretStart!"
        try:
            ensure_ready()
        finally:
            config.AUTO_SEED_DEMO = True
            del os.environ["INITIAL_ADMIN_PASSWORD"]
        self.assertEqual(query_one("SELECT COUNT(*) c FROM students")["c"], 0)
        c = make_client()
        self.assertEqual(login(c, "admin", "S3cretStart!").status_code, 302)

    def test_stale_jobs_failed_on_start(self):
        isolate()
        from database.db import execute, query_one
        execute("INSERT INTO jobs (id, name, status) VALUES ('old', 'train_model', 'running')")
        from core.bootstrap import ensure_ready
        config.AUTO_SEED_DEMO = False
        os.environ["INITIAL_ADMIN_PASSWORD"] = "abcdefgh1"
        try:
            ensure_ready()
        finally:
            config.AUTO_SEED_DEMO = True
            del os.environ["INITIAL_ADMIN_PASSWORD"]
        self.assertEqual(query_one("SELECT status FROM jobs WHERE id='old'")["status"], "failed")


class LiveDriftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        isolate()
        from database import seed
        seed.run(log=lambda *a: None)

    def test_demo_population_matches_baseline(self):
        from ml.drift import check_drift
        report = check_drift()
        self.assertFalse(report["insufficient_data"])
        self.assertEqual(report["n_students"], 42)
        self.assertFalse(report["any_drift"], report)

    def test_shifted_population_is_flagged(self):
        import pandas as pd
        from ml.drift import check_drift
        shifted = pd.DataFrame({"attendance_percentage": [40.0] * 10, "marks_average_percentage": [30.0] * 10, "previous_gpa": [4.0] * 10})
        report = check_drift(shifted)
        self.assertTrue(report["any_drift"])
        self.assertTrue(all(f["drifted"] for f in report["features"].values()))

    def test_too_few_students_reports_insufficient_data_instead_of_guessing(self):
        import pandas as pd
        from ml.drift import check_drift
        tiny = pd.DataFrame({"attendance_percentage": [80.0], "marks_average_percentage": [70.0], "previous_gpa": [7.0]})
        self.assertTrue(check_drift(tiny)["insufficient_data"])


class WebFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        isolate()
        from database import seed
        seed.run(log=lambda *a: None)

    def setUp(self):
        self.c = make_client()
        login(self.c, "admin", "admin123")

    def test_every_page_renders_with_demo_data(self):
        for path in ["/dashboard", "/students", "/students/STU001", "/syllabus", "/academic", "/face/register",
                     "/face/live_attendance", "/attendance", "/ml/train", "/prediction", "/reports",
                     "/admin/users", "/admin/audit", "/account/password"]:
            self.assertEqual(self.c.get(path).status_code, 200, path)

    def test_dashboard_shows_at_risk_students_model_and_demo_badge(self):
        html = self.c.get("/dashboard").data.decode()
        self.assertIn("Students needing attention", html)
        self.assertIn("Live model", html)
        self.assertIn("DEMO DATA", html)
        self.assertNotIn("No predictions yet", html)

    def test_training_runs_as_a_job_and_refreshes_predictions(self):
        from database.db import query_one
        before = query_one("SELECT COUNT(*) c FROM predictions")["c"]
        self.c.post("/ml/train")
        job = query_one("SELECT id, status FROM jobs WHERE name='train_model' ORDER BY rowid DESC LIMIT 1")
        self.assertEqual(job["status"], "succeeded")
        result = self.c.get(f"/jobs/{job['id']}").get_json()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["progress"], 100)
        if result["result"]["promoted"]:
            self.assertGreater(query_one("SELECT COUNT(*) c FROM predictions")["c"], before)
        self.assertIn(b"Live Model", self.c.get("/ml/train").data)

    def test_bulk_prediction_job_reports_skips(self):
        from database.db import query_one
        self.c.post("/prediction/run_all")
        job = query_one("SELECT id FROM jobs WHERE name='predict_all' ORDER BY rowid DESC LIMIT 1")
        result = self.c.get(f"/jobs/{job['id']}").get_json()["result"]
        self.assertEqual(result["predicted"], 42)
        self.assertEqual(len(result["skipped"]), 3)

    def test_single_prediction_ok_and_missing_data_message(self):
        ok = self.c.post("/prediction", data={"student_id": "STU001"})
        self.assertIn(b"Predicted Score", ok.data)
        bad = self.c.post("/prediction", data={"student_id": "STU045"}, follow_redirects=True)
        self.assertIn(b"missing", bad.data)

    def test_unknown_job_is_404_and_requires_login(self):
        self.assertEqual(self.c.get("/jobs/nope").status_code, 404)
        self.assertEqual(make_client().get("/jobs/nope").status_code, 302)

    def test_reports_and_pdf(self):
        self.assertEqual(self.c.get("/reports").status_code, 200)
        self.assertEqual(self.c.get("/reports/pdf").data[:5], b"%PDF-")
        for name in ("attendance_trend", "risk_distribution", "attendance_by_subject", "feature_importance"):
            self.assertEqual(self.c.get(f"/reports/chart/{name}.png").data[:4], b"\x89PNG")

    def test_marks_sheet_edit_cycle_still_upserts(self):
        from database.db import query_one
        data = {"subject_id": "1", "exam_name": "Pop Quiz", "total_marks": "10", "section": "A",
                "student_id": ["STU001"], "obtained_marks": ["7"]}
        self.c.post("/academic/save_sheet", data=data)
        data["obtained_marks"] = ["9"]
        self.c.post("/academic/save_sheet", data=data)
        rows = query_one("SELECT COUNT(*) c, MAX(obtained_marks) m FROM marks WHERE exam_name='Pop Quiz'")
        self.assertEqual((rows["c"], rows["m"]), (1, 9.0))


if __name__ == "__main__":
    unittest.main()
