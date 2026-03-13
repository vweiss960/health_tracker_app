import os
import secrets
import string
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, abort
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta, timezone
from models import (db, User, BodyMetric, FoodEntry, TrainingEntry, TrainingPlan,
                    MealPlan, ProgressPhoto, ChatConversation, ChatMessage,
                    CommonMeal, WaterEntry, CaffeineEntry, BlockedIP, LoginAttempt,
                    GeoCache, UserSession)

admin_bp = Blueprint('admin', __name__, template_folder='../templates/admin')

# ---------------------------------------------------------------------------
# Access control: local network only + must be admin
# ---------------------------------------------------------------------------
_LOCAL_PREFIXES = ('127.', '10.', '172.16.', '172.17.', '172.18.', '172.19.',
                   '172.20.', '172.21.', '172.22.', '172.23.', '172.24.',
                   '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
                   '172.30.', '172.31.', '192.168.', '100.',  # 100.x = Tailscale CGNAT
                   '::1', 'fd')


def _is_local_ip(ip):
    if not ip:
        return False
    return ip.startswith(_LOCAL_PREFIXES) or ip == '::1'


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        # Check local network access
        remote = request.remote_addr or ''
        if not _is_local_ip(remote):
            abort(403)
        # Check admin flag
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _generate_temp_password(length=12):
    """Generate a readable temporary password."""
    chars = string.ascii_letters + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route('/')
