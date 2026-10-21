import os, sys, unittest, tempfile
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class AuthTestCase(unittest.TestCase):
    def setUp(self):
        import config
        self.tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp_db.close()
        config.DATABASE_PATH = self.tmp_db.name
        from database.db import init_db, execute
        init_db()
        from werkzeug.security import generate_password_hash
        execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                ("testadmin", generate_password_hash("testpass"), "admin"))
        from app import create_app
        self.client = create_app().test_client()

    def tearDown(self):
        os.unlink(self.tmp_db.name)

    def test_login_page_loads(self):
        self.assertEqual(self.client.get("/login").status_code, 200)

    def test_valid_login_redirects(self):
        r = self.client.post("/login", data={"username": "testadmin", "password": "testpass"})
        self.assertEqual(r.status_code, 302)

    def test_invalid_password_rejected(self):
        r = self.client.post("/login", data={"username": "testadmin", "password": "wrong"}, follow_redirects=True)
        self.assertIn(b"Invalid username or password", r.data)

    def test_dashboard_requires_login(self):
        r = self.client.get("/dashboard", follow_redirects=True)
        self.assertIn(b"Please log in", r.data)

    def test_logout_clears_session(self):
        self.client.post("/login", data={"username": "testadmin", "password": "testpass"})
        self.client.get("/logout")
        r = self.client.get("/dashboard", follow_redirects=True)
        self.assertIn(b"Please log in", r.data)


if __name__ == "__main__":
    unittest.main()
