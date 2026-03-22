package com.healthtracker.app.music

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.healthtracker.app.R
import kotlinx.coroutines.launch

class MusicLoginActivity : AppCompatActivity() {

    private lateinit var apiClient: ApiClient
    private lateinit var etUsername: EditText
    private lateinit var etPassword: EditText
    private lateinit var btnLogin: Button
    private lateinit var tvError: TextView
    private lateinit var progressBar: ProgressBar

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_music_login)

        apiClient = ApiClient(applicationContext)

        if (apiClient.isLoggedIn) {
            startMusicHome()
            return
        }

        etUsername = findViewById(R.id.etUsername)
        etPassword = findViewById(R.id.etPassword)
        btnLogin = findViewById(R.id.btnLogin)
        tvError = findViewById(R.id.tvError)
        progressBar = findViewById(R.id.progressBar)

        btnLogin.setOnClickListener { doLogin() }
    }

    private fun doLogin() {
        val username = etUsername.text.toString().trim()
        val password = etPassword.text.toString()

        if (username.isEmpty() || password.isEmpty()) {
            tvError.text = "Username and password required"
            tvError.visibility = View.VISIBLE
            return
        }

        tvError.visibility = View.GONE
        progressBar.visibility = View.VISIBLE
        btnLogin.isEnabled = false

        lifecycleScope.launch {
            try {
                apiClient.login(username, password)
                startMusicHome()
            } catch (e: Exception) {
                tvError.text = e.message ?: "Login failed"
                tvError.visibility = View.VISIBLE
            } finally {
                progressBar.visibility = View.GONE
                btnLogin.isEnabled = true
            }
        }
    }

    private fun startMusicHome() {
        startActivity(Intent(this, MusicHomeActivity::class.java))
        finish()
    }
}
