package com.healthtracker.app.music

import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.SeekBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import coil.load
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

    private var mediaController: MediaController? = null
    private var userSeeking = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_now_playing)

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

        // Enable marquee on title
        tvTitle.isSelected = true

        // Back button
        findViewById<ImageButton>(R.id.btnBack).setOnClickListener {
            finish()
        }

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
                    val duration = mediaController?.duration ?: 0
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
                val duration = mediaController?.duration ?: 0
                if (duration > 0 && seekBar != null) {
                    val position = (seekBar.progress.toLong() * duration) / 1000
                    mediaController?.seekTo(position)
                }
                userSeeking = false
            }
        })

        connectToService()
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
        val ctrl = mediaController ?: return
        val metadata = ctrl.mediaMetadata

        tvTitle.text = metadata.title?.toString() ?: "Not Playing"
        tvArtist.text = metadata.artist?.toString() ?: ""

        btnPlayPause.setImageResource(
            if (ctrl.isPlaying) android.R.drawable.ic_media_pause
            else android.R.drawable.ic_media_play
        )

        // Try to load thumbnail from video ID in the current URI
        val uri = ctrl.currentMediaItem?.localConfiguration?.uri?.toString()
        // We don't have a direct thumbnail URL from the media item,
        // so use a placeholder background
        ivArt.setBackgroundColor(resources.getColor(R.color.music_card, null))
    }

    private fun startProgressUpdater() {
        lifecycleScope.launch {
            while (isActive) {
                val ctrl = mediaController
                if (ctrl != null && !userSeeking) {
                    val duration = ctrl.duration
                    val position = ctrl.currentPosition

                    if (duration > 0) {
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
