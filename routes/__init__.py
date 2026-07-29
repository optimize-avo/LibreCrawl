import threading
import time
import csv
import json
import xml.etree.ElementTree as ET
import uuid
import os
from io import StringIO
from datetime import datetime, timedelta
from functools import wraps
from fnmatch import fnmatch
from urllib.parse import urlparse

from flask import request, session, jsonify, redirect, url_for, Blueprint
from src.log_tracker import log_tracker
from src.utils import lazy

crawler_mod = lazy('src.crawler')
settings_mod = lazy('src.settings_manager')
crawl_db = lazy('src.crawl_db')

crawler_instances = {}
instances_lock = threading.Lock()

class _Config:
    LOCAL_MODE = False
    DISABLE_REGISTER = False
    DISABLE_GUEST = False
    DEMO_MODE = False
    SKIP_AUTH = False

cfg = _Config()

def init_routes_config(local, disable_register, disable_guest, demo, skip_auth):
    cfg.LOCAL_MODE = local
    cfg.DISABLE_REGISTER = disable_register
    cfg.DISABLE_GUEST = disable_guest
    cfg.DEMO_MODE = demo
    cfg.SKIP_AUTH = skip_auth

def get_client_ip():
    if 'CF-Connecting-IP' in request.headers:
        return request.headers['CF-Connecting-IP']
    if 'X-Forwarded-For' in request.headers:
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    if 'X-Real-IP' in request.headers:
        return request.headers['X-Real-IP']
    return request.remote_addr

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
            return redirect(url_for('auth.login_page'))
        return f(*args, **kwargs)
    return decorated_function

def get_or_create_crawler():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    session_id = session['session_id']
    user_id = session.get('user_id')
    tier = session.get('tier', 'guest')
    current_crawl_id = session.get('current_crawl_id')

    with instances_lock:
        if session_id not in crawler_instances:
            existing_instance = None
            if current_crawl_id:
                for sid, instance_data in list(crawler_instances.items()):
                    c = instance_data['crawler']
                    if hasattr(c, 'crawl_id') and c.crawl_id == current_crawl_id:
                        existing_instance = instance_data
                        if sid != session_id and sid in crawler_instances:
                            del crawler_instances[sid]
                        crawler_instances[session_id] = instance_data
                        instance_data['last_accessed'] = datetime.now()
                        break

            if not existing_instance:
                crawler = crawler_mod.WebCrawler()
                crawler_instances[session_id] = {
                    'crawler': crawler,
                    'settings': settings_mod.SettingsManager(session_id=session_id, user_id=user_id, tier=tier),
                    'last_accessed': datetime.now()
                }
                if current_crawl_id:
                    try:
                        crawl_info = crawl_db.get_crawl_by_id(current_crawl_id)
                        if crawl_info and crawl_info.get('status') in ('completed', 'paused', 'failed'):
                            if crawl_info['status'] == 'completed':
                                success, msg = crawler.load_completed_crawl(current_crawl_id, user_id=user_id)
                            else:
                                success, msg = crawler.resume_from_database(current_crawl_id, user_id=user_id, session_id=session_id)
                            if not success:
                                session.pop('current_crawl_id', None)
                        elif crawl_info and crawl_info.get('status') == 'running':
                            success, msg = crawler.resume_from_database(current_crawl_id, user_id=user_id, session_id=session_id)
                            if not success:
                                session.pop('current_crawl_id', None)
                    except Exception as e:
                        session.pop('current_crawl_id', None)
        else:
            crawler_instances[session_id]['last_accessed'] = datetime.now()

        return crawler_instances[session_id]['crawler']

def get_session_settings():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    session_id = session['session_id']
    user_id = session.get('user_id')
    tier = session.get('tier', 'guest')

    with instances_lock:
        if session_id not in crawler_instances:
            crawler_instances[session_id] = {
                'crawler': crawler_mod.WebCrawler(),
                'settings': settings_mod.SettingsManager(session_id=session_id, user_id=user_id, tier=tier),
                'last_accessed': datetime.now()
            }
        else:
            crawler_instances[session_id]['last_accessed'] = datetime.now()
        return crawler_instances[session_id]['settings']

def cleanup_old_logs():
    try:
        crawl_db.cleanup_old_logs(retention_days=7)
    except Exception as e:
        pass

def cleanup_old_instances():
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
            if crawler.is_running:
                continue
            log_tracker.info('system', f'Membersihkan sesi idle {session_id[:8]}...',
                              crawl_id=getattr(crawler, 'crawl_id', None))
            del crawler_instances[session_id]

def start_cleanup_thread():
    def cleanup_loop():
        while True:
            time.sleep(300)
            try:
                cleanup_old_instances()
                cleanup_old_logs()
            except Exception as e:
                pass
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

