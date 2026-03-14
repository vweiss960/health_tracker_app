from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from models import db, FoodEntry, CommonMeal, CommonMealItem, WaterEntry, CaffeineEntry, BarcodeCache
from datetime import datetime, date
from app import user_today

food_bp = Blueprint('food', __name__)


@food_bp.route('/')
@login_required
def food_log():
    selected_date = request.args.get('date')
    if selected_date:
        view_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    else:
        view_date = user_today(current_user.tz)

    entries = FoodEntry.query.filter_by(user_id=current_user.id, date=view_date)\
        .order_by(FoodEntry.meal_type, FoodEntry.created_at).all()

    totals = {
        'calories': sum(e.calories or 0 for e in entries),
        'protein': sum(e.protein or 0 for e in entries),
        'carbs': sum(e.carbs or 0 for e in entries),
        'fat': sum(e.fat or 0 for e in entries),
        'fiber': sum(e.fiber or 0 for e in entries),
    }

    # Get common meals for this user
    common_meals = CommonMeal.query.filter_by(user_id=current_user.id)\
        .order_by(CommonMeal.name).all()

    # Get water and caffeine entries for this date
    water_entries = WaterEntry.query.filter_by(user_id=current_user.id, date=view_date)\
        .order_by(WaterEntry.created_at).all()
    caffeine_entries = CaffeineEntry.query.filter_by(user_id=current_user.id, date=view_date)\
        .order_by(CaffeineEntry.created_at).all()

    water_total = sum(w.amount_ml or 0 for w in water_entries)
    caffeine_total = sum(c.amount_mg or 0 for c in caffeine_entries)

    return render_template('food.html', entries=entries, view_date=view_date, totals=totals,
                           common_meals=common_meals, water_entries=water_entries,
                           caffeine_entries=caffeine_entries, water_total=water_total,
                           caffeine_total=caffeine_total)


@food_bp.route('/add', methods=['POST'])
@login_required
def add_food():
    date_str = request.form.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

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


@food_bp.route('/save-common-meal', methods=['POST'])
@login_required
def save_common_meal():
    data = request.get_json()
    meal_name = data.get('name', '').strip()
    entry_ids = data.get('entry_ids', [])
    if not meal_name or not entry_ids:
        return jsonify({'error': 'Name and entries required'}), 400

    meal = CommonMeal(user_id=current_user.id, name=meal_name)
    db.session.add(meal)
    db.session.flush()

    for eid in entry_ids:
        entry = FoodEntry.query.get(eid)
        if entry and entry.user_id == current_user.id:
            item = CommonMealItem(
                common_meal_id=meal.id,
                food_name=entry.food_name,
                serving_size=entry.serving_size,
                calories=entry.calories,
                protein=entry.protein,
                carbs=entry.carbs,
                fat=entry.fat,
                fiber=entry.fiber,
            )
            db.session.add(item)

    db.session.commit()
    return jsonify({'ok': True, 'id': meal.id, 'name': meal.name})


@food_bp.route('/add-common-meal', methods=['POST'])
@login_required
def add_common_meal():
    data = request.get_json()
    meal_id = data.get('common_meal_id')
    meal_type = data.get('meal_type', 'snack')
    date_str = data.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

    common_meal = CommonMeal.query.get_or_404(meal_id)
    if common_meal.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403

    for item in common_meal.items:
        entry = FoodEntry(
            user_id=current_user.id,
            date=entry_date,
            meal_type=meal_type,
            food_name=item.food_name,
            serving_size=item.serving_size,
            calories=item.calories,
            protein=item.protein,
            carbs=item.carbs,
            fat=item.fat,
            fiber=item.fiber,
        )
        db.session.add(entry)

    db.session.commit()
    return jsonify({'ok': True})


@food_bp.route('/delete-common-meal/<int:meal_id>', methods=['POST'])
@login_required
def delete_common_meal(meal_id):
    meal = CommonMeal.query.get_or_404(meal_id)
    if meal.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(meal)
    db.session.commit()
    return jsonify({'ok': True})


