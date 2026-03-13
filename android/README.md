# Health Tracker Android App

A native Android wrapper for the Health Tracker web app. Connects to your self-hosted Flask server via WebView with full native integration.

## Features

- **WebView shell** — Full access to all web app features (food, training, AI chat, etc.)
- **Pull-to-refresh** — Swipe down to reload the page
- **Photo uploads** — Camera and gallery picker for progress photos
- **Server settings** — Configure your server URL from within the app
- **Offline handling** — Shows a friendly error screen when the server is unreachable
- **External links** — YouTube, Google, etc. open in the system browser
- **Back navigation** — Hardware back button goes to previous page

## Setup

### Prerequisites

- Android Studio (Arctic Fox or later)
- Android SDK 34
- Your Health Tracker server running and accessible from your phone

### Build

1. Open the `android/` directory in Android Studio
2. Update the server URL in `app/build.gradle`:
   ```groovy
   buildConfigField "String", "SERVER_URL", "\"http://YOUR_SERVER_IP:8080\""
   ```
3. Build and run on your device

### Server URL

The default URL points to `10.0.2.2:8080` (Android emulator's alias for localhost). For a real device:

- **Same network**: Use your server's local IP, e.g., `http://192.168.1.100:8080`
- **Remote**: Use your public domain, e.g., `https://health.yourdomain.com`

You can also change the server URL from within the app if it can't connect (tap "Server Settings" on the error screen).

### Signing for Release

To build a release APK:

1. Generate a keystore:
   ```bash
   keytool -genkey -v -keystore health-tracker.jks -keyalg RSA -keysize 2048 -validity 10000 -alias health-tracker
   ```

2. Add to `app/build.gradle`:
   ```groovy
   android {
       signingConfigs {
           release {
               storeFile file('health-tracker.jks')
               storePassword 'your-password'
               keyAlias 'health-tracker'
               keyPassword 'your-password'
           }
       }
       buildTypes {
           release {
               signingConfig signingConfigs.release
           }
       }
   }
   ```

3. Build: `./gradlew assembleRelease`

The APK will be at `app/build/outputs/apk/release/app-release.apk`.
