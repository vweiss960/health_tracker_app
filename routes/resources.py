from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from models import db, SavedPlaylist

resources_bp = Blueprint('resources', __name__)


def _get_effective_ai_key_resources(user):
    """Return the AI API key to use: user's own key, or system key if granted."""
    if user.ai_api_key:
        return user.ai_api_key, user.ai_provider or 'claude'
    if user.use_system_ai_key:
        from models import SystemConfig
        sys_key = SystemConfig.get('system_ai_api_key')
        if sys_key:
            return sys_key, 'claude'
    return None, user.ai_provider or 'claude'


@resources_bp.route('/')
@login_required
def resources_page():
    has_yt_key = bool(current_user.youtube_api_key)
    saved = SavedPlaylist.query.filter_by(user_id=current_user.id).order_by(SavedPlaylist.created_at.desc()).all()
    return render_template('resources_music.html', has_yt_key=has_yt_key, saved_playlists=saved)


@resources_bp.route('/api/save-playlist', methods=['POST'])
@login_required
def save_playlist():
    data = request.get_json() or {}
    youtube_id = data.get('id', '').strip()
    title = data.get('title', '').strip()
    if not youtube_id or not title:
        return jsonify({'error': 'Missing playlist info'}), 400

    existing = SavedPlaylist.query.filter_by(user_id=current_user.id, youtube_id=youtube_id).first()
    if existing:
        return jsonify({'error': 'Already saved'}), 409

    sp = SavedPlaylist(
        user_id=current_user.id,
        title=title,
        playlist_type=data.get('type', 'playlist'),
        youtube_id=youtube_id,
        thumbnail=data.get('thumbnail', ''),
        channel=data.get('channel', ''),
        search_query=data.get('query', ''),
    )
    db.session.add(sp)
    db.session.commit()
    return jsonify({'ok': True, 'id': sp.id})


@resources_bp.route('/api/delete-playlist/<int:playlist_id>', methods=['POST'])
@login_required
def delete_playlist(playlist_id):
    sp = SavedPlaylist.query.filter_by(id=playlist_id, user_id=current_user.id).first()
    if not sp:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(sp)
    db.session.commit()
    return jsonify({'ok': True})


@resources_bp.route('/player')
@login_required
def popup_player():
    return render_template('resources_player.html')


@resources_bp.route('/api/music-search', methods=['POST'])
@login_required
def music_search():
    """Use AI to generate YouTube music suggestions, then find real playlists."""
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'error': 'Please describe the music you want'}), 400

    ai_key, ai_provider = _get_effective_ai_key_resources(current_user)
    if not ai_key:
        return jsonify({'error': 'No AI API key configured. Add one in Settings.'}), 400

    yt_key = current_user.youtube_api_key

    # Step 1: AI generates optimized search queries
    suggestions = _ai_music_suggestions(ai_provider, ai_key, prompt)
    if not suggestions:
        return jsonify({'error': 'AI failed to generate suggestions. Check your AI API key.'}), 502

    # Step 2: Resolve to real YouTube playlist IDs
    if yt_key:
        results = _resolve_with_youtube_api(yt_key, suggestions)
    else:
        results = _resolve_with_ytmusic(suggestions)

    if not results:
        return jsonify({'error': 'Could not find playable playlists. Try a different description.'}), 404

    # Step 3: With API key, enrich with playlist details and sort by popularity
    if yt_key:
        results = _enrich_and_sort_playlists(yt_key, results)

    # Step 4: Deduplicate and prefer results with thumbnails
    results = _dedupe_and_prefer_thumbnails(results)

    # Step 5: Filter out user's already-saved playlists
    saved_ids = {sp.youtube_id for sp in SavedPlaylist.query.filter_by(user_id=current_user.id).all()}
    if saved_ids:
        results = [r for r in results if r.get('id', '') not in saved_ids]

    # Step 6: Filter out search-only fallbacks and ensure exactly 6 results
    results = [r for r in results if r.get('type') != 'search'] or results
    results = results[:6]

    return jsonify({'search_query': prompt, 'results': results})


