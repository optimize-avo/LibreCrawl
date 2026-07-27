# Background Crawl — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable crawls to survive browser close/navigation so users can fire-and-forget a crawl, close their laptop, and later see results (still running or completed) from any device.

**Architecture:** Server-side crawl threads already survive browser disconnection. The gap is (1) startup recovery auto-resumes instead of failing, (2) API endpoints let any session discover and attach to active crawls, (3) frontend auto-detects active crawls on page load and shows a reconnect banner.

**Tech Stack:** Python 3.11+, Flask, SQLite, vanilla JS (no framework)

## Global Constraints

- No new dependencies — use only existing Flask, SQLite, threading
- No database migration — schema already supports needed queries
- No auth changes — team uses shared server with existing auth model
- Follow existing code patterns (large-file style, no restructuring)
- Branch: `background-crawl`

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `src/crawl_db.py` | Modify | Add `get_user_active_crawls(user_id)` query |
| `main.py` | Modify | New endpoints, recovery logic, cleanup adjustment |
| `web/static/js/app.js` | Modify | Auto-reconnect banner on page load |
| `web/static/js/dashboard.js` | Modify | Active crawls section at top of dashboard |
| `web/templates/dashboard.html` | Modify | CSS for active crawl banner/badge |

---

### Task 1: Backend — DB Query for Active Crawls

**Files:**
- Modify: `src/crawl_db.py:628` (after `get_crashed_crawls`)

**Interfaces:**
- Consumes: existing `get_db()` context manager, SQLite `crawls` table
- Produces: `get_user_active_crawls(user_id)` → returns `list[dict]`

- [ ] **Step 1: Add `get_user_active_crawls` function**

After the `get_crashed_crawls` function (line 628), add:

```python
def get_user_active_crawls(user_id):
    """Get crawls that are currently running or paused for a user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, base_url, base_domain, status, started_at,
                       urls_discovered, max_depth_reached
                FROM crawls
                WHERE user_id = ? AND status IN ('running', 'paused')
                ORDER BY started_at DESC
            ''', (user_id,))

            crawls = []
            for row in cursor.fetchall():
                crawl = dict(row)
                # Get crawled count from crawled_urls table
                cursor.execute('''
                    SELECT COUNT(*) FROM crawled_urls WHERE crawl_id = ?
                ''', (crawl['id'],))
                crawl['urls_crawled'] = cursor.fetchone()[0]

                # Calculate progress
                discovered = crawl.get('urls_discovered') or 1
                crawled = crawl.get('urls_crawled') or 0
                crawl['progress_percent'] = min(100, round((crawled / discovered) * 100)) if discovered > 0 else 0

                crawls.append(crawl)

            return crawls

    except Exception as e:
        print(f"Error finding active crawls: {e}")
        return []
```

- [ ] **Step 2: Verify existing `get_crashed_crawls` still works**

Run: `python -c "from src.crawl_db import get_user_active_crawls; print('import ok')"`
Expected: `import ok`

- [ ] **Step 3: Commit**

```bash
git add src/crawl_db.py
git commit -m "feat(crawl_db): add get_user_active_crawls query for background crawl reconnect"
```

---

### Task 2: Backend — New API Endpoints

**Files:**
- Modify: `main.py:1093` (after `list_crawls` endpoint)
- Modify: `main.py:1110` (after `crawl_history` endpoint)

**Interfaces:**
- Consumes: `get_user_active_crawls(user_id)` from Task 1, existing `crawler_instances` dict, `WebCrawler.resume_from_database()`
- Produces: `GET /api/my_active_crawls`, `POST /api/crawls/<id>/reconnect`

- [ ] **Step 1: Add `GET /api/my_active_crawls` endpoint**

After the `list_crawls` endpoint (after line 1093), add:

