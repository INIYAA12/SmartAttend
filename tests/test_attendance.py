import os, sys, unittest, tempfile, sqlite3
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AttendanceTestCase(unittest.TestCase):
    def setUp(self):
        import config
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.DATABASE_PATH = self.tmp_db.name
        from database.db import init_db, execute
        init_db()
        execute("INSERT INTO students (student_id, name) VALUES (?, ?)", ("STU001", "Test Student"))
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)", ("CS101", "Test Subject"))
        self.execute = execute
        self.query_one = __import__("database.db", fromlist=["query_one"]).query_one

    def tearDown(self):
        os.unlink(self.tmp_db.name)

    def test_attendance_insert_succeeds(self):
        self.execute(
            "INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, 1, '2026-08-20', '09:00:00', 'Present')",
            ("STU001",))
        row = self.query_one("SELECT * FROM attendance WHERE student_id = ?", ("STU001",))
        self.assertIsNotNone(row)

    def test_duplicate_attendance_rejected_by_db(self):
        self.execute(
            "INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, 1, '2026-08-20', '09:00:00', 'Present')",
            ("STU001",))
        with self.assertRaises(sqlite3.IntegrityError):
            self.execute(
                "INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, 1, '2026-08-20', '09:05:00', 'Present')",
                ("STU001",))

    def test_attendance_service_prevents_duplicates(self):
        from services.attendance_service import mark_attendance
        self.assertTrue(mark_attendance("STU001", 1))   # newly marked
        self.assertFalse(mark_attendance("STU001", 1))  # already present today
        from database.db import query_all
        self.assertEqual(len(query_all("SELECT * FROM attendance WHERE student_id = 'STU001'")), 1)


if __name__ == "__main__":
    unittest.main()
