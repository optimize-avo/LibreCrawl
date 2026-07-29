import time
import uuid
import os
from datetime import datetime

from flask import Blueprint, request, jsonify, session

import sqlite3

from routes import (
    login_required, get_or_create_crawler, get_session_settings,
    get_client_ip, cfg,
    crawler_instances, instances_lock,
    filter_issues_by_exclusion_patterns, crawler_info_to_response,
    generate_csv_export, generate_json_export, generate_xml_export,
    generate_links_csv_export, generate_links_json_export,
    generate_issues_csv_export, generate_issues_json_export
)
from src.log_tracker import log_tracker
from src.utils import lazy

crawl_db = lazy('src.crawl_db')
auth_db = lazy('src.auth_db')
memory_profiler_mod = lazy('src.core.memory_profiler')

api_bp = Blueprint('api', __name__)

# ── Crawl endpoints ──────────────────────────────────────────────

def _validate_crawl_url(url):
    """Validate URL for crawling: length, format, and SSRF prevention."""
    from urllib.parse import urlparse
    import socket
    import ipaddress

    if not url:
        return False, 'URL is required'
    if len(url) > 2048:
        return False, 'URL is too long (max 2048 characters)'
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False, 'Invalid URL format'
    except Exception:
        return False, 'Invalid URL format'
    try:
        hostname = parsed.netloc.split(':')[0]
        addrs = socket.getaddrinfo(hostname, 80, socket.AF_INET)
        for family, type, proto, canonname, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return False, f'Cannot crawl private/internal IP addresses ({sockaddr[0]})'
    except socket.gaierror:
        return False, f'Could not resolve hostname: {hostname}'
    return True, url


@api_bp.route('/api/start_crawl', methods=['POST'])
@login_required
def start_crawl():
    data = request.get_json()
    url = data.get('url')
    valid, result = _validate_crawl_url(url)
    if not valid:
        return jsonify({'success': False, 'error': result})
    url = result
    user_id = session.get('user_id')
    session_id = session.get('session_id')
    tier = session.get('tier', 'guest')
    if tier == 'guest' and not cfg.LOCAL_MODE:
        client_ip = get_client_ip()
        crawls_from_ip = auth_db.get_guest_crawls_last_24h(client_ip)
        if crawls_from_ip >= 3:
            return jsonify({'success': False, 'error': 'Guest limit reached: 3 crawls per 24 hours from your IP address. Please register for unlimited crawls.'})
        auth_db.log_guest_crawl(client_ip)
    crawler = get_or_create_crawler()
    settings_manager = get_session_settings()
    try:
        crawler_config = settings_manager.get_crawler_config()
        crawler.update_config(crawler_config)
    except Exception as e:
        pass
    if cfg.DEMO_MODE:
        crawler.config['demo_mode'] = True
        crawler.config['demo_memory_limit_bytes'] = int(1.5 * 1024 * 1024 * 1024)
    owner_username = session.get('username')
    success, message = crawler.start_crawl(url, user_id=user_id, session_id=session_id, owner_username=owner_username)
    if success and crawler.crawl_id:
        session['current_crawl_id'] = crawler.crawl_id
        auth_db.log_crawl_start(user_id, url)
    else:
        log_tracker.error('system', f'Gagal memulai audit {url}: {message}', url=url)
    return jsonify({'success': success, 'message': message, 'crawl_id': crawler.crawl_id})

@api_bp.route('/api/stop_crawl', methods=['POST'])
@login_required
def stop_crawl():
    crawler = get_or_create_crawler()
    crawl_id = getattr(crawler, 'crawl_id', None)
    success, message = crawler.stop_crawl()
    log_tracker.info('system', f'Menghentikan audit: {message}', crawl_id=crawl_id, status='stopped')
    return jsonify({'success': success, 'message': message})

