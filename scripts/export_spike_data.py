"""
export_spike_data.py — Add this code to stdp_two_populations.py

Insert the block below just before the "# Visualization" section in
stdp_two_populations.py to save the files needed by the FPGA replay.

Files produced:
  spike_data.npy         — pre and post spike times and neuron IDs
  nest_final_weights.npy — final NEST weight matrix, shape (50, 50)

These two files are transferred to the Pynq-Z2 alongside the bitstream.
"""

# ---------------------------------------------------------------------------
# Paste this block into stdp_two_populations.py before the visualisation
# ---------------------------------------------------------------------------

import numpy as np

np.save("spike_data.npy", {
    "pre_times":  spike_times_pre,
    "pre_ids":    spike_senders_pre,
    "post_times": spike_times_post,
    "post_ids":   spike_senders_post,
})

np.save("nest_final_weights.npy",
        np.array(nest_weights[-1]).reshape(N_PRE, N_POST))

print("Saved spike_data.npy and nest_final_weights.npy")
print(f"  Pre  spikes: {len(spike_times_pre)}")
print(f"  Post spikes: {len(spike_times_post)}")