def generate_csv_export(urls, fields):
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for url_data in urls:
        row = {}
        for field in fields:
            value = url_data.get(field, '')
            if field == 'analytics' and isinstance(value, dict):
                analytics_list = []
                if value.get('gtag') or value.get('ga4_id'): analytics_list.append('GA4')
                if value.get('google_analytics'): analytics_list.append('GA')
                if value.get('gtm_id'): analytics_list.append('GTM')
                if value.get('facebook_pixel'): analytics_list.append('FB')
                if value.get('hotjar'): analytics_list.append('HJ')
                if value.get('mixpanel'): analytics_list.append('MP')
                row[field] = ', '.join(analytics_list)
            elif field == 'og_tags' and isinstance(value, dict):
                row[field] = f"{len(value)} tags" if value else ''
            elif field == 'twitter_tags' and isinstance(value, dict):
                row[field] = f"{len(value)} tags" if value else ''
            elif field == 'json_ld' and isinstance(value, list):
                row[field] = f"{len(value)} scripts" if value else ''
            elif field == 'images' and isinstance(value, list):
                row[field] = f"{len(value)} images" if value else ''
            elif field == 'internal_links' and isinstance(value, (int, float)):
                row[field] = f"{int(value)} internal links" if value else '0 internal links'
            elif field == 'external_links' and isinstance(value, (int, float)):
                row[field] = f"{int(value)} external links" if value else '0 external links'
            elif field == 'h2' and isinstance(value, list):
                row[field] = ', '.join(value[:3]) + ('...' if len(value) > 3 else '')
            elif field == 'h3' and isinstance(value, list):
                row[field] = ', '.join(value[:3]) + ('...' if len(value) > 3 else '')
            elif isinstance(value, (dict, list)):
                row[field] = str(value)
            else:
                row[field] = value
        writer.writerow(row)
    return output.getvalue()

def generate_json_export(urls, fields):
    filtered_urls = []
    for url_data in urls:
        filtered_data = {}
        for field in fields:
            value = url_data.get(field, '')
            filtered_data[field] = value
        filtered_urls.append(filtered_data)
    return json.dumps({
        'export_date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_urls': len(filtered_urls),
        'fields': fields,
        'data': filtered_urls
    }, indent=2, default=str)

def generate_xml_export(urls, fields):
    root = ET.Element('librecrawl_export')
    root.set('export_date', time.strftime('%Y-%m-%d %H:%M:%S'))
    root.set('total_urls', str(len(urls)))
    urls_element = ET.SubElement(root, 'urls')
    for url_data in urls:
        url_element = ET.SubElement(urls_element, 'url')
        for field in fields:
            field_element = ET.SubElement(url_element, field)
            field_element.text = str(url_data.get(field, ''))
    return ET.tostring(root, encoding='unicode')

def generate_links_csv_export(links):
    output = StringIO()
    fieldnames = ['source_url', 'target_url', 'anchor_text', 'is_internal', 'target_domain', 'target_status', 'placement']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for link in links:
        row = {
            'source_url': link.get('source_url', ''),
            'target_url': link.get('target_url', ''),
            'anchor_text': link.get('anchor_text', ''),
            'is_internal': 'Yes' if link.get('is_internal') else 'No',
            'target_domain': link.get('target_domain', ''),
            'target_status': link.get('target_status', 'Not crawled'),
            'placement': link.get('placement', 'body')
        }
        writer.writerow(row)
    return output.getvalue()

def generate_links_json_export(links):
    return json.dumps(links, indent=2)

def generate_issues_csv_export(issues):
    output = StringIO()
    fieldnames = ['url', 'type', 'category', 'issue', 'details']
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for issue in issues:
        row = {
            'url': issue.get('url', ''),
            'type': issue.get('type', ''),
            'category': issue.get('category', ''),
            'issue': issue.get('issue', ''),
            'details': issue.get('details', '')
        }
        writer.writerow(row)
    return output.getvalue()

def generate_issues_json_export(issues):
    issues_by_url = {}
    for issue in issues:
        url = issue.get('url', '')
        if url not in issues_by_url:
            issues_by_url[url] = []
        issues_by_url[url].append({
            'type': issue.get('type', ''),
            'category': issue.get('category', ''),
            'issue': issue.get('issue', ''),
            'details': issue.get('details', '')
        })
    return json.dumps({
        'export_date': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_issues': len(issues),
        'total_urls_with_issues': len(issues_by_url),
        'issues_by_url': issues_by_url,
        'all_issues': issues
    }, indent=2)

def filter_issues_by_exclusion_patterns(issues, exclusion_patterns):
    if not exclusion_patterns:
        return issues
    filtered_issues = []
    for issue in issues:
        url = issue.get('url', '')
        parsed = urlparse(url)
        path = parsed.path
        should_exclude = False
        for pattern in exclusion_patterns:
            if not pattern.strip() or pattern.strip().startswith('#'):
                continue
            if '*' in pattern:
                if fnmatch(path, pattern):
                    should_exclude = True
                    break
            elif path == pattern or path.startswith(pattern.rstrip('*')):
                should_exclude = True
                break
        if not should_exclude:
            filtered_issues.append(issue)
    return filtered_issues

def crawler_info_to_response(crawl_info, status_data=None):
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
