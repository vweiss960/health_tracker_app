from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from models import db, MealPlan

meal_plan_bp = Blueprint('meal_plan', __name__)

DAY_ORDER = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack']


@meal_plan_bp.route('/')
@login_required
def meal_plan_page():
    plan_entries = MealPlan.query.filter_by(user_id=current_user.id, active=True)\
        .order_by(MealPlan.order_index).all()

    plan_name = plan_entries[0].name if plan_entries else None

    # Group by day, then by meal_type
    plan_by_day = {}
    for e in plan_entries:
        day = e.day_of_week
        if day not in plan_by_day:
            plan_by_day[day] = {}
        mt = e.meal_type or 'snack'
        if mt not in plan_by_day[day]:
            plan_by_day[day][mt] = []
        plan_by_day[day][mt].append(e)

    # Order days and meals properly
    ordered_plan = []
    for d in DAY_ORDER:
        if d in plan_by_day:
            day_meals = []
            for mt in MEAL_ORDER:
                if mt in plan_by_day[d]:
                    day_meals.append((mt, plan_by_day[d][mt]))
            ordered_plan.append((d, day_meals))

    # Calculate daily totals per day
    day_totals = {}
    for d in plan_by_day:
        totals = {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0}
        for mt in plan_by_day[d]:
            for meal in plan_by_day[d][mt]:
                totals['calories'] += meal.calories or 0
                totals['protein'] += meal.protein or 0
                totals['carbs'] += meal.carbs or 0
                totals['fat'] += meal.fat or 0
        day_totals[d] = totals

    from app import user_today
    today_day_name = user_today(current_user.tz).strftime('%A').lower()

    return render_template('meal_plan.html',
        plan_name=plan_name, ordered_plan=ordered_plan,
        day_totals=day_totals, today_day_name=today_day_name)


@meal_plan_bp.route('/delete-plan', methods=['POST'])
@login_required
def delete_plan():
    MealPlan.query.filter_by(user_id=current_user.id, active=True).update({"active": False})
    db.session.commit()
    return redirect(url_for('meal_plan.meal_plan_page'))
