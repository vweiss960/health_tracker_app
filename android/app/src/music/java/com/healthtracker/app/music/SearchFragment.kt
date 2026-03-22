package com.healthtracker.app.music

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.EditorInfo
import android.widget.*
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import coil.load
import com.healthtracker.app.R
import kotlinx.coroutines.launch

class SearchFragment : Fragment() {

    private lateinit var etSearch: EditText
    private lateinit var btnSearch: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var tvStatus: TextView
    private lateinit var recyclerView: RecyclerView
    private lateinit var apiClient: ApiClient

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_search, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        apiClient = ApiClient(requireContext())

        etSearch = view.findViewById(R.id.etSearch)
        btnSearch = view.findViewById(R.id.btnSearch)
        progressBar = view.findViewById(R.id.progressBar)
        tvStatus = view.findViewById(R.id.tvStatus)
        recyclerView = view.findViewById(R.id.recyclerView)

        recyclerView.layoutManager = LinearLayoutManager(requireContext())

        btnSearch.setOnClickListener { doSearch() }
        etSearch.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEARCH) { doSearch(); true } else false
        }
    }

    private fun doSearch() {
        val query = etSearch.text.toString().trim()
        if (query.isEmpty()) return

        progressBar.visibility = View.VISIBLE
        tvStatus.visibility = View.GONE

        lifecycleScope.launch {
            try {
                val results = apiClient.searchMusic(query)
                progressBar.visibility = View.GONE

                if (results.isEmpty()) {
                    tvStatus.text = "No results found"
                    tvStatus.visibility = View.VISIBLE
                    return@launch
                }

                recyclerView.adapter = SearchResultAdapter(results) { result ->
                    playSearchResult(result)
                }
            } catch (e: AuthException) {
                goToLogin()
            } catch (e: Exception) {
                progressBar.visibility = View.GONE
                tvStatus.text = e.message ?: "Search failed"
                tvStatus.visibility = View.VISIBLE
            }
        }
    }

    private fun playSearchResult(result: PlaylistResult) {
        if (result.type != "playlist" || result.id.isEmpty()) return

        progressBar.visibility = View.VISIBLE
        tvStatus.text = "Loading tracks..."
        tvStatus.visibility = View.VISIBLE

        lifecycleScope.launch {
            try {
                val tracks = apiClient.getPlaylistTracks(result.id)
                progressBar.visibility = View.GONE
                tvStatus.visibility = View.GONE

                if (tracks.isEmpty()) {
                    tvStatus.text = "No playable tracks found"
                    tvStatus.visibility = View.VISIBLE
                    return@launch
                }

                (activity as? MusicHomeActivity)?.startPlayback(tracks)
            } catch (e: AuthException) {
                goToLogin()
            } catch (e: Exception) {
                progressBar.visibility = View.GONE
                tvStatus.text = "Failed to load tracks"
                tvStatus.visibility = View.VISIBLE
            }
        }
    }

    private fun goToLogin() {
        apiClient.logout()
        startActivity(android.content.Intent(requireContext(), MusicLoginActivity::class.java))
        activity?.finish()
    }

    // ── Adapter ─────────────────────────────────────────────────────────────

    inner class SearchResultAdapter(
        private val items: List<PlaylistResult>,
        private val onClick: (PlaylistResult) -> Unit,
    ) : RecyclerView.Adapter<SearchResultAdapter.VH>() {

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
