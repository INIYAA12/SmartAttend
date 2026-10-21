"""
Built-in demo data.

Builds a complete, realistic demo school so every screen works the moment
the app starts:
  - 1 admin + 3 teacher logins
  - 8 global subjects (Syllabus Management)
  - 45 students across sections A/B/C, each with a previous GPA
    (the last 3 are "new admissions" with no history, to show how the
    system reports missing data instead of guessing)
  - ~5 weeks of attendance history (3 sessions per weekday)
  - 3-4 exams per subject with marks for every student
  - the synthetic ML training dataset, a trained + versioned model, and a
    prediction for every student with complete data

EVERYTHING HERE IS SYNTHETIC DEMO DATA, generated from a fixed random seed
so it is reproducible. It is flagged in the UI ("DEMO DATA" badge). It is
never real institutional data. Face embeddings are NOT seeded -- faces must
be captured from a real webcam.

Run:   python database/seed.py                 (fresh DB: full demo)
       python database/seed.py --reset         (wipe DB + model, reseed)
       python database/seed.py --no-history    (users/subjects/students only)
       python database/seed.py --skip-train    (don't train the model)
"""

import argparse
import csv
import datetime
import os
import random
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import init_db, execute, query_one, transaction
from werkzeug.security import generate_password_hash

SECTIONS = ["A", "B", "C"]
DEPARTMENT, YEAR, SEMESTER = "AI & ML", "3", "5"
STUDENTS_PER_SECTION = 15
NEW_ADMISSIONS = 3          # last N students get no GPA / attendance / marks
HISTORY_DAYS = 35
SESSIONS_PER_DAY = 3

DEMO_USERS = [("admin", "admin123", "admin")] + [(f"teacher_{s.lower()}", "teacher123", "teacher") for s in SECTIONS]

SUBJECTS = [
    ("CS301", "Big Data Technologies"), ("CS302", "Machine Learning"),
    ("CS303", "Computer Networks"), ("CS304", "Operating Systems"),
    ("CS305", "Cloud Computing"), ("CS306", "Software Engineering"),
    ("CS307", "Cyber Security"), ("CS308", "Data Structures"),
]
EXAMS = [("Unit Test 1", 50), ("Assignment 1", 20), ("Mid Term", 100)]
EXTRA_EXAMS = [("Quiz 1", 20)]       # only for the first 3 subjects (not every subject has one)

FIRST_NAMES = ["Aditi", "Rahul", "Sara", "Vikram", "Priya", "Arjun", "Ananya", "Karthik", "Meera", "Rohan",
               "Divya", "Aryan", "Ishita", "Siddharth", "Kavya", "Nikhil", "Pooja", "Aditya", "Sneha", "Varun",
               "Riya", "Sanjay", "Neha", "Manish", "Deepika", "Rajesh", "Swathi", "Vivek", "Anjali", "Harish",
               "Lakshmi", "Suresh", "Preethi", "Gautam", "Ramya", "Kiran", "Shreya", "Akash", "Nandini",
               "Vishal", "Tanvi", "Yash", "Aishwarya", "Naveen", "Radhika", "Sameer"]
LAST_NAMES = ["Rao", "Menon", "Fernandes", "Sethi", "Nair", "Reddy", "Sharma", "Kumar", "Iyer", "Gupta",
              "Pillai", "Verma", "Krishnan", "Joshi", "Desai", "Patel", "Chowdhury", "Bose", "Mehta", "Kapoor"]

# (probability, diligence range, ability range %, previous-GPA range)
TIERS = [
    (0.30, (0.88, 0.99), (78, 95), (8.2, 9.6)),   # strong
    (0.50, (0.72, 0.90), (60, 78), (6.8, 8.4)),   # average
    (0.20, (0.50, 0.70), (35, 58), (5.0, 6.8)),   # needs support
]


