# =============================================================================
# create_hls_project.tcl — Automates Vitis HLS project creation
# =============================================================================
# Usage (from fpga_stdp/ directory):
#   vitis_hls -f scripts/create_hls_project.tcl
# or for Vivado HLS 2019.x:
#   vivado_hls -f scripts/create_hls_project.tcl
# =============================================================================

# Path to fpga_stdp/ directory (adjust if running from elsewhere)
set ROOT [file dirname [file normalize [info script]]]/..

open_project -reset stdp_hls

set_top stdp_top

add_files      $ROOT/hls/stdp_top.h
add_files      $ROOT/hls/stdp_top.cpp
add_files -tb  $ROOT/hls/testbench.cpp

open_solution -reset solution1

# Target device: Pynq-Z2 (xc7z020clg400-1), 100 MHz clock
set_part xc7z020clg400-1
create_clock -period 10 -name default

# C simulation: Vitis HLS 2023.1 ships with old binutils (2.37) that cannot
# link against Arch Linux's newer glibc (RELR section type 0x13).
# C-sim correctness has been verified with the system GCC instead:
#   g++ -std=c++14 -I<vitis_hls>/include hls/testbench.cpp hls/stdp_top.cpp -o csim && ./csim
# Uncomment the next line if running on a compatible distro (Ubuntu 20/22):
# csim_design

# Run C synthesis (generates RTL, check timing report)
csynth_design

# Optional: run co-simulation (verifies RTL matches C — takes longer)
# cosim_design -tool xsim

# Export RTL as a Vivado IP package (.zip)
export_design -format ip_catalog -description "STDP weight-update accelerator" \
              -vendor "user" -library "hls" -version "1.0"

puts "==================================================================="
puts "HLS flow complete."
puts "IP export: stdp_hls/solution1/impl/export.zip"
puts "Add this IP repository to Vivado to create the block design."
puts "==================================================================="
