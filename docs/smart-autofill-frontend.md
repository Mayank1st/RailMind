# Smart Form Autofill — Frontend Integration Guide

> **This is the ONE autofill endpoint to use.** The old `/api/v1/ai/form/autofill`
> route is deprecated/not wired for the FE — ignore it. Everything below is the only
> supported path.

It returns history-based suggestions (train class, quota, passengers, berths) from the
user's own bookings. Backend automatically picks the engine:

- new user / little history → safe **defaults**
- some history → **rules** (most-used class for this distance)
- rich history (>10 bookings) + trained model → **ML model**

The FE does **not** need to know which engine ran — the response shape is always the
same. The `source` field just tells you, for analytics/debug.

---

## 0. What THIS page owns (read first)

In our flow, **class and quota are chosen on the search page** and arrive at the
passenger page as **fixed URL params** (they drive fare + the summary bar and are
**not editable here**). So on the **passenger page**:

- ✅ **Apply autofill to: `passengers` + their `berths`.** That's what this page owns.
- 🚫 **Do NOT override the user's already-chosen `class` / `quota`** with the response's
  `train_class` / `quota` fields. The user picked those on the prior step — respect them.

The response still returns `train_class` and `quota` (the endpoint is generic), but on
this page treat them as **read-only context** (see §4) — don't write them into the form.

> Surfacing class/quota *suggestions earlier* (e.g. pre-selecting the class chip on the
> search / train-details step) is a **separate, larger change** to the search flow — not
> part of this page. Doable later if wanted.

---

## 1. Endpoint

```
GET /api/v1/ai/form/smart-autofill
```

**Auth: required.** Uses the same cookie session as the rest of the app
(`access_token` httpOnly cookie set at login). So:

- Send credentials with the request (`fetch(..., { credentials: "include" })` or
  axios `withCredentials: true`).
- **Only call it for logged-in users.** For guests it returns `401` — don't call it,
  just skip autofill.

### Query params

| Param | Required | Type | Notes |
|-------|----------|------|-------|
| `source_station_code` | ✅ | string | boarding station code, e.g. `"HWH"` |
| `destination_station_code` | ✅ | string | destination code, e.g. `"NDLS"` |
| `train_number` | optional | string | the selected train, e.g. `"12381"`. **Omit it** to get only the `favourite_train` block (no class/berth prediction). |
| `journey_date` | optional | string `YYYY-MM-DD` | improves the ML prediction (season/weekday). Send it if the user has picked a date. |

**Two ways to call it:**

| You send | You get back |
|----------|--------------|
| route **+ `train_number`** | full autofill (class/passengers/berths) **+** `favourite_train` |
| route only (**no `train_number`**) | `favourite_train` only; autofill fields come back empty (`train_class.value = null`, `passengers = []`) |

`favourite_train` depends only on **user + route**, so it's returned in both cases.

Example:

```
GET /api/v1/ai/form/smart-autofill?train_number=12381&source_station_code=HWH&destination_station_code=NDLS&journey_date=2026-07-15
```

---

## 2. When to call it

Call **once**, right after the user has chosen **train + source + destination**
(i.e. when the passenger/class form opens) and **before** they start filling it —
that's the whole point: arrive on a pre-filled form.

