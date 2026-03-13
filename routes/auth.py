import re
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, LoginAttempt, BlockedIP, GeoCache, UserSession

auth_bp = Blueprint('auth', __name__)

FAIL_THRESHOLD = 30  # block after this many failures


def _geolocate_ip(ip):
    """Look up IP geolocation, using cache first. Returns a GeoCache row."""
    if not ip or ip.startswith('127.') or ip.startswith('10.') or ip.startswith('192.168.') or ip == '::1':
        # Private/local IPs won't resolve — return a stub
        cached = GeoCache.query.filter_by(ip_address=ip).first()
        if not cached:
            cached = GeoCache(ip_address=ip, country='Local', city='Local Network')
            db.session.add(cached)
            db.session.commit()
        return cached

    cached = GeoCache.query.filter_by(ip_address=ip).first()
    if cached:
        return cached

    # Look up via ip-api.com (free, no key, 45 req/min)
    try:
        import requests as req_lib
        resp = req_lib.get(f'http://ip-api.com/json/{ip}', timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'success':
                cached = GeoCache(
                    ip_address=ip,
                    country=data.get('country', ''),
                    region=data.get('regionName', ''),
                    city=data.get('city', ''),
                    isp=data.get('isp', ''),
                    lat=data.get('lat'),
                    lon=data.get('lon'),
                )
                db.session.add(cached)
                db.session.commit()
                return cached
    except Exception:
        pass

    # If lookup fails, cache a stub so we don't retry constantly
    cached = GeoCache(ip_address=ip, country='Unknown')
    db.session.add(cached)
    db.session.commit()
    return cached


def _record_session(user, ip):
    """Record or update a user login session."""
    ua = request.headers.get('User-Agent', '')[:500]
    session = UserSession(
        user_id=user.id,
        ip_address=ip,
        user_agent=ua,
    )
    db.session.add(session)
    db.session.commit()
    # Trigger geo lookup in background (caches for later)
    _geolocate_ip(ip)


def _record_fail(ip, username=''):
    """Record a failed login attempt and block the IP if threshold is reached."""
    attempt = LoginAttempt(ip_address=ip, username_tried=username)
    db.session.add(attempt)
    db.session.commit()

    # Count recent failures for this IP (last 24 hours)
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    fail_count = LoginAttempt.query.filter(
        LoginAttempt.ip_address == ip,
        LoginAttempt.created_at >= since
    ).count()

    if fail_count >= FAIL_THRESHOLD:
        existing = BlockedIP.query.filter_by(ip_address=ip).first()
        if not existing:
            blocked = BlockedIP(
                ip_address=ip,
                fail_count=fail_count,
                reason=f'Auto-blocked: {fail_count} failed login attempts in 24h'
            )
            db.session.add(blocked)
            db.session.commit()


def _is_blocked(ip):
    """Check if an IP is blocked."""
    return BlockedIP.query.filter_by(ip_address=ip).first() is not None


@auth_bp.before_app_request
def _check_blocked_ip():
    """Block requests from banned IPs (allow admin panel so admins can unblock)."""
    remote = request.remote_addr or ''
    if remote and _is_blocked(remote):
        # Allow admin routes so local admins can unblock
        if request.endpoint and request.endpoint.startswith('admin.'):
            return
        return 'Your IP has been blocked due to too many failed login attempts. Contact an administrator.', 403


@auth_bp.before_app_request
def _force_password_change():
    """Redirect users with must_change_password to the change-password page."""
    if current_user.is_authenticated and getattr(current_user, 'must_change_password', False) is True:
        allowed = ('auth.change_password', 'auth.logout', 'auth.set_timezone', 'static')
        if request.endpoint not in allowed:
            return redirect(url_for('auth.change_password'))


# Username: 3-30 chars, alphanumeric + underscores/hyphens
_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,30}$')


def _validate_password(password):
    """Return an error message if the password is too weak, else None."""
    if len(password) < 8:
        return 'Password must be at least 8 characters'
    if not re.search(r'[A-Z]', password):
        return 'Password must contain at least one uppercase letter'
    if not re.search(r'[a-z]', password):
        return 'Password must contain at least one lowercase letter'
    if not re.search(r'[0-9]', password):
        return 'Password must contain at least one number'
    return None


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('metrics.dashboard'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            _record_session(user, request.remote_addr or '')
            if user.must_change_password:
                return redirect(url_for('auth.change_password'))
            return redirect(url_for('metrics.dashboard'))
        _record_fail(request.remote_addr or '', username)
        flash('Invalid username or password', 'error')
    import os
    reg_disabled = os.environ.get('DISABLE_REGISTRATION', '').lower() in ('1', 'true', 'yes')
    return render_template('login.html', reg_disabled=reg_disabled)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    import os
    if os.environ.get('DISABLE_REGISTRATION', '').lower() in ('1', 'true', 'yes'):
        flash('Registration is currently disabled', 'error')
        return redirect(url_for('auth.login'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        display_name = request.form.get('display_name', '').strip() or username

        if not username or not password:
            flash('Username and password are required', 'error')
        elif not _USERNAME_RE.match(username):
            flash('Username must be 3-30 characters (letters, numbers, hyphens, underscores)', 'error')
        elif User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
        else:
            pw_error = _validate_password(password)
            if pw_error:
                flash(pw_error, 'error')
            else:
                user = User(
                    username=username,
                    password_hash=generate_password_hash(password),
                    display_name=display_name
                )
                db.session.add(user)
                db.session.commit()
                login_user(user)
                return redirect(url_for('metrics.dashboard'))
    return render_template('register.html')


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
        else:
            pw_error = _validate_password(new_password)
            if pw_error:
                flash(pw_error, 'error')
            else:
                current_user.password_hash = generate_password_hash(new_password)
                current_user.must_change_password = False
                db.session.commit()
                flash('Password updated successfully', 'success')
                return redirect(url_for('metrics.dashboard'))
    return render_template('change_password.html')


@auth_bp.route('/debug-date')
@login_required
def debug_date():
    import os
    if os.environ.get('FLASK_ENV') != 'development':
        return jsonify({'error': 'Not available in production'}), 403
    from datetime import date, datetime
    from flask import g
    from app import user_today
    cookie_val = request.cookies.get('client_today', '(none)')
    tz_val = current_user.tz or '(none)'
    server_date = date.today().isoformat()
    g_date = g.client_date.isoformat() if hasattr(g, 'client_date') else '(not set)'
    user_date = user_today(current_user.tz).isoformat()
    try:
        from zoneinfo import ZoneInfo
        zi_date = datetime.now(ZoneInfo(current_user.tz)).date().isoformat() if current_user.tz else '(no tz set)'
    except Exception as e:
        zi_date = f'error: {e}'
    return jsonify({
        'cookie_client_today': cookie_val,
        'g_client_date': g_date,
        'user_today_result': user_date,
        'server_date_today': server_date,
        'zoneinfo_date': zi_date,
        'user_tz_in_db': tz_val,
        'TZ_env': os.environ.get('TZ', '(not set)'),
    })


@auth_bp.route('/set-timezone', methods=['POST'])
@login_required
def set_timezone():
    tz = request.get_json(silent=True) or {}
    tz_name = tz.get('timezone', '')
    if tz_name and len(tz_name) <= 64:
        # Validate it's a real timezone
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(tz_name)
            current_user.tz = tz_name
            db.session.commit()
        except Exception:
            pass
    return jsonify({'ok': True})


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