```python
@app.route('/api/my_active_crawls')
@login_required
def my_active_crawls():
    """Get active (running/paused) crawls for the current user"""
    try:
        user_id = session.get('user_id')
        from src.crawl_db import get_user_active_crawls

        crawls = get_user_active_crawls(user_id)

        return jsonify({
            'success': True,
            'crawls': crawls
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'crawls': []})
```

- [ ] **Step 2: Add `POST /api/crawls/<id>/reconnect` endpoint**

After the `crawl_history` endpoint (after line 1110), add:

```python
@app.route('/api/crawls/<int:crawl_id>/reconnect', methods=['POST'])
@login_required
def reconnect_crawl(crawl_id):
    """Reconnect to an active crawl — bind it to the current session"""
    try:
        user_id = session.get('user_id')
        from src.crawl_db import get_crawl_by_id

        # Verify crawl exists and is active
        crawl_info = get_crawl_by_id(crawl_id)
        if not crawl_info:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404

        if crawl_info.get('status') not in ('running', 'paused'):
            return jsonify({'success': False, 'error': f'Crawl is {crawl_info.get("status")}, cannot reconnect'}), 400

        # Check if crawler instance already exists in memory (any session)
        with instances_lock:
            for sid, instance_data in crawler_instances.items():
                crawler = instance_data['crawler']
                if crawler.crawl_id == crawl_id:
                    # Found in-memory instance — bind to current session
                    session_id = session.get('session_id')
                    if not session_id:
                        session['session_id'] = str(uuid.uuid4())
                        session_id = session['session_id']

                    # Move to current session if not already there
                    if sid != session_id:
                        instance_data['last_accessed'] = datetime.now()
                        crawler_instances[session_id] = instance_data
                        print(f"Rebound crawl {crawl_id} from session {sid} to {session_id}")

                    instance_data['last_accessed'] = datetime.now()

                    # Load existing data for initial response
                    status_data = crawler.get_status()
                    return jsonify({
                        'success': True,
                        'message': 'Reconnected to active crawl',
                        'status': crawler_info_to_response(crawl_info, status_data)
                    })

        # Not in memory — resume from database
        crawler = get_or_create_crawler()
        success, message = crawler.resume_from_database(crawl_id, user_id=user_id)

        if success:
            return jsonify({
                'success': True,
                'message': message,
                'status': crawler.get_status()
            })
        else:
            return jsonify({'success': False, 'error': message}), 400

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def crawler_info_to_response(crawl_info, status_data=None):
    """Format crawl info for reconnect response"""
    response = {
        'crawl_id': crawl_info.get('id'),
        'base_url': crawl_info.get('base_url'),
        'base_domain': crawl_info.get('base_domain'),
        'status': crawl_info.get('status'),
        'urls_crawled': status_data.get('stats', {}).get('crawled', 0) if status_data else 0,
        'urls_queued': status_data.get('stats', {}).get('discovered', 0) if status_data else 0,
        'progress_percent': 0,
    }
    discovered = response['urls_queued'] or 1
    crawled = response['urls_crawled'] or 0
    response['progress_percent'] = min(100, round((crawled / discovered) * 100)) if discovered > 0 else 0
    return response
```

- [ ] **Step 3: Verify server starts without errors**

