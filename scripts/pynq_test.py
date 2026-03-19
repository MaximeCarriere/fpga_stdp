"""
pynq_test.py — STDP FPGA benchmark and validation
Run on Pynq-Z2 (Linux + Pynq framework), e.g. from Jupyter.

Prerequisites (files in the same directory):
  stdp_system_wrapper.bit   — bitstream from Vivado
  stdp_system_wrapper.hwh   — hardware handoff from Vivado (renamed to match .bit)
  spike_data.npy            — pre/post spike times+ids from stdp_two_populations.py
  nest_final_weights.npy    — final NEST weight matrix from stdp_two_populations.py

AXI-Lite register offsets — verify against generated header after HLS synthesis:
  <project>/stdp_hls/solution1/impl/ip/drivers/stdp_top_v*/src/xstdp_top_hw.h
"""

import pynq
import numpy as np
import time

# =============================================================================
# Configuration
# =============================================================================

BITSTREAM = "stdp_system_wrapper.bit"

# AXI-Lite register byte offsets (check xstdp_top_hw.h after HLS synthesis)
# Offsets verified against stdp_hls/solution1/impl/ip/drivers/stdp_top_v1_0/src/xstdp_top_hw.h
OFFSET_CTRL        = 0x00   # ap_ctrl: bit0=ap_start, bit1=ap_done, bit2=ap_idle
OFFSET_MODE        = 0x10
OFFSET_SPIKE_TYPE  = 0x18
OFFSET_NEURON_ID   = 0x20
OFFSET_SPIKE_TIME  = 0x28
OFFSET_RW_ADDR     = 0x30
OFFSET_WRITE_DATA  = 0x38
OFFSET_READ_DATA   = 0x40   # 0x44 = ap_vld flag (read/clear on read)
OFFSET_CYCLE_COUNT = 0x50   # 0x54 = ap_vld flag

# Operation modes (must match MODE_* in stdp_top.h)
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
stdp = ol.stdp_top_0          # check ol.ip_dict.keys() if this fails
print("Bitstream loaded.")
print("Available IPs:", list(ol.ip_dict.keys()))

# =============================================================================
# Helper functions
# =============================================================================

def _run():
    """Pulse ap_start and wait for ap_done."""
    stdp.write(OFFSET_CTRL, 1)
    while not (stdp.read(OFFSET_CTRL) & 0x2):
        pass


def send_spike(spike_type, neuron_id, spike_time_01ms):
    """Inject one spike event.  Returns FPGA cycle count."""
    stdp.write(OFFSET_MODE,       MODE_SPIKE)
    stdp.write(OFFSET_SPIKE_TYPE, int(spike_type))
    stdp.write(OFFSET_NEURON_ID,  int(neuron_id))
    stdp.write(OFFSET_SPIKE_TIME, int(spike_time_01ms))
    _run()
    return int(stdp.read(OFFSET_CYCLE_COUNT))


def read_weight(pre, post):
    """Read W[pre][post] as float (Q1.15: raw / 32768)."""
    stdp.write(OFFSET_MODE,    MODE_READ_W)
    stdp.write(OFFSET_RW_ADDR, pre * N_POST + post)
    _run()
    return stdp.read(OFFSET_READ_DATA) / 32768.0


def write_weight(pre, post, val_float):
    """Write W[pre][post] = val_float."""
    stdp.write(OFFSET_MODE,       MODE_WRITE_W)
    stdp.write(OFFSET_RW_ADDR,    pre * N_POST + post)
    stdp.write(OFFSET_WRITE_DATA, int(val_float * 32768))
    _run()


def init_all_weights(w_init=0.5):
    """Reset all weights to w_init, clear all traces and timestamps."""
    if abs(w_init - 0.5) < 1e-6:
        # Fast path: hardware MODE_INIT_ALL (sets to W_INIT = 0.5)
        stdp.write(OFFSET_MODE, MODE_INIT_ALL)
        _run()
    else:
        # Manual init for non-default value
        for i in range(N_PRE):
            for j in range(N_POST):
                write_weight(i, j, w_init)


def read_all_weights():
    """Read all N_PRE × N_POST weights.  Returns (50, 50) float32 array."""
    w = np.zeros((N_PRE, N_POST), dtype=np.float32)
    for i in range(N_PRE):
        for j in range(N_POST):
            w[i, j] = read_weight(i, j)
    return w


# =============================================================================
# Initialise weights to 0.5 (matching Python / NEST simulation start)
# =============================================================================
print("\nInitialising weights to 0.5 …")
init_all_weights(0.5)

# =============================================================================
# Sanity check — single LTP and LTD event
# =============================================================================
print("\n--- Sanity check ---")

send_spike(0, 0, 1000)   # pre  fires at 100 ms
send_spike(1, 0, 1100)   # post fires at 110 ms → LTP
w_ltp = read_weight(0, 0)
print(f"W[0][0] after LTP:  {w_ltp:.4f}  (expected > 0.5)")
assert w_ltp > 0.5, "LTP FAILED"

