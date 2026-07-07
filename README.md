# RailMind

AI-Powered Railway Reservation System — IRCTC Replica with Intelligent Automation

---

## 🌍 Local vs Prod — environment switching (`APP_ENV`)

Config **3 files** mein split hai (secrets ek hi jagah, env-specific cheezein alag):

| File | Kya hai | Git |
|------|---------|-----|
| `.env` | **Shared** — saare secrets + DB credentials (`DB_NAME` / `DB_USERNAME` / `DB_PASSWORD` / `DB_SCHEMA`) | ignored |
| `.env.local` | Local overrides — `DB_HOST=localhost`, `DB_PORT=5432`, `DEBUG=true` | ignored |
| `.env.prod` | Prod overrides — VM DB via SSH tunnel (`DB_HOST=127.0.0.1`, `DB_PORT=5433`) | ignored |

Templates committed hain — copy karke values bharo:

```bash
cp .sample.env .env
cp .sample.env.local .env.local
cp .sample.env.prod .env.prod
```

**Kaunsa env load hoga** yeh ek **shell variable `APP_ENV`** decide karta hai (kisi `.env` ke *andar* nahi — woh to decide karta hai ki konsi file padhni hai). Default `local`:

| `APP_ENV` | Loads | DB |
|-----------|-------|-----|
| *(set nahi)* / `local` | `.env` + `.env.local` | Local Postgres (`localhost:5432`) |
| `prod` | `.env` + `.env.prod` | VM Postgres (tunnel `127.0.0.1:5433`) |

> Internally: `env_file=(".env", f".env.{APP_ENV}")` — `.env.<env>` value **jeetti** hai. Koi real OS env var (jaise docker-compose ka `DB_HOST=postgres`) dono files se upar jeetta hai, to containers bina change ke chalte hain.

### ▶️ Server start

**Local DB pe (default — kuch set karne ki zarurat nahi):**

```bash
source venv/bin/activate
fastapi dev app/main.py            # ya: uvicorn app.main:app --reload
```

**Prod / VM DB pe:** VM ka Postgres internet pe expose nahi hai (SSH-only), isliye **pehle SSH tunnel** chalao, phir `APP_ENV=prod`:

```bash
scripts/db-tunnel.sh               # tunnel background mein (start | status | stop | watch)
APP_ENV=prod fastapi dev app/main.py
```

> **One-time setup** — tunnel ki connection detail tumhari *local* `~/.ssh/config` me rehti hai (repo me hardcode nahi, taaki infra leak na ho). Ek baar yeh `railmind-db` host add karo (apni values bharo):
>
> ```sshconfig
> Host railmind-db
>     HostName <your-vm-host>
>     User <your-ssh-user>
>     IdentityFile ~/.ssh/<your-key>
>     LocalForward 5433 localhost:5432
>     ServerAliveInterval 30
>     ServerAliveCountMax 3
>     ExitOnForwardFailure yes
> ```

> `export APP_ENV=prod` poore terminal session ke liye set kar deta hai; wapas local ke liye `export APP_ENV=local` ya `unset APP_ENV`. **Safer:** inline `APP_ENV=prod <cmd>` — taaki galti se prod DB pe na likho.

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

> **Note:** Config ab **3 files** mein split hai — `.env` (shared secrets) + `.env.local` / `.env.prod` (env-specific). Details + server start upar **"🌍 Local vs Prod"** section mein. Niche wali keys shared `.env` + active `.env.<env>` ka combined set hain.

- Project root mein **`.env`** banao (`cp .sample.env .env`), aur `.env.local` / `.env.prod` bhi (`cp .sample.env.local .env.local`, etc.).
- **`app/config.py`** jo keys maangta hai woh **exact names** se honi chahiye (`case_sensitive=True` hai).
- `DB_HOST` / `DB_PORT` ab `.env.local` / `.env.prod` mein hain (env ke hisaab se badalte hain), baaki sab shared `.env` mein.

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

**Terminal B — Celery worker (+ beat)** *(skip only if `CELERY_TASK_ALWAYS_EAGER=true`)*

```bash
cd /path/to/RailMind
source venv/bin/activate
# worker — tasks ko execute karta hai (OTP email, chart-prep, …)
celery -A app.tasks.celery_app worker -l info
```

Scheduled jobs (chart-prep har 5 min, occupancy rollup, trending) ke liye ek **aur** terminal mein **beat** bhi chalao:

```bash
cd /path/to/RailMind && source venv/bin/activate
celery -A app.tasks.celery_app beat -l info
```

*Worker nahi chalayoge toh `.delay()` wale tasks queue mein padenge (OTP email process nahi honge). **Beat** nahi chalayoge toh koi bhi periodic/cron job fire hi nahi hoga.* Poori detail (jobs list + VM) neeche **“Celery — background tasks”** section mein hai.

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
   worker → `celery -A app.tasks.celery_app worker -l info`  
   beat (scheduled jobs) → `celery -A app.tasks.celery_app beat -l info` *(separate terminal; see the “Celery — background tasks” section)*
