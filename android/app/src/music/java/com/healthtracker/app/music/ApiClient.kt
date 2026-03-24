package com.healthtracker.app.music

import android.content.Context
import com.google.gson.Gson
import com.google.gson.JsonParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

class ApiClient(private val context: Context) {

    private val gson = Gson()
    private val jsonType = "application/json; charset=utf-8".toMediaType()

    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .build()

    private val prefs get() = context.getSharedPreferences("health_tracker", Context.MODE_PRIVATE)

    var token: String?
        get() = prefs.getString("music_api_token", null)
        set(value) = prefs.edit().putString("music_api_token", value).apply()

    val serverUrl: String
        get() = prefs.getString("server_url", null)
            ?: com.healthtracker.app.BuildConfig.SERVER_URL

    val isLoggedIn: Boolean get() = token != null

    private fun apiUrl(path: String) = "$serverUrl/mobile-api$path"

    private fun authRequest(url: String): Request.Builder =
        Request.Builder().url(url).header("Authorization", "Bearer ${token ?: ""}")

    suspend fun login(username: String, password: String): AuthResult = withContext(Dispatchers.IO) {
        val body = gson.toJson(mapOf("username" to username, "password" to password))
            .toRequestBody(jsonType)

        val request = Request.Builder()
            .url(apiUrl("/login"))
            .post(body)
            .build()

        val response = client.newCall(request).execute()
        val json = response.body?.string() ?: throw Exception("Empty response")

        if (!response.isSuccessful) {
            val error = try {
                JsonParser.parseString(json).asJsonObject.get("error")?.asString
            } catch (e: Exception) { null }
            throw Exception(error ?: "Login failed (${response.code})")
        }

        val obj = JsonParser.parseString(json).asJsonObject
        val result = AuthResult(
            token = obj.get("token").asString,
            userId = obj.get("user_id").asInt,
            displayName = obj.get("display_name").asString,
        )
        token = result.token
        result
    }

    fun logout() {
        token = null
    }

    suspend fun getPlaylists(): List<Playlist> = withContext(Dispatchers.IO) {
        val request = authRequest(apiUrl("/playlists")).build()
        val response = client.newCall(request).execute()
        checkAuth(response)
        val json = response.body?.string() ?: return@withContext emptyList()
        val obj = JsonParser.parseString(json).asJsonObject
        val arr = obj.getAsJsonArray("playlists")

        arr.map { el ->
            val o = el.asJsonObject
            Playlist(
                id = o.get("id").asInt,
                title = o.get("title").asString,
                youtubeId = o.get("youtubeId").asString,
                playlistType = o.get("playlistType")?.asString ?: "playlist",
                thumbnail = o.get("thumbnail")?.asString ?: "",
                channel = o.get("channel")?.asString ?: "",
            )
        }
    }

    suspend fun getPlaylistTracks(youtubeId: String): List<Track> = withContext(Dispatchers.IO) {
        val request = authRequest(apiUrl("/playlist-tracks?id=$youtubeId")).build()
        val response = client.newCall(request).execute()
        checkAuth(response)
        val json = response.body?.string() ?: return@withContext emptyList()
        val obj = JsonParser.parseString(json).asJsonObject
        val arr = obj.getAsJsonArray("tracks")

        arr.map { el ->
            val o = el.asJsonObject
            Track(
                videoId = o.get("videoId").asString,
                title = o.get("title").asString,
                channel = o.get("channel")?.asString ?: "",
                position = o.get("position")?.asInt ?: 0,
                thumbnail = "https://i.ytimg.com/vi/${o.get("videoId").asString}/hqdefault.jpg",
            )
        }
    }

    suspend fun getStreamUrl(videoId: String): StreamResult? = withContext(Dispatchers.IO) {
        val request = authRequest(apiUrl("/stream-url?v=$videoId")).build()
        val response = client.newCall(request).execute()
        checkAuth(response)
        if (!response.isSuccessful) return@withContext null
        val json = response.body?.string() ?: return@withContext null
        val o = JsonParser.parseString(json).asJsonObject

        StreamResult(
            url = o.get("url").asString,
            duration = o.get("duration")?.asInt ?: 0,
            title = o.get("title")?.asString ?: "",
            channel = o.get("channel")?.asString ?: "",
            thumbnail = o.get("thumbnail")?.asString ?: "",
        )
    }

    suspend fun searchMusic(prompt: String): List<PlaylistResult> = withContext(Dispatchers.IO) {
        val body = gson.toJson(mapOf("prompt" to prompt)).toRequestBody(jsonType)
        val request = authRequest(apiUrl("/music-search")).post(body).build()
        val response = client.newCall(request).execute()
        checkAuth(response)
        if (!response.isSuccessful) return@withContext emptyList()
        val json = response.body?.string() ?: return@withContext emptyList()
        val obj = JsonParser.parseString(json).asJsonObject
        val arr = obj.getAsJsonArray("results") ?: return@withContext emptyList()

        arr.map { el ->
            val o = el.asJsonObject
            PlaylistResult(
                type = o.get("type")?.asString ?: "playlist",
                id = o.get("id")?.asString ?: "",
                title = o.get("title")?.asString ?: "",
                channel = o.get("channel")?.asString ?: "",
                thumbnail = o.get("thumbnail")?.asString ?: "",
                trackCount = o.get("track_count")?.asInt ?: 0,
                description = o.get("description")?.asString ?: "",
                query = o.get("query")?.asString ?: "",
            )
        }
    }

