import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db

settings_bp = Blueprint('settings', __name__)


@settings_bp.route('/', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        current_user.display_name = request.form.get('display_name', '').strip() or current_user.username
        current_user.target_weight = _float_or_none(request.form.get('target_weight'))
        current_user.target_calories = _int_or_none(request.form.get('target_calories'))
        current_user.health_goals = request.form.get('health_goals', '').strip() or None
        current_user.fitness_level = request.form.get('fitness_level', '').strip() or None
        current_user.dietary_restrictions = request.form.get('dietary_restrictions', '').strip() or None
        tz_val = request.form.get('tz', '').strip()
        if tz_val:
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(tz_val)
                current_user.tz = tz_val
            except Exception:
                pass
        else:
            current_user.tz = None
        current_user.ai_provider = request.form.get('ai_provider', 'claude')
        api_key = request.form.get('ai_api_key', '').strip()
        if api_key:
            current_user.ai_api_key = api_key
        cn_key = request.form.get('calorieninjas_api_key', '').strip()
        if cn_key:
            current_user.calorieninjas_api_key = cn_key
        yt_key = request.form.get('youtube_api_key', '').strip()
        if yt_key == '__CLEAR__':
            current_user.youtube_api_key = None
        elif yt_key:
            current_user.youtube_api_key = yt_key
        db.session.commit()
        flash('Settings saved', 'success')
        return redirect(url_for('settings.settings'))
    apk_path = os.path.join(current_app.static_folder, 'android', 'GritBoard.apk')
    wrapper_apk_available = os.path.exists(apk_path)
    return render_template('settings.html', wrapper_apk_available=wrapper_apk_available)


@settings_bp.route('/download-app')
@login_required
def download_wrapper_app():
    """Serve the GritBoard wrapper APK."""
    return send_from_directory(
        os.path.join(current_app.static_folder, 'android'),
        'GritBoard.apk',
        as_attachment=True,
        mimetype='application/vnd.android.package-archive',
    )


@settings_bp.route('/change-password', methods=['POST'])
@login_required
def change_password():
    import re
    current_pw = request.form.get('current_password', '')
    new_pw = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    if not check_password_hash(current_user.password_hash, current_pw):
        flash('Current password is incorrect', 'error')
    elif new_pw != confirm_pw:
        flash('New passwords do not match', 'error')
    elif len(new_pw) < 8:
        flash('Password must be at least 8 characters', 'error')
    elif not re.search(r'[A-Z]', new_pw):
        flash('Password must contain at least one uppercase letter', 'error')
    elif not re.search(r'[a-z]', new_pw):
        flash('Password must contain at least one lowercase letter', 'error')
    elif not re.search(r'[0-9]', new_pw):
        flash('Password must contain at least one number', 'error')
    else:
        current_user.password_hash = generate_password_hash(new_pw)
        current_user.must_change_password = False
        db.session.commit()
        flash('Password updated successfully', 'success')
    return redirect(url_for('settings.settings'))


def _float_or_none(val):
    if val is None or val.strip() == '':
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _int_or_none(val):
    if val is None or val.strip() == '':
        return None
    try:
        return int(val)
    except ValueError:
        return None
