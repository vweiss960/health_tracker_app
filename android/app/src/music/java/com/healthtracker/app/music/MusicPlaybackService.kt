package com.healthtracker.app.music

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.os.Build
import android.util.Log
import androidx.annotation.OptIn
import androidx.core.app.NotificationCompat
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import kotlinx.coroutines.*

@OptIn(UnstableApi::class)
class MusicPlaybackService : MediaSessionService() {

    companion object {
        const val CHANNEL_ID = "music_playback"
        const val NOTIFICATION_ID = 1001
        const val TAG = "MusicPlayback"

        const val ACTION_LOAD_TRACKS = "com.healthtracker.app.music.LOAD_TRACKS"
        const val ACTION_TOGGLE_SHUFFLE = "com.healthtracker.app.music.TOGGLE_SHUFFLE"
        const val ACTION_SKIP_NEXT = "com.healthtracker.app.music.SKIP_NEXT"
        const val ACTION_SKIP_PREV = "com.healthtracker.app.music.SKIP_PREV"
        const val ACTION_PLAY_PAUSE = "com.healthtracker.app.music.PLAY_PAUSE"
        const val ACTION_STOP = "com.healthtracker.app.music.STOP"

        const val MAX_CONSECUTIVE_SKIPS = 5
    }

    private var mediaSession: MediaSession? = null
    private lateinit var player: ExoPlayer
    private lateinit var apiClient: ApiClient
    private val queueManager = QueueManager()

    private val serviceScope = CoroutineScope(Dispatchers.Main + SupervisorJob())
    private var prefetchJob: Job? = null
    private var consecutiveErrors = 0
    private var currentStreamUrl: String? = null

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()

        apiClient = ApiClient(applicationContext)

        player = ExoPlayer.Builder(this)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setContentType(C.AUDIO_CONTENT_TYPE_MUSIC)
                    .setUsage(C.USAGE_MEDIA)
                    .build(),
                true
            )
            .setHandleAudioBecomingNoisy(true)
            .build()

        player.addListener(object : Player.Listener {
            override fun onPlaybackStateChanged(playbackState: Int) {
                if (playbackState == Player.STATE_ENDED) {
                    consecutiveErrors = 0
                    playNext()
                }
            }

            override fun onPlayerError(error: PlaybackException) {
                Log.w(TAG, "Playback error: ${error.message}")
                consecutiveErrors++
                if (consecutiveErrors <= MAX_CONSECUTIVE_SKIPS) {
                    playNext()
                } else {
                    Log.e(TAG, "Too many consecutive errors, stopping")
                    player.stop()
                }
            }
        })

        val sessionIntent = PendingIntent.getActivity(
            this, 0,
            Intent(this, NowPlayingActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        mediaSession = MediaSession.Builder(this, player)
            .setSessionActivity(sessionIntent)
            .build()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        ensureForeground()

        when (intent?.action) {
            ACTION_LOAD_TRACKS -> {
                val tracksJson = intent.getStringExtra("tracks_json")
                if (tracksJson != null) {
                    loadTracksFromJson(tracksJson)
                }
            }
            ACTION_TOGGLE_SHUFFLE -> {
                queueManager.toggleShuffle()
            }
            ACTION_SKIP_NEXT -> {
                playNext()
            }
            ACTION_SKIP_PREV -> {
                playPrevious()
            }
            ACTION_PLAY_PAUSE -> {
                if (player.isPlaying) player.pause() else player.play()
            }
            ACTION_STOP -> {
                player.stop()
                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
            }
        }
        return super.onStartCommand(intent, flags, startId)
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? {
        return mediaSession
    }

    override fun onTaskRemoved(rootIntent: Intent?) {
        // Stop playback when user swipes the app away
        player.stop()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
        super.onTaskRemoved(rootIntent)
    }

    override fun onDestroy() {
        serviceScope.cancel()
        mediaSession?.run {
            player.release()
            release()
        }
        mediaSession = null
        super.onDestroy()
    }

    private fun ensureForeground() {
        try {
            val contentIntent = PendingIntent.getActivity(
                this, 0,
                Intent(this, NowPlayingActivity::class.java),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )

            val notification = NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("GritBoard Music")
                .setContentText("Loading...")
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentIntent(contentIntent)
                .setOngoing(true)
                .setSilent(true)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .build()

            startForeground(NOTIFICATION_ID, notification)
        } catch (e: Exception) {
            Log.w(TAG, "Could not start foreground: ${e.message}")
        }
    }

    private fun loadTracksFromJson(json: String) {
        try {
            val tracks = com.google.gson.Gson().fromJson(
                json, Array<Track>::class.java
            ).toList()

            queueManager.loadTracks(tracks)
            consecutiveErrors = 0
            playCurrentTrack()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse tracks: ${e.message}")
        }
    }

    private fun playCurrentTrack() {
        val track = queueManager.currentTrack ?: return

        serviceScope.launch {
            try {
                val stream = apiClient.getStreamUrl(track.videoId)
                if (stream != null) {
                    currentStreamUrl = stream.url
                    consecutiveErrors = 0

                    val metadata = MediaMetadata.Builder()
                        .setTitle(stream.title.ifEmpty { track.title })
                        .setArtist(stream.channel.ifEmpty { track.channel })
                        .build()

                    val mediaItem = MediaItem.Builder()
                        .setUri(stream.url)
                        .setMediaMetadata(metadata)
                        .build()

                    player.setMediaItem(mediaItem)
                    player.prepare()
                    player.play()

                    schedulePrefetch()
                } else {
                    Log.w(TAG, "No stream for ${track.videoId}, skipping")
                    consecutiveErrors++
                    if (consecutiveErrors <= MAX_CONSECUTIVE_SKIPS) {
                        playNext()
                    }
                }
            } catch (e: Exception) {
                Log.w(TAG, "Error fetching stream: ${e.message}")
                consecutiveErrors++
                if (consecutiveErrors <= MAX_CONSECUTIVE_SKIPS) {
                    playNext()
                }
            }
        }
    }

    private fun playNext() {
        val track = queueManager.next()
        if (track != null) {
            playCurrentTrack()
        }
    }

    private fun playPrevious() {
        val track = queueManager.previous()
        if (track != null) {
            playCurrentTrack()
        }
    }

    private fun schedulePrefetch() {
        prefetchJob?.cancel()
        prefetchJob = serviceScope.launch {
            while (isActive) {
                delay(5000)
                val duration = player.duration
                val position = player.currentPosition
                if (duration > 0 && position > 0) {
                    val progress = position.toFloat() / duration.toFloat()
                    if (progress >= 0.8f) {
                        val nextTrack = peekNextTrack()
                        if (nextTrack != null) {
                            try {
                                apiClient.getStreamUrl(nextTrack.videoId)
                            } catch (_: Exception) { }
                        }
                        break
                    }
                }
            }
        }
    }

    private fun peekNextTrack(): Track? {
        val nextPos = queueManager.currentIndex + 1
        if (nextPos >= queueManager.trackCount) return null
        return queueManager.getAllTracks().getOrNull(nextPos)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Music Playback",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Controls for music playback"
                setShowBadge(false)
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }
}
