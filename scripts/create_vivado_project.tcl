# =============================================================================
# create_vivado_project.tcl — Creates Vivado block design and generates bitstream
# =============================================================================
# Usage (from fpga_stdp/ directory):
#   vivado -mode batch -source scripts/create_vivado_project.tcl
#
# Prerequisites:
#   HLS IP must already be exported at:
#     fpga_stdp/stdp_hls/solution1/impl/export.zip  (or unpacked)
# =============================================================================

set ROOT [file dirname [file normalize [info script]]]/..
set PROJ_DIR $ROOT/vivado_stdp

# Clean previous project
if {[file exists $PROJ_DIR]} {
    file delete -force $PROJ_DIR
}

# =============================================================================
# Create project
# =============================================================================
create_project stdp_system $PROJ_DIR -part xc7z020clg400-1

# Set Pynq-Z2 board if board files are installed
# (comment out if board files not available — it still works)
catch {set_property BOARD_PART tul.com.tw:pynq-z2:part0:1.0 [current_project]}

# =============================================================================
# Add HLS IP to repository
# =============================================================================
set hls_ip_dir $ROOT/stdp_hls/solution1/impl/ip
if {![file exists $hls_ip_dir]} {
    puts "ERROR: HLS IP not found at $hls_ip_dir"
    puts "Run Vitis HLS first: vitis_hls -f scripts/create_hls_project.tcl"
    exit 1
}
set_property IP_REPO_PATHS $hls_ip_dir [current_project]
update_ip_catalog

# =============================================================================
# Create block design
# =============================================================================
create_bd_design "stdp_system"

# --- Zynq PS ---
set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 processing_system7_0]
# Apply Pynq-Z2 preset if available, else set minimal config
catch {
    set_property CONFIG.preset {ZynqBerry} $ps7
}
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} \
    $ps7

# Enable GP0 master AXI port (for driving the STDP IP)
set_property CONFIG.PCW_USE_M_AXI_GP0 {1} $ps7
# Set FCLK0 = 100 MHz
set_property CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} $ps7

# --- Processor System Reset ---
set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset proc_sys_reset_0]

# --- AXI Interconnect ---
set axi_ic [create_bd_cell -type ip -vlnv xilinx.com:ip:axi_interconnect axi_interconnect_0]
set_property CONFIG.NUM_MI {1} $axi_ic

# --- STDP Top IP ---
set stdp [create_bd_cell -type ip -vlnv user:hls:stdp_top:1.0 stdp_top_0]

# =============================================================================
# Connections
# =============================================================================

# Clocks: FCLK_CLK0 → everything (M_AXI_GP0_ACLK must be driven explicitly)
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
               [get_bd_pins processing_system7_0/M_AXI_GP0_ACLK]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
               [get_bd_pins proc_sys_reset_0/slowest_sync_clk]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
               [get_bd_pins axi_interconnect_0/ACLK]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
               [get_bd_pins axi_interconnect_0/S00_ACLK]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
               [get_bd_pins axi_interconnect_0/M00_ACLK]
connect_bd_net [get_bd_pins processing_system7_0/FCLK_CLK0] \
               [get_bd_pins stdp_top_0/ap_clk]

# Resets: FCLK_RESET0_N → proc_sys_reset → peripheral_aresetn
connect_bd_net [get_bd_pins processing_system7_0/FCLK_RESET0_N] \
               [get_bd_pins proc_sys_reset_0/ext_reset_in]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] \
               [get_bd_pins axi_interconnect_0/ARESETN]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] \
               [get_bd_pins axi_interconnect_0/S00_ARESETN]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] \
               [get_bd_pins axi_interconnect_0/M00_ARESETN]
connect_bd_net [get_bd_pins proc_sys_reset_0/peripheral_aresetn] \
               [get_bd_pins stdp_top_0/ap_rst_n]

# AXI data path: PS M_AXI_GP0 → AXI Interconnect → stdp_top s_axi_CTRL
connect_bd_intf_net [get_bd_intf_pins processing_system7_0/M_AXI_GP0] \
                    [get_bd_intf_pins axi_interconnect_0/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_interconnect_0/M00_AXI] \
                    [get_bd_intf_pins stdp_top_0/s_axi_CTRL]

# External DDR and FIXED_IO pins
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/DDR]
make_bd_intf_pins_external [get_bd_intf_pins processing_system7_0/FIXED_IO]

# =============================================================================
# Assign address space
# =============================================================================
assign_bd_address

# Base address is auto-assigned (e.g. 0x43C00000).
# Pynq reads the exact address from the .hwh file — no manual override needed.

# =============================================================================
# Validate and save
# =============================================================================
validate_bd_design
save_bd_design

# Generate HDL wrapper (in Vivado 2023.1 it lands in .gen/, not .srcs/)
make_wrapper -files [get_files stdp_system.bd] -top
set wrapper [glob $PROJ_DIR/stdp_system.gen/sources_1/bd/stdp_system/hdl/stdp_system_wrapper.v]
add_files -norecurse $wrapper
set_property top stdp_system_wrapper [current_fileset]

# =============================================================================
# Run synthesis, implementation, and generate bitstream
# =============================================================================
puts "INFO: Starting synthesis …"
launch_runs synth_1 -jobs 4
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} {
    error "Synthesis failed"
}

puts "INFO: Starting implementation …"
launch_runs impl_1 -to_step write_bitstream -jobs 4
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} {
    error "Implementation failed"
}

# =============================================================================
# Copy output files for Pynq deployment
# =============================================================================
set impl_dir $PROJ_DIR/stdp_system.runs/impl_1
set deploy_dir $ROOT/deploy

file mkdir $deploy_dir
file copy -force $impl_dir/stdp_system_wrapper.bit $deploy_dir/
# Hardware handoff file (.hwh) — Pynq requires it to match the .bit filename
set hwh_src [glob $PROJ_DIR/stdp_system.gen/sources_1/bd/stdp_system/hw_handoff/stdp_system.hwh]
file copy -force $hwh_src $deploy_dir/stdp_system_wrapper.hwh

puts ""
puts "================================================================="
puts "BITSTREAM GENERATION COMPLETE"
puts "================================================================="
puts "Bitstream: $deploy_dir/stdp_system_wrapper.bit"
puts "HWH file:  $deploy_dir/stdp_system_wrapper.hwh"
puts ""
puts "Next: scp deploy/* user@pynq-z2:~/"
puts "      Also scp spike_data.npy nest_final_weights.npy scripts/pynq_test.py user@pynq-z2:~/"
puts "================================================================="

# Print resource utilisation summary
report_utilization -file $deploy_dir/utilization_report.txt
report_power       -file $deploy_dir/power_report.txt
puts "Reports saved to $deploy_dir/"
