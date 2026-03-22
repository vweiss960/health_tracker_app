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

        recyclerView.layoutManager = GridLayoutManager(requireContext(), 2)
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
                val playlists = apiClient.getPlaylists()
                progressBar.visibility = View.GONE

                if (playlists.isEmpty()) {
                    tvEmpty.visibility = View.VISIBLE
                    return@launch
                }

                recyclerView.adapter = PlaylistCardAdapter(playlists) { playlist ->
                    playPlaylist(playlist)
                }
            } catch (e: AuthException) {
                goToLogin()
            } catch (e: Exception) {
                progressBar.visibility = View.GONE
                tvEmpty.text = "Failed to load playlists"
                tvEmpty.visibility = View.VISIBLE
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

    private fun goToLogin() {
        apiClient.logout()
        startActivity(android.content.Intent(requireContext(), MusicLoginActivity::class.java))
        activity?.finish()
    }

    // ── Adapter ─────────────────────────────────────────────────────────────

    inner class PlaylistCardAdapter(
        private val items: List<Playlist>,
        private val onClick: (Playlist) -> Unit,
    ) : RecyclerView.Adapter<PlaylistCardAdapter.VH>() {

        inner class VH(view: View) : RecyclerView.ViewHolder(view) {
            val thumbnail: ImageView = view.findViewById(R.id.ivThumbnail)
            val title: TextView = view.findViewById(R.id.tvTitle)
            val channel: TextView = view.findViewById(R.id.tvChannel)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_playlist_card, parent, false)
            return VH(view)
        }

        override fun onBindViewHolder(holder: VH, position: Int) {
            val item = items[position]
            holder.title.text = item.title
            holder.channel.text = item.channel
            if (item.thumbnail.isNotEmpty()) {
                holder.thumbnail.load(item.thumbnail) { crossfade(true) }
            }
            holder.itemView.setOnClickListener { onClick(item) }
        }

        override fun getItemCount() = items.size
    }
}
