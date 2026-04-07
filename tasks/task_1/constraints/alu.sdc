# Task 1 ALU Constraints (combinational — no clock needed)
# The ALU is purely combinational, so no clock constraint.
# Area optimization target: minimize total cell area.
set_max_fanout 16 [current_design]
set_max_transition 0.5 [current_design]
