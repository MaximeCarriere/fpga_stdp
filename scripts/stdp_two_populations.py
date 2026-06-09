"""
STDP Two Populations: 50 pre-synaptic neurons -> 50 post-synaptic neurons
All-to-all STDP connections (2500 synapses).

Python implementation validated to match NEST 3.6 stdp_synapse exactly
(see ../stdp_project_Claude/README.md for the validation methodology).
"""
import nest
import numpy as np
import matplotlib.pyplot as plt
from collections import namedtuple

# ---------------------------------------------------------------------------
# Validated NEST-exact Python classes (from two-neuron validation)
# ---------------------------------------------------------------------------

HistEntry = namedtuple('HistEntry', ['t', 'Kminus', 'Kminus_triplet', 'access_counter'])

class ArchivingNode:
    def __init__(self, tau_minus=20.0):
        self.tau_minus = tau_minus
        self.tau_minus_inv = 1.0 / tau_minus
        self.Kminus = 0.0
        self.last_spike = -1.0
        self.history = []
        self.stdp_eps = 1e-6

    def get_K_value(self, t):
        """Matches NEST archiving_node::get_K_value() exactly."""
        if not self.history:
            return 0.0
        i = len(self.history) - 1
        while i >= 0:
            if t - self.history[i].t > self.stdp_eps:
                return self.history[i].Kminus * np.exp((self.history[i].t - t) * self.tau_minus_inv)
            i -= 1
        return 0.0

    def set_spiketime(self, t_sp):
        self.Kminus = self.Kminus * np.exp((self.last_spike - t_sp) * self.tau_minus_inv) + 1.0
        self.last_spike = t_sp
        self.history.append(HistEntry(t=t_sp, Kminus=self.Kminus,
                                      Kminus_triplet=0.0, access_counter=0))

    def get_history(self, t1, t2):
        """Returns spikes in (t1, t2] — matches NEST archiving_node::get_history()."""
        if not self.history:
            return []
        t2_lim = t2 + self.stdp_eps
        t1_lim = t1 + self.stdp_eps  # exclusive lower bound
        result = []
        for entry in reversed(self.history):
            if entry.t < t1_lim:
                break
            if entry.t < t2_lim:
                result.append(entry)
        return list(reversed(result))


class STDPSynapse:
    def __init__(self, weight, Wmax=1.0, tau_plus=20.0, lambd=0.01, alpha=1.2, delay=0.1):
        self.weight = weight
        self.Wmax = Wmax
        self.tau_plus = tau_plus
        self.lambd = lambd
        self.alpha = alpha
        self.delay = delay
        self.Kplus = 0.0
        self.t_lastspike = 0.0  # fire time (matches NEST t_lastspike_)
        self.stdp_eps = 1e-6

    def facilitate(self, w, kplus):
        norm_w = (w / self.Wmax) + (self.lambd * kplus)
        return np.clip(norm_w, 0.0, 1.0) * self.Wmax

    def depress(self, w, kminus):
        norm_w = (w / self.Wmax) - (self.lambd * self.alpha * kminus)
        return np.clip(norm_w, 0.0, 1.0) * self.Wmax

    def send(self, t_spike, target_neuron):
        """
        Matches NEST stdp_synapse::send() exactly.
        t_spike: presynaptic fire time (= e.get_stamp().get_ms() in NEST).
        """
        start_time = self.t_lastspike - self.delay
        end_time   = t_spike          - self.delay

        for hist_entry in target_neuron.get_history(start_time, end_time):
            minus_dt = self.t_lastspike - (hist_entry.t + self.delay)
            self.weight = self.facilitate(self.weight, self.Kplus * np.exp(minus_dt / self.tau_plus))

        K_value = target_neuron.get_K_value(t_spike - self.delay)
        self.weight = self.depress(self.weight, K_value)

        self.Kplus = self.Kplus * np.exp((self.t_lastspike - t_spike) / self.tau_plus) + 1.0
        self.t_lastspike = t_spike


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------

