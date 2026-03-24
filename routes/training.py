import json
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from models import db, TrainingEntry, TrainingPlan
from datetime import datetime, date
from app import user_today

training_bp = Blueprint('training', __name__)

DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']


@training_bp.route('/')
@login_required
def training_log():
    selected_date = request.args.get('date')
    if selected_date:
        view_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    else:
        view_date = user_today(current_user.tz)

    entries = TrainingEntry.query.filter_by(user_id=current_user.id, date=view_date)\
        .order_by(TrainingEntry.category, TrainingEntry.created_at).all()

    # Load active training plan grouped by day
    plan_entries = TrainingPlan.query.filter_by(user_id=current_user.id, active=True)\
        .order_by(TrainingPlan.order_index).all()

    plan_name = plan_entries[0].name if plan_entries else None
    plan_by_day = {}
    for e in plan_entries:
        day = e.day_of_week
        if day not in plan_by_day:
            plan_by_day[day] = []
        plan_by_day[day].append(e)

    # Order days properly
    ordered_plan = [(d, plan_by_day[d]) for d in DAY_ORDER if d in plan_by_day]

    # What day is the viewed date?
    today_day_name = view_date.strftime('%A').lower()

    # Build set of exercise names already logged today (for strikethrough)
    logged_names = {e.exercise_name.lower() for e in entries}

    return render_template('training.html',
        entries=entries, view_date=view_date,
        plan_name=plan_name, ordered_plan=ordered_plan,
        today_day_name=today_day_name,
        logged_names=logged_names)


@training_bp.route('/add', methods=['POST'])
@login_required
def add_training():
    date_str = request.form.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

    num_sets = _int_or_none(request.form.get('sets'))
    set_data = _build_set_data(num_sets, request.form)

    entry = TrainingEntry(
        user_id=current_user.id,
        date=entry_date,
        exercise_name=request.form.get('exercise_name', '').strip(),
        category=request.form.get('category', ''),
        sets=num_sets,
        reps=_int_or_none(request.form.get('reps')),
        weight_used=_float_or_none(request.form.get('weight_used')),
        duration_minutes=_float_or_none(request.form.get('duration_minutes')),
        calories_burned=_float_or_none(request.form.get('calories_burned')),
        set_data=json.dumps(set_data) if set_data else None,
        notes=request.form.get('notes', '').strip() or None,
    )
    db.session.add(entry)
    db.session.commit()
    return redirect(url_for('training.training_log', date=entry_date.isoformat()))


@training_bp.route('/complete-exercises', methods=['POST'])
@login_required
def complete_exercises():
    """Bulk-log selected plan exercises to the training log."""
    date_str = request.form.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

    plan_ids = request.form.getlist('plan_ids')
    if not plan_ids:
        return redirect(url_for('training.training_log', date=entry_date.isoformat()))

    exercises = TrainingPlan.query.filter(
        TrainingPlan.id.in_(plan_ids),
        TrainingPlan.user_id == current_user.id,
        TrainingPlan.active == True,
    ).all()

    for ex in exercises:
        # Parse minimum reps from range like "8-12" → 8
        min_reps = None
        if ex.reps:
            try:
                min_reps = int(str(ex.reps).split('-')[0].strip())
            except (ValueError, IndexError):
                pass

        entry = TrainingEntry(
            user_id=current_user.id,
            date=entry_date,
            exercise_name=ex.exercise_name,
            category=ex.category,
            sets=ex.sets,
            reps=min_reps,
            notes=f"From plan: {ex.sets}x{ex.reps}" if ex.sets and ex.reps else None,
        )
        db.session.add(entry)

    db.session.commit()
    return redirect(url_for('training.training_log', date=entry_date.isoformat()))


@training_bp.route('/uncomplete-exercise', methods=['POST'])
@login_required
def uncomplete_exercise():
    """Remove a logged exercise that came from the plan."""
    date_str = request.form.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)
    exercise_name = request.form.get('exercise_name', '').strip()

    if exercise_name:
        entry = TrainingEntry.query.filter(
            TrainingEntry.user_id == current_user.id,
            TrainingEntry.date == entry_date,
            db.func.lower(TrainingEntry.exercise_name) == exercise_name.lower(),
        ).first()
        if entry:
            db.session.delete(entry)
            db.session.commit()

    return jsonify({'ok': True})


@training_bp.route('/update/<int:entry_id>', methods=['POST'])
@login_required
def update_training(entry_id):
    """Update a single field on a training entry."""
    entry = TrainingEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    field = data.get('field')
    value = data.get('value', '').strip()

    allowed = {
        'exercise_name': str,
        'category': str,
        'sets': 'int',
        'reps': 'int',
        'weight_used': 'float',
        'duration_minutes': 'float',
        'calories_burned': 'float',
        'notes': str,
    }

    if field not in allowed:
        return jsonify({'error': 'Invalid field'}), 400

    if allowed[field] == 'int':
        setattr(entry, field, _int_or_none(value) if value else None)
    elif allowed[field] == 'float':
        setattr(entry, field, _float_or_none(value) if value else None)
    else:
        setattr(entry, field, value or None)

    db.session.commit()
    return jsonify({'ok': True, 'value': str(getattr(entry, field) or '')})


