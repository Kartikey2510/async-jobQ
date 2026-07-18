# Job Queue API

Minimal FastAPI async job queue: submit jobs, poll status. SQLite + in-process worker pool.

## Layout

```
app/
  main.py           # FastAPI app, starts/stops worker pool
  db.py             # engine, session, init_db
  routes/jobs.py    # HTTP endpoints
  services/jobs.py  # create/get + enqueue
  models/job.py     # Pydantic schemas + status enum
  models/orm.py     # SQLAlchemy JobRecord
  store/jobs.py     # persistence via SQLAlchemy
  workers/pool.py   # in-process queue + worker threads
```

## Setup

```bash
cd async-jobQ
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
cd async-jobQ
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

SQLite file `jobs.db` is created on startup in the project root.

Mock processing: each job sleeps 3 seconds, then sets `result` to an echo of the payload.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/jobs` | Create a job (202). Body: non-empty JSON object with ≥1 non-null value. |
| `GET` | `/jobs/{job_id}` | Fetch status / result / timestamps (404 if missing). |

### Examples

```bash
# Create a job (202) — returns immediately with id
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"task": "echo", "message": "hello"}'

# Poll status (replace JOB_ID) — queued → running → succeeded (~3s)
curl -s http://localhost:8000/jobs/JOB_ID
```