init_all_weights()
send_spike(1, 1, 2000)   # post fires at 200 ms
send_spike(0, 1, 2100)   # pre  fires at 210 ms → LTD
w_ltd = read_weight(1, 1)
print(f"W[1][1] after LTD:  {w_ltd:.4f}  (expected < 0.5)")
assert w_ltd < 0.5, "LTD FAILED"

print("Sanity check PASSED")

# =============================================================================
# Single-event timing characterisation
# =============================================================================
print("\n--- Single-event timing ---")

init_all_weights()
N_WARMUP  = 5
N_MEASURE = 100

for _ in range(N_WARMUP):
    send_spike(0, 0, 3000)

pre_wall_us = []
pre_cycles  = []
for k in range(N_MEASURE):
    t0 = time.perf_counter()
    c  = send_spike(0, 0, 3000 + k * 500)
    t1 = time.perf_counter()
    pre_wall_us.append((t1 - t0) * 1e6)
    pre_cycles.append(c)

mean_cycles = np.mean(pre_cycles)
mean_wall   = np.mean(pre_wall_us)
fpga_ns     = mean_cycles * 10           # 100 MHz → 10 ns/cycle
comms_us    = mean_wall - fpga_ns / 1e3

print(f"Mean FPGA cycles/event:     {mean_cycles:.1f}")
print(f"Mean FPGA compute time:     {fpga_ns:.1f} ns  ({fpga_ns/1000:.3f} µs)")
print(f"Mean wall clock/event:      {mean_wall:.2f} µs")
print(f"Estimated AXI overhead:     {comms_us:.2f} µs")

# =============================================================================
# Full simulation replay
# =============================================================================
print("\n--- Full simulation replay ---")

init_all_weights()

data    = np.load("spike_data.npy", allow_pickle=True).item()
pre_t   = (data["pre_times"]  * 10).astype(int)
pre_id  = data["pre_ids"].astype(int)
post_t  = (data["post_times"] * 10).astype(int)
post_id = data["post_ids"].astype(int)

all_spikes = (
    [(t, i, 0) for t, i in zip(pre_t,  pre_id)] +
    [(t, j, 1) for t, j in zip(post_t, post_id)]
)
all_spikes.sort(key=lambda x: x[0])
print(f"Total events: {len(all_spikes)}  (pre={len(pre_t)}, post={len(post_t)})")

total_cycles = 0
t_sim_start  = time.perf_counter()
for t, nid, stype in all_spikes:
    total_cycles += send_spike(stype, nid, t)
t_sim_end = time.perf_counter()

wall_ms    = (t_sim_end - t_sim_start) * 1e3
compute_ms = total_cycles * 10 / 1e6
comms_ms   = wall_ms - compute_ms
n_ev       = len(all_spikes)

print(f"Total wall clock:            {wall_ms:.2f} ms")
print(f"Total FPGA compute:          {compute_ms:.3f} ms")
print(f"Total AXI overhead:          {comms_ms:.2f} ms")
print(f"Avg FPGA cycles/event:       {total_cycles / n_ev:.1f}")
print(f"Avg FPGA compute/event:      {compute_ms * 1e6 / n_ev:.1f} ns")
throughput = n_ev * N_POST / (compute_ms / 1e3) / 1e6
print(f"Throughput (syn updates/s):  {throughput:.1f} M/s")

# =============================================================================
# Accuracy validation vs NEST
# =============================================================================
print("\n--- Accuracy vs NEST ---")

fpga_w = read_all_weights()
nest_w = np.load("nest_final_weights.npy")
err    = np.abs(fpga_w - nest_w)
print(f"Mean absolute error:  {err.mean():.2e}  (16-bit target: ~5e-5)")
print(f"Max  absolute error:  {err.max():.2e}")
print(f"Mean weight (FPGA):   {fpga_w.mean():.6f}")
print(f"Mean weight (NEST):   {nest_w.mean():.6f}")

# =============================================================================
# Paper summary
# =============================================================================
print("\n" + "=" * 60)
print("PAPER SUMMARY")
print("=" * 60)
print(f"Pure FPGA compute / event:   {compute_ms * 1e6 / n_ev:.0f} ns")
print(f"AXI overhead / event:        {comms_ms * 1e3 / n_ev:.0f} µs")
print(f"Full simulation (compute):   {compute_ms:.2f} ms")
print(f"Full simulation (wall):      {wall_ms:.2f} ms")
print(f"Synapse update throughput:   {throughput:.1f} M syn/s")
print(f"Weight accuracy (mean err):  {err.mean():.2e}")
print("=" * 60)
print("\nComparison targets:")
print("  NEST:   ~3.6 µs/event,  ~64 ms total")
print("  Python: ~192 µs/event,  ~5.6 s total")
