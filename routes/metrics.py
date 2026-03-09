from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from models import db, BodyMetric
from datetime import datetime
from app import user_today

metrics_bp = Blueprint('metrics', __name__)


@metrics_bp.route('/')
@login_required
def dashboard():
    metrics = BodyMetric.query.filter_by(user_id=current_user.id)\
        .order_by(BodyMetric.date.desc()).limit(30).all()
    return render_template('dashboard.html', metrics=metrics)


@metrics_bp.route('/add', methods=['POST'])
@login_required
def add_metric():
    date_str = request.form.get('date')
    date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

    metric = BodyMetric(
        user_id=current_user.id,
        date=date,
        weight=_float_or_none(request.form.get('weight')),
        belly=_float_or_none(request.form.get('belly')),
        waist=_float_or_none(request.form.get('waist')),
        chest=_float_or_none(request.form.get('chest')),
        arm_left=_float_or_none(request.form.get('arm_left')),
        arm_right=_float_or_none(request.form.get('arm_right')),
        leg_left=_float_or_none(request.form.get('leg_left')),
        leg_right=_float_or_none(request.form.get('leg_right')),
        notes=request.form.get('notes', '').strip() or None,
    )
    db.session.add(metric)
    db.session.commit()
    return redirect(url_for('metrics.dashboard'))


@metrics_bp.route('/edit/<int:metric_id>', methods=['POST'])
@login_required
def edit_metric(metric_id):
    metric = BodyMetric.query.get_or_404(metric_id)
    if metric.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    date_str = request.form.get('date')
    if date_str:
        metric.date = datetime.strptime(date_str, '%Y-%m-%d').date()

    metric.weight = _float_or_none(request.form.get('weight'))
    metric.belly = _float_or_none(request.form.get('belly'))
    metric.waist = _float_or_none(request.form.get('waist'))
    metric.chest = _float_or_none(request.form.get('chest'))
    metric.arm_left = _float_or_none(request.form.get('arm_left'))
    metric.arm_right = _float_or_none(request.form.get('arm_right'))
    metric.leg_left = _float_or_none(request.form.get('leg_left'))
    metric.leg_right = _float_or_none(request.form.get('leg_right'))
    metric.notes = request.form.get('notes', '').strip() or None
    db.session.commit()
    return redirect(url_for('metrics.dashboard'))


@metrics_bp.route('/delete/<int:metric_id>', methods=['POST'])
@login_required
def delete_metric(metric_id):
    metric = BodyMetric.query.get_or_404(metric_id)
    if metric.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(metric)
    db.session.commit()
    return redirect(url_for('metrics.dashboard'))


@metrics_bp.route('/api/data')
@login_required
def api_data():
    days = request.args.get('days', 90, type=int)
    metrics = BodyMetric.query.filter_by(user_id=current_user.id)\
        .order_by(BodyMetric.date.asc()).limit(days).all()
    return jsonify([{
        'date': m.date.isoformat(),
        'weight': m.weight,
        'belly': m.belly,
        'waist': m.waist,
        'chest': m.chest,
        'arm_left': m.arm_left,
        'arm_right': m.arm_right,
        'leg_left': m.leg_left,
        'leg_right': m.leg_right,
    } for m in metrics])


def _float_or_none(val):
    if val is None or val.strip() == '':
        return None
    try:
        return float(val)
    except ValueError:
        return None
