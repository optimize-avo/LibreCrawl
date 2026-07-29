import threading
import time
from collections import deque
from datetime import datetime
import json


class LogTracker:
    """Thread-safe in-memory + DB-backed log storage with SSE support.

    Captures all crawl lifecycle events so the Log Tracker page can
    display real-time process updates. Logs are persisted to the
    database so history survives server restarts.
    """

    def __init__(self, max_logs=20000):
        self._logs = deque(maxlen=max_logs)
        self._lock = threading.Lock()
        self._subscribers = []
        self._subscribers_lock = threading.Lock()
        self._db_batch = []
        self._db_batch_size = 20
        self._db_save_interval = 10
        self._last_db_save = time.time()
        self._history_seeded = False

    def seed_from_db(self):
        """Load historical crawls from DB and inject as log entries."""
        if self._history_seeded:
            return
        self._history_seeded = True
        try:
            from src.crawl_db import get_all_crawls_for_logs, cleanup_crawl_logs
            crawls = get_all_crawls_for_logs()
            cleanup_crawl_logs()  # remove duplicate old entries before re-seeding
            for c in crawls:
                domain = c['base_domain'] or c['base_url'] or 'Unknown'
                crawled = c['urls_crawled'] or 0
                discovered = c['urls_discovered'] or 0

                # Start event
                start_ts = c['started_epoch'] or (time.time() - 10)
                self._log(
                    'INFO', 'history',
                    f'Memulai audit {domain}',
                    crawl_id=c['crawl_id'], url=c['base_url'],
                    progress=0, status=None,
                    timestamp_epoch=start_ts,
                )

                # Completion / stop / failed event (5 seconds later)
                end_ts = (c.get('completed_epoch') or start_ts + 5)
                progress = 100 if c['status'] == 'completed' else (
                    min(100, crawled / max(discovered, 1) * 100)
                )

                if c['status'] == 'completed':
                    msg = f'Audit {domain} selesai — {crawled} halaman terindeks, {discovered} tautan ditemukan'
                elif c['status'] == 'failed':
                    msg = f'Audit {domain} gagal — hanya {crawled} dari {discovered} halaman'
                elif c['status'] == 'stopped':
                    msg = f'Audit {domain} dihentikan — {crawled} halaman berhasil diproses'
                elif c['status'] == 'paused':
                    msg = f'Audit {domain} dijeda — {crawled}/{discovered} halaman'
                elif c['status'] == 'demo_stopped':
                    msg = f'Audit {domain} berhenti (batas demo) — {crawled} halaman'
                else:
                    msg = f'Audit {domain} — {crawled} halaman dari {discovered}'

                self._log(
                    'INFO' if c['status'] in ('completed',) else 'WARN',
                    'history', msg,
                    crawl_id=c['crawl_id'], url=c['base_url'],
                    progress=round(progress, 1), status=c['status'],
                    timestamp_epoch=end_ts,
                )
            if crawls:
                print(f"Seeded {len(crawls)} historical crawls into log tracker")
        except Exception as e:
            print(f"Error seeding historical crawls: {e}")

    def info(self, source, message, crawl_id=None, url=None, progress=None, status=None):
        self._log('INFO', source, message, crawl_id, url, progress, status)

    def warn(self, source, message, crawl_id=None, url=None, progress=None, status=None):
        self._log('WARN', source, message, crawl_id, url, progress, status)

    def error(self, source, message, crawl_id=None, url=None, progress=None, status=None):
        self._log('ERROR', source, message, crawl_id, url, progress, status)

    def _log(self, level, source, message, crawl_id=None, url=None, progress=None, status=None, timestamp_epoch=None):
        ts = timestamp_epoch if timestamp_epoch else time.time()
        entry = {
            'timestamp': datetime.fromtimestamp(ts).isoformat(),
            'timestamp_epoch': ts,
            'level': level,
            'source': source,
            'message': message,
            'crawl_id': crawl_id,
            'url': url,
            'progress': progress,
            'status': status,
        }
        with self._lock:
            self._logs.append(entry)

        with self._subscribers_lock:
            for queue in self._subscribers[:]:
                try:
                    queue.append(entry)
                except Exception:
                    pass

        self._maybe_save_db(entry)

    def _maybe_save_db(self, entry):
        self._db_batch.append(entry)
        now = time.time()
        if len(self._db_batch) >= self._db_batch_size or now - self._last_db_save >= self._db_save_interval:
            batch = self._db_batch
            self._db_batch = []
            self._last_db_save = now
            try:
                from src.crawl_db import save_logs_batch
                save_logs_batch(batch)
            except Exception:
                pass

    def get_logs(self, since=None, crawl_id=None, level=None, limit=500, offset=0, page=None, per_page=None):
        """Return logs from DB + in-memory, newest first, deduplicated."""
        from src.crawl_db import get_historical_logs

        # 1. Load from DB (older entries)
        db_result = get_historical_logs(
            since=None,
            crawl_id=crawl_id,
            level=level,
            limit=999999,
            offset=0,
        )

        # 2. Load from memory (newer entries)
        with self._lock:
            mem_logs = list(self._logs)

        if crawl_id is not None:
            mem_logs = [e for e in mem_logs if e.get('crawl_id') == crawl_id]
        if level is not None:
            levels = [l.strip() for l in level.split(',')]
            mem_logs = [e for e in mem_logs if e['level'] in levels]

        # 3. Merge: DB logs first, then mem logs (newest at end), deduplicate by (timestamp_epoch, crawl_id)
        seen_keys = set()
        merged = []

        for e in reversed(mem_logs):
            cid = e.get('crawl_id')
            key = (e.get('timestamp_epoch', 0), cid) if cid else (e.get('timestamp_epoch', 0), e.get('message', ''))
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(e)

        for e in reversed(db_result['logs']):
            cid = e.get('crawl_id')
            key = (e.get('timestamp_epoch', 0), cid) if cid else (e.get('timestamp_epoch', 0), e.get('message', ''))
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(e)

        # 4. Sort by timestamp descending (newest first)
        merged.sort(key=lambda e: e.get('timestamp_epoch', 0), reverse=True)

        total = len(merged)

        # 5. Pagination
        if page is not None and per_page is not None:
            start = (page - 1) * per_page
            sliced = merged[start:start + per_page]
            pages = max(1, -(-total // per_page))  # ceil division
        else:
            sliced = merged[offset:offset + limit]
            pages = 1

        # 6. Compute summary counts from full dataset
        summary = {'active': 0, 'completed': 0, 'failed': 0, 'stopped': 0}
        seen_crawls = set()
        for e in merged:
            cid = e.get('crawl_id')
            if cid and cid not in seen_crawls:
                seen_crawls.add(cid)
                s = (e.get('status') or '').lower()
                if s in ('running', 'idle'):
                    summary['active'] += 1
                elif s == 'completed':
                    summary['completed'] += 1
                elif s == 'failed':
                    summary['failed'] += 1
                elif s in ('stopped', 'demo_stopped'):
                    summary['stopped'] += 1

        # 7. Apply since filter after merge (so sorting works)
        if since is not None:
            sliced = [e for e in sliced if e['timestamp_epoch'] > since]

        return {
            'logs': sliced,
            'total': total,
            'page': page or 1,
            'per_page': per_page or limit,
            'pages': pages,
            'summary': summary,
        }

    def subscribe(self):
        q = deque()
        with self._subscribers_lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self._subscribers_lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def get_active_crawls_summary(self):
        """Return crawls that are currently running or paused — from memory + DB."""
        seen = {}

        # 1. Check in-memory logs
        with self._lock:
            for e in reversed(self._logs):
                cid = e.get('crawl_id')
                status = e.get('status', '')
                if cid and status in ('running', 'paused', 'idle') and cid not in seen:
                    seen[cid] = {
                        'crawl_id': cid,
                        'url': e.get('url'),
                        'status': status,
                        'progress': e.get('progress'),
                        'source': e.get('source'),
                        'last_message': e['message'],
                        'last_timestamp': e['timestamp'],
                    }

        # 2. Also check DB for any running/paused crawls not in memory
        try:
            from src.crawl_db import get_historical_logs, get_crawl_by_id
            db_result = get_historical_logs(limit=5000, offset=0)
            for e in reversed(db_result['logs']):
                cid = e.get('crawl_id')
                status = e.get('status', '')
                if cid and status in ('running', 'paused', 'idle') and cid not in seen:
                    # Verify against actual crawl status (crawl_logs may be stale)
                    info = get_crawl_by_id(cid)
                    actual_status = (info or {}).get('status', '')
                    if actual_status not in ('running', 'paused'):
                        continue
                    seen[cid] = {
                        'crawl_id': cid,
                        'url': e.get('url'),
                        'status': status,
                        'progress': e.get('progress'),
                        'source': e.get('source'),
                        'last_message': e['message'],
                        'last_timestamp': e['timestamp'],
                    }
        except Exception:
            pass

        return list(seen.values())[:50]


log_tracker = LogTracker()
