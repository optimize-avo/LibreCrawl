# Crawl History & Compare Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace file-based save/load with database-backed crawl history organized by domain, with a dedicated compare page showing per-issue diffs.

**Architecture:** Backend adds 3 new API endpoints + DB query functions. Frontend gets a redesigned Dashboard (domain sidebar + crawl detail), a new Compare page, and DB-backed Save/Load modals in the main UI.

**Tech Stack:** Python Flask, SQLite, vanilla JS, Tailwind CSS (via tw.css)

## Global Constraints

- SQLite database at `data/users.db` — no new database engines
- Existing `crawl_db.py` patterns: context manager `get_db()`, `sqlite3.Row` factory
- Existing UI patterns: Tailwind utility classes, `var(--token)` CSS variables, `_rail.html` + `_topbar.html` partials
- No new npm dependencies — vanilla JS only
- Branch: `db-migration`

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/crawl_db.py` | Modify | Add `crawl_name` migration, `get_crawl_history()`, `compare_crawls()`, `update_crawl_name()`, `get_crawl_issues_count()` |
| `main.py` | Modify | Add `/api/crawls/history`, `/api/crawls/compare`, `/api/crawls/<id>/save-name` routes; update `/api/crawls/list` to include `issues_count` |
| `web/templates/dashboard.html` | Rewrite | Domain sidebar + crawl detail layout |
| `web/static/js/dashboard.js` | Rewrite | Domain sidebar logic, crawl list, compare selection |
| `web/templates/compare.html` | Create | Dedicated compare page |
| `web/static/js/compare.js` | Create | Compare page logic |
| `web/static/js/app.js` | Modify | Replace `saveCrawl()` and `loadCrawl()` with DB-backed modals |
| `web/templates/partials/_topbar.html` | Modify | Update Save/Load button onclick handlers |

---

### Task 1: Backend — crawl_db.py new functions

**Files:**
- Modify: `src/crawl_db.py`

**Interfaces:**
- Produces: `get_crawl_history()`, `compare_crawls(id_a, id_b)`, `update_crawl_name(crawl_id, name)`, `get_crawl_issues_count(crawl_id)`

- [ ] **Step 1: Add crawl_name migration to init_crawl_tables()**

In `src/crawl_db.py`, inside `init_crawl_tables()`, after the existing migration block (line ~118), add:

```python
        # Migration: add crawl_name column to existing crawls tables
        try:
            cursor.execute('ALTER TABLE crawls ADD COLUMN crawl_name TEXT DEFAULT NULL')
        except sqlite3.OperationalError:
            pass  # Column already exists
