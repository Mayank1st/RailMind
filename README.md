# RailMind

AI-Powered Railway Reservation System — IRCTC Replica with Intelligent Automation

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

## Project Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-org/railmind.git
cd railmind
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install celery[redis]   # Redis transport for Celery
```

### 4. Set up environment variables

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

Open `.env` and configure:

```env
# Application
APP_NAME=RailMind
ENVIRONMENT=development
DEBUG=True

# Database
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/railmind_db

# Redis (must start with redis://)
REDIS_URL=redis://127.0.0.1:6379/0

# Auth
JWT_SECRET_KEY=your-secret-key-here
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Email (Gmail SMTP)
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_USER=yourgmail@gmail.com
EMAIL_SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # Gmail App Password (not your login password)

# Celery
CELERY_TASK_ALWAYS_EAGER=False   # Set True only for testing (bypasses Redis)

# AI (Phase 2+)
OPENAI_API_KEY=
HUGGINGFACE_API_KEY=

# Payment (Phase 1)
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
```

> **Gmail App Password:** Go to [myaccount.google.com](https://myaccount.google.com) → Security → 2-Step Verification → App Passwords → Generate one for "Mail".

---

## Running the Project

You need **3 separate terminals** running simultaneously.

### Terminal 1 — Start Redis

```bash
redis-server
```

Verify Redis is running:

```bash
redis-cli ping
# Expected output: PONG
```

### Terminal 2 — Start Celery Worker

```bash
celery -A app.tasks.celery_app:celery_app worker --loglevel=info
```

When Celery starts correctly, you will see your registered tasks listed:

```
[tasks]
  . task_send_otp_email
  . task_send_booking_confirmation
  . task_process_refund

[2026-04-04 ...] celery@your-machine ready.
```

> The Celery worker **must be running** for background tasks like OTP emails to be processed. Tasks are queued into Redis by FastAPI and consumed by this worker.

### Terminal 3 — Start FastAPI

```bash
uvicorn app.main:app --reload
```

The API will be available at:

```
http://localhost:8000
API Docs: http://localhost:8000/docs
Redoc:    http://localhost:8000/redoc
```

---

## Database Migrations

Run Alembic migrations to set up the database schema:

```bash
# Run all pending migrations
alembic upgrade head

# Create a new migration (after model changes)
alembic revision --autogenerate -m "describe your change"

# Rollback one migration
alembic downgrade -1
```

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