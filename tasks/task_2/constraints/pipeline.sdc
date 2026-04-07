# Task 2 Pipeline Constraints — 4ns clock (250 MHz)
create_clock -period 4.0 [get_ports clk]
set_max_fanout 16 [current_design]
set_max_transition 0.4 [current_design]
