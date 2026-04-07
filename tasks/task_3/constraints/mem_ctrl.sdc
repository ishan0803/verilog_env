# Task 3 Memory Controller Constraints — 5ns clock (200 MHz)
create_clock -period 5.0 [get_ports clk]
set_max_fanout 12 [current_design]
set_max_transition 0.3 [current_design]
# Hidden constraint: max read latency = 3 cycles (checked by grader, not visible here)