# --------------------------------------------------------------------------
# Building blocks
# --------------------------------------------------------------------------
def seed_users():
    if query_one("SELECT id FROM users LIMIT 1"):
        return False
    with transaction() as conn:
        for username, password, role in DEMO_USERS:
            conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                         (username, generate_password_hash(password), role))
    return True


def seed_subjects():
    if query_one("SELECT id FROM subjects LIMIT 1"):
        return False
    with transaction() as conn:
        conn.executemany("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)", SUBJECTS)
    return True


def _pick_tier(rng):
    r, acc = rng.random(), 0.0
    for tier in TIERS:
        acc += tier[0]
        if r <= acc:
            return tier
    return TIERS[-1]


def seed_students(rng):
    """Returns {student_id: traits} for the students created (empty if they already exist)."""
    if query_one("SELECT id FROM students LIMIT 1"):
        return {}
    traits, used, num = {}, set(), 1
    total = len(SECTIONS) * STUDENTS_PER_SECTION
    with transaction() as conn:
        for section in SECTIONS:
            for _ in range(STUDENTS_PER_SECTION):
                while True:
                    name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
                    if name not in used:
                        used.add(name)
                        break
                sid = f"STU{num:03d}"
                new_admission = num > total - NEW_ADMISSIONS
                _, dil, abil, gpa = _pick_tier(rng)
                traits[sid] = {
                    "diligence": rng.uniform(*dil), "ability": rng.uniform(*abil),
                    "gpa": None if new_admission else round(rng.uniform(*gpa), 2),
                    "new": new_admission,
                }
                conn.execute(
                    """INSERT INTO students (student_id, roll_number, name, department, year, section,
                                             semester, email, previous_gpa) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (sid, f"23A{num:03d}", name, DEPARTMENT, YEAR, section, SEMESTER,
                     name.lower().replace(" ", ".") + "@example.edu", traits[sid]["gpa"]),
                )
                num += 1
    return traits


def seed_attendance_history(rng, traits):
    """~5 weeks of weekday sessions; each student attends with probability
    equal to their diligence, so the data has a realistic spread."""
    today = datetime.date.today()
    days = [today - datetime.timedelta(days=i) for i in range(1, HISTORY_DAYS + 1)]
    days = sorted(d for d in days if d.weekday() < 5)
    times = ["09:05", "10:10", "11:20"]
    rows = []
    for di, day in enumerate(days):
        for k in range(SESSIONS_PER_DAY):
            subject_id = (di * SESSIONS_PER_DAY + k) % len(SUBJECTS) + 1
            for sid, t in traits.items():
                if t["new"]:
                    continue
                if rng.random() < t["diligence"]:
                    hh, mm = times[k].split(":")
                    stamp = f"{hh}:{int(mm) + rng.randint(0, 9):02d}:{rng.randint(0, 59):02d}"
                    rows.append((sid, subject_id, day.isoformat(), stamp, "Present"))
    with transaction() as conn:
        conn.executemany("INSERT OR IGNORE INTO attendance (student_id, subject_id, date, time, status) VALUES (?,?,?,?,?)", rows)
    return len(rows)


def seed_marks(rng, traits):
    rows = []
    for subject_idx in range(len(SUBJECTS)):
        subject_id = subject_idx + 1
        exams = EXAMS + (EXTRA_EXAMS if subject_idx < 3 else [])
        subject_effect = rng.uniform(-4, 4)  # some subjects are harder than others
        for exam_name, total in exams:
            for sid, t in traits.items():
                if t["new"]:
                    continue
                pct = max(8.0, min(99.0, t["ability"] + subject_effect + rng.gauss(0, 7)))
                obtained = round(pct / 100 * total * 2) / 2            # half-mark resolution
                obtained = min(obtained, total)
                rows.append((sid, subject_id, exam_name, total, obtained, round(obtained / total * 100, 2)))
    with transaction() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO marks (student_id, subject_id, exam_name, total_marks, obtained_marks, percentage) "
            "VALUES (?,?,?,?,?,?)", rows)
    return len(rows)


def generate_synthetic_academic_dataset(n_records=300):
    """SYNTHETIC training set: attendance %, marks average %, previous GPA -> final score."""
    os.makedirs(os.path.dirname(config.ML_DATASET_PATH), exist_ok=True)
    if os.path.exists(config.ML_DATASET_PATH):
        return False
    rng = random.Random(42)
    rows = []
    for i in range(1, n_records + 1):
        attendance = round(rng.uniform(50, 100), 1)
        marks_avg = round(rng.uniform(40, 100), 1)
        gpa = round(rng.uniform(5.0, 10.0), 2)
        base = attendance * 0.35 + marks_avg * 0.45 + (gpa * 10) * 0.20
        final = max(0, min(100, round(base + rng.uniform(-5, 5), 1)))
        rows.append({"student_id": f"SYN{i:04d}", "attendance_percentage": attendance,
                     "marks_average_percentage": marks_avg, "previous_gpa": gpa, "final_score": final})
    with open(config.ML_DATASET_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return True


def set_meta(key, value):
    execute("INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value))


def reset_all():
    """Deletes the database, dataset and trained models. Captured face
    embeddings (data/faces) are deliberately left alone -- they come from a
    real camera and can't be regenerated."""
    removed = []
    for path in (config.DATABASE_PATH, config.DATABASE_PATH + "-wal", config.DATABASE_PATH + "-shm", config.ML_DATASET_PATH):
        if os.path.exists(path):
            os.remove(path)
            removed.append(os.path.basename(path))
    if os.path.isdir(config.MODEL_REGISTRY_DIR):
        for name in os.listdir(config.MODEL_REGISTRY_DIR):
            if name != ".gitkeep":
                os.remove(os.path.join(config.MODEL_REGISTRY_DIR, name))
                removed.append(name)
    return removed


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def run(reset=False, history=True, train=True, log=print):
    """Seeds the database. Idempotent: existing data is never duplicated."""
    if reset:
        removed = reset_all()
        log(f"Reset: removed {len(removed)} file(s).")
    applied = init_db()
    if applied:
        log(f"Migrations applied: {', '.join(applied)}")

    rng = random.Random(7)  # fixed seed -> identical demo data every time
    summary = {"users": seed_users(), "subjects": seed_subjects()}
    traits = seed_students(rng)
    summary["students"] = len(traits)
    generate_synthetic_academic_dataset()

    if traits and history:
        summary["attendance_rows"] = seed_attendance_history(rng, traits)
        summary["marks_rows"] = seed_marks(rng, traits)
        set_meta("demo_data", "1")
        log(f"Seeded {len(traits)} students, {len(SUBJECTS)} subjects, "
            f"{summary['attendance_rows']} attendance records, {summary['marks_rows']} marks.")
    elif traits:
        log(f"Seeded {len(traits)} students, {len(SUBJECTS)} subjects (no history).")

    if train and history and traits:
        from ml.train import train_model
        from services.prediction_service import predict_all_students
        log("Training the prediction model (cross-validation + tuning)...")
        metrics = train_model()
        log(f"  selected {metrics['selected_model']}  MAE={metrics['mae']}  R2={metrics['r2_score']}")
        result = predict_all_students()
        summary["predictions"] = result
        log(f"  predictions: {result['predicted']} students "
            f"({result['risk_counts']}), {len(result['skipped'])} skipped for missing data")

    if summary["users"]:
        log("Logins:  admin / admin123   |   teacher_a, teacher_b, teacher_c / teacher123   (change these!)")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the built-in demo school.")
    parser.add_argument("--reset", action="store_true", help="Wipe the database and models, then reseed.")
    parser.add_argument("--no-history", action="store_true", help="Seed users/subjects/students only.")
    parser.add_argument("--skip-train", action="store_true", help="Don't train the model after seeding.")
    args = parser.parse_args()
    run(reset=args.reset, history=not args.no_history, train=not args.skip_train)