@food_bp.route('/api/common-foods')
@login_required
def common_foods():
    """Return the user's most frequently logged food items."""
    from sqlalchemy import func
    results = db.session.query(
        FoodEntry.food_name,
        FoodEntry.serving_size,
        func.avg(FoodEntry.calories).label('avg_cal'),
        func.avg(FoodEntry.protein).label('avg_protein'),
        func.avg(FoodEntry.carbs).label('avg_carbs'),
        func.avg(FoodEntry.fat).label('avg_fat'),
        func.avg(FoodEntry.fiber).label('avg_fiber'),
        func.count(FoodEntry.id).label('count'),
    ).filter_by(user_id=current_user.id)\
     .group_by(FoodEntry.food_name, FoodEntry.serving_size)\
     .order_by(func.count(FoodEntry.id).desc())\
     .limit(20).all()

    return jsonify([{
        'food_name': r.food_name,
        'serving_size': r.serving_size,
        'calories': round(float(r.avg_cal or 0), 1),
        'protein': round(float(r.avg_protein or 0), 1),
        'carbs': round(float(r.avg_carbs or 0), 1),
        'fat': round(float(r.avg_fat or 0), 1),
        'fiber': round(float(r.avg_fiber or 0), 1),
        'count': r.count,
    } for r in results])


@food_bp.route('/add-water', methods=['POST'])
@login_required
def add_water():
    data = request.form if request.form else request.get_json()
    date_str = data.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

    amount = data.get('amount_ml')
    if not amount:
        if request.is_json:
            return jsonify({'error': 'Amount required'}), 400
        return redirect(url_for('food.food_log', date=entry_date.isoformat()))

    entry = WaterEntry(
        user_id=current_user.id,
        date=entry_date,
        amount_ml=float(amount),
        time=data.get('time', ''),
        notes=data.get('notes', ''),
    )
    db.session.add(entry)
    db.session.commit()

    if request.is_json:
        return jsonify({'ok': True, 'id': entry.id})
    return redirect(url_for('food.food_log', date=entry_date.isoformat()))


@food_bp.route('/delete-water/<int:entry_id>', methods=['POST'])
@login_required
def delete_water(entry_id):
    entry = WaterEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    entry_date = entry.date.isoformat()
    db.session.delete(entry)
    db.session.commit()
    if request.is_json:
        return jsonify({'ok': True})
    return redirect(url_for('food.food_log', date=entry_date))


@food_bp.route('/add-caffeine', methods=['POST'])
@login_required
def add_caffeine():
    data = request.form if request.form else request.get_json()
    date_str = data.get('date')
    entry_date = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else user_today(current_user.tz)

    amount = data.get('amount_mg')
    if not amount:
        if request.is_json:
            return jsonify({'error': 'Amount required'}), 400
        return redirect(url_for('food.food_log', date=entry_date.isoformat()))

    entry = CaffeineEntry(
        user_id=current_user.id,
        date=entry_date,
        amount_mg=float(amount),
        source=data.get('source', ''),
        time=data.get('time', ''),
        notes=data.get('notes', ''),
    )
    db.session.add(entry)
    db.session.commit()

    if request.is_json:
        return jsonify({'ok': True, 'id': entry.id})
    return redirect(url_for('food.food_log', date=entry_date.isoformat()))


@food_bp.route('/delete-caffeine/<int:entry_id>', methods=['POST'])
@login_required
def delete_caffeine(entry_id):
    entry = CaffeineEntry.query.get_or_404(entry_id)
    if entry.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    entry_date = entry.date.isoformat()
    db.session.delete(entry)
    db.session.commit()
    if request.is_json:
        return jsonify({'ok': True})
    return redirect(url_for('food.food_log', date=entry_date))


@food_bp.route('/api/water-summary')
@login_required
def water_summary():
    """Return water intake summary for AI tools."""
    days = request.args.get('days', 7, type=int)
    from sqlalchemy import func
    since = user_today(current_user.tz) - __import__('datetime').timedelta(days=days)
    results = db.session.query(
        WaterEntry.date,
        func.sum(WaterEntry.amount_ml).label('total_ml'),
        func.count(WaterEntry.id).label('count'),
    ).filter(
        WaterEntry.user_id == current_user.id,
        WaterEntry.date >= since,
    ).group_by(WaterEntry.date).order_by(WaterEntry.date.desc()).all()

    return jsonify([{
        'date': r.date.isoformat(),
        'total_ml': round(float(r.total_ml or 0), 1),
        'entries': r.count,
    } for r in results])


