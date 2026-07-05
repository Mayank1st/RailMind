# RailMind Admin Panel — Ops, AI Control & Config Console

> RailMind · Phase 3 · Admin
> Status: **Planning** · Owner: Backend

---

## 1. Purpose

Ab tak RailMind ka saara kaam **user-facing** hai — book, search, PNR, AI advisor. Par jaise-jaise features badhte hain, ek sawaal baar-baar aata hai:

> *"Peeche se kaun dekhega ki kya chal raha hai? Kaunsa email gaya, kaunsa cron chala, kaunsa model live hai, kis admin ne refund kiya?"*

Aaj ye visibility **zero** hai — sab kuch logs/DB me bikhra hai, aur koi bhi sensitive action (refund, model-toggle, seed-run) ka **koi record nahi**. Admin Panel isi gap ko bharta hai: ek **operations + AI-control + config console** jahan se team RailMind ko **dekh** aur **control** kar sake — bina DB me ghuse, bina prod pe risky script chalaye.

**Ye ek feature nahi, ek sub-product hai.** Isliye doc tier-wise phased hai — core ops pehle, AI control uske baad, entity/config aakhir me.

### Design north-star (teen non-negotiable)
1. **Har sensitive action audit-logged** — kaun, kya, kab. Accountability iske bina zero.
2. **Read alag, Action alag** — logs dekhna ek permission, refund/seed/toggle lena doosri. Galti se kuch na ho.
3. **No RCE footguns** — arbitrary script upload/run **kabhi nahi**. Sirf pre-defined, whitelisted operations (§7).

---

## 2. Kya pehle se hai (foundation — zero se nahi banega)

Admin panel ki **neenv already padi hai** — ye doc uske **upar** banata hai, dubara nahi:

| Cheez | Kahan | Status |
|-------|-------|--------|
| Role enum `GUEST / USER / AGENT / ADMIN` (+ hierarchy) | `app/domain/auth/constants/auth_user.py:93` | ✅ hai |
| RBAC deps `require_role` / `require_minimum_role` / `IsAdmin` / `IsAgent` | `app/core/permissions.py` | ✅ hai |
| `Users.role` column (indexed, default `USER`) | `app/db/models/user.py:31` | ✅ hai |
| `admin` domain + router (`prefix="/admin"`, tag `Admin`) | `app/domain/admin/admin_router/admin.py` | ⚠️ **khaali stub** — koi endpoint nahi |
| Registered in v1 router | `app/api/v1/router.py:41` | ✅ hai |
| Email delivery (SMTP via `fastapi_mail`) | `app/integrations/email.py` | ✅ hai (par **persist nahi hota** — sirf logger) |
| AI artifacts (`*.pkl` + `encoders.json` + `metrics.json`) | `app/ai/models/` (waitlist_v1, fare_advisor_v1, autofill_v2) | ✅ hai (par **koi registry/toggle nahi**) |
| Celery beat jobs (3) | `app/tasks/celery_app.py:47-64` | ✅ chalte hain (par **koi run-history nahi**) |
| `KycStatus` enum (PASSED/PENDING/FAILED) | `app/domain/auth/constants/auth_user.py` | ✅ hai (KYC queue ke liye) |
| Error code convention `RM-<DOMAIN>-NNN` | poore codebase me | ✅ hai |
| `ok()` response envelope | `app/core/response.py` | ✅ hai |

**Matlab:** RBAC + roles ka skeleton ready hai. Kaam hai (a) us skeleton pe permission-matrix banana, (b) 4 nayi **log/observability tables** add karna (audit, email, job-run, prediction/LLM), aur (c) admin endpoints ka surface bharo.

---

## 3. Scope & Non-goals

### In scope
- Read-only **observability** — audit / email / job / error / prediction / LLM logs, dashboards.
- Controlled **actions** — manual cancel/refund, AI toggles, model switch, retrain trigger, safe seeding.
- **Config** — fare rules, quota, rate-limits, notification templates, holiday calendar.
- **Entity management** — train/route/station CRUD, user management, waitlist/inventory view.
- **RBAC + audit** cross-cutting sab pe.

