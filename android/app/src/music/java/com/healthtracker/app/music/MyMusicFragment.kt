package com.healthtracker.app.music

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.GridLayoutManager
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.healthtracker.app.R
import kotlinx.coroutines.launch

class MyMusicFragment : Fragment() {

    private lateinit var recyclerView: RecyclerView
    private lateinit var progressBar: ProgressBar
    private lateinit var tvEmpty: TextView
    private lateinit var apiClient: ApiClient

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_my_music, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        apiClient = ApiClient(requireContext())
        recyclerView = view.findViewById(R.id.recyclerView)
        progressBar = view.findViewById(R.id.progressBar)
        tvEmpty = view.findViewById(R.id.tvEmpty)

        recyclerView.layoutManager = LinearLayoutManager(requireContext())
        loadPlaylists()
    }

    override fun onResume() {
        super.onResume()
        loadPlaylists()
    }

    private fun loadPlaylists() {
        progressBar.visibility = View.VISIBLE
        tvEmpty.visibility = View.GONE

        lifecycleScope.launch {
            try {
                val userPlaylists = apiClient.getUserPlaylists()
                val ytPlaylists = apiClient.getPlaylists()
                progressBar.visibility = View.GONE

                if (userPlaylists.isEmpty() && ytPlaylists.isEmpty()) {
                    tvEmpty.visibility = View.VISIBLE
                    return@launch
                }

                val items = mutableListOf<ListItem>()

                // User playlists section (favorites + saved mixes)
                if (userPlaylists.isNotEmpty()) {
                    items.add(ListItem.Header("My Playlists"))
                    userPlaylists.forEach { items.add(ListItem.UserPlaylistItem(it)) }
                }

                // YouTube playlists section
                if (ytPlaylists.isNotEmpty()) {
                    items.add(ListItem.Header("Saved from Search"))
                    ytPlaylists.forEach { items.add(ListItem.YTPlaylistItem(it)) }
                }

                recyclerView.adapter = CombinedAdapter(items)
            } catch (e: AuthException) {
                goToLogin()
            } catch (e: Exception) {
                progressBar.visibility = View.GONE
                tvEmpty.text = "Failed to load playlists"
                tvEmpty.visibility = View.VISIBLE
            }
        }
    }

    private fun playUserPlaylist(playlist: UserPlaylistInfo) {
        progressBar.visibility = View.VISIBLE

        lifecycleScope.launch {
            try {
                val tracks = apiClient.getUserPlaylistTracks(playlist.id)
                progressBar.visibility = View.GONE
                if (tracks.isEmpty()) return@launch
                (activity as? MusicHomeActivity)?.startPlayback(tracks)
            } catch (e: AuthException) {
                goToLogin()
            } catch (e: Exception) {
                progressBar.visibility = View.GONE
            }
        }
    }

    private fun playPlaylist(playlist: Playlist) {
        progressBar.visibility = View.VISIBLE

        lifecycleScope.launch {
            try {
                val tracks = apiClient.getPlaylistTracks(playlist.youtubeId)
                progressBar.visibility = View.GONE
                if (tracks.isEmpty()) return@launch
                (activity as? MusicHomeActivity)?.startPlayback(tracks)
            } catch (e: AuthException) {
                goToLogin()
            } catch (e: Exception) {
                progressBar.visibility = View.GONE
            }
        }
    }

    private fun deleteUserPlaylist(playlist: UserPlaylistInfo, position: Int) {
        android.app.AlertDialog.Builder(requireContext())
            .setTitle("Delete Playlist")
            .setMessage("Delete \"${playlist.name}\"?")
            .setPositiveButton("Delete") { _, _ ->
                lifecycleScope.launch {
                    try {
                        apiClient.deleteUserPlaylist(playlist.id)
                        loadPlaylists()
                    } catch (_: Exception) { }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }

    private fun goToLogin() {
        apiClient.logout()
        startActivity(android.content.Intent(requireContext(), MusicLoginActivity::class.java))
        activity?.finish()
    }

    // ── Combined list items ─────────────────────────────────────────────────

    sealed class ListItem {
        data class Header(val title: String) : ListItem()
        data class UserPlaylistItem(val playlist: UserPlaylistInfo) : ListItem()
        data class YTPlaylistItem(val playlist: Playlist) : ListItem()
    }

    inner class CombinedAdapter(
        private val items: List<ListItem>,
    ) : RecyclerView.Adapter<RecyclerView.ViewHolder>() {

        private val TYPE_HEADER = 0
        private val TYPE_USER_PLAYLIST = 1
        private val TYPE_YT_PLAYLIST = 2

        override fun getItemViewType(position: Int) = when (items[position]) {
            is ListItem.Header -> TYPE_HEADER
            is ListItem.UserPlaylistItem -> TYPE_USER_PLAYLIST
            is ListItem.YTPlaylistItem -> TYPE_YT_PLAYLIST
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): RecyclerView.ViewHolder {
            val inflater = LayoutInflater.from(parent.context)
            return when (viewType) {
                TYPE_HEADER -> {
                    val tv = TextView(parent.context).apply {
                        layoutParams = RecyclerView.LayoutParams(
                            RecyclerView.LayoutParams.MATCH_PARENT,
                            RecyclerView.LayoutParams.WRAP_CONTENT
                        )
                        setPadding(32, 32, 32, 12)
                        textSize = 16f
                        setTextColor(resources.getColor(R.color.music_text_secondary, null))
                    }
                    object : RecyclerView.ViewHolder(tv) {}
                }
                TYPE_USER_PLAYLIST -> {
                    val view = inflater.inflate(R.layout.item_track, parent, false)
                    UserPlaylistVH(view)
                }
                else -> {
                    val view = inflater.inflate(R.layout.item_playlist_card, parent, false)
                    YTPlaylistVH(view)
                }
            }
        }

        override fun onBindViewHolder(holder: RecyclerView.ViewHolder, position: Int) {
            when (val item = items[position]) {
                is ListItem.Header -> {
                    (holder.itemView as TextView).text = item.title
                }
                is ListItem.UserPlaylistItem -> {
                    val vh = holder as UserPlaylistVH
                    val p = item.playlist
                    val icon = if (p.playlistType == "favorites") "\u2605 " else "\u266B "
                    vh.title.text = "$icon${p.name}"
                    vh.channel.text = "${p.trackCount} tracks"
                    vh.position.text = ""
                    vh.itemView.setOnClickListener { playUserPlaylist(p) }
                    vh.itemView.setOnLongClickListener {
                        if (p.playlistType != "favorites") {
                            deleteUserPlaylist(p, position)
                        }
                        true
                    }
                }
                is ListItem.YTPlaylistItem -> {
                    val vh = holder as YTPlaylistVH
                    val p = item.playlist
                    vh.title.text = p.title
                    vh.channel.text = p.channel
                    if (p.thumbnail.isNotEmpty()) {
                        vh.thumbnail.load(p.thumbnail) { crossfade(true) }
                    }
                    vh.itemView.setOnClickListener { playPlaylist(p) }
                }
            }
        }

        override fun getItemCount() = items.size

        inner class UserPlaylistVH(view: View) : RecyclerView.ViewHolder(view) {
            val position: TextView = view.findViewById(R.id.tvTrackPosition)
            val title: TextView = view.findViewById(R.id.tvTrackTitle)
            val channel: TextView = view.findViewById(R.id.tvTrackChannel)
        }

        inner class YTPlaylistVH(view: View) : RecyclerView.ViewHolder(view) {
            val thumbnail: ImageView = view.findViewById(R.id.ivThumbnail)
            val title: TextView = view.findViewById(R.id.tvTitle)
            val channel: TextView = view.findViewById(R.id.tvChannel)
        }
    }
}
