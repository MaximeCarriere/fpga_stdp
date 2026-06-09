"""
generate_paper_figures.py — Generate publication-ready figures for ICANN 2026 paper.
Produces figures specifically for the merged benchmark + FPGA paper.
Run from any directory; paths are absolute.

Figures produced in icann2026_paper/:
  fig_benchmark_overview.png — 3-panel: overhead %, per-synapse zones, log-log timing
  fig_validation_CD.png      — panels C (scatter) + D (error dist) only
  fig_performance.png        — latency bar chart (NEST vs FPGA)
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import os

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = "/home/mc/Project/FPGA/NEST/STDP/Second"
OUT_DIR  = "/home/mc/Project/FPGA/NEST/STDP/Second/icann2026_paper"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Style (publication: clean, no grid on scatter, tight) ─────────────────────
plt.rcParams.update({
    'font.family':      'DejaVu Sans',
    'font.size':        11,
    'axes.titlesize':   12,
    'axes.labelsize':   11,
    'xtick.labelsize':  10,
    'ytick.labelsize':  10,
    'legend.fontsize':  9,
    'figure.dpi':       200,
    'axes.grid':        True,
    'grid.alpha':       0.25,
    'axes.spines.top':  False,
    'axes.spines.right':False,
})

# ── Benchmark colour palette (matches make_paper_figures.py) ──────────────────
BLUE   = '#2E86AB'
PURPLE = '#A23B72'
ORANGE = '#F18F01'
GREEN  = '#06A77D'
RED    = '#D62246'

# ─────────────────────────────────────────────────────────────────────────────
# Figure 0 — Benchmark overview: 3 panels
#   A  STDP overhead % vs network size   (fig3 panel A)
#   B  Per-synapse cost / memory zones   (fig3 panel B)
#   C  Log-log absolute timing comparison (fig2 panel B)
# ─────────────────────────────────────────────────────────────────────────────
BENCH_DIR = "/home/mc/Project/PhD/NEST/NEST_LR_Time/clean_comparison/processed_data"

overhead = pd.read_pickle(f"{BENCH_DIR}/stdp_overhead.pkl")
agg      = pd.read_pickle(f"{BENCH_DIR}/aggregated_trials.pkl")

fig, axes = plt.subplots(1, 3, figsize=(15, 4.4))
fig.subplots_adjust(wspace=0.38, left=0.06, right=0.97, top=0.88, bottom=0.15)

# ── Panel A: overhead % vs N ──────────────────────────────────────────────────
ax = axes[0]
sub = overhead[(overhead.n_cores == 1) & (overhead.firing_rate == 20.0)]
palette = [BLUE, ORANGE, RED]
lbl_map = ['p = 0.05  (sparse)', 'p = 0.10  (medium)', 'p = 0.20  (dense)']
for cp, color, lbl in zip(sorted(sub.conn_prob.unique()), palette, lbl_map):
    d = (sub[sub.conn_prob == cp]
         .groupby('n_neurons')['overhead_pct']
         .agg(['mean', 'sem']).reset_index())
    ax.errorbar(d.n_neurons, d['mean'], yerr=d['sem'],
                marker='o', linewidth=2, color=color,
                label=lbl, capsize=3, zorder=3)
y_top = max(sub['overhead_pct'].dropna().max() * 1.08, 110)
for yval, ls, lbl in [(50, '--', '50 %'), (100, ':', '100 %')]:
    if yval < y_top:
        ax.axhline(yval, color='#bbbbbb', linestyle=ls, linewidth=0.9, zorder=1)
        ax.text(0.98, yval, lbl, fontsize=8, color='#888888',
                va='bottom', ha='right', transform=ax.get_yaxis_transform())
ax.set_xscale('log')
ax.set_ylim(-5, y_top)
ax.set_xlabel('Number of neurons', fontsize=10)
ax.set_ylabel('STDP overhead (%)', fontsize=10)
ax.set_title('(A)  STDP overhead vs. network size\n(1 core, 20 Hz)',
             loc='left', fontweight='bold', fontsize=9.5)
ax.legend(title='Connection prob.', frameon=False, fontsize=8,
          title_fontsize=8, loc='upper left')
ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)

# ── Panel B: per-synapse cost / memory zones ──────────────────────────────────
ax2 = axes[1]
sub2 = (overhead[(overhead.n_cores == 1) & (overhead.firing_rate == 20.0)
                 & (overhead.conn_prob == 0.1)]
        .groupby('n_neurons')
        .agg(T_overhead_mean=('T_overhead', 'mean'),
             n_connections_mean=('n_connections', 'mean'))
        .reset_index())
sub2 = sub2[sub2.n_connections_mean > 0].copy()
sub2['us_per_conn'] = sub2.T_overhead_mean / sub2.n_connections_mean * 1e6

bands = [
    (8,   80,  '#dde0ff', '1  Fixed call\noverhead', '#3344bb'),
    (80,  800, '#d4f0da', '2  In cache\n(fast)',     '#226633'),
    (800, 2e5, '#ffe0e0', '3  Cache miss\n(slow)',   '#cc3333'),
]
for x0, x1, fc, lbl, tc in bands:
    ax2.axvspan(x0, x1, color=fc, alpha=0.60, zorder=0, linewidth=0)
ax2.plot(sub2.n_neurons, sub2.us_per_conn,
         marker='D', linewidth=2.2, color=PURPLE, zorder=4)
zone2 = sub2[sub2.n_neurons.between(80, 800)]['us_per_conn']
baseline = zone2.min() if len(zone2) > 0 else sub2['us_per_conn'].min()
ax2.axhline(baseline, color='#999999', linestyle='--', linewidth=1.0, zorder=2)
ax2.text(0.02, baseline, f'Cache-friendly: {baseline:.0f} µs/syn',
         fontsize=7, color='#777777', va='bottom',
         transform=ax2.get_yaxis_transform())
ax2.axvline(800, color='#cc3333', linestyle=':', linewidth=1.2, zorder=2)
y_min = sub2['us_per_conn'].min(); y_max = sub2['us_per_conn'].max()
label_positions = [
    (np.sqrt(8   * 80),  y_max, 'bottom'),
    (np.sqrt(80  * 800), y_min, 'top'),
    (np.sqrt(800 * 3e4), y_max, 'bottom'),
]
for (x0, x1, fc, lbl, tc), (xm, ym, va) in zip(bands, label_positions):
    ax2.text(xm, ym, lbl, ha='center', va=va, fontsize=8, color=tc,
             fontweight='bold',
             bbox=dict(boxstyle='round,pad=0.2', fc='white',
                       ec=tc, alpha=0.85, linewidth=0.8))
ax2.set_xscale('log')
margin = (y_max - y_min) * 0.25
ax2.set_ylim(y_min - margin, y_max + margin)
ax2.set_xlabel('Number of neurons', fontsize=10)
ax2.set_ylabel('STDP cost per synapse (µs)', fontsize=10)
ax2.set_title('(B)  Cost per synapse  (p = 0.1, 1 core, 20 Hz)',
              loc='left', fontweight='bold', fontsize=9.5)
ax2.spines['top'].set_visible(False); ax2.spines['right'].set_visible(False)

# ── Panel C: overhead gap persists across core counts (fig4 panel B) ──────────
ax3 = axes[2]
scaling = pd.read_pickle(f"{BENCH_DIR}/core_scaling.pkl")
cores   = [1, 2, 4, 8]
size    = 4000
data_pairs = {}
for rule, color, label in [('static', BLUE, 'Static synapse'),
                            ('stdp',   PURPLE, 'STDP synapse')]:
    d = (scaling[(scaling.learning_rule == rule) &
                 (scaling.n_neurons == size) &
                 (scaling.conn_prob == 0.1) &
                 (scaling.firing_rate == 20.0)]
         .sort_values('n_cores'))
    if len(d) == 0:
        continue
    data_pairs[rule] = d
    ax3.errorbar(d.n_cores, d.T_simulate, yerr=d.T_simulate_sem,
                 marker='o', linewidth=2, color=color, label=label, capsize=3)
    t1 = d[d.n_cores == 1]['T_simulate'].values[0]
    ax3.plot([1, 2, 4, 8], [t1, t1/2, t1/4, t1/8],
             '--', color=color, linewidth=1, alpha=0.35)

ax3.set_yscale('log')
ax3.set_xticks(cores)
ax3.set_xlabel('Number of CPU cores', fontsize=10)
ax3.set_ylabel('Wall-clock time (s)', fontsize=10)
ax3.set_title(f'(C)  Overhead gap persists  (N={size:,}, p=0.1, 20 Hz)',
              loc='left', fontweight='bold', fontsize=9.5)
ax3.legend(frameon=False, fontsize=8, loc='upper right')
ax3.text(0.03, 0.04, 'Dashed = ideal linear scaling\nfrom 1-core baseline',
         transform=ax3.transAxes, fontsize=6.5, color='#666666', va='bottom')

# Annotate persistent gap at 8 cores
if 'static' in data_pairs and 'stdp' in data_pairs:
    t_s8 = data_pairs['static'][data_pairs['static'].n_cores == 8]['T_simulate'].values[0]
    t_d8 = data_pairs['stdp'][data_pairs['stdp'].n_cores == 8]['T_simulate'].values[0]
    ratio = t_d8 / t_s8
    ax3.annotate('', xy=(8.3, t_d8), xytext=(8.3, t_s8),
                 arrowprops=dict(arrowstyle='<->', color='black', lw=1.0))
    ax3.text(8.5, (t_s8 * t_d8) ** 0.5,
             f'{ratio:.1f}×\noverhead',
             fontsize=7.5, va='center', ha='left', color='black', fontweight='bold')
ax3.spines['top'].set_visible(False); ax3.spines['right'].set_visible(False)

out = f"{OUT_DIR}/fig_benchmark_overview.png"
fig.savefig(out, bbox_inches='tight')
plt.close()
print(f"✓ fig_benchmark_overview.png  →  {out}")

# ── Load FPGA data ─────────────────────────────────────────────────────────────
nest_w   = np.load(f"{DATA_DIR}/nest_final_weights.npy")
fpga_w   = np.load(f"{DATA_DIR}/fpga_final_weights.npy")
python_w = np.load(f"{DATA_DIR}/python_online_weights.npy")

err    = np.abs(fpga_w - nest_w.astype(np.float32))
err_py = np.abs(fpga_w - python_w.astype(np.float32))

mae_nest = err.mean()
mae_py   = err_py.mean()

# ─────────────────────────────────────────────────────────────────────────────
# Figure 1 — Validation: panels C + D only (1 row × 2 cols)
# ─────────────────────────────────────────────────────────────────────────────
fig, (ax_c, ax_d) = plt.subplots(1, 2, figsize=(11, 4.5))
fig.subplots_adjust(wspace=0.35)

# Panel C — scatter FPGA vs NEST
ax_c.scatter(nest_w.flatten(), fpga_w.flatten(),
             s=1.5, alpha=0.35, c='mediumpurple', rasterized=True)
ax_c.plot([0, 1], [0, 1], 'r--', lw=1.5, label='Ideal (y = x)')
ax_c.set_xlabel("NEST weight")
ax_c.set_ylabel("FPGA weight")
ax_c.set_title(f"(A) FPGA vs. NEST  (MAE = {mae_nest:.2e})")
ax_c.legend(fontsize=9)
ax_c.set_xlim(0, 1)
ax_c.set_ylim(0, 1)
ax_c.set_aspect('equal')
ax_c.grid(True, alpha=0.2)

# Panel D — error distributions
ax_d.hist(err.flatten(),    bins=80, density=True, alpha=0.65,
          color='steelblue', label=f'FPGA vs. NEST  (MAE={mae_nest:.2e})')
ax_d.hist(err_py.flatten(), bins=80, density=True, alpha=0.60,
          color='tomato',    label=f'FPGA vs. Python online  (MAE={mae_py:.2e})')
ax_d.axvline(1/32768, color='k', linestyle=':', lw=1.5, label='Q1.15 step (3×10⁻⁵)')
ax_d.set_xlabel("Absolute error")
ax_d.set_ylabel("Density")
ax_d.set_title("(B) Error Distributions")
ax_d.legend(fontsize=8.5)
ax_d.set_yscale('log')

out = f"{OUT_DIR}/fig_validation_CD.png"
fig.savefig(out, bbox_inches='tight')
plt.close()
print(f"✓ fig_validation_CD.png  →  {out}")

# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 — Performance: latency bar chart (NEST vs FPGA only)
# Python online omitted from performance chart — slower than NEST and not
# the relevant baseline for hardware comparison.
# ─────────────────────────────────────────────────────────────────────────────
N_EVENTS = 35309

# Measured values in ns per event
latencies = {
    'NEST 3.6\nbaseline':       3_000.0,    # 3 µs/spike (measured)
    'FPGA\n(compute only)':       500.0,    # 500 ns/event (50 cycles @ 100 MHz)
    'FPGA\n(end-to-end\nw/ AXI)': 159_000.0, # 159 µs/event (AXI-Lite bottleneck)
}

labels  = list(latencies.keys())
values  = [latencies[k] for k in labels]
colors  = ['#1b7837', '#2166ac', '#92c5de']
hatches = ['', '', '//']

fig, ax = plt.subplots(figsize=(7, 4.5))

bars = ax.bar(labels, values, color=colors, hatch=hatches,
              edgecolor='white', width=0.5)

# Annotate bars with human-readable values
def fmt_ns(val):
    if val >= 1_000_000:
        return f"{val/1_000_000:.0f} ms"
    elif val >= 1_000:
        return f"{val/1_000:.0f} µs"
    else:
        return f"{val:.0f} ns"

for bar, val in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() * 1.25,
            fmt_ns(val), ha='center', va='bottom', fontsize=10, fontweight='bold')

ax.set_yscale('log')
ax.set_ylabel("Per-spike latency (ns, log scale)")
ax.set_title("Per-Spike Latency: NEST vs. FPGA")
ax.set_ylim(100, max(values) * 8)
ax.yaxis.grid(True, alpha=0.3)
ax.set_axisbelow(True)

# Annotation: 6× speedup (NEST vs FPGA compute)
ax.annotate('',
    xy=(1, 500), xytext=(0, 3000),
    arrowprops=dict(arrowstyle='<->', color='black', lw=1.2))
ax.text(0.55, 1200, '6×', fontsize=11, color='black', ha='center', fontweight='bold')

out = f"{OUT_DIR}/fig_performance.png"
fig.savefig(out, bbox_inches='tight')
plt.close()
print(f"✓ fig_performance.png    →  {out}")

print("\nAll paper figures written to:", OUT_DIR)