### Explicit Non-goals (jaan-boojh kar bahar)
- ❌ **Arbitrary script upload + run on live DB** — ye RCE hai, kabhi nahi (§7 me safe redesign).
- ❌ Direct SQL console / raw DB editor from panel — DB access alag rehta hai (SSH-tunnel, §VM memory).
- ❌ Full BI/analytics suite — Tier-5 dashboard **nice-to-have**, deep analytics baad me.
- ❌ Multi-tenant / org-level admin — abhi single RailMind instance.
- ❌ Frontend/UI is out of scope of *this* doc — ye **backend contract + data model** define karta hai; FE alag.

---

## 4. Cross-cutting foundation (feature nahi — neenv)

Ye do cheezein **har** tier pe lagti hain. Inhe pehle solid karo, warna baaki sab pe patch lagana padega.

### 4.1 RBAC — role × permission
`ROLE_HIERARCHY` already hai (`GUEST 0 < USER 1 < AGENT 2 < ADMIN 3`). Admin panel ke liye do **admin-facing** roles chahiye — inhe existing enum me hi map karo, naya parallel system mat banao:

| Panel role | Maps to | Kya kar sakta hai |
|------------|---------|-------------------|
| **Support-admin** | `AGENT` | Booking/PNR dekho + manual cancel/refund, saare **logs read-only**, user KYC queue. **Seed/model/config NAHI.** |
| **Super-admin** | `ADMIN` | Sab kuch — seeding, model-toggle, retrain, config edit, user-role assign. |

> Convention: routes pe `Depends(require_role(...))` / `IsAgent` / `IsAdmin` use karo (`app/core/permissions.py`). Read-endpoints `IsAgent`, action-endpoints `IsAdmin` (ya feature-specific). **Naya role enum add mat karo** — hierarchy kaafi hai; agar granular permission chahiye to §11 backlog me "permission flags" hai.

### 4.2 Read vs Action separation
- **Read** (`GET /admin/...`) → `IsAgent`+ — logs, lists, detail dekhna.
- **Action** (`POST/PATCH/DELETE /admin/...`) → `IsAdmin` (ya explicit `require_role`) — refund, toggle, seed, config-write.
- Har **action** endpoint mandatory: (a) audit-log likhta hai, (b) reason/confirmation field leta hai jahan applicable.

### 4.3 Audit-everything (Tier-1 #1, par foundation)
Ek `admin_audit_logs` table + ek chhota helper/decorator jo har action endpoint pe: `actor_user_id`, `action`, `target_type`, `target_id`, `before/after` (JSON), `ip`, `created_at` likhe. **Sensitive action bina audit-write commit na ho** (same txn me likho).

---

## 5. Feature tiers

Har feature ke saath: **kyun** chahiye + **existing code hook** (kahan se juda) + **naya kaam**.

### Tier 1 — Core Ops (inke bina panel adhura)

| # | Feature | Kyun | Existing hook | Naya kaam |
|---|---------|------|---------------|-----------|
| 1 | **Audit log** | Accountability ki neenv — har refund/cancel/ban/seed/toggle yahan record | — (naya) | `admin_audit_logs` table + write-helper (§4.3) |
| 2 | **Email logs** ⭐#1 | Kaunsa email gaya/failed/bounced, kis booking/user ko, retry | `app/integrations/email.py`, `app/tasks/notification_tasks.py` (abhi sirf `logger.info`) | `email_logs` table; `send_email` + notification tasks me persist (queued→sent→failed); retry endpoint |
| 3 | **Cron/Celery job logs** ⭐#2 | Har scheduled job ka trigger + status + duration + last/next-run + manual re-trigger | `app/tasks/celery_app.py` (3 beat jobs), Celery signals | `job_runs` table; hook `task_prerun`/`postrun`/`failure` signals; re-trigger endpoint (`.delay()`) |
| 4 | **Error logs (RM-\* codes)** | Har feature me `RM-...-NNN` bane hain — unhe ek jagah, filter by code/domain/severity | `app/utils/logger`, RM codes poore codebase me | structured error capture (table ya log-drain); dashboard read |
| 5 | **Booking / PNR oversight** | Rozana support ka kaam — search by PNR/user/train/date, detail, manual cancel/refund | `app/domain/booking/*`, `app/domain/pnr/*` services (reuse) | admin search + detail + action endpoints (audit-logged) |
| 6 | **Payment + refund logs** | Failed payments, stuck refunds, gateway txn IDs | `app/db/models/payment.py`, `app/db/models/refund.py`, `app/domain/payment/*` | admin list/filter + stuck-refund action |

