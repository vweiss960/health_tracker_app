from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from models import db, FoodEntry
from datetime import datetime, date

food_bp = Blueprint('food', __name__)


@food_bp.route('/')
@login_required
def food_log():
    selected_date = request.args.get('date')
    if selected_date:
        view_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    else:
        view_date = date.today()

    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=view_date)\
        .order_by(FoodEntry.meal_type, FoodEntry.created_at).all()

    totals = {
        'calories': sum(e.calories or 0 for e in entries),
        'protein': sum(e.protein or 0 for e in entries),
        'carbs': sum(e.carbs or 0 for e in entries),
        'fat': sum(e.fat or 0 for e in entries),
        'fiber': sum(e.fiber or 0 for e in entries),
    }

    return render_template('food.html', entries=entries, view_date=view_date, totals=totals)


@food_bp.route('/add', methods=['POST'])
@login_required
def add_food():
    date_str = request.form.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()

    entry = FoodEntry(
        user_id=current_user.id,
        date=entry_date,
        meal_type=request.form.get('meal_type', 'snack'),
        food_name=request.form.get('food_name', '').strip(),
        serving_size=request.form.get('serving_size', '').strip() or None,
        calories=_float_or_none(request.form.get('calories')),
        protein=_float_or_none(request.form.get('protein')),
        carbs=_float_or_none(request.form.get('carbs')),
        fat=_float_or_none(request.form.get('fat')),
        fiber=_float_or_none(request.form.get('fiber')),
        notes=request.form.get('notes', '').strip() or None,
    )
    db.session.add(entry)
    db.session.commit()
    return redirect(url_for('food.food_log', date=entry_date.isoformat()))


@food_bp.route('/edit/<int:entry_id>', methods=['POST'])
@login_required
def edit_food(entry_id):
    entry = FoodEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    entry.meal_type = request.form.get('meal_type', entry.meal_type)
    entry.food_name = request.form.get('food_name', '').strip() or entry.food_name
    entry.serving_size = request.form.get('serving_size', '').strip() or None
    entry.calories = _float_or_none(request.form.get('calories'))
    entry.protein = _float_or_none(request.form.get('protein'))
    entry.carbs = _float_or_none(request.form.get('carbs'))
    entry.fat = _float_or_none(request.form.get('fat'))
    entry.fiber = _float_or_none(request.form.get('fiber'))
    db.session.commit()
    return redirect(url_for('food.food_log', date=entry.date.isoformat()))


@food_bp.route('/duplicate/<int:entry_id>', methods=['POST'])
@login_required
def duplicate_food(entry_id):
    entry = FoodEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    dup = FoodEntry(
        user_id=current_user.id,
        date=entry.date,
        meal_type=entry.meal_type,
        food_name=entry.food_name,
        serving_size=entry.serving_size,
        calories=entry.calories,
        protein=entry.protein,
        carbs=entry.carbs,
        fat=entry.fat,
        fiber=entry.fiber,
        notes=entry.notes,
    )
    db.session.add(dup)
    db.session.commit()
    return redirect(url_for('food.food_log', date=entry.date.isoformat()))


@food_bp.route('/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_food(entry_id):
    entry = FoodEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    entry_date = entry.date.isoformat()
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('food.food_log', date=entry_date))


@food_bp.route('/copy', methods=['POST'])
@login_required
def copy_food():
    source_date_str = request.form.get('source_date')
    target_date_str = request.form.get('target_date')
    if not source_date_str or not target_date_str:
        return redirect(url_for('food.food_log'))

    source_date = datetime.strptime(source_date_str, '%Y-%m-%d').date()
    target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()

    source_entries = FoodEntry.query.filter_by(
        user_id=current_user.id, date=source_date
    ).all()

    for e in source_entries:
        new_entry = FoodEntry(
            user_id=current_user.id,
            date=target_date,
            meal_type=e.meal_type,
            food_name=e.food_name,
            serving_size=e.serving_size,
            calories=e.calories,
            protein=e.protein,
            carbs=e.carbs,
            fat=e.fat,
            fiber=e.fiber,
            notes=e.notes,
        )
        db.session.add(new_entry)

    db.session.commit()
    return redirect(url_for('food.food_log', date=target_date.isoformat()))


@food_bp.route('/api/dates-with-entries')
@login_required
def dates_with_entries():
    """Return recent dates that have food entries, for the copy-from picker."""
    from sqlalchemy import func
    results = db.session.query(
        FoodEntry.date,
        func.count(FoodEntry.id).label('count')
    ).filter_by(user_id=current_user.id)\
     .group_by(FoodEntry.date)\
     .order_by(FoodEntry.date.desc())\
     .limit(30).all()
    return jsonify([{
        'date': r.date.isoformat(),
        'count': r.count,
    } for r in results])