```

- [ ] **Step 2: Add get_crawl_history() function**

Add after `get_crawl_count()` (after line 646):

```python
def get_crawl_history(user_id=None):
    """
    Get crawls grouped by base_domain with issue counts.
    Returns list of domain groups, each with a list of crawls.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT
                    c.id, c.crawl_name, c.base_url, c.base_domain, c.status,
                    c.started_at, c.completed_at, c.urls_crawled,
                    c.user_id,
                    COUNT(DISTINCT ci.id) as issues_count
                FROM crawls c
                LEFT JOIN crawl_issues ci ON ci.crawl_id = c.id
            '''
            params = []
            if user_id:
                query += ' WHERE c.user_id = ?'
                params.append(user_id)
            query += ' GROUP BY c.id ORDER BY c.base_domain, c.started_at DESC'

            cursor.execute(query, params)
            rows = [dict(row) for row in cursor.fetchall()]

            # Group by domain
            domains = {}
            for row in rows:
                domain = row['base_domain'] or 'unknown'
                if domain not in domains:
                    domains[domain] = {
                        'domain': domain,
                        'crawl_count': 0,
                        'crawls': []
                    }
                # Use crawl_name or fallback to domain
                row['display_name'] = row['crawl_name'] or domain
                domains[domain]['crawls'].append(row)
                domains[domain]['crawl_count'] += 1

            # Sort domains alphabetically
            result = sorted(domains.values(), key=lambda d: d['domain'])
            return result

    except Exception as e:
        print(f"Error getting crawl history: {e}")
        return []
```

- [ ] **Step 3: Add compare_crawls() function**

Add after `get_crawl_history()`:

```python
def compare_crawls(crawl_id_a, crawl_id_b):
    """
    Compare two crawls and return detailed issue diff.
    Returns crawl metadata for both + categories with FIXED/STILL/NEW items.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Get crawl metadata
            cursor.execute('SELECT * FROM crawls WHERE id IN (?, ?)', (crawl_id_a, crawl_id_b))
            crawls = {row['id']: dict(row) for row in cursor.fetchall()}

            if len(crawls) < 2:
                return None

            crawl_a = crawls.get(crawl_id_a)
            crawl_b = crawls.get(crawl_id_b)

            # Get issues for both crawls
            cursor.execute('SELECT * FROM crawl_issues WHERE crawl_id = ?', (crawl_id_a,))
            issues_a = [dict(row) for row in cursor.fetchall()]

            cursor.execute('SELECT * FROM crawl_issues WHERE crawl_id = ?', (crawl_id_b,))
            issues_b = [dict(row) for row in cursor.fetchall()]

            # Build lookup: (category, url, issue) -> issue data
            def issue_key(issue):
                return (issue.get('category') or '', issue.get('url') or '', issue.get('issue') or '')

            keys_a = {issue_key(i): i for i in issues_a}
            keys_b = {issue_key(i): i for i in issues_b}

            all_keys = set(keys_a.keys()) | set(keys_b.keys())

            # Group by category
            categories = {}
            for key in all_keys:
                cat = key[0] or 'uncategorized'
                if cat not in categories:
                    categories[cat] = {'items': []}

                in_a = key in keys_a
                in_b = key in keys_b

                if in_a and not in_b:
                    status = 'new'  # regression: only in newer crawl
                elif in_b and not in_a:
                    status = 'fixed'  # improvement: was in old, gone in new
                else:
                    status = 'still'  # unchanged: in both

                item = {
                    'url': key[1],
                    'issue': key[2],
                    'status': status,
                    'details_a': keys_a.get(key, {}).get('details'),
                    'details_b': keys_b.get(key, {}).get('details'),
                    'type_a': keys_a.get(key, {}).get('type'),
                    'type_b': keys_b.get(key, {}).get('type'),
                }
                categories[cat]['items'].append(item)

            # Build response
            result_categories = []
            for cat_name, cat_data in sorted(categories.items()):
                items = cat_data['items']
                count_a = sum(1 for i in items if i['status'] in ('still', 'new'))
                count_b = sum(1 for i in items if i['status'] in ('still', 'fixed'))
                fixed = sum(1 for i in items if i['status'] == 'fixed')
                still = sum(1 for i in items if i['status'] == 'still')
                new = sum(1 for i in items if i['status'] == 'new')

                result_categories.append({
                    'category': cat_name,
                    'count_a': count_a,
                    'count_b': count_b,
                    'diff': count_a - count_b,
                    'fixed': fixed,
                    'still': still,
                    'new': new,
                    'items': sorted(items, key=lambda x: (x['status'] != 'fixed', x['status'] != 'still', x['url']))
                })

            return {
                'crawl_a': {
                    'id': crawl_id_a,
                    'crawl_name': crawl_a['crawl_name'] or crawl_a['base_domain'],
                    'base_url': crawl_a['base_url'],
                    'started_at': crawl_a['started_at'],
                    'urls_crawled': crawl_a['urls_crawled'],
                    'status': crawl_a['status'],
                },
                'crawl_b': {
                    'id': crawl_id_b,
                    'crawl_name': crawl_b['crawl_name'] or crawl_b['base_domain'],
                    'base_url': crawl_b['base_url'],
                    'started_at': crawl_b['started_at'],
                    'urls_crawled': crawl_b['urls_crawled'],
                    'status': crawl_b['status'],
                },
                'summary': {
                    'total_issues_a': len(issues_a),
                    'total_issues_b': len(issues_b),
                    'fixed': sum(1 for i in all_keys if i in keys_a and i not in keys_b),
                    'still': sum(1 for i in all_keys if i in keys_a and i in keys_b),
                    'new': sum(1 for i in all_keys if i not in keys_a and i in keys_b),
                },
                'categories': result_categories
            }

    except Exception as e:
        print(f"Error comparing crawls: {e}")
        import traceback
        traceback.print_exc()
        return None