### Tier 2 — AI Control (Phase-2 ko controllable banata hai — ye USP hai)

| # | Feature | Kyun | Existing hook | Naya kaam |
|---|---------|------|---------------|-----------|
| 7 | **AI advisor toggles (feature flags)** | Koi model kharab nikle → admin turant band kare (graceful-degradation ka **manual switch**) | AI services (`waitlist`, `fare`, `autofill`) — abhi hamesha model-available→L2 | `feature_flags` table; services flag padhein: `off` / `force_L1` / `on` |
| 8 | **Model version management** | Kaunsa version live hai, metrics dekho, naye artifact pe switch/rollback | `app/ai/models/*.{pkl,encoders.json,metrics.json}` | active-version pointer (DB/config); switch endpoint; `metrics.json` surface |
| 9 | **Retrain trigger + status** | Model manually retrain + gate-metrics (precision/recall) pass/fail dekho | `scripts/phase-2/train_*.py` (abhi manual) | trainer ko Celery task me wrap; status via `job_runs`; gate result surface |
| 10 | **Prediction logs** | Advisor ne kya predict kiya vs real outcome — monitoring **+ future retrain ka labelled data** | AI services (predictions abhi persist nahi) | `prediction_logs` table; services predict pe likhein; outcome baad me backfill |
| 11 | **Gemini/LLM usage** | API calls, 429/rate-limit hits, fallback count — free-tier credits track | `gemini_client`, `app/integrations/replicate_client.py` | `llm_usage_logs` table; client wrappers me count/log |

### Tier 3 — Data & Config

| # | Feature | Kyun | Existing hook |
|---|---------|------|---------------|
| 12 | **Manual seeding — SAFE version** ⭐#3 (redesigned) | Pre-defined seeders as buttons + dry-run + confirm; **prod blocked** | §7 (full design) — `scripts/phase-2/*`, `scripts/seed_*` |
| 13 | **Fare rules editor** | Per-class base fare, charges, Tatkal multipliers, GST | `FareRules` (`app/db/models/booking.py`), `app/core/fare_calculator.py` |
| 14 | **Quota allocation** | Per-train/class quota config | `SeatInventories` (`app/db/models/train.py`) |
| 15 | **Rate-limit config** | Search/booking/AI limits (abhi constants me hardcoded) | `RATE_LIMIT_*` constants (`auth_user.py`) → DB/Redis-backed |
| 16 | **Notification templates** | Email/SMS body edit | `app/integrations/email_templates/` (file-based → DB-backed) |
| 17 | **Holiday calendar config** | Window (lookahead/lookbehind) + festival list admin edit | `app/domain/fare/fare_service/holiday_context.py` (fare-advisor doc §02.1) |

### Tier 4 — Entity Management (standard, jab time ho)

| # | Feature | Existing hook |
|---|---------|---------------|
| 18 | **Train / route / station CRUD** | `app/domain/train/*`, `app/domain/station/*`, `app/db/models/train.py` |
| 19 | **User management** (search, deactivate, role assign, KYC queue) | `Users` (`role`, `is_active`), `KycStatus` enum |
| 20 | **Waitlist / inventory view** | `SeatInventories`, `app/db/models/waiting_list.py`, chart-prep status |

### Tier 5 — Dashboard (nice-to-have)

