# FE on localhost + BE on GCP (`https://railmind.ddns.net`) — Cookie Auth Setup

## The Problem

Login (Google / password / OTP) succeeds, but every protected route (`/api/v1/auth/me`, bookings, etc.) returns:

```json
{ "success": false, "errors": [{ "code": "RM-AUTH-001", "message": "Not authenticated. Please login" }] }
```

### Why it happens

RailMind auth is **cookie-based** (`access_token`, `refresh_token`, `csrf_token` are set as cookies by the backend — see `app/services/auth_service.py → _set_auth_cookies`).

| Setup | Site relationship | Cookie type | Result |
|---|---|---|---|
| FE `localhost:3000` + BE `localhost:8000` | Same site (`localhost`) | First-party | ✅ Works |
| FE `localhost:3000` + BE `railmind.ddns.net` | **Cross-site** | **Third-party** | ❌ Blocked |

When the page is `http://localhost:3000` and the API is `https://railmind.ddns.net`, the auth cookies become **third-party cookies**. Chrome blocks third-party cookies (tracking protection, default in Incognito and rolling out everywhere) — **even with `SameSite=None; Secure` set correctly**. The `Set-Cookie` header arrives but the browser silently refuses to store it, so the next request carries no cookie → 401.

This is a browser policy, not a backend bug. The fix is to make the browser believe everything is same-origin.

---

## The Solution: Dev-Server Proxy

Route all API calls **through the FE dev server**. The browser only ever talks to `localhost:3000`; the dev server forwards requests to GCP behind the scenes. Cookies become first-party and everything works exactly like full-local dev.

```
Browser ──same-origin──▶ localhost:3000 (dev server) ──proxy──▶ https://railmind.ddns.net
                          cookies stored against localhost:3000 ✅
```

### Step 1 — Configure the proxy

**Next.js** (`next.config.js`):

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "https://railmind.ddns.net/api/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
```

**Vite / React** (`vite.config.ts`):

```ts
export default defineConfig({
  server: {
    proxy: {
      "/api": {
        target: "https://railmind.ddns.net",
        changeOrigin: true, // sends Host: railmind.ddns.net upstream
        secure: true,       // verify the TLS cert (set false only if cert issues)
      },
    },
  },
});
```

### Step 2 — Use relative API URLs in FE code

The browser must never see `railmind.ddns.net` directly. Make the base URL environment-driven:

```js
// .env.development  →  NEXT_PUBLIC_API_BASE_URL=          (empty → relative, goes via proxy)
// .env.production   →  NEXT_PUBLIC_API_BASE_URL=https://railmind.ddns.net

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "";

fetch(`${API_BASE}/api/v1/auth/google`, {
  method: "POST",
  credentials: "include", // harmless on same-origin, required if you ever go cross-origin
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ id_token: idToken }),
});

fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" });
```

> ❌ `fetch("https://railmind.ddns.net/api/v1/auth/me")` from localhost — cookies blocked.
> ✅ `fetch("/api/v1/auth/me")` — goes through the proxy, cookies are first-party.

### Step 3 — Restart the dev server and verify

1. Restart `npm run dev` (proxy config is read at startup).
2. Login via Google.
3. DevTools → **Application → Cookies → `http://localhost:3000`** → `access_token`, `refresh_token`, `csrf_token` should be present.
4. DevTools → Network → `me` request → Request Headers must contain `Cookie: access_token=...`.
5. `/api/v1/auth/me` returns `200` ✅

---

## Switching FE Between Local BE ↔ GCP BE (the daily workflow)

FE code me **kabhi bhi** backend ka absolute URL mat rakho. Sirf **proxy ka target** switch karo — browser ke liye sab kuch hamesha `localhost:3000` same-origin rehta hai, isliye cookies/CORS ka sawal hi nahi uthta, chahe BE kahin bhi ho.

```js
// next.config.js — target env se aata hai
const BE_TARGET = process.env.BE_TARGET || "http://localhost:8000";

module.exports = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BE_TARGET}/api/:path*` }];
  },
};
```

```bash
# FE development (BE GCP pe chal raha hai):
BE_TARGET=https://railmind.ddns.net npm run dev

# BE development (BE local pe chal raha hai):
npm run dev          # default localhost:8000
```

(Vite me same cheez: `target: process.env.BE_TARGET || "http://localhost:8000"`.)

Ek hi env var ka switch — FE code untouched, BE config untouched, dono case me cookies first-party. ✅

---

## Backend Checklist (already in place — do not break these)

Cookie flags are **env-derived** via `app/config.py` — `DEBUG` drives sane defaults, with explicit overrides available:

| Mode | `cookie_secure` | `cookie_samesite` | Why it works |
|---|---|---|---|
| Local BE (`DEBUG=true`) | `False` | `lax` | Plain http pe har browser me chalta hai (Safari included); `none`+insecure combo har browser reject karta hai |
| Prod BE (`DEBUG=false`) | `True` | `none` | HTTPS + cross-site capable |
| Explicit override | `COOKIE_SECURE` / `COOKIE_SAMESITE` in `.env` | — | Kisi special deployment ke liye |

⚠️ **Historical bug (fixed):** `DEBUG` was typed `str` in `config.py`, so `.env` ka `DEBUG=false` string `"false"` (truthy!) banta tha → prod cookies `SameSite=None` + `Secure=False` ke saath jati thin, jo browsers reject karte hain. Ab `bool` hai — yeh type kabhi wapas `str` mat karna.

| Setting | Location | Value | Why |
|---|---|---|---|
| `samesite` / `secure` | `auth_service.py → _set_auth_cookies` (set **and** `delete_cookie` in logout) | env-derived (table above) | Set/delete dono pe same flags, warna logout cross-site me cookie clear nahi karta |
| `httponly=True` | same (access/refresh) | `True` | JS cannot read tokens (XSS protection); CSRF cookie stays readable by design |
| `allow_credentials=True` | `app/main.py` CORSMiddleware | `True` | Browser refuses credentialed CORS without it |
| Explicit origins (no `*`) | `app/main.py` ← `CORS_ORIGINS` in `.env` | `http://localhost:3000,...` (comma-separated) | `*` is invalid when `allow_credentials=True`; nayi origin add karni ho to sirf `.env` badlo |