Run: `python -c "from main import app; print('routes ok')"`
Expected: No import errors, `routes ok`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(api): add my_active_crawls and reconnect endpoints for background crawl"
```

---

### Task 3: Backend — Startup Recovery Auto-Resume

**Files:**
- Modify: `main.py:1508-1528` (`recover_crashed_crawls` function)

**Interfaces:**
- Consumes: existing `get_crashed_crawls()`, `WebCrawler.resume_from_database()`, `crawler_instances` dict
- Produces: Auto-recovered crawls running in background

- [ ] **Step 1: Rewrite `recover_crashed_crawls` to auto-resume**

Replace the entire `recover_crashed_crawls` function (lines 1508-1528) with:

```python
def recover_crashed_crawls():
    """Auto-resume any crawls that were running when server shut down"""
    try:
        from src.crawl_db import get_crashed_crawls, set_crawl_status, fix_stopped_to_completed

        # Fix old crawls affected by the stopped-vs-completed bug
        fix_stopped_to_completed()

        crashed = get_crashed_crawls()

        if crashed:
            print("\n" + "=" * 60)
            print("CRASH RECOVERY — Auto-resuming active crawls")
            print("=" * 60)
            recovered_count = 0
            for crawl in crashed:
                try:
                    crawler = WebCrawler()
                    success, message = crawler.resume_from_database(
                        crawl['id'],
                        user_id=crawl.get('user_id'),
                        session_id=crawl.get('session_id')
                    )
                    if success:
                        # Store under a recovered key so it's accessible
                        recovered_key = f"recovered_{crawl['id']}"
                        with instances_lock:
                            instances_lock  # ensure lock exists
                        recovered_key = f"recovered_{crawl['id']}"
                        with instances_lock:
                            from datetime import datetime
                            instances_lock  # just checking it exists
                        # Use a simpler approach — store in crawler_instances
                        recovered_key = f"recovered_{crawl['id']}"
                        with instances_lock:
                            crawler_instances[recovered_key] = {
                                'crawler': crawler,
                                'settings': None,
                                'last_accessed': datetime.now()
                            }
                        recovered_count += 1
                        print(f"  ✅ Resumed: {crawl['base_url']} (ID: {crawl['id']}) — {message}")
                    else:
                        set_crawl_status(crawl['id'], 'failed')
                        print(f"  ❌ Failed to resume: {crawl['base_url']} (ID: {crawl['id']}) — {message}")
                except Exception as e:
                    set_crawl_status(crawl['id'], 'failed')
                    print(f"  ❌ Error resuming: {crawl['base_url']} (ID: {crawl['id']}) — {e}")

            print(f"\n  Recovered {recovered_count}/{len(crashed)} crawls")
            print("=" * 60 + "\n")
    except Exception as e:
        print(f"Error during crash recovery: {e}")
```

- [ ] **Step 2: Fix the redundant lock issue — clean up the function**

Actually, let me provide the clean version. Replace lines 1508-1528 with:

```python
def recover_crashed_crawls():
    """Auto-resume any crawls that were running when server shut down"""
    try:
        from src.crawl_db import get_crashed_crawls, set_crawl_status, fix_stopped_to_completed

        # Fix old crawls affected by the stopped-vs-completed bug
        fix_stopped_to_completed()

        crashed = get_crashed_crawls()

        if crashed:
            print("\n" + "=" * 60)
            print("CRASH RECOVERY — Auto-resuming active crawls")
            print("=" * 60)
            recovered_count = 0
            for crawl in crashed:
                try:
                    crawler = WebCrawler()
                    success, message = crawler.resume_from_database(
                        crawl['id'],
                        user_id=crawl.get('user_id'),
                        session_id=crawl.get('session_id')
                    )
                    if success:
                        recovered_key = f"recovered_{crawl['id']}"
                        with instances_lock:
                            crawler_instances[recovered_key] = {
                                'crawler': crawler,
                                'settings': None,
                                'last_accessed': datetime.now()
                            }
                        recovered_count += 1
                        print(f"  Resumed: {crawl['base_url']} (ID: {crawl['id']}) - {message}")
                    else:
                        set_crawl_status(crawl['id'], 'failed')
                        print(f"  Failed to resume: {crawl['base_url']} (ID: {crawl['id']}) - {message}")
                except Exception as e:
                    set_crawl_status(crawl['id'], 'failed')
                    print(f"  Error resuming: {crawl['base_url']} (ID: {crawl['id']}) - {e}")

            print(f"\n  Recovered {recovered_count}/{len(crashed)} crawls")
            print("=" * 60 + "\n")
    except Exception as e:
        print(f"Error during crash recovery: {e}")
