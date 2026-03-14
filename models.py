from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    display_name = db.Column(db.String(120))
    target_weight = db.Column(db.Float)
    target_calories = db.Column(db.Integer)
    health_goals = db.Column(db.Text)  # free-text overall health goals
    fitness_level = db.Column(db.String(20))  # beginner, intermediate, advanced
    dietary_restrictions = db.Column(db.String(500))
    ai_provider = db.Column(db.String(20), default='claude')  # 'claude' or 'openai'
    ai_api_key = db.Column(db.String(256))
    calorieninjas_api_key = db.Column(db.String(256))
    youtube_api_key = db.Column(db.String(256))
    tz = db.Column(db.String(64))  # IANA timezone, e.g. 'America/New_York'
    is_admin = db.Column(db.Boolean, default=False)
    must_change_password = db.Column(db.Boolean, default=False)
    use_system_ai_key = db.Column(db.Boolean, default=False)
    motivation_text = db.Column(db.Text)  # What motivates the user — drives personalized content
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    metrics = db.relationship('BodyMetric', backref='user', lazy=True, cascade='all, delete-orphan')
    food_entries = db.relationship('FoodEntry', backref='user', lazy=True, cascade='all, delete-orphan')
    training_entries = db.relationship('TrainingEntry', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_conversations = db.relationship('ChatConversation', backref='user', lazy=True, cascade='all, delete-orphan')
    chat_messages = db.relationship('ChatMessage', backref='user', lazy=True, cascade='all, delete-orphan')
    training_plans = db.relationship('TrainingPlan', backref='user', lazy=True, cascade='all, delete-orphan')
    meal_plans = db.relationship('MealPlan', backref='user', lazy=True, cascade='all, delete-orphan')
    progress_photos = db.relationship('ProgressPhoto', backref='user', lazy=True, cascade='all, delete-orphan')
    strength_entries = db.relationship('StrengthEntry', backref='user', lazy=True, cascade='all, delete-orphan')


class BodyMetric(db.Model):
    __tablename__ = 'body_metrics'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    weight = db.Column(db.Float)
    belly = db.Column(db.Float)
    waist = db.Column(db.Float)
    chest = db.Column(db.Float)
    arm_left = db.Column(db.Float)
    arm_right = db.Column(db.Float)
    leg_left = db.Column(db.Float)
    leg_right = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class FoodEntry(db.Model):
    __tablename__ = 'food_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    meal_type = db.Column(db.String(20))  # breakfast, lunch, dinner, snack
    food_name = db.Column(db.String(200), nullable=False)
    serving_size = db.Column(db.String(100))
    calories = db.Column(db.Float)
    protein = db.Column(db.Float)
    carbs = db.Column(db.Float)
    fat = db.Column(db.Float)
    fiber = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class ChatConversation(db.Model):
    __tablename__ = 'chat_conversations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(200), default='New Chat')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    messages = db.relationship('ChatMessage', backref='conversation', lazy=True, cascade='all, delete-orphan')


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('chat_conversations.id'), nullable=True)
    role = db.Column(db.String(20), nullable=False)  # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class ProgressPhoto(db.Model):
    __tablename__ = 'progress_photos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    filename = db.Column(db.String(300), nullable=False)
    caption = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class CommonMeal(db.Model):
    __tablename__ = 'common_meals'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    items = db.relationship('CommonMealItem', backref='common_meal', lazy=True, cascade='all, delete-orphan')


class CommonMealItem(db.Model):
    __tablename__ = 'common_meal_items'
    id = db.Column(db.Integer, primary_key=True)
    common_meal_id = db.Column(db.Integer, db.ForeignKey('common_meals.id'), nullable=False)
    food_name = db.Column(db.String(200), nullable=False)
    serving_size = db.Column(db.String(100))
    calories = db.Column(db.Float)
    protein = db.Column(db.Float)
    carbs = db.Column(db.Float)
    fat = db.Column(db.Float)
    fiber = db.Column(db.Float)


