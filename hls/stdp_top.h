#pragma once
// =============================================================================
// stdp_top.h — Types, constants and top-function declaration
// STDP HLS kernel for Pynq-Z2 (xc7z020clg400-1)
// =============================================================================
// Fixed-point format: Q1.15 unsigned
//   weight_t : ap_ufixed<16,1>  range [0.0, 2.0),  1.0 = 0x8000
//   trace_t  : ap_ufixed<16,2>  range [0.0, 4.0),  1.0 = 0x4000
//   spktime_t: ap_uint<20>      spike time in 0.1 ms units, covers 104 s
//   lut_idx_t: ap_uint<11>      delta-t index into exp_lut[2048]
// =============================================================================

#include <ap_int.h>
#include <ap_fixed.h>

typedef ap_ufixed<16, 1> weight_t;   // Q1.15
typedef ap_ufixed<16, 2> trace_t;    // Q2.14 — traces can exceed 1.0
typedef ap_uint<20>      spktime_t;  // spike time in 0.1 ms units
typedef ap_uint<11>      lut_idx_t;  // index into exp_lut[2048]

// Network dimensions
#define N_PRE  50
#define N_POST 50
#define N_LUT  2048

// STDP parameters (Song, Miller & Abbott 2000, additive pair-based rule)
static const weight_t LAMBDA    = weight_t(0.01);
static const weight_t LAMBDA_A  = weight_t(0.012);   // lambda * alpha = 0.01 * 1.2
static const weight_t WMAX      = weight_t(1.0);
static const weight_t W_INIT    = weight_t(0.5);     // initial weight
static const trace_t  TRACE_ONE = trace_t(1.0);

// ---------------------------------------------------------------------------
// Operation modes (ap_uint<2> mode parameter)
// ---------------------------------------------------------------------------
//   MODE_SPIKE     = 0 : process one spike event (spike_type, neuron_id, spike_time)
//   MODE_READ_W    = 1 : read  W[rw_addr/N_POST][rw_addr%N_POST] → *read_data
//   MODE_WRITE_W   = 2 : write W[rw_addr/N_POST][rw_addr%N_POST] = write_data
//   MODE_INIT_ALL  = 3 : reset all weights to W_INIT, clear all traces & timestamps
#define MODE_SPIKE    0
#define MODE_READ_W   1
#define MODE_WRITE_W  2
#define MODE_INIT_ALL 3

// ---------------------------------------------------------------------------
// AXI-Lite top function
// ---------------------------------------------------------------------------
// mode         : operation (see MODE_* above)
// spike_type   : 0 = pre-spike,  1 = post-spike       (mode 0 only)
// neuron_id    : 0..49                                 (mode 0 only)
// spike_time   : time in 0.1 ms units (e.g. 100ms→1000) (mode 0 only)
// rw_addr      : weight index = pre*N_POST + post       (modes 1, 2)
// write_data   : weight value to write (Q1.15)          (mode 2 only)
// read_data    : weight value read back (Q1.15 float)   (mode 1 output)
// cycle_count  : FPGA cycles used by last spike event   (mode 0 output)
void stdp_top(
    ap_uint<2>   mode,
    ap_uint<1>   spike_type,
    ap_uint<6>   neuron_id,
    spktime_t    spike_time,
    ap_uint<12>  rw_addr,
    weight_t     write_data,
    weight_t    *read_data,
    ap_uint<32> *cycle_count
);
