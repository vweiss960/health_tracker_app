"""
Background service that generates daily motivational content by searching YouTube
for real videos. Uses yt-dlp (no API key needed).
Zero AI tokens consumed. Runs once per day, pre-generating content for all 7 categories.
"""
import json
import random
import threading
import time
from datetime import date
from urllib.parse import quote_plus


# Pool of search queries per category — rotated daily for variety
SEARCH_QUERIES = {
    'general': [
        'fitness motivation workout compilation',
        'gym motivation never give up',
        'discipline fitness mindset',
        'workout motivation speech',
        'fitness journey transformation motivation',
        'morning workout motivation energy',
        'push yourself fitness inspiration',
        'consistency is key fitness',
        'no excuses workout motivation',
        'grind mentality fitness',
        'fitness motivation cinematic 4K',
        'gym motivation short film',
        'fitness cinematic edit motivation',
    ],
    'weight_loss': [
        'weight loss transformation story',
        'fat loss tips that actually work',
        'weight loss journey before and after',
        'how I lost weight and kept it off',
        'calorie deficit weight loss explained',
        'weight loss motivation real results',
        'body transformation fat to fit',
        'sustainable weight loss tips',
        'weight loss mistakes to avoid',
        'walking for weight loss results',
        'weight loss transformation cinematic',
        'fat to fit documentary short film',
    ],
    'muscle_building': [
        'muscle building tips for beginners',
        'hypertrophy training science',
        'Jeff Nippard muscle building',
        'Renaissance Periodization training',
        'natural bodybuilding motivation',
        'progressive overload explained',
        'muscle gain transformation',
        'compound exercises for muscle growth',
        'AthleanX build muscle',
        'strength training motivation',
        'bodybuilding motivation cinematic 4K',
        'aesthetic bodybuilding short film',
    ],
    'nutrition': [
        'healthy meal prep for the week',
        'high protein meal ideas',
        'nutrition tips for muscle building',
        'healthy eating habits that changed my life',
        'meal prep for weight loss',
        'macros explained simple',
        'healthy grocery haul',
        'anti inflammatory foods diet',
        'nutrition science explained',
        'healthy recipes high protein easy',
        'food documentary healthy eating',
        'nutrition science cinematic',
    ],
    'mindset': [
        'mental toughness fitness',
        'David Goggins motivation',
        'discipline vs motivation',
        'overcoming fitness plateau',
        'growth mindset workout',
        'how to stay consistent gym',
        'building discipline habits',
        'fitness mindset shift',
        'never quit motivation speech',
        'resilience training mindset',
        'discipline motivation cinematic speech',
        'mental strength documentary short film',
    ],
    'success_stories': [
        'body transformation 1 year',
        'fitness transformation story real',
        'before and after weight loss journey',
        'skinny to muscular transformation',
        'obese to fit transformation',
        'real people fitness transformation',
        'incredible body transformation',
        'fitness journey documentary',
        'life changing fitness story',
        '100 pound weight loss journey',
        'fitness transformation mini documentary',
        'body transformation cinematic story',
    ],
    'cinematic': [
        'fitness cinematic short film',
        'gym motivation cinematic edit',
        'fitness cinematic 4K visual',
        'workout cinematic montage',
        'bodybuilding cinematic film',
        'fitness motivation no talking cinematic',
        'gym aesthetic cinematic edit',
        'fitness short film indie',
        'health motivation visual film',
        'running cinematic short film',
        'training montage cinematic no speech',
        'fitness lifestyle cinematic visual',
        'gym cinematic b roll edit',
        'indie fitness film motivation',
        'athletic cinematic visual storytelling',
    ],
}