N_PRE  = 50
N_POST = 50
N_SYN  = N_PRE * N_POST  # 2500 all-to-all

DURATION        = 10000.0  # ms
SAMPLE_INTERVAL = 100.0    # ms (sample weights every 100ms)
RESOLUTION      = 0.1      # ms

TAU_PLUS  = 20.0
TAU_MINUS = 20.0
LAMBDA    = 0.01
ALPHA     = 1.2
WMAX      = 1.0
W_INIT    = 0.5
DELAY     = 0.1

I_E_PRE        = 400.0  # pA — drives pre population to fire
I_E_POST       = 400.0  # pA — drives post population to fire
POISSON_RATE   = 20.0   # Hz — independent Poisson input to each pre neuron
POISSON_RATE_POST = 5.0 # Hz — weaker independent Poisson to each post neuron

print("=" * 70)
print(f"STDP TWO POPULATIONS: {N_PRE} pre x {N_POST} post = {N_SYN} synapses")
print("=" * 70)

# ---------------------------------------------------------------------------
# NEST simulation
# ---------------------------------------------------------------------------

nest.ResetKernel()
nest.resolution = RESOLUTION

pre_pop  = nest.Create("iaf_psc_alpha", N_PRE,  params={"I_e": I_E_PRE})
post_pop = nest.Create("iaf_psc_alpha", N_POST, params={"I_e": I_E_POST})

# Independent Poisson generators for each pre neuron (one-to-one)
pg_pre = nest.Create("poisson_generator", N_PRE, params={"rate": POISSON_RATE})
nest.Connect(pg_pre, pre_pop, conn_spec={"rule": "one_to_one"}, syn_spec={"weight": 50.0})

# Weaker independent Poisson for each post neuron
pg_post = nest.Create("poisson_generator", N_POST, params={"rate": POISSON_RATE_POST})
nest.Connect(pg_post, post_pop, conn_spec={"rule": "one_to_one"}, syn_spec={"weight": 50.0})

nest.Connect(pre_pop, post_pop, conn_spec={"rule": "all_to_all"}, syn_spec={
    "synapse_model": "stdp_synapse",
    "weight": W_INIT,
    "Wmax": WMAX,
    "lambda": LAMBDA,
    "alpha": ALPHA,
    "tau_plus": TAU_PLUS,
    "mu_plus": 0.0,
    "mu_minus": 0.0,
    "delay": DELAY,
})

sr_pre  = nest.Create("spike_recorder")
sr_post = nest.Create("spike_recorder")
nest.Connect(pre_pop,  sr_pre)
nest.Connect(post_pop, sr_post)

conns = nest.GetConnections(pre_pop, post_pop)

n_samples  = int(DURATION / SAMPLE_INTERVAL)
nest_times = []
nest_weights = []  # shape: (n_samples, N_SYN)

print(f"\nRunning {DURATION}ms NEST simulation ({n_samples} weight samples)...")
for i in range(n_samples):
    nest.Simulate(SAMPLE_INTERVAL)
    t = (i + 1) * SAMPLE_INTERVAL
    nest_times.append(t)
    nest_weights.append(nest.GetStatus(conns, "weight"))

events_pre  = nest.GetStatus(sr_pre,  "events")[0]
events_post = nest.GetStatus(sr_post, "events")[0]

spike_times_pre  = events_pre["times"]
spike_senders_pre = events_pre["senders"] - pre_pop[0].get('global_id')

spike_times_post  = events_post["times"]
spike_senders_post = events_post["senders"] - post_pop[0].get('global_id')

print(f"Pre  spikes: {len(spike_times_pre)}")
print(f"Post spikes: {len(spike_times_post)}")

# ---------------------------------------------------------------------------
# Python reimplementation — replay NEST spikes
# ---------------------------------------------------------------------------