@resources_bp.route('/api/playlist-details')
@login_required
def playlist_details():
    """Fetch tracklist for a playlist. Requires YouTube API key."""
    playlist_id = request.args.get('id', '').strip()
    if not playlist_id:
        return jsonify({'error': 'No playlist ID'}), 400

    yt_key = current_user.youtube_api_key
    if not yt_key:
        return jsonify({'error': 'YouTube API key required for tracklist'}), 400

    tracks = _fetch_playlist_tracks(yt_key, playlist_id)
    return jsonify({'playlist_id': playlist_id, 'tracks': tracks})


@resources_bp.route('/api/more-like-this', methods=['POST'])
@login_required
def more_like_this():
    """Find similar playlists based on a query."""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    title = data.get('title', '').strip()
    if not query and not title:
        return jsonify({'error': 'No query provided'}), 400

    search_term = query or title
    yt_key = current_user.youtube_api_key

    if yt_key:
        results = _more_like_this_api(yt_key, search_term)
    else:
        results = _more_like_this_ytmusic(search_term)

    if not results:
        return jsonify({'error': 'No similar playlists found'}), 404

    if yt_key:
        results = _enrich_and_sort_playlists(yt_key, results)

    # Deduplicate, prefer thumbnails, filter saved
    results = _dedupe_and_prefer_thumbnails(results)
    saved_ids = {sp.youtube_id for sp in SavedPlaylist.query.filter_by(user_id=current_user.id).all()}
    if saved_ids:
        results = [r for r in results if r.get('id', '') not in saved_ids]

    results = [r for r in results if r.get('type') != 'search'] or results
    results = results[:6]

    return jsonify({'results': results})


def _ai_music_suggestions(provider, api_key, user_prompt):
    """Ask AI to suggest specific YouTube Music searches."""
    import json as _json

    system = (
        "You are a music recommendation assistant. The user describes what they want to listen to. "
        "Return a JSON array of 10 music suggestions. Each item should be an object with:\n"
        '- "title": A descriptive title for this suggestion\n'
        '- "query": An optimized YouTube Music search query to find this (be specific with genres, artists, descriptors)\n'
        '- "description": A one-line description of why this fits\n\n'
        "Return ONLY valid JSON array, no other text. Focus on playlists, mixes, and compilations. "
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
        if not query:
            return [_search_fallback(s)]

        try:
            search_results = ytmusic.search(query, filter='playlists', limit=3)
            if not search_results:
                return [_search_fallback(s)]

            found = []
            for item in search_results:
                playlist_id = item.get('browseId', '')
                # browseId format is VL + playlistId, strip VL prefix
                if playlist_id.startswith('VL'):
                    playlist_id = playlist_id[2:]
                if playlist_id:
                    found.append({
                        'type': 'playlist',
                        'id': playlist_id,
                        'title': item.get('title', '') or s.get('title', query),
                        'channel': item.get('author', ''),
                        'thumbnail': _best_thumbnail(item),
                        'description': s.get('description', ''),
                        'query': query,
                    })
            return found if found else [_search_fallback(s)]
        except Exception:
            pass

        return [_search_fallback(s)]

    with ThreadPoolExecutor(max_workers=6) as executor:
        nested = list(executor.map(resolve, suggestions))
    results = [r for group in nested for r in group]

    return results


def _best_thumbnail(item):
    """Extract the best thumbnail URL from a ytmusicapi result."""
    thumbnails = item.get('thumbnails', [])
    if thumbnails:
        return thumbnails[-1].get('url', '')
    return ''


def _resolve_with_youtube_api(api_key, suggestions):
    """Use YouTube Data API to search and get real playlist IDs (parallel)."""
    import requests
    from concurrent.futures import ThreadPoolExecutor

    def resolve(s):
        query = s.get('query', '')
        if not query:
            return [_search_fallback(s)]
        try:
            resp = requests.get('https://www.googleapis.com/youtube/v3/search', params={
                'part': 'snippet',
                'q': query,
                'type': 'playlist',
                'maxResults': 3,
                'key': api_key,
            }, timeout=5)
            resp.raise_for_status()
            items = resp.json().get('items', [])
            if items:
                found = []
                for item in items:
                    found.append({
                        'type': 'playlist',
                        'id': item['id']['playlistId'],
                        'title': item['snippet']['title'],
                        'channel': item['snippet']['channelTitle'],
                        'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', ''),
                        'description': s.get('description', ''),
                        'query': query,
                    })
                return found
        except Exception:
            pass
        return [_search_fallback(s)]

    with ThreadPoolExecutor(max_workers=6) as executor:
        nested = list(executor.map(resolve, suggestions))
    results = [r for group in nested for r in group]

    return results