| # | Feature |
|---|---------|
| 21 | **Metrics overview** — bookings/day, revenue, occupancy, cancellation-rate, WL-confirmation-rate, top routes |
| 22 | **AI health widget** — har advisor ka uptime, avg latency, fallback-rate ek jagah (Tier-2 logs se aggregate) — ⏸️ **Phase-3 backlog** (§12: telemetry abhi collect hi nahi hoti) |

---

## 6. Backend endpoint surface (proposed)

Saare admin routes `admin` router (`prefix="/admin"`, already registered) ke neeche. Convention: thin router → service; `ok()` envelope; error codes `RM-ADMIN-NNN`. **Read = `IsAgent`, Action = `IsAdmin`.**

```
# ── Tier 1: Ops ──────────────────────────────────────────────
GET    /api/v1/admin/audit-logs                 IsAgent   filter: actor, action, target, date
GET    /api/v1/admin/email-logs                 IsAgent   filter: user, booking, status
POST   /api/v1/admin/email-logs/{id}/retry      IsAdmin   re-enqueue failed email
GET    /api/v1/admin/jobs                        IsAgent   list beat + event tasks, last/next-run
GET    /api/v1/admin/jobs/{name}/runs            IsAgent   run history (status/duration)
POST   /api/v1/admin/jobs/{name}/trigger         IsAdmin   manual re-trigger (audit-logged)
GET    /api/v1/admin/error-logs                  IsAgent   filter: RM-code, domain, severity
GET    /api/v1/admin/bookings                     IsAgent   search: PNR/user/train/date
POST   /api/v1/admin/bookings/{id}/cancel         IsAdmin   manual cancel (reason required)
POST   /api/v1/admin/bookings/{id}/refund         IsAdmin   manual refund
GET    /api/v1/admin/payments                     IsAgent   failed/stuck + gateway txn ids

# ── Tier 2: AI control ───────────────────────────────────────
GET    /api/v1/admin/ai/flags                     IsAgent
PATCH  /api/v1/admin/ai/flags/{advisor}           IsAdmin   off | force_L1 | on
GET    /api/v1/admin/ai/models                     IsAgent   active version + metrics
POST   /api/v1/admin/ai/models/{name}/activate     IsAdmin   switch/rollback artifact
POST   /api/v1/admin/ai/models/{name}/retrain      IsAdmin   → Celery task, gate result
GET    /api/v1/admin/ai/predictions                IsAgent   predicted vs outcome
GET    /api/v1/admin/ai/llm-usage                   IsAgent   calls / 429s / fallbacks

# ── Tier 3: Config + safe seeding ────────────────────────────
GET    /api/v1/admin/seeders                        IsAdmin   whitelisted list (§7)
POST   /api/v1/admin/seeders/{key}/dry-run          IsAdmin   preview counts, no write
POST   /api/v1/admin/seeders/{key}/run              IsAdmin   confirm → Celery, prod-blocked
PATCH  /api/v1/admin/config/fare-rules              IsAdmin
PATCH  /api/v1/admin/config/quota                    IsAdmin
PATCH  /api/v1/admin/config/rate-limits              IsAdmin
GET/PATCH /api/v1/admin/config/notification-templates IsAdmin
GET/PATCH /api/v1/admin/config/holiday-calendar       IsAdmin

# ── Tier 4: Entities ─────────────────────────────────────────
CRUD   /api/v1/admin/trains | /routes | /stations    IsAdmin
GET    /api/v1/admin/users                            IsAgent   search
PATCH  /api/v1/admin/users/{id}                       IsAdmin   deactivate / role / KYC
GET    /api/v1/admin/inventory                         IsAgent   WL depth, seats, chart status

# ── Tier 5: Dashboard ────────────────────────────────────────
GET    /api/v1/admin/metrics/overview                 IsAgent
GET    /api/v1/admin/metrics/ai-health                 IsAgent
```

> File layout (railmind-conventions §folder): `app/domain/admin/admin_router/*.py` (split by tier: `logs.py`, `ai_control.py`, `config.py`, `entities.py`), `admin_service/*.py` (service classes), `dto/*.py`, `constants/admin.py` (error codes + enums).