    suspend fun generateMix(prompt: String): List<Track> = withContext(Dispatchers.IO) {
        val body = gson.toJson(mapOf("prompt" to prompt)).toRequestBody(jsonType)
        val request = authRequest(apiUrl("/generate-mix")).post(body).build()

        val response = client.newCall(request).execute()
        checkAuth(response)
        if (!response.isSuccessful) return@withContext emptyList()
        val json = response.body?.string() ?: return@withContext emptyList()
        val obj = JsonParser.parseString(json).asJsonObject
        val arr = obj.getAsJsonArray("tracks") ?: return@withContext emptyList()

        arr.map { el ->
            val o = el.asJsonObject
            Track(
                videoId = o.get("videoId").asString,
                title = o.get("title")?.asString ?: "",
                channel = o.get("channel")?.asString ?: "",
                position = o.get("position")?.asInt ?: 0,
                thumbnail = o.get("thumbnail")?.asString ?: "",
            )
        }
    }

    suspend fun savePlaylist(
        id: String, type: String, title: String,
        thumbnail: String, channel: String, query: String
    ): Boolean = withContext(Dispatchers.IO) {
        val body = gson.toJson(mapOf(
            "id" to id, "type" to type, "title" to title,
            "thumbnail" to thumbnail, "channel" to channel, "query" to query,
        )).toRequestBody(jsonType)
        val request = authRequest(apiUrl("/save-playlist")).post(body).build()
        client.newCall(request).execute().isSuccessful
    }

    suspend fun deletePlaylist(playlistId: Int): Boolean = withContext(Dispatchers.IO) {
        val body = "{}".toRequestBody(jsonType)
        val request = authRequest(apiUrl("/delete-playlist/$playlistId")).post(body).build()
        client.newCall(request).execute().isSuccessful
    }

    suspend fun getUserPlaylists(): List<UserPlaylistInfo> = withContext(Dispatchers.IO) {
        val request = authRequest(apiUrl("/user-playlists")).build()
        val response = client.newCall(request).execute()
        checkAuth(response)
        val json = response.body?.string() ?: return@withContext emptyList()
        val obj = JsonParser.parseString(json).asJsonObject
        val arr = obj.getAsJsonArray("playlists") ?: return@withContext emptyList()

        arr.map { el ->
            val o = el.asJsonObject
            UserPlaylistInfo(
                id = o.get("id").asInt,
                name = o.get("name").asString,
                playlistType = o.get("playlistType")?.asString ?: "mix",
                trackCount = o.get("trackCount")?.asInt ?: 0,
            )
        }
    }

    suspend fun getUserPlaylistTracks(playlistId: Int): List<Track> = withContext(Dispatchers.IO) {
        val request = authRequest(apiUrl("/user-playlist-tracks/$playlistId")).build()
        val response = client.newCall(request).execute()
        checkAuth(response)
        val json = response.body?.string() ?: return@withContext emptyList()
        val obj = JsonParser.parseString(json).asJsonObject
        val arr = obj.getAsJsonArray("tracks") ?: return@withContext emptyList()

        arr.map { el ->
            val o = el.asJsonObject
            Track(
                videoId = o.get("videoId").asString,
                title = o.get("title").asString,
                channel = o.get("channel")?.asString ?: "",
                position = o.get("position")?.asInt ?: 0,
                thumbnail = o.get("thumbnail")?.asString ?: "",
            )
        }
    }

    suspend fun saveMix(name: String, tracks: List<Track>): Boolean = withContext(Dispatchers.IO) {
        val trackMaps = tracks.map { mapOf(
            "videoId" to it.videoId, "title" to it.title,
            "channel" to it.channel, "thumbnail" to it.thumbnail,
        )}
        val body = gson.toJson(mapOf("name" to name, "tracks" to trackMaps)).toRequestBody(jsonType)
        val request = authRequest(apiUrl("/save-mix")).post(body).build()
        client.newCall(request).execute().isSuccessful
    }

    suspend fun deleteUserPlaylist(playlistId: Int): Boolean = withContext(Dispatchers.IO) {
        val body = "{}".toRequestBody(jsonType)
        val request = authRequest(apiUrl("/delete-user-playlist/$playlistId")).post(body).build()
        client.newCall(request).execute().isSuccessful
    }

    suspend fun favoriteTrack(track: Track): Boolean = withContext(Dispatchers.IO) {
        val body = gson.toJson(mapOf(
            "videoId" to track.videoId, "title" to track.title,
            "channel" to track.channel, "thumbnail" to track.thumbnail,
        )).toRequestBody(jsonType)
        val request = authRequest(apiUrl("/favorite-track")).post(body).build()
        client.newCall(request).execute().isSuccessful
    }

    suspend fun unfavoriteTrack(videoId: String): Boolean = withContext(Dispatchers.IO) {
        val body = gson.toJson(mapOf("videoId" to videoId)).toRequestBody(jsonType)
        val request = authRequest(apiUrl("/unfavorite-track")).post(body).build()
        client.newCall(request).execute().isSuccessful
    }

    suspend fun isFavorited(videoId: String): Boolean = withContext(Dispatchers.IO) {
        val request = authRequest(apiUrl("/is-favorited?videoId=$videoId")).build()
        val response = client.newCall(request).execute()
        checkAuth(response)
        if (!response.isSuccessful) return@withContext false
        val json = response.body?.string() ?: return@withContext false
        val obj = JsonParser.parseString(json).asJsonObject
        obj.get("favorited")?.asBoolean ?: false
    }

    private fun checkAuth(response: okhttp3.Response) {
        if (response.code == 401) {
            token = null
            throw AuthException("Session expired")
        }
    }
}

class AuthException(message: String) : Exception(message)
