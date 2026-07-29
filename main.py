import threading
import time
import webbrowser
import argparse
import secrets
import os
import signal
import sys
from datetime import datetime

from flask import Flask
from flask_compress import Compress
from dotenv import load_dotenv

from routes import (
    init_routes_config, crawler_instances, instances_lock, start_cleanup_thread
)
from routes.auth import auth_bp, pages_bp
from routes.api import api_bp
from src.crawler import WebCrawler
from src.auth_db import init_db
from src.log_tracker import log_tracker
import logging
logger = logging.getLogger(__name__)

load_dotenv()

parser = argparse.ArgumentParser(description='LibreCrawl - SEO Spider Tool')
parser.add_argument('--local', '-l', action='store_true',
                    help='Run in local mode (all users get admin tier, no rate limits)')
parser.add_argument('--disable-register', '-dr', action='store_true',
                    help='Disable new user registrations')
parser.add_argument('--disable-guest', '-dg', action='store_true',
                    help='Disable guest login')
parser.add_argument('--demo', '-dm', action='store_true',
                    help='Demo mode: 1.5GB memory limit per user, crawls auto-stop at limit')
parser.add_argument('--dangerously-skip-auth', '-dsa', action='store_true',
                    help='DANGEROUS: Allow anyone to log in as any username with no password. '
                         'The username is only used to separate per-user sessions. '
                         'Do NOT use on a public network or in production.')
args = parser.parse_args()

LOCAL_MODE = args.local or os.getenv('LOCAL_MODE', '').lower() in ('true', '1', 'yes')
DISABLE_REGISTER = args.disable_register or os.getenv('REGISTRATION_DISABLED', '').lower() in ('true', '1', 'yes')
DISABLE_GUEST = args.disable_guest or os.getenv('DISABLE_GUEST', '').lower() in ('true', '1', 'yes')
DEMO_MODE = args.demo or os.getenv('DEMO_MODE', '').lower() in ('true', '1', 'yes')
SKIP_AUTH = args.dangerously_skip_auth or os.getenv('DANGEROUSLY_SKIP_AUTH', '').lower() in ('true', '1', 'yes')

init_routes_config(LOCAL_MODE, DISABLE_REGISTER, DISABLE_GUEST, DEMO_MODE, SKIP_AUTH)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
if not os.environ.get('SECRET_KEY'):
    logger.warning('SECRET_KEY not set — using an ephemeral random key. '
          'Sessions will not persist across restarts. Set SECRET_KEY in production.')

Compress(app)

app.register_blueprint(auth_bp)
app.register_blueprint(pages_bp)
app.register_blueprint(api_bp)

@app.after_request
def add_no_cache_header(response):
    if response.content_type and 'text/html' in response.content_type:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
    return response

init_db()

if LOCAL_MODE:
    logger.info("LOCAL MODE ENABLED — All users get admin tier, no password required")
if DISABLE_REGISTER:
    logger.info("REGISTRATION DISABLED")
if DISABLE_GUEST:
    logger.info("GUEST MODE DISABLED")
if DEMO_MODE:
    logger.info("DEMO MODE ENABLED — 1.5GB memory limit per user")
if SKIP_AUTH:
    logger.info("DANGEROUSLY SKIP AUTH ENABLED — Anyone can log in as any username!")

def recover_crashed_crawls():
    try:
        from src.crawl_db import get_crashed_crawls, set_crawl_status, fix_stopped_to_completed, cleanup_crawl_logs
        fix_stopped_to_completed()
        crashed = get_crashed_crawls()
        if crashed:
            logger.info("CRASH RECOVERY — Auto-resuming active crawls")
            recovered_count = 0
            for crawl in crashed:
                urls_disc = crawl.get('urls_discovered') or 0
                urls_crawl = crawl.get('urls_crawled') or 0
                if urls_disc == 0 and urls_crawl == 0:
                    set_crawl_status(crawl['id'], 'failed')
                    cleanup_crawl_logs(crawl['id'])
                    log_tracker.warn('system', f'Pemulihan dilewati: {crawl["base_url"]} — tidak ada URL',
                                        crawl_id=crawl['id'], status='failed')
                    continue
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
                        log_tracker.info('system', f'Pemulihan crash: audit {crawl["base_url"]} dilanjutkan',
                                          crawl_id=crawl['id'], status='running')
                    else:
                        set_crawl_status(crawl['id'], 'failed')
                        cleanup_crawl_logs(crawl['id'])
                        log_tracker.error('system', f'Pemulihan crash gagal: {crawl["base_url"]} — {message}',
                                           crawl_id=crawl['id'], status='failed')
                except Exception as e:
                    set_crawl_status(crawl['id'], 'failed')
                    cleanup_crawl_logs(crawl['id'])
            if recovered_count:
                logger.info(f"Recovered {recovered_count}/{len(crashed)} crawls")
    except Exception as e:
        logger.error(f"Error during crash recovery: {e}")

def graceful_shutdown(signum, frame):
    logger.info("GRACEFUL SHUTDOWN — Saving all active crawls...")
    log_tracker.info('system', 'Server dimatikan — menyimpan semua audit...')
    try:
        with instances_lock:
            for session_id, instance_data in list(crawler_instances.items()):
                crawler = instance_data['crawler']
                if crawler.is_running and crawler.crawl_id and crawler.db_save_enabled:
                    try:
                        crawler._save_batch_to_db(force=True)
                        crawler._save_queue_checkpoint()
                        from src.crawl_db import set_crawl_status
                        set_crawl_status(crawler.crawl_id, 'stopped')
                    except Exception as e:
                        pass
        log_tracker.info('system', 'Semua audit tersimpan — sampai jumpa')
    except Exception as e:
        pass
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    recover_crashed_crawls()
    start_cleanup_thread()

    port = int(os.environ.get('PORT', 5001))
    log_tracker.seed_from_db()
    log_tracker.info('system', f'Server berjalan di port {port}')

    logger.info("LibreCrawl - SEO Spider Tool")
    logger.info(f"Server starting on http://0.0.0.0:{port}")
    logger.info(f"Access from browser: http://localhost:{port}")

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f'http://localhost:{port}')

    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    from waitress import serve
    serve(app, host='0.0.0.0', port=port, threads=8)

if __name__ == '__main__':
    main()
