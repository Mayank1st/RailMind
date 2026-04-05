# RailMind

AI-Powered Railway Reservation System — IRCTC Replica with Intelligent Automation

---

## Zaroori steps — sequence mein (Hinglish)

*Neeche wale steps **order mein** follow karo; skip mat karo warna DB, email ya Celery break ho jayega.*

### Step 1 — PostgreSQL chalu hona chahiye

- Machine pe **PostgreSQL install** ho aur service **running** ho (default port `5432`).
- Ek **empty database** bana lo (jaise `railmind_db`) — ya app first start pe DB create kar sakti hai, lekin Postgres server pehle se up hona chahiye.

### Step 2 — Redis install + baad mein run

- **Redis** install karo (macOS: `brew install redis`).
- Abhi start mat karo; **Step 8 (Terminal A)** mein `redis-server` chalayenge.

### Step 3 — Repo clone + project folder

```bash
git clone <your-repo-url>
cd RailMind
```

### Step 4 — Virtual environment (venv)

```bash
python3 -m venv venv
source venv/bin/activate          # macOS / Linux
# Windows: venv\Scripts\activate
```

*Har nayi terminal mein `source venv/bin/activate` dubara karna padega.*

### Step 5 — Dependencies install

```bash
pip install -r requirements.txt
```

*Isme Alembic ke liye **psycopg**, app ke liye **asyncpg**, Celery + **redis** package sab aa jate hain.*

### Step 6 — `.env` file (mandatory keys)

- Project root mein **`.env`** banao (agar `.env.example` ho toh copy karke values bharo).
- **`app/config.py`** jo keys maangta hai woh **exact names** se honi chahiye (`case_sensitive=True` hai).

**Minimum jo set karni hi karni hain:**

| Variable | Baat (Hinglish) |
|----------|------------------|
| `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` | Postgres connection |
| `DB_SCHEMA` | Schema name, jaise `railmind_be` — tables isi schema mein banenge |
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | Pool size, jaise `5` aur `10` |
| `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASSWORD` | Gmail + **App Password** (normal password nahi) |
| `EMAIL_SMTP_HOST` | `smtp.gmail.com` |
| `JWT_SECRET_KEY` | Random long string |
| `RAPIDAPI_KEY`, `RAPIDAPI_HOST` | RapidAPI config (project ke hisaab se) |

**Strongly recommended:**

```env
REDIS_URL=redis://127.0.0.1:6379/0
```

*URL **hamesha** `redis://` se start honi chahiye — warna Celery galat broker (AMQP) use kar leta hai.*

**Local dev jaldi test ke liye (Redis/Celery bina OTP bhejna):**

```env
CELERY_TASK_ALWAYS_EAGER=true
```

*Isse task API process ke andar hi run hoga; production mein `false` rakho.*

> **Tip:** Agar dotenv “parse error” de toh `.env` mein `#` ya spaces wali lines ko **double quotes** mein band karo.

### Step 7 — Database migrations (Alembic)

Project root se (venv activated):

```bash
alembic upgrade head
```

*Ye **sync psycopg** se chalti hai — tables + `alembic_version` tumhare `DB_SCHEMA` mein create/update honge.*

Check karne ke liye:

```bash
alembic current
# output mein (head) revision dikhna chahiye
```

### Step 8 — Ab 3 cheezein parallel (3 terminals)

**Terminal A — Redis**

```bash
source venv/bin/activate   # optional, redis-cli ke liye
redis-server
```

Verify:

```bash
redis-cli ping    # PONG aana chahiye
```

**Terminal B — Celery worker** *(skip only if `CELERY_TASK_ALWAYS_EAGER=true`)*

```bash
cd /path/to/RailMind
source venv/bin/activate
celery -A app.tasks.celery_app:celery_app worker -l info
```

*Nahi chalayoge toh `.delay()` wale tasks queue mein padenge — OTP email worker ke bina process nahi honge.*

**Terminal C — API server**

