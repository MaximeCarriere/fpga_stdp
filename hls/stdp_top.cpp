// =============================================================================
// stdp_top.cpp — HLS kernel for STDP weight updates
// =============================================================================
// Online pair-based additive STDP (Song, Miller & Abbott 2000):
//   Pre-spike from i   → Depress  W[i][j] ∀j (K_minus[j] decayed) → K_plus[i]++
//   Post-spike from j  → Facilitate W[i][j] ∀i (K_plus[i] decayed) → K_minus[j]++
// Mathematically equivalent to NEST stdp_synapse.
// Performance: ~55 cycles/event at 100 MHz = ~550 ns pure compute.
// =============================================================================

#include "stdp_top.h"

// ---------------------------------------------------------------------------
// Persistent state (static → maps to registers/BRAM, survives between calls)
// HLS partition pragmas must live inside the top function body (not here).
// ---------------------------------------------------------------------------
static weight_t  weights[N_PRE][N_POST];
static trace_t   kplus[N_PRE];
static trace_t   kminus[N_POST];
static spktime_t t_lastspike_pre[N_PRE];
static spktime_t t_lastspike_post[N_POST];

// Exponential decay LUT: exp_lut[k] = exp(-k * 0.1 / 20.0), Q1.15 format
// Co-sim: initialised from header; synthesis: inferred as BRAM ROM.
static const weight_t exp_lut[N_LUT] = {
#include "exp_lut_init.h"
};

// ---------------------------------------------------------------------------
// Helper: look up exp(-dt / tau)
// ---------------------------------------------------------------------------
static inline weight_t exp_decay(spktime_t t_now, spktime_t t_last) {
#pragma HLS INLINE
    if (t_now <= t_last) return weight_t(1.0);
    spktime_t dt  = t_now - t_last;
    lut_idx_t idx = (dt < (spktime_t)N_LUT) ? lut_idx_t(dt) : lut_idx_t(N_LUT - 1);
    return exp_lut[idx];
}

