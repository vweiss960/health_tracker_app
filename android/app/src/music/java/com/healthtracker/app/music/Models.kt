package com.healthtracker.app.music

data class Playlist(
    val id: Int,
    val title: String,
    val youtubeId: String,
    val playlistType: String,
    val thumbnail: String,
    val channel: String,
)

data class Track(
    val videoId: String,
    val title: String,
    val channel: String,
    val position: Int,
    val thumbnail: String = "",
)

data class StreamResult(
    val url: String,
    val duration: Int,
    val title: String,
    val channel: String,
    val thumbnail: String,
)

data class PlaylistResult(
    val type: String,
    val id: String,
    val title: String,
    val channel: String,
    val thumbnail: String,
    val trackCount: Int = 0,
    val description: String = "",
    val query: String = "",
)

data class AuthResult(
    val token: String,
    val userId: Int,
    val displayName: String,
)