10. **Terminal 3 — API:** `fastapi dev app/main.py` or `uvicorn app.main:app --reload`
11. **Open:** `http://127.0.0.1:8000/docs`
12. **Smoke test:** `GET /`, `GET /db-test`, try register; watch logs for `[railmind]` / Celery.

**New migration (after model changes):**  
`alembic revision --autogenerate -m "message"` → **open the file** → remove junk (e.g. fake ENUM `alter_column`, `drop_table('alembic_version')`, random index renames) → then `alembic upgrade head`.

---

## Celery — background tasks (worker + beat)

RailMind ke background kaam Celery pe chalte hain. **Do alag process hote hain — dono chahiye:**

- **worker** — tasks ko *execute* karta hai (OTP email, chart-prep, occupancy rollup…). `.delay()` / `.apply_async()` se aaye jobs yahi uthata hai.
- **beat** — *scheduler*. Cron/periodic jobs ko time pe queue mein daalta hai. **Beat ke bina koi bhi scheduled job fire nahi hoga** — chahe worker chal raha ho.

> `CELERY_TASK_ALWAYS_EAGER=true` ho toh tasks inline (synchronously) chalte hain — worker/beat dono ki zaroorat nahi, **par scheduled/cron jobs bhi nahi chalenge**. Real background behavior dekhne ke liye `false` rakho.

### Scheduled jobs (`beat_schedule` — `app/tasks/celery_app.py`)

| Job | Kab |
|-----|-----|
| `check-chart-preparation-due` | har **5 min** (`*/5`) |
| `refresh-daily-seat-occupancy` | har **10 min** |
| `cleanup-search-histories-daily` | roz **03:00 IST** |
| `compute-weekly-trending-routes` | **Sunday 23:59 IST** |

Crontabs **IST wall-clock** pe hain (`timezone="Asia/Kolkata"`) — `*/5` matlab :00, :05, :10…, beat start hone ke *theek* 5 min baad nahi. Pehli baar next 5-min boundary tak wait karna pad sakta hai.

### Local

Redis chal raha ho (`redis-server` → `redis-cli ping` = `PONG`). Phir alag terminals mein:

```bash
# worker — tasks execute
celery -A app.tasks.celery_app worker -l info

# beat — scheduler (scheduled jobs ke liye zaroori)
celery -A app.tasks.celery_app beat -l info
```

Sirf local dev ke liye dono ek hi process mein (prod mein **kabhi nahi**):

```bash
celery -A app.tasks.celery_app worker --beat -l info   # -B = embedded beat
```

**Verify:** beat log mein har 5 min pe `Scheduler: Sending due task check-chart-preparation-due …`, aur worker log mein `Task …task_check_chart_preparation_due… received / succeeded`.

### VM / prod

VM pe sab kuch **`docker-compose.prod.yml`** (project `railmind`, repo root) ke through chalta hai — worker aur beat **alag services** hain, koi manual `celery` command nahi:

| Service | Command (compose ke andar) |
|---------|-----------------------------|
| `celery_worker` | `celery -A app.tasks.celery_app worker --loglevel=info --concurrency=1` |
| `celery_beat` | `celery -A app.tasks.celery_app beat --loglevel=info --schedule=/tmp/celerybeat-schedule` |

Repo root pe (jahan `docker-compose.prod.yml` hai):

```bash
# worker + beat start / recreate
docker compose -p railmind -f docker-compose.prod.yml up -d celery_worker celery_beat

# logs
docker compose -p railmind -f docker-compose.prod.yml logs -f celery_beat
docker compose -p railmind -f docker-compose.prod.yml logs -f celery_worker

# code change / deploy ke baad restart
docker compose -p railmind -f docker-compose.prod.yml restart celery_worker celery_beat
```

> Beat ka koi health endpoint nahi hota, isliye dono services mein image ka baked-in `HEALTHCHECK` **disabled** hai — Docker mein "unhealthy" jaisa kuch na dikhe, ghabrana nahi.

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
5. Terminals: `redis-server` → `celery -A app.tasks.celery_app worker -l info` → `celery -A app.tasks.celery_app beat -l info` (scheduled jobs) → `fastapi dev app/main.py` (or `uvicorn app.main:app --reload`)

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

**Scheduled/cron job not firing (e.g. chart-prep every 5 min)**
The Celery **beat** process is not running — the worker alone only executes tasks, it does not schedule them. Start beat too: `celery -A app.tasks.celery_app beat -l info` (see the “Celery — background tasks” section). Note `*/5` fires on IST wall-clock boundaries (:00, :05, …), so the first run can be up to 5 min away.

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


# Dry run — parse only, no DB writes
python scripts/seed_train_data.py --csv data/Train_details_22122017.csv --dry-run

# Full seed / upsert
python scripts/seed_train_data.py --csv data/Train_details_22122017.csv

# Custom batch size
python scripts/seed_train_data.py --csv data/Train_details_22122017.csv --batch-size 1000



# To Check The Folder Structure 
tree -L 2 -I '__pycache__|venv'

# To Initiate Celery Worker 
celery -A app.tasks.celery_app worker --loglevel=info