- ✅ Trigger: train selected → opening the "add passengers / choose class" step.
- ✅ Re-call only if the train or route changes.
- ❌ Don't call on every keystroke / repeatedly. It's one call per form open.
- ❌ Don't block the form on it — render the form, apply suggestions when the
  response arrives (it's fast, but treat it as enhancement, not a gate).

---

## 3. Response shape

Standard API envelope:

```jsonc
{
  "success": true,
  "message": "Autofill suggestions generated successfully.",
  "data": { /* SmartAutofill — see below */ },
  "errors": null,
  "meta": { "confidence_threshold": 0.75 }   // <-- use this, don't hardcode 0.75
}
```

`data`:

```jsonc
{
  "train_class": { "value": "3A", "confidence": 0.82 },
  "quota":       { "value": "GN", "confidence": 1.0 },
  "passengers": [
    {
      "passenger_id": "09b287f8-...",
      "full_name": "Aarav Sharma",
      "age": 34,
      "gender": "FEMALE",
      "berth": { "value": "LB", "confidence": 1.0 },   // suggested berth for THIS passenger
      "confidence": 1.0                                  // how often this passenger is booked
    }
  ],
  "favourite_train": {            // most-booked train on THIS route; null if none
    "train_number": "14317",
    "train_name": "IND DDN EXPR",
    "previous_booking_count": 4
  },
  "source": "MODEL",              // "MODEL" | "HISTORY" | "DEFAULTS"
  "model_version": "autofill-class-v2", // present only when source = MODEL
  "distance_bucket": "LONG",      // SHORT | MEDIUM | LONG | XLONG  (info only)
  "journey_distance_km": 1438,    // info only
  "booking_count": 1000,          // user's total bookings (info only)
  "based_on_bookings": 1000,      // how many bookings the suggestion used (info only)
  "auto_fill": false              // convenience: train_class.confidence >= threshold
}
```

### TypeScript types

```ts
interface FieldSuggestion {
  value: string | null;
  confidence: number; // 0.0 - 1.0
}

interface PassengerSuggestion {
  passenger_id: string;
  full_name: string;
  age: number;
  gender: "MALE" | "FEMALE" | "TRANSGENDER";
  berth: FieldSuggestion;
  confidence: number;
}

interface FavouriteTrain {
  train_number: string;
  train_name: string;
  previous_booking_count: number;
}

interface SmartAutofill {
  train_class: FieldSuggestion;
  quota: FieldSuggestion;
  passengers: PassengerSuggestion[];
  favourite_train: FavouriteTrain | null;
  source: "MODEL" | "HISTORY" | "DEFAULTS";
  model_version: string | null;
  distance_bucket: "SHORT" | "MEDIUM" | "LONG" | "XLONG" | null;
  journey_distance_km: number | null;
  booking_count: number;
  based_on_bookings: number;
  auto_fill: boolean;
}

interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T | null;
  errors: { code: string; field: string | null; message: string }[] | null;
  meta: { confidence_threshold: number } | null;
}
```

---

## 4. How to apply the suggestions (the important part)

Every suggestible field comes as `{ value, confidence }`. Compare each field's
`confidence` against `meta.confidence_threshold` (currently `0.75`):

| confidence | UX |
|------------|-----|
| `>= threshold` | **Auto-fill** the field (pre-select it). User can still change it. |
| `< threshold` (and `> 0`) | **Soft suggestion** — pre-fill but mark it visually (e.g. a "suggested" chip / lighter style), or show as a hint the user confirms. Do not treat as final. |
| `0.0` | No real signal (cold-start default) — fill it as a neutral default, no "smart" badge. |

### ✅ Apply on THIS (passenger) page

- **`passengers[]`** → pre-tick / pre-add these saved passengers (use `passenger_id`
  as the key when adding to the booking). Show `full_name / age / gender`. They're
  ordered most-frequent first.
- **`passengers[].berth.value`** → preselect that passenger's berth preference
  (apply the confidence rule above).

Always let the user override — these are suggestions, not locks.

```ts
const res = await fetch(
  `/api/v1/ai/form/smart-autofill?train_number=${trainNumber}` +
  `&source_station_code=${src}&destination_station_code=${dst}` +
  (journeyDate ? `&journey_date=${journeyDate}` : ""),
  { credentials: "include" }
);
const body: ApiResponse<SmartAutofill> = await res.json();
if (!body.success || !body.data) return; // skip autofill silently

const { data } = body;
const threshold = body.meta?.confidence_threshold ?? 0.75;

// This page owns passengers + berths only:
data.passengers.forEach((p) => {
  addPassenger({ id: p.passenger_id, name: p.full_name, age: p.age, gender: p.gender });
  setBerth(p.passenger_id, p.berth.value, p.berth.confidence >= threshold);
});

// data.train_class / data.quota are NOT written here — class & quota came as fixed
// URL params from the search page. See "read-only context" below.
```

### 🚫 Read-only context (do NOT write to the form on this page)

- **`train_class.value`** and **`quota.value`** — informational only here. The user
  already chose class/quota on the search step (fixed URL params). Don't override them.
- Optional use: you *may* compare the suggestion to the user's chosen class for a
  gentle, non-blocking nudge (e.g. "You usually book 3A on this route" if it differs) —
  but never auto-change their selection.
- `distance_bucket`, `journey_distance_km`, `booking_count`, `based_on_bookings`,
  `source`, `auto_fill` → analytics/debug only.

> If/when class & quota become suggestible on the search step, the same
> `train_class` / `quota` fields + confidence rule apply there — no API change needed.

### ⭐ `favourite_train` (route-level hint)

The most-booked train on the selected route — a plain history count, not ML.
Great as a quick-pick on the **train-selection / search step**: call the endpoint
with **only the route (no `train_number`)** and, if `favourite_train` is non-null,
show e.g. *"You usually take **IND DDN EXPR (14317)** — booked 4×"* as a one-tap option.

- `null` → user hasn't booked this route before; show nothing.
- No confidence field — it's a factual count (`previous_booking_count`), not a prediction.
- It does **not** check live availability for the date; that's handled later in the
  booking flow. Treat it as "your usual train", not "guaranteed bookable".

---

## 5. Value → label reference (map codes to UI text)

**Train class** (`train_class.value`):

| Code | Label |
|------|-------|
| `SL` | Sleeper |
| `3A` | AC 3 Tier |
| `2A` | AC 2 Tier |
| `1A` | AC First Class |
| `CC` | AC Chair Car |
| `2S` | Second Sitting |
| `FC` | First Class |
| `3E` | AC 3 Economy |

**Quota** (`quota.value`):

| Code | Label |
|------|-------|
| `GN` | General |
| `TQ` | Tatkal |
| `PT` | Premium Tatkal |
| `LD` | Ladies |
| `SS` | Senior Citizen |
| `HP` | Handicapped |
| `DF` | Defence |
| `FT` | Foreign Tourist |
| `LB` | Lower Berth |

**Berth** (`passengers[].berth.value`):

| Code | Label |
|------|-------|
| `LB` | Lower |
| `MB` | Middle |
| `UB` | Upper |
| `SL` | Side Lower |
| `SU` | Side Upper |
| `NP` | No Preference |

**Gender** (`passengers[].gender`): `MALE` / `FEMALE` / `TRANSGENDER`.

---

## 6. Edge cases

| Situation | What you get | FE behavior |
|-----------|--------------|-------------|
| Guest / not logged in | `401`, `errors[0].code = "RM-AUTH-001"` | Don't call it; render an empty form. |
| New user, ≤5 bookings | `source: "DEFAULTS"`, confidences `0.0`, defaults `3A` / `GN` / primary passenger | Fill as plain defaults, no "smart" badge. |
| Route can't be resolved | suggestions still return (history-based), `journey_distance_km` may be `null` | Apply normally. |
| No saved passengers | `passengers: []` | Just don't pre-add anyone. |
| `value` is `null` | rare; means no signal for that field | Skip that field. |
| First time on this route | `favourite_train: null` | Don't show the "usual train" hint. |
| Called without `train_number` | autofill fields empty, `favourite_train` populated | Use it for the route-level "usual train" hint only. |

Always code defensively: if `success` is false or `data` is null, just skip autofill —
the user fills the form manually. Autofill is an enhancement, never a blocker.

---

## 7. Quick manual test (curl)

```bash
# 1) login (use a verified test user) -> saves cookie
curl -s -c cookies.txt -X POST https://<API>/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"<email>","password":"<password>"}'

# 2) autofill
curl -s -b cookies.txt \
  "https://<API>/api/v1/ai/form/smart-autofill?train_number=12381&source_station_code=HWH&destination_station_code=NDLS&journey_date=2026-07-15"
```

`source` in the response tells you which engine answered: `MODEL` (ML), `HISTORY`
(rules), or `DEFAULTS` (cold start).
