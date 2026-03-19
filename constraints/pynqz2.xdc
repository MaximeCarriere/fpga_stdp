# pynqz2.xdc — Timing constraints for Pynq-Z2 STDP accelerator
#
# The Zynq PS provides all clocks via FCLK_CLK0 (100 MHz by default).
# No explicit clock constraints are needed for a pure PS-driven design.
# This file is a placeholder; add pin constraints here if external I/O is used.
#
# If the PS clock is reconfigured away from 100 MHz, add:
#   create_clock -period 10.000 -name clk_100 [get_ports clk]
