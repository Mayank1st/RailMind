# AI Fare Predictor — "Book Now vs Wait" Advisor

> RailMind · Phase 2 · Feature 02
> Status: **Planning** · Owner: Backend

---

## 1. Purpose

Har yatri ticket book karte waqt ek hi confusion mein phasta hai:

> *"Abhi book karun ya kuch din ruk jaun? Kahin seat na nikal jaaye… ya bekaar mein jaldbaazi to nahi?"*

Aaj IRCTC sirf batata hai **abhi kitni seat hai** — yeh nahi batata ki **aage kya hoga**. RailMind ka AI Fare Predictor isi gap ko bharta hai. Yeh ek experienced dost ki tarah saaf salah deta hai:

- 🔴 **BOOK_NOW / URGENT** — "abhi book kar lo, seat tezi se ja rahi hai, baad mein Tatkal ka extra lagega"
- 🟢 **CAN_WAIT** — "aaram se, abhi rush nahi, last-minute bhi mil jaayegi"

…aur sirf decision nahi, uska **reason** bhi bataata hai taaki user ko bharosa ho.

**Base fare deterministic hai** (`app/core/fare_calculator.py` IRCA tables se exact compute karta hai). Isliye is feature ka asli ML value **fare ko dobara calculate karna nahi**, balki yeh predict karna hai ki **wait karne par availability/effective-fare bigdega ya nahi** — yaani sahi booking-time ki salah.

---

## 2. Kaise kaam karega — 3-layer hybrid architecture

Decision ek hi service ke andar 3 layers se banta hai (autofill feature ka proven pattern mirror karta hai):

| Layer | Kaam | Soch |
|-------|------|------|
| **L1 — Rules** | Threshold-based decision (fill-rate, days-to-journey, velocity, waitlist) | Human-written rulebook; cold-start + fallback |
| **L2 — XGBoost** | History se seekha hua probability `P(wait → worse outcome)` | Machine 40k booking-curves se khud seekhti hai |
| **L3 — Gemini** | Decision ko insaani, samjhaane-wali salah mein badalna | LLM sirf *explanation* deta hai, decision nahi |

**Routing:** model **global/per-journey** hai (per-user nahi) — isliye autofill jaisa *per-user booking-count threshold yahaan NAHI lagta*. Trigger sirf: **model artifact available + journey ka inventory mil raha → L2**; warna **L1** (cold-start / fallback); model missing/fail → auto **L1**. Endpoint kabhi nahi girta.

**Layer responsibilities:**
- **L1/L2 = dimaag** — actual faisla (deterministic, reliable math)
- **L3 Gemini = zubaan** — sirf presentation; fail ho to templated reason fallback

### Request lifecycle
```
Frontend → Router (thin: auth + delegate) → Service (decision logic)
        → DB reads (SeatInventories, Bookings) → DTO (contract) → ok() envelope → Frontend
```

---

## 3. Backend endpoints

Saare AI routes `/api/v1/ai/` ke neeche aate hain (convention §3). Yeh feature `app/ai/pipelines/fare_predictor.py` mein rehta hai (abhi woh ek galat NLP copy-paste hai → rewrite hoga), aur `app/ai/router.py` mein register hota hai.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/api/v1/ai/fare/advisor` | Required (`get_current_user`) | Ek journey ke liye **BOOK_NOW / CAN_WAIT / URGENT** decision + confidence + reason + signals |

### Query params
| Param | Type | Required | Notes |
|-------|------|----------|-------|
| `train_number` | `str` | ✅ | jaise `"12951"` |
| `source_station_code` | `str` | ✅ | jaise `"BCT"` |
| `destination_station_code` | `str` | ✅ | jaise `"NDLS"` |
| `train_class` | `str` | ✅ | `SL / 3A / 2A / 1A / CC / 2S` |
| `quota` | `str` | ➖ | default `GN` |
| `journey_date` | `date` | ✅ | jaise `2026-07-15` |

### Response shape (`FareAdvisorResponseDTO`)
```jsonc
{
  "success": true,
  "message": "Fare advice generated successfully.",
  "data": {
    "decision": "BOOK_NOW",          // BOOK_NOW | CAN_WAIT | URGENT
    "confidence": 0.82,              // 0.0–1.0 — kitna sure
    "reason": "Abhi book kar lo — is route pe seat tezi se ja rahi hai (78% full), festival rush bhi hai. Ruke to Tatkal ~₹340 extra.",
    "signals": {                     // transparency — kis aadhar pe
      "fill_rate": 0.78,
      "days_to_journey": 5,
      "booking_velocity": "HIGH",
      "waitlist_pressure": 0.0
    },
    "source": "RULES"               // RULES | MODEL
  },
  "meta": { "confidence_threshold": 0.75 }
}
```

**Graceful degradation:** har risky step `try/except`, error code `RM-FARE-ADV-001` se log; endpoint hamesha `200` (autofill principle — advisor booking flow ko block na kare).

### L1 decision rule (rules path)
URGENT **availability-rule** pehle (§8.6 mein L2 ke saath shared), phir fill-rate + velocity se BOOK_NOW/CAN_WAIT (safe-biased). Thresholds: `constants/fare_advisor.py`.
```
URGENT    : seats gone (available<=0) OR wl_count>0 OR fill_rate >= URGENT_FILL_RATE (0.90)
BOOK_NOW  : fill_rate >= BOOK_NOW_FILL_RATE (0.70)
            OR (velocity HIGH AND days_to_journey <= NEAR_JOURNEY_DAYS (3))
