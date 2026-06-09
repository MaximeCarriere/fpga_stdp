# FPGA STDP Accelerator

Code and data for the ICANN 2026 paper:

> **From NEST Benchmark to FPGA Silicon: Quantifying the Cost of STDP and Demonstrating Efficient Kernel Offloading**  
> Maxime Carrière, Freie Universität Berlin (2026)

---

## Repository structure

```
fpga_stdp/
├── hls/                         # Vitis HLS kernel source
│   ├── stdp_top.h               # Types and top-function declaration
│   ├── stdp_top.cpp             # HLS kernel (online STDP)
│   ├── testbench.cpp            # C-simulation testbench
│   └── exp_lut_init.h           # 2048-entry Q1.15 exponential LUT (generated)
├── scripts/
│   ├── stdp_two_populations.py  # NEST benchmark simulation (Fig. 1)
│   ├── fpga_nest_compare.py     # FPGA replay + accuracy validation (Fig. 2–3)
│   ├── pynq_test.py             # On-board throughput benchmark (Pynq-Z2)
│   ├── gen_exp_lut.py           # Regenerate exp_lut_init.h and exp_lut.coe
│   ├── export_spike_data.py     # Snippet: export spike_data.npy from NEST sim
│   ├── create_hls_project.tcl   # Automate Vitis HLS project creation
│   └── create_vivado_project.tcl
├── figures/
│   └── generate_paper_figures.py  # Reproduce all paper figures from data/
├── data/                        # Pre-computed validation data
│   ├── spike_data.npy           # 10-s NEST spike train (35,309 events)
│   ├── nest_final_weights.npy   # NEST final weight matrix (2,500 synapses)
│   ├── fpga_final_weights.npy   # FPGA final weight matrix
│   ├── python_online_weights.npy # Python online reference weights
│   └── nest_weight_evolution.npy # Weight evolution sampled every 0.1 s
├── deploy/
│   ├── stdp_system_wrapper.bit  # Pre-built bitstream (Xilinx XC7Z020, 100 MHz)
│   └── stdp_system_wrapper.hwh  # Hardware handoff file for PYNQ
├── exp_lut.coe                  # BRAM initialisation file for Vivado IP
├── constraints/
│   └── pynqz2.xdc               # Pin constraints for Pynq-Z2
├── stdp_hls/                    # Vitis HLS project metadata
└── vivado_stdp/
    └── stdp_system.xpr          # Vivado block design project file
```

---

## Hardware

- **Board**: Digilent Pynq-Z2 (Xilinx Zynq XC7Z020clg400-1)
- **Clock**: 100 MHz
- **Toolchain**: Vitis HLS 2023.1, Vivado 2023.1, PYNQ 3.x

---

## Quick start

### 1. Run the CPU benchmark (requires NEST 3.6)

```bash
cd scripts
python stdp_two_populations.py   # runs NEST sim, saves spike_data.npy + weights
```

### 2. Synthesise the HLS kernel

```bash
cd scripts
vitis_hls create_hls_project.tcl   # creates and runs C-sim + synthesis
```

Or open Vitis HLS and import `hls/stdp_top.cpp` with `hls/stdp_top.h`.

### 3. Build the Vivado bitstream

Open `vivado_stdp/stdp_system.xpr` in Vivado 2023.1 and run Implementation → Generate Bitstream.  
A pre-built bitstream is in `deploy/` for the XC7Z020 at 100 MHz.

### 4. Run on Pynq-Z2

Copy `deploy/stdp_system_wrapper.bit`, `deploy/stdp_system_wrapper.hwh`, `data/spike_data.npy`, and `scripts/fpga_nest_compare.py` to the board, then:

```bash
# on the Pynq-Z2:
export XILINX_XRT=/usr
echo xilinx | sudo -S -E /usr/local/share/pynq-venv/bin/python3 fpga_nest_compare.py
```

### 5. Reproduce paper figures

```bash
cd figures
python generate_paper_figures.py   # reads ../data/, writes fig_*.png
```

---

## Results (measured on hardware)

| Metric | Value |
|---|---|
| Compute latency | 500 ns / spike event |
| Throughput | 100 M syn/s (2,500-synapse network) |
| End-to-end latency (AXI-Lite) | 159 µs / spike |
| Board power | 1.73 W |
| LUT utilisation | 11.3 % (5,995 / 53,200) |
| BRAM utilisation | 17.9 % (27 / 140 tiles) |
| Timing (WNS) | +0.495 ns at 100 MHz |
| FPGA vs Python MAE | 1.91 × 10⁻³ (quantisation only) |
| FPGA vs NEST MAE | 1.10 × 10⁻² (update-timing semantics) |

---

## Fixed-point format

| Signal | Format | Range | Resolution |
|---|---|---|---|
| Weights | Q1.15 | [0, 2) | 3.05 × 10⁻⁵ |
| Traces | Q2.14 | [0, 4) | 6.10 × 10⁻⁵ |

---

## Dependencies

- Python ≥ 3.10, NumPy, Matplotlib
- [NEST Simulator 3.6](https://nest-simulator.org) (for `stdp_two_populations.py`)
- [PYNQ 3.x](https://pynq.io) (on-board scripts only)
- Vitis HLS 2023.1 / Vivado 2023.1 (synthesis only)

---

## Citation

```bibtex
@inproceedings{carriere2026stdp,
  author    = {Carri{\`e}re, Maxime},
  title     = {From {NEST} Benchmark to {FPGA} Silicon: Quantifying the
               Cost of {STDP} and Demonstrating Efficient Kernel Offloading},
  booktitle = {Proceedings of the International Conference on Artificial
               Neural Networks (ICANN)},
  series    = {LNCS},
  publisher = {Springer},
  year      = {2026}
}
```

---

## License

MIT License — see `LICENSE` for details.
