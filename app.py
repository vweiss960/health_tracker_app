import os
from datetime import timedelta, date
from flask import Flask
from flask_login import LoginManager
from models import db, User

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:////app/data/health_tracker.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Register blueprints
from routes.auth import auth_bp
from routes.metrics import metrics_bp
from routes.food import food_bp
from routes.training import training_bp
from routes.ai_chat import ai_bp
from routes.settings import settings_bp
from routes.photos import photos_bp
from routes.resources import resources_bp

app.register_blueprint(auth_bp)
app.register_blueprint(metrics_bp, url_prefix='/metrics')
app.register_blueprint(food_bp, url_prefix='/food')
app.register_blueprint(training_bp, url_prefix='/training')
app.register_blueprint(ai_bp, url_prefix='/ai')
app.register_blueprint(settings_bp, url_prefix='/settings')
app.register_blueprint(photos_bp, url_prefix='/photos')
app.register_blueprint(resources_bp, url_prefix='/resources')

@app.context_processor
def inject_helpers():
    return {'import_timedelta': timedelta, 'today': date.today().isoformat()}

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
    ]
    for table, column, col_type, default in migrations:
        cursor.execute(f"PRAGMA table_info({table})")
        existing = [row[1] for row in cursor.fetchall()]
        if column not in existing:
            default_clause = f" DEFAULT '{default}'" if default else ""
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}")

    conn.commit()
    conn.close()


with app.app_context():
    _migrate_db()
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