# One ArchivingNode per neuron
pre_nodes  = [ArchivingNode(tau_minus=TAU_MINUS) for _ in range(N_PRE)]
post_nodes = [ArchivingNode(tau_minus=TAU_MINUS) for _ in range(N_POST)]

# 2500 STDPSynapse objects: synapses[i][j] = pre_i -> post_j
synapses = [[STDPSynapse(weight=W_INIT, Wmax=WMAX, tau_plus=TAU_PLUS,
                         lambd=LAMBDA, alpha=ALPHA, delay=DELAY)
             for j in range(N_POST)]
            for i in range(N_PRE)]

# Merge and sort all spikes by time
all_spikes = []
for t, nid in zip(spike_times_pre, spike_senders_pre):
    all_spikes.append((t, int(nid), 'pre'))
for t, nid in zip(spike_times_post, spike_senders_post):
    all_spikes.append((t, int(nid), 'post'))
all_spikes.sort(key=lambda x: x[0])

our_times   = []
our_weights = []  # shape: (n_samples, N_SYN)

spike_idx = 0
n_total = len(all_spikes)

print("\nRunning Python reimplementation...")
for sample_idx in range(n_samples):
    target_time = (sample_idx + 1) * SAMPLE_INTERVAL

    while spike_idx < n_total and all_spikes[spike_idx][0] <= target_time:
        t_spike, nid, pop = all_spikes[spike_idx]

        if pop == 'pre':
            pre_nodes[nid].set_spiketime(t_spike)
            for j in range(N_POST):
                synapses[nid][j].send(t_spike, post_nodes[j])
        else:
            post_nodes[nid].set_spiketime(t_spike)
            # Post spike does NOT trigger send() — STDP is pre-synaptic in NEST stdp_synapse

        spike_idx += 1

    our_times.append(target_time)
    our_weights.append([synapses[i][j].weight for i in range(N_PRE) for j in range(N_POST)])

# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------

nest_w = np.array(nest_weights)   # (n_samples, N_SYN)
our_w  = np.array(our_weights)    # (n_samples, N_SYN)

errors = np.abs(nest_w - our_w)   # (n_samples, N_SYN)

mean_error_over_time = errors.mean(axis=1)   # mean over synapses at each time step
max_error_over_time  = errors.max(axis=1)

final_error_per_syn  = errors[-1]
final_mean_error     = final_error_per_syn.mean()
final_max_error      = final_error_per_syn.max()

nest_final_mean_w = nest_w[-1].mean()
avg_pct_error = (final_mean_error / nest_final_mean_w) * 100 if nest_final_mean_w > 0 else 0

print(f"\nFinal Results:")
print(f"  NEST mean weight: {nest_final_mean_w:.6f}")
print(f"  Our  mean weight: {our_w[-1].mean():.6f}")
print(f"  Mean abs error (final): {final_mean_error:.6f} ({avg_pct_error:.2f}%)")
print(f"  Max  abs error (final): {final_max_error:.6f}")
print(f"  Max  abs error (any time): {errors.max():.6f}")

# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

fig, axes = plt.subplots(3, 1, figsize=(14, 11))

# --- Weight distribution over time ---
ax = axes[0]
ax.plot(nest_times, nest_w.mean(axis=1), 'b-', linewidth=2, label='NEST mean weight')
ax.fill_between(nest_times,
                nest_w.mean(axis=1) - nest_w.std(axis=1),
                nest_w.mean(axis=1) + nest_w.std(axis=1),
                alpha=0.2, color='blue', label='NEST ±1 std')
ax.plot(our_times, our_w.mean(axis=1), 'r--', linewidth=2, label='Python mean weight')
ax.set_ylabel('Weight', fontsize=12)
ax.set_title(f'Mean synaptic weight over time ({N_SYN} synapses)', fontsize=13)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
ax.set_xlim([0, DURATION])