@food_bp.route('/api/caffeine-summary')
@login_required
def caffeine_summary():
    """Return caffeine intake summary for AI tools."""
    days = request.args.get('days', 7, type=int)
    from sqlalchemy import func
    since = user_today(current_user.tz) - __import__('datetime').timedelta(days=days)
    results = db.session.query(
        CaffeineEntry.date,
        func.sum(CaffeineEntry.amount_mg).label('total_mg'),
        func.count(CaffeineEntry.id).label('count'),
    ).filter(
        CaffeineEntry.user_id == current_user.id,
        CaffeineEntry.date >= since,
    ).group_by(CaffeineEntry.date).order_by(CaffeineEntry.date.desc()).all()

    return jsonify([{
        'date': r.date.isoformat(),
        'total_mg': round(float(r.total_mg or 0), 1),
        'entries': r.count,
    } for r in results])


@food_bp.route('/api/analyze-food-photo', methods=['POST'])
@login_required
def analyze_food_photo():
    """Send a food photo to Claude vision API for calorie/macro estimation."""
    import base64
    import json as _json
    import re as _re

    if 'photo' not in request.files:
        return jsonify({'error': 'No photo provided'}), 400

    file = request.files['photo']
    if not file or file.filename == '':
        return jsonify({'error': 'No photo provided'}), 400

    image_data = base64.standard_b64encode(file.read()).decode('utf-8')
    media_type = file.content_type or 'image/jpeg'

    # Resolve AI key (same pattern as ai_chat.py)
    from models import SystemConfig
    ai_key = current_user.ai_api_key
    if not ai_key and current_user.use_system_ai_key:
        ai_key = SystemConfig.get('system_ai_api_key')

    if not ai_key:
        return jsonify({'error': 'No AI API key configured. Add one in Settings.'}), 400

    provider = current_user.ai_provider or 'claude'

    try:
        if provider == 'openai':
            import openai
            client = openai.OpenAI(api_key=ai_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{image_data}"}},
                        {"type": "text", "text": "Analyze this food photo. Identify each food item visible and estimate the nutritional content. Return ONLY a JSON object with this structure: {\"items\": [{\"food_name\": \"...\", \"serving_size\": \"...\", \"calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"fiber\": 0}], \"total\": {\"calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"fiber\": 0}}. Be as accurate as possible with portion estimation based on visual cues. No other text."}
                    ]
                }]
            )
            reply = response.choices[0].message.content
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=ai_key)
            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                        {"type": "text", "text": "Analyze this food photo. Identify each food item visible and estimate the nutritional content. Return ONLY a JSON object with this structure: {\"items\": [{\"food_name\": \"...\", \"serving_size\": \"...\", \"calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"fiber\": 0}], \"total\": {\"calories\": 0, \"protein\": 0, \"carbs\": 0, \"fat\": 0, \"fiber\": 0}}. Be as accurate as possible with portion estimation based on visual cues. No other text."}
                    ]
                }]
            )
            reply = response.content[0].text

        json_match = _re.search(r'\{[\s\S]*\}', reply)
        if json_match:
            result = _json.loads(json_match.group())
            return jsonify({'result': result, 'source': 'AI Vision Estimate'})
        return jsonify({'error': 'Could not parse AI response'}), 500

    except Exception as e:
        return jsonify({'error': f'AI analysis failed: {str(e)}'}), 500


