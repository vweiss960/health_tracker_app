package com.healthtracker.app

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.MediaStore
import android.view.View
import android.webkit.*
import android.Manifest
import android.content.pm.PackageManager
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.FileProvider
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import java.io.File
import java.text.SimpleDateFormat
import java.util.*

class MainActivity : AppCompatActivity() {

    companion object {
        private const val CAMERA_PERMISSION_REQUEST = 1001
    }

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var errorView: LinearLayout
    private var fileUploadCallback: ValueCallback<Array<Uri>>? = null
    private var cameraPhotoUri: Uri? = null
    private var pendingPermissionRequest: PermissionRequest? = null

    private val fileChooserLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val data = result.data
            val results: Array<Uri>? = when {
                data == null || data.data == null -> cameraPhotoUri?.let { arrayOf(it) }
                else -> arrayOf(data.data!!)
            }
            fileUploadCallback?.onReceiveValue(results)
        } else {
            fileUploadCallback?.onReceiveValue(null)
        }
        fileUploadCallback = null
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        errorView = findViewById(R.id.errorView)

        swipeRefresh.setOnRefreshListener {
            webView.reload()
        }

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            allowFileAccess = true
            allowContentAccess = true
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            cacheMode = WebSettings.LOAD_DEFAULT
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
            useWideViewPort = true
            loadWithOverviewMode = true
            layoutAlgorithm = WebSettings.LayoutAlgorithm.TEXT_AUTOSIZING
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val url = request.url.toString()
                val serverUrl = getServerUrl()
                return if (url.startsWith(serverUrl) || url.startsWith("http://10.") ||
                    url.startsWith("http://192.168.") || url.startsWith("http://localhost")) {
                    false
                } else {
                    startActivity(Intent(Intent.ACTION_VIEW, request.url))
                    true
                }
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                swipeRefresh.isRefreshing = false
                errorView.visibility = View.GONE
                webView.visibility = View.VISIBLE
            }

            override fun onReceivedError(
                view: WebView?, request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                if (request?.isForMainFrame == true) {
                    swipeRefresh.isRefreshing = false
                    showError("Cannot connect to server")
                }
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest?) {
                runOnUiThread {
                    val grantedResources = request?.resources?.filter { resource ->
                        resource == PermissionRequest.RESOURCE_VIDEO_CAPTURE ||
                        resource == PermissionRequest.RESOURCE_AUDIO_CAPTURE
                    }?.toTypedArray()

                    if (!grantedResources.isNullOrEmpty()) {
                        if (ContextCompat.checkSelfPermission(this@MainActivity, Manifest.permission.CAMERA)
                            == PackageManager.PERMISSION_GRANTED) {
                            request?.grant(grantedResources)
                        } else {
                            pendingPermissionRequest = request
                            ActivityCompat.requestPermissions(
                                this@MainActivity,
                                arrayOf(Manifest.permission.CAMERA),
                                CAMERA_PERMISSION_REQUEST
                            )
                        }
                    } else {
                        request?.deny()
                    }
                }
            }

            override fun onShowFileChooser(
                webView: WebView?,
                callback: ValueCallback<Array<Uri>>?,
                params: FileChooserParams?
            ): Boolean {
                fileUploadCallback?.onReceiveValue(null)
                fileUploadCallback = callback

                val acceptTypes = params?.acceptTypes ?: arrayOf()
                val isImage = acceptTypes.any { it.startsWith("image") }

                val intents = mutableListOf<Intent>()

                if (isImage) {
                    val photoFile = createImageFile()
                    if (photoFile != null) {
                        cameraPhotoUri = FileProvider.getUriForFile(
                            this@MainActivity,
                            "${applicationContext.packageName}.fileprovider",
                            photoFile
                        )
                        val cameraIntent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
                            putExtra(MediaStore.EXTRA_OUTPUT, cameraPhotoUri)
                        }
                        intents.add(cameraIntent)
                    }
                }

                val pickerIntent = Intent(Intent.ACTION_GET_CONTENT).apply {
                    addCategory(Intent.CATEGORY_OPENABLE)
                    type = if (isImage) "image/*" else "*/*"
                }

                val chooserIntent = Intent.createChooser(pickerIntent, "Select file")
                if (intents.isNotEmpty()) {
                    chooserIntent.putExtra(Intent.EXTRA_INITIAL_INTENTS, intents.toTypedArray())
                }
                fileChooserLauncher.launch(chooserIntent)
                return true
            }
        }

        findViewById<Button>(R.id.btnRetry).setOnClickListener {
            loadApp()
        }
        findViewById<Button>(R.id.btnSettings).setOnClickListener {
            startActivity(Intent(this, ServerSettingsActivity::class.java))
        }

        loadApp()
    }

    private fun loadApp() {
        val serverUrl = getServerUrl()
        if (isNetworkAvailable()) {
            errorView.visibility = View.GONE
            webView.visibility = View.VISIBLE
            webView.loadUrl(serverUrl)
        } else {
            showError("No internet connection")
        }
    }

    private fun showError(message: String) {
        webView.visibility = View.GONE
        errorView.visibility = View.VISIBLE
        findViewById<TextView>(R.id.errorMessage).text = message
    }

    private fun getServerUrl(): String {
        val prefs = getSharedPreferences("health_tracker", MODE_PRIVATE)
        return prefs.getString("server_url", BuildConfig.SERVER_URL) ?: BuildConfig.SERVER_URL
    }

    private fun isNetworkAvailable(): Boolean {
        val cm = getSystemService(ConnectivityManager::class.java)
        val network = cm.activeNetwork ?: return false
        val caps = cm.getNetworkCapabilities(network) ?: return false
        return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }

    private fun createImageFile(): File? {
        return try {
            val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
            val dir = getExternalFilesDir(Environment.DIRECTORY_PICTURES)
            File.createTempFile("PHOTO_${timestamp}_", ".jpg", dir)
        } catch (e: Exception) {
            null
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == CAMERA_PERMISSION_REQUEST) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                pendingPermissionRequest?.grant(pendingPermissionRequest?.resources)
            } else {
                pendingPermissionRequest?.deny()
            }
            pendingPermissionRequest = null
        }
    }

    override fun onResume() {
        super.onResume()
        val currentUrl = webView.url
        val serverUrl = getServerUrl()
        if (currentUrl != null && !currentUrl.startsWith(serverUrl)) {
            loadApp()
        }
    }

    @Deprecated("Use OnBackPressedDispatcher")
    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }
}
