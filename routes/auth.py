from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for

from routes import (
    login_required, get_or_create_crawler, get_session_settings,
    get_client_ip, cfg,
    crawler_instances, instances_lock, filter_issues_by_exclusion_patterns
)
from src.log_tracker import log_tracker
from src.utils import lazy

auth_db = lazy('src.auth_db')

auth_bp = Blueprint('auth', __name__)
pages_bp = Blueprint('pages', __name__)

def generate_random_password(length=16):
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def skip_auth_login(username):
    import sqlite3
    import os
    try:
        conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'users.db'))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, username FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if user:
            user_id = user['id']
        else:
            random_password = generate_random_password()
            password_hash = auth_db.hash_password(random_password)
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, verified, tier)
                VALUES (?, ?, ?, 1, 'admin')
            ''', (username, f'{username}@skipauth.local', password_hash))
            conn.commit()
            user_id = cursor.lastrowid
        conn.close()
        session['user_id'] = user_id
        session['username'] = username
        session['tier'] = 'admin'
        session.permanent = True
        return True, 'Logged in (authentication skipped)'
    except sqlite3.IntegrityError as e:
        return False, f'Username conflict: try a different username ({e})'
    except Exception as e:
        return False, f'Login error: {str(e)}'

@pages_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login_page'))
    user = auth_db.get_user_by_id(session.get('user_id'))
    return render_template('index.html', user=user)

@pages_bp.route('/dashboard')
@login_required
def dashboard():
    user = auth_db.get_user_by_id(session.get('user_id'))
    return render_template('dashboard.html', user=user)

@pages_bp.route('/settings')
@login_required
def settings_page():
    user = auth_db.get_user_by_id(session.get('user_id'))
    return render_template('settings.html', user=user)

@pages_bp.route('/compare')
@login_required
def compare_page():
    user = auth_db.get_user_by_id(session.get('user_id'))
    return render_template('compare.html', user=user)

@pages_bp.route('/debug/memory')
@login_required
def debug_memory_page():
    return render_template('debug_memory.html')

@pages_bp.route('/logs')
@login_required
def logs_page():
    return render_template('logs.html')

@auth_bp.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('pages.index'))
    if cfg.LOCAL_MODE:
        return render_template('login.html', registration_disabled=True, guest_disabled=True, skip_auth=True, local_mode=True)
    return render_template('login.html', registration_disabled=cfg.DISABLE_REGISTER, guest_disabled=cfg.DISABLE_GUEST, skip_auth=cfg.SKIP_AUTH)

@auth_bp.route('/register')
def register_page():
    if 'user_id' in session:
        return redirect(url_for('pages.index'))
    if cfg.LOCAL_MODE:
        return redirect(url_for('auth.login_page'))
    return render_template('register.html', registration_disabled=cfg.DISABLE_REGISTER)

@auth_bp.route('/verify')
def verify_email():
    token = request.args.get('token')
    if not token:
        return render_template('verification_result.html', success=False, message='Invalid verification link', app_source='main')
    from src.email_service import send_welcome_email
    import os
    success, message, app_source, user_email = auth_db.verify_token(token)
    if success and user_email:
        try:
            user = auth_db.get_user_by_email(user_email)
            if user:
                send_welcome_email(user_email, user['username'], app_source or 'main')
        except Exception as e:
            pass
    redirect_url = None
    if success:
        if app_source == 'workshop':
            redirect_url = os.getenv('WORKSHOP_APP_URL', 'https://workshop.librecrawl.com')
        else:
            redirect_url = url_for('auth.login_page')
    return render_template('verification_result.html', success=success, message=message, app_source=app_source or 'main', redirect_url=redirect_url)

@auth_bp.route('/api/register', methods=['POST'])
def register():
    if cfg.DISABLE_REGISTER:
        return jsonify({'success': False, 'message': 'Registration is currently disabled'})
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    from src.email_service import send_verification_email
    import sqlite3, os
    success, message, user_id = auth_db.create_user(username, email, password)
    if success and cfg.LOCAL_MODE:
        try:
            conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'users.db'))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            conn.close()
            if user:
                auth_db.verify_user(user['id'])
                auth_db.set_user_tier(user['id'], 'admin')
                message = 'Account created and verified! You have admin access in local mode.'
        except Exception as e:
            pass
    elif success:
        is_resend = (message == 'resend')
        try:
            token = auth_db.create_verification_token(user_id, app_source='main')
            if token:
                email_success, email_message = send_verification_email(email, username, token, app_source='main', is_resend=is_resend)
                if email_success:
                    message = 'A verification email was already sent to this address. We\'ve updated your account details and sent a new verification link.' if is_resend else 'Registration successful! Please check your email to verify your account.'
                else:
                    message = 'Account created, but we could not send the verification email. Please contact support.'
            else:
                message = 'Account created, but verification token generation failed. Please contact support.'
        except Exception as e:
            message = 'Account created, but we could not send the verification email. Please contact support.'
    return jsonify({'success': success, 'message': message})

@auth_bp.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if cfg.LOCAL_MODE or cfg.SKIP_AUTH:
        if not username:
            return jsonify({'success': False, 'message': 'Username required'})
        if len(username) > 50:
            return jsonify({'success': False, 'message': 'Username must be 50 characters or less'})
        success, message = skip_auth_login(username)
        return jsonify({'success': success, 'message': message})
    success, message, user_data = auth_db.authenticate_user(username, password)
    if success:
        session['user_id'] = user_data['id']
        session['username'] = user_data['username']
        session['tier'] = 'admin' if cfg.LOCAL_MODE else user_data['tier']
        session.permanent = True
    return jsonify({'success': success, 'message': message})

@auth_bp.route('/api/guest-login', methods=['POST'])
def guest_login():
    if cfg.DISABLE_GUEST:
        return jsonify({'success': False, 'message': 'Guest login is disabled'})
    session['user_id'] = None
    session['username'] = 'Guest'
    session['tier'] = 'admin' if cfg.LOCAL_MODE else 'guest'
    session.permanent = False
    return jsonify({'success': True, 'message': 'Logged in as guest'})

@auth_bp.route('/api/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@auth_bp.route('/api/user/info')
@login_required
def user_info():
    user_id = session.get('user_id')
    tier = session.get('tier', 'guest')
    username = session.get('username')
    crawls_today = 0
    if tier == 'guest':
        client_ip = get_client_ip()
        crawls_today = auth_db.get_guest_crawls_last_24h(client_ip)
    else:
        crawls_today = auth_db.get_crawls_last_24h(user_id)
    return jsonify({
        'success': True,
        'user': {
            'id': user_id,
            'username': username,
            'tier': tier,
            'crawls_today': crawls_today,
            'crawls_remaining': max(0, 3 - crawls_today) if tier == 'guest' else -1
        }
    })