@food_bp.route('/api/barcode-lookup')
@login_required
def barcode_lookup():
    """Look up nutrition info by barcode — checks local cache first, then Open Food Facts."""
    import requests
    barcode = request.args.get('barcode', '').strip()
    if not barcode:
        return jsonify({'error': 'No barcode provided'}), 400

    # Check local cache first
    cached = BarcodeCache.query.filter_by(barcode=barcode).first()
    if cached:
        return jsonify({
            'product': {
                'name': cached.product_name or 'Unknown',
                'brand': cached.brand or '',
                'serving_size': cached.serving_size or '100g',
                'nutrients': {
                    'calories': cached.calories_per_100g or 0,
                    'protein': cached.protein_per_100g or 0,
                    'carbs': cached.carbs_per_100g or 0,
                    'fat': cached.fat_per_100g or 0,
                    'fiber': cached.fiber_per_100g or 0,
                },
                'image_url': cached.image_url or '',
                'barcode': barcode,
                'source': 'local',
            }
        })

    # Fall back to Open Food Facts
    try:
        resp = requests.get(
            f'https://world.openfoodfacts.org/api/v0/product/{barcode}.json',
            headers={'User-Agent': 'GritBoard/1.0'},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return jsonify({'error': f'Barcode lookup failed: {str(e)}'}), 502

    if data.get('status') != 1:
        return jsonify({'error': 'Product not found. Try entering the food manually.'}), 404

    product = data.get('product', {})
    n = product.get('nutriments', {})

    result = {
        'name': product.get('product_name', 'Unknown'),
        'brand': product.get('brands', ''),
        'serving_size': product.get('serving_size', '100g'),
        'nutrients': {
            'calories': round(n.get('energy-kcal_100g') or n.get('energy-kcal_serving') or 0, 1),
            'protein': round(n.get('proteins_100g') or 0, 1),
            'carbs': round(n.get('carbohydrates_100g') or 0, 1),
            'fat': round(n.get('fat_100g') or 0, 1),
            'fiber': round(n.get('fiber_100g') or 0, 1),
        },
        'image_url': product.get('image_front_small_url', ''),
        'barcode': barcode,
        'source': 'openfoodfacts',
    }

    # Cache locally for future lookups
    try:
        cache_entry = BarcodeCache(
            barcode=barcode,
            product_name=result['name'],
            brand=result['brand'],
            serving_size=result['serving_size'],
            calories_per_100g=result['nutrients']['calories'],
            protein_per_100g=result['nutrients']['protein'],
            carbs_per_100g=result['nutrients']['carbs'],
            fat_per_100g=result['nutrients']['fat'],
            fiber_per_100g=result['nutrients']['fiber'],
            image_url=result['image_url'],
        )
        db.session.add(cache_entry)
        db.session.commit()
    except Exception:
        db.session.rollback()

    return jsonify({'product': result})


@food_bp.route('/api/barcode-manual-add', methods=['POST'])
@login_required
def barcode_manual_add():
    """Add a manually entered barcode product to the food log and cache it locally."""
    data = request.get_json()
    if not data or not data.get('product_name'):
        return jsonify({'error': 'Product name is required'}), 400

    barcode = data.get('barcode', '').strip()
    cal = float(data.get('calories') or 0)
    protein = float(data.get('protein') or 0)
    carbs = float(data.get('carbs') or 0)
    fat = float(data.get('fat') or 0)
    fiber = float(data.get('fiber') or 0)
    product_name = data['product_name'].strip()
    brand = data.get('brand', '').strip()
    serving_size = data.get('serving_size', '100g').strip()

    # Add to food log
    food_name = product_name + (f' ({brand})' if brand else '')
    entry = FoodEntry(
        user_id=current_user.id,
        date=datetime.strptime(data.get('date', ''), '%Y-%m-%d').date() if data.get('date') else date.today(),
        meal_type=data.get('meal_type', 'snack'),
        food_name=food_name,
        serving_size=serving_size,
        calories=cal, protein=protein, carbs=carbs, fat=fat, fiber=fiber,
    )
    db.session.add(entry)

    # Cache in barcode database for future lookups (per 100g)
    if barcode:
        existing = BarcodeCache.query.filter_by(barcode=barcode).first()
        if not existing:
            cache_entry = BarcodeCache(
                barcode=barcode,
                product_name=product_name,
                brand=brand,
                serving_size=serving_size,
                calories_per_100g=cal,
                protein_per_100g=protein,
                carbs_per_100g=carbs,
                fat_per_100g=fat,
                fiber_per_100g=fiber,
            )
            db.session.add(cache_entry)

    db.session.commit()
    return jsonify({'ok': True})


def _float_or_none(val):
    if val is None or val.strip() == '':
        return None
    try:
        return float(val)
    except ValueError:
        return None
