from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
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
        current_user.ai_provider = request.form.get('ai_provider', 'claude')
        api_key = request.form.get('ai_api_key', '').strip()
        if api_key:
            current_user.ai_api_key = api_key
        cn_key = request.form.get('calorieninjas_api_key', '').strip()
        if cn_key:
            current_user.calorieninjas_api_key = cn_key
        yt_key = request.form.get('youtube_api_key', '').strip()
        if yt_key:
            current_user.youtube_api_key = yt_key
        db.session.commit()
        flash('Settings saved', 'success')
        return redirect(url_for('settings.settings'))
    return render_template('settings.html')


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
