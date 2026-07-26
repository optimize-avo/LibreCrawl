"""
Crawl data persistence module
Handles database operations for storing and retrieving crawl data
Enables crash recovery and historical crawl access
"""
import sqlite3
import json
import time
from datetime import datetime
from contextlib import contextmanager

# Database file location (same as auth database) - stored in data/ for Docker volume persistence
import os
DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'users.db')

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_crawl_tables():
    """Initialize crawl persistence tables"""
    with get_db() as conn:
        cursor = conn.cursor()

        # Main crawls table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                session_id TEXT NOT NULL,
                base_url TEXT NOT NULL,
                base_domain TEXT,
                status TEXT DEFAULT 'running',

                config_snapshot TEXT,

                urls_discovered INTEGER DEFAULT 0,
                urls_crawled INTEGER DEFAULT 0,
                max_depth_reached INTEGER DEFAULT 0,

                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                last_saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                peak_memory_mb REAL,
                estimated_size_mb REAL,

                can_resume BOOLEAN DEFAULT 1,
                resume_checkpoint TEXT,

                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')

        # Crawled URLs table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawled_urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crawl_id INTEGER NOT NULL,
                url TEXT NOT NULL,

                status_code INTEGER,
                content_type TEXT,
                size INTEGER,
                is_internal BOOLEAN,
                depth INTEGER,

                title TEXT,
                meta_description TEXT,
                h1 TEXT,
                h2 TEXT,
                h3 TEXT,
                word_count INTEGER,

                canonical_url TEXT,
                lang TEXT,
                charset TEXT,
                viewport TEXT,
                robots TEXT,

                meta_tags TEXT,
                og_tags TEXT,
                twitter_tags TEXT,
                json_ld TEXT,
                analytics TEXT,
                images TEXT,
                hreflang TEXT,
                schema_org TEXT,
                redirects TEXT,
                linked_from TEXT,

                external_links INTEGER,
                internal_links INTEGER,

                response_time REAL,
                javascript_rendered BOOLEAN DEFAULT 0,
                error_type TEXT,

                crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (crawl_id) REFERENCES crawls(id) ON DELETE CASCADE
            )
        ''')

        # Migration: add error_type column to existing crawled_urls tables
        try:
            cursor.execute('ALTER TABLE crawled_urls ADD COLUMN error_type TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migration: add crawl_name column to existing crawls tables
        try:
            cursor.execute('ALTER TABLE crawls ADD COLUMN crawl_name TEXT DEFAULT NULL')
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Links table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawl_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crawl_id INTEGER NOT NULL,

                source_url TEXT NOT NULL,
                target_url TEXT NOT NULL,
                anchor_text TEXT,

                is_internal BOOLEAN,
                target_domain TEXT,
                target_status INTEGER,
                placement TEXT,

                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (crawl_id) REFERENCES crawls(id) ON DELETE CASCADE
            )
        ''')

        # Issues table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawl_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crawl_id INTEGER NOT NULL,

                url TEXT NOT NULL,
                type TEXT,
                category TEXT,
                issue TEXT,
                details TEXT,

                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (crawl_id) REFERENCES crawls(id) ON DELETE CASCADE
            )
        ''')

        # Queue table for crash recovery
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawl_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                crawl_id INTEGER NOT NULL,

                url TEXT NOT NULL,
                depth INTEGER,
                priority INTEGER DEFAULT 0,

                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                FOREIGN KEY (crawl_id) REFERENCES crawls(id) ON DELETE CASCADE,
                UNIQUE(crawl_id, url)
            )
        ''')

        # Create indexes for performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawls_user_status ON crawls(user_id, status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawls_session ON crawls(session_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawled_urls_crawl ON crawled_urls(crawl_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawled_urls_url ON crawled_urls(crawl_id, url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawled_urls_status ON crawled_urls(crawl_id, status_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_links_crawl ON crawl_links(crawl_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_links_source ON crawl_links(crawl_id, source_url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_links_target ON crawl_links(crawl_id, target_url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_issues_crawl ON crawl_issues(crawl_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_issues_url ON crawl_issues(crawl_id, url)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_issues_category ON crawl_issues(crawl_id, category)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_crawl_queue_crawl ON crawl_queue(crawl_id)')

        print("Crawl persistence tables initialized successfully")