---

## 7. Safe-seeding design (⭐#3 — RCE ko design se maara)

**Problem:** "koi bhi script upload karo + live DB pe chalao" = remote code execution + prod data wipe ka footgun. Isliye shape hi badal diya:

### Rules (locked)
1. **No arbitrary upload.** Sirf **whitelisted, in-repo seeders** — ek registry (`constants/admin.py`) me `{key → module, human-name, param-schema}`. Registry me `scripts/phase-2/*` + top-level `scripts/seed_*` map honge.
2. **Params, not code.** Admin sirf **declared params** de (e.g. `--journeys N`, `--clean`) — ek Pydantic schema se validate. Koi free-text code path nahi.
3. **Dry-run mandatory pehle.** `POST /seeders/{key}/dry-run` → seeder ko `dry_run=True` me chala kar **kya-kya insert/delete hoga** ka count/preview de, **koi write nahi**. (Seeders me `--dry-run` already hai — e.g. `seed_fare_advisor_bookings.py`.)
4. **Explicit confirm.** `run` endpoint ko dry-run ka `token` + `confirm=true` chahiye.
5. **Celery me chale, sync nahi.** Seed heavy hai — `task_run_seeder.delay(key, params, actor)` → `job_runs` me status. Panel poll kare.
6. **Prod pe by-default BLOCKED.** `APP_ENV=production` me seeder endpoints `403` (`RM-ADMIN-SEED-001`), jab tak ek explicit env-flag (`ALLOW_PROD_SEEDING`) na ho. Seed data local/staging ka kaam hai.
7. **Audit-logged.** Har run: actor, key, params, dry/live, row-counts → `admin_audit_logs`.

```
Admin → GET /seeders (whitelist)
      → POST /seeders/{key}/dry-run (params)  → preview {will_insert, will_delete}  [NO WRITE]
      → POST /seeders/{key}/run (token+confirm) → Celery task_run_seeder → job_runs → audit
                                                   ↑ prod: 403 unless ALLOW_PROD_SEEDING
```

---

## 8. RBAC — permission matrix

`AGENT` = support-admin (read + booking actions), `ADMIN` = super-admin (sab kuch). Guest/User panel ko dekh hi nahi sakte (`IsAgent` minimum).

| Capability | GUEST/USER | AGENT (support) | ADMIN (super) |
|-----------|:----------:|:---------------:|:-------------:|
| Panel access | ❌ | ✅ | ✅ |
| Read all logs (audit/email/job/error/prediction/LLM) | ❌ | ✅ | ✅ |
| Booking search + detail | ❌ | ✅ | ✅ |
| Manual cancel / refund | ❌ | ✅¹ | ✅ |
| Email retry / job re-trigger | ❌ | ❌ | ✅ |
| AI flags / model switch / retrain | ❌ | ❌ | ✅ |
| Safe seeding (dry-run + run) | ❌ | ❌ | ✅ |
| Config (fare/quota/rate-limit/templates/holiday) | ❌ | ❌ | ✅ |
| Entity CRUD (train/route/station) | ❌ | ❌ | ✅ |
| User management (deactivate/role/KYC) | ❌ | ❌ | ✅ |
| Metrics dashboard | ❌ | ✅ | ✅ |

> ¹ Refund/cancel AGENT ko dena ek policy call hai — agar chaho to AGENT read-only + ADMIN action. Default: AGENT booking-action de sakta hai (rozana support), par **seed/model/config ADMIN-only** (destructive/systemic). Fine-grained (e.g. "refund cap") = §11 backlog "permission flags".

---

## 9. Naye data models (tables to add)

