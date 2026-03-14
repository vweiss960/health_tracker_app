import json
from datetime import date
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user


motivation_bp = Blueprint('motivation', __name__)



@motivation_bp.route('/')
@login_required
def motivation_page():
    from models import DailyMotivation
    has_daily = DailyMotivation.query.filter_by(date=date.today()).first() is not None
    return render_template('motivation.html', has_daily=has_daily)


@motivation_bp.route('/api/daily-content', methods=['POST'])
@login_required
def get_daily_content():
    """Return pre-generated daily motivational content."""
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


@motivation_bp.route('/api/search-motivation', methods=['POST'])
@login_required
def search_motivation():
    """Search YouTube directly using text provided by the user."""
    data = request.get_json() or {}
    text = (data.get('text', '') or '').strip()

    if not text:
        return jsonify({'error': 'Enter what motivates you to search for content.'}), 400

    try:
        # Each line becomes a YouTube search query
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        queries = [line for line in lines[:5]]

        print(f"[Motivation] User search: {queries}")
        results = _search_youtube(queries)

        if not results:
            return jsonify({'error': 'No results found. Try different search terms.'}), 404

        return jsonify({'results': results})

    except Exception as e:
        print(f"[Motivation] Search error: {e}")
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500


def _normalize_title(title):
    """Normalize a title for deduplication: lowercase, strip punctuation and extra spaces."""
    import re
    t = title.lower().strip()
    t = re.sub(r'[^\w\s]', '', t)  # remove punctuation
    t = re.sub(r'\s+', ' ', t)     # collapse whitespace
    return t


def _search_youtube(queries, max_per_query=4):
    """Search regular YouTube for videos using yt-dlp."""
    import concurrent.futures

    all_items = []  # collect raw results from all queries first

    def _do_search(query):
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

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        future_map = {executor.submit(_do_search, q): q for q in queries}
        for future in concurrent.futures.as_completed(future_map, timeout=30):
            try:
                search_results = future.result(timeout=15)
            except Exception:
                continue
            all_items.extend(search_results or [])

    # Deduplicate by video ID and normalized title
    results = []
    seen_ids = set()
    seen_titles = set()

    for item in all_items:
        video_id = item.get('id', '') or item.get('url', '')
        if not video_id or video_id in seen_ids:
            continue

        title = item.get('title', '')
        if not title:
            continue

        norm_title = _normalize_title(title)
        if norm_title in seen_titles:
            continue

        seen_ids.add(video_id)
        seen_titles.add(norm_title)

        channel = item.get('uploader', '') or item.get('channel', '') or ''
        duration_secs = item.get('duration')

        # Skip videos shorter than 2 minutes
        if duration_secs and int(duration_secs) < 120:
            continue

        if duration_secs:
            mins, secs = divmod(int(duration_secs), 60)
            duration = f"{mins}:{secs:02d}"
        else:
            duration = ''

        thumb_id = item.get('id', video_id)
        thumbnail = f"https://i.ytimg.com/vi/{thumb_id}/hqdefault.jpg"

        url = item.get('url', '')
        if not url.startswith('http'):
            url = f"https://www.youtube.com/watch?v={thumb_id}"

        results.append({
            'type': 'video',
            'video_id': thumb_id,
            'title': title,
            'description': f'{channel} • {duration}' if channel and duration else channel or duration or '',
            'url': url,
            'thumbnail': thumbnail,
            'source_hint': channel,
        })

    return results[:10]
