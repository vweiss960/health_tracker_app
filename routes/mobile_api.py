"""Mobile API blueprint — token-authenticated endpoints for the Android music player."""

import secrets
from functools import wraps
from flask import Blueprint, request, jsonify, g
from werkzeug.security import check_password_hash
from models import db, User, SavedPlaylist

mobile_api_bp = Blueprint('mobile_api', __name__)


# ── Authentication decorator ────────────────────────────────────────────────

def token_required(f):
    """Require a valid Bearer token in the Authorization header."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        token = auth[7:]
        user = User.query.filter_by(api_token=token).first()
        if not user:
            return jsonify({'error': 'Invalid token'}), 401
        g.api_user = user
        return f(*args, **kwargs)
    return decorated


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


# ── Login ────────────────────────────────────────────────────────────────────

@mobile_api_bp.route('/login', methods=['POST'])
def login():
    """Authenticate with username/password, return a bearer token."""
    data = request.get_json() or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401

    # Generate token on first login, reuse thereafter
    if not user.api_token:
        user.api_token = secrets.token_hex(32)
        db.session.commit()

    return jsonify({
        'token': user.api_token,
        'user_id': user.id,
        'display_name': user.display_name or user.username,
    })


# ── Saved playlists ─────────────────────────────────────────────────────────

@mobile_api_bp.route('/playlists')
@token_required
def playlists():
    """Return the user's saved playlists."""
    saved = SavedPlaylist.query.filter_by(
        user_id=g.api_user.id
    ).order_by(SavedPlaylist.created_at.desc()).all()

    return jsonify({'playlists': [{
        'id': sp.id,
        'title': sp.title,
        'youtubeId': sp.youtube_id,
        'playlistType': sp.playlist_type,
        'thumbnail': sp.thumbnail or '',
        'channel': sp.channel or '',
    } for sp in saved]})


@mobile_api_bp.route('/save-playlist', methods=['POST'])
@token_required
def save_playlist():
    """Save a playlist to the user's collection."""
    data = request.get_json() or {}
    youtube_id = data.get('id', '').strip()
    title = data.get('title', '').strip()
    if not youtube_id or not title:
        return jsonify({'error': 'Missing playlist info'}), 400

    existing = SavedPlaylist.query.filter_by(
        user_id=g.api_user.id, youtube_id=youtube_id
    ).first()
    if existing:
        return jsonify({'error': 'Already saved'}), 409

    sp = SavedPlaylist(
        user_id=g.api_user.id,
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


@mobile_api_bp.route('/delete-playlist/<int:playlist_id>', methods=['POST'])
@token_required
def delete_playlist(playlist_id):
    """Remove a saved playlist."""
    sp = SavedPlaylist.query.filter_by(
        id=playlist_id, user_id=g.api_user.id
    ).first()
    if not sp:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(sp)
    db.session.commit()
    return jsonify({'ok': True})


# ── Playlist tracks (YouTube API with yt-dlp fallback) ───────────────────────

@mobile_api_bp.route('/playlist-tracks')
@token_required
def playlist_tracks():
    """Fetch tracks from a YouTube playlist. Falls back to yt-dlp if no API key."""
    playlist_id = request.args.get('id', '').strip()
    if not playlist_id:
        return jsonify({'error': 'No playlist ID'}), 400

    yt_key = g.api_user.youtube_api_key
    if yt_key:
        from routes.resources import _fetch_playlist_tracks
        tracks = _fetch_playlist_tracks(yt_key, playlist_id)
    else:
        tracks = _fetch_playlist_tracks_ytdlp(playlist_id)

    return jsonify({'playlist_id': playlist_id, 'tracks': tracks})


def _fetch_playlist_tracks_ytdlp(playlist_id, max_tracks=50):
    """Fetch playlist tracks using yt-dlp (no API key needed)."""
    import yt_dlp

    tracks = []
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'socket_timeout': 15,
        'playlistend': max_tracks,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/playlist?list={playlist_id}"
            info = ydl.extract_info(url, download=False)

            for i, entry in enumerate(info.get('entries', []) or []):
                if not entry:
                    continue
                video_id = entry.get('id', '') or entry.get('url', '')
                tracks.append({
                    'videoId': video_id,
                    'title': entry.get('title', '') or 'Unknown',
                    'channel': entry.get('uploader', '') or entry.get('channel', '') or '',
                    'position': i,
                })
    except Exception:
        pass

    return tracks


# ── Stream URL extraction ────────────────────────────────────────────────────

@mobile_api_bp.route('/stream-url')
@token_required
def stream_url():
    """Extract a direct audio stream URL for a video using yt-dlp."""
    video_id = request.args.get('v', '').strip()
    if not video_id:
        return jsonify({'error': 'No video ID'}), 400

    result = _extract_stream_url(video_id)
    if not result:
        return jsonify({'error': 'unavailable'}), 404

    return jsonify(result)


def _extract_stream_url(video_id):
    """Use yt-dlp to get the best audio stream URL for a YouTube video."""
    import yt_dlp

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'skip_download': True,
        'socket_timeout': 15,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            url = f"https://www.youtube.com/watch?v={video_id}"
            info = ydl.extract_info(url, download=False)

            return {
                'url': info['url'],
                'duration': info.get('duration', 0),
                'title': info.get('title', ''),
                'channel': info.get('uploader', '') or info.get('channel', ''),
                'thumbnail': info.get('thumbnail', '')
                             or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            }
    except Exception:
        return None


# ── Music search (reuses existing logic) ─────────────────────────────────────

@mobile_api_bp.route('/music-search', methods=['POST'])
@token_required
def music_search():
    """AI-powered playlist search. Reuses resources.py logic."""
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'error': 'Please describe the music you want'}), 400

    ai_key, ai_provider = _get_effective_ai_key(g.api_user)
    if not ai_key:
        return jsonify({'error': 'No AI API key configured'}), 400

    from routes.resources import (
        _ai_music_suggestions, _resolve_with_youtube_api,
        _resolve_with_ytmusic, _enrich_and_sort_playlists,
        _dedupe_and_prefer_thumbnails,
    )

    suggestions = _ai_music_suggestions(ai_provider, ai_key, prompt)
    if not suggestions:
        return jsonify({'error': 'AI failed to generate suggestions'}), 502

    yt_key = g.api_user.youtube_api_key
    if yt_key:
        results = _resolve_with_youtube_api(yt_key, suggestions)
    else:
        results = _resolve_with_ytmusic(suggestions)

    if not results:
        return jsonify({'error': 'No playlists found'}), 404

    if yt_key:
        results = _enrich_and_sort_playlists(yt_key, results)

    results = _dedupe_and_prefer_thumbnails(results)

    saved_ids = {sp.youtube_id for sp in
                 SavedPlaylist.query.filter_by(user_id=g.api_user.id).all()}
    if saved_ids:
        results = [r for r in results if r.get('id', '') not in saved_ids]

    results = [r for r in results if r.get('type') != 'search'] or results
    results = results[:6]

    return jsonify({'search_query': prompt, 'results': results})


