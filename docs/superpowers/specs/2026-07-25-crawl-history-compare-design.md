# Crawl History & Compare Design

## Goal

Replace file-based save/load with database-backed crawl history, organized by domain. Users can see all past crawls per domain, compare two crawls with detailed issue diffs, and load any previous crawl from the main UI.

## Summary

- **Domain as key**: crawls grouped by `base_domain` (e.g., `avonetiq.com`)
- **History per domain**: all runs listed chronologically with stats (URLs crawled, issues count, duration)
- **Compare mode**: select 2 crawls → dedicated compare page with per-category issue diff (FIXED / STILL / NEW)
- **DB-backed save/load**: Save button saves to DB, Load button opens domain history picker. No file download/upload.

## Backend

### 1. DB Migration — add `crawl_name` column

```sql
ALTER TABLE crawls ADD COLUMN crawl_name TEXT DEFAULT NULL;
```

- Default: `base_domain` (fallback if null)
- User can set a custom name when saving

### 2. New API: `GET /api/crawls/history`

Returns crawls grouped by domain.

```
Response:
{
  "success": true,
  "domains": [
    {
      "domain": "avonetiq.com",
      "crawl_count": 3,
      "crawls": [
        {
          "id": 12,
          "crawl_name": "avonetiq.com",
          "base_url": "https://avonetiq.com",
          "status": "completed",
          "started_at": "2026-07-25T14:30:00",
          "completed_at": "2026-07-25T14:32:30",
          "urls_crawled": 45,
          "issues_count": 12
        }
      ]
    }
  ]
}
```

Implementation: query `crawls` table grouped by `base_domain`, LEFT JOIN `crawl_issues` to get counts.

### 3. New API: `GET /api/crawls/compare?ids=1,2`

Compare two crawls with detailed issue diff.

```
Response:
{
  "success": true,
  "crawl_a": { "id": 12, "crawl_name": "...", "started_at": "...", "urls_crawled": 45 },
  "crawl_b": { "id": 10, "crawl_name": "...", "started_at": "...", "urls_crawled": 38 },
  "summary": {
    "total_issues_a": 12,
    "total_issues_b": 18,
    "fixed": 6,
    "still": 11,
    "new": 1
  },
  "categories": [
    {
      "category": "broken_links",
      "label": "Broken Links",
      "count_a": 3,
      "count_b": 5,
      "diff": -2,
      "items": [
        { "url": "/old-page", "issue": "404 Not Found", "status": "fixed", "details_a": null, "details_b": "404" },
        { "url": "/missing-img", "issue": "Image not found", "status": "fixed", ... },
        { "url": "/broken-form", "issue": "404 Not Found", "status": "still", ... },
        { "url": "/old-blog/5", "issue": "404 Not Found", "status": "still", ... },
        { "url": "/deprecated", "issue": "404 Not Found", "status": "still", ... }
      ]
    },
    {
      "category": "missing_meta",
      "label": "Missing Meta Description",
      "count_a": 2,
      "count_b": 3,
      "diff": -1,
      "items": [
        { "url": "/about", "issue": "Missing meta description", "status": "fixed", ... },
        { "url": "/contact", "issue": "Missing meta description", "status": "still", ... },
        { "url": "/pricing", "issue": "Missing meta description", "status": "still", ... }
      ]
    },
    {
      "category": "new_issues",
      "label": "New Issues (regression)",
      "count_a": 1,
      "count_b": 0,
      "diff": 1,
      "items": [
        { "url": "/api/docs", "issue": "Missing canonical", "status": "new", ... }
      ]
    }
  ]
}
```

Logic per item:
- `fixed` — in crawl_b but not in crawl_a (improved)
- `still` — in both crawls (unchanged)
- `new` — in crawl_a but not in crawl_b (regression)

Match key: `category + url + issue` (same issue on same URL)

### 4. New API: `POST /api/crawls/<id>/save-name`

Update crawl name:
```json
{ "crawl_name": "After fixing meta tags" }
```

### 5. Update `GET /api/crawls/list`

Add `issues_count` and `base_domain` to each crawl entry.

### 6. Update `POST /api/crawls/<id>/load`

No change needed — already loads from DB.

### 7. Update main.py crawl start

When crawl completes, auto-set `crawl_name` to `base_domain` if not set.

## Frontend

### 1. Dashboard — Domain Sidebar + Crawl Detail

Layout:
```
┌──────────────┬─────────────────────────────────────┐
│  DOMAINS     │  Domain header + stats              │
│  (sidebar)   │                                     │
│              │  Crawl list (chronological)          │
│  ▸ avonetiq  │  Each crawl: date, status, URLs,    │
│    3 crawls  │  issues, duration, actions           │
│              │                                     │
│  ▸ example   │  [Load] [Compare] [Rename] [Delete] │
│    1 crawl   │                                     │
│              │  Compare mode: checkbox on 2 crawls  │
│              │  → "Compare Selected" button         │
└──────────────┴─────────────────────────────────────┘
```

- Sidebar: list of domains, click to filter
- Right panel: crawls for selected domain, sorted by date desc
- Each crawl row: date, status badge, URLs crawled, issues count, duration
- Actions: Load, Compare (checkbox), Rename (inline edit), Delete
- Compare: check 2 crawls → "Compare Selected" button appears → navigates to compare page

### 2. Compare Page — `/compare?id_a=12&id_b=10`

Full-page dedicated view:

- Header: domain name, both crawl dates/stats
- Summary bar: total issues A vs B, ↓ improved / ↑ regression
- Per-category expandable sections:
  - Category name + count diff
  - Expandable list of items with status icons:
    - ✅ FIXED — was in old, gone in new
    - ➖ STILL — same in both
    - 🆕 NEW — only in new (regression)
  - Each item shows: URL, issue description

### 3. Main UI — Save/Load Buttons

**Save button** → Modal:
- Input field: crawl name (pre-filled with domain)
- "Save" button → POST to save name to DB
- Shows confirmation toast

**Load button** → Modal:
- Shows domain history list (same as Dashboard right panel)
- Click a crawl → loads it into current session
- No file download/upload

## Files to Modify

| File | Change |
|------|--------|
| `src/crawl_db.py` | Add `crawl_name` migration, `get_crawl_history()`, `compare_crawls()`, `update_crawl_name()` |
| `main.py` | Add `/api/crawls/history`, `/api/crawls/compare`, `/api/crawls/<id>/save-name` routes; update `/api/crawls/list` |
| `web/templates/dashboard.html` | Rewrite to sidebar+detail layout |
| `web/static/js/dashboard.js` | Rewrite for domain sidebar, crawl list, compare selection |
| `web/static/js/app.js` | Replace saveCrawl() and loadCrawl() with DB-backed modals |
| `web/templates/compare.html` | New page for compare detail view |
| `web/static/js/compare.js` | New JS for compare page |

## Out of Scope

- File export/import (removed, not needed)
- Real-time crawl comparison (only compare completed crawls)
- Historical trend charts (future enhancement)
