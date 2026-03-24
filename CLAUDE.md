# GritBoard Health Tracker App

## Build & Deploy

### Docker (Backend)
- The Flask backend runs in Docker: `docker compose up -d --build`
- Always rebuild the Docker container after backend changes (models, routes, templates, static files)

### Android Music APK
The main GritBoard app is a **PWA** (not an APK). Only the **Music app** is an Android APK.

When changes are made to Android music source files under `android/app/src/music/`:

1. Build the debug APK (debug is signed and installable; release is unsigned and won't install):
   ```bash
   cd android && ./gradlew assembleMusicDebug
   cp android/app/build/outputs/apk/music/debug/app-music-debug.apk static/android/GritBoard-Music.apk
   ```

2. **Rebuild the Docker container** so the updated APK is served:
   ```bash
   docker compose up -d --build
   ```

**Important:** Always rebuild the music APK AND the Docker container when Android code changes are made.

## Project Structure
- `app.py` — Flask app entry point, migrations
- `models.py` — SQLAlchemy models
- `routes/` — Route blueprints (resources, settings, mobile_api, etc.)
- `templates/` — Jinja2 HTML templates
- `static/` — Static assets including APKs in `static/android/`
- `android/` — Android app with two product flavors: `wrapper` (WebView) and `music` (native player)
