package com.healthtracker.app.music

import android.Manifest
import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.ImageButton
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.fragment.app.Fragment
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import coil.load
import com.google.android.material.bottomnavigation.BottomNavigationView
import com.google.gson.Gson
import com.healthtracker.app.R

class MusicHomeActivity : AppCompatActivity() {

    private lateinit var apiClient: ApiClient
    private lateinit var miniPlayer: LinearLayout
    private lateinit var tvMiniTitle: TextView
    private lateinit var tvMiniArtist: TextView
    private lateinit var ivMiniThumbnail: ImageView
    private lateinit var btnMiniPrev: ImageButton
    private lateinit var btnMiniPlayPause: ImageButton
    private lateinit var btnMiniNext: ImageButton
    private lateinit var bottomNav: BottomNavigationView

    private var mediaController: MediaController? = null

    private val myMusicFragment = MyMusicFragment()
    private val searchFragment = SearchFragment()
    private val generateMixFragment = GenerateMixFragment()
    private var activeFragment: Fragment = myMusicFragment

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_music_home)

        apiClient = ApiClient(applicationContext)

        if (!apiClient.isLoggedIn) {
            startActivity(Intent(this, MusicLoginActivity::class.java))
            finish()
            return
        }

        requestNotificationPermission()
        initViews()
        setupFragments()
        connectToService()
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1001
                )
            }
        }
    }

    private fun initViews() {
        miniPlayer = findViewById(R.id.miniPlayer)
        tvMiniTitle = findViewById(R.id.tvMiniTitle)
        tvMiniArtist = findViewById(R.id.tvMiniArtist)
        ivMiniThumbnail = findViewById(R.id.ivMiniThumbnail)
        btnMiniPrev = findViewById(R.id.btnMiniPrev)
        btnMiniPlayPause = findViewById(R.id.btnMiniPlayPause)
        btnMiniNext = findViewById(R.id.btnMiniNext)
        bottomNav = findViewById(R.id.bottomNav)

        // Mini player controls
        btnMiniPrev.setOnClickListener {
            val intent = Intent(this, MusicPlaybackService::class.java)
            intent.action = MusicPlaybackService.ACTION_SKIP_PREV
            startService(intent)
        }
        btnMiniPlayPause.setOnClickListener {
            val intent = Intent(this, MusicPlaybackService::class.java)
            intent.action = MusicPlaybackService.ACTION_PLAY_PAUSE
            startService(intent)
        }
        btnMiniNext.setOnClickListener {
            val intent = Intent(this, MusicPlaybackService::class.java)
            intent.action = MusicPlaybackService.ACTION_SKIP_NEXT
            startService(intent)
        }

        // Tap mini player to open full-screen now playing
        miniPlayer.setOnClickListener {
            startActivity(Intent(this, NowPlayingActivity::class.java))
        }

        // Logout button
        findViewById<ImageButton>(R.id.btnLogout).setOnClickListener {
            apiClient.logout()
            startActivity(Intent(this, MusicLoginActivity::class.java))
            finish()
        }

        // Bottom navigation
        bottomNav.setOnItemSelectedListener { item ->
            when (item.itemId) {
                R.id.nav_my_music -> switchFragment(myMusicFragment)
                R.id.nav_search -> switchFragment(searchFragment)
                R.id.nav_generate -> switchFragment(generateMixFragment)
            }
            true
        }
    }

    private fun setupFragments() {
        supportFragmentManager.beginTransaction()
            .add(R.id.fragmentContainer, generateMixFragment, "generate").hide(generateMixFragment)
            .add(R.id.fragmentContainer, searchFragment, "search").hide(searchFragment)
            .add(R.id.fragmentContainer, myMusicFragment, "mymusic")
            .commit()
    }

    private fun switchFragment(fragment: Fragment) {
        supportFragmentManager.beginTransaction()
            .hide(activeFragment)
            .show(fragment)
            .commit()
        activeFragment = fragment
    }

    fun startPlayback(tracks: List<Track>) {
        val json = Gson().toJson(tracks)
        val intent = Intent(this, MusicPlaybackService::class.java).apply {
            action = MusicPlaybackService.ACTION_LOAD_TRACKS
            putExtra("tracks_json", json)
        }
        startForegroundService(intent)

        miniPlayer.visibility = View.VISIBLE
        tvMiniTitle.text = tracks.firstOrNull()?.title ?: "Playing..."
        tvMiniArtist.text = tracks.firstOrNull()?.channel ?: ""

        val thumbnail = tracks.firstOrNull()?.thumbnail
        if (!thumbnail.isNullOrEmpty()) {
            ivMiniThumbnail.load(thumbnail) { crossfade(true) }
        }

        // Reconnect to get media session updates
        connectToService()
    }

    private fun connectToService() {
        try {
            val sessionToken = SessionToken(this, ComponentName(this, MusicPlaybackService::class.java))
            val controllerFuture = MediaController.Builder(this, sessionToken).buildAsync()
            controllerFuture.addListener({
                try {
                    mediaController = controllerFuture.get()
                    mediaController?.addListener(object : androidx.media3.common.Player.Listener {
                        override fun onMediaMetadataChanged(metadata: androidx.media3.common.MediaMetadata) {
                            val title = metadata.title?.toString()
                            val artist = metadata.artist?.toString()
                            if (title != null) tvMiniTitle.text = title
                            if (artist != null) tvMiniArtist.text = artist
                        }

                        override fun onIsPlayingChanged(isPlaying: Boolean) {
                            btnMiniPlayPause.setImageResource(
                                if (isPlaying) android.R.drawable.ic_media_pause
                                else android.R.drawable.ic_media_play
                            )
                        }
                    })

                    if (mediaController?.isPlaying == true || mediaController?.playbackState == androidx.media3.common.Player.STATE_BUFFERING) {
                        miniPlayer.visibility = View.VISIBLE
                        val title = mediaController?.mediaMetadata?.title?.toString()
                        val artist = mediaController?.mediaMetadata?.artist?.toString()
                        if (title != null) tvMiniTitle.text = title
                        if (artist != null) tvMiniArtist.text = artist
                    }
                } catch (_: Exception) { }
            }, mainExecutor)
        } catch (_: Exception) { }
    }

    override fun onDestroy() {
        // Stop music when the app is closed
        val intent = Intent(this, MusicPlaybackService::class.java)
        intent.action = MusicPlaybackService.ACTION_STOP
        startService(intent)
        mediaController?.release()
        super.onDestroy()
    }
}