def create_crawl(user_id, session_id, base_url, base_domain, config_snapshot):
    """
    Create a new crawl record
    Returns the crawl_id
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO crawls (user_id, session_id, base_url, base_domain, config_snapshot, status)
                VALUES (?, ?, ?, ?, ?, 'running')
            ''', (user_id, session_id, base_url, base_domain, json.dumps(config_snapshot)))

            crawl_id = cursor.lastrowid
            print(f"Created new crawl record: ID={crawl_id}, URL={base_url}")
            return crawl_id
    except Exception as e:
        print(f"Error creating crawl: {e}")
        return None

def update_crawl_stats(crawl_id, discovered=None, crawled=None, max_depth=None, peak_memory_mb=None, estimated_size_mb=None):
    """Update crawl statistics"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            updates = []
            params = []

            if discovered is not None:
                updates.append("urls_discovered = ?")
                params.append(discovered)
            if crawled is not None:
                updates.append("urls_crawled = ?")
                params.append(crawled)
            if max_depth is not None:
                updates.append("max_depth_reached = ?")
                params.append(max_depth)
            if peak_memory_mb is not None:
                updates.append("peak_memory_mb = ?")
                params.append(peak_memory_mb)
            if estimated_size_mb is not None:
                updates.append("estimated_size_mb = ?")
                params.append(estimated_size_mb)

            updates.append("last_saved_at = CURRENT_TIMESTAMP")
            params.append(crawl_id)

            query = f"UPDATE crawls SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

            return True
    except Exception as e:
        print(f"Error updating crawl stats: {e}")
        return False

