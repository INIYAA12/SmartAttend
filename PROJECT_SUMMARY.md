# Project Summary

## Smart Attendance Monitoring and Academic Performance Prediction System
### Using Computer Vision and Machine Learning

**What it is.** A working prototype that automates attendance with webcam face
recognition (ArcFace) and uses machine learning to predict each student's likely
performance and flag at-risk students early — in one platform with a faculty dashboard.

**Workflow.** Syllabus Management → Student registration → Face capture → Face
recognition → Automatic attendance → Marks entry (Subject + free-typed Exam Name +
Total Mark) → Features (Attendance %, Marks Average %, Previous GPA) → ML prediction →
Risk analysis → Dashboard & reports.

**Engineering highlights (v2).**
- Camera runs in a background worker; detection is split into a cheap every-frame path
  and a heavier embedding path used only when needed.
- Face gallery is a vector index (FAISS when installed, NumPy otherwise).
- Training and bulk prediction run as background jobs with live progress; a newly
  promoted model automatically refreshes all predictions.
- Versioned model registry with a promotion guard, plus drift monitoring on live students.
- Versioned DB migrations (SQLite, WAL), env-driven config, structured logging, `/health`.
- Security: CSRF, role-based access, login throttling, audit log, hardened sessions.
- Ships with a built-in demo school (45 students, 8 subjects, ~5 weeks of attendance,
  marks, a trained model and predictions) so it works on first start.

**Key design decision.** Marks have no "final exam" category, so there is no reliable
ground-truth label in real data. The model is trained on a synthetic baseline and applied
to real students' current numbers for prediction. Stated openly, not hidden.

**Status.** 104 automated tests pass, including an end-to-end test with the real ArcFace
model (register two faces → recognise each → reject a stranger) and a verified live-server
run (CSRF, login lockout, job progress, camera-failure handling).

**Limitations.** No liveness/anti-spoofing; prediction validated only on synthetic data;
single camera/machine; accuracy depends on lighting and camera quality. Postgres, Celery/Redis
and containerised deployment are documented as migration paths in `docs/ARCHITECTURE.md`,
not implemented/verified here.