def _enrich_and_sort_playlists(api_key, results):
    """Fetch playlist metadata (item count) and sort by popularity. API key required."""
    import requests

    playlist_ids = [r['id'] for r in results if r.get('id') and r.get('type') == 'playlist']
    if not playlist_ids:
        return results

    try:
        resp = requests.get('https://www.googleapis.com/youtube/v3/playlists', params={
            'part': 'contentDetails',
            'id': ','.join(playlist_ids),
            'key': api_key,
        }, timeout=5)
        resp.raise_for_status()
        items = resp.json().get('items', [])
        details = {item['id']: item.get('contentDetails', {}) for item in items}
    except Exception:
        return results

    for r in results:
        pid = r.get('id', '')
        if pid in details:
            r['track_count'] = details[pid].get('itemCount', 0)

    # Sort: playlists with more tracks first (proxy for popularity), fallbacks last
    results.sort(key=lambda r: r.get('track_count', 0), reverse=True)
    return results


def _fetch_playlist_tracks(api_key, playlist_id, max_tracks=25):
    """Fetch track titles from a playlist via YouTube Data API."""
    import requests

    tracks = []
    try:
        resp = requests.get('https://www.googleapis.com/youtube/v3/playlistItems', params={
            'part': 'snippet',
            'playlistId': playlist_id,
            'maxResults': max_tracks,
            'key': api_key,
        }, timeout=5)
        resp.raise_for_status()
        for item in resp.json().get('items', []):
            snippet = item.get('snippet', {})
            video_id = snippet.get('resourceId', {}).get('videoId', '')
            tracks.append({
                'title': snippet.get('title', ''),
                'channel': snippet.get('videoOwnerChannelTitle', ''),
                'position': snippet.get('position', 0),
                'videoId': video_id,
            })
    except Exception:
        pass

    return tracks


def _more_like_this_api(api_key, search_term):
    """Find similar playlists using YouTube Data API."""
    import requests

    try:
        resp = requests.get('https://www.googleapis.com/youtube/v3/search', params={
            'part': 'snippet',
            'q': search_term,
            'type': 'playlist',
            'maxResults': 6,
            'key': api_key,
        }, timeout=5)
        resp.raise_for_status()
        results = []
        for item in resp.json().get('items', []):
            results.append({
                'type': 'playlist',
                'id': item['id']['playlistId'],
                'title': item['snippet']['title'],
                'channel': item['snippet']['channelTitle'],
                'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', ''),
                'description': '',
                'query': search_term,
            })
        return results
    except Exception:
        return []


def _more_like_this_ytmusic(search_term):
    """Find similar playlists using ytmusicapi (no API key)."""
    from ytmusicapi import YTMusic

    ytmusic = YTMusic()
    results = []
    try:
        items = ytmusic.search(search_term, filter='playlists', limit=6)
        for item in items:
            playlist_id = item.get('browseId', '')
            if playlist_id.startswith('VL'):
                playlist_id = playlist_id[2:]
            if playlist_id:
                results.append({
                    'type': 'playlist',
                    'id': playlist_id,
                    'title': item.get('title', ''),
                    'channel': item.get('author', ''),
                    'thumbnail': _best_thumbnail(item),
                    'description': '',
                    'query': search_term,
                })
    except Exception:
        pass

    return results


def _dedupe_and_prefer_thumbnails(results):
    """Remove duplicate playlist IDs, keeping the one with a thumbnail if available."""
    seen = {}
    for r in results:
        rid = r.get('id', '')
        if not rid:
            # Keep all fallback/search results
            seen[id(r)] = r
            continue
        if rid in seen:
            # Replace if existing has no thumbnail but this one does
            if not seen[rid].get('thumbnail') and r.get('thumbnail'):
                seen[rid] = r
        else:
            seen[rid] = r
    # Sort: items with thumbnails first, then by track_count desc
    deduped = list(seen.values())
    deduped.sort(key=lambda r: (0 if r.get('thumbnail') else 1, -(r.get('track_count') or 0)))
    return deduped


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
