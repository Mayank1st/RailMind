# RailMind — Tests Guide

Is folder me do tarah ke tests hain:

- **Unit tests** — koi DB/network nahi, milliseconds me chalte hain (jaise `test_fare_calculator.py`).
- **Integration tests** — asli (alag) Postgres test DB pe poora flow chalate hain: HTTP request → router → service → DB → response (jaise `test_integration_smoke.py`, `test_booking_integration.py`).

---

## 1. Pehli baar setup (kuch karne ki zaroorat nahi)

Integration tests **khud** apna test database bana lete hain. Pehli `pytest` run pe:

1. Local Postgres pe `railmind_test` database ban jaata hai (agar nahi hai to) — dev `railmind_db` ko **haath nahi lagता**.
2. Saari Alembic migrations us pe chal jaati hain (`alembic upgrade head`) — yानी schema bilkul prod jaisa.

Sirf yeh chahiye:
- Local Postgres chal raha ho (`pg_isready`).
- `.env` / `.env.local` me sahi `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SCHEMA` ho.
- venv activated ho:
  ```bash
  source venv/bin/activate
  ```

---

## 2. Tests kaise chalayein

```bash
# Poora suite (chhota output)
python -m pytest -q

# Poora suite (har test ka naam + PASS/FAIL)
python -m pytest -v

# Sirf ek file
python -m pytest tests/test_integration_smoke.py -v

# Sirf unit tests (fast, no DB)
python -m pytest tests/test_fare_calculator.py -v

# Sirf ek test (file::test_name)
python -m pytest tests/test_booking_integration.py::test_list_bookings_empty_for_new_user -v
```

### Kaam ke flags

| Flag | Kya karta hai |
|------|---------------|
| `-v` | Har test ka naam + PASS/FAIL |
| `-q` | Chhota/quiet output |
| `-s` | Tumhare `print()` bhi dikhao (warna pytest chupa deta hai) |
| `-k "db"` | Sirf woh tests jinke naam me "db" hai |
| `--lf` | "Last failed" — sirf woh tests jo pichli baar fail hue |
| `-x` | Pehle fail pe ruk jao |

---

## 3. Coverage report — "kitna code test ho chuka hai"

`pytest-cov` pehle se installed hai. Yeh batata hai kaun si line test hui, kaun si chhooti.

```bash
# Terminal me — Missing column me untested line numbers dikhte hain
python -m pytest --cov=app --cov-report=term-missing -q

# Sirf ek module par focus
python -m pytest tests/test_fare_calculator.py \
  --cov=app.core.fare_calculator --cov-report=term-missing -q

# HTML report — browser me clickable, line-by-line (hari = tested, laal = untested)
python -m pytest --cov=app --cov-report=html
open htmlcov/index.html      # mac
```

Padhne ka tarika: `Cover` = % tested, `Missing` = abhi tak untested line numbers (= "yahaan test likhna baaki hai" ki to-do list).

> Note: `htmlcov/` generated output hai — ise `.gitignore` me rakho, commit mat karo.

---

## 4. Swagger `/docs` (yeh testing doc NAHI hai)

App chalne pe `http://localhost:8000/docs` pe FastAPI ki **interactive API documentation** milti hai — endpoints haath se try karne ke liye. Yeh manual testing me kaam aati hai, par automated `pytest` se alag cheez hai. Confuse mat hona.

---

## 5. Harness kaise kaam karta hai (`conftest.py`)

Saara wiring `tests/conftest.py` me hai. Sabse zaroori fixtures:

| Fixture | Kya deta hai |
|---------|--------------|
| `db_session` | Ek session jo outer transaction me chalta hai aur test ke baad **hamesha rollback** ho jaata hai — har test clean DB se shuru, kuch bhi likha survive nahi karta. (savepoint recipe) |
| `client` | httpx async client, seedha ASGI app se juda (no socket). `get_db` isi `db_session` (rolled-back) ko point karta hai. Auth-free / public routes ke liye. |
| `auth_client` | `client` jaisa hi, par `get_current_user` bhi fake — bina asli JWT/Redis ke logged-in user simulate karta hai. Protected endpoints ke liye. |
| `_test_db` | Session me ek baar test DB bana ke migrate karta hai. Sirf DB-waale tests is par depend karte hain, isliye unit tests DB-free aur fast rehte hain. |
| `booking_world` | WL booking ke liye seed (inventory me 0 confirmed seats). POST references ka dict return. |
| `available_world` | AVAILABLE booking ke liye seed (1 coach + 2 seats, inventory 2 confirmed). `inventory_id` bhi return karta hai. |
| `single_seat_world` | Exactly 1 confirmed seat — sequential oversell guard test ke liye. |
| `racing_client` | get_db har request ko apni alag **committing** session deta hai (production jaisa) — true concurrency test ke liye. |
| `concurrency_world` | `single_seat_world` jaisa par **committed** (alag connections dekh sakein); teardown pe `TRUNCATE` se cleanup. |
| `_reset_singleton_caches` | Autouse — `CommonService` ke module-level FareRules/Stations cache ko har test ke aas-paas reset karta hai (warna test ke beech leak). |

### Test likhne ka pattern

```python
# Public / no-auth endpoint
async def test_home(client):
    resp = await client.get("/")
    assert resp.status_code == 200

# Protected endpoint
async def test_my_bookings(auth_client):
    resp = await auth_client.get("/api/v1/bookings/")
    assert resp.status_code == 200
```

Async tests bina `@pytest.mark.asyncio` ke chalte hain kyunki `pytest.ini` me `asyncio_mode = auto` set hai.

---

## 6. Gotchas (jo humne jhel liye)

- **`RuntimeError: ... attached to a different loop`** — test engine ko `poolclass=NullPool` ke saath banao. pytest-asyncio har test ko naya event loop deta hai; pooled asyncpg connection purane loop se chipki reh jaati hai. (`conftest.py` me already fix hai.) Symptom: test akele pass, poore suite me fail.
- **SQLite mat use karo** — booking flow Postgres-only features pe khada hai (`railmind_be` schema, `SELECT FOR UPDATE`, partial unique indexes). SQLite inhe chup-chaap ignore kar deta hai → test green dikhega par jhoot bolega. Isliye asli Postgres test DB.
- **Tables `create_all` se nahi, Alembic se** — taaki raw `op.execute()` waale custom index/constraint (double-booking guard) bhi test DB me aayein.

---

## 7. Test DB manually check karna

```bash
# railmind_test me tables aur alembic head dekho
DB_NAME=railmind_test python -m alembic current

# psql se andar jhaanko
psql -h localhost -U <DB_USERNAME> -d railmind_test -c '\dt railmind_be.*'
```

---

## 8. Roadmap (kahaan tak pahunche)

- [x] 3a — client harness + public `GET /`
- [x] 3b — test DB + migrations + `get_db` override + `GET /db-test`
- [x] 3c — auth override + read-only `GET /api/v1/bookings/`
- [x] 3d-1 — per-test rollback isolation (savepoint recipe), proved in `test_db_isolation.py`
- [x] 3d-2a — POST `/api/v1/bookings/` failure path (unknown train → 404, zero seed) — proves write endpoint reachable + authed
- [x] 3d-2b — happy-path **WL** booking (`booking_world` fixture seeds 7 tables; inventory has 0 confirmed/RAC seats → availability WL → no coaches/seats needed)
- [x] 3d-2c — **AVAILABLE** booking (seat allotted CNF + inventory decremented) and sequential **oversell guard** (last seat → 2nd booking falls to WL)
- [x] 3d-2d — **concurrency** guard: two requests race for the last seat (`asyncio.gather`), one CNF + one WL, no oversell. Uses `racing_client` + `concurrency_world` (real committing sessions + truncate cleanup). Note: proves correct concurrent *outcome*; forcing the lock to *always* contend would need a mid-transaction barrier (out of scope).
