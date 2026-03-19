"""
fpga_nest_compare.py — Run on Pynq-Z2 after stdp_two_populations.py has exported:
  spike_data.npy, nest_final_weights.npy

This script:
  1. Replays the exact NEST spike train on the FPGA
  2. Reads all 2500 weights back from FPGA
  3. Compares FPGA vs NEST weights (mean/max error, distribution)
  4. Saves fpga_final_weights.npy for offline plotting

Run on board:
  export XILINX_XRT=/usr
  echo xilinx | sudo -S -E /usr/local/share/pynq-venv/bin/python3 fpga_nest_compare.py
"""

import pynq
import numpy as np
import time

# =============================================================================
# Configuration — verify offsets against xstdp_top_hw.h after HLS synthesis
# =============================================================================

BITSTREAM = "stdp_system_wrapper.bit"

OFFSET_CTRL        = 0x00
OFFSET_MODE        = 0x10
OFFSET_SPIKE_TYPE  = 0x18
OFFSET_NEURON_ID   = 0x20
OFFSET_SPIKE_TIME  = 0x28
OFFSET_RW_ADDR     = 0x30
OFFSET_WRITE_DATA  = 0x38
OFFSET_READ_DATA   = 0x40
OFFSET_CYCLE_COUNT = 0x50

MODE_SPIKE    = 0
MODE_READ_W   = 1
MODE_WRITE_W  = 2
MODE_INIT_ALL = 3

N_PRE  = 50
N_POST = 50

# =============================================================================
# Load overlay
# =============================================================================

print("Loading bitstream …")
ol   = pynq.Overlay(BITSTREAM)
stdp = ol.stdp_top_0
print("Bitstream loaded. IPs:", list(ol.ip_dict.keys()))

# =============================================================================
# Helpers
# =============================================================================

def _run():
    stdp.write(OFFSET_CTRL, 1)
    while not (stdp.read(OFFSET_CTRL) & 0x2):
        pass

def send_spike(spike_type, neuron_id, spike_time_01ms):
    stdp.write(OFFSET_MODE,       MODE_SPIKE)
    stdp.write(OFFSET_SPIKE_TYPE, int(spike_type))
    stdp.write(OFFSET_NEURON_ID,  int(neuron_id))
    stdp.write(OFFSET_SPIKE_TIME, int(spike_time_01ms))
    _run()
    return int(stdp.read(OFFSET_CYCLE_COUNT))

def read_weight(pre, post):
    stdp.write(OFFSET_MODE,    MODE_READ_W)
    stdp.write(OFFSET_RW_ADDR, pre * N_POST + post)
    _run()
    return stdp.read(OFFSET_READ_DATA) / 32768.0

def read_all_weights():
    w = np.zeros((N_PRE, N_POST), dtype=np.float32)
    for i in range(N_PRE):
        for j in range(N_POST):
            w[i, j] = read_weight(i, j)
    return w

def init_all():
    stdp.write(OFFSET_MODE, MODE_INIT_ALL)
    _run()

# =============================================================================
# Load spike data from NEST
# =============================================================================

print("\nLoading spike data …")
data    = np.load("spike_data.npy", allow_pickle=True).item()
pre_t   = (data["pre_times"]  * 10).astype(int)   # ms → 0.1ms integer
pre_id  = data["pre_ids"].astype(int)
post_t  = (data["post_times"] * 10).astype(int)
post_id = data["post_ids"].astype(int)

nest_w  = np.load("nest_final_weights.npy")        # (50, 50) float64

all_spikes = (
    [(t, i, 0) for t, i in zip(pre_t,  pre_id)]  +
    [(t, j, 1) for t, j in zip(post_t, post_id)]
)
all_spikes.sort(key=lambda x: x[0])

print(f"Total spikes: {len(all_spikes)}  (pre={len(pre_t)}, post={len(post_t)})")

# =============================================================================
# Replay on FPGA
# =============================================================================

print("\nInitialising weights to 0.5 …")
init_all()

print("Replaying spike train on FPGA …")
total_cycles = 0
t_start = time.perf_counter()

for t, nid, stype in all_spikes:
    total_cycles += send_spike(stype, nid, t)

t_end = time.perf_counter()
wall_ms    = (t_end - t_start) * 1e3
compute_ms = total_cycles * 10 / 1e6   # 100 MHz
n_ev       = len(all_spikes)

print(f"  Wall clock:         {wall_ms:.2f} ms")
print(f"  FPGA compute:       {compute_ms:.3f} ms")
print(f"  Avg cycles/event:   {total_cycles / n_ev:.1f}")
print(f"  Throughput:         {n_ev * N_POST / (compute_ms / 1e3) / 1e6:.1f} M syn/s")

# =============================================================================
# Read back all weights
# =============================================================================

print("\nReading all weights from FPGA …")
t_read_start = time.perf_counter()
fpga_w = read_all_weights()
t_read_end   = time.perf_counter()
print(f"  Read-back time:  {(t_read_end - t_read_start)*1e3:.1f} ms")

np.save("fpga_final_weights.npy", fpga_w)
print("  Saved: fpga_final_weights.npy")

# =============================================================================
# Accuracy comparison
# =============================================================================

err       = np.abs(fpga_w - nest_w.astype(np.float32))
rel_err   = err / (nest_w.astype(np.float32) + 1e-9)

print(f"\n{'='*60}")
print("ACCURACY: FPGA vs NEST")
print(f"{'='*60}")
print(f"  Mean weight (FPGA):     {fpga_w.mean():.6f}")
print(f"  Mean weight (NEST):     {nest_w.mean():.6f}")
print(f"  Mean absolute error:    {err.mean():.2e}  (16-bit target: ~5e-5)")
print(f"  Max  absolute error:    {err.max():.2e}")
print(f"  Mean relative error:    {rel_err.mean()*100:.3f}%")
print(f"  Max  relative error:    {rel_err.max()*100:.3f}%")

# Quantisation floor (Q1.15 = 1/32768 ≈ 3e-5)
print(f"\n  Q1.15 resolution:       {1/32768:.2e}")
print(f"  Error / Q-step ratio:   {err.mean() / (1/32768):.1f}×")
print(f"  (>1 = dominated by online-vs-batch formulation difference)")

# Fraction of weights that differ from NEST by more than 1 Q-step
frac_large = (err > 2/32768).mean() * 100
print(f"  Weights with err > 2 Q-steps:  {frac_large:.1f}%")

print(f"\n{'='*60}")
print("PERFORMANCE SUMMARY (for paper)")
print(f"{'='*60}")
print(f"  FPGA compute per event:   {compute_ms*1e6/n_ev:.0f} ns")
print(f"  AXI overhead per event:   {(wall_ms-compute_ms)*1e3/n_ev:.0f} µs")
print(f"  Total FPGA compute:       {compute_ms:.2f} ms")
print(f"  Total wall clock:         {wall_ms:.2f} ms")
print(f"  Synapse update rate:      {n_ev*N_POST/(compute_ms/1e3)/1e6:.1f} M/s")
print(f"  Weight MAE vs NEST:       {err.mean():.2e}")
print(f"{'='*60}")
print("\nComparison targets:")
print("  NEST:   ~3.6 µs/event,  ~64 ms total (network sim, not just STDP)")
print("  Python: ~192 µs/event,  ~5.6 s total")