@api_bp.route('/api/crawl_status')
@login_required
def crawl_status():
    crawler = get_or_create_crawler()
    settings_manager = get_session_settings()
    url_since = request.args.get('url_since', type=int)
    link_since = request.args.get('link_since', type=int)
    issue_since = request.args.get('issue_since', type=int)
    status_data = crawler.get_status()
    if crawler.base_url and 'stats' in status_data:
        status_data['stats']['baseUrl'] = crawler.base_url
    force_full = session.pop('force_full_refresh', False)
    if not force_full:
        if url_since is not None:
            status_data['urls'] = status_data.get('urls', [])[url_since:]
        if link_since is not None:
            status_data['links'] = status_data.get('links', [])[link_since:]
        if issue_since is not None:
            status_data['issues'] = status_data.get('issues', [])[issue_since:]
    issues = status_data.get('issues', [])
    if issues:
        current_settings = settings_manager.get_settings()
        exclusion_patterns_text = current_settings.get('issueExclusionPatterns', '')
        exclusion_patterns = [p.strip() for p in exclusion_patterns_text.split('\n') if p.strip()]
        filtered_issues = filter_issues_by_exclusion_patterns(issues, exclusion_patterns)
        status_data['issues'] = filtered_issues
    status_data['crawl_id'] = getattr(crawler, 'crawl_id', None)
    return jsonify(status_data)

@api_bp.route('/api/visualization_data')
@login_required
def visualization_data():
    try:
        crawler = get_or_create_crawler()
        status_data = crawler.get_status()
        crawled_pages = status_data.get('urls', [])
        all_links = status_data.get('links', [])
        nodes = []
        edges = []
        url_to_id = {}
        max_nodes = 500
        pages_to_visualize = crawled_pages[:max_nodes]
        for idx, page in enumerate(pages_to_visualize):
            url = page.get('url', '')
            status_code = page.get('status_code', 0)
            if 200 <= status_code < 300:
                color = '#10b981'
            elif 300 <= status_code < 400:
                color = '#3b82f6'
            elif 400 <= status_code < 500:
                color = '#f59e0b'
            elif 500 <= status_code < 600:
                color = '#ef4444'
            else:
                color = '#6b7280'
            node = {
                'data': {
                    'id': f'node-{idx}',
                    'label': url.split('/')[-1] or url.split('//')[-1],
                    'url': url,
                    'status_code': status_code,
                    'title': page.get('title', ''),
                    'color': color,
                    'size': 30 if idx == 0 else 20,
                    'depth': page.get('depth', 0)
                }
            }
            nodes.append(node)
            url_to_id[url] = f'node-{idx}'
        edges_set = set()
        for link in all_links:
            if link.get('is_internal'):
                source_url = link.get('source_url', '')
                target_url = link.get('target_url', '')
                source_id = url_to_id.get(source_url)
                target_id = url_to_id.get(target_url)
                if source_id and target_id and source_id != target_id:
                    edge_key = f'{source_id}-{target_id}'
                    if edge_key not in edges_set:
                        edges_set.add(edge_key)
                        edge = {
                            'data': {
                                'id': f'edge-{edge_key}',
                                'source': source_id,
                                'target': target_id
                            }
                        }
                        edges.append(edge)
        return jsonify({
            'success': True,
            'nodes': nodes,
            'edges': edges,
            'total_pages': len(crawled_pages),
            'visualized_pages': len(nodes),
            'truncated': len(crawled_pages) > max_nodes
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'nodes': [], 'edges': []})

@api_bp.route('/api/pause_crawl', methods=['POST'])
@login_required
def pause_crawl():
    try:
        crawler = get_or_create_crawler()
        crawl_id = getattr(crawler, 'crawl_id', None)
        success, message = crawler.pause_crawl()
        log_tracker.info('system', f'Menjeda audit: {message}', crawl_id=crawl_id, status='paused')
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/resume_crawl', methods=['POST'])
@login_required
def resume_crawl():
    try:
        crawler = get_or_create_crawler()
        crawl_id = getattr(crawler, 'crawl_id', None)
        success, message = crawler.resume_crawl()
        log_tracker.info('system', f'Melanjutkan audit: {message}', crawl_id=crawl_id, status='running')
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Crawl list / history ─────────────────────────────────────────

