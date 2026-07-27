# Background Crawl — Design Spec

## Problem

LibreCrawl is deployed on a shared Ubuntu server accessed via Tailscale by a team. When a user starts a crawl and closes their browser (or laptop), the crawl thread keeps running on the server — but there is no way for anyone to reconnect to it or see its results unless they manually navigate to the dashboard and find the crawl record.

**Current gaps:**
- `crawler_instances` dict is keyed by ephemeral `session_id` — no cross-session visibility
- `recover_crashed_crawls()` marks running crawls as `failed` on server restart instead of auto-resuming
- Frontend `initializeApp()` does not check for active crawls on page load
- Dashboard shows all crawls but does not surface running crawls prominently
- Cleanup thread calls `stop_crawl()` on idle instances, potentially killing a still-useful crawl

## Goal

A user can start a crawl, close their browser (or turn off their laptop), and later — from any device — open LibreCrawl and see the crawl is either still running (with live progress) or completed (with full results available).

## Use Case

1. Richo starts crawl of `avonetiq.com` from MacBook
2. Richo closes browser, turns off laptop
3. Server continues crawling — data saved to SQLite every 30 seconds
4. 1 hour later, Dika opens LibreCrawl from Windows laptop
5. Dika sees "avonetiq.com — running (73%)" banner on main page
6. Dika clicks banner → live progress view loads
7. Crawl finishes → Dika views full results

## Architecture

### Current Flow
```
Browser → POST /api/start_crawl → WebCrawler.start_crawl()
  → Thread spawned → returns True
  → Browser polls /api/crawl_status every 1s
  → Browser closes → polling stops → thread keeps running
  → No way to reconnect
```

### New Flow
```
Browser → POST /api/start_crawl → WebCrawler.start_crawl()
  → Thread spawned → crawl_id stored in DB
  → Browser closes → thread keeps running → data saved to DB
  → Browser reopens → GET /api/my_active_crawls
  → Sees active crawl → clicks to reconnect
  → Frontend loads crawl data from DB → starts polling
```

## Changes

### 1. Backend: Crawler Recovery on Startup

**File:** `main.py` — `recover_crashed_crawls()`

Currently marks `running` crawls as `failed`. Change to:

1. Find crawls with `status = 'running'` in DB
2. For each: create a new `WebCrawler` instance, call `resume_from_database(crawl_id)`
3. This re-attaches the in-memory crawler to the DB state and restarts the thread
4. Store the re-attached crawler in `crawler_instances` under a synthetic session key (e.g., `recovered_{crawl_id}`)
5. If resume fails (e.g., DB corruption), fall back to marking as `failed`

**File:** `src/crawler.py` — verify `resume_from_database()` handles the full lifecycle correctly (it already does at line 435-580).

### 2. Backend: New API Endpoints

#### `GET /api/my_active_crawls`
Returns all crawls with `status IN ('running', 'paused')` for the current user.

```json
[
  {
    "crawl_id": 42,
    "base_url": "https://avonetiq.com",
    "base_domain": "avonetiq.com",
    "status": "running",
    "urls_crawled": 150,
    "urls_queued": 55,
    "progress_percent": 73,
    "started_at": "2026-07-26T10:30:00",
    "last_saved_at": "2026-07-26T11:15:00"
  }
]
```

**Implementation:**
- `crawl_db.py`: Add `get_user_active_crawls(user_id)` query
- `main.py`: New route, uses existing auth middleware

#### `POST /api/crawls/<id>/reconnect`
Attaches current session to an existing crawl's in-memory crawler instance.

**Implementation:**
- Look up crawl in `crawler_instances` (check by crawl_id across all instances)
- If in-memory instance exists: bind to current session, return success
- If not (crawl was recovered or server restarted): call `resume_from_database()` to create fresh instance
- Return crawl status + initial data snapshot for frontend rendering

### 3. Backend: Cleanup Thread Adjustment

**File:** `main.py` — `cleanup_old_instances()`

**Current:** Calls `crawler.stop_crawl()` on idle instances, which stops the thread and marks as `stopped`.

**New:**
- Remove in-memory instance from `crawler_instances` dict (free memory)
- Do NOT call `stop_crawl()` — the crawl data is already persisted to DB
- The crawl thread will eventually finish naturally, or can be resumed from DB later
- Exception: if the crawl thread is truly orphaned (no DB record, or completed), just remove it

### 4. Frontend: Auto-Reconnect on Page Load

**File:** `web/static/js/app.js` — `initializeApp()`

After existing initialization:

1. Call `GET /api/my_active_crawls`
2. If results non-empty:
   - Show a banner bar below the URL input: "avonetiq.com sedang dicrawl (73%) — Klik untuk melihat live progress"
   - Banner is dismissible but auto-shows on each page load while crawl is active
3. Clicking the banner:
   - Calls `POST /api/crawls/<id>/reconnect`
   - Loads existing crawl data from the reconnect response
   - Starts `pollCrawlProgress()` to resume live monitoring
   - Same UX as watching a fresh crawl

### 5. Frontend: Dashboard Active Crawl Section

**File:** `web/static/js/dashboard.js`

Dashboard already shows all crawls. Changes:

1. At top of dashboard, add "Active Crawls" section
2. Show crawls with `status === 'running'` or `status === 'paused'` with:
   - Live pulsing badge
   - Progress percentage
   - "Click to monitor" action
3. Completed crawls remain in the existing grouped-by-domain layout below

## File Impact Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `main.py` | Modify | New endpoints, recovery logic, cleanup adjustment |
| `src/crawl_db.py` | Modify | New query `get_user_active_crawls()` |
| `src/crawler.py` | Minor verify | Ensure `resume_from_database()` is robust |
| `web/static/js/app.js` | Modify | Auto-reconnect banner in `initializeApp()` |
| `web/static/js/dashboard.js` | Modify | Active crawls section |
| `web/templates/dashboard.html` | Minor | CSS for active crawl section styling |

## Out of Scope

- Separate worker process / task queue (Celery, Redis) — not needed for single-server team use
- Server-side sessions — current client-side sessions are sufficient
- Auth changes — team shares same server, existing auth model works
- Multi-device crawl triggering — already works since all devices hit same server
- Database migration — schema already supports all needed queries

## Risks

1. **Server restart during active crawl:** `recover_crashed_crawls()` will auto-resume, but there's a brief window where crawl data between last save and crash is lost (max 30 seconds of data)
2. **Memory pressure:** Multiple recovered crawls on startup could consume significant memory — mitigate by limiting concurrent crawl recovery
3. **Resume failure:** If `resume_from_database()` fails (corrupted state), crawl is marked `failed` with a clear error message — user can manually retry from dashboard

## Success Criteria

1. Start a crawl → close browser → reopen → see crawl status (running/completed)
2. Start a crawl → close browser → reopen from different device → see crawl status
3. Server restart → active crawls auto-recover → dashboard shows them
4. Dashboard prominently shows active crawls at top
5. Any team member can view any crawl's results (shared team context)
