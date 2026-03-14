import json
import time
import random
from datetime import date
from urllib.parse import quote_plus
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

motivation_bp = Blueprint('motivation', __name__)


def _get_effective_ai_key(user):
    """Return the AI API key to use: user's own key, or system key if granted."""
    if user.ai_api_key:
        return user.ai_api_key, user.ai_provider or 'claude'
    if user.use_system_ai_key:
        from models import SystemConfig
        sys_key = SystemConfig.get('system_ai_api_key')
        if sys_key:
            return sys_key, 'claude'
    return None, user.ai_provider or 'claude'


# ---- Category keyword map for non-AI personalization fallback ----
CATEGORY_KEYWORDS = {
    'general': ['fitness motivation', 'workout motivation', 'discipline fitness'],
    'weight_loss': ['weight loss journey', 'fat loss tips', 'body transformation'],
    'muscle_building': ['muscle building', 'strength training', 'hypertrophy'],
    'nutrition': ['healthy eating', 'meal prep', 'nutrition tips'],
    'mindset': ['mental toughness fitness', 'discipline vs motivation', 'growth mindset'],
    'success_stories': ['fitness transformation story', 'before and after fitness', 'weight loss success'],
}


@motivation_bp.route('/')
@login_required
def motivation_page():
    has_key = bool(_get_effective_ai_key(current_user)[0])
    from models import DailyMotivation
    has_daily = DailyMotivation.query.filter_by(date=date.today()).first() is not None
    # Check if user has profile data for personalization
    has_profile = bool(current_user.motivation_text or current_user.health_goals
                       or current_user.fitness_level)
    return render_template('motivation.html', has_api_key=has_key, has_daily=has_daily,
                           has_profile=has_profile)


@motivation_bp.route('/api/daily-content', methods=['POST'])
@login_required
def get_daily_content():
    """Return pre-generated daily motivational content (no API key needed)."""
    data = request.get_json() or {}
    category = data.get('category', 'general')

    from models import DailyMotivation
    entry = DailyMotivation.query.filter_by(date=date.today(), category=category).first()
    if not entry:
        return jsonify({'error': 'Daily content not yet generated. Check back later.'}), 404

    results = json.loads(entry.content_json)
    return jsonify({'category': category, 'results': results})


@motivation_bp.route('/api/save-motivation', methods=['POST'])
@login_required
def save_motivation_text():
    """Save the user's motivation text (full replacement from textarea)."""
    from models import db
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    current_user.motivation_text = text if text else None
    db.session.commit()
    return jsonify({'ok': True, 'text': current_user.motivation_text or ''})


@motivation_bp.route('/api/get-content', methods=['POST'])
@login_required
def get_content():
    """Personalized motivation: AI generates search queries, ytmusicapi finds real videos."""
    data = request.get_json() or {}
    category = data.get('category', 'general')

    from models import User
    user = User.query.get(current_user.id)

    # Build user context — motivation text is the primary input
    motivation_text = (user.motivation_text or '').strip()
    background_parts = []
    if user.health_goals:
        background_parts.append(f"Health goals: {user.health_goals}")
    if user.fitness_level:
        background_parts.append(f"Fitness level: {user.fitness_level}")
    if user.dietary_restrictions:
        background_parts.append(f"Diet: {user.dietary_restrictions}")
    background = '; '.join(background_parts)

    try:
        # Try AI-powered search query generation
        ai_key, ai_provider = _get_effective_ai_key(current_user)
        if ai_key and (motivation_text or background):
            queries = _ai_generate_search_queries(ai_provider, ai_key, category,
                                                   motivation_text, background)
            if queries:
                print(f"[Motivation] AI queries for {category}: {queries}")
                results = _search_youtube(queries)
                if results:
                    return jsonify({'category': category, 'results': results})

        # Fallback: build queries from profile fields directly (no AI)
        queries = _build_profile_queries(user, category)
        print(f"[Motivation] Fallback queries for {category}: {queries}")
        results = _search_youtube(queries)

        if not results:
            return jsonify({'error': 'Could not find personalized content. Try updating your motivation text above.'}), 404

        return jsonify({'category': category, 'results': results})

    except Exception as e:
        print(f"[Motivation] Personalized content error: {e}")
        return jsonify({'error': 'Something went wrong generating personalized content. Please try again.'}), 500


