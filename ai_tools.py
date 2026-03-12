"""AI tools that give the chat agent access to user health data."""

import json
from datetime import date, timedelta, datetime, timezone
from models import db, BodyMetric, FoodEntry, TrainingEntry, TrainingPlan, MealPlan, User, WaterEntry, CaffeineEntry


def _user_today(user_id):
    """Return today's date in the user's timezone."""
    import re
    from flask import request as flask_request

    # 1. Trust the browser's date cookie
    try:
        client_date = flask_request.cookies.get('client_today', '')
        if client_date and re.match(r'^\d{4}-\d{2}-\d{2}$', client_date):
            return datetime.strptime(client_date, '%Y-%m-%d').date()
    except RuntimeError:
        pass

    # 2. Fall back to zoneinfo
    user = db.session.get(User, user_id)
    if user and user.tz:
        try:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(user.tz)).date()
        except Exception:
            pass

    return date.today()


TOOL_DEFINITIONS = [
    {
        "name": "get_body_metrics_trend",
        "description": "Get the user's body measurement history and trends (weight, waist, belly, chest, arm, leg circumferences). Use this to analyze progress over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to retrieve (default 30)",
                    "default": 30
                }
            }
        }
    },
    {
        "name": "get_nutrition_summary",
        "description": "Get the user's daily nutrition summary (calories, protein, carbs, fat, fiber) for recent days. Use this to understand their eating patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to retrieve (default 7)",
                    "default": 7
                }
            }
        }
    },
    {
        "name": "get_food_log",
        "description": "Get detailed food log entries for a specific date, showing every individual food item grouped by meal type (breakfast, lunch, dinner, snack). Includes each item's name, serving size, calories, protein, carbs, fat, fiber, notes, and entry ID. Also returns daily totals.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format (default today)"
                }
            }
        }
    },
    {
        "name": "get_training_history",
        "description": "Get the user's workout/training history. Use this to review exercise patterns and progress.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to retrieve (default 14)",
                    "default": 14
                }
            }
        }
    },
    {
        "name": "lookup_food_nutrition",
        "description": "Look up nutrition information (calories, protein, carbs, fat, fiber) for a food item from the USDA FoodData Central database. Returns verified data from the US government nutrition database.",
        "input_schema": {
            "type": "object",
            "properties": {
                "food_item": {
                    "type": "string",
                    "description": "The food item to look up, e.g. 'grilled chicken breast 6oz' or '1 cup brown rice'"
                }
            },
            "required": ["food_item"]
        }
    },
    {
        "name": "suggest_meal_plan",
        "description": "Generate a meal plan suggestion based on the user's calorie and macro targets. First call get_nutrition_summary and check user goals to provide personalized suggestions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_calories": {
                    "type": "integer",
                    "description": "Target daily calories"
                },
                "meals_per_day": {
                    "type": "integer",
                    "description": "Number of meals to plan (default 3)",
                    "default": 3
                },
                "dietary_preferences": {
                    "type": "string",
                    "description": "Any dietary preferences or restrictions"
                }
            }
        }
    },
    {
        "name": "suggest_workout_plan",
        "description": "Generate a workout plan suggestion. First call get_training_history to understand the user's current routine and fitness level.",
        "input_schema": {
            "type": "object",
            "properties": {
                "focus_area": {
                    "type": "string",
                    "description": "Focus area: full_body, upper, lower, push, pull, cardio"
                },
                "fitness_level": {
                    "type": "string",
                    "description": "beginner, intermediate, or advanced"
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": "Desired workout duration in minutes",
                    "default": 45
                }
            }
        }
    },
    {
        "name": "get_user_goals",
        "description": "Get the user's full profile including health goals, target weight, target calories, fitness level, and dietary restrictions. Call this early in conversations to understand the user's context.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "update_user_goals",
        "description": "Update the user's health goals profile. Only call this AFTER asking the user for confirmation. You can update any combination of fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "health_goals": {
                    "type": "string",
                    "description": "Overall health goals text, e.g. 'Lose 20 lbs, build lean muscle, improve cardiovascular health'"
                },
                "target_weight": {
                    "type": "number",
                    "description": "Target weight in lbs or kg"
                },
                "target_calories": {
                    "type": "integer",
                    "description": "Daily calorie target"
                },
                "fitness_level": {
                    "type": "string",
                    "description": "beginner, intermediate, or advanced"
                },
                "dietary_restrictions": {
                    "type": "string",
                    "description": "Any dietary restrictions or preferences, e.g. 'vegetarian, lactose intolerant'"
                }
            }
        }
    },
    {
        "name": "find_exercise_video",
        "description": "Find a YouTube tutorial video for a specific exercise. Returns a YouTube search URL that will show relevant tutorial videos for the exercise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "exercise_name": {
                    "type": "string",
                    "description": "Name of the exercise to find a video for"
                }
            },
            "required": ["exercise_name"]
        }
    },
    {
        "name": "save_training_plan",
        "description": "Save a weekly training plan for the user. This replaces any existing plan. Provide the full week's exercises organized by day. Each exercise needs: day_of_week, exercise_name, category, sets, reps, rest_seconds, and optional notes. The plan will appear on the user's Training page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_name": {
                    "type": "string",
                    "description": "Name for this training plan, e.g. 'Push/Pull/Legs 4-Day Split'"
                },
                "exercises": {
                    "type": "array",
                    "description": "List of exercises for the week",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_of_week": {
                                "type": "string",
                                "description": "Day: monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            },
                            "exercise_name": {
                                "type": "string",
                                "description": "Name of the exercise"
                            },
                            "category": {
                                "type": "string",
                                "description": "Category: chest, back, legs, shoulders, arms, core, cardio"
                            },
                            "sets": {
                                "type": "integer",
                                "description": "Number of sets"
                            },
                            "reps": {
                                "type": "string",
                                "description": "Reps per set, can be a range like '8-12' or a duration like '30 sec'"
                            },
                            "rest_seconds": {
                                "type": "integer",
                                "description": "Rest between sets in seconds"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional notes like form tips or variations"
                            }
                        },
                        "required": ["day_of_week", "exercise_name"]
                    }
                }
            },
            "required": ["plan_name", "exercises"]
        }
    },
    {
        "name": "get_training_plan",
        "description": "Get the user's current saved weekly training plan.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_water_intake",
        "description": "Get the user's water intake history. Shows daily totals and individual entries. Use this to analyze hydration habits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to retrieve (default 7)",
                    "default": 7
                },
                "date": {
                    "type": "string",
                    "description": "Specific date in YYYY-MM-DD format to get detailed entries for"
                }
            }
        }
    },
    {
        "name": "get_caffeine_intake",
        "description": "Get the user's caffeine intake history. Shows daily totals, sources, and timing. Use this to analyze caffeine consumption patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days of history to retrieve (default 7)",
                    "default": 7
                },
                "date": {
                    "type": "string",
                    "description": "Specific date in YYYY-MM-DD format to get detailed entries for"
                }
            }
        }
    },
    {
        "name": "save_meal_plan",
        "description": "Save a weekly meal plan for the user. This replaces any existing meal plan. Provide the full week's meals organized by day and meal type. Each meal needs: day_of_week, meal_type (breakfast/lunch/dinner/snack), meal_name, and optionally serving_size, calories, protein, carbs, fat, fiber, notes. The plan will appear on the user's Meal Plan page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_name": {
                    "type": "string",
                    "description": "Name for this meal plan, e.g. 'High-Protein Weight Loss Plan'"
                },
                "meals": {
                    "type": "array",
                    "description": "List of meals for the week",
                    "items": {
                        "type": "object",
                        "properties": {
                            "day_of_week": {
                                "type": "string",
                                "description": "Day: monday, tuesday, wednesday, thursday, friday, saturday, sunday"
                            },
                            "meal_type": {
                                "type": "string",
                                "description": "Type: breakfast, lunch, dinner, snack"
                            },
                            "meal_name": {
                                "type": "string",
                                "description": "Name/description of the meal, e.g. 'Grilled chicken breast with steamed broccoli and brown rice'"
                            },
                            "serving_size": {
                                "type": "string",
                                "description": "Serving size, e.g. '6 oz chicken, 1 cup rice, 1 cup broccoli'"
                            },
                            "calories": {
                                "type": "number",
                                "description": "Estimated calories for this meal"
                            },
                            "protein": {
                                "type": "number",
                                "description": "Protein in grams"
                            },
                            "carbs": {
                                "type": "number",
                                "description": "Carbs in grams"
                            },
                            "fat": {
                                "type": "number",
                                "description": "Fat in grams"
                            },
                            "fiber": {
                                "type": "number",
                                "description": "Fiber in grams"
                            },
                            "notes": {
                                "type": "string",
                                "description": "Optional notes like prep tips or substitutions"
                            }
                        },
                        "required": ["day_of_week", "meal_type", "meal_name"]
                    }
                }
            },
            "required": ["plan_name", "meals"]
        }
    },
    {
        "name": "get_meal_plan",
        "description": "Get the user's current saved weekly meal plan.",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]


def execute_tool(tool_name, tool_input, user_id):
    """Execute an AI tool and return the result as a string."""
    handlers = {
        "get_body_metrics_trend": _get_body_metrics_trend,
        "get_nutrition_summary": _get_nutrition_summary,
        "get_food_log": _get_food_log,
        "get_training_history": _get_training_history,
        "lookup_food_nutrition": _lookup_food_nutrition,
        "suggest_meal_plan": _suggest_meal_plan,
        "suggest_workout_plan": _suggest_workout_plan,
        "get_user_goals": _get_user_goals,
        "update_user_goals": _update_user_goals,
        "find_exercise_video": _find_exercise_video,
        "save_training_plan": _save_training_plan,
        "get_training_plan": _get_training_plan,
        "save_meal_plan": _save_meal_plan,
        "get_meal_plan": _get_meal_plan,
        "get_water_intake": _get_water_intake,
        "get_caffeine_intake": _get_caffeine_intake,
    }
    handler = handlers.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    return handler(tool_input, user_id)


def _get_body_metrics_trend(input_data, user_id):
    days = input_data.get("days", 30)
    since = _user_today(user_id) - timedelta(days=days)
    metrics = BodyMetric.query.filter(
        BodyMetric.user_id == user_id,
        BodyMetric.date >= since
    ).order_by(BodyMetric.date.asc()).all()

    if not metrics:
        return json.dumps({"message": "No body metrics recorded yet.", "data": []})

    data = []
    for m in metrics:
        data.append({
            "date": m.date.isoformat(),
            "weight": m.weight,
            "belly": m.belly,
            "waist": m.waist,
            "chest": m.chest,
            "arm_left": m.arm_left,
            "arm_right": m.arm_right,
            "leg_left": m.leg_left,
            "leg_right": m.leg_right,
        })

    # Calculate trends
    summary = {"entries": len(data), "period_days": days}
    if len(data) >= 2 and data[0].get("weight") and data[-1].get("weight"):
        summary["weight_change"] = round(data[-1]["weight"] - data[0]["weight"], 1)
        summary["weight_start"] = data[0]["weight"]
        summary["weight_current"] = data[-1]["weight"]

    return json.dumps({"summary": summary, "data": data})


def _get_nutrition_summary(input_data, user_id):
    days = input_data.get("days", 7)
    since = _user_today(user_id) - timedelta(days=days)

    from sqlalchemy import func
    results = db.session.query(
        FoodEntry.date,
        func.sum(FoodEntry.calories).label('calories'),
        func.sum(FoodEntry.protein).label('protein'),
        func.sum(FoodEntry.carbs).label('carbs'),
        func.sum(FoodEntry.fat).label('fat'),
        func.sum(FoodEntry.fiber).label('fiber'),
        func.count(FoodEntry.id).label('item_count'),
    ).filter(
        FoodEntry.user_id == user_id,
        FoodEntry.date >= since
    ).group_by(FoodEntry.date).order_by(FoodEntry.date.desc()).all()

    if not results:
        return json.dumps({"message": f"No food entries recorded in the last {days} days.", "data": []})

    data = [{
        "date": r.date.isoformat(),
        "calories": round(float(r.calories or 0), 1),
        "protein": round(float(r.protein or 0), 1),
        "carbs": round(float(r.carbs or 0), 1),
        "fat": round(float(r.fat or 0), 1),
        "fiber": round(float(r.fiber or 0), 1),
        "items_logged": r.item_count,
    } for r in results]

    avg_cal = sum(d["calories"] for d in data) / len(data) if data else 0
    total_items = sum(d["items_logged"] for d in data)
    summary = {
        "days_with_data": len(data),
        "total_items_logged": total_items,
        "avg_daily_calories": round(avg_cal, 0),
    }
    return json.dumps({
        "message": f"Found food entries across {len(data)} days ({total_items} total items) in the last {days} days.",
        "summary": summary,
        "data": data,
    })


def _get_food_log(input_data, user_id):
    date_str = input_data.get("date")
    if date_str:
        log_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        log_date = _user_today(user_id)

    entries = FoodEntry.query.filter_by(
        user_id=user_id, date=log_date
    ).order_by(FoodEntry.meal_type, FoodEntry.created_at).all()

    data = [{
        "id": e.id,
        "meal_type": e.meal_type,
        "food_name": e.food_name,
        "serving_size": e.serving_size,
        "calories": e.calories,
        "protein": e.protein,
        "carbs": e.carbs,
        "fat": e.fat,
        "fiber": e.fiber,
        "notes": e.notes,
    } for e in entries]

    # Group by meal type for easier reading
    meals = {}
    for entry in data:
        mt = entry["meal_type"] or "other"
        if mt not in meals:
            meals[mt] = []
        meals[mt].append(entry)

    totals = {
        "calories": round(sum(e.calories or 0 for e in entries), 1),
        "protein": round(sum(e.protein or 0 for e in entries), 1),
        "carbs": round(sum(e.carbs or 0 for e in entries), 1),
        "fat": round(sum(e.fat or 0 for e in entries), 1),
        "fiber": round(sum(e.fiber or 0 for e in entries), 1),
        "total_items": len(entries),
    }

    if not entries:
        return json.dumps({
            "date": log_date.isoformat(),
            "message": f"No food entries found for {log_date.isoformat()}.",
            "totals": totals,
            "meals": {},
            "entries": [],
        })

    return json.dumps({
        "date": log_date.isoformat(),
        "message": f"Found {len(entries)} food entries for {log_date.isoformat()}.",
        "totals": totals,
        "meals": meals,
        "entries": data,
    })


def _get_training_history(input_data, user_id):
    days = input_data.get("days", 14)
    since = _user_today(user_id) - timedelta(days=days)

    entries = TrainingEntry.query.filter(
        TrainingEntry.user_id == user_id,
        TrainingEntry.date >= since
    ).order_by(TrainingEntry.date.desc()).all()

    if not entries:
        return json.dumps({"message": "No training entries recorded yet.", "data": []})

    data = [{
        "date": e.date.isoformat(),
        "exercise": e.exercise_name,
        "category": e.category,
        "sets": e.sets,
        "reps": e.reps,
        "weight_used": e.weight_used,
        "duration_minutes": e.duration_minutes,
        "calories_burned": e.calories_burned,
    } for e in entries]

    categories = list(set(e.category for e in entries if e.category))
    workout_days = len(set(e.date for e in entries))
    summary = {
        "total_exercises": len(data),
        "workout_days": workout_days,
        "categories_trained": categories,
    }
    return json.dumps({"summary": summary, "data": data})


def _lookup_food_nutrition(input_data, user_id):
    food = input_data.get("food_item", "")
    if not food:
        return json.dumps({"error": "No food item provided"})

    result = _usda_lookup(food)
    if result and "error" not in result:
        return json.dumps(result)

    fallback_reason = result.get("error", "No results found") if result else "No results found"
    return json.dumps({
        "message": f"USDA database unavailable for '{food}' ({fallback_reason}).",
        "instruction": f"The USDA database could not be reached or had no match. Use your own nutritional knowledge to provide a reasonable estimate for: {food}. IMPORTANT: Clearly tell the user that this is an AI estimate, not from the USDA database, so they know the values may not be exact.",
        "source": "ai_estimate"
    })


def _usda_lookup(query, max_results=5):
    """Search the USDA FoodData Central database for nutrition info."""
    import requests
    import os

    api_key = os.environ.get('USDA_API_KEY', 'DEMO_KEY')
    url = "https://api.nal.usda.gov/fdc/v1/foods/search"

    try:
        resp = requests.post(f"{url}?api_key={api_key}", json={
            "query": query,
            "pageSize": max_results,
            "dataType": ["Survey (FNDDS)", "SR Legacy", "Foundation"],
        }, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": f"USDA API request failed: {str(e)}"}

    foods = data.get("foods", [])
    if not foods:
        return None

    results = []
    for food in foods:
        nutrients = {}
        for n in food.get("foodNutrients", []):
            name = n.get("nutrientName", "")
            val = n.get("value", 0)
            if "Energy" in name and n.get("unitName") == "KCAL":
                nutrients["calories"] = round(val, 1)
            elif name == "Protein":
                nutrients["protein"] = round(val, 1)
            elif "Carbohydrate" in name:
                nutrients["carbs"] = round(val, 1)
            elif "Total lipid" in name:
                nutrients["fat"] = round(val, 1)
            elif "Fiber, total" in name:
                nutrients["fiber"] = round(val, 1)

        results.append({
            "description": food.get("description", ""),
            "serving_size": food.get("servingSize"),
            "serving_unit": food.get("servingSizeUnit"),
            "data_type": food.get("dataType", ""),
            "nutrients": nutrients,
        })

    top = results[0]
    return {
        "source": "USDA FoodData Central",
        "query": query,
        "best_match": top,
        "other_matches": results[1:] if len(results) > 1 else [],
        "note": f"Nutrition values are per 100g unless a serving size is specified. Best match: {top['description']}"
    }


def _suggest_meal_plan(input_data, user_id):
    # Pass-through for AI to generate based on context
    return json.dumps({
        "instruction": "Generate a detailed meal plan based on the provided parameters. Include specific foods, portions, and macro breakdowns for each meal.",
        "parameters": input_data
    })


def _suggest_workout_plan(input_data, user_id):
    # Pass-through for AI to generate based on context
    return json.dumps({
        "instruction": "Generate a detailed workout plan based on the provided parameters. Include specific exercises, sets, reps, and rest periods.",
        "parameters": input_data
    })


def _get_user_goals(input_data, user_id):
    user = db.session.get(User, user_id)
    return json.dumps({
        "display_name": user.display_name,
        "target_weight": user.target_weight,
        "target_calories": user.target_calories,
        "health_goals": user.health_goals,
        "fitness_level": user.fitness_level,
        "dietary_restrictions": user.dietary_restrictions,
    })


def _update_user_goals(input_data, user_id):
    user = db.session.get(User, user_id)
    updated = []
    if "health_goals" in input_data:
        user.health_goals = input_data["health_goals"]
        updated.append("health_goals")
    if "target_weight" in input_data:
        user.target_weight = input_data["target_weight"]
        updated.append("target_weight")
    if "target_calories" in input_data:
        user.target_calories = input_data["target_calories"]
        updated.append("target_calories")
    if "fitness_level" in input_data:
        user.fitness_level = input_data["fitness_level"]
        updated.append("fitness_level")
    if "dietary_restrictions" in input_data:
        user.dietary_restrictions = input_data["dietary_restrictions"]
        updated.append("dietary_restrictions")
    db.session.commit()
    return json.dumps({
        "success": True,
        "message": f"Updated user goals: {', '.join(updated)}",
        "updated_fields": updated,
    })


def _find_exercise_video(input_data, user_id):
    from urllib.parse import quote_plus
    exercise = input_data.get("exercise_name", "")
    query = quote_plus(f"{exercise} exercise tutorial how to proper form")
    url = f"https://www.youtube.com/results?search_query={query}"
    return json.dumps({
        "exercise": exercise,
        "youtube_search_url": url,
        "message": f"Here's a YouTube search for '{exercise}' tutorials: {url}",
    })


def _save_training_plan(input_data, user_id):
    plan_name = input_data.get("plan_name", "My Training Plan")
    exercises = input_data.get("exercises", [])

    if not exercises:
        return json.dumps({"error": "No exercises provided"})

    # Deactivate existing plan
    TrainingPlan.query.filter_by(user_id=user_id, active=True).update({"active": False})

    # Save new plan
    for i, ex in enumerate(exercises):
        entry = TrainingPlan(
            user_id=user_id,
            name=plan_name,
            day_of_week=ex.get("day_of_week", "monday").lower(),
            exercise_name=ex.get("exercise_name", ""),
            category=ex.get("category"),
            sets=ex.get("sets"),
            reps=ex.get("reps"),
            rest_seconds=ex.get("rest_seconds"),
            notes=ex.get("notes"),
            order_index=i,
            active=True,
        )
        db.session.add(entry)

    db.session.commit()

    days_count = len(set(ex.get("day_of_week", "").lower() for ex in exercises))
    return json.dumps({
        "success": True,
        "message": f"Training plan '{plan_name}' saved with {len(exercises)} exercises across {days_count} days. The user can now see it on their Training page.",
    })


def _get_training_plan(input_data, user_id):
    plan_entries = TrainingPlan.query.filter_by(
        user_id=user_id, active=True
    ).order_by(TrainingPlan.order_index).all()

    if not plan_entries:
        return json.dumps({"message": "No training plan saved yet."})

    plan_name = plan_entries[0].name
    days = {}
    for e in plan_entries:
        day = e.day_of_week
        if day not in days:
            days[day] = []
        days[day].append({
            "exercise": e.exercise_name,
            "category": e.category,
            "sets": e.sets,
            "reps": e.reps,
            "rest_seconds": e.rest_seconds,
            "notes": e.notes,
        })

    return json.dumps({"plan_name": plan_name, "days": days})


def _save_meal_plan(input_data, user_id):
    plan_name = input_data.get("plan_name", "My Meal Plan")
    meals = input_data.get("meals", [])

    if not meals:
        return json.dumps({"error": "No meals provided"})

    # Deactivate existing meal plan
    MealPlan.query.filter_by(user_id=user_id, active=True).update({"active": False})

    # Save new plan
    for i, meal in enumerate(meals):
        entry = MealPlan(
            user_id=user_id,
            name=plan_name,
            day_of_week=meal.get("day_of_week", "monday").lower(),
            meal_type=meal.get("meal_type", "snack").lower(),
            meal_name=meal.get("meal_name", ""),
            serving_size=meal.get("serving_size"),
            calories=meal.get("calories"),
            protein=meal.get("protein"),
            carbs=meal.get("carbs"),
            fat=meal.get("fat"),
            fiber=meal.get("fiber"),
            notes=meal.get("notes"),
            order_index=i,
            active=True,
        )
        db.session.add(entry)

    db.session.commit()

    days_count = len(set(meal.get("day_of_week", "").lower() for meal in meals))
    return json.dumps({
        "success": True,
        "message": f"Meal plan '{plan_name}' saved with {len(meals)} meals across {days_count} days. The user can now see it on their Meal Plan page.",
    })


def _get_meal_plan(input_data, user_id):
    plan_entries = MealPlan.query.filter_by(
        user_id=user_id, active=True
    ).order_by(MealPlan.order_index).all()

    if not plan_entries:
        return json.dumps({"message": "No meal plan saved yet."})

    plan_name = plan_entries[0].name
    days = {}
    for meal in plan_entries:
        day = meal.day_of_week
        if day not in days:
            days[day] = []
        days[day].append({
            "meal_name": meal.meal_name,
            "meal_type": meal.meal_type,
            "serving_size": meal.serving_size,
            "calories": meal.calories,
            "protein": meal.protein,
            "carbs": meal.carbs,
            "fat": meal.fat,
            "fiber": meal.fiber,
            "notes": meal.notes,
        })

    return json.dumps({"plan_name": plan_name, "days": days})


def _get_water_intake(input_data, user_id):
    specific_date = input_data.get("date")
    days = input_data.get("days", 7)

    if specific_date:
        log_date = datetime.strptime(specific_date, "%Y-%m-%d").date()
        entries = WaterEntry.query.filter_by(
            user_id=user_id, date=log_date
        ).order_by(WaterEntry.created_at).all()

        data = [{
            "amount_ml": e.amount_ml,
            "time": e.time,
            "notes": e.notes,
        } for e in entries]

        total = sum(e.amount_ml or 0 for e in entries)
        return json.dumps({
            "date": log_date.isoformat(),
            "total_ml": round(total, 1),
            "entries": data,
        })

    since = _user_today(user_id) - timedelta(days=days)
    from sqlalchemy import func
    results = db.session.query(
        WaterEntry.date,
        func.sum(WaterEntry.amount_ml).label('total_ml'),
        func.count(WaterEntry.id).label('count'),
    ).filter(
        WaterEntry.user_id == user_id,
        WaterEntry.date >= since,
    ).group_by(WaterEntry.date).order_by(WaterEntry.date.desc()).all()

    if not results:
        return json.dumps({"message": "No water intake recorded yet.", "data": []})

    data = [{
        "date": r.date.isoformat(),
        "total_ml": round(float(r.total_ml or 0), 1),
        "entries": r.count,
    } for r in results]

    avg = sum(d["total_ml"] for d in data) / len(data) if data else 0
    return json.dumps({
        "summary": {"days_with_data": len(data), "avg_daily_ml": round(avg, 0)},
        "data": data,
    })


def _get_caffeine_intake(input_data, user_id):
    specific_date = input_data.get("date")
    days = input_data.get("days", 7)

    if specific_date:
        log_date = datetime.strptime(specific_date, "%Y-%m-%d").date()
        entries = CaffeineEntry.query.filter_by(
            user_id=user_id, date=log_date
        ).order_by(CaffeineEntry.created_at).all()

        data = [{
            "amount_mg": e.amount_mg,
            "source": e.source,
            "time": e.time,
            "notes": e.notes,
        } for e in entries]

        total = sum(e.amount_mg or 0 for e in entries)
        return json.dumps({
            "date": log_date.isoformat(),
            "total_mg": round(total, 1),
            "entries": data,
        })

    since = _user_today(user_id) - timedelta(days=days)
    from sqlalchemy import func
    results = db.session.query(
        CaffeineEntry.date,
        func.sum(CaffeineEntry.amount_mg).label('total_mg'),
        func.count(CaffeineEntry.id).label('count'),
    ).filter(
        CaffeineEntry.user_id == user_id,
        CaffeineEntry.date >= since,
    ).group_by(CaffeineEntry.date).order_by(CaffeineEntry.date.desc()).all()

    if not results:
        return json.dumps({"message": "No caffeine intake recorded yet.", "data": []})

    data = [{
        "date": r.date.isoformat(),
        "total_mg": round(float(r.total_mg or 0), 1),
        "entries": r.count,
    } for r in results]

    avg = sum(d["total_mg"] for d in data) / len(data) if data else 0
    return json.dumps({
        "summary": {"days_with_data": len(data), "avg_daily_mg": round(avg, 0)},
        "data": data,
    })