```

- [ ] **Step 3: Verify server starts without errors**

Run: `python -c "from main import recover_crashed_crawls; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(recovery): auto-resume running crawls on server startup instead of marking failed"
```

---

### Task 4: Backend — Cleanup Thread: Don't Stop Crawls

**Files:**
- Modify: `main.py:287-308` (`cleanup_old_instances` function)

**Interfaces:**
- Consumes: existing `crawler_instances` dict
- Produces: Memory cleanup without stopping crawl threads

- [ ] **Step 1: Modify `cleanup_old_instances` to not call `stop_crawl()`**

Replace lines 287-308 with:

```python
def cleanup_old_instances():
    """Remove in-memory crawler instances that haven't been accessed in 1 hour.

    Crawls continue running even after the in-memory instance is removed.
    Data is persisted to DB and can be resumed later.
    """
    timeout = timedelta(hours=1)
    now = datetime.now()

    with instances_lock:
        sessions_to_remove = []
        for session_id, instance_data in crawler_instances.items():
            if now - instance_data['last_accessed'] > timeout:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            instance = crawler_instances[session_id]
            crawler = instance['crawler']
            # Only remove if the crawl is NOT currently running
            if crawler.is_running:
                # Skip — crawl is active, keep it in memory
                print(f"Keeping active crawl in memory: session {session_id} (crawl {crawler.crawl_id})")
                continue

            print(f"Cleaning up idle crawler instance for session: {session_id}")
            del crawler_instances[session_id]

        if sessions_to_remove:
            active_kept = sum(1 for s in sessions_to_remove
                            if crawler_instances.get(s, {}).get('crawler', WebCrawler()).is_running)
            removed = len(sessions_to_remove) - active_kept
            print(f"Cleaned up {removed} inactive crawler instances ({active_kept} active crawls kept)")
```

- [ ] **Step 2: Verify cleanup logic**

Run: `python -c "from main import cleanup_old_instances; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "fix(cleanup): don't stop crawl threads during idle instance cleanup"
```

---

### Task 5: Frontend — Auto-Reconnect Banner on Main Page

**Files:**
- Modify: `web/static/js/app.js:49-133` (`initializeApp` function)

**Interfaces:**
- Consumes: `GET /api/my_active_crawls` (from Task 2), existing `pollCrawlProgress()` and `crawlState`
- Produces: Banner UI element, auto-reconnect flow

- [ ] **Step 1: Add reconnect banner HTML container**

In `web/templates/index.html`, find the section after the URL input area and before the results area. Add a banner container. Find the `urlInputContainer` or equivalent and add after it:

```html
<!-- Background Crawl Reconnect Banner -->
<div id="reconnectBanner" style="display:none; background: linear-gradient(135deg, #1e40af, #3b82f6); color: white; padding: 12px 20px; border-radius: 10px; margin-bottom: 16px; display: none; align-items: center; justify-content: space-between; cursor: pointer; transition: all 0.2s;" onclick="reconnectToCrawl()">
    <div style="display: flex; align-items: center; gap: 12px;">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: #4ade80; animation: pulse 2s infinite;"></div>
        <div>
            <div id="reconnectBannerText" style="font-weight: 600; font-size: 14px;">Crawl sedang berjalan</div>
            <div id="reconnectBannerDetail" style="font-size: 12px; opacity: 0.85; margin-top: 2px;">Loading...</div>
        </div>
    </div>
    <div style="font-size: 13px; opacity: 0.8;">Click to reconnect →</div>
</div>
<style>
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
</style>
```

- [ ] **Step 2: Add `checkActiveCrawls` and `reconnectToCrawl` functions to app.js**

At the end of `initializeApp()` (before the `document.getElementById('urlInput').focus()` line, around line 132), add:

```javascript
    // Check for active background crawls
    checkActiveCrawls();
