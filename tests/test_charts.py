import os
import sys
import unittest
import tempfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ChartsTestCase(unittest.TestCase):
    def setUp(self):
        import config
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.DATABASE_PATH = self.tmp_db.name

        from database.db import init_db, execute
        init_db()
        execute("INSERT INTO students (student_id, name) VALUES (?, ?)", ("STU001", "Test Student"))
        execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)", ("CS101", "Test Subject"))

    def tearDown(self):
        os.unlink(self.tmp_db.name)

    def _assert_valid_png(self, png_bytes):
        self.assertEqual(png_bytes[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(png_bytes), 500)

    def test_all_four_charts_render_on_empty_data(self):
        from analytics.charts import png_bytes_for
        for name in ["attendance_trend", "risk_distribution", "attendance_by_subject", "feature_importance"]:
            self._assert_valid_png(png_bytes_for(name))

    def test_unknown_chart_raises(self):
        from analytics.charts import png_bytes_for
        with self.assertRaises(ValueError):
            png_bytes_for("not_a_real_chart")

    def test_attendance_trend_reflects_real_data(self):
        import datetime
        from database.db import execute
        from analytics.charts import attendance_trend_figure
        today = datetime.date.today().isoformat()
        execute("INSERT INTO attendance (student_id, subject_id, date, time, status) VALUES (?, 1, ?, '09:00:00', 'Present')",
                ("STU001", today))
        fig = attendance_trend_figure(days=7)
        line = fig.axes[0].lines[0]
        self.assertIn(1, list(line.get_ydata()))
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_pdf_report_is_valid(self):
        from analytics.charts import generate_pdf_report
        pdf_bytes = generate_pdf_report()
        self.assertEqual(pdf_bytes[:5], b"%PDF-")
        self.assertGreater(len(pdf_bytes), 5000)


if __name__ == "__main__":
    unittest.main()
