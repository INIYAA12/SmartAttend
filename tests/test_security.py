import os, sys, unittest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from tests.helpers import isolate, add_user, make_client, login


class SecurityTests(unittest.TestCase):
    def setUp(self):
        isolate()
        add_user("admin", "adminpass1", "admin")
        add_user("teacher", "teacherpass1", "teacher")
        from database.db import execute
        execute("INSERT INTO students (student_id, name) VALUES ('S1', 'Student One')")
        self.client = make_client()
        self._attempts = config.LOGIN_MAX_ATTEMPTS

    def tearDown(self):
        config.LOGIN_MAX_ATTEMPTS = self._attempts

    # ---- CSRF ----
    def test_csrf_blocks_post_without_token_and_accepts_valid_token(self):
        config.CSRF_ENABLED = True
        self.client.get("/login")  # renders the form -> issues a token in the session
        r = self.client.post("/login", data={"username": "admin", "password": "adminpass1"})
        self.assertEqual(r.status_code, 400)
        with self.client.session_transaction() as s:
            token = s["_csrf_token"]
        r = self.client.post("/login", data={"username": "admin", "password": "adminpass1", "csrf_token": token})
        self.assertEqual(r.status_code, 302)

    def test_csrf_accepts_header_token_for_fetch_calls(self):
        config.CSRF_ENABLED = True
        self.client.get("/login")
        with self.client.session_transaction() as s:
            token = s["_csrf_token"]
        r = self.client.post("/login", data={"username": "admin", "password": "adminpass1"},
                             headers={"X-CSRF-Token": token})
        self.assertEqual(r.status_code, 302)

    def test_every_post_form_in_templates_carries_a_csrf_token(self):
        import re, glob
        for path in glob.glob(os.path.join(config.BASE_DIR, "templates", "*.html")):
            html = open(path, encoding="utf-8").read()
            for form in re.finditer(r'<form\b[^>]*method="POST"[^>]*>\s*(.{0,120})', html, re.S):
                self.assertIn("csrf_token", form.group(0), f"{os.path.basename(path)} has a POST form without a CSRF token")

    # ---- login throttling ----
    def test_lockout_after_repeated_failures_even_with_correct_password(self):
        config.LOGIN_MAX_ATTEMPTS = 3
        for _ in range(3):
            login(self.client, "admin", "wrong")
        r = login(self.client, "admin", "adminpass1")
        self.assertEqual(r.status_code, 429)

    def test_successful_login_clears_failure_count(self):
        config.LOGIN_MAX_ATTEMPTS = 3
        login(self.client, "admin", "wrong"); login(self.client, "admin", "wrong")
        self.assertEqual(login(self.client, "admin", "adminpass1").status_code, 302)
        self.client.get("/logout")
        login(self.client, "admin", "wrong"); login(self.client, "admin", "wrong")
        self.assertEqual(login(self.client, "admin", "adminpass1").status_code, 302)  # not locked

    def test_unknown_usernames_are_throttled_too(self):
        config.LOGIN_MAX_ATTEMPTS = 2
        login(self.client, "ghost", "x"); login(self.client, "ghost", "x")
        self.assertEqual(login(self.client, "ghost", "x").status_code, 429)

    # ---- RBAC ----
    def test_teacher_cannot_delete_student_but_admin_can(self):
        from database.db import query_one
        login(self.client, "teacher", "teacherpass1")
        r = self.client.post("/students/S1/delete", follow_redirects=True)
        self.assertIn(b"admin only", r.data)
        self.assertIsNotNone(query_one("SELECT 1 FROM students WHERE student_id='S1'"))
        self.client.get("/logout")
        login(self.client, "admin", "adminpass1")
        self.client.post("/students/S1/delete")
        self.assertIsNone(query_one("SELECT 1 FROM students WHERE student_id='S1'"))

    def test_admin_pages_and_training_are_admin_only(self):
        from database.db import query_one
        login(self.client, "teacher", "teacherpass1")
        self.assertEqual(self.client.get("/admin/audit").status_code, 302)
        self.assertEqual(self.client.get("/admin/users").status_code, 302)
        self.client.post("/ml/train")
        self.assertIsNone(query_one("SELECT 1 FROM jobs WHERE name='train_model'"))

    # ---- audit ----
    def test_audit_trail_records_login_and_destructive_actions(self):
        from database.db import query_all
        login(self.client, "admin", "adminpass1")
        self.client.post("/students/S1/delete")
        actions = [r["action"] for r in query_all("SELECT action FROM audit_log")]
        self.assertIn("auth.login", actions)
        self.assertIn("student.delete", actions)
        row = query_all("SELECT * FROM audit_log WHERE action='student.delete'")[0]
        self.assertEqual((row["username"], row["role"], row["entity_id"]), ("admin", "admin", "S1"))

    # ---- accounts ----
    def test_password_change_rules_and_effect(self):
        login(self.client, "teacher", "teacherpass1")
        def change(cur, new, conf):
            return self.client.post("/account/password", data={"current_password": cur, "new_password": new, "confirm_password": conf}, follow_redirects=True)
        self.assertIn(b"incorrect", change("nope", "newpassword1", "newpassword1").data)
        self.assertIn(b"at least 8", change("teacherpass1", "short", "short").data)
        self.assertIn(b"don&#39;t match", change("teacherpass1", "newpassword1", "different1").data)
        self.assertIn(b"Password updated", change("teacherpass1", "newpassword1", "newpassword1").data)
        self.client.get("/logout")
        self.assertEqual(login(self.client, "teacher", "newpassword1").status_code, 302)

    def test_cannot_delete_last_admin_or_self(self):
        from database.db import query_one
        login(self.client, "admin", "adminpass1")
        admin_id = query_one("SELECT id FROM users WHERE username='admin'")["id"]
        self.client.post(f"/admin/users/{admin_id}/delete")
        self.assertIsNotNone(query_one("SELECT 1 FROM users WHERE username='admin'"))

    # ---- hardening ----
    def test_security_headers_and_cookie_flags(self):
        r = self.client.get("/login")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        r = login(self.client, "admin", "adminpass1")
        cookie = r.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)

    def test_secret_key_is_not_a_hardcoded_literal(self):
        self.assertGreaterEqual(len(config.SECRET_KEY), 32)
        self.assertNotIn("dev-secret-key", config.SECRET_KEY)


if __name__ == "__main__":
    unittest.main()