@api_bp.route('/api/crawls/list')
@login_required
def list_crawls():
    try:
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        status_filter = request.args.get('status')
        mine_only = request.args.get('mine', '').lower() in ('1', 'true')
        user_id = session.get('user_id') if mine_only else None
        crawls = crawl_db.get_user_crawls(user_id, limit=limit, offset=offset, status_filter=status_filter)
        if user_id is not None:
            total_count = crawl_db.get_crawl_count(user_id)
        else:
            total_count = len(crawls)
            if len(crawls) >= limit:
                with crawl_db.get_db() as conn:
                    total_count = conn.cursor().execute('SELECT COUNT(*) FROM crawls').fetchone()[0]
        return jsonify({'success': True, 'crawls': crawls, 'total': total_count})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/my_active_crawls')
@login_required
def my_active_crawls():
    try:
        user_id = session.get('user_id')
        crawls = crawl_db.get_user_active_crawls(user_id)
        return jsonify({'success': True, 'crawls': crawls})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'crawls': []})

@api_bp.route('/api/crawls/history')
@login_required
def crawl_history():
    try:
        mine_only = request.args.get('mine', '').lower() in ('1', 'true')
        user_id = session.get('user_id') if mine_only else None
        domains = crawl_db.get_crawl_history(user_id=user_id)
        return jsonify({'success': True, 'domains': domains})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/crawls/stats')
