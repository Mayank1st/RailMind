# Booking + Payment Flow — Frontend Guide

> Status: **changed** (pay-first lifecycle). Backend ab booking ko turant `confirmed`
> nahi karta — pehle payment hota hai, tabhi seat confirm hoti hai.
> Yeh doc batata hai: **naya flow**, **exact API contracts**, **FE pe kya test karna hai**,
> aur **kya missing ho sakta hai jo FE ko check + fix karna hai.**

Auth: in saare endpoints pe `Authorization: Bearer <access_token>` header chahiye.
Har response is envelope me wrapped hai:

```jsonc
{ "success": true, "message": "...", "data": { /* actual payload */ }, "errors": null, "meta": null }
```

Asli fields hamesha `data` ke andar hain.

---

## 1. Kya badla (TL;DR)

| | **Pehle** | **Ab** |
|---|---|---|
| Booking banते hi status | `confirmed` / `rac` / `waitlisted` | **`payment_pending`** |
| Seat kab block hoti hai | booking pe | booking pe (same — seat turant HOLD hoti hai) |
| Confirm kab hoti hai | booking pe hi | **payment success pe** |
| Payment fail ho to | kuch nahi (seat block reh jaati thi) | **seat release + booking `cancelled`** |

**FE impact:** booking banane ke baad ab ek **payment step zaroori hai**. Jab tak payment
success na ho, ticket `payment_pending` rahega (confirmed nahi). Pehle wala "book = ticket
mil gaya" assumption ab galat hai.

---

## 2. Naya flow (sequence)

```
[1] POST /api/v1/bookings/                -> booking banti hai, status = "payment_pending"
                                              (seat/RAC/WL turant HOLD ho jaata hai)
        |
        v   (booking_id mila)
[2] POST /api/v1/payments/initiate        -> payment order banta hai, payment_status = "pending"
                                              (payment_id mila)
        |
        v   (user card/UPI/netbanking enter karta hai)
[3] POST /api/v1/payments/process
        |
        +-- SUCCESS  -> booking_status = "confirmed" / "rac" / "waitlisted"
        |               (jo availability booking pe mili thi)
        |
        +-- FAILED   -> seat release, booking_status = "cancelled"
                        (user ko dobara book karna padega)
```

> Ek booking ke liye ek hi active payment allowed hai. Agar `initiate` ke baad
> dobara `initiate` karoge to `409` aayega (RM-PAY-009).

---

## 3. API contracts (exact)

### 3.1 — Create booking
`POST /api/v1/bookings/`

**Request**
```jsonc
{
  "train_number": "12951",
  "journey_date": "2026-05-01",
  "from_station": "NDLS",
  "to_station": "BCT",
  "train_class": "SL",
  "quota": "GN",
  "passengers": [
    { "passenger_id": "<uuid>", "berth_preference": "LB" }
  ]
}
```

**Response (`data`)**
```jsonc
{
  "pnr_number": "1234567890",
  "booking_id": "<uuid>",
  "booking_status": "payment_pending",   // <-- AB YEH AATA HAI (pehle confirmed/rac/waitlisted)
  "train_number": "12951",
  "train_name": "...",
  "journey_date": "2026-05-01",
  "from_station": "NDLS",
  "to_station": "BCT",
  "train_class": "SL",
  "quota": "GN",
  "total_fare": 850.0,
  "availability": "AVAILABLE",           // AVAILABLE | RAC | WL  -> seat kis type ki hold hui
  "wl_type": null,                       // WL hone par "GNWL"/"RLWL"/... warna null
  "next_wl_position": null,
  "passengers": [ { "passenger_id": "...", "passenger_status": "CNF", "seat_number": "S4-32", ... } ]
}
```

FE ko yahan se chahiye: **`booking_id`** (next step ke liye) aur **`total_fare`** (user ko dikhane ke liye).
`availability` se FE bata sakta hai ki user CNF/RAC/WL seat ke liye pay kar raha hai.

### 3.2 — Initiate payment
`POST /api/v1/payments/initiate`

**Request**
```jsonc
{ "booking_id": "<uuid from step 3.1>" }
```

**Response (`data`)**
```jsonc
{
  "payment_id": "<uuid>",            // <-- process step me chahiye
  "booking_id": "<uuid>",
  "booking_pnr": "1234567890",
  "amount": 850.0,
  "currency": "INR",
  "mock_order_id": "mock_order_xxx",
  "payment_status": "pending"
}
```

### 3.3 — Process payment
`POST /api/v1/payments/process`

**Request** — `payment_method` ke hisaab se fields (validation backend karta hai):

```jsonc
// CARD
{ "payment_id": "<uuid>", "payment_method": "CARD",
  "card_number": "4242424242424242", "card_cvv": "123", "card_holder_name": "..." }

// UPI
{ "payment_id": "<uuid>", "payment_method": "UPI", "upi_id": "railmind@upi" }

// NETBANKING
{ "payment_id": "<uuid>", "payment_method": "NETBANKING",
  "netbanking_user": "railmind", "netbanking_password": "railmind" }
```

**Response (`data`)** — envelope ka `success` payment ke result ko reflect karta hai:
```jsonc
{
  "payment_id": "<uuid>",
  "booking_pnr": "1234567890",
  "payment_status": "success",        // ya "failed"
  "payment_method": "CARD",
  "booking_status": "confirmed",      // success -> confirmed/rac/waitlisted ; fail -> cancelled
  "paid_at": "2026-06-03T10:00:00Z",
  "failure_reason": null              // fail pe reason aata hai (e.g. "Invalid card number")
}
```