def _ai_generate_search_queries(provider, api_key, category, motivation_text, background):
    """Use AI to generate 5 YouTube search queries tailored to the user. Minimal token usage."""
    category_labels = {
        'general': 'fitness motivation',
        'weight_loss': 'weight loss',
        'muscle_building': 'muscle building',
        'nutrition': 'nutrition and healthy eating',
        'mindset': 'mental toughness and discipline',
        'success_stories': 'fitness transformation stories',
    }
    topic = category_labels.get(category, 'fitness motivation')

    # Build prompt with motivation text as the PRIMARY input
    prompt_parts = [
        f"Generate exactly 5 YouTube search queries about {topic}.",
        "",
        "THE MOST IMPORTANT INPUT — the user wrote this about what motivates them:",
    ]

    if motivation_text:
        prompt_parts.append(f'"""\n{motivation_text}\n"""')
    else:
        prompt_parts.append("(No motivation text provided)")

    if background:
        prompt_parts.append(f"\nAdditional context: {background}")

    prompt_parts.extend([
        "",
        "Each search query MUST directly reflect the user's specific words, goals, and interests above.",
        "Do NOT use generic fitness queries — make every query specific to what they wrote.",
        "Return ONLY a JSON array of 5 search query strings. No other text.",
    ])

    prompt = '\n'.join(prompt_parts)

    try:
        if provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=15)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            text = resp.choices[0].message.content.strip()
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=15)
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = resp.content[0].text.strip()

        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
            text = text.strip()

        queries = json.loads(text)
        if isinstance(queries, list) and all(isinstance(q, str) for q in queries):
            return queries[:5]
    except Exception as e:
        print(f"[Motivation] AI query generation failed: {e}")

    return None


def _build_profile_queries(user, category):
    """Build YouTube search queries from user profile fields (no AI needed)."""
    category_labels = {
        'general': 'fitness motivation',
        'weight_loss': 'weight loss',
        'muscle_building': 'muscle building',
        'nutrition': 'nutrition healthy eating',
        'mindset': 'mental toughness discipline',
        'success_stories': 'fitness transformation',
    }
    topic = category_labels.get(category, 'fitness motivation')
    queries = []

    # Use each line of motivation text as a direct search query combined with the topic
    if user.motivation_text:
        lines = [ln.strip() for ln in user.motivation_text.splitlines() if ln.strip()]
        for line in lines[:4]:
            queries.append(f"{line} {topic}")

    # Add queries from health goals
    if user.health_goals and len(queries) < 5:
        queries.append(f"{user.health_goals[:60]} {topic}")

    # If still not enough, pad with category keywords + fitness level
    if len(queries) < 3:
        keywords = CATEGORY_KEYWORDS.get(category, CATEGORY_KEYWORDS['general'])
        level = user.fitness_level or ''
        for kw in keywords:
            if len(queries) >= 5:
                break
            queries.append(f"{kw} {level}".strip())

    return queries[:5]


def _search_youtube(queries, max_per_query=2):
    """Search regular YouTube for videos using yt-dlp."""
    import concurrent.futures

    results = []
    seen_ids = set()

    def _do_search(query):
        """Use yt-dlp to search regular YouTube (not YouTube Music)."""
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'skip_download': True,
                'socket_timeout': 10,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_url = f"ytsearch{max_per_query + 2}:{query}"
                info = ydl.extract_info(search_url, download=False)
                return info.get('entries', []) if info else []
        except Exception as e:
            print(f"[Motivation] YouTube search error for '{query}': {e}")
            return []

    # Run searches in parallel with a timeout
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(_do_search, q): q for q in queries}
        for future in concurrent.futures.as_completed(future_map, timeout=30):
            try:
                search_results = future.result(timeout=15)
            except Exception:
                continue

            count = 0
            for item in (search_results or []):
                if count >= max_per_query:
                    break
                video_id = item.get('id', '') or item.get('url', '')
                if not video_id or video_id in seen_ids:
                    continue
                seen_ids.add(video_id)

                title = item.get('title', '')
                if not title:
                    continue

                channel = item.get('uploader', '') or item.get('channel', '') or ''
                duration_secs = item.get('duration')
                if duration_secs:
                    mins, secs = divmod(int(duration_secs), 60)
                    duration = f"{mins}:{secs:02d}"
                else:
                    duration = ''

                # Build thumbnail URL from video ID
                thumb_id = item.get('id', video_id)
                thumbnail = f"https://i.ytimg.com/vi/{thumb_id}/hqdefault.jpg"

                url = item.get('url', '')
                if not url.startswith('http'):
                    url = f"https://www.youtube.com/watch?v={thumb_id}"

                results.append({
                    'type': 'video',
                    'title': title,
                    'description': f'{channel} • {duration}' if channel and duration else channel or duration or '',
                    'url': url,
                    'thumbnail': thumbnail,
                    'source_hint': channel,
                })
                count += 1

    # Limit to 6, shuffle for variety
    results = results[:6]
    random.shuffle(results)
    return results