# ── Generate Mix (AI-curated individual tracks) ─────────────────────────────

@mobile_api_bp.route('/generate-mix', methods=['POST'])
@token_required
def generate_mix():
    """AI generates specific songs, yt-dlp resolves each to a video ID."""
    data = request.get_json() or {}
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return jsonify({'error': 'Please describe the music you want'}), 400

    ai_key, ai_provider = _get_effective_ai_key(g.api_user)
    if not ai_key:
        return jsonify({'error': 'No AI API key configured'}), 400

    # Step 1: AI generates specific songs
    songs = _ai_generate_song_list(ai_provider, ai_key, prompt)
    if not songs:
        return jsonify({'error': 'AI failed to generate song list'}), 502

    # Step 2: Resolve each song to a YouTube video ID using yt-dlp
    tracks = _resolve_songs_to_tracks(songs)
    if not tracks:
        return jsonify({'error': 'Could not find any of the suggested songs'}), 404

    return jsonify({'prompt': prompt, 'tracks': tracks})


def _ai_generate_song_list(provider, api_key, user_prompt):
    """Ask AI to return specific song titles and artists."""
    import json as _json

    system = (
        "You are a music recommendation assistant. The user describes what they want to listen to. "
        "Return a JSON array of 25 specific songs. Each item should be an object with:\n"
        '- "title": The exact song title\n'
        '- "artist": The artist or band name\n\n'
        "Return ONLY valid JSON array, no other text. "
        "Pick real, well-known songs that match the mood/genre described. "
        "Include a mix of popular hits and deeper cuts. Avoid duplicates."
    )
    messages = [{"role": "user", "content": user_prompt}]

    try:
        if provider == 'openai':
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": system}] + messages,
                max_tokens=2000,
            )
            text = resp.choices[0].message.content.strip()
        else:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
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


def _resolve_songs_to_tracks(songs):
    """Resolve a list of {title, artist} to YouTube video IDs using yt-dlp."""
    import yt_dlp
    from concurrent.futures import ThreadPoolExecutor

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'skip_download': True,
        'socket_timeout': 10,
    }

    def resolve(song):
        title = song.get('title', '')
        artist = song.get('artist', '')
        query = f"{artist} - {title}" if artist else title
        if not query:
            return None

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                entries = info.get('entries', [])
                if entries and entries[0]:
                    entry = entries[0]
                    video_id = entry.get('id', '') or entry.get('url', '')
                    return {
                        'videoId': video_id,
                        'title': entry.get('title', '') or f"{artist} - {title}",
                        'channel': entry.get('uploader', '') or entry.get('channel', '') or artist,
                        'thumbnail': f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else '',
                    }
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(resolve, songs))

    # Filter out failed resolutions and deduplicate by video ID
    tracks = []
    seen_ids = set()
    for r in results:
        if r and r['videoId'] and r['videoId'] not in seen_ids:
            seen_ids.add(r['videoId'])
            r['position'] = len(tracks)
            tracks.append(r)

    return tracks