```

Then add these new functions at the end of app.js:

```javascript
// ========================================
// Background Crawl Reconnection
// ========================================

let activeCrawlReconnectId = null;

async function checkActiveCrawls() {
    try {
        const response = await fetch('/api/my_active_crawls');
        const data = await response.json();

        if (data.success && data.crawls && data.crawls.length > 0) {
            const crawl = data.crawls[0]; // Show first active crawl
            showReconnectBanner(crawl);
        }
    } catch (error) {
        console.log('No active crawls or error checking:', error);
    }
}

function showReconnectBanner(crawl) {
    const banner = document.getElementById('reconnectBanner');
    if (!banner) return;

    activeCrawlReconnectId = crawl.id;

    const text = document.getElementById('reconnectBannerText');
    const detail = document.getElementById('reconnectBannerDetail');

    if (text) text.textContent = `${crawl.base_url} sedang dicrawl`;
    if (detail) {
        const pct = crawl.progress_percent || 0;
        const crawled = crawl.urls_crawled || 0;
        const discovered = crawl.urls_discovered || 0;
        detail.textContent = `${pct}% — ${crawled}/${discovered} URLs`;
    }

    banner.style.display = 'flex';
}

async function reconnectToCrawl() {
    if (!activeCrawlReconnectId) return;

    try {
        const response = await fetch(`/api/crawls/${activeCrawlReconnectId}/reconnect`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            // Hide banner
            const banner = document.getElementById('reconnectBanner');
            if (banner) banner.style.display = 'none';

            // Load crawl data into UI
            clearAllTables();
            resetStats();

            crawlState.urls = [];
            crawlState.baseUrl = data.status?.base_url || '';

            if (crawlState.baseUrl) {
                document.getElementById('urlInput').value = crawlState.baseUrl;
            }

            // Start polling for live updates
            if (data.status?.status === 'running') {
                crawlState.isRunning = true;
                crawlState.isPaused = false;
                crawlState.startTime = new Date();
                showProgress();
                updateCrawlButtons();
                updateStatus('Reconnected to background crawl — updating...');
                pollCrawlProgress();
            } else if (data.status?.status === 'paused') {
                crawlState.isRunning = true;
                crawlState.isPaused = true;
                showProgress();
                updateCrawlButtons();
                updateStatus('Crawl is paused — click Resume to continue');
            } else {
                // Completed — load full data
                updateStatus(`Loaded: ${data.status?.urls_crawled || 0} URLs`);
                // Fetch full crawl data
                const statusResp = await fetch('/api/crawl_status');
                const statusData = await statusResp.json();
                if (statusData.urls) {
                    statusData.urls.forEach(url => addUrlToTable(url));
                }
                crawlState.links = statusData.links || [];
                crawlState.issues = statusData.issues || [];
                crawlState.stats = statusData.stats || {};
                updateStatsDisplay();
                updateFilterCounts();
                updateStatusCodesTable();
            }
        } else {
            updateStatus('Failed to reconnect: ' + (data.error || 'Unknown error'));
        }
    } catch (error) {
        console.error('Reconnect error:', error);
        updateStatus('Error reconnecting to crawl');
    }
}
```

- [ ] **Step 3: Verify no JS syntax errors**

Run: `node -c web/static/js/app.js`
Expected: No output (syntax OK)

- [ ] **Step 4: Commit**

```bash
git add web/static/js/app.js web/templates/index.html
git commit -m "feat(frontend): auto-detect and show reconnect banner for active background crawls"
```

---

### Task 6: Frontend — Dashboard Active Crawl Section

**Files:**
- Modify: `web/static/js/dashboard.js:11-38` (`loadDashboard` function)
- Modify: `web/templates/dashboard.html` (add CSS for active crawl section)

**Interfaces:**
- Consumes: `GET /api/my_active_crawls` (from Task 2), existing `selectDomain()` flow
- Produces: Active crawl banner at top of dashboard

- [ ] **Step 1: Add active crawls section to dashboard.js**

In `loadDashboard()` (line 11), after fetching history data, also fetch active crawls. Modify the function:

```javascript
async function loadDashboard() {
    try {
        // Fetch active crawls and history in parallel
        const [historyResponse, activeResponse] = await Promise.all([
            fetch('/api/crawls/history'),
            fetch('/api/my_active_crawls').catch(() => ({ json: () => ({ success: false, crawls: [] }) }))
        ]);

        const data = await historyResponse.json();
        const activeData = await activeResponse.json();

        if (!data.success) {
            console.error('Failed to load history:', data.error);
            return;
        }

        allDomains = data.domains || [];
        renderDomainSidebar();
        renderActiveCrawls(activeData.crawls || []);

        // Auto-select first domain if none selected, or refresh if one is already selected
        if (allDomains.length > 0) {
            if (!selectedDomain || !allDomains.find(d => d.domain === selectedDomain)) {
                selectDomain(allDomains[0].domain);
            } else {
                renderCrawlDetail();
            }
        } else {
            selectedDomain = null;
            renderCrawlDetailEmpty();
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

function renderActiveCrawls(crawls) {
    const container = document.getElementById('activeCrawlsSection');
    if (!container) return;

    if (crawls.length === 0) {
        container.style.display = 'none';
        return;
    }

    container.style.display = 'block';
    container.innerHTML = `
        <div class="active-crawls-header">
            <div class="active-crawls-pulse"></div>
            <span>Active Crawls</span>
        </div>
        <div class="active-crawls-list">
            ${crawls.map(crawl => `
                <div class="active-crawl-item" onclick="openActiveCrawl(${crawl.id})">
                    <div class="active-crawl-info">
                        <div class="active-crawl-url">${crawl.base_url}</div>
                        <div class="active-crawl-status">${crawl.status === 'running' ? 'Crawling...' : 'Paused'}</div>
                    </div>
                    <div class="active-crawl-progress">
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${crawl.progress_percent}%"></div>
                        </div>
                        <span class="progress-text">${crawl.progress_percent}%</span>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

function openActiveCrawl(crawlId) {
    sessionStorage.setItem('force_ui_refresh', 'true');
    sessionStorage.setItem('reconnect_crawl_id', crawlId);
    window.location.href = '/';
}
```

- [ ] **Step 2: Add `activeCrawlsSection` container to dashboard.html**

In `web/templates/dashboard.html`, add the container div at the top of the dashboard content area (before the domain sidebar). Find the main content area and add:

```html
<!-- Active Crawl Section -->
<div id="activeCrawlsSection" style="display:none; margin-bottom: 20px;"></div>
```

- [ ] **Step 3: Add CSS for active crawl section**

In `web/templates/dashboard.html`, add styles in the `<style>` block:

```css
.active-crawls-header {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--fg);
    margin-bottom: 10px;
}
.active-crawls-pulse {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #4ade80;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
.active-crawls-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.active-crawl-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    cursor: pointer;
    transition: border-color 0.2s;
}
.active-crawl-item:hover {
    border-color: #3b82f6;
}
.active-crawl-url {
    font-weight: 600;
    font-size: 14px;
    color: var(--fg);
}
.active-crawl-status {
    font-size: 12px;
    color: var(--fg-muted);
    margin-top: 2px;
}
.active-crawl-progress {
    display: flex;
    align-items: center;
    gap: 10px;
}
.progress-bar {
    width: 100px;
    height: 6px;
    background: var(--bg-muted);
    border-radius: 3px;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #60a5fa);
    border-radius: 3px;
    transition: width 0.3s ease;
}
.progress-text {
    font-size: 13px;
    font-weight: 600;
    color: var(--fg);
    min-width: 36px;
}
```

- [ ] **Step 4: Verify no JS syntax errors**

Run: `node -c web/static/js/dashboard.js`
Expected: No output (syntax OK)

- [ ] **Step 5: Commit**

```bash
git add web/static/js/dashboard.js web/templates/dashboard.html
git commit -m "feat(dashboard): show active crawls section at top of dashboard with live progress"
```

---

### Task 7: Frontend — Support `reconnect_crawl_id` in initializeApp

**Files:**
- Modify: `web/static/js/app.js:49-133` (`initializeApp` function)

**Interfaces:**
- Consumes: existing `reconnectToCrawl()` from Task 5, `sessionStorage.reconnect_crawl_id`
- Produces: Auto-reconnect when navigating from dashboard

- [ ] **Step 1: Add reconnect_crawl_id handling to initializeApp**

Inside the `force_ui_refresh` block in `initializeApp()` (around line 66), after `sessionStorage.removeItem('force_ui_refresh')`, add reconnect support:

Replace the existing block starting at line 66:

```javascript
    // Check if we just opened a crawl from dashboard
    if (sessionStorage.getItem('force_ui_refresh') === 'true') {
        sessionStorage.removeItem('force_ui_refresh');

        // Check if we should reconnect to a specific crawl
        const reconnectId = sessionStorage.getItem('reconnect_crawl_id');
        if (reconnectId) {
            sessionStorage.removeItem('reconnect_crawl_id');
            activeCrawlReconnectId = parseInt(reconnectId);
            await reconnectToCrawl();
            return;
        }

        try {
```

The rest of the existing try/catch block stays unchanged.

- [ ] **Step 2: Verify no JS syntax errors**

Run: `node -c web/static/js/app.js`
Expected: No output (syntax OK)

- [ ] **Step 3: Commit**

```bash
git add web/static/js/app.js
git commit -m "feat(frontend): support reconnect_crawl_id for dashboard-to-main-page navigation"
```

---

### Task 8: Smoke Test & Manual Verification

**Files:** None (verification only)

- [ ] **Step 1: Start server and verify basic functionality**

```bash
python main.py --local &
sleep 3
# Verify server starts without errors
curl -s http://localhost:5001/ | head -5
```

- [ ] **Step 2: Verify new endpoints exist**

```bash
# Check active crawls endpoint returns valid JSON (even if empty)
curl -s http://localhost:5001/api/my_active_crawls | python3 -c "import sys,json; d=json.load(sys.stdin); print('Active crawls:', d.get('crawls', []))"
```

- [ ] **Step 3: Start a crawl and verify it survives page navigation**

```bash
# Start a crawl via API
curl -s -X POST http://localhost:5001/api/start_crawl -H "Content-Type: application/json" -d '{"url": "https://example.com"}'
# Wait a few seconds
sleep 5
# Check it's in the active crawls list
curl -s http://localhost:5001/api/my_active_crawls | python3 -c "import sys,json; d=json.load(sys.stdin); print('Active:', len(d.get('crawls', [])), 'crawls')"
```

- [ ] **Step 4: Kill and restart server — verify recovery**

```bash
# Kill server
pkill -f "python main.py"
sleep 2
# Restart
python main.py --local &
sleep 3
# Check logs for "CRASH RECOVERY — Auto-resuming active crawls"
# Verify crawl is auto-recovered
```

- [ ] **Step 5: Stop test server**

```bash
pkill -f "python main.py"
```

- [ ] **Step 6: Final commit — all changes on background-crawl branch**

```bash
git status
# Verify all files are committed
git log --oneline -10
```

---

## Verification Summary

After implementation, verify these scenarios manually:

1. **Start crawl → close browser → reopen → see banner** ✅
2. **Start crawl → kill server → restart → crawl auto-resumes** ✅
3. **Dashboard shows active crawls at top** ✅
4. **Click active crawl on dashboard → reconnect on main page** ✅
5. **Crawl finishes while user is away → results available on next visit** ✅