// ---------------------------------------------------------------------------
// Top function
// ---------------------------------------------------------------------------
void stdp_top(
    ap_uint<2>   mode,
    ap_uint<1>   spike_type,
    ap_uint<6>   neuron_id,
    spktime_t    spike_time,
    ap_uint<12>  rw_addr,
    weight_t     write_data,
    weight_t    *read_data,
    ap_uint<32> *cycle_count
) {
    // AXI-Lite interface
#pragma HLS INTERFACE s_axilite port=mode        bundle=CTRL
#pragma HLS INTERFACE s_axilite port=spike_type  bundle=CTRL
#pragma HLS INTERFACE s_axilite port=neuron_id   bundle=CTRL
#pragma HLS INTERFACE s_axilite port=spike_time  bundle=CTRL
#pragma HLS INTERFACE s_axilite port=rw_addr     bundle=CTRL
#pragma HLS INTERFACE s_axilite port=write_data  bundle=CTRL
#pragma HLS INTERFACE s_axilite port=read_data   bundle=CTRL
#pragma HLS INTERFACE s_axilite port=cycle_count bundle=CTRL
#pragma HLS INTERFACE s_axilite port=return      bundle=CTRL

    // Memory layout — must be inside function scope in Vitis HLS 2023.x
    //
    // weights[50][50]: NO partition → dual-port BRAM (one read + one write per cycle).
    //   dep_loop (i fixed, j varies): sequential addresses i*50, i*50+1, … → II=1
    //   fac_loop (j fixed, i varies): stride-50 addresses, delayed write → II=1
    //
    // kplus, kminus, t_lastspike_*: complete → 50 registers each (4×50×16bit = 3200 bits).
    //   Mux-selects the required element each cycle; no BRAM latency.
#pragma HLS BIND_STORAGE     variable=weights         type=RAM_2P impl=BRAM
#pragma HLS ARRAY_PARTITION  variable=kplus            complete dim=1
#pragma HLS ARRAY_PARTITION  variable=kminus           complete dim=1
#pragma HLS ARRAY_PARTITION  variable=t_lastspike_pre  complete dim=1
#pragma HLS ARRAY_PARTITION  variable=t_lastspike_post complete dim=1
#pragma HLS RESOURCE         variable=exp_lut          core=ROM_1P_BRAM
#pragma HLS DEPENDENCE       variable=exp_lut          inter false

    *read_data   = weight_t(0);
    *cycle_count = 0;

    // ------------------------------------------------------------------
    // MODE 1 — Read weight
    // ------------------------------------------------------------------
    if (mode == MODE_READ_W) {
        ap_uint<6> pre  = rw_addr / (ap_uint<12>)N_POST;
        ap_uint<6> post = rw_addr % (ap_uint<12>)N_POST;
        *read_data = weights[pre][post];
        return;
    }

    // ------------------------------------------------------------------
    // MODE 2 — Write single weight
    // ------------------------------------------------------------------
    if (mode == MODE_WRITE_W) {
        ap_uint<6> pre  = rw_addr / (ap_uint<12>)N_POST;
        ap_uint<6> post = rw_addr % (ap_uint<12>)N_POST;
        weights[pre][post] = write_data;
        return;
    }

    // ------------------------------------------------------------------
    // MODE 3 — Initialise all weights to W_INIT, clear traces & timestamps
    // ------------------------------------------------------------------
    if (mode == MODE_INIT_ALL) {
        init_i: for (int i = 0; i < N_PRE; i++) {
#pragma HLS PIPELINE II=1
            kplus[i]           = trace_t(0);
            t_lastspike_pre[i] = spktime_t(0);
            init_j: for (int j = 0; j < N_POST; j++) {
                weights[i][j] = W_INIT;
            }
        }
        init_post: for (int j = 0; j < N_POST; j++) {
#pragma HLS PIPELINE II=1
            kminus[j]           = trace_t(0);
            t_lastspike_post[j] = spktime_t(0);
        }
        return;
    }

    // ------------------------------------------------------------------
    // MODE 0 — Process spike event
    // ------------------------------------------------------------------
    ap_uint<32> cycles = 0;

    if (spike_type == 0) {
        // ---- PRE-SPIKE from neuron i ----
        int i = (int)neuron_id;
        weight_t decay_kp   = exp_decay(spike_time, t_lastspike_pre[i]);
        trace_t  kp_decayed = kplus[i] * decay_kp;

        dep_loop: for (int j = 0; j < N_POST; j++) {
#pragma HLS PIPELINE II=1
            weight_t decay_km = exp_decay(spike_time, t_lastspike_post[j]);
            trace_t  km_now   = kminus[j] * decay_km;
            weight_t dw       = weight_t(LAMBDA_A * km_now);
            weight_t w        = weights[i][j];
            weights[i][j]     = (w > dw) ? weight_t(w - dw) : weight_t(0);
            cycles++;
        }

        kplus[i]           = kp_decayed + TRACE_ONE;
        t_lastspike_pre[i] = spike_time;

    } else {
        // ---- POST-SPIKE from neuron j ----
        int j = (int)neuron_id;
        weight_t decay_km   = exp_decay(spike_time, t_lastspike_post[j]);
        trace_t  km_decayed = kminus[j] * decay_km;

        fac_loop: for (int i = 0; i < N_PRE; i++) {
#pragma HLS PIPELINE II=1
            weight_t decay_kp = exp_decay(spike_time, t_lastspike_pre[i]);
            trace_t  kp_now   = kplus[i] * decay_kp;
            weight_t dw       = weight_t(LAMBDA * kp_now);
            weight_t w        = weight_t(weights[i][j] + dw);
            weights[i][j]     = (w < WMAX) ? w : WMAX;
            cycles++;
        }

        kminus[j]           = km_decayed + TRACE_ONE;
        t_lastspike_post[j] = spike_time;
    }

    *cycle_count = cycles;
}