def save_url_batch(crawl_id, urls):
    """
    Batch save crawled URLs
    urls: list of URL result dictionaries from crawler
    """
    if not urls:
        return True

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            # Prepare batch insert
            rows = []
            for url_data in urls:
                row = (
                    crawl_id,
                    url_data.get('url'),
                    url_data.get('status_code'),
                    url_data.get('content_type'),
                    url_data.get('size'),
                    url_data.get('is_internal'),
                    url_data.get('depth'),
                    url_data.get('title'),
                    url_data.get('meta_description'),
                    url_data.get('h1'),
                    json.dumps(url_data.get('h2', [])),
                    json.dumps(url_data.get('h3', [])),
                    url_data.get('word_count'),
                    url_data.get('canonical_url'),
                    url_data.get('lang'),
                    url_data.get('charset'),
                    url_data.get('viewport'),
                    url_data.get('robots'),
                    json.dumps(url_data.get('meta_tags', {})),
                    json.dumps(url_data.get('og_tags', {})),
                    json.dumps(url_data.get('twitter_tags', {})),
                    json.dumps(url_data.get('json_ld', [])),
                    json.dumps(url_data.get('analytics', {})),
                    json.dumps(url_data.get('images', [])),
                    json.dumps(url_data.get('hreflang', [])),
                    json.dumps(url_data.get('schema_org', [])),
                    json.dumps(url_data.get('redirects', [])),
                    json.dumps(url_data.get('linked_from', [])),
                    url_data.get('external_links'),
                    url_data.get('internal_links'),
                    url_data.get('response_time'),
                    url_data.get('javascript_rendered', False),
                    url_data.get('error_type')
                )
                rows.append(row)

            cursor.executemany('''
                INSERT INTO crawled_urls (
                    crawl_id, url, status_code, content_type, size, is_internal, depth,
                    title, meta_description, h1, h2, h3, word_count,
                    canonical_url, lang, charset, viewport, robots,
                    meta_tags, og_tags, twitter_tags, json_ld, analytics, images,
                    hreflang, schema_org, redirects, linked_from,
                    external_links, internal_links, response_time, javascript_rendered,
                    error_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', rows)

            print(f"Saved {len(urls)} URLs to database for crawl {crawl_id}")
            return True

    except Exception as e:
        print(f"Error saving URL batch: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_links_batch(crawl_id, links):
    """Batch save links"""
    if not links:
        return True

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            rows = []
            for link in links:
                row = (
                    crawl_id,
                    link.get('source_url'),
                    link.get('target_url'),
                    link.get('anchor_text'),
                    link.get('is_internal'),
                    link.get('target_domain'),
                    link.get('target_status'),
                    link.get('placement', 'body')
                )
                rows.append(row)

            cursor.executemany('''
                INSERT INTO crawl_links (
                    crawl_id, source_url, target_url, anchor_text,
                    is_internal, target_domain, target_status, placement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', rows)

            print(f"Saved {len(links)} links to database for crawl {crawl_id}")
            return True

    except Exception as e:
        print(f"Error saving links batch: {e}")
        return False

def save_issues_batch(crawl_id, issues):
    """Batch save SEO issues"""
    if not issues:
        return True

    try:
        with get_db() as conn:
            cursor = conn.cursor()

            rows = []
            for issue in issues:
                row = (
                    crawl_id,
                    issue.get('url'),
                    issue.get('type'),
                    issue.get('category'),
                    issue.get('issue'),
                    issue.get('details')
                )
                rows.append(row)

            cursor.executemany('''
                INSERT INTO crawl_issues (
                    crawl_id, url, type, category, issue, details
                ) VALUES (?, ?, ?, ?, ?, ?)
            ''', rows)

            print(f"Saved {len(issues)} issues to database for crawl {crawl_id}")
            return True

    except Exception as e:
        print(f"Error saving issues batch: {e}")
        return False

def save_checkpoint(crawl_id, checkpoint_data):
    """Save queue checkpoint for crash recovery"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE crawls
                SET resume_checkpoint = ?, last_saved_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (json.dumps(checkpoint_data), crawl_id))

            return True
    except Exception as e:
        print(f"Error saving checkpoint: {e}")
        return False

def set_crawl_status(crawl_id, status):
    """
    Update crawl status
    status: 'running', 'paused', 'completed', 'failed', 'stopped', 'archived'
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            if status in ['completed', 'failed', 'stopped']:
                cursor.execute('''
                    UPDATE crawls
                    SET status = ?, completed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (status, crawl_id))
            else:
                cursor.execute('''
                    UPDATE crawls
                    SET status = ?
                    WHERE id = ?
                ''', (status, crawl_id))

            print(f"Updated crawl {crawl_id} status to: {status}")
            return True

    except Exception as e:
        print(f"Error setting crawl status: {e}")
        return False

def get_crawl_by_id(crawl_id):
    """Get crawl metadata by ID"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM crawls WHERE id = ?
            ''', (crawl_id,))

            row = cursor.fetchone()
            if row:
                crawl = dict(row)
                # Parse JSON fields
                if crawl.get('config_snapshot'):
                    crawl['config_snapshot'] = json.loads(crawl['config_snapshot'])
                if crawl.get('resume_checkpoint'):
                    crawl['resume_checkpoint'] = json.loads(crawl['resume_checkpoint'])
                return crawl
            return None

    except Exception as e:
        print(f"Error fetching crawl: {e}")
        return None

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

def load_crawled_urls(crawl_id, limit=None, offset=0):
    """Load all crawled URLs for a crawl"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM crawled_urls WHERE crawl_id = ? ORDER BY crawled_at'
            params = [crawl_id]

            if limit:
                query += ' LIMIT ? OFFSET ?'
                params.extend([limit, offset])

            cursor.execute(query, params)

            urls = []
            for row in cursor.fetchall():
                url_data = dict(row)
                # Parse JSON fields
                for field in ['h2', 'h3', 'meta_tags', 'og_tags', 'twitter_tags',
                             'json_ld', 'analytics', 'images', 'hreflang',
                             'schema_org', 'redirects', 'linked_from']:
                    if url_data.get(field):
                        try:
                            url_data[field] = json.loads(url_data[field])
                        except:
                            url_data[field] = []

                urls.append(url_data)

            return urls

    except Exception as e:
        print(f"Error loading crawled URLs: {e}")
        return []

def load_crawl_links(crawl_id, limit=None, offset=0):
    """Load all links for a crawl"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM crawl_links WHERE crawl_id = ?'
            params = [crawl_id]

            if limit:
                query += ' LIMIT ? OFFSET ?'
                params.extend([limit, offset])

            cursor.execute(query, params)

            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        print(f"Error loading links: {e}")
        return []

def load_crawl_issues(crawl_id, limit=None, offset=0):
    """Load all issues for a crawl"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            query = 'SELECT * FROM crawl_issues WHERE crawl_id = ?'
            params = [crawl_id]

            if limit:
                query += ' LIMIT ? OFFSET ?'
                params.extend([limit, offset])

            cursor.execute(query, params)

            return [dict(row) for row in cursor.fetchall()]

    except Exception as e:
        print(f"Error loading issues: {e}")
        return []

def get_resume_data(crawl_id):
    """Get all data needed to resume a crawl"""
    crawl = get_crawl_by_id(crawl_id)
    if not crawl:
        return None

    # Only allow resume for paused/failed/running crawls
    if crawl['status'] not in ['paused', 'failed', 'running']:
        return None

    return crawl

def delete_crawl(crawl_id):
    """Delete a crawl and all associated data (CASCADE handles related tables)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM crawls WHERE id = ?', (crawl_id,))
            print(f"Deleted crawl {crawl_id} and all associated data")
            return True
    except Exception as e:
        print(f"Error deleting crawl: {e}")
        return False

def get_crashed_crawls():
    """Find crawls that were running when server crashed"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM crawls
                WHERE status = 'running'
                ORDER BY started_at DESC
            ''')

            crawls = []
            for row in cursor.fetchall():
                crawl = dict(row)
                crawls.append(crawl)

            return crawls

    except Exception as e:
        print(f"Error finding crashed crawls: {e}")
        return []

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

def fix_stopped_to_completed():
    """Fix old crawls that show 'stopped' but were actually completed naturally.

    Before the _natural_finish fix, session timeouts would call stop_crawl()
    during post-processing, overwriting 'completed' with 'stopped'. This
    migration corrects those records on startup.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE crawls
                SET status = 'completed'
                WHERE status = 'stopped'
                AND id IN (
                    SELECT crawl_id FROM crawl_links
                    GROUP BY crawl_id
                    HAVING COUNT(*) > 0
                )
            ''')
            fixed = cursor.rowcount
            if fixed > 0:
                print(f"Migration: fixed {fixed} crawls from 'stopped' → 'completed'")
            return fixed
    except Exception as e:
        print(f"Error fixing stopped crawls: {e}")
        return 0

def cleanup_old_crawls(days=90):
    """Delete crawls older than specified days (optional maintenance)"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM crawls
                WHERE started_at < datetime('now', '-' || ? || ' days')
                AND status IN ('completed', 'failed', 'stopped')
            ''', (days,))

            deleted = cursor.rowcount
            print(f"Cleaned up {deleted} old crawls")
            return deleted

    except Exception as e:
        print(f"Error cleaning up old crawls: {e}")
        return 0

def get_crawl_count(user_id):
    """Get total number of crawls for a user"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) as count FROM crawls WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result['count'] if result else 0
    except Exception as e:
        print(f"Error getting crawl count: {e}")
        return 0

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
                row['display_name'] = row['crawl_name'] or domain
                domains[domain]['crawls'].append(row)
                domains[domain]['crawl_count'] += 1

            result = sorted(domains.values(), key=lambda d: d['domain'])
            return result

    except Exception as e:
        print(f"Error getting crawl history: {e}")
        return []


def compare_crawls(crawl_id_a, crawl_id_b):
    """
    Compare two crawls and return detailed issue diff.
    Returns crawl metadata for both + categories with FIXED/STILL/NEW items.
    """
    try:
        with get_db() as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM crawls WHERE id IN (?, ?)', (crawl_id_a, crawl_id_b))
            crawls = {row['id']: dict(row) for row in cursor.fetchall()}

            if len(crawls) < 2:
                return None

            crawl_a = crawls.get(crawl_id_a)
            crawl_b = crawls.get(crawl_id_b)

            cursor.execute('SELECT * FROM crawl_issues WHERE crawl_id = ?', (crawl_id_a,))
            issues_a = [dict(row) for row in cursor.fetchall()]

            cursor.execute('SELECT * FROM crawl_issues WHERE crawl_id = ?', (crawl_id_b,))
            issues_b = [dict(row) for row in cursor.fetchall()]

            def issue_key(issue):
                return (issue.get('category') or '', issue.get('url') or '', issue.get('issue') or '')

            keys_a = {issue_key(i): i for i in issues_a}
            keys_b = {issue_key(i): i for i in issues_b}

            all_keys = set(keys_a.keys()) | set(keys_b.keys())

            categories = {}
            for key in all_keys:
                cat = key[0] or 'uncategorized'
                if cat not in categories:
                    categories[cat] = {'items': []}

                in_a = key in keys_a
                in_b = key in keys_b

                if in_a and not in_b:
                    status = 'new'
                elif in_b and not in_a:
                    status = 'fixed'
                else:
                    status = 'still'

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

            result_categories = []
            for cat_name, cat_data in sorted(categories.items()):
                items = cat_data['items']
                count_a = sum(1 for i in items if i['status'] in ('still', 'new'))
                count_b = sum(1 for i in items if i['status'] in ('still', 'fixed'))
                fixed = sum(1 for i in items if i['status'] == 'fixed')
                still = sum(1 for i in items if i['status'] == 'still')
                new_count = sum(1 for i in items if i['status'] == 'new')

                result_categories.append({
                    'category': cat_name,
                    'count_a': count_a,
                    'count_b': count_b,
                    'diff': count_a - count_b,
                    'fixed': fixed,
                    'still': still,
                    'new': new_count,
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


def get_database_size_mb():
    """Get total database size in MB"""
    try:
        import os
        if os.path.exists(DB_FILE):
            size_bytes = os.path.getsize(DB_FILE)
            return round(size_bytes / (1024 * 1024), 2)
        return 0
    except Exception as e:
        print(f"Error getting database size: {e}")
        return 0