@login_required
def crawl_stats():
    try:
        user_id = session.get('user_id')
        conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'users.db'))
        cursor = conn.cursor()
        cursor.execute('SELECT status, COUNT(*) as count FROM crawls WHERE user_id = ? GROUP BY status', (user_id,))
        status_counts = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()
        return jsonify({
            'success': True,
            'total_crawls': crawl_db.get_crawl_count(user_id),
            'by_status': status_counts,
            'database_size_mb': crawl_db.get_database_size_mb()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Crawl detail / reconnect / CRUD ─────────────────────────────

@api_bp.route('/api/crawls/<int:crawl_id>/reconnect', methods=['POST'])
@login_required
def reconnect_crawl(crawl_id):
    try:
        user_id = session.get('user_id')
        crawl_info = crawl_db.get_crawl_by_id(crawl_id)
        if not crawl_info:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404
        if crawl_info.get('status') not in ('running', 'paused'):
            return jsonify({'success': False, 'error': f'Crawl is {crawl_info.get("status")}, cannot reconnect'}), 400
        with instances_lock:
            for sid, instance_data in crawler_instances.items():
                crawler = instance_data['crawler']
                if crawler.crawl_id == crawl_id:
                    if user_id and crawl_info.get('user_id') != user_id:
                        return jsonify({'success': False, 'error': 'Unauthorized - you don\'t own this crawl'}), 403
                    session_id = session.get('session_id')
                    if not session_id:
                        session['session_id'] = str(uuid.uuid4())
                        session_id = session['session_id']
                    if sid != session_id:
                        if sid in crawler_instances:
                            del crawler_instances[sid]
                        instance_data['last_accessed'] = datetime.now()
                        crawler_instances[session_id] = instance_data
                    instance_data['last_accessed'] = datetime.now()
                    status_data = crawler.get_status()
                    log_tracker.info('system', f'Terhubung kembali ke audit #{crawl_id}', crawl_id=crawl_id, status='running')
                    return jsonify({
                        'success': True,
                        'message': 'Reconnected to active crawl',
                        'status': crawler_info_to_response(crawl_info, status_data)
                    })
        crawler = get_or_create_crawler()
        success, message = crawler.resume_from_database(crawl_id, user_id=user_id)
        if success:
            log_tracker.info('system', f'Memulihkan audit #{crawl_id} dari database: {message}', crawl_id=crawl_id, status='running')
            return jsonify({'success': True, 'message': message, 'status': crawler.get_status()})
        else:
            return jsonify({'success': False, 'error': message}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/api/crawls/compare')
@login_required
def compare_crawls_endpoint():
    try:
        user_id = session.get('user_id')
        crawl_id_a = request.args.get('ids', type=str)
        if not crawl_id_a or ',' not in crawl_id_a:
            return jsonify({'success': False, 'error': 'Provide two crawl IDs as ids=1,2'}), 400
        id_a, id_b = [int(x.strip()) for x in crawl_id_a.split(',')]
        crawl_a = crawl_db.get_crawl_by_id(id_a)
        crawl_b = crawl_db.get_crawl_by_id(id_b)
        if not crawl_a or not crawl_b:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404
        if user_id:
            if crawl_a.get('user_id') != user_id or crawl_b.get('user_id') != user_id:
                return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        result = crawl_db.compare_crawls(id_a, id_b)
        if not result:
            return jsonify({'success': False, 'error': 'Failed to compare crawls'}), 500
        return jsonify({'success': True, **result})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/crawls/<int:crawl_id>/save-name', methods=['POST'])
@login_required
def save_crawl_name(crawl_id):
    try:
        user_id = session.get('user_id')
        crawl = crawl_db.get_crawl_by_id(crawl_id)
        if not crawl:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404
        if user_id and crawl.get('user_id') != user_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        data = request.get_json()
        crawl_name = data.get('crawl_name', '').strip()
        if not crawl_name:
            crawl_name = crawl.get('base_domain') or 'unnamed'
        success = crawl_db.update_crawl_name(crawl_id, crawl_name)
        return jsonify({'success': success, 'crawl_name': crawl_name})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/crawls/<int:crawl_id>')
@login_required
def get_crawl(crawl_id):
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 500, type=int)
        per_page = min(per_page, 5000)
        offset = (page - 1) * per_page

        crawl = crawl_db.get_crawl_by_id(crawl_id)
        if not crawl:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404

        total_urls = crawl_db.count_crawled_urls(crawl_id)
        total_links = crawl_db.count_crawl_links(crawl_id)
        total_issues = crawl_db.get_crawl_issues_count(crawl_id)

        urls = crawl_db.load_crawled_urls(crawl_id, limit=per_page, offset=offset)
        links = crawl_db.load_crawl_links(crawl_id, limit=per_page, offset=offset)
        issues = crawl_db.load_crawl_issues(crawl_id, limit=per_page, offset=offset)

        return jsonify({
            'success': True,
            'crawl': crawl,
            'urls': urls,
            'links': links,
            'issues': issues,
            'total_urls': total_urls,
            'total_links': total_links,
            'total_issues': total_issues,
            'page': page,
            'per_page': per_page
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/api/crawls/<int:crawl_id>/load', methods=['POST'])
@login_required
def load_crawl_endpoint(crawl_id):
    try:
        user_id = session.get('user_id')
        crawler = get_or_create_crawler()
        success, message = crawler.load_completed_crawl(crawl_id, user_id=user_id)
        if success:
            session['current_crawl_id'] = crawl_id
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/crawls/<int:crawl_id>/resume', methods=['POST'])
@login_required
def resume_crawl_endpoint(crawl_id):
    try:
        user_id = session.get('user_id')
        session_id = session.get('session_id')
        crawler = get_or_create_crawler()
        if cfg.DEMO_MODE:
            crawler.config['demo_mode'] = True
            crawler.config['demo_memory_limit_bytes'] = int(1.5 * 1024 * 1024 * 1024)
        success, message = crawler.resume_from_database(crawl_id, user_id=user_id, session_id=session_id)
        if success:
            session['current_crawl_id'] = crawl_id
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/crawls/<int:crawl_id>/delete', methods=['DELETE'])
@login_required
def delete_crawl_endpoint(crawl_id):
    try:
        user_id = session.get('user_id')
        crawl = crawl_db.get_crawl_by_id(crawl_id)
        if not crawl:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404
        if user_id and crawl.get('user_id') != user_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        success = crawl_db.delete_crawl(crawl_id)
        return jsonify({'success': success, 'message': 'Crawl deleted successfully' if success else 'Failed to delete crawl'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/crawls/<int:crawl_id>/archive', methods=['POST'])
@login_required
def archive_crawl(crawl_id):
    try:
        user_id = session.get('user_id')
        crawl = crawl_db.get_crawl_by_id(crawl_id)
        if not crawl:
            return jsonify({'success': False, 'error': 'Crawl not found'}), 404
        if user_id and crawl.get('user_id') != user_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        success = crawl_db.set_crawl_status(crawl_id, 'archived')
        return jsonify({'success': success, 'message': 'Crawl archived successfully' if success else 'Failed to archive crawl'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Settings ────────────────────────────────────────────────────

@api_bp.route('/api/get_settings')
@login_required
def get_settings():
    try:
        settings_manager = get_session_settings()
        settings = settings_manager.get_settings()
        return jsonify({'success': True, 'settings': settings})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/save_settings', methods=['POST'])
@login_required
def save_settings():
    try:
        data = request.get_json()
        settings_manager = get_session_settings()
        success, message = settings_manager.save_settings(data)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/reset_settings', methods=['POST'])
@login_required
def reset_settings():
    try:
        settings_manager = get_session_settings()
        success, message = settings_manager.reset_settings()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/update_crawler_settings', methods=['POST'])
@login_required
def update_crawler_settings():
    try:
        crawler = get_or_create_crawler()
        settings_manager = get_session_settings()
        crawler_config = settings_manager.get_crawler_config()
        crawler.update_config(crawler_config)
        return jsonify({'success': True, 'message': 'Crawler settings updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Logs ────────────────────────────────────────────────────────

@api_bp.route('/api/logs')
@login_required
def get_logs():
    crawl_id = request.args.get('crawl_id', type=int)
    level = request.args.get('level')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    result = log_tracker.get_logs(crawl_id=crawl_id, level=level, page=page, per_page=per_page)
    return jsonify({'success': True, **result})

@api_bp.route('/api/logs/poll')
@login_required
def logs_poll():
    since = request.args.get('since', type=float)
    result = log_tracker.get_logs(since=since, limit=200, page=1, per_page=200)
    return jsonify({'success': True, 'logs': result.get('logs', []), 'summary': result.get('summary', {})})

@api_bp.route('/api/logs/active')
@login_required
def logs_active():
    crawl_ids = set()
    enriched = []
    with instances_lock:
        for sid, inst in crawler_instances.items():
            c = inst['crawler']
            if hasattr(c, 'is_running') and c.is_running and hasattr(c, 'crawl_id') and c.crawl_id:
                cid = c.crawl_id
                if cid not in crawl_ids:
                    crawl_ids.add(cid)
                    try:
                        info = crawl_db.get_crawl_by_id(cid)
                    except Exception:
                        info = None
                    enriched.append({
                        'crawl_id': cid,
                        'base_url': getattr(c, 'base_url', ''),
                        'base_domain': getattr(c, 'base_domain', ''),
                        'status': 'running',
                        'progress': round((getattr(c, 'stats', {}) or {}).get('crawled', 0) / max((getattr(c, 'stats', {}) or {}).get('discovered', 1), 1) * 100, 1),
                        'urls_crawled': (getattr(c, 'stats', {}) or {}).get('crawled', 0),
                        'urls_discovered': (getattr(c, 'stats', {}) or {}).get('discovered', 0),
                        'last_message': f'Memeriksa {getattr(c, "current_crawl_url", "")}' if getattr(c, 'current_crawl_url', None) else 'Audit berjalan',
                        'last_timestamp': '',
                        'source': 'crawler',
                        'url': getattr(c, 'base_url', ''),
                    })
    log_summary = log_tracker.get_active_crawls_summary()
    for s in log_summary:
        cid = s['crawl_id']
        if cid not in crawl_ids:
            crawl_ids.add(cid)
            try:
                info = crawl_db.get_crawl_by_id(cid)
                if info:
                    s['base_url'] = info.get('base_url')
                    s['base_domain'] = info.get('base_domain')
                    s['urls_crawled'] = info.get('urls_crawled', 0)
                    s['urls_discovered'] = info.get('urls_discovered', 0)
                    s['max_depth'] = info.get('max_depth_reached', 0)
            except Exception:
                pass
            enriched.append(s)
    return jsonify({'success': True, 'crawls': enriched})

# ── Export ──────────────────────────────────────────────────────

@api_bp.route('/api/filter_issues', methods=['POST'])
@login_required
def filter_issues():
    try:
        data = request.get_json()
        issues = data.get('issues', [])
        settings_manager = get_session_settings()
        current_settings = settings_manager.get_settings()
        exclusion_patterns_text = current_settings.get('issueExclusionPatterns', '')
        exclusion_patterns = [p.strip() for p in exclusion_patterns_text.split('\n') if p.strip()]
        filtered_issues = filter_issues_by_exclusion_patterns(issues, exclusion_patterns)
        return jsonify({'success': True, 'issues': filtered_issues})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@api_bp.route('/api/export_data', methods=['POST'])
@login_required
def export_data():
    try:
        data = request.get_json()
        export_format = data.get('format', 'csv')
        export_fields = data.get('fields', ['url', 'status_code', 'title'])
        local_data = data.get('localData', {})
        filename_suffix = data.get('filenameSuffix', '')
        urls = local_data.get('urls', []) if local_data else []
        links = local_data.get('links', []) if local_data else []
        issues = local_data.get('issues', []) if local_data else []
        if not urls and not links and not issues:
            crawler = get_or_create_crawler()
            crawl_data = crawler.get_status()
            urls = crawl_data.get('urls', [])
            links = crawl_data.get('links', [])
            issues = crawl_data.get('issues', [])
        tab = data.get('tab', 'all')
        if tab in ['links', 'issues'] and not urls:
            if tab == 'links' and links:
                pass
            elif tab == 'issues' and issues:
                pass
            elif not urls:
                return jsonify({'success': False, 'error': 'No data to export'})
        elif not urls:
            return jsonify({'success': False, 'error': 'No data to export'})
        if links and urls:
            status_lookup = {url_data['url']: url_data.get('status_code') for url_data in urls}
            for link in links:
                target_url = link.get('target_url')
                if target_url in status_lookup:
                    link['target_status'] = status_lookup[target_url]
        if issues:
            settings_manager = get_session_settings()
            current_settings = settings_manager.get_settings()
            exclusion_patterns_text = current_settings.get('issueExclusionPatterns', '')
            exclusion_patterns = [p.strip() for p in exclusion_patterns_text.split('\n') if p.strip()]
            issues = filter_issues_by_exclusion_patterns(issues, exclusion_patterns)
        files_to_export = []
        has_issues_export = 'issues_detected' in export_fields
        has_links_export = 'links_detailed' in export_fields
        regular_fields = [f for f in export_fields if f not in ['issues_detected', 'links_detailed']]
        if tab == 'issues':
            has_issues_export = True
            has_links_export = False
            regular_fields = []
            urls = []
        elif tab == 'links':
            has_issues_export = False
            has_links_export = True
            regular_fields = []
            urls = []
        elif tab in ['internal', 'external']:
            has_issues_export = False
            has_links_export = False
        if tab == 'issues':
            has_links_export = False
            regular_fields = []
            urls = []
        if has_issues_export and issues:
            if export_format == 'csv':
                issues_content = generate_issues_csv_export(issues)
                issues_mimetype = 'text/csv'
            elif export_format == 'json':
                issues_content = generate_issues_json_export(issues)
                issues_mimetype = 'application/json'
            else:
                issues_content = generate_issues_csv_export(issues)
                issues_mimetype = 'text/csv'
            files_to_export.append({
                'content': issues_content,
                'mimetype': issues_mimetype,
                'filename': f'librecrawl{filename_suffix}_{int(time.time())}.{"json" if export_format == "json" else "csv"}'
            })
        if has_links_export and links:
            if export_format == 'csv':
                links_content = generate_links_csv_export(links)
                links_mimetype = 'text/csv'
            elif export_format == 'json':
                links_content = generate_links_json_export(links)
                links_mimetype = 'application/json'
            else:
                links_content = generate_links_csv_export(links)
                links_mimetype = 'text/csv'
            files_to_export.append({
                'content': links_content,
                'mimetype': links_mimetype,
                'filename': f'librecrawl{filename_suffix}_{int(time.time())}.{"json" if export_format == "json" else "csv"}'
            })
        if regular_fields:
            if export_format == 'csv':
                regular_content = generate_csv_export(urls, regular_fields)
                regular_mimetype = 'text/csv'
                regular_filename = f'librecrawl{filename_suffix}_{int(time.time())}.csv'
            elif export_format == 'json':
                regular_content = generate_json_export(urls, regular_fields)
                regular_mimetype = 'application/json'
                regular_filename = f'librecrawl{filename_suffix}_{int(time.time())}.json'
            elif export_format == 'xml':
                regular_content = generate_xml_export(urls, regular_fields)
                regular_mimetype = 'application/xml'
                regular_filename = f'librecrawl{filename_suffix}_{int(time.time())}.xml'
            else:
                return jsonify({'success': False, 'error': 'Unsupported export format'})
            files_to_export.append({
                'content': regular_content,
                'mimetype': regular_mimetype,
                'filename': regular_filename
            })
        if not files_to_export:
            if has_issues_export and not issues:
                return jsonify({'success': False, 'error': 'No issues data to export'})
            elif has_links_export and not links:
                return jsonify({'success': False, 'error': 'No links data to export'})
            else:
                return jsonify({'success': False, 'error': 'No data to export'})
        if len(files_to_export) > 1:
            return jsonify({'success': True, 'multiple_files': True, 'files': files_to_export})
        else:
            file_data = files_to_export[0]
            return jsonify({'success': True, 'content': file_data['content'], 'mimetype': file_data['mimetype'], 'filename': file_data['filename']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ── Debug ───────────────────────────────────────────────────────

@api_bp.route('/api/debug/memory')
@login_required
def debug_memory():
    with instances_lock:
        memory_stats = {'total_instances': len(crawler_instances), 'instances': []}
        for session_id, instance_data in crawler_instances.items():
            crawler = instance_data['crawler']
            stats = crawler.memory_monitor.get_stats()
            memory_stats['instances'].append({
                'session_id': session_id[:8] + '...',
                'last_accessed': instance_data['last_accessed'].isoformat(),
                'urls_crawled': len(crawler.crawl_results),
                'memory': stats,
                'data_sizes': crawler.user_memory.get_stats()
            })
        return jsonify(memory_stats)

@api_bp.route('/api/debug/memory/profile')
@login_required
def debug_memory_profile():
    with instances_lock:
        profiles = []
        for session_id, instance_data in crawler_instances.items():
            crawler = instance_data['crawler']
            breakdown = memory_profiler_mod.MemoryProfiler.get_object_memory_breakdown()
            profiles.append({
                'session_id': session_id[:8] + '...',
                'urls_crawled': len(crawler.crawl_results),
                'object_breakdown': breakdown,
                'data_sizes': crawler.user_memory.get_stats()
            })
        return jsonify({'total_instances': len(crawler_instances), 'profiles': profiles})