**Note:** with the dev proxy, requests reaching GCP have `Origin: http://localhost:3000` (Next.js) or the proxied host — CORS still passes because `localhost:3000` is in `allow_origins`. No backend change needed.

### Nginx on GCP (if backend sits behind it)

Make sure the proxy does **not** strip or rewrite cookies:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;  # so FastAPI knows it's https
    # do NOT use proxy_cookie_domain / proxy_hide_header Set-Cookie
}
```

---

## Production Deployment (when FE also goes live)

Host FE and BE under the **same hostname** with path-based routing, so cookies are always first-party:

```
https://railmind.ddns.net/        → FE (static build / Node server)
https://railmind.ddns.net/api/... → FastAPI backend
```

⚠️ **`ddns.net` is on the Public Suffix List.** `fe.ddns.net` and `railmind.ddns.net` count as *different sites*, so a separate-subdomain FE would hit the exact same third-party cookie blocking. Same hostname + path routing is the safe pattern. (On a normal owned domain like `railmind.com`, `app.railmind.com` + `api.railmind.com` with `SameSite=None` would also work.)

---

## If Errors Keep Recurring — Check the GCP Box Itself

Cookie/proxy setup being correct doesn't help if the server itself is choking. Observed symptoms: intermittent hangs/timeouts, and first-byte time on `/common/stations` swinging between **1s and 15s** — that smells like a small instance getting saturated.

### 1. Nginx

- `keepalive_timeout` should not be very short — the default **65s is fine**; don't lower it.
- Check `/var/log/nginx/error.log` around the failure timestamps — upstream timeouts, worker connection limits, etc. show up here first.

### 2. HTTP/2 hang

One window was observed where **HTTP/2 hung while HTTP/1.1 answered instantly**. If that recurs:

```bash
# reproduce/compare:
curl -sso /dev/null -w "%{time_starttransfer}\n" --http2 https://railmind.ddns.net/api/v1/common/stations
curl -sso /dev/null -w "%{time_starttransfer}\n" --http1.1 https://railmind.ddns.net/api/v1/common/stations
```

If h2 is consistently slower/hanging, check nginx's http2 handling (nginx version, `http2_max_concurrent_streams`) or temporarily disable it:

```nginx
listen 443 ssl;        # was: listen 443 ssl http2;
```

### 3. Uvicorn workers & VM resources

The dev compose (`docker/docker-compose.yml`) runs uvicorn with **`--reload`** — single process + file-watcher overhead. Never run that on the GCP box; it is the main reason prod requests crawl.

**Fixed in repo:** use the prod override file on GCP instead:

```bash
# on the GCP box, from the repo root:
docker compose --env-file .env \
  -f docker/docker-compose.yml -f docker/docker-compose.prod.yml \
  up -d --build
```

`docker/docker-compose.prod.yml` swaps the backend command to multi-worker uvicorn (no `--reload`) and adds `restart: unless-stopped` to all services. Worker count is tunable via `WEB_CONCURRENCY` in `.env` (default **2**; raise towards CPU core count on bigger instances). The `Dockerfile` CMD has the same `--workers ${WEB_CONCURRENCY:-2}` default for non-compose deploys (e.g. Cloud Run).

Local dev is unchanged — plain `-f docker/docker-compose.yml` still gives you `--reload`.

And check resource pressure while requests are slow:

```bash
top            # CPU steal/load
free -m        # memory; swap usage = bad sign on small instances
docker stats   # per-container CPU/mem
```

If a small e2-micro/small instance is pegged, either upsize or reduce per-request work (next point).

### 4. Cache `/common/stations` (~400 KB per hit)

`app/api/v1/endpoints/common.py → get_all_stations` hits the DB and serializes ~400 KB on **every** request, for data that almost never changes. Two cheap wins:

- **Redis cache** in the service (e.g. `setex("stations:all", 86400, json)`), invalidate on station writes.
- **HTTP caching**: add `Cache-Control: public, max-age=86400` on the response so browsers/nginx can cache it; optionally `proxy_cache` in nginx.

This alone removes the biggest repeated payload from the slow path.

---

## Debugging Quick Reference

| Symptom | Check | Meaning |
|---|---|---|
| 401 right after successful login | `Set-Cookie` in login response has ⚠️ icon in DevTools | Browser blocked the cookie (third-party / Secure violation) |
| Cookie stored but not sent | Login on `localhost`, `/me` on `127.0.0.1` (or vice-versa) | Host mismatch — cookies are host-scoped, use one host everywhere |
| Works in Chrome, fails in Incognito | Third-party cookies | Incognito blocks them by default — use the proxy |
| `Set-Cookie` missing entirely | Nginx config / `issue_session` not called | Inspect server logs |
| CORS error in console | Origin missing from `allow_origins` in `app/main.py` | Add the exact FE origin |
