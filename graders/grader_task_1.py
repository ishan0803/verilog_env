"""Task 1 Grader — ALU Optimization (Easy)."""

from typing import Any, Dict, Tuple
from .grader_base import BaseGrader


class Task1Grader(BaseGrader):
    """Grader for Task 1: Combinational ALU area optimization.

    No timing constraint (purely combinational).
    Timing closure score is always 1.0 for this task.
    """

    def _evaluate_timing_closure(
        self, submission_dir: str
    ) -> Tuple[float, Dict[str, Any]]:
        """ALU is combinational — timing always met."""
        return 1.0, {
            "note": "Combinational design — no clock constraint",
            "timing_met": True,
        }
