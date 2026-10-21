"""Shared test scaffolding: an isolated temp DB/registry and a ready app client."""

import os
import sys
import tempfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


def isolate(tmp=None):
    """Point every writable path at a fresh temp dir and migrate an empty DB."""
    tmp = tmp or tempfile.mkdtemp()
    config.DATABASE_PATH = os.path.join(tmp, "test.db")
    config.ML_DATASET_PATH = os.path.join(tmp, "dataset.csv")
    config.MODEL_REGISTRY_DIR = os.path.join(tmp, "registry")
    config.CURRENT_VERSION_POINTER = os.path.join(config.MODEL_REGISTRY_DIR, "current_version.txt")
    config.BASELINE_STATS_PATH = os.path.join(config.MODEL_REGISTRY_DIR, "training_baseline_stats.json")
    config.FACES_DIR = os.path.join(tmp, "faces")
    config.FACE_GALLERY_PATH = os.path.join(tmp, "gallery.npz")
    config.RF_PARAM_GRID = {"model__n_estimators": [30], "model__max_depth": [4, None]}
    from database.db import init_db
    init_db()
    return tmp


def add_user(username, password, role):
    from database.db import execute
    from werkzeug.security import generate_password_hash
    execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), role))


def make_client():
    from app import create_app
    return create_app().test_client()


def login(client, username, password):
    return client.post("/login", data={"username": username, "password": password}, follow_redirects=False)


def write_dataset(n=60):
    import csv, random
    rng = random.Random(1)
    with open(config.ML_DATASET_PATH, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["student_id", "attendance_percentage", "marks_average_percentage", "previous_gpa", "final_score"])
        for i in range(n):
            a, m, g = rng.uniform(50, 100), rng.uniform(40, 100), rng.uniform(5, 10)
            w.writerow([f"S{i}", a, m, g, min(100, max(0, a * 0.35 + m * 0.45 + g * 2))])
