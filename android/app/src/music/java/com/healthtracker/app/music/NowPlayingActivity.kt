package com.healthtracker.app.music

import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.C
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import com.healthtracker.app.R
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

class NowPlayingActivity : AppCompatActivity() {

    private lateinit var ivArt: ImageView
    private lateinit var tvTitle: TextView
    private lateinit var tvArtist: TextView
    private lateinit var seekBar: SeekBar
    private lateinit var tvElapsed: TextView
    private lateinit var tvRemaining: TextView
    private lateinit var btnPlayPause: ImageButton
    private lateinit var btnNext: ImageButton
    private lateinit var btnPrev: ImageButton
    private lateinit var btnShuffle: ImageButton
    private lateinit var btnFavorite: ImageButton
    private lateinit var apiClient: ApiClient

    private lateinit var nowPlayingPrefs: SharedPreferences
    private var mediaController: MediaController? = null
    private var userSeeking = false
    private var isFavorited = false
    private var currentVideoId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_now_playing)

        apiClient = ApiClient(applicationContext)
        nowPlayingPrefs = getSharedPreferences(
            MusicPlaybackService.NOW_PLAYING_PREFS, Context.MODE_PRIVATE
        )

        ivArt = findViewById(R.id.ivArt)
        tvTitle = findViewById(R.id.tvTitle)
        tvArtist = findViewById(R.id.tvArtist)
        seekBar = findViewById(R.id.seekBar)
        tvElapsed = findViewById(R.id.tvElapsed)
        tvRemaining = findViewById(R.id.tvRemaining)
        btnPlayPause = findViewById(R.id.btnPlayPause)
        btnNext = findViewById(R.id.btnNext)
        btnPrev = findViewById(R.id.btnPrev)
        btnShuffle = findViewById(R.id.btnShuffle)
        btnFavorite = findViewById(R.id.btnFavorite)

        // Enable marquee on title
        tvTitle.isSelected = true

        // Back button
        findViewById<ImageButton>(R.id.btnBack).setOnClickListener {
            finish()
        }

        // Favorite button
        btnFavorite.setOnClickListener { toggleFavorite() }

        // Transport controls
        btnPlayPause.setOnClickListener {
            val intent = Intent(this, MusicPlaybackService::class.java)
            intent.action = MusicPlaybackService.ACTION_PLAY_PAUSE
            startService(intent)
        }

        btnNext.setOnClickListener {
            val intent = Intent(this, MusicPlaybackService::class.java)
            intent.action = MusicPlaybackService.ACTION_SKIP_NEXT
            startService(intent)
        }

        btnPrev.setOnClickListener {
            val intent = Intent(this, MusicPlaybackService::class.java)
            intent.action = MusicPlaybackService.ACTION_SKIP_PREV
            startService(intent)
        }

        btnShuffle.setOnClickListener {
            val intent = Intent(this, MusicPlaybackService::class.java)
            intent.action = MusicPlaybackService.ACTION_TOGGLE_SHUFFLE
            startService(intent)
        }

        // Seek bar interaction
        seekBar.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) {
                    val duration = getEffectiveDuration()
                    if (duration > 0) {
                        val position = (progress.toLong() * duration) / 1000
                        tvElapsed.text = formatTime(position)
                    }
                }
            }

            override fun onStartTrackingTouch(seekBar: SeekBar?) {
                userSeeking = true
            }

            override fun onStopTrackingTouch(seekBar: SeekBar?) {
                val duration = getEffectiveDuration()
                if (duration > 0 && seekBar != null) {
                    val position = (seekBar.progress.toLong() * duration) / 1000
                    mediaController?.seekTo(position)
                }
                userSeeking = false
            }
        })

        // Load track info from SharedPreferences immediately (no need to wait for MediaController)
        updateUI()

        connectToService()
    }

    private fun toggleFavorite() {
        val title = tvTitle.text?.toString() ?: return
        val artist = tvArtist.text?.toString() ?: ""
        val videoId = currentVideoId
            ?: nowPlayingPrefs.getString("video_id", null)
            ?: return
        currentVideoId = videoId

        lifecycleScope.launch {
            try {
                if (isFavorited) {
                    apiClient.unfavoriteTrack(videoId)
                    isFavorited = false
                } else {
                    val track = Track(
                        videoId = videoId,
                        title = title,
                        channel = artist,
                        position = 0,
                        thumbnail = "https://i.ytimg.com/vi/$videoId/hqdefault.jpg",
                    )
                    apiClient.favoriteTrack(track)
                    isFavorited = true
                }
                updateFavoriteIcon()
            } catch (_: Exception) { }
        }
    }

    private fun updateFavoriteIcon() {
        if (isFavorited) {
            btnFavorite.setImageResource(android.R.drawable.btn_star_big_on)
            btnFavorite.imageTintList = android.content.res.ColorStateList.valueOf(
                resources.getColor(R.color.music_accent, null)
            )
        } else {
            btnFavorite.setImageResource(android.R.drawable.btn_star_big_off)
            btnFavorite.imageTintList = android.content.res.ColorStateList.valueOf(
                resources.getColor(R.color.music_text_secondary, null)
            )
        }
    }

    private fun checkFavoriteStatus(videoId: String) {
        currentVideoId = videoId
        lifecycleScope.launch {
            try {
                isFavorited = apiClient.isFavorited(videoId)
                updateFavoriteIcon()
            } catch (_: Exception) { }
        }
    }

    private fun connectToService() {
        try {
            val sessionToken = SessionToken(this, ComponentName(this, MusicPlaybackService::class.java))
            val controllerFuture = MediaController.Builder(this, sessionToken).buildAsync()
            controllerFuture.addListener({
                try {
                    mediaController = controllerFuture.get()
                    updateUI()
                    startProgressUpdater()

                    mediaController?.addListener(object : Player.Listener {
                        override fun onMediaMetadataChanged(metadata: MediaMetadata) {
                            updateUI()
                        }

                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            btnPlayPause.setImageResource(
                                if (isPlaying) android.R.drawable.ic_media_pause
                                else android.R.drawable.ic_media_play
                            )
                        }

                        override fun onPlaybackStateChanged(playbackState: Int) {
                            updateUI()
                        }
                    })
                } catch (_: Exception) { }
            }, mainExecutor)
        } catch (_: Exception) { }
    }

    private fun updateUI() {
        // Read track info from SharedPreferences (written by MusicPlaybackService)
        val title = nowPlayingPrefs.getString("title", null)
        val artist = nowPlayingPrefs.getString("artist", null)
        val videoId = nowPlayingPrefs.getString("video_id", null)

        tvTitle.text = title ?: "Not Playing"
        tvArtist.text = artist ?: ""

        // Set default music note image
        ivArt.setImageResource(R.drawable.ic_music_note)
        ivArt.scaleType = ImageView.ScaleType.CENTER
        ivArt.setBackgroundColor(resources.getColor(R.color.music_card, null))

        // Update play/pause button from MediaController if available
        val ctrl = mediaController
        if (ctrl != null) {
            btnPlayPause.setImageResource(
                if (ctrl.isPlaying) android.R.drawable.ic_media_pause
                else android.R.drawable.ic_media_play
            )
        }

        // Check favorite status when track changes
        if (!videoId.isNullOrEmpty() && videoId != currentVideoId) {
            checkFavoriteStatus(videoId)
        }
    }

    private fun startProgressUpdater() {
        lifecycleScope.launch {
            var lastVideoId: String? = null
            while (isActive) {
                // Check for track changes via SharedPreferences
                val prefsVideoId = nowPlayingPrefs.getString("video_id", null)
                if (prefsVideoId != null && prefsVideoId != lastVideoId) {
                    lastVideoId = prefsVideoId
                    updateUI()
                }

                val ctrl = mediaController
                if (ctrl != null && !userSeeking) {
                    var duration = ctrl.duration
                    val position = ctrl.currentPosition

                    // Fall back to duration from SharedPreferences if MediaController doesn't have it
                    if (duration <= 0 || duration == C.TIME_UNSET) {
                        duration = nowPlayingPrefs.getLong("duration_ms", 0)
                    }

                    if (duration > 0 && duration != C.TIME_UNSET) {
                        val progress = ((position * 1000) / duration).toInt()
                        seekBar.progress = progress
                        tvElapsed.text = formatTime(position)
                        tvRemaining.text = formatTime(duration - position)
                    }
                }
                delay(500)
            }
        }
    }

    private fun getEffectiveDuration(): Long {
        val ctrlDuration = mediaController?.duration ?: 0
        if (ctrlDuration > 0 && ctrlDuration != C.TIME_UNSET) return ctrlDuration
        return nowPlayingPrefs.getLong("duration_ms", 0)
    }

    private fun formatTime(ms: Long): String {
        val totalSeconds = ms / 1000
        val minutes = totalSeconds / 60
        val seconds = totalSeconds % 60
        return "%d:%02d".format(minutes, seconds)
    }

    override fun onDestroy() {
        mediaController?.release()
        super.onDestroy()
    }
}