CAN_WAIT  : fill_rate < CAN_WAIT_FILL_RATE (0.40) AND days_to_journey > FAR_JOURNEY_DAYS (10)
unclear   : BOOK_NOW @ CONFIDENCE_LOW (safe-bias — galat CAN_WAIT mehnga)
```

### L1 confidence (rules path)
L2 mein confidence = `P`. L1 mein hardcoded nahi — **threshold se doori** se banta hai: jis fill-rate threshold ne decision trigger kiya, value usse jitni door (decisive), confidence utni high; threshold ke bilkul paas (borderline) → `CONFIDENCE_LOW`. Indirect signal (velocity + proximity) → fixed `CONFIDENCE_MEDIUM`. Already-WL / seats=0 → `CONFIDENCE_HIGH` (certain). Formula: `LOW + min(|value − threshold| / SPAN, 1) × (HIGH − LOW)`.

---

## 4. Models / data used

**Naya DB table nahi banega (L1 + L2-v1)** — saare signals existing tables se **read-only** aate hain. (L2-v2 mein daily snapshot table aa sakta hai — §8.8.)

### SQLAlchemy models (read-only)
| Model | File | Yahan se kya |
|-------|------|--------------|
| `SeatInventories` | `app/db/models/train.py:197` | `available_confirmed_seats`, `total_confirmed_seats` → **fill rate**; `wl_count`, `wl_max` → **waitlist pressure** |
| `Bookings` | `app/db/models/booking.py:24` | `booked_at` vs `journey_date` → **booking velocity / lead-time curve** (L2 labels ka source) |
| `Trains` / `TrainStations` | `app/db/models/train.py` | `train_type` (Rajdhani/Shatabdi surge), `distance_km` → distance bucket |
| `FareRules` + `FareCalculator` | `app/db/models/booking.py:305`, `app/core/fare_calculator.py` | GN vs Tatkal/PT ka **fare delta** (reason mein "₹X extra") |
| `SearchHistories` | `app/db/models/search_histories.py` | route demand signal (per-user-route deduped — secondary) |

### ML artifacts (L2 — phase mein aayega, autofill pattern)
| File | Purpose |
|------|---------|
| `app/ai/pipelines/fare_advisor_features.py` | train/serve **shared** feature engineering (no skew) |
| `app/ai/pipelines/fare_predictor.py` | lazy-singleton inference (`is_available()` + `predict()`) |
| `scripts/phase-2/train_fare_advisor.py` | offline trainer + metrics + baseline gate |
| `app/ai/models/fare_advisor_v1.{pkl,encoders.json,metrics.json}` | versioned artifact (git/GCS) |

### New BE files (L1 first)
```
app/domain/fare/
├── fare_service/fare_advisor_rules_service.py   # L1 logic
├── fare_service/fare_advisor_model_service.py   # L2 (later)
├── dto/fare_advisor_dto.py                       # request/response contract
└── constants/fare_advisor.py                     # thresholds, enums, error codes
app/ai/pipelines/fare_predictor.py               # thin router (rewrite)
```

---

## 5. Yeh feature humare project ke liye innovation kyun hai

1. **IRCTC se aage ka kaam** — IRCTC sirf current availability dikhata hai. Hum *future* predict karke **actionable salah** dete hain — "book now vs wait" — jo koi mainstream rail app reliably nahi deta.
2. **Deterministic core + LLM polish** — asli faisla math (L1/L2) se aata hai (reliable, consistent), aur Gemini usse **insaani salah** banata hai. Reliability aur "wow" dono — best of both.
3. **Existing infra ka smart reuse** — naya stack nahi: XGBoost + Celery + versioned artifacts (autofill se proven), Gemini (NLP search se), Postgres signals. Innovation **architecture** mein hai, na ki bolt-on tooling mein.
4. **Booking-curve learning** — 40k bookings ke `booked_at` se journey ki demand-curve reconstruct karke "wait karna kab mehnga pada" seekhna — ek non-trivial, data-driven idea jo same data ko naye tareeke se istemal karta hai.
5. **Hybrid graceful design** — cold-start, missing model, ya LLM failure — har case mein feature safe-degrade hota hai. Production-grade soch, demo-grade nahi.

---

## 6. End user ko kya faayda

| Faayda | Kaise |
|--------|-------|
| 💸 **Paisa bachta hai** | Time pe alert → Tatkal/Premium-Tatkal ka surge charge bach jaata hai |
| 😌 **Tension khatam** | "Book karun ya na karun" wala guesswork khatam — decision saaf |
| 🎯 **Seat miss nahi hoti** | Khatam hone se pehle warning → confirmed seat |
| ⏱️ **Time bachta hai** | Baar-baar availability check karne ki zaroorat nahi |
| 🤝 **Bharosa** | Sirf decision nahi, *reason* bhi — user samajh ke decide karta hai |

**Example:** Riya ko Diwali pe 10 din baad ki train chahiye. Bina feature: 3 din baad dekhti hai → seat khatam, WL 45, ya Tatkal ₹400 extra. Feature ke saath: pehle din hi *"🔴 Festival rush, abhi book kar lo, seat tezi se ja rahi hai"* → confirmed seat, normal price, zero tension.

---

## 7. Phasing (autofill jaisa incremental ship)

1. **L1 — Rules advisor** ✅ pehla deliverable — working endpoint, conventions, cold-start + fallback foundation
2. **L2 — XGBoost** — booking-curve labels + shared features + versioned artifact + Celery retrain
3. **L3 — Gemini reason** — decision → natural-language nudge (templated fallback ke saath)

### Known risk (L2 se pehle)
Seeded data ka `lead_days → status` relation thoda synthetic hai. L2 se pehle seeder ki **booking-curve realism verify/enrich** karni hogi — warna model baseline beat nahi karega (autofill P18 jaisa data-artifact sabak). Real daily snapshots (§8.8) is risk ko jad se khatam karte hain.

### ✅ Verification — local DB (2026-06-27): L1 code OK, seed data L2 ke liye insufficient
End-to-end `advise()` real local Postgres pe verified — DB path, signal math, DTO, URGENT availability-rule, no-inventory fallback sab **kaam karte hain**. Par seed data quality (measured):

| Check | Result | Impact |
|-------|--------|--------|
| Inventory touched (`available < total`) | **9 / 16,250,778** (0.000%) | L1 `fill_rate` signal **inert** — decisions safe-bias default pe gir jaate hain |
| `fill_rate ≥ 0.70` rows | **0** | BOOK_NOW/URGENT fill-branch kabhi fire nahi hota |
| Bookings per journey | **~1.06** (20,015 / 18,892 distinct) | **booking-curve hai hi nahi** → §8.1 reconstruction impossible |
| Contested journeys (≥1 `WAITLISTED`) | **623 (3.3%)**, ~1 WL each | L2 positive labels sparse + single-point |

**Root cause:** `seed_autofill_bookings.py` autofill ke liye bana (per-user class preference, ~1 booking/journey); bookings ne `SeatInventories` decrement bhi nahi kiya.

### ✅ L2 v1 trained (`scripts/phase-2/train_fare_advisor.py`, 2026-06-27)
Shared features `app/ai/pipelines/fare_advisor_features.py` (train/serve parity) + trainer → `app/ai/models/fare_advisor_v1.{pkl,encoders.json,metrics.json}`. **Test (journey-split, threshold 0.30):** sellout **recall 0.984** (548 me se 9 missed — asymmetric-cost goal: false-CAN_WAIT minimized), precision 0.651, false-BOOK_NOW 0.349 (<0.6 guardrail), accuracy 0.927, scale_pos_weight 6.33, gate **PASS**. Feature importance multi-feature (quota 0.32, fill_rate 0.24, wl 0.12, days/velocity ~0.09, festival/month/type modest) — koi single-feature tautology nahi. **Caveat:** metrics synthetic data pe (signal construction se clean) — real data pe kam honge; pipeline (leakage-free as-of-d, journey-split, asymmetric-cost) sound.

### ✅ L2 serving wired (2026-06-27)
`app/ai/pipelines/fare_advisor_model.py` (lazy singleton) + `app/domain/fare/fare_service/fare_advisor_model_service.py` (live as-of-now features + §8.6 URGENT-rule-then-P) + router (`fare_predictor.py`) routes **model available → L2, else L1**; no-inventory → rules fallback; error → safe default. Rules service refactored to share `gather_signals` / `is_urgent` / `build_result` / `build_reason` (no duplication). Verified on real DB: model loads, routes, URGENT identical in both layers, DTO holds; model gives correct high P on reconstructed positives (TQ & GN), low on negatives — **not a bug.**

**Tuning observation (v2):** positive rows mostly have fill 0.88–1.0, so URGENT (fill≥0.90) fires first and the model-BOOK_NOW band is a thin sliver (fill ~0.77–0.89); with W=5 the window is also narrow. Decisions are correct (about-to-sellout → book, else wait) but the model's incremental value over the URGENT rule is modest on this synthetic data. Knobs: `URGENT_FILL_RATE`, `BOOK_NOW_HORIZON_DAYS`. Real data (with earlier, noisier demand build-up) will widen the model's useful range.

**Fix applied (high-fill floor, from API testing):** Postman testing surfaced a risky output — a 2A/GN journey at **89% fill (5 seats left)** returned CAN_WAIT @0.91, because the model read slow recent demand (P=0.095). That's the false-CAN_WAIT risk (§8.3) realized, plus a sharp cliff at 0.90 (0.89→wait vs 0.90→urgent). Fix: `BOOK_NOW_FLOOR_FILL_RATE=0.85` — on the model path, `fill≥0.85` clamps a model CAN_WAIT up to BOOK_NOW (fill-based confidence), so a near-full journey never says “wait” (L1 already did this via its 0.70 rule). Verified: 89% case → BOOK_NOW @0.88; no CAN_WAIT with fill≥0.85 remains; sub-0.85 model decisions unchanged.

### ✅ Resolved — demand-curve seeder (`scripts/phase-2/seed_fare_advisor_bookings.py`)
Purpose-built seeder banaya: per-journey demand curves (load = observable features se → P18 trap nahi), arrival-order se confirmed→WL (`sellout_lead` emerge), `SeatInventories` depletion, future journeys `now` pe truncated. **Result (2,500 journeys):** 2,429 realized · **888 contested (36.6%)** vs pehle 3.3% · 145,623 bookings (~60/journey) · `sellout_lead` spread 0→19d (med 3) · ~21,861 L2 training rows. L1 ab real data pe full spread deta hai (URGENT/BOOK_NOW/CAN_WAIT), L2 trainable hai. Run: `APP_ENV=local ./venv/bin/python scripts/phase-2/seed_fare_advisor_bookings.py` (`--clean` / `--journeys N` / `--dry-run`).

---

### ✅ L3 Gemini reason wired (2026-06-27)
`app/domain/fare/fare_service/fare_advisor_reason_service.py` + router `explain` param (default true). Decision + signals **BE se** Gemini ko jaate hain with strict system-instruction (§8.7: only given numbers, no invented fares/facts, don't contradict, ≤28 words); reuses `gemini_client`. **Verified:** live nudges on-message ("Seats 95% full, demand HIGH, 3 days left… book now!" / Hinglish "Abhi wait karna theek hai, 22% seats…"); Gemini 503/error → falls back to templated reason (the deterministic one already on the payload) — endpoint never blocks. **Pending enhancement:** ₹-delta (GN-vs-Tatkal via FareCalculator) abhi pass nahi hota — reason qualitative hai; fare-delta wiring backlog (§9).

### ✅ #02.1 Holiday-aware reason (shipped, reason-only)
`app/domain/fare/fare_service/holiday_context.py` (pure, offline `holidays` pkg, lazy import → None on any failure). `get_nearby_holiday(journey_date)` — asymmetric window (lookahead 7, lookbehind 2; festival se pehle travel), closest-first. Adds `signals.nearby_holiday` (festival name | null) + appends a holiday clause to the reason (BOOK_NOW/URGENT → "book in time"; CAN_WAIT → soft "still room"). **Decision/model UNCHANGED** — `is_festival_season` model feature already makes the decision season-aware; this is display-only (no double-count). Threaded through L1 + L2 (single + batch) via `build_result`/`build_reason`; L3 Gemini gets the BE-computed name with a "use this exact name, don't invent" guard; templated fallback is also holiday-aware. Verified: decision identical with/without holiday; Diwali detected at ±window; far/out-of-window → null. `HOLIDAY_LOOKAHEAD_DAYS`/`HOLIDAY_LOOKBEHIND_DAYS` in constants. **Backlog:** state-specific festivals (`holidays.India(subdiv=...)` via `stations.state`); long-weekend label.

## 8. ML Design — Label & Cost (L2)

> Yeh feature ka 80% ML difficulty hai. Autofill se alag — wahaan label row mein already tha (user ne jo class chuni); yahaan label **exist hi nahi karta**, history se construct karna padta hai.

### 8.1 Label construction (the core)

**"Wait" ki definition (locked): "thodi der baad dobara dekho" (check-again-later)**, "aakhir tak ruko" nahi. Advisor baar-baar query hota hai — `CAN_WAIT` = "abhi safe, sellout paas aate hi BOOK_NOW pe flip". Isse cry-wolf nahi hota (§8.3.4 guardrail ke saath consistent).

Hum counterfactual ("agar wait karta to kya hota") observe nahi karte — bas dekhte hain ki **journey ne decision-moment ke baad kitni jaldi sellout/WL chhua.** Yeh `Bookings.booking_status` + `booked_at` mein already chhupa hai. **Inequality ke bajaaye horizon-window `W` (BOOK_NOW_HORIZON_DAYS) se operationally define karte hain** — single inequality flip-prone hai, margin+horizon nahi.

```
lead = journey_date − booked_at            # bada lead = pehle; chhota lead = journey ke paas
sellout_lead(J) = max(lead) over J ki WAITLISTED bookings   # sellout onset; None agar kabhi WL nahi
margin(d)       = d − sellout_lead(J)       # decision kitne din sellout se PEHLE hai

