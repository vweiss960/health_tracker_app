from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from models import db, BodyMetric, StrengthEntry
from datetime import datetime
from app import user_today

metrics_bp = Blueprint('metrics', __name__)


@metrics_bp.route('/')
@login_required
def dashboard():
    metrics = BodyMetric.query.filter_by(user_id=current_user.id)\
        .order_by(BodyMetric.date.desc()).limit(30).all()
    strength = StrengthEntry.query.filter_by(user_id=current_user.id)\
        .order_by(StrengthEntry.date.desc()).limit(30).all()
    return render_template('dashboard.html', metrics=metrics, strength=strength)


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


# --- Strength entries ---

@metrics_bp.route('/strength/add', methods=['POST'])
@login_required
def add_strength():
    date_str = request.form.get('date')
    date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

    entry = StrengthEntry(
        user_id=current_user.id,
        date=date,
        lift=request.form.get('lift', 'bench'),
        weight=float(request.form.get('weight', 0)),
        reps=int(request.form.get('reps', 1)),
        body_weight=_float_or_none(request.form.get('body_weight')),
        notes=request.form.get('notes', '').strip() or None,
    )
    db.session.add(entry)
    db.session.commit()
    return redirect(url_for('metrics.dashboard'))


@metrics_bp.route('/strength/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_strength(entry_id):
    entry = StrengthEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('metrics.dashboard'))


# --- Inline update endpoints ---

@metrics_bp.route('/update/<int:metric_id>', methods=['POST'])
@login_required
def update_metric(metric_id):
    """Update a single field on a body metric entry (inline edit)."""
    metric = BodyMetric.query.get_or_404(metric_id)
    if metric.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    field = data.get('field')
    value = data.get('value', '').strip()

    allowed = {
        'date': 'date',
        'weight': 'float', 'belly': 'float', 'waist': 'float', 'chest': 'float',
        'arm_left': 'float', 'arm_right': 'float', 'leg_left': 'float', 'leg_right': 'float',
        'notes': 'str',
    }

    if field not in allowed:
        return jsonify({'error': 'Invalid field'}), 400

    if allowed[field] == 'date':
        metric.date = datetime.strptime(value, '%Y-%m-%d').date() if value else metric.date
        db.session.commit()
        return jsonify({'ok': True, 'value': metric.date.strftime('%b %d')})
    elif allowed[field] == 'float':
        setattr(metric, field, _float_or_none(value) if value else None)
    else:
        setattr(metric, field, value or None)

    db.session.commit()
    return jsonify({'ok': True, 'value': str(getattr(metric, field) or '')})


@metrics_bp.route('/strength/update/<int:entry_id>', methods=['POST'])
@login_required
def update_strength(entry_id):
    """Update a single field on a strength entry (inline edit)."""
    entry = StrengthEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    field = data.get('field')
    value = data.get('value', '').strip()

    allowed = {
        'date': 'date',
        'lift': 'str',
        'weight': 'float',
        'reps': 'int',
        'body_weight': 'float',
        'notes': 'str',
    }

    if field not in allowed:
        return jsonify({'error': 'Invalid field'}), 400

    if allowed[field] == 'date':
        entry.date = datetime.strptime(value, '%Y-%m-%d').date() if value else entry.date
        db.session.commit()
        return jsonify({'ok': True, 'value': entry.date.strftime('%b %d')})
    elif allowed[field] == 'float':
        setattr(entry, field, _float_or_none(value) if value else None)
    elif allowed[field] == 'int':
        setattr(entry, field, _int_or_none(value) if value else None)
    else:
        if field == 'lift' and value not in ('bench', 'squat', 'deadlift'):
            return jsonify({'error': 'Invalid lift'}), 400
        setattr(entry, field, value or None)

    db.session.commit()

    # Return computed values too so the row can update derived columns
    return jsonify({
        'ok': True,
        'value': str(getattr(entry, field) or ''),
        'estimated_1rm': entry.estimated_1rm,
        'relative_strength': entry.relative_strength,
    })


# --- API endpoints ---

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


@metrics_bp.route('/api/strength-data')
@login_required
def api_strength_data():
    days = request.args.get('days', 90, type=int)
    entries = StrengthEntry.query.filter_by(user_id=current_user.id)\
        .order_by(StrengthEntry.date.asc()).limit(days * 3).all()
    return jsonify([{
        'date': e.date.isoformat(),
        'lift': e.lift,
        'weight': e.weight,
        'reps': e.reps,
        'body_weight': e.body_weight,
        'estimated_1rm': e.estimated_1rm,
        'relative_strength': e.relative_strength,
    } for e in entries])


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