@food_bp.route('/api/summary')
@login_required
def api_summary():
    days = request.args.get('days', 30, type=int)
    from sqlalchemy import func
    results = db.session.query(
        FoodEntry.date,
        func.sum(FoodEntry.calories).label('calories'),
        func.sum(FoodEntry.protein).label('protein'),
        func.sum(FoodEntry.carbs).label('carbs'),
        func.sum(FoodEntry.fat).label('fat'),
    ).filter_by(user_id=current_user.id)\
     .group_by(FoodEntry.date)\
     .order_by(FoodEntry.date.desc())\
     .limit(days).all()

    return jsonify([{
        'date': r.date.isoformat(),
        'calories': float(r.calories or 0),
        'protein': float(r.protein or 0),
        'carbs': float(r.carbs or 0),
        'fat': float(r.fat or 0),
    } for r in results])


@food_bp.route('/api/usda-lookup')
@login_required
def usda_lookup():
    """Look up nutrition info from USDA FoodData Central."""
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'error': 'No food item provided'}), 400

    from ai_tools import _usda_lookup
    result = _usda_lookup(query, max_results=3)
    if result and 'error' not in result:
        return jsonify(result)
    elif result and 'error' in result:
        return jsonify(result), 502
    return jsonify({'error': 'No results found in USDA database'}), 404


@food_bp.route('/api/openfoodfacts-lookup')
@login_required
def openfoodfacts_lookup():
    """Look up nutrition info from Open Food Facts (free, no API key)."""
    import requests
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'error': 'No food item provided'}), 400
    try:
        resp = requests.get(
            'https://world.openfoodfacts.org/cgi/search.pl',
            params={'search_terms': query, 'search_simple': 1, 'action': 'process', 'json': 1, 'page_size': 5},
            headers={'User-Agent': 'HealthTracker/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return jsonify({'error': f'Open Food Facts request failed: {str(e)}'}), 502

    products = data.get('products', [])
    if not products:
        return jsonify({'error': 'No results found'}), 404

    # Find best match with nutrient data
    for product in products:
        n = product.get('nutriments', {})
        if not n:
            continue
        nutrients = {
            'calories': round(n.get('energy-kcal_100g') or n.get('energy-kcal_serving') or 0, 1),
            'protein': round(n.get('proteins_100g') or 0, 1),
            'carbs': round(n.get('carbohydrates_100g') or 0, 1),
            'fat': round(n.get('fat_100g') or 0, 1),
            'fiber': round(n.get('fiber_100g') or 0, 1),
        }
        if nutrients['calories'] > 0:
            return jsonify({
                'best_match': {
                    'description': product.get('product_name', query),
                    'nutrients': nutrients,
                    'serving_size': product.get('serving_size', '100g'),
                    'source': 'Open Food Facts',
                }
            })
    return jsonify({'error': 'No nutritional data found'}), 404


@food_bp.route('/api/calorieninjas-lookup')
@login_required
def calorieninjas_lookup():
    """Look up nutrition info from CalorieNinjas API (free tier, needs API key)."""
    import requests
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify({'error': 'No food item provided'}), 400

    api_key = current_user.calorieninjas_api_key
    if not api_key:
        return jsonify({'error': 'No CalorieNinjas API key configured. Add one in Settings.'}), 400

    try:
        resp = requests.get(
            'https://api.calorieninjas.com/v1/nutrition',
            params={'query': query},
            headers={'X-Api-Key': api_key},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return jsonify({'error': f'CalorieNinjas request failed: {str(e)}'}), 502

    items = data.get('items', [])
    if not items:
        return jsonify({'error': 'No results found'}), 404

    # Aggregate all items (CalorieNinjas parses "1 cup rice and 4oz chicken" into separate items)
    totals = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0, 'fiber': 0}
    names = []
    for item in items:
        totals['calories'] += item.get('calories', 0)
        totals['protein'] += item.get('protein_g', 0)
        totals['carbs'] += item.get('carbohydrates_total_g', 0)
        totals['fat'] += item.get('fat_total_g', 0)
        totals['fiber'] += item.get('fiber_g', 0)
        names.append(item.get('name', ''))

    for k in totals:
        totals[k] = round(totals[k], 1)

    serving = items[0].get('serving_size_g', '')
    return jsonify({
        'best_match': {
            'description': ', '.join(names),
            'nutrients': totals,
            'serving_size': f"{serving}g" if serving else '',
            'source': 'CalorieNinjas',
        }
    })


def _float_or_none(val):
    if val is None or val.strip() == '':
        return None
    try:
        return float(val)
    except ValueError:
        return None
