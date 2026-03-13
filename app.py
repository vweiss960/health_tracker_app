import os
import re
import secrets
from datetime import timedelta, date, datetime, timezone
from flask import Flask, request as flask_request, g
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import db, User

app = Flask(__name__, static_folder='static', template_folder='templates')

# --- Reverse proxy support ---
# When behind a reverse proxy (nginx, Caddy, etc.), trust X-Forwarded-For headers
# so that request.remote_addr reflects the real client IP.
_proxy_count = int(os.environ.get('PROXY_COUNT', '0'))
if _proxy_count > 0:
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=_proxy_count, x_proto=1, x_host=1)

# --- SECRET_KEY: require a real secret in production ---
_secret = os.environ.get('SECRET_KEY', '')
if not _secret or _secret == 'change-me-in-production':
    if os.environ.get('FLASK_ENV') == 'development':
        _secret = 'dev-only-insecure-key'
    else:
        _secret = secrets.token_hex(32)
        print("WARNING: No SECRET_KEY set. Generated a random key — sessions will not persist across restarts. Set SECRET_KEY in your environment.")
app.config['SECRET_KEY'] = _secret

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////app/data/health_tracker.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB upload limit

# --- Secure session cookies ---
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['REMEMBER_COOKIE_HTTPONLY'] = True
app.config['REMEMBER_COOKIE_SAMESITE'] = 'Lax'
if os.environ.get('HTTPS_ENABLED', '').lower() in ('1', 'true', 'yes'):
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['REMEMBER_COOKIE_SECURE'] = True

# --- CSRF protection ---
csrf = CSRFProtect(app)

# --- Rate limiting ---
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri="memory://",
)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def _resolve_today():
    """Resolve today's date from cookie, then zoneinfo, then server clock."""
    # 1. Trust the browser's date cookie
    try:
        client_date = flask_request.cookies.get('client_today', '')
        if client_date and re.match(r'^\d{4}-\d{2}-\d{2}$', client_date):
            return datetime.strptime(client_date, '%Y-%m-%d').date()
    except RuntimeError:
        pass

    # 2. Fall back to zoneinfo
    try:
        from flask_login import current_user as cu
        if cu and cu.is_authenticated and cu.tz:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(cu.tz)).date()
    except Exception:
        pass

    # 3. Last resort
    return date.today()


def user_today(tz_name=None):
    """Return today's date in the user's timezone. Uses cached g.today if available."""
    try:
        if hasattr(g, 'client_date'):
            return g.client_date
    except RuntimeError:
        pass
    return _resolve_today()


@app.before_request
def _set_client_date():
    """Parse the client_today cookie once per request and cache in g."""
    g.client_date = _resolve_today()


# Register blueprints
from routes.auth import auth_bp
from routes.metrics import metrics_bp
from routes.food import food_bp
from routes.training import training_bp
from routes.ai_chat import ai_bp
from routes.settings import settings_bp
from routes.photos import photos_bp
from routes.resources import resources_bp
from routes.meal_plan import meal_plan_bp
from routes.motivation import motivation_bp
from routes.admin import admin_bp

app.register_blueprint(auth_bp)
# Rate-limit auth endpoints
limiter.limit("10 per minute")(app.view_functions['auth.login'])
limiter.limit("5 per minute")(app.view_functions['auth.register'])
app.register_blueprint(metrics_bp, url_prefix='/metrics')
app.register_blueprint(food_bp, url_prefix='/food')
app.register_blueprint(training_bp, url_prefix='/training')
app.register_blueprint(ai_bp, url_prefix='/ai')
app.register_blueprint(settings_bp, url_prefix='/settings')
app.register_blueprint(photos_bp, url_prefix='/photos')
app.register_blueprint(resources_bp, url_prefix='/resources')
app.register_blueprint(meal_plan_bp, url_prefix='/meal-plan')
app.register_blueprint(motivation_bp, url_prefix='/motivation')
app.register_blueprint(admin_bp, url_prefix='/admin')


@app.context_processor
def inject_helpers():
    today_val = g.client_date.isoformat() if hasattr(g, 'client_date') else date.today().isoformat()
    return {'import_timedelta': timedelta, 'today': today_val, 'server_today': today_val}


@app.after_request
def _set_security_headers(response):
    """Add security headers to every response."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://www.youtube.com https://s.ytimg.com; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https://i.ytimg.com; "
        "frame-src https://www.youtube.com; "
        "connect-src 'self'; "
        "font-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    if os.environ.get('HTTPS_ENABLED', '').lower() in ('1', 'true', 'yes'):
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response

def _migrate_db():
    """Add missing columns to existing tables for schema upgrades."""
    import sqlite3
    db_uri = app.config['SQLALCHEMY_DATABASE_URI']
    if not db_uri.startswith('sqlite'):
        return
    # Extract file path from sqlite URI (sqlite:////app/data/health_tracker.db)
    db_path = db_uri.replace('sqlite:///', '', 1)
    if not os.path.exists(db_path):
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Define migrations: (table, column, type, default)
    migrations = [
        ('users', 'health_goals', 'TEXT', None),
        ('users', 'fitness_level', 'VARCHAR(20)', None),
        ('users', 'dietary_restrictions', 'VARCHAR(500)', None),
        ('chat_messages', 'conversation_id', 'INTEGER', None),
        ('users', 'calorieninjas_api_key', 'VARCHAR(256)', None),
        ('users', 'youtube_api_key', 'VARCHAR(256)', None),
        ('users', 'tz', 'VARCHAR(64)', None),
        ('users', 'is_admin', 'BOOLEAN', None),
        ('users', 'must_change_password', 'BOOLEAN', None),
    ]
    for table, column, col_type, default in migrations:
        cursor.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in cursor.fetchall()]
        if column not in existing:
            default_clause = f" DEFAULT '{default}'" if default else ""
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")

    # Fix boolean columns: normalize NULLs to 0 (only for rows that were never explicitly set)
    cursor.execute("UPDATE users SET is_admin = 0 WHERE is_admin IS NULL")
    cursor.execute("UPDATE users SET must_change_password = 0 WHERE must_change_password IS NULL")

    conn.commit()
    conn.close()


with app.app_context():
    _migrate_db()
    db.create_all()

    # Auto-promote a user to admin via env var (for initial setup)
    _admin_user = os.environ.get('ADMIN_USER', '').strip()
    if _admin_user:
        _u = User.query.filter_by(username=_admin_user).first()
        if _u:
            _u.is_admin = True
            db.session.commit()
            print(f"Ensured '{_admin_user}' is admin.")

@app.cli.command('make-admin')
def make_admin_cmd():
    """Promote a user to admin. Usage: flask make-admin"""
    import click
    username = click.prompt('Username to promote')
    user = User.query.filter_by(username=username).first()
    if not user:
        click.echo(f'User "{username}" not found.')
        return
    user.is_admin = True
    db.session.commit()
    click.echo(f'User "{username}" is now an admin.')


if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=8080, debug=debug_mode)
