"""
Central configuration.

Every deployment-sensitive value can be overridden with an environment
variable or a `.env` file in the project root (see .env.example), so
secrets and machine-specific settings never need to be edited into source
control.
"""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv(path):
    """Tiny .env reader (KEY=VALUE per line) -- avoids an extra dependency.
    Real environment variables always win over the file."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(os.path.join(BASE_DIR, ".env"))


def _env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _load_secret_key():
    """SECRET_KEY from the environment, else a random key generated once and
    persisted under instance/ -- never a hard-coded string in source."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    instance_dir = os.path.join(BASE_DIR, "instance")
    key_path = os.path.join(instance_dir, "secret_key")
    try:
        if os.path.exists(key_path):
            with open(key_path, "r", encoding="utf-8") as f:
                existing = f.read().strip()
            if existing:
                return existing
        os.makedirs(instance_dir, exist_ok=True)
        key = secrets.token_hex(32)
        with open(key_path, "w", encoding="utf-8") as f:
            f.write(key)
        return key
    except OSError:
        return secrets.token_hex(32)  # read-only FS: ephemeral key (sessions reset on restart)


# ---------------------------------------------------------------------------
# Application / environment
# ---------------------------------------------------------------------------
APP_VERSION = "2.0.0"
ENV = os.environ.get("APP_ENV", "development")
DEBUG = _env_bool("DEBUG", ENV != "production")
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "5000"))
SECRET_KEY = _load_secret_key()

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
CSRF_ENABLED = _env_bool("CSRF_ENABLED", True)
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", False)  # set True behind HTTPS
SESSION_LIFETIME_HOURS = int(os.environ.get("SESSION_LIFETIME_HOURS", "8"))
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "10"))
MIN_PASSWORD_LENGTH = 8

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_TO_FILE = _env_bool("LOG_TO_FILE", True)

# ---------------------------------------------------------------------------
# Database (SQLite in WAL mode; schema managed by versioned migrations)
# ---------------------------------------------------------------------------
DATABASE_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "database", "attendance.db"))
MIGRATIONS_DIR = os.path.join(BASE_DIR, "database", "migrations")

# ---------------------------------------------------------------------------
# Background jobs (in-process worker pool; same submit/status interface a
# Celery+Redis deployment would expose -- see core/jobs.py)
# ---------------------------------------------------------------------------
JOB_WORKERS = int(os.environ.get("JOB_WORKERS", "2"))
JOBS_SYNC = _env_bool("JOBS_SYNC", False)  # run jobs inline (used by tests)

# ---------------------------------------------------------------------------
# First-run bootstrap
# ---------------------------------------------------------------------------
AUTO_SEED_DEMO = _env_bool("AUTO_SEED_DEMO", True)  # seed demo data when the DB is empty

# ---------------------------------------------------------------------------
# Face recognition (ArcFace via insightface's "buffalo_l" model pack)
# ---------------------------------------------------------------------------
FACES_DIR = os.path.join(BASE_DIR, "data", "faces")  # stores *.npy embeddings, not images
FACE_SAMPLES_PER_STUDENT = 15

ARCFACE_MODEL_NAME = "buffalo_l"
ARCFACE_CTX_ID = -1                # -1 = CPU, 0 = first GPU
ARCFACE_DET_SIZE = (480, 480)
ARCFACE_MIN_DET_SCORE = 0.5

# ArcFace embeddings are L2-normalized, so cosine SIMILARITY (higher =
# better match) is the natural score here -- the opposite of LBPH's
# "lower is better" distance. Verified empirically: different people
# scored -0.08 to 0.06; genuine matches scored 0.6+.
ARCFACE_SIMILARITY_THRESHOLD = 0.45

FACE_GALLERY_PATH = os.path.join(BASE_DIR, "models", "face_gallery.npz")
# "auto" uses FAISS when installed, else a NumPy dot-product search (both
# exact cosine similarity on L2-normalised embeddings).
VECTOR_BACKEND = os.environ.get("VECTOR_BACKEND", "auto")

# How often (in frames) a tracked face gets a fresh ArcFace recognition
# check rather than trusting the tracker's last-known identity. Paired
# with the fast/full detection split in face_reco/embedder.py -- this is
# what keeps the live attendance loop from lagging.
RECOGNIZE_EVERY_N_FRAMES = 15

# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
CAMERA_INDEX = 0
CAMERA_WARMUP_FRAMES = 15

# ---------------------------------------------------------------------------
# Machine learning (academic performance prediction)
# ---------------------------------------------------------------------------
# REDESIGNED FEATURE SET: no more Assignment/Quiz/Internal/Lab categories.
# Marks entry is now fully generic (Subject + free-typed Exam Name + Total
# Mark), so there's no reliable way to bucket a real exam into one of
# those four categories automatically. Instead, every mark a student has
# (regardless of subject or exam name) is averaged into ONE feature:
# "marks average %". Combined with real attendance % and previous GPA,
# that's the full feature set used for prediction.
ML_DATASET_PATH = os.path.join(BASE_DIR, "data", "academic_dataset.csv")
ML_FEATURE_COLUMNS = [
    "attendance_percentage",
    "marks_average_percentage",
    "previous_gpa",
]
ML_TARGET_COLUMN = "final_score"

# ---------------------------------------------------------------------------
# Model registry (versioned models instead of one overwritten .pkl file)
# ---------------------------------------------------------------------------
MODEL_REGISTRY_DIR = os.path.join(BASE_DIR, "models", "registry")
CURRENT_VERSION_POINTER = os.path.join(MODEL_REGISTRY_DIR, "current_version.txt")
BASELINE_STATS_PATH = os.path.join(MODEL_REGISTRY_DIR, "training_baseline_stats.json")

# ---------------------------------------------------------------------------
# Cross-validation & hyperparameter tuning
# ---------------------------------------------------------------------------
CV_FOLDS = 5
RF_PARAM_GRID = {
    "model__n_estimators": [100, 200],
    "model__max_depth": [4, 6, 8, None],
    "model__min_samples_leaf": [1, 2, 4],
}

# ---------------------------------------------------------------------------
# Drift monitoring
# ---------------------------------------------------------------------------
DRIFT_RELATIVE_THRESHOLD = 0.15

# ---------------------------------------------------------------------------
# Performance / risk bands (out of 100)
# ---------------------------------------------------------------------------
PERFORMANCE_BANDS = [
    (90, 100, "Excellent"),
    (80, 89.999, "Very Good"),
    (70, 79.999, "Good"),
    (60, 69.999, "Average"),
    (0, 59.999, "Poor"),
]
RISK_BANDS = [
    (75, 100, "Low"),
    (55, 74.999, "Medium"),
    (0, 54.999, "High"),
]
