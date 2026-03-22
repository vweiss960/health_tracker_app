package com.healthtracker.app.music

import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.healthtracker.app.R
import kotlinx.coroutines.launch

class GenerateMixFragment : Fragment() {

    private lateinit var etPrompt: EditText
    private lateinit var btnGenerate: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var tvStatus: TextView
    private lateinit var recyclerView: RecyclerView
    private lateinit var apiClient: ApiClient

    override fun onCreateView(inflater: LayoutInflater, container: ViewGroup?, savedInstanceState: Bundle?): View {
        return inflater.inflate(R.layout.fragment_generate_mix, container, false)
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        apiClient = ApiClient(requireContext())

        etPrompt = view.findViewById(R.id.etPrompt)
        btnGenerate = view.findViewById(R.id.btnGenerate)
        progressBar = view.findViewById(R.id.progressBar)
        tvStatus = view.findViewById(R.id.tvStatus)
        recyclerView = view.findViewById(R.id.recyclerView)

        recyclerView.layoutManager = LinearLayoutManager(requireContext())

        btnGenerate.setOnClickListener { generateMix() }
    }

    private fun generateMix() {
        val prompt = etPrompt.text.toString().trim()
        if (prompt.isEmpty()) return

        progressBar.visibility = View.VISIBLE
        tvStatus.text = "AI is building your mix..."
        tvStatus.visibility = View.VISIBLE
        btnGenerate.isEnabled = false

        lifecycleScope.launch {
            try {
                val tracks = apiClient.generateMix(prompt)
                progressBar.visibility = View.GONE
                btnGenerate.isEnabled = true

                if (tracks.isEmpty()) {
                    tvStatus.text = "Could not generate mix. Try a different description."
                    return@launch
                }

                tvStatus.text = "${tracks.size} tracks generated"

                recyclerView.adapter = TrackAdapter(tracks)

                (activity as? MusicHomeActivity)?.startPlayback(tracks)
            } catch (e: AuthException) {
                goToLogin()
            } catch (e: Exception) {
                progressBar.visibility = View.GONE
                btnGenerate.isEnabled = true
                tvStatus.text = e.message ?: "Failed to generate mix"
            }
        }
    }

    private fun goToLogin() {
        apiClient.logout()
        startActivity(android.content.Intent(requireContext(), MusicLoginActivity::class.java))
        activity?.finish()
    }

    // ── Adapter ─────────────────────────────────────────────────────────────

    inner class TrackAdapter(
        private val items: List<Track>,
    ) : RecyclerView.Adapter<TrackAdapter.VH>() {

        inner class VH(view: View) : RecyclerView.ViewHolder(view) {
            val position: TextView = view.findViewById(R.id.tvTrackPosition)
            val title: TextView = view.findViewById(R.id.tvTrackTitle)
            val channel: TextView = view.findViewById(R.id.tvTrackChannel)
        }

        override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): VH {
            val view = LayoutInflater.from(parent.context)
                .inflate(R.layout.item_track, parent, false)
            return VH(view)
        }

        override fun onBindViewHolder(holder: VH, position: Int) {
            val item = items[position]
            holder.position.text = "${position + 1}"
            holder.title.text = item.title
            holder.channel.text = item.channel
        }

        override fun getItemCount() = items.size
    }
}
