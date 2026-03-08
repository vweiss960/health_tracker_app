from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

resources_bp = Blueprint('resources', __name__)


@resources_bp.route('/')
@login_required
def resources_page():
    has_yt_key = bool(current_user.youtube_api_key)
    return render_template('resources_music.html', has_yt_key=has_yt_key)


@resources_bp.route('/api/music-search', methods=['POST'])
@login_required
def music_search():
    """Use AI to generate YouTube music suggestions, then find real videos."""
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'error': 'Please describe the music you want'}), 400

    ai_key = current_user.ai_api_key
    if not ai_key:
        return jsonify({'error': 'No AI API key configured. Add one in Settings.'}), 400

    yt_key = current_user.youtube_api_key

    # Step 1: AI generates optimized search queries
    suggestions = _ai_music_suggestions(current_user.ai_provider, ai_key, prompt)
    if not suggestions:
        return jsonify({'error': 'AI failed to generate suggestions. Check your AI API key.'}), 502

    # Step 2: Resolve to real YouTube video/playlist IDs
    if yt_key:
        results = _resolve_with_youtube_api(yt_key, suggestions)
    else:
        results = _resolve_with_ytmusic(suggestions)

    if not results:
        return jsonify({'error': 'Could not find playable videos. Try a different description.'}), 404

    return jsonify({'search_query': prompt, 'results': results})


def _ai_music_suggestions(provider, api_key, user_prompt):
    """Ask AI to suggest specific YouTube Music searches."""
    import json as _json

    system = (
        "You are a music recommendation assistant. The user describes what they want to listen to. "
        "Return a JSON array of 6 music suggestions. Each item should be an object with:\n"
        '- "title": A descriptive title for this suggestion\n'
        '- "query": An optimized YouTube Music search query to find this (be specific with genres, artists, descriptors)\n'
        '- "search_type": Either "songs" or "playlists" — use "playlists" for mixes/compilations, "songs" for individual tracks\n'
        '- "description": A one-line description of why this fits\n\n'
        "Return ONLY valid JSON array, no other text. Include a mix of individual songs and playlists. "
        "Prefer well-known artists and popular playlists/mixes."
    )
    messages = [{"role": "user", "content": user_prompt}]

    try:
        if provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system}] + messages,
                max_tokens=800,
            )
            text = resp.choices[0].message.content.strip()
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                system=system,
                messages=messages,
            )
            text = resp.content[0].text.strip()

        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
            text = text.strip()

        return _json.loads(text)
    except Exception:
        return None


def _resolve_with_ytmusic(suggestions):
    """Use ytmusicapi to search YouTube Music for real video/playlist IDs (parallel, no API key)."""
    from concurrent.futures import ThreadPoolExecutor
    from ytmusicapi import YTMusic

    ytmusic = YTMusic()

    def resolve(s):
        query = s.get('query', '')
        search_type = s.get('search_type', 'songs')
        if not query:
            return _search_fallback(s)

        # Validate search_type
        if search_type not in ('songs', 'playlists'):
            search_type = 'songs'

        try:
            results = ytmusic.search(query, filter=search_type, limit=3)
            if not results:
                return _search_fallback(s)

            if search_type == 'playlists':
                for item in results:
                    playlist_id = item.get('browseId', '')
                    # browseId format is VL + playlistId, strip VL prefix
                    if playlist_id.startswith('VL'):
                        playlist_id = playlist_id[2:]
                    if playlist_id:
                        return {
                            'type': 'playlist',
                            'id': playlist_id,
                            'title': item.get('title', '') or s.get('title', query),
                            'channel': item.get('author', ''),
                            'thumbnail': _best_thumbnail(item),
                            'description': s.get('description', ''),
                            'query': query,
                        }
            else:
                for item in results:
                    video_id = item.get('videoId', '')
                    if video_id:
                        artists = ', '.join(a.get('name', '') for a in item.get('artists', []))
                        return {
                            'type': 'video',
                            'id': video_id,
                            'title': item.get('title', '') or s.get('title', query),
                            'channel': artists,
                            'thumbnail': _best_thumbnail(item),
                            'description': s.get('description', ''),
                            'query': query,
                        }
        except Exception:
            pass

        return _search_fallback(s)

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(resolve, suggestions))

    return results


def _best_thumbnail(item):
    """Extract the best thumbnail URL from a ytmusicapi result."""
    thumbnails = item.get('thumbnails', [])
    if thumbnails:
        return thumbnails[-1].get('url', '')
    return ''


def _resolve_with_youtube_api(api_key, suggestions):
    """Use YouTube Data API to search and get real video IDs (parallel)."""
    import requests
    from concurrent.futures import ThreadPoolExecutor

    def resolve(s):
        query = s.get('query', '')
        if not query:
            return _search_fallback(s)
        try:
            resp = requests.get('https://www.googleapis.com/youtube/v3/search', params={
                'part': 'snippet',
                'q': query,
                'type': 'video',
                'maxResults': 1,
                'videoEmbeddable': 'true',
                'key': api_key,
            }, timeout=5)
            resp.raise_for_status()
            items = resp.json().get('items', [])
            if items:
                item = items[0]
                return {
                    'type': 'video',
                    'id': item['id']['videoId'],
                    'title': item['snippet']['title'],
                    'channel': item['snippet']['channelTitle'],
                    'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', ''),
                    'description': s.get('description', ''),
                    'query': query,
                }
        except Exception:
            pass
        return _search_fallback(s)

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(resolve, suggestions))

    return results


def _search_fallback(s):
    """Return a search-only result (opens YouTube search in new tab)."""
    query = s.get('query', s.get('title', ''))
    return {
        'type': 'search',
        'id': '',
        'title': s.get('title', query),
        'channel': '',
        'thumbnail': '',
        'description': s.get('description', ''),
        'query': query,
    }