# --- Final weight distribution ---
ax = axes[1]
ax.hist(nest_w[-1], bins=40, alpha=0.6, color='blue', label=f'NEST (mean={nest_w[-1].mean():.3f})')
ax.hist(our_w[-1],  bins=40, alpha=0.6, color='red',  label=f'Python (mean={our_w[-1].mean():.3f})')
ax.set_xlabel('Weight', fontsize=12)
ax.set_ylabel('Count', fontsize=12)
ax.set_title('Final weight distribution', fontsize=13)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)

# --- Error over time ---
ax = axes[2]
ax.plot(nest_times, mean_error_over_time, 'green', linewidth=2,
        label=f'Mean error (final: {final_mean_error:.6f})')
ax.plot(nest_times, max_error_over_time,  'orange', linewidth=2,
        label=f'Max error  (final: {final_max_error:.6f})')
ax.fill_between(nest_times, 0, mean_error_over_time, alpha=0.2, color='green')
ax.set_xlabel('Time (ms)', fontsize=12)
ax.set_ylabel('Absolute Error', fontsize=12)
ax.set_title(f'NEST vs Python error over time (avg: {avg_pct_error:.2f}%)', fontsize=13)
ax.legend(fontsize=10)
ax.grid(True, alpha=0.3)
ax.set_xlim([0, DURATION])

plt.suptitle(
    f'STDP Two Populations: {N_PRE} pre x {N_POST} post ({N_SYN} synapses)\n'
    f'{len(spike_times_pre)} pre spikes, {len(spike_times_post)} post spikes',
    fontsize=14, fontweight='bold'
)
plt.tight_layout()
plt.savefig('two_populations_result.png', dpi=150, bbox_inches='tight')
print("\nVisualization saved: two_populations_result.png")

print(f"\n{'='*70}")
print("STATISTICS")
print(f"{'='*70}")
print(f"Mean error over time: {mean_error_over_time.mean():.6f}")
print(f"Max  error over all:  {errors.max():.6f}")

if avg_pct_error < 0.5:
    print(f"\nEXCELLENT: Error < 0.5% — Near-perfect match!")
elif avg_pct_error < 1.0:
    print(f"\nGREAT: Error < 1%")
elif avg_pct_error < 2.0:
    print(f"\nGOOD: Error < 2%")
else:
    print(f"\nWARNING: Error {avg_pct_error:.2f}% — needs investigation")

# ---------------------------------------------------------------------------
# Export data for FPGA replay and comparison
# ---------------------------------------------------------------------------

# Spike data: all pre and post spikes, times in ms and neuron IDs (0-indexed)
spike_data = {
    "pre_times":  spike_times_pre,           # ms, float64
    "pre_ids":    spike_senders_pre,          # 0-indexed int
    "post_times": spike_times_post,           # ms, float64
    "post_ids":   spike_senders_post,         # 0-indexed int
}
np.save("spike_data.npy", spike_data)

# NEST final weight matrix: shape (N_PRE, N_POST), float64
# NEST returns weights ordered by connection: conns[i*N_POST + j] = pre_i -> post_j
nest_final_w = np.array(nest_weights[-1], dtype=np.float64).reshape(N_PRE, N_POST)
np.save("nest_final_weights.npy", nest_final_w)

# Weight evolution: shape (n_samples, N_PRE, N_POST) — useful for time-series plots
nest_weight_evolution = np.array(nest_weights, dtype=np.float64).reshape(n_samples, N_PRE, N_POST)
np.save("nest_weight_evolution.npy", nest_weight_evolution)

print(f"\nSaved for FPGA replay:")
print(f"  spike_data.npy            — {len(spike_times_pre)} pre + {len(spike_times_post)} post spikes")
print(f"  nest_final_weights.npy    — shape {nest_final_w.shape}, mean={nest_final_w.mean():.4f}")
print(f"  nest_weight_evolution.npy — shape {nest_weight_evolution.shape}")
