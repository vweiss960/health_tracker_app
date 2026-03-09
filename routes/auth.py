from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User

auth_bp = Blueprint('auth', __name__)


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
            return redirect(url_for('metrics.dashboard'))
        flash('Invalid username or password', 'error')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        display_name = request.form.get('display_name', '').strip() or username

        if not username or not password:
            flash('Username and password are required', 'error')
        elif User.query.filter_by(username=username).first():
            flash('Username already exists', 'error')
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


@auth_bp.route('/debug-date')
@login_required
def debug_date():
    from datetime import date, datetime
    from flask import g
    from app import user_today
    import os
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
