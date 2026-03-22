package com.healthtracker.app.music

class QueueManager {

    private var originalTracks: List<Track> = emptyList()
    private var shuffledIndices: IntArray = intArrayOf()
    private var currentPosition: Int = -1

    var shuffleEnabled: Boolean = true
        private set

    val currentTrack: Track?
        get() {
            if (originalTracks.isEmpty() || currentPosition < 0) return null
            val idx = if (shuffleEnabled) {
                shuffledIndices.getOrNull(currentPosition) ?: return null
            } else {
                currentPosition
            }
            return originalTracks.getOrNull(idx)
        }

    val trackCount: Int get() = originalTracks.size
    val currentIndex: Int get() = currentPosition

    val hasNext: Boolean
        get() = originalTracks.isNotEmpty() && currentPosition < originalTracks.size - 1

    val hasPrevious: Boolean
        get() = currentPosition > 0

    fun loadTracks(tracks: List<Track>) {
        originalTracks = tracks
        currentPosition = if (tracks.isNotEmpty()) 0 else -1
        if (shuffleEnabled) {
            rebuildShuffleOrder()
        }
    }

    fun toggleShuffle(): Boolean {
        shuffleEnabled = !shuffleEnabled
        if (shuffleEnabled) {
            rebuildShuffleOrder()
        }
        return shuffleEnabled
    }

    fun next(): Track? {
        if (originalTracks.isEmpty()) return null
        currentPosition++
        if (currentPosition >= originalTracks.size) {
            if (shuffleEnabled) {
                rebuildShuffleOrder()
            }
            currentPosition = 0
        }
        return currentTrack
    }

    fun previous(): Track? {
        if (originalTracks.isEmpty()) return null
        if (currentPosition > 0) {
            currentPosition--
        }
        return currentTrack
    }

    fun skipToIndex(index: Int): Track? {
        if (index < 0 || index >= originalTracks.size) return null
        currentPosition = index
        return currentTrack
    }

    fun getAllTracks(): List<Track> {
        if (!shuffleEnabled) return originalTracks
        return shuffledIndices.toList().mapNotNull { originalTracks.getOrNull(it) }
    }

    private fun rebuildShuffleOrder() {
        val indices = originalTracks.indices.toMutableList()
        for (i in indices.size - 1 downTo 1) {
            val j = (0..i).random()
            val temp = indices[i]
            indices[i] = indices[j]
            indices[j] = temp
        }
        shuffledIndices = indices.toIntArray()
    }
}