@training_bp.route('/exercise-history')
@login_required
def exercise_history():
    """Return history for a specific exercise (last 3 months)."""
    from datetime import timedelta
    name = request.args.get('name', '').strip()
    if not name:
        return jsonify({'error': 'No exercise name'}), 400

    cutoff = user_today(current_user.tz) - timedelta(days=90)
    entries = TrainingEntry.query.filter(
        TrainingEntry.user_id == current_user.id,
        db.func.lower(TrainingEntry.exercise_name) == name.lower(),
        TrainingEntry.date >= cutoff,
    ).order_by(TrainingEntry.date.desc()).all()

    if not entries:
        return jsonify({'found': False})

    # Most recent entry (for "last time" display)
    latest = entries[0]
    last_set_data = json.loads(latest.set_data) if latest.set_data else None

    # Build timeline for chart/progress
    timeline = []
    for e in reversed(entries):  # chronological order
        entry_data = {
            'date': e.date.isoformat(),
            'sets': e.sets,
            'reps': e.reps,
            'weight': e.weight_used,
        }
        if e.set_data:
            parsed = json.loads(e.set_data)
            # Max weight across sets
            weights = [s['weight'] for s in parsed if s.get('weight')]
            reps_list = [s['reps'] for s in parsed if s.get('reps')]
            entry_data['max_weight'] = max(weights) if weights else None
            entry_data['total_reps'] = sum(reps_list) if reps_list else None
            entry_data['set_details'] = parsed
        else:
            entry_data['max_weight'] = e.weight_used
            entry_data['total_reps'] = (e.sets or 1) * (e.reps or 0) if e.reps else None
        timeline.append(entry_data)

    # Summary stats
    all_weights = [t['max_weight'] for t in timeline if t.get('max_weight')]
    total_sessions = len(timeline)

    return jsonify({
        'found': True,
        'exercise_name': latest.exercise_name,
        'last_performed': latest.date.isoformat(),
        'last_sets': latest.sets,
        'last_reps': latest.reps,
        'last_weight': latest.weight_used,
        'last_set_data': last_set_data,
        'total_sessions': total_sessions,
        'max_weight_ever': max(all_weights) if all_weights else None,
        'timeline': timeline,
    })


@training_bp.route('/entry/<int:entry_id>', methods=['GET'])
@login_required
def get_entry(entry_id):
    """Return entry details as JSON (for the edit modal)."""
    entry = TrainingEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    return jsonify({
        'id': entry.id,
        'exercise_name': entry.exercise_name,
        'category': entry.category,
        'sets': entry.sets,
        'reps': entry.reps,
        'weight_used': entry.weight_used,
        'duration_minutes': entry.duration_minutes,
        'calories_burned': entry.calories_burned,
        'set_data': json.loads(entry.set_data) if entry.set_data else None,
        'notes': entry.notes,
    })


@training_bp.route('/update-sets/<int:entry_id>', methods=['POST'])
@login_required
def update_sets(entry_id):
    """Update the set count and per-set data for an entry."""
    entry = TrainingEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json() or {}
    num_sets = data.get('sets')
    set_data = data.get('set_data')  # list of {set_number, reps, weight}

    if num_sets is not None:
        entry.sets = int(num_sets) if num_sets else None

    if set_data is not None:
        # Validate and clean set_data
        cleaned = []
        for s in set_data:
            cleaned.append({
                'set_number': int(s.get('set_number', 0)),
                'reps': int(s['reps']) if s.get('reps') not in (None, '', 0) else None,
                'weight': float(s['weight']) if s.get('weight') not in (None, '', 0) else None,
            })
        entry.set_data = json.dumps(cleaned) if cleaned else None

    # Also update summary reps/weight from first set for backward compat
    if data.get('reps') is not None:
        entry.reps = int(data['reps']) if data['reps'] else None
    if data.get('weight_used') is not None:
        entry.weight_used = float(data['weight_used']) if data['weight_used'] else None
    if data.get('duration_minutes') is not None:
        entry.duration_minutes = float(data['duration_minutes']) if data['duration_minutes'] else None
    if data.get('calories_burned') is not None:
        entry.calories_burned = float(data['calories_burned']) if data['calories_burned'] else None
    if data.get('notes') is not None:
        entry.notes = data['notes'].strip() or None

    db.session.commit()
    return jsonify({'ok': True})


@training_bp.route('/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_training(entry_id):
    entry = TrainingEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    entry_date = entry.date.isoformat()
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('training.training_log', date=entry_date))


@training_bp.route('/delete-plan', methods=['POST'])
@login_required
def delete_plan():
    TrainingPlan.query.filter_by(user_id=current_user.id, active=True).update({"active": False})
    db.session.commit()
    return redirect(url_for('training.training_log'))


@training_bp.route('/exercise-video')
@login_required
def exercise_video():
    from urllib.parse import quote_plus
    exercise = request.args.get('name', '').strip()
    if not exercise:
        return jsonify({'error': 'No exercise name provided'}), 400
    query = quote_plus(f"{exercise} exercise tutorial how to proper form")
    url = f"https://www.youtube.com/results?search_query={query}"
    return jsonify({'exercise': exercise, 'url': url})


@training_bp.route('/api/history')
@login_required
def api_history():
    days = request.args.get('days', 30, type=int)
    entries = TrainingEntry.query.filter_by(user_id=current_user.id)\
        .order_by(TrainingEntry.date.desc()).limit(days * 10).all()
    return jsonify([{
        'date': e.date.isoformat(),
        'exercise_name': e.exercise_name,
        'category': e.category,
        'sets': e.sets,
        'reps': e.reps,
        'weight_used': e.weight_used,
        'duration_minutes': e.duration_minutes,
        'calories_burned': e.calories_burned,
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


def _build_set_data(num_sets, form):
    """Build per-set data list from form fields like set_reps_1, set_weight_1, etc."""
    if not num_sets or num_sets < 1:
        return None
    sets = []
    for i in range(1, num_sets + 1):
        reps = _int_or_none(form.get(f'set_reps_{i}'))
        weight = _float_or_none(form.get(f'set_weight_{i}'))
        if reps is not None or weight is not None:
            sets.append({'set_number': i, 'reps': reps, 'weight': weight})
    return sets if sets else None