@admin_required
def dashboard():
    users = User.query.order_by(User.created_at.desc()).all()
    stats = {
        'total_users': len(users),
        'admin_users': sum(1 for u in users if u.is_admin),
        'food_entries': FoodEntry.query.count(),
        'training_entries': TrainingEntry.query.count(),
    }
    reg_disabled = os.environ.get('DISABLE_REGISTRATION', '').lower() in ('1', 'true', 'yes')
    blocked_ips = BlockedIP.query.order_by(BlockedIP.blocked_at.desc()).all()

    # Recent sessions (last 7 days) with geo data
    since = datetime.now(timezone.utc) - timedelta(days=7)
    recent_sessions = (UserSession.query
                       .filter(UserSession.logged_in_at >= since)
                       .order_by(UserSession.logged_in_at.desc())
                       .limit(50)
                       .all())
    # Build geo lookup dict
    session_ips = {s.ip_address for s in recent_sessions}
    geo_map = {}
    for ip in session_ips:
        geo = GeoCache.query.filter_by(ip_address=ip).first()
        if geo:
            geo_map[ip] = geo

    return render_template('admin/dashboard.html', users=users, stats=stats,
                           reg_disabled=reg_disabled, blocked_ips=blocked_ips,
                           recent_sessions=recent_sessions, geo_map=geo_map)


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------
@admin_bp.route('/user/<int:user_id>')
@admin_required
def user_detail(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    counts = {
        'food_entries': FoodEntry.query.filter_by(user_id=user_id).count(),
        'training_entries': TrainingEntry.query.filter_by(user_id=user_id).count(),
        'body_metrics': BodyMetric.query.filter_by(user_id=user_id).count(),
        'photos': ProgressPhoto.query.filter_by(user_id=user_id).count(),
        'conversations': ChatConversation.query.filter_by(user_id=user_id).count(),
        'training_plans': TrainingPlan.query.filter_by(user_id=user_id, active=True).count(),
        'meal_plans': MealPlan.query.filter_by(user_id=user_id, active=True).count(),
        'common_meals': CommonMeal.query.filter_by(user_id=user_id).count(),
        'water_entries': WaterEntry.query.filter_by(user_id=user_id).count(),
        'caffeine_entries': CaffeineEntry.query.filter_by(user_id=user_id).count(),
    }
    all_users = User.query.filter(User.id != user_id).order_by(User.username).all()
    return render_template('admin/user_detail.html', user=user, counts=counts,
                           all_users=all_users)


@admin_bp.route('/user/<int:user_id>/reset-password', methods=['POST'])
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    temp_pw = _generate_temp_password()
    user.password_hash = generate_password_hash(temp_pw)
    user.must_change_password = True
    db.session.commit()
    flash(f'Temporary password for {user.username}: {temp_pw}', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/user/<int:user_id>/toggle-admin', methods=['POST'])
@admin_required
def toggle_admin(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash('You cannot remove your own admin access', 'error')
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        status = 'granted' if user.is_admin else 'revoked'
        flash(f'Admin access {status} for {user.username}', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash('You cannot delete your own account', 'error')
        return redirect(url_for('admin.user_detail', user_id=user_id))
    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User {username} deleted', 'success')
    return redirect(url_for('admin.dashboard'))


# ---------------------------------------------------------------------------
# Create user with temp password
# ---------------------------------------------------------------------------
@admin_bp.route('/create-user', methods=['POST'])
@admin_required
def create_user():
    username = request.form.get('username', '').strip()
    display_name = request.form.get('display_name', '').strip() or username
    make_admin = request.form.get('is_admin') == '1'

    import re
    if not re.match(r'^[a-zA-Z0-9_-]{3,30}$', username):
        flash('Username must be 3-30 characters (letters, numbers, hyphens, underscores)', 'error')
        return redirect(url_for('admin.dashboard'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" already exists', 'error')
        return redirect(url_for('admin.dashboard'))

    temp_pw = _generate_temp_password()
    user = User(
        username=username,
        password_hash=generate_password_hash(temp_pw),
        display_name=display_name,
        is_admin=make_admin,
        must_change_password=True,
    )
    db.session.add(user)
    db.session.commit()
    flash(f'User "{username}" created. Temporary password: {temp_pw}', 'success')
    return redirect(url_for('admin.dashboard'))


# ---------------------------------------------------------------------------
# Blocked IP management
# ---------------------------------------------------------------------------
@admin_bp.route('/unblock-ip/<int:block_id>', methods=['POST'])
@admin_required
def unblock_ip(block_id):
    blocked = db.session.get(BlockedIP, block_id)
    if not blocked:
        abort(404)
    ip = blocked.ip_address
    # Remove the block
    db.session.delete(blocked)
    # Clear failed attempts for this IP so it doesn't get re-blocked immediately
    LoginAttempt.query.filter_by(ip_address=ip).delete()
    db.session.commit()
    flash(f'Unblocked IP {ip} and cleared its login history', 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/block-ip', methods=['POST'])
@admin_required
def block_ip():
    ip = request.form.get('ip_address', '').strip()
    if not ip:
        flash('IP address is required', 'error')
        return redirect(url_for('admin.dashboard'))
    existing = BlockedIP.query.filter_by(ip_address=ip).first()
    if existing:
        flash(f'IP {ip} is already blocked', 'error')
    else:
        blocked = BlockedIP(ip_address=ip, fail_count=0, reason='Manually blocked by admin')
        db.session.add(blocked)
        db.session.commit()
        flash(f'Blocked IP {ip}', 'success')
    return redirect(url_for('admin.dashboard'))


# ---------------------------------------------------------------------------
# Data migration between users
# ---------------------------------------------------------------------------
DATA_MODELS = {
    'food_entries': FoodEntry,
    'training_entries': TrainingEntry,
    'body_metrics': BodyMetric,
    'training_plans': TrainingPlan,
    'meal_plans': MealPlan,
    'photos': ProgressPhoto,
    'conversations': ChatConversation,
    'common_meals': CommonMeal,
    'water_entries': WaterEntry,
    'caffeine_entries': CaffeineEntry,
}


@admin_bp.route('/user/<int:user_id>/migrate-data', methods=['POST'])
@admin_required
def migrate_data(user_id):
    source_user = db.session.get(User, user_id)
    if not source_user:
        abort(404)

    target_id = request.form.get('target_user_id', type=int)
    data_type = request.form.get('data_type', '')
    action = request.form.get('action', 'copy')  # 'copy' or 'move'

    target_user = db.session.get(User, target_id) if target_id else None
    if not target_user:
        flash('Target user not found', 'error')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    if target_id == user_id:
        flash('Source and target user cannot be the same', 'error')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    model_cls = DATA_MODELS.get(data_type)
    if not model_cls:
        flash('Invalid data type', 'error')
        return redirect(url_for('admin.user_detail', user_id=user_id))

    records = model_cls.query.filter_by(user_id=user_id).all()

    if data_type == 'conversations':
        # Conversations also have messages — handle both
        count = 0
        for conv in records:
            if action == 'move':
                conv.user_id = target_id
                for msg in conv.messages:
                    msg.user_id = target_id
                count += 1
            else:
                new_conv = ChatConversation(
                    user_id=target_id,
                    title=conv.title,
                    created_at=conv.created_at,
                )
                db.session.add(new_conv)
                db.session.flush()
                for msg in conv.messages:
                    new_msg = ChatMessage(
                        user_id=target_id,
                        conversation_id=new_conv.id,
                        role=msg.role,
                        content=msg.content,
                        created_at=msg.created_at,
                    )
                    db.session.add(new_msg)
                count += 1
    elif data_type == 'common_meals':
        from models import CommonMealItem
        count = 0
        for meal in records:
            if action == 'move':
                meal.user_id = target_id
                count += 1
            else:
                new_meal = CommonMeal(
                    user_id=target_id,
                    name=meal.name,
                    created_at=meal.created_at,
                )
                db.session.add(new_meal)
                db.session.flush()
                for item in meal.items:
                    new_item = CommonMealItem(
                        common_meal_id=new_meal.id,
                        food_name=item.food_name,
                        serving_size=item.serving_size,
                        calories=item.calories,
                        protein=item.protein,
                        carbs=item.carbs,
                        fat=item.fat,
                        fiber=item.fiber,
                    )
                    db.session.add(new_item)
                count += 1
    else:
        count = 0
        for record in records:
            if action == 'move':
                record.user_id = target_id
                count += 1
            else:
                # Clone the record
                data = {c.name: getattr(record, c.name)
                        for c in record.__table__.columns
                        if c.name not in ('id',)}
                data['user_id'] = target_id
                new_record = model_cls(**data)
                db.session.add(new_record)
                count += 1

    db.session.commit()
    verb = 'moved' if action == 'move' else 'copied'
    flash(f'{count} {data_type.replace("_", " ")} {verb} to {target_user.username}', 'success')
    return redirect(url_for('admin.user_detail', user_id=user_id))
