"""Task 2 Grader — Pipeline Retiming (Medium)."""

import os
import re
import subprocess
from typing import Any, Dict, List, Tuple

from .grader_base import BaseGrader


class Task2Grader(BaseGrader):
    """Grader for Task 2: Pipeline timing closure at 4ns.

    Timing closure is binary: WNS >= 0 at 4ns clock = 1.0, else 0.0.
    Uses analytical timing estimate from synthesis cell count.
    """

    CLOCK_PERIOD_NS = 4.0

    def _evaluate_timing_closure(
        self, submission_dir: str
    ) -> Tuple[float, Dict[str, Any]]:
        """Evaluate timing closure at 4ns clock period."""
        details = {}
        rtl_files = self._find_rtl_files(submission_dir)

        if not rtl_files:
            return 0.0, {"error": "No RTL files"}

        num_cells, area = self._run_synthesis(rtl_files)
        details["num_cells"] = num_cells

        if num_cells == 0:
            return 0.0, {"error": "Synthesis produced no cells"}

        # Analytical timing estimate
        import math
        estimated_depth = math.sqrt(num_cells) * 0.8
        avg_delay_per_level = 0.06  # ns — average for pipeline design
        critical_path_delay = estimated_depth * avg_delay_per_level

        wns = self.CLOCK_PERIOD_NS - critical_path_delay
        details["critical_path_delay_ns"] = round(critical_path_delay, 3)
        details["wns"] = round(wns, 3)
        details["timing_met"] = wns >= 0.0

        score = 1.0 if wns >= 0.0 else 0.0
        return score, details