```bash
cd /path/to/RailMind
source venv/bin/activate
fastapi dev app/main.py
# ya: uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

### Step 9 — Quick sanity check

- `GET /` — app up
- `GET /db-test` — DB connected
- Register flow — logs mein `[railmind]` email / Celery lines dekho

---

## Full setup checklist (English, in order)

1. **Install tools:** Python 3.11+, PostgreSQL (running), Redis (install; start later), Git.
2. **Clone & enter repo:** `git clone <url> && cd RailMind`
3. **Virtualenv:** `python3 -m venv venv` → `source venv/bin/activate` (Windows: `venv\Scripts\activate`)
4. **Dependencies:** `pip install -r requirements.txt`
5. **Create `.env` in project root** with the variables your app needs (names are **case-sensitive**, match `app/config.py`):

   | Required in `.env` |
   |-------------------|
   | `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SCHEMA`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` |
   | `EMAIL_SMTP_USER`, `EMAIL_SMTP_PASSWORD`, `EMAIL_SMTP_HOST` |
   | `JWT_SECRET_KEY` |
   | `RAPIDAPI_KEY`, `RAPIDAPI_HOST` |

   **Recommended:** `REDIS_URL=redis://127.0.0.1:6379/0` (must start with `redis://`).  
   **Optional:** `MAIL_FROM`, `CELERY_TASK_ALWAYS_EAGER=true` for local email without a worker, `ECHO=true` for SQL logging.

6. **PostgreSQL:** Ensure the server is up; create an empty database with the name in `DB_NAME` if you do not rely on app auto-create.
7. **Migrations (from repo root, venv on):** `alembic upgrade head`  
   - Check: `alembic current` (should show `head`).  
   - **Not** a valid command: `alembic head` — use `alembic heads` or `alembic current`.
8. **Terminal 1 — Redis:** `redis-server` → verify `redis-cli ping` → `PONG`
9. **Terminal 2 — Celery** *(skip if `CELERY_TASK_ALWAYS_EAGER=true`):*  
   `celery -A app.tasks.celery_app:celery_app worker -l info`
10. **Terminal 3 — API:** `fastapi dev app/main.py` or `uvicorn app.main:app --reload`
11. **Open:** `http://127.0.0.1:8000/docs`
12. **Smoke test:** `GET /`, `GET /db-test`, try register; watch logs for `[railmind]` / Celery.

**New migration (after model changes):**  
`alembic revision --autogenerate -m "message"` → **open the file** → remove junk (e.g. fake ENUM `alter_column`, `drop_table('alembic_version')`, random index renames) → then `alembic upgrade head`.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI (Python 3.11+) |
| Database | PostgreSQL 16 |
| Cache / Broker | Redis 7 |
| Task Queue | Celery |
| Email | fastapi-mail (Gmail SMTP) |
| AI Runtime | ONNX / HuggingFace / OpenAI |

---

## Prerequisites

Make sure you have the following installed before starting:

- Python 3.11+
- PostgreSQL 16
- Redis 7
- pip

---

## Project Setup (English quick reference)

Full **sequence** upar **“Zaroori steps (Hinglish)”** section mein hai. Short version:

1. Postgres + Redis installed  
2. `venv` → `pip install -r requirements.txt`  
3. `.env` — see `app/config.py` for exact variable names  
4. `alembic upgrade head`  
5. Three terminals: `redis-server` → `celery -A app.tasks.celery_app:celery_app worker -l info` → `fastapi dev app/main.py` (or `uvicorn app.main:app --reload`)

### `.env` example shape *(values apni machine ke hisaab se)*

```env
DB_USERNAME=postgres
DB_PASSWORD=yourpassword
DB_HOST=127.0.0.1
DB_PORT=5432
DB_NAME=railmind_db
DB_SCHEMA=railmind_be
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10

JWT_SECRET_KEY=change-me-long-random-string

EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_USER=you@gmail.com
EMAIL_SMTP_PASSWORD=your-gmail-app-password
MAIL_FROM=you@gmail.com

REDIS_URL=redis://127.0.0.1:6379/0
CELERY_TASK_ALWAYS_EAGER=false

RAPIDAPI_KEY=your-key
RAPIDAPI_HOST=your-host
```