```

- [ ] **Step 4: Add update_crawl_name() function**

Add after `compare_crawls()`:

```python
def update_crawl_name(crawl_id, crawl_name):
    """Update the display name for a crawl"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE crawls SET crawl_name = ? WHERE id = ?', (crawl_name, crawl_id))
            return True
    except Exception as e:
        print(f"Error updating crawl name: {e}")
        return False
```

- [ ] **Step 5: Add get_crawl_issues_count() helper**

Add after `update_crawl_name()`:

```python
def get_crawl_issues_count(crawl_id):
    """Get the number of issues for a crawl"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM crawl_issues WHERE crawl_id = ?', (crawl_id,))
            result = cursor.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        print(f"Error getting issues count: {e}")
        return 0
```

- [ ] **Step 6: Update get_user_crawls() to include issues_count**

Replace the `get_user_crawls()` function (lines 462-491) with:

```python
def get_user_crawls(user_id, limit=50, offset=0, status_filter=None):
    """Get all crawls for a user with issue counts"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            query = '''
                SELECT
                    c.*,
                    COUNT(DISTINCT ci.id) as issues_count
                FROM crawls c
                LEFT JOIN crawl_issues ci ON ci.crawl_id = c.id
                WHERE c.user_id = ?
            '''
            params = [user_id]

            if status_filter:
                query += ' AND c.status = ?'
                params.append(status_filter)

            query += ' GROUP BY c.id ORDER BY c.started_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])

            cursor.execute(query, params)

            crawls = []
            for row in cursor.fetchall():
                crawl = dict(row)
                crawl['config_snapshot'] = None  # Save bandwidth
                crawl['display_name'] = crawl.get('crawl_name') or crawl.get('base_domain') or 'unknown'
                crawls.append(crawl)

            return crawls

    except Exception as e:
        print(f"Error fetching user crawls: {e}")
        return []
```

- [ ] **Step 7: Commit**

```bash
git add src/crawl_db.py
git commit -m "feat(db): add crawl_name, history grouping, and compare functions

- Add crawl_name column migration
- Add get_crawl_history() for domain-grouped crawl listing
- Add compare_crawls() for detailed issue diff between two crawls
- Add update_crawl_name() and get_crawl_issues_count() helpers
- Update get_user_crawls() to include issues_count"
```

---

### Task 2: Backend — main.py new routes

**Files:**
- Modify: `main.py`

**Interfaces:**
- Consumes: `get_crawl_history()`, `compare_crawls()`, `update_crawl_name()` from `crawl_db.py`

- [ ] **Step 1: Add /api/crawls/history route**

Add after the `list_crawls` route (after line ~1069):

```python
@app.route('/api/crawls/history')
@login_required
def crawl_history():
    """Get crawls grouped by domain"""
    try:
        user_id = session.get('user_id')
        from src.crawl_db import get_crawl_history

        domains = get_crawl_history(user_id=user_id)

        return jsonify({
            'success': True,
            'domains': domains
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
```

- [ ] **Step 2: Add /api/crawls/compare route**

Add after the history route:

```python
@app.route('/api/crawls/compare')
@login_required
def compare_crawls_endpoint():
    """Compare two crawls with detailed issue diff"""
    try:
        user_id = session.get('user_id')
        from src.crawl_db import compare_crawls, get_crawl_by_id

        crawl_id_a = request.args.get('ids', type=str)
        if not crawl_id_a or ',' not in crawl_id_a:
            return jsonify({'success': False, 'error': 'Provide two crawl IDs as ids=1,2'}), 400

        id_a, id_b = [int(x.strip()) for x in crawl_id_a.split(',')]

        # Verify ownership
        crawl_a = get_crawl_by_id(id_a)
        crawl_b = get_crawl_by_id(id_b)
        if not crawl_a or not crawl_b:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404

        if user_id:
            if crawl_a.get('user_id') != user_id or crawl_b.get('user_id') != user_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        result = compare_crawls(id_a, id_b)
        if not result:
            return jsonify({'success': False, 'error': 'Failed to compare crawls'}), 500

        return jsonify({
            'success': True,
            **result
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})
```

- [ ] **Step 3: Add /api/crawls/<id>/save-name route**

Add after the compare route:

```python
@app.route('/api/crawls/<int:crawl_id>/save-name', methods=['POST'])
@login_required
def save_crawl_name(crawl_id):
    """Update display name for a crawl"""
    try:
        user_id = session.get('user_id')
        from src.crawl_db import update_crawl_name, get_crawl_by_id

        crawl = get_crawl_by_id(crawl_id)
        if not crawl:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404

        if user_id and crawl.get('user_id') != user_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403

        data = request.get_json()
        crawl_name = data.get('crawl_name', '').strip()

        if not crawl_name:
            crawl_name = crawl.get('base_domain') or 'unnamed'

        success = update_crawl_name(crawl_id, crawl_name)
        return jsonify({'success': success, 'crawl_name': crawl_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
```

- [ ] **Step 4: Add /compare page route**

Add after the `/dashboard` route (after line ~710):

```python
@app.route('/compare')
@login_required
def compare_page():
    """Compare page — compare two crawls"""
    user = get_user_by_id(session.get('user_id'))
    return render_template('compare.html', user=user)
```

- [ ] **Step 5: Update crawl auto-name on completion**

In `main.py`, find the crawl completion logic. In `src/crawler.py`, in the `_crawl_worker` method where status is set to 'completed', add auto-naming. Search for `set_crawl_status(crawl_id, 'completed')` and add after it:

```python
                # Auto-set crawl_name if not set
                from src.crawl_db import get_crawl_by_id, update_crawl_name
                crawl_info = get_crawl_by_id(self.crawl_id)
                if crawl_info and not crawl_info.get('crawl_name'):
                    update_crawl_name(self.crawl_id, self.base_domain)
```

- [ ] **Step 6: Commit**

```bash
git add main.py src/crawler.py
git commit -m "feat(api): add history, compare, and save-name endpoints

- GET /api/crawls/history — domain-grouped crawl listing
- GET /api/crawls/compare?ids=1,2 — detailed issue diff
- POST /api/crawls/<id>/save-name — update crawl display name
- GET /compare — compare page route
- Auto-set crawl_name on crawl completion"
```

---

### Task 3: Frontend — Dashboard redesign (domain sidebar + detail)

**Files:**
- Modify: `web/templates/dashboard.html`
- Modify: `web/static/js/dashboard.js`

**Interfaces:**
- Consumes: `GET /api/crawls/history`, `POST /api/crawls/<id>/load`, `POST /api/crawls/<id>/save-name`, `DELETE /api/crawls/<id>/delete`, `GET /api/crawls/stats`

- [ ] **Step 1: Rewrite dashboard.html**

Replace the entire content of `web/templates/dashboard.html` with the new domain sidebar + detail layout. Use the existing design tokens (`var(--bg)`, `var(--card)`, `var(--ink)`, etc.) and Tailwind classes matching the existing dashboard style.

Key layout:
- Left sidebar (240px): list of domains with crawl count
- Right content: header with domain name + stats, then list of crawls for that domain
- Each crawl: date, status badge, URLs crawled, issues count, duration, actions (Load, Compare checkbox, Rename, Delete)
- Compare mode: checkbox on 2 crawls → "Compare Selected" button appears at top

- [ ] **Step 2: Rewrite dashboard.js**

Replace the entire content of `web/static/js/dashboard.js` with new logic:

- `loadDomainSidebar()` — fetch `/api/crawls/history`, render domain list in sidebar
- `selectDomain(domain)` — filter crawls for selected domain, render in right panel
- `renderCrawlList(crawls)` — render crawl cards with actions
- `toggleCompareMode()` — enable/disable compare checkbox selection
- `compareSelected()` — navigate to `/compare?id_a=X&id_b=Y`
- `renameCrawl(crawlId)` — inline edit or prompt for new name, POST to `/api/crawls/<id>/save-name`
- `loadCrawlFromDashboard(crawlId)` — same as current, POST to `/api/crawls/<id>/load`
- `deleteCrawlFromDashboard(crawlId)` — same as current

- [ ] **Step 3: Commit**

```bash
git add web/templates/dashboard.html web/static/js/dashboard.js
git commit -m "feat(dashboard): redesign with domain sidebar and crawl detail

- Domain sidebar with crawl counts
- Crawl detail panel with stats and actions
- Compare mode with checkbox selection
- Inline rename for crawl names
- Issue count display per crawl"
```

---

### Task 4: Frontend — Compare page

**Files:**
- Create: `web/templates/compare.html`
- Create: `web/static/js/compare.js`

**Interfaces:**
- Consumes: `GET /api/crawls/compare?ids=X,Y`

- [ ] **Step 1: Create compare.html**

Create `web/templates/compare.html` — full-page compare view:

- Include `_rail.html` partial for navigation
- Header: domain name, both crawl dates/stats, summary bar (fixed/still/new counts)
- Per-category expandable sections with items showing:
  - ✅ FIXED (green) — was in old, gone in new
  - ➖ STILL (gray) — same in both
  - 🆕 NEW (red) — only in new (regression)
- Each item: URL, issue description
- Use existing design tokens and Tailwind classes

- [ ] **Step 2: Create compare.js**

Create `web/static/js/compare.js`:

- Parse `?ids=X,Y` from URL
- Fetch `/api/crawls/compare?ids=X,Y`
- Render header with crawl_a and crawl_b info
- Render summary bar
- Render category sections with expandable item lists
- Group items by status (fixed first, then still, then new)

- [ ] **Step 3: Commit**

```bash
git add web/templates/compare.html web/static/js/compare.js
git commit -m "feat(compare): add dedicated compare page with issue diffs

- Full-page compare view with domain header
- Per-category expandable sections
- FIXED/STILL/NEW status icons per issue
- Summary bar with totals"
```

---

### Task 5: Frontend — Save/Load modals in main UI

**Files:**
- Modify: `web/static/js/app.js`
- Modify: `web/templates/partials/_topbar.html`

**Interfaces:**
- Consumes: `POST /api/crawls/<id>/save-name`, `GET /api/crawls/history`

- [ ] **Step 1: Update topbar buttons**

In `web/templates/partials/_topbar.html`, change the Save and Load button onclick handlers:

Line 45: Change `onclick="saveCrawl()"` to `onclick="openSaveModal()"`
Line 46: Change `onclick="loadCrawl()"` to `onclick="openLoadModal()"`

- [ ] **Step 2: Replace saveCrawl() in app.js**

In `web/static/js/app.js`, replace the `saveCrawl()` function (lines 1993-2062) with:

```javascript
async function openSaveModal() {
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'saveModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:1000;';

    const domain = crawlState.baseUrl ? new URL(crawlState.baseUrl).hostname : 'crawl';

    modal.innerHTML = `
        <div style="background:var(--card);border:1px solid var(--border-hairline);border-radius:12px;padding:24px;width:400px;max-width:90vw;">
            <h3 style="font-size:16px;font-weight:600;margin-bottom:16px;color:var(--ink);">Save Crawl</h3>
            <label style="display:block;font-size:12px;color:var(--fg-muted);margin-bottom:6px;">Crawl Name</label>
            <input type="text" id="saveCrawlName" value="${domain}"
                style="width:100%;background:var(--panel);border:1px solid var(--border-hairline);border-radius:6px;padding:8px 12px;font-size:13px;color:var(--ink);outline:none;box-sizing:border-box;"
                placeholder="e.g. After fixing meta tags">
            <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:20px;">
                <button onclick="document.getElementById('saveModal').remove()"
                    style="padding:6px 14px;background:var(--panel-2);color:var(--ink);border:1px solid var(--border-hairline);border-radius:6px;font-size:13px;cursor:pointer;">Cancel</button>
                <button onclick="confirmSaveCrawl()"
                    style="padding:6px 14px;background:var(--primary);color:var(--primary-fg);border:1px solid var(--primary);border-radius:6px;font-size:13px;cursor:pointer;">Save</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    document.getElementById('saveCrawlName').focus();
    document.getElementById('saveCrawlName').select();
}

async function confirmSaveCrawl() {
    const name = document.getElementById('saveCrawlName').value.trim();
    if (!name) return;

    // Find current crawl ID from session or stats
    try {
        const statusResponse = await fetch('/api/crawl_status');
        const statusData = await statusResponse.json();
        const crawlId = statusData.crawl_id;

        if (crawlId) {
            await fetch(`/api/crawls/${crawlId}/save-name`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ crawl_name: name })
            });
        }

        document.getElementById('saveModal').remove();
        showNotification('Crawl saved to database', 'success');
    } catch (error) {
        console.error('Save error:', error);
        showNotification('Failed to save crawl', 'error');
    }
}
```

- [ ] **Step 3: Replace loadCrawl() in app.js**

In `web/static/js/app.js`, replace the `loadCrawl()` function (lines 2064-2225) with:

```javascript
async function openLoadModal() {
    const modal = document.createElement('div');
    modal.id = 'loadModal';
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:1000;';

    modal.innerHTML = `
        <div style="background:var(--card);border:1px solid var(--border-hairline);border-radius:12px;padding:24px;width:500px;max-width:90vw;max-height:80vh;overflow:hidden;display:flex;flex-direction:column;">
            <h3 style="font-size:16px;font-weight:600;margin-bottom:16px;color:var(--ink);">Load Crawl</h3>
            <div id="loadModalContent" style="flex:1;overflow-y:auto;color:var(--fg-muted);font-size:13px;">Loading...</div>
            <div style="display:flex;justify-content:flex-end;margin-top:16px;">
                <button onclick="document.getElementById('loadModal').remove()"
                    style="padding:6px 14px;background:var(--panel-2);color:var(--ink);border:1px solid var(--border-hairline);border-radius:6px;font-size:13px;cursor:pointer;">Close</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    // Load history
    try {
        const response = await fetch('/api/crawls/history');
        const data = await response.json();
        const container = document.getElementById('loadModalContent');

        if (!data.success || !data.domains || data.domains.length === 0) {
            container.innerHTML = '<p style="text-align:center;padding:20px;">No saved crawls found.</p>';
            return;
        }

        let html = '';
        data.domains.forEach(domain => {
            html += `<div style="margin-bottom:16px;">`;
            html += `<div style="font-weight:600;color:var(--ink);margin-bottom:8px;">${domain.domain} <span style="font-weight:400;color:var(--fg-muted);">(${domain.crawl_count})</span></div>`;
            domain.crawls.forEach(crawl => {
                const date = new Date(crawl.started_at).toLocaleString();
                const issues = crawl.issues_count || 0;
                html += `
                    <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border:1px solid var(--border-hairline);border-radius:6px;margin-bottom:4px;cursor:pointer;" onclick="loadFromModal(${crawl.id})" onmouseover="this.style.background='var(--muted)'" onmouseout="this.style.background='transparent'">
                        <span style="flex:1;font-size:13px;color:var(--ink);">${date}</span>
                        <span style="font-size:12px;color:var(--fg-muted);">${crawl.urls_crawled || 0} URLs</span>
                        <span style="font-size:12px;color:${issues > 0 ? 'var(--error)' : 'var(--success)'};">${issues} issues</span>
                        <span style="font-size:11px;color:var(--fg-muted);">${crawl.status}</span>
                    </div>
                `;
            });
            html += `</div>`;
        });
        container.innerHTML = html;

    } catch (error) {
        document.getElementById('loadModalContent').innerHTML = '<p style="color:var(--error);">Error loading history</p>';
    }
}

async function loadFromModal(crawlId) {
    if (!confirm('Load this crawl? Current data will be lost.')) return;

    try {
        const response = await fetch(`/api/crawls/${crawlId}/load`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            document.getElementById('loadModal').remove();
            sessionStorage.setItem('force_ui_refresh', 'true');
            window.location.href = '/';
        } else {
            alert('Error: ' + (data.error || data.message));
        }
    } catch (error) {
        alert('Error loading crawl: ' + error.message);
    }
}
```

- [ ] **Step 4: Remove old saveCrawl/loadCrawl functions**

Make sure the old `saveCrawl()` and `loadCrawl()` functions are fully removed from app.js (they were replaced in steps 2 and 3).

- [ ] **Step 5: Commit**

```bash
git add web/static/js/app.js web/templates/partials/_topbar.html
git commit -m "feat(ui): replace file save/load with DB-backed modals

- Save modal: input crawl name, saves to database
- Load modal: shows domain history, click to load
- Remove file download/upload functionality"
```

---

### Task 6: Final verification

- [ ] **Step 1: Start the server and test**

```bash
python main.py --local
```

- [ ] **Step 2: Test crawl flow**
- Start a crawl for a test URL
- Verify crawl completes and appears in Dashboard with domain grouping
- Click Save → verify name modal appears → save → verify toast
- Click Load → verify history modal with domain groups → load a crawl

- [ ] **Step 3: Test compare flow**
- Need 2 crawls for same domain (or different domains)
- Go to Dashboard → select domain → check 2 crawls → Compare
- Verify compare page shows: summary, categories, FIXED/STILL/NEW items

- [ ] **Step 4: Commit final state**

```bash
git add -A
git commit -m "chore: final verification and cleanup"
```
