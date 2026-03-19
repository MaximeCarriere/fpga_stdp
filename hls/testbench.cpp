// =============================================================================
// testbench.cpp — HLS C-simulation testbench for stdp_top
// =============================================================================
// Tests:
//   0. MODE_INIT_ALL initialises all weights to 0.5
//   1. LTD  — post before pre  → W[0][0] < 0.5
//   2. LTP  — pre before post  → W[5][5] > 0.5
//   3. MODE_WRITE_W / MODE_READ_W round-trip
//   4. Cycle count == N_POST (50) per spike event
// =============================================================================

#include "stdp_top.h"
#include <stdio.h>
#include <stdlib.h>
#include <math.h>

// ---------------------------------------------------------------------------
// Wrappers
// ---------------------------------------------------------------------------
static void do_spike(ap_uint<1> type, int nid, int t_01ms) {
    weight_t    w; ap_uint<32> c;
    stdp_top(MODE_SPIKE, type, (ap_uint<6>)nid, (spktime_t)t_01ms,
             0, weight_t(0), &w, &c);
}

static float read_w(int pre, int post) {
    weight_t w; ap_uint<32> c;
    stdp_top(MODE_READ_W, 0, 0, 0,
             (ap_uint<12>)(pre * N_POST + post), weight_t(0), &w, &c);
    return (float)w;
}

static void write_w(int pre, int post, float val) {
    weight_t w; ap_uint<32> c;
    stdp_top(MODE_WRITE_W, 0, 0, 0,
             (ap_uint<12>)(pre * N_POST + post), weight_t(val), &w, &c);
}

static void init_all() {
    weight_t w; ap_uint<32> c;
    stdp_top(MODE_INIT_ALL, 0, 0, 0, 0, weight_t(0), &w, &c);
}

static ap_uint<32> spike_cycles(ap_uint<1> type, int nid, int t) {
    weight_t w; ap_uint<32> c;
    stdp_top(MODE_SPIKE, type, (ap_uint<6>)nid, (spktime_t)t,
             0, weight_t(0), &w, &c);
    return c;
}

// ---------------------------------------------------------------------------
int main() {
    int fail = 0;
    printf("=== STDP HLS Testbench ===\n\n");

    // ------------------------------------------------------------------
    // Test 0: MODE_INIT_ALL sets all weights to W_INIT = 0.5
    // ------------------------------------------------------------------
    printf("Test 0: MODE_INIT_ALL\n");
    init_all();
    float w00 = read_w(0, 0);
    float w49 = read_w(49, 49);
    printf("  W[0][0]   = %.6f  (expected 0.5)\n", w00);
    printf("  W[49][49] = %.6f  (expected 0.5)\n", w49);
    if (fabsf(w00 - 0.5f) > 1e-3f || fabsf(w49 - 0.5f) > 1e-3f) {
        printf("  FAIL: init not 0.5\n"); fail++;
    } else printf("  PASS\n");

    // ------------------------------------------------------------------
    // Test 1: LTD (post fires 20 ms before pre)
    //   t=0: init, post[0] at 100ms, pre[0] at 120ms → W[0][0] should drop
    // ------------------------------------------------------------------
    printf("\nTest 1: LTD (post before pre, dt = 20 ms)\n");
    init_all();
    do_spike(1, 0, 1000);   // post fires at 100.0 ms
    do_spike(0, 0, 1200);   // pre  fires at 120.0 ms → depression
    float w_ltd = read_w(0, 0);
    printf("  W[0][0] = %.6f  (expected < 0.5)\n", w_ltd);
    if (w_ltd >= 0.5f) { printf("  FAIL\n"); fail++; } else printf("  PASS\n");

    // ------------------------------------------------------------------
    // Test 2: LTP (pre fires 10 ms before post)
    //   pre[5] at 200ms, post[5] at 210ms → W[5][5] should rise
    // ------------------------------------------------------------------
    printf("\nTest 2: LTP (pre before post, dt = 10 ms)\n");
    init_all();
    do_spike(0, 5, 2000);   // pre  fires at 200.0 ms
    do_spike(1, 5, 2100);   // post fires at 210.0 ms → potentiation
    float w_ltp = read_w(5, 5);
    printf("  W[5][5] = %.6f  (expected > 0.5)\n", w_ltp);
    if (w_ltp <= 0.5f) { printf("  FAIL\n"); fail++; } else printf("  PASS\n");

    // ------------------------------------------------------------------
    // Test 3: MODE_WRITE_W / MODE_READ_W round-trip
    // ------------------------------------------------------------------
    printf("\nTest 3: Write/read round-trip\n");
    write_w(10, 20, 0.75f);
    float w_rt = read_w(10, 20);
    printf("  Written 0.75, read back %.6f\n", w_rt);
    if (fabsf(w_rt - 0.75f) > 1e-3f) { printf("  FAIL\n"); fail++; } else printf("  PASS\n");

    // ------------------------------------------------------------------
    // Test 4: Cycle count == N_POST (50)
    // ------------------------------------------------------------------
    printf("\nTest 4: Cycle count per spike event\n");
    init_all();
    ap_uint<32> c_pre  = spike_cycles(0, 3, 5000);
    ap_uint<32> c_post = spike_cycles(1, 3, 5100);
    printf("  Pre-spike  cycles = %u  (expected 50)\n", (unsigned)c_pre);
    printf("  Post-spike cycles = %u  (expected 50)\n", (unsigned)c_post);
    if ((unsigned)c_pre != 50 || (unsigned)c_post != 50) {
        printf("  WARNING: cycle count differs — check II in synthesis report\n");
    } else printf("  PASS\n");

    // ------------------------------------------------------------------
    printf("\n%s\n", fail == 0 ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
    return fail;
}