> **Gmail App Password:** [Google Account → Security → App passwords](https://myaccount.google.com/security)

---

## Database Migrations (Alembic)

```bash
alembic upgrade head          # apply all pending
alembic current               # show current revision
alembic revision --autogenerate -m "message"   # then manually review the file!
alembic downgrade -1          # rollback one step
```

*Migrations **psycopg** (sync) use karti hain; runtime app **asyncpg** use karti hai — dono `requirements.txt` mein hain.*

---

## Project Structure

```
railmind/
├── app/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings via pydantic-settings
│   ├── dependencies.py          # Shared DI: get_db, get_redis
│   ├── core/                    # Security, middleware, exceptions
│   ├── domain/                  # Feature modules (auth, booking, train...)
│   ├── ai/                      # AI pipelines (Phase 2 & 3)
│   ├── integrations/            # Third-party clients
│   │   ├── email_client.py
│   │   └── email_templates/     # HTML email templates
│   │       ├── otp.html
│   │       ├── booking_confirmed.html
│   │       └── booking_cancelled.html
│   ├── tasks/                   # Celery async tasks
│   │   ├── celery_app.py
│   │   ├── notification_tasks.py
│   │   ├── booking_tasks.py
│   │   └── ai_tasks.py
│   └── db/                      # SQLAlchemy base, session, migrations
├── tests/
├── docker/
├── .env.example
├── alembic.ini
├── pyproject.toml
└── README.md
```

---

## Email Templates

HTML templates live in `app/integrations/email_templates/`. They use `{{ placeholder }}` syntax:

| Template | Placeholders |
|----------|-------------|
| `otp.html` | `{{ otp }}`, `{{ user_name }}`, `{{ validity_minutes }}` |
| `booking_confirmed.html` | `{{ user_name }}`, `{{ pnr }}`, `{{ train_name }}`, `{{ journey_date }}` |
| `booking_cancelled.html` | `{{ user_name }}`, `{{ pnr }}`, `{{ refund_amount }}` |

To add a new template, create the HTML file in the folder and load it via:

```python
from app.integrations.email_client import load_template, send_email

body = load_template("your_template.html", key="value")
await send_email(to="user@example.com", subject="Subject", body=body)
```

---

## API Error Codes

| Code | Description | HTTP Status |
|------|-------------|-------------|
| RM-AUTH-001 | Invalid credentials | 401 |
| RM-AUTH-002 | Token expired | 401 |
| RM-AUTH-003 | OTP verification failed | 400 |
| RM-BKG-001 | Seat not available | 409 |
| RM-BKG-002 | Max passengers exceeded | 422 |
| RM-PAY-001 | Payment timeout | 408 |
| RM-AI-001 | AI model inference failed | 503 |

---

## Running Tests

```bash
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Run a specific test file
pytest tests/domain/test_auth.py -v
```

---

## Docker (Optional)

```bash
# Start all services (FastAPI + PostgreSQL + Redis + Celery)
docker-compose -f docker/docker-compose.dev.yml up --build
```

---

## Common Issues

**Celery using AMQP instead of Redis**
Make sure `REDIS_URL` in `.env` starts with `redis://` — e.g. `redis://127.0.0.1:6379/0`.

**OTP email queued but not sent**
The Celery worker is not running. Start it in a separate terminal with the command in Terminal 2 above.

**Email going to spam**
Check the spam/junk folder. Add your sender Gmail address to contacts to avoid future filtering.

**`redis-cli ping` returns connection refused**
Redis is not running. Start it with `redis-server` in Terminal 1.

---

## Phase Roadmap

| Phase | Scope | Timeline |
|-------|-------|----------|
| Phase 1 — Foundation | Core IRCTC feature replica (no AI) | Weeks 1–10 |
| Phase 2 — AI Enhancement | Replace manual workflows with AI | Weeks 11–20 |
| Phase 3 — AI Innovation | Net-new AI features beyond IRCTC | Weeks 21–32 |

---

*RailMind — Internal Codename. Database: `railmind_db`*