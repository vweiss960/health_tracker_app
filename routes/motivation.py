from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

motivation_bp = Blueprint('motivation', __name__)


@motivation_bp.route('/')
@login_required
def motivation_page():
    has_key = bool(current_user.ai_api_key)
    return render_template('motivation.html', has_api_key=has_key)


@motivation_bp.route('/api/get-content', methods=['POST'])
@login_required
def get_content():
    """Use AI to generate motivational content recommendations."""
    data = request.get_json() or {}
    category = data.get('category', 'general')

    ai_key = current_user.ai_api_key
    if not ai_key:
        return jsonify({'error': 'No AI API key configured. Add one in Settings.'}), 400

    # Fetch user goals for personalization
    from models import User
    user = User.query.get(current_user.id)
    goals_context = ""
    if user.health_goals:
        goals_context += f"User's goals: {user.health_goals}. "
    if user.fitness_level:
        goals_context += f"Fitness level: {user.fitness_level}. "
    if user.target_weight:
        goals_context += f"Target weight: {user.target_weight}. "
    if user.dietary_restrictions:
        goals_context += f"Dietary preferences: {user.dietary_restrictions}. "

    content = _ai_motivation_content(
        current_user.ai_provider, ai_key, category, goals_context)

    if not content:
        return jsonify({'error': 'AI failed to generate content. Check your API key.'}), 502

    return jsonify({'category': category, 'results': content})


def _ai_motivation_content(provider, api_key, category, goals_context):
    """Ask AI to generate motivational content with real YouTube/web links."""
    import json as _json

    category_prompts = {
        'general': 'general fitness motivation, discipline, and consistency',
        'weight_loss': 'weight loss journeys, body transformation stories, and fat loss tips',
        'muscle_building': 'muscle building motivation, bodybuilding, and strength gains',
        'nutrition': 'healthy eating motivation, meal prep inspiration, and nutrition education',
        'mindset': 'mental toughness, discipline, overcoming plateaus, and growth mindset for fitness',
        'success_stories': 'real transformation stories, before/after journeys, and fitness success',
    }

    topic = category_prompts.get(category, category_prompts['general'])

    system = (
        "You are a fitness motivation assistant. Generate motivational content recommendations "
        "for someone on their fitness journey.\n\n"
        f"USER CONTEXT: {goals_context}\n\n" if goals_context else
        "You are a fitness motivation assistant. Generate motivational content recommendations "
        "for someone on their fitness journey.\n\n"
    )
    system += (
        "Return a JSON array of 6 items. Each item should have:\n"
        '- "title": A compelling title for this content\n'
        '- "description": 2-3 sentence description of why this is motivating and relevant\n'
        '- "type": Either "video" or "article"\n'
        '- "youtube_query": For videos, an optimized YouTube search query to find this specific content '
        '(use specific creator names, video titles, or distinctive phrases). For articles, leave empty.\n'
        '- "web_query": For articles, an optimized Google search query. For videos, leave empty.\n'
        '- "source_hint": Suggest a specific YouTuber, channel, website, or creator known for this content\n\n'
        "Return ONLY valid JSON array, no other text. Mix videos and articles. "
        "Prefer well-known fitness YouTubers (Jeff Nippard, AthleanX, Natacha Oceane, Greg Doucette, "
        "Renaissance Periodization, etc.) and reputable fitness websites. "
        "Make recommendations specific and actionable, not generic."
    )

    user_msg = f"Find motivational content about: {topic}"

    try:
        if provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg}
                ],
                max_tokens=1200,
            )
            text = resp.choices[0].message.content.strip()
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )
            text = resp.content[0].text.strip()

        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
            text = text.strip()

        results = _json.loads(text)

        # Build actionable URLs for each result
        from urllib.parse import quote_plus
        for r in results:
            if r.get('type') == 'video' and r.get('youtube_query'):
                r['url'] = f"https://www.youtube.com/results?search_query={quote_plus(r['youtube_query'])}"
            elif r.get('web_query'):
                r['url'] = f"https://www.google.com/search?q={quote_plus(r['web_query'])}"
            else:
                r['url'] = ''

        return results
    except Exception:
        return None