class WaterEntry(db.Model):
    __tablename__ = 'water_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    amount_ml = db.Column(db.Float, nullable=False)
    time = db.Column(db.String(10))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class CaffeineEntry(db.Model):
    __tablename__ = 'caffeine_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    amount_mg = db.Column(db.Float, nullable=False)
    source = db.Column(db.String(100))
    time = db.Column(db.String(10))
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class TrainingPlan(db.Model):
    __tablename__ = 'training_plans'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    day_of_week = db.Column(db.String(20), nullable=False)  # monday, tuesday, etc. or 'rest'
    exercise_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))
    sets = db.Column(db.Integer)
    reps = db.Column(db.String(50))  # string to allow ranges like "8-12"
    rest_seconds = db.Column(db.Integer)
    notes = db.Column(db.Text)
    order_index = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class MealPlan(db.Model):
    __tablename__ = 'meal_plans'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    day_of_week = db.Column(db.String(20), nullable=False)  # monday, tuesday, etc.
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast, lunch, dinner, snack
    meal_name = db.Column(db.String(200), nullable=False)
    serving_size = db.Column(db.String(100))
    calories = db.Column(db.Float)
    protein = db.Column(db.Float)
    carbs = db.Column(db.Float)
    fat = db.Column(db.Float)
    fiber = db.Column(db.Float)
    notes = db.Column(db.Text)
    order_index = db.Column(db.Integer, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class LoginAttempt(db.Model):
    __tablename__ = 'login_attempts'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    username_tried = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class BlockedIP(db.Model):
    __tablename__ = 'blocked_ips'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False, index=True)
    fail_count = db.Column(db.Integer, default=0)
    blocked_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reason = db.Column(db.String(200))


class GeoCache(db.Model):
    """Cache IP geolocation lookups to avoid repeated API calls."""
    __tablename__ = 'geo_cache'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False, index=True)
    country = db.Column(db.String(100))
    region = db.Column(db.String(100))
    city = db.Column(db.String(100))
    isp = db.Column(db.String(200))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    looked_up_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class UserSession(db.Model):
    """Track user login sessions with IP and location."""
    __tablename__ = 'user_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)
    user_agent = db.Column(db.String(500))
    logged_in_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user = db.relationship('User', backref=db.backref('sessions', lazy=True))


class SavedPlaylist(db.Model):
    __tablename__ = 'saved_playlists'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    playlist_type = db.Column(db.String(20), default='playlist')  # playlist or video
    youtube_id = db.Column(db.String(100), nullable=False)
    thumbnail = db.Column(db.String(500))
    channel = db.Column(db.String(200))
    search_query = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user = db.relationship('User', backref=db.backref('saved_playlists', lazy=True, cascade='all, delete-orphan'))


class SystemConfig(db.Model):
    """Key-value store for system-wide settings (e.g. backend AI API key)."""
    __tablename__ = 'system_config'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)

    @staticmethod
    def get(key, default=None):
        row = SystemConfig.query.filter_by(key=key).first()
        return row.value if row else default

    @staticmethod
    def set(key, value):
        row = SystemConfig.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            row = SystemConfig(key=key, value=value)
            db.session.add(row)
        db.session.commit()


class DailyMotivation(db.Model):
    """Pre-generated daily motivational content available to all users."""
    __tablename__ = 'daily_motivations'
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, index=True)
    category = db.Column(db.String(50), nullable=False)
    content_json = db.Column(db.Text, nullable=False)  # JSON array of items
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class StrengthEntry(db.Model):
    """Track big-three lifts: bench press, squat, deadlift."""
    __tablename__ = 'strength_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    lift = db.Column(db.String(20), nullable=False)  # 'bench', 'squat', 'deadlift'
    weight = db.Column(db.Float, nullable=False)  # weight lifted
    reps = db.Column(db.Integer, nullable=False)
    body_weight = db.Column(db.Float)  # needed for squat & deadlift relative strength
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def estimated_1rm(self):
        """Epley formula: weight × (1 + reps/30)"""
        if self.reps == 1:
            return self.weight
        return round(self.weight * (1 + self.reps / 30), 1)

    @property
    def relative_strength(self):
        """Estimated 1RM / body weight (for squat & deadlift)."""
        if not self.body_weight or self.body_weight == 0:
            return None
        return round(self.estimated_1rm / self.body_weight, 2)


class BarcodeCache(db.Model):
    """Local cache of barcode nutrition lookups to avoid slow external API calls."""
    __tablename__ = 'barcode_cache'
    id = db.Column(db.Integer, primary_key=True)
    barcode = db.Column(db.String(50), unique=True, nullable=False, index=True)
    product_name = db.Column(db.String(300))
    brand = db.Column(db.String(200))
    serving_size = db.Column(db.String(100))
    calories_per_100g = db.Column(db.Float)
    protein_per_100g = db.Column(db.Float)
    carbs_per_100g = db.Column(db.Float)
    fat_per_100g = db.Column(db.Float)
    fiber_per_100g = db.Column(db.Float)
    image_url = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class TrainingEntry(db.Model):
    __tablename__ = 'training_entries'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=lambda: datetime.now(timezone.utc).date())
    exercise_name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50))  # chest, back, legs, arms, shoulders, cardio, core
    sets = db.Column(db.Integer)
    reps = db.Column(db.Integer)
    weight_used = db.Column(db.Float)
    duration_minutes = db.Column(db.Float)
    calories_burned = db.Column(db.Float)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
