"""Migrations, WAL, latest_predictions view, jobs, health."""
import os, sys, sqlite3, unittest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tests.helpers import isolate, add_user, make_client, login


class MigrationTests(unittest.TestCase):
    def setUp(self):
        isolate()

    def test_migrations_apply_once(self):
        from database.db import init_db, query_all
        self.assertEqual(init_db(), [])  # setUp already applied everything
        versions = [r["version"] for r in query_all("SELECT version FROM schema_migrations ORDER BY version")]
        self.assertEqual(versions, ["001", "002"])

    def test_wal_mode_enabled(self):
        conn = sqlite3.connect(config.DATABASE_PATH)
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
        conn.close()

    def test_new_migration_file_is_picked_up(self):
        import shutil, tempfile
        from database import migrate
        d = tempfile.mkdtemp()
        for f in os.listdir(config.MIGRATIONS_DIR):
            shutil.copy(os.path.join(config.MIGRATIONS_DIR, f), d)
        with open(os.path.join(d, "003_extra.sql"), "w") as f:
            f.write("CREATE TABLE extra_demo (id INTEGER PRIMARY KEY);")
        original = config.MIGRATIONS_DIR
        config.MIGRATIONS_DIR = d
        try:
            self.assertEqual(migrate.run_migrations(), ["003_extra.sql"])
        finally:
            config.MIGRATIONS_DIR = original
        from database.db import query_one
        self.assertIsNotNone(query_one("SELECT name FROM sqlite_master WHERE name='extra_demo'"))

    def test_latest_predictions_view_one_row_per_student_even_in_same_second(self):
        from database.db import execute, query_all
        execute("INSERT INTO students (student_id, name) VALUES ('S1', 'A')")
        for score in (50, 60, 70):  # identical created_at second
            execute("INSERT INTO predictions (student_id, predicted_score, performance_category, risk_level, model_version) "
                    "VALUES ('S1', ?, 'Good', 'Low', 'v')", (score,))
        rows = query_all("SELECT * FROM latest_predictions")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["predicted_score"], 70)


class JobTests(unittest.TestCase):
    def setUp(self):
        isolate()
        self._sync = config.JOBS_SYNC

    def tearDown(self):
        config.JOBS_SYNC = self._sync

    def test_job_success_records_progress_and_result(self):
        from core import jobs
        def task(progress, x):
            progress(40, "halfway")
            return {"double": x * 2}
        job = jobs.get(jobs.submit("t", task, 21))
        self.assertEqual((job["status"], job["progress"], job["result"]), ("succeeded", 100, {"double": 42}))

    def test_job_failure_is_captured_not_raised(self):
        from core import jobs
        def boom(progress):
            raise ValueError("boom")
        job = jobs.get(jobs.submit("t", boom))
        self.assertEqual(job["status"], "failed")
        self.assertIn("boom", job["error"])

    def test_async_job_runs_on_worker_pool(self):
        from core import jobs
        config.JOBS_SYNC = False
        job_id = jobs.submit("async_t", lambda progress: {"ok": True})
        self.assertEqual(jobs.wait(job_id)["status"], "succeeded")
        jobs.shutdown()

    def test_active_and_recover_stale(self):
        from core import jobs
        from database.db import execute
        execute("INSERT INTO jobs (id, name, status) VALUES ('stuck', 'train_model', 'running')")
        self.assertEqual(jobs.active("train_model"), "stuck")
        jobs.recover_stale()
        self.assertIsNone(jobs.active("train_model"))
        self.assertEqual(jobs.get("stuck")["status"], "failed")


class HealthTests(unittest.TestCase):
    def test_health_ok_without_login(self):
        isolate()
        r = make_client().get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["status"], "ok")
        for key in ("database", "model", "face_gallery", "camera", "jobs"):
            self.assertIn(key, body["checks"])

    def test_health_degraded_when_database_unusable(self):
        import tempfile
        config.DATABASE_PATH = os.path.join(tempfile.mkdtemp(), "empty.db")  # never migrated
        r = make_client().get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.get_json()["status"], "degraded")


if __name__ == "__main__":
    unittest.main()