Sab `BaseModel` inherit karenge (id/is_active/created_at/updated_at/created_by — existing convention). Alembic migration ek saath.

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `admin_audit_logs` | Har admin action (§4.3) | `actor_user_id`, `action`, `target_type`, `target_id`, `before` (JSON), `after` (JSON), `ip`, `created_at` |
| `email_logs` | Email lifecycle (Tier-1 #2) | `to`, `template`, `subject`, `status` (queued/sent/failed/bounced), `user_id?`, `booking_id?`, `error?`, `sent_at?` |
| `job_runs` | Celery/beat run history (Tier-1 #3) | `job_name`, `task_id`, `status` (running/success/fail), `started_at`, `finished_at`, `duration_ms`, `error?`, `triggered_by` (beat/manual/event) |
| `prediction_logs` | AI predict vs outcome (Tier-2 #10) | `advisor` (waitlist/fare/autofill), `model_version`, `input` (JSON), `prediction` (JSON), `outcome?` (JSON, backfill), `created_at` |
| `llm_usage_logs` | Gemini/Replicate calls (Tier-2 #11) | `provider`, `model`, `endpoint`, `status`, `is_fallback`, `is_rate_limited`, `latency_ms`, `created_at` |
| `feature_flags` | AI advisor toggles (Tier-2 #7) | `key` (e.g. `advisor.waitlist`), `value` (off/force_L1/on), `updated_by`, `updated_at` |
| `model_registry` (ya config row) | Active model pointer (Tier-2 #8) | `advisor`, `active_version`, `activated_by`, `activated_at` |

> **Error logs (#4) aur rate-limit/config (#15):** naya table optional. Errors already `logger` + `RM-*` codes se aate hain — v1 me log-query (ya ek `error_logs` table) se surface; config values ek generic `admin_config` key-value table me reh sakte hain (rate-limits, holiday-window, quota-overrides). Isse har config-item ke liye alag table nahi banana padta.

---

## 10. Phasing (incremental ship — user-priority order)

> User priority: **email logs #1, cron/job logs #2, safe seeding #3.** Aur Tier-1 + Tier-2 pehle.

1. **P0 — Foundation** (§4): RBAC permission-matrix wire (`IsAgent`/`IsAdmin` deps ready hain), `admin_audit_logs` table + write-helper, admin router split-by-tier scaffold.
2. **P1 — Ops logs** (Tier-1 #2, #3, #1): `email_logs` + persist hook ⭐, `job_runs` + Celery signal hook ⭐, audit-log read endpoint. → **user ke top-2 yahin ship ho jaate hain.**
3. **P2 — Ops actions** (Tier-1 #5, #6, #4): booking/PNR oversight + manual cancel/refund, payment/refund logs, error-log surface.
4. **P3 — AI control** (Tier-2 #7, #8, #10): feature flags + services me padhna, model-version pointer, prediction logs. (#9 retrain, #11 LLM-usage next.)
5. **P4 — Safe seeding** (§7, Tier-3 #12) ⭐: whitelist registry + dry-run + confirm + prod-block.
6. **P5 — Config** (Tier-3 #13-17): fare-rules, quota, rate-limits, templates, holiday.
7. **P6 — Entities** (Tier-4) → **P7 — Dashboard** (Tier-5).

**Recommendation:** P0 → P1 pehle standalone ship karo (2 logs = user ka #1 aur #2, tumhare kaam se seedha juda). Fir P3 (AI control — Phase-2 USP). Baaki jab bandwidth ho.

---

## 11. Backlog / open questions

| Item | Priority | Notes |
|------|----------|-------|
| **Fine-grained permission flags** | Medium | Role-hierarchy kaafi hai v1 ko; agar "refund-cap" / "read-only-agent" jaisa chahiye to per-capability flags (RBAC v2) |
| **Error-log storage** | Medium | Table vs log-drain (Loki/CloudWatch) — abhi `logger`; volume dekhkar decide |
| **Prediction outcome backfill job** | Medium | `prediction_logs.outcome` ko real result se bharne wali Celery beat job (retrain data quality) |
| **Config hot-reload** | Low | Rate-limit/fare-rule DB edit → cache-invalidate/reload bina restart |
| **2FA for super-admin** | Medium | Sensitive actions (seed/refund) pe step-up auth |
| **Admin action rate-limit / anomaly alert** | Low | Bulk-refund / mass-toggle pe alert |
| **Notification templates → DB** | Low | Abhi file-based (`email_templates/`); DB-backed editable v2 |
| **SMS logs** | Low | `email_logs` ka SMS analog jab SMS provider aaye |

---

## 12. Deferred — AI Health page (`GET /admin/metrics/ai-health`) → Phase-3

> **Decision (2026-07-06):** FE mock ready hai (3 advisor cards: uptime / latency / fallback-rate + 7-bar sparkline + "Recent advisor events" feed), par ise **abhi nahi banayenge** — Phase-3 backlog. Reason: Overview ki tarah ye real business tables se aggregate **nahi** ho sakta; jo telemetry chahiye woh RailMind **collect hi nahi karta**. Contract-first stub bhi tab tak jhoothe zeros dega, isliye pehle instrumentation, fir page.

### Kya already hai (Phase-3 me reuse hoga — zero se nahi)
- **Model versions** (real): `MODEL_VERSION` const per pipeline — `waitlist-predictor-v1`, `fare-advisor-v1`, `autofill-class-v2` (`app/ai/pipelines/*_features.py`). → card ka version badge.
- **Gate + metrics** (real): `app/ai/models/*.metrics.json` — `gate: PASS`, precision/recall/accuracy. → model-health signal.
- **Graceful-degradation logic** (real, per advisor): teeno services me L2-model → L1-rules fallback already coded — `_degraded_result` (`waitlist_prediction_service.py`), "No live signals → degrade to the rules fallback" (`fare_advisor_model_service.py`), autofill class. → live/degraded status ka **source of truth** yahin se derive hoga (naya flag banane se pehle).

### Kya missing hai (Phase-3 me banega — mock ke har number ka gap)
| Mock field | Aaj data-source | Phase-3 kaam |
|-----------|-----------------|--------------|
| Uptime % | ❌ koi uptime tracking nahi | Health-probe / success-ratio over window |
| Avg/p95 latency (82/110/46 ms) | ❌ koi latency instrumentation nahi | Har predict call pe `latency_ms` record |
| Fallback rate (2.1/5.8/12.4%) | ❌ per-call fallback counter nahi | `is_fallback` flag record per call |
| 7-bar sparkline | ❌ koi time-series telemetry nahi | Bucketed aggregate (Overview jaise) |
| Recent advisor events feed | ❌ `job_runs`/events table nahi | `advisor_events` (ya `job_runs` reuse) |

### Phase-3 build order (P3 ke andar, plan §10 se aligned)
1. `prediction_logs` table (§9): `advisor`, `model_version`, `latency_ms`, `is_fallback`, `created_at`, `outcome?`.
2. `advisor_events` log (ya `job_runs` reuse): model-reload / batch-scored / health-check-failed / fallback-engaged — status warn/success/failed, `RM-AI-*` codes.
3. Instrument teeno AI services (waitlist / fare / autofill) — har call pe latency + `is_fallback` + version likho (existing degrade branches me hook).
4. Health probe (uptime + degraded detect) — SLO breach pe event emit.
5. `AdminAiHealthService` + `GET /admin/metrics/ai-health` — Overview jaisa Redis-cached + bucketed aggregate; DTO mock se 1:1.

**Router aaj:** `admin_ai_control.py` bare stub hai (sirf `prefix="/ai"`) — Phase-3 tak waise hi rahega.

---

### TL;DR
- **Neenv 40% ready** hai (role enum + RBAC deps + empty admin router). Zero se nahi banega.
- **Do cross-cutting** (RBAC matrix + audit-everything) pehle → fir tiers.
- **User ke top-3** (email-logs, job-logs, safe-seeding) P1 aur P4 me — inhe standalone ship kar sakte ho.
- **Safe-seeding** = whitelist + params + dry-run + confirm + prod-block; **kabhi arbitrary script upload nahi.**
- Poora panel ek **sub-product** hai — Tier 1+2 se shuru, baaki phase.
