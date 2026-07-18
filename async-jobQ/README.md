# Job Queue API

FastAPI async job queue with SQLite storage, in-process workers, and DigitalOcean Serverless Inference.

## Layout

```
app/
  main.py                 # FastAPI app, loads .env, starts worker pool
  db.py                   # engine, session, init_db
  routes/jobs.py          # HTTP endpoints
  services/jobs.py        # create/get + enqueue
  models/job.py           # Pydantic schemas
  models/orm.py           # SQLAlchemy JobRecord
  store/jobs.py           # persistence
  workers/pool.py         # queue + worker threads
  workers/inference.py    # DigitalOcean LLM client
```

## Setup

```bash
cd async-jobQ
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then put your DO model access key in .env
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/jobs` | Create a job (202). |
| `GET` | `/jobs/{job_id}` | Fetch status / result. |

### Example

```bash
# Create an inference job
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Say hello in one sentence"}'

# Or with explicit model / chat messages
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "llama3.3-70b-instruct",
    "messages": [{"role": "user", "content": "What is 2+2?"}]
  }'

# Poll until status is succeeded or failed
curl -s http://localhost:8000/jobs/JOB_ID
```
