# Architecture (v2)

```
Browser (Bootstrap + Chart.js)
   │  HTTP (CSRF-protected forms, fetch with X-CSRF-Token)
   ▼
Waitress (serve.py)  ← optional Nginx in front (deploy/nginx.conf)
   ▼
Flask app (app.py)       thin routes → services / domain modules
   ├── routes/           auth · dashboard · students · syllabus · academic · face
   │                     attendance · predictions · reports · system(/health) · admin
   ├── services/         audit · auth_service (throttling) · attendance_service · prediction_service
   ├── academic/         marks upsert + feature computation
   ├── ml/               train (CV + tuning) · registry (versions) · predict · drift (live data)
   ├── face_reco/        embedder (fast/full detection split) · vector_index · recognizer
   │                     camera_worker (background capture) · registration · attendance_camera · tracker
   └── core/             config-driven logging · security (CSRF/RBAC) · jobs · bootstrap · tasks
   ▼
SQLite (WAL) ─ versioned migrations      Model registry (models/registry)      Face gallery (.npz)
```

## Key design decisions

**Camera ownership.** One background thread (`CameraSession`) owns the webcam and runs a
*processor* (registration or attendance) on every frame, publishing the latest JPEG.
The HTTP stream only serves that frame, so capture speed is independent of any request,
refreshing the page doesn't touch the camera, and several viewers can watch. Only one
session runs at a time (one physical camera).

**Fast / full detection split.** Every frame uses detection-only (cheap, ~3× faster). The
heavier detection + ArcFace embedding runs only when needed: when saving a registration
sample, and when a tracked face is new or due for a periodic re-check.

**Jobs.** Training and bulk prediction run on a worker pool and persist status in the
`jobs` table; the UI polls `/jobs/<id>`. A newly promoted model automatically refreshes
every student's prediction. Stale jobs are failed on restart.

**Prediction.** Features: attendance % (derived from real attendance records), marks
average % (all exams, all subjects), previous GPA. Trained on a synthetic baseline; applied
to real students for inference. Drift is measured between the training baseline and the
**live** student population (needs ≥ 5 students with complete data).

**Security.** CSRF on every state-changing request; admin-only actions (delete student /
subject, train, roll back, users, audit); per-username login throttling (also for unknown
usernames); session fixation protection; HttpOnly + SameSite cookies; security headers;
secret key from env or a generated persistent file; audit trail of sensitive actions.

## Recommendations vs. what is implemented

| Recommendation | Status |
|---|---|
| Replace Flask dev server | **Done** — Waitress (`serve.py`), run and tested. Gunicorn isn't used: it doesn't run on Windows, and camera/job state is per-process so a single multi-threaded worker is required anyway |
| Nginx reverse proxy | **Provided, not run** — `deploy/nginx.conf` (stream buffering off) + `docker-compose.yml` |
| Background workers (camera, training) | **Done** and tested, including with the real ArcFace model |
| Task queue (Celery + Redis) | **Not included.** An in-process job manager exposes the same submit/status interface. Celery/Redis only pays off with multiple machines; swap `core/jobs.py` if you need it |
| FAISS vector index | **Done** — used automatically when installed, NumPy fallback; both tested for identical results |
| PostgreSQL | **Not implemented.** SQLite in WAL mode with versioned migrations. The SQL uses SQLite dialect (`INSERT OR IGNORE`, `datetime('now')`, `ON CONFLICT`), so moving to Postgres means porting those; all DB access goes through `database/db.py` to keep that localised |
| Service layer / thin routes | **Partly done** — prediction, auth, attendance, audit extracted; some simple CRUD still queries the DB directly in routes |
| Config & secrets from environment | **Done** |
| Structured logging, health check | **Done** — `logs/app.log`, `/health` |
| Schema migrations | **Done** |
| CSRF, RBAC, throttling, audit | **Done** and tested |
| Drift on live data | **Done** (the earlier version compared training data to itself) |
| CI | **Provided, not run** — `.github/workflows/ci.yml` |
| Docker | **Provided, not built** — `Dockerfile`, `docker-compose.yml` |

## Not covered

Liveness / anti-spoofing, encryption of embeddings at rest, HTTPS termination (set
`SESSION_COOKIE_SECURE=1` behind TLS), a CSP header, multi-camera / multi-classroom
support, and validating the prediction model against real historical outcomes.