# Article search queries per category (Google search links)
ARTICLE_QUERIES = {
    'general': [
        'best fitness motivation tips',
        'how to stay motivated working out',
        'fitness discipline strategies',
    ],
    'weight_loss': [
        'evidence based weight loss strategies',
        'sustainable fat loss guide',
        'weight loss science explained',
    ],
    'muscle_building': [
        'science of muscle hypertrophy',
        'best muscle building program beginners',
        'progressive overload training guide',
    ],
    'nutrition': [
        'healthy eating guide for fitness',
        'meal planning for fitness goals',
        'sports nutrition fundamentals',
    ],
    'mindset': [
        'mental toughness in fitness',
        'building discipline habits research',
        'psychology of fitness motivation',
    ],
    'success_stories': [
        'incredible fitness transformation stories',
        'real weight loss success stories',
        'inspiring body transformation journeys',
    ],
    'cinematic': [
        'cinematic fitness short films',
        'indie fitness motivation films',
        'visual fitness motivation no talking',
    ],
}


def _search_youtube_videos(queries, max_per_query=2):
    """Search regular YouTube for videos using yt-dlp. Returns list of result dicts."""
    results = []
    seen_ids = set()

    for query in queries:
        try:
            import yt_dlp
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'skip_download': True,
                'socket_timeout': 15,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_url = f"ytsearch{max_per_query + 2}:{query}"
                info = ydl.extract_info(search_url, download=False)
                search_results = info.get('entries', []) if info else []

            count = 0
            for item in search_results:
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
                count += 1
        except Exception as e:
            print(f"[DailyMotivation] YouTube search error for '{query}': {e}")
            continue

        # Small delay between searches
        time.sleep(0.5)

    return results


def _generate_content_for_category(category):
    """Generate real content for a category from YouTube."""
    # Pick random subset of video queries for variety
    video_queries = SEARCH_QUERIES.get(category, SEARCH_QUERIES['general'])
    selected_video_queries = random.sample(video_queries, min(5, len(video_queries)))

    # Search YouTube for real videos
    videos = _search_youtube_videos(selected_video_queries, max_per_query=2)

    if category == 'cinematic':
        # Cinematic is purely visual — no articles
        results = videos[:8]
    else:
        # Add article links from predefined queries
        article_queries = ARTICLE_QUERIES.get(category, ARTICLE_QUERIES['general'])
        selected_article_queries = random.sample(article_queries, min(2, len(article_queries)))

        articles = []
        for query in selected_article_queries:
            articles.append({
                'type': 'article',
                'title': query.title(),
                'description': 'Search for articles and guides on this topic',
                'url': f'https://www.google.com/search?q={quote_plus(query)}',
                'thumbnail': '',
                'source_hint': 'Web Search',
            })

        # Combine: YouTube videos + articles
        results = videos[:6] + articles[:2]
        results = results[:8]

    # Shuffle for variety
    random.shuffle(results)

    return results if results else None


def generate_daily_content(app):
    """Generate motivational content for all categories for today."""
    with app.app_context():
        from models import db, DailyMotivation

        today = date.today()

        # Check if we already generated for today
        existing = DailyMotivation.query.filter_by(date=today).first()
        if existing:
            print(f"[DailyMotivation] Content already generated for {today}. Skipping.")
            return

        print(f"[DailyMotivation] Generating content for {today}...")

        for category in SEARCH_QUERIES:
            results = _generate_content_for_category(category)
            if results:
                entry = DailyMotivation(
                    date=today,
                    category=category,
                    content_json=json.dumps(results),
                )
                db.session.add(entry)
                db.session.commit()
                print(f"[DailyMotivation]   {category}: OK ({len(results)} items)")
            else:
                print(f"[DailyMotivation]   {category}: FAILED")

            # Delay between categories
            time.sleep(1)

        print(f"[DailyMotivation] Done generating for {today}.")


def start_daily_scheduler(app):
    """Start a background thread that checks once per hour if daily content needs generating."""
    def _scheduler_loop():
        while True:
            try:
                generate_daily_content(app)
            except Exception as e:
                print(f"[DailyMotivation] Scheduler error: {e}")
            # Check every hour
            time.sleep(3600)

    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    print("[DailyMotivation] Scheduler started (checks hourly).")
