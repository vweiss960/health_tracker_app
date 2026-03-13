package com.healthtracker.app

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class ServerSettingsActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_server_settings)

        val urlInput = findViewById<EditText>(R.id.serverUrlInput)
        val saveBtn = findViewById<Button>(R.id.btnSave)

        val prefs = getSharedPreferences("health_tracker", MODE_PRIVATE)
        val currentUrl = prefs.getString("server_url", BuildConfig.SERVER_URL) ?: BuildConfig.SERVER_URL
        urlInput.setText(currentUrl)

        saveBtn.setOnClickListener {
            val url = urlInput.text.toString().trim().trimEnd('/')
            if (url.isEmpty()) {
                Toast.makeText(this, "URL cannot be empty", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (!url.startsWith("http://") && !url.startsWith("https://")) {
                Toast.makeText(this, "URL must start with http:// or https://", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            prefs.edit().putString("server_url", url).apply()
            Toast.makeText(this, "Server URL saved", Toast.LENGTH_SHORT).show()
            finish()
        }
    }
}