For each decision-snapshot lead d ∈ {1,2,3,5,7,10,15,20,30}:
    label(J, d):
        sellout_lead is None       → CAN_WAIT (0)        # kabhi sold out nahi
        margin < 0                 → ALREADY-GONE         # decision ke waqt already sold out
                                                          #   → URGENT (rule §8.6), training se EXCLUDE
        0 <= margin <= W           → BOOK_NOW (1)         # W dinon me sellout (boundary margin=0 included)
        margin > W                 → CAN_WAIT (0)         # W+ din buffer, abhi safe
```

**Worked example (`sellout_lead = 4`, `W = 5`):**

| d | margin | label | kyun |
|---|--------|-------|------|
| 10 | 6 | **CAN_WAIT** | buffer > W → cry-wolf nahi (flip baad mein) |
| 9 | 5 | **BOOK_NOW** | window me aa gaya |
| 4 | 0 | **BOOK_NOW** | boundary (margin=0 included) |
| 2 | −2 | **ALREADY-GONE** → URGENT/exclude | decision ke waqt already sold out |

- **Inequality-flip risk khatam** — single `<`/`<=` nahi, `margin` + horizon `W`. Train/serve dono same.
- **Already-gone alag** (`margin<0`) — BOOK_NOW mein nahi ghusaaya; woh §8.6 ka "already WL → URGENT" rule hai, model ka training case nahi.
- `W` tunable (default **5d**): chhota W = kam cry-wolf; bada W = jaldi alert.
- *(Capacity variant: cumulative confirmed = `total_confirmed_seats` jis lead pe pahunche = sellout_lead. Status-based cleaner.)*

> **v1 simplification — journey key.** Key = `(train, class, quota, journey_date)` — **segment (boarding→alighting) NAHI.** `SeatInventories` schema bhi **train-level** hai (segment-level availability track nahi karta). Lambi train ek segment (DLI→CNB) pe available, doosre (DLI→PNBE) pe WL ho sakti hai (Phase-1 GNWL/PQWL/RLWL nuance). v1 train-level WL se label banata hai; **segment-keying v2 refinement** hai (open item).

> **Snapshot `d` cap.** `d ≤ 30` deliberately (advance booking `MAX_ADVANCE_BOOKING_DAYS=120`, par real action <30 din). Conscious choice — 30 ke aage demand-signal lagbhag flat.

### 8.2 ⚠️ "Never-sold-out" skew (critical)

`label=0` (CAN_WAIT) = "journey kabhi sold out nahi hua" **YA** sellout abhi `W` din se door hai → aisi (especially never-sold-out) journeys ke **saare snapshots label 0**. Bahut saari trains kabhi full nahi hoti → dataset 0 se bhar jaata hai (imbalance 90%+ ho sakta hai, sirf 75% nahi).

- **Asli value sirf "contested" journeys pe hai** (jo kabhi-kabhi full hoti hain). Trivially-empty journeys model ko "bas CAN_WAIT bol do" sikha denge → woh confident-galat ho jaayega exactly contested cases pe.
- Empty journeys **hatao mat** (legit CAN_WAIT examples), par:
  - `scale_pos_weight` (§8.3) yahaan **critical hai, optional nahi.**
  - **Evaluation contested journeys pe** — overall sellout-recall nahi, contested-subset pe recall dekho.

### 8.3 Asymmetric cost / safe-bias

Galat CAN_WAIT (trip miss / Tatkal ₹400) >> galat BOOK_NOW (thoda jaldi). Teen mechanism, par **double-bias se over-correct mat karo**:

1. **`scale_pos_weight` — STRONG bias (mechanical):** data-imbalance ratio ke hisaab se set; false-CAN_WAIT (sellout miss) ko zyada penalize.
2. **Inference threshold — TUNED bias (light):** `P >= 0.30 → BOOK_NOW` sirf **starting guess** hai. Final number precision-recall tradeoff se nikaalo — sellout-recall acceptable ho **bina** CAN_WAIT poora maare.
3. **Metric:** overall accuracy **nahi**. Primary = **contested-journey pe sellout-class recall** (false negative = "predicted CAN_WAIT, actually sold out" minimize).
4. **Guardrail:** **false-BOOK_NOW rate monitor karo** ("BOOK_NOW bola par wait kar sakte the"). ~60% ho gaya → advisor ki value gayi (jo hamesha "book now" bole uspe koi bharosa nahi karta). Over-correction ka red flag.

> Rule: ek jagah strong bias (weight) + doosri tuned (threshold). Dono ko max mat karo.

### 8.4 Leakage — as-of-decision-moment features

Har feature lead `d` pe **time-slice** — sirf `lead >= d` wale bookings se: `fill_rate_at_d = cumulative_confirmed(lead≥d) / capacity`, `velocity_at_d = bookings in [d, d+window]`. Journey ke **final state se kabhi nahi** (poora feature time-evolving hai → autofill ke `user_hist_*` trap se zyada risky). Same shared module training + serving (`fare_advisor_features.py`).

**Full feature vector (sab as-of `d`, leakage-free):**
- *Demand/availability (time-sliced):* `fill_rate_at_d`, `velocity_at_d`, `waitlist_pressure_at_d`, `days_to_journey (=d)`
- *Context (static, journey se):* `distance_bucket`, `train_type` (Rajdhani/Shatabdi surge), `quota`, `train_class`
- *Seasonality (autofill se already paas):* `month`, `is_weekend`, `is_festival_season`
- *Banned (leakage):* `total_fare`, future `booking_status`, final availability

### 8.5 Baseline — recall mein, accuracy mein nahi

Label construct karte hi `P(label=1)` print karo. §8.2 ke skew se "hamesha CAN_WAIT" model high accuracy dega — **par wahi sabse khatarnak model hai.** Gate = "contested sellout-recall mein dumb baseline beat karo", accuracy mein nahi. Balance + baseline number pehle.

**Data sufficiency (training se pehle):** `distinct journeys × snapshots-per-journey` = total training rows print karo, aur **distinct contested journeys** alag se. Agar trains ke distinct journey-dates kam hain → L2 sparse/overfit ho sakta hai; tab L2 defer karke L1 pe raho ya snapshot-window badhaao. 40k bookings ≠ 40k useful rows — aggregation ke baad asli count dekho.

### 8.6 Binary model → decision (URGENT overlay + P bridge)

**Vocabulary (locked — teen alag cheezein, kabhi mix mat karo):**
- `d` = `days_to_journey` — journey kitni paas (serving-time signal)
- `margin = d − sellout_lead` — **sirf §8.1 label construction (training-time)**; serving me iska naamo-nishaan nahi
- `P` = model ka `P(sells-out-within-W)` — L2 serving output
- `fill_rate` / `wl_count` = present availability — L1 serving signal (L2 features mein bhi)

**URGENT ek availability RULE hai (model-class NAHI), dono layers me same, sabse pehle:**
```
already WL (wl_count>0)  OR  seats gone (available<=0)  OR  fill_rate >= URGENT_FILL_RATE  → URGENT
```
URGENT = present-state critical (abhi seat ja chuki / ja rahi) — **time ya probability se nahi**. (Journey 1 din door par seats khaali = URGENT nahi; 10 din door par already-WL = URGENT — isliye time-based URGENT galat hota.)

**URGENT na ho, to forward-looking decision BINARY hai** (§8.1 ka label bhi binary hai — consistency):
- **L2:** `P >= BOOK_NOW_P (0.30, safe-biased tuned) → BOOK_NOW; warna CAN_WAIT`
- **L1:** fill-rate rule (§3 "L1 decision rule")

> Model 3 classes predict **nahi** karta — woh **binary** hai (BOOK_NOW/CAN_WAIT). **URGENT ek rule overlay** hai jo L1 aur L2 dono pe ek jaisa lagta hai. Purani "≤2 din / P>=0.75" wali URGENT definition hata di — woh `margin`/`d`/`P` ko mix kar rahi thi.

### 8.7 Gemini guard (L3)

Decision + numbers **BE mein** compute hote hain (`₹340` = FareCalculator ka GN-vs-Tatkal delta); Gemini ko sirf yeh diye jaate hain with strict prompt: *"sirf in numbers ko shabdon mein kaho, koi naya number/fact mat banao."* Gemini kabhi calculate nahi karta. Fail/rate-limit → templated reason fallback.

### 8.8 Snapshot table (open question — L2-v2)

`booked_at` se sirf **confirmed-arrival curve** banta hai — cancellation/RAC churn nahi. Accurate L2 ke liye **daily availability snapshot** (Celery beat job jo roz har active journey ka `available_confirmed_seats` likhe — "fare_history daily-snapshot" idea) chahiye. Real snapshot = ground truth → seeder-realism risk (§7) bhi khatam.

- **Plan:** L1 + L2-v1 = `booked_at` reconstruction; L2-v2 = real daily snapshots jab jama ho jaayein.

---

## 9. Backlog (deferred — Phase-2 BE doc mein bhi logged)

| Item | Priority | Notes |
|------|----------|-------|
| Effective fare / surge forecast | Medium | GN→Tatkal/PT effective-fare regression (premium component) |
| Price-level classification | Low | `cheap / normal / expensive` band — lightweight UI badge |
| Future base-fare estimate | Low | mostly deterministic via FareCalculator; ML value tabhi jab fare-revision history jama ho |
| Daily availability snapshot table | Medium | Celery beat → per-journey daily `available_confirmed_seats`; L2-v2 ground truth (§8.8) |
| ✅ Batch endpoint (search-list) | **Done** | `POST /api/v1/ai/fare/advisor/batch` — N journeys, 1 call, batched DB (train_id-keyed, index-safe) + batched model inference; badge-only (explain=false). Order-aligned response. |
| ✅ Prediction caching | **Done** | Redis decision cache keyed `(train,class,quota,date)` (explain-independent — list badge & expand share it), TTL 60s (availability churn). `meta.cached` exposed. Explicit booking-invalidation = future (short TTL bounds staleness). |
| ✅ Rate limiting | **Done** | `GET /advisor` 60/min, `POST /advisor/batch` 30/min (per-IP scoped). Batch keeps a search to one rate-limit hit. |
| Autofill-predicted-class wiring | Medium | FE feeds Autofill's predicted class into batch advisor at search time (no BE change — advisor already takes class). |
| Retrain automation | Low | manual one-command → Celery cron, accuracy gate ke saath |