> **Important:** payment success ka matlab hamesha `confirmed` nahi. Agar booking RAC/WL
> me thi, success ke baad `booking_status` `"rac"` / `"waitlisted"` aayega. FE ise raw
> `booking_status` se dikhaye, hardcode "Confirmed" mat karo.

### 3.4 — Payment status (poll/refresh)
`GET /api/v1/payments/{payment_id}/status` — `data` me `payment_status`, `payment_method`,
`paid_at`, `failed_at`, `failure_reason`.

### 3.5 — Cancel booking
`POST /api/v1/bookings/{booking_id}/cancel` — `payment_pending` aur `confirmed`/`rac`/`waitlisted`
dono cancel ho sakte hain; held seat release ho jaata hai.

---

## 4. Status values — FE ko kya dikhana hai

**`booking_status`** (string):

| value | FE pe dikhao | kab |
|---|---|---|
| `payment_pending` | "Payment Pending" / payment screen kholo | booking banne ke baad, pay se pehle |
| `confirmed` | "Confirmed (CNF)" | payment success (seat available thi) |
| `rac` | "RAC" | payment success (RAC seat) |
| `waitlisted` | "Waitlisted (WL)" | payment success (WL) |
| `cancelled` | "Cancelled" | payment fail **ya** user cancel |

**`payment_status`**: `pending` → `success` / `failed`.

---

## 5. FE ko ye test karna hai (checklist)

1. **Happy path (CNF):** available seat wali booking banao → `payment_pending` aana chahiye →
   initiate → process (valid card) → `booking_status: confirmed`.
2. **RAC / WL path:** aisi journey jisme available seat na ho (RAC/WL) → pay success ke baad
   status `rac` / `waitlisted` aaye, "Confirmed" nahi. FE label sahi dikhe.
3. **Payment fail → seat release:** koi **galat** card/UPI daalo (table neeche) → response
   `success:false`, `payment_status: failed`, `booking_status: cancelled`. **Seat wapas
   available honi chahiye** — same train/class/date pe dobara book karke verify karo ki seat
   count badh gaya (leak nahi hona chahiye).
4. **Double initiate block:** ek booking pe `initiate` 2 baar → 2nd pe `409` (RM-PAY-009).
   FE error handle kare (button disable / "payment already started").
5. **Cancelled booking pe pay:** fail ke baad jo booking `cancelled` ho gayi, uspe dobara
   `initiate` → `422` (RM-PAY-005 "Booking not in payable state"). FE graceful message dikhaye.
6. **Cancel of unpaid booking:** `payment_pending` booking ko `/cancel` karo → seat release ho.
7. **Refresh/resume:** payment screen pe user refresh kare → `GET /payments/{id}/status`
   se actual state dikhe (stuck na ho).

**Mock test credentials** (`.sample.env` ke; actual `.env` backend se confirm karo):

| Method | VALID (success) | INVALID (fail test) |
|---|---|---|
| Card (credit) | `4242424242424242`, CVV `123` | koi bhi aur number/CVV |
| Card (debit) | `1212121212121212`, CVV `123` | — |
| UPI | `railmind@upi` | koi aur upi id |
| Netbanking | user `railmind` / pass `railmind` | koi aur cred |

---

## 6. Kya missing ho sakta hai — FE check + fix kare

In points ko FE side pe verify karke, agar gap ho to fix/handle karo:

1. **Booking ke baad payment screen auto-trigger** — booking success pe FE ab seedha
   confirmation mat dikhaye; payment flow shuru karna hai. Purana "booking done" screen
   hata/adjust karo.

2. **"Confirmed" hardcode** — pehle booking response `confirmed` deta tha, FE ne shayad
   wahi hardcode kar rakha ho. Ab `booking_status` raw value se render karo (`payment_pending`
   handle karna zaroori hai, warna unknown state pe UI toot sakta hai).

3. **Payment failure pe seat-released messaging** — fail hone par booking `cancelled` ho
   jaati hai. FE clearly bataye "Payment fail, booking cancelled — please rebook." User ko
   ye lagna nahi chahiye ki ticket still pending hai.

4. **Abandoned payment (BACKEND GAP — FE ke liye limitation):** agar user `initiate` karke
   payment screen chhod de (process kabhi na kare), to abhi koi auto-release/timeout **nahi**
   hai — seat hold reh jaayega aur us booking pe dobara initiate bhi block rahega.
   - FE temporary mitigation: payment screen pe ek "Cancel / Go back" button do jo
     `POST /bookings/{booking_id}/cancel` call kare, taaki user khud seat free kar sake.
   - Proper fix backend pe aana chahiye (timeout job — `PAYMENT_TIMEOUT_SECONDS = 600`
     constant already defined hai par use nahi ho raha). Isko backend ticket banao.

5. **Razorpay vs mock** — abhi `PAYMENT_MODE=mock`. Non-mock gateway pe `initiate`
   `501 Not Implemented` dega. FE error handle kare; real gateway integration pending hai.

6. **`amount` precision** — `amount` `Decimal`/string ya number ho sakta hai JSON me; FE
   parse karte waqt `total_fare` (booking) aur `amount` (payment) match karke dikhaye.

---

### Endpoints summary

| Action | Method + Path |
|---|---|
| Create booking | `POST /api/v1/bookings/` |
| Initiate payment | `POST /api/v1/payments/initiate` |
| Process payment | `POST /api/v1/payments/process` |
| Payment status | `GET /api/v1/payments/{payment_id}/status` |
| Cancel booking | `POST /api/v1/bookings/{booking_id}/cancel` |
