import unittest
from tests.helpers import isolate, add_user, make_client, login


class DashboardDateRangeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = isolate()
        add_user("admin", "adminpass", "admin")
        self.client = make_client()
        login(self.client, "admin", "adminpass")

        # Insert sample attendance records across various dates
        from database.db import execute
        execute("INSERT INTO students (student_id, name, section) VALUES ('STU001', 'Alice', 'A')")
        execute("INSERT INTO students (student_id, name, section) VALUES ('STU002', 'Bob', 'A')")
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES ('CS101', 'Intro CS')")

        # Older date attendance (September)
        execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES ('STU001', 1, '2026-09-18', '09:00', 'Present')")
        execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES ('STU002', 1, '2026-09-18', '09:00', 'Present')")

        # Mid October attendance
        execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES ('STU001', 1, '2026-10-12', '10:00', 'Present')")

        # Recent attendance
        import datetime
        self.today = datetime.date.today().isoformat()
        execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES ('STU001', 1, ?, '11:00', 'Present')", (self.today,))

    # 1. Default dashboard graph
    def test_1_default_dashboard_graph(self):
        # HTML Page render
        res = self.client.get("/dashboard")
        self.assertEqual(res.status_code, 200)
        html = res.data.decode()
        self.assertIn("trendChart", html)
        self.assertIn("Start Date:", html)
        self.assertIn("End Date:", html)
        self.assertIn("Apply / View", html)
        self.assertIn("No attendance data available for this date range", html)

        # API endpoint default (no query params -> 7 days)
        api_res = self.client.get("/dashboard/attendance-trend")
        self.assertEqual(api_res.status_code, 200)
        data = api_res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["total_days"], 7)
        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(len(data["counts"]), 7)
        self.assertTrue(data["has_data"])

    # 2. Selecting a custom date range
    def test_2_custom_date_range(self):
        res = self.client.get("/dashboard/attendance-trend?start_date=2026-10-10&end_date=2026-10-15")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["start_date"], "2026-10-10")
        self.assertEqual(data["end_date"], "2026-10-15")
        self.assertEqual(data["total_days"], 6)
        self.assertTrue(data["has_data"])
        # Oct 12 had 1 student present
        idx = data["labels"].index("2026-10-12")
        self.assertEqual(data["counts"][idx], 1)

    # 3. Selecting a range covering more than 7 days
    def test_3_range_more_than_7_days(self):
        # 16-day date range
        res = self.client.get("/dashboard/attendance-trend?start_date=2026-10-01&end_date=2026-10-16")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["total_days"], 16)
        self.assertEqual(len(data["labels"]), 16)
        self.assertEqual(len(data["counts"]), 16)

    # 4. Selecting an older date range
    def test_4_older_date_range(self):
        res = self.client.get("/dashboard/attendance-trend?start_date=2026-09-15&end_date=2026-09-20")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["has_data"])
        idx = data["labels"].index("2026-09-18")
        self.assertEqual(data["counts"][idx], 2)  # Alice & Bob present
        self.assertEqual(data["peak_count"], 2)

    # 5. Selecting a range with no data
    def test_5_range_with_no_data(self):
        res = self.client.get("/dashboard/attendance-trend?start_date=2025-01-01&end_date=2025-01-07")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ok"])
        self.assertFalse(data["has_data"])
        self.assertEqual(data["total_attendance"], 0)
        self.assertEqual(sum(data["counts"]), 0)

        # Also test on the HTML dashboard route
        page = self.client.get("/dashboard?start_date=2025-01-01&end_date=2025-01-07")
        self.assertEqual(page.status_code, 200)
        self.assertIn("No attendance data available for this date range", page.data.decode())

    # 6. Invalid Start Date > End Date
    def test_6_invalid_start_date_after_end_date(self):
        res = self.client.get("/dashboard/attendance-trend?start_date=2026-10-25&end_date=2026-10-10")
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["ok"])
        self.assertIn("Start Date cannot be after End Date", data["error"])


if __name__ == "__main__":
    unittest.main()
