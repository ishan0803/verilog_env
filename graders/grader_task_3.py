"""Task 3 Grader — Memory Controller Power Optimization (Hard)."""

import os
import re
import subprocess
from typing import Any, Dict, List, Tuple

from .grader_base import BaseGrader


class Task3Grader(BaseGrader):
    """Grader for Task 3: Memory controller power optimization.

    Timing closure at 5ns clock.
    HIDDEN constraint: read latency must be <= 3 clock cycles.
    Power improvement is the primary PPA metric.
    """

    CLOCK_PERIOD_NS = 5.0
    MAX_READ_LATENCY_CYCLES = 3

    def _evaluate_timing_closure(
        self, submission_dir: str
    ) -> Tuple[float, Dict[str, Any]]:
        """Evaluate timing closure at 5ns clock + hidden latency constraint."""
        details = {}
        rtl_files = self._find_rtl_files(submission_dir)

        if not rtl_files:
            return 0.0, {"error": "No RTL files"}

        num_cells, area = self._run_synthesis(rtl_files)
        details["num_cells"] = num_cells

        if num_cells == 0:
            return 0.0, {"error": "Synthesis produced no cells"}

        # Timing check
        import math
        estimated_depth = math.sqrt(num_cells) * 0.8
        avg_delay = 0.05  # ns
        critical_path_delay = estimated_depth * avg_delay

        wns = self.CLOCK_PERIOD_NS - critical_path_delay
        timing_met = wns >= 0.0
        details["wns"] = round(wns, 3)
        details["timing_met"] = timing_met

        if not timing_met:
            return 0.0, details

        # Hidden latency constraint check via simulation
        latency_ok = self._check_read_latency(rtl_files)
        details["latency_constraint_met"] = latency_ok

        if not latency_ok:
            details["violation"] = (
                f"Read latency exceeds {self.MAX_READ_LATENCY_CYCLES} cycles"
            )
            return 0.0, details

        return 1.0, details

    def _check_read_latency(self, rtl_files: List[str]) -> bool:
        """Check that read latency <= MAX_READ_LATENCY_CYCLES.

        Runs the hidden testbench and checks for latency test result.
        """
        hidden_tbs = self._find_hidden_testbenches()
        for tb in hidden_tbs:
            _, _, output = self._run_testbench(rtl_files, tb)
            # Check for latency test
            match = re.search(
                r"read_latency_constraint\s+(PASSED|FAILED)", output, re.I
            )
            if match:
                return match.group(1).upper() == "PASSED"

        # If no explicit latency test, check FSM state count
        # Read operation: IDLE -> READ_1 -> READ_2 -> RESP = 3 cycles
        return True  # Default pass if test not found

    def _evaluate_ppa(
        self,
        submission_dir: str,
        baseline_metrics: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """Override PPA to weight power more heavily for Task 3."""
        from server.tool_wrappers.metrics import (
            DYNAMIC_POWER_PER_CELL,
            HIGH_POWER_CELLS,
            LEAKAGE_POWER_PER_CELL,
        )

        details = {}
        rtl_files = self._find_rtl_files(submission_dir)

        if not rtl_files:
            return 0.0, {"error": "No RTL files"}

        num_cells, area = self._run_synthesis(rtl_files)
        details["current_cells"] = num_cells

        # Estimate power (simplified)
        power = num_cells * (DYNAMIC_POWER_PER_CELL + LEAKAGE_POWER_PER_CELL)
        details["current_power_mw"] = round(power, 4)

        baseline_power = baseline_metrics.get("power", 0.0)
        if baseline_power <= 0:
            return 0.0, {"error": "No baseline power"}

        improvement = (baseline_power - power) / baseline_power
        details["improvement_pct"] = round(improvement * 100, 2)

        # Full score at 15% power improvement
        score = min(1.0, max(0.0, improvement / 0.15))
        return round(score, 4), details
