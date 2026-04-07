"""
Base Grader — Shared Scoring Logic.

Final score = 0.40 * functional_correctness
            + 0.30 * ppa_improvement
            + 0.20 * timing_closure
            + 0.10 * trajectory_stability

All graders are fully deterministic: same RTL input always produces same score.
"""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class GraderResult:
    """Result of grading an RTL submission."""
    score: float = 0.0
    functional_correctness: float = 0.0
    ppa_improvement: float = 0.0
    timing_closure: float = 0.0
    trajectory_stability: float = 0.0
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class BaseGrader:
    """Base class for task graders."""

    # Scoring weights
    W_FUNCTIONAL = 0.40
    W_PPA = 0.30
    W_TIMING = 0.20
    W_STABILITY = 0.10

    # Timeouts
    COMPILE_TIMEOUT = 30
    SIMULATION_TIMEOUT = 60
    SYNTHESIS_TIMEOUT = 120

    def __init__(self, task_dir: str):
        """Initialize grader with task directory.

        Args:
            task_dir: Path to task directory containing baseline_rtl/,
                      hidden_tests/, and constraints/.
        """
        self.task_dir = task_dir
        self.baseline_dir = os.path.join(task_dir, "baseline_rtl")
        self.hidden_test_dir = os.path.join(task_dir, "hidden_tests")
        self.constraints_dir = os.path.join(task_dir, "constraints")

    def grade(
        self,
        submission_dir: str,
        baseline_metrics: Dict[str, Any],
        action_history: Optional[List[Dict[str, Any]]] = None,
    ) -> GraderResult:
        """Grade an RTL submission.

        Args:
            submission_dir: Directory containing the agent's modified RTL.
            baseline_metrics: Baseline PPA metrics for comparison.
            action_history: List of actions taken (for trajectory stability).

        Returns:
            GraderResult with score in [0.0, 1.0].
        """
        result = GraderResult()

        # 1. Functional correctness (40%)
        fc_score, fc_details = self._evaluate_functional_correctness(
            submission_dir
        )
        result.functional_correctness = fc_score
        result.details["functional_correctness"] = fc_details

        # CRITICAL: If functional correctness is 0, final score is 0
        if fc_score == 0.0:
            result.score = 0.0
            result.details["early_termination"] = (
                "Zero functional correctness — all other scores zeroed"
            )
            return result

        # 2. PPA improvement (30%)
        ppa_score, ppa_details = self._evaluate_ppa(
            submission_dir, baseline_metrics
        )
        result.ppa_improvement = ppa_score
        result.details["ppa"] = ppa_details

        # 3. Timing closure (20%)
        tc_score, tc_details = self._evaluate_timing_closure(submission_dir)
        result.timing_closure = tc_score
        result.details["timing"] = tc_details

        # 4. Trajectory stability (10%)
        ts_score = self._evaluate_trajectory_stability(action_history or [])
        result.trajectory_stability = ts_score

        # Final weighted score
        result.score = (
            self.W_FUNCTIONAL * result.functional_correctness
            + self.W_PPA * result.ppa_improvement
            + self.W_TIMING * result.timing_closure
            + self.W_STABILITY * result.trajectory_stability
        )

        # Clamp to [0.0, 1.0]
        result.score = max(0.0, min(1.0, round(result.score, 4)))

        return result

    def _evaluate_functional_correctness(
        self, submission_dir: str
    ) -> Tuple[float, Dict[str, Any]]:
        """Run hidden exhaustive testbench against submitted RTL.

        Returns:
            Tuple of (score [0.0, 1.0], details dict).
        """
        details = {}
        rtl_files = self._find_rtl_files(submission_dir)
        hidden_tbs = self._find_hidden_testbenches()

        if not rtl_files:
            details["error"] = "No RTL files found in submission"
            return 0.0, details

        if not hidden_tbs:
            details["error"] = "No hidden testbenches found"
            return 0.0, details

        total_pass = 0
        total_tests = 0

        for tb in hidden_tbs:
            pass_count, fail_count, output = self._run_testbench(
                rtl_files, tb
            )
            total_pass += pass_count
            total_tests += pass_count + fail_count
            details[os.path.basename(tb)] = {
                "passed": pass_count,
                "failed": fail_count,
                "output_snippet": output[:500],
            }

        if total_tests == 0:
            details["error"] = "No test results parsed (compilation may have failed)"
            return 0.0, details

        score = total_pass / total_tests
        details["total_passed"] = total_pass
        details["total_tests"] = total_tests
        return round(score, 4), details

    def _evaluate_ppa(
        self,
        submission_dir: str,
        baseline_metrics: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        """Evaluate PPA improvement via Yosys synthesis.

        Returns normalized improvement score [0.0, 1.0].
        Full 1.0 at 15% improvement.
        """
        details = {}
        rtl_files = self._find_rtl_files(submission_dir)

        if not rtl_files:
            return 0.0, {"error": "No RTL files"}

        # Run synthesis
        cells, area = self._run_synthesis(rtl_files)
        details["current_cells"] = cells
        details["current_area"] = area

        baseline_area = baseline_metrics.get("area", 0.0)
        if baseline_area <= 0:
            return 0.0, {"error": "No baseline area"}

        improvement = (baseline_area - area) / baseline_area
        details["improvement_pct"] = round(improvement * 100, 2)

        # Normalize: 15% improvement = full score
        score = min(1.0, max(0.0, improvement / 0.15))
        return round(score, 4), details

    def _evaluate_timing_closure(
        self, submission_dir: str
    ) -> Tuple[float, Dict[str, Any]]:
        """Evaluate timing closure. Binary: met or not."""
        # Default implementation — overridden by sequential task graders
        return 1.0, {"note": "No timing constraint for this task"}

    def _evaluate_trajectory_stability(
        self, action_history: List[Dict[str, Any]]
    ) -> float:
        """Evaluate trajectory stability.

        Deducts for:
        - Compile-error loops (same error repeated)
        - Excessive rollbacks
        """
        if not action_history:
            return 1.0

        penalty = 0.0
        penalty_per_loop = 0.1

        # Detect compile-error loops
        consecutive_compile_fails = 0
        for action in action_history:
            if (
                action.get("tool_name") == "compile_and_lint"
                and not action.get("success", True)
            ):
                consecutive_compile_fails += 1
                if consecutive_compile_fails >= 3:
                    penalty += penalty_per_loop
                    consecutive_compile_fails = 0
            else:
                consecutive_compile_fails = 0

        # Excessive rollbacks
        rollback_count = sum(
            1 for a in action_history if a.get("tool_name") == "rollback_version"
        )
        if rollback_count > 5:
            penalty += (rollback_count - 5) * 0.02

        return max(0.0, min(1.0, 1.0 - penalty))

    def _find_rtl_files(self, directory: str) -> List[str]:
        """Find Verilog source files in a directory."""
        files = []
        rtl_dir = os.path.join(directory, "rtl")
        search_dir = rtl_dir if os.path.isdir(rtl_dir) else directory

        for f in sorted(os.listdir(search_dir)):
            if (f.endswith(".v") or f.endswith(".sv")) and not f.startswith("tb_"):
                files.append(os.path.join(search_dir, f))
        return files

    def _find_hidden_testbenches(self) -> List[str]:
        """Find hidden testbench files."""
        if not os.path.isdir(self.hidden_test_dir):
            return []
        return [
            os.path.join(self.hidden_test_dir, f)
            for f in sorted(os.listdir(self.hidden_test_dir))
            if f.endswith(".v") and f.startswith("tb_")
        ]

    def _run_testbench(
        self, rtl_files: List[str], testbench: str
    ) -> Tuple[int, int, str]:
        """Compile and run a testbench. Returns (pass_count, fail_count, output)."""
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".vvp", delete=False
            ) as tmp:
                sim_bin = tmp.name

            # Compile
            cmd = ["iverilog", "-o", sim_bin, "-g2012"] + rtl_files + [testbench]
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=self.COMPILE_TIMEOUT,
            )
            if proc.returncode != 0:
                return 0, 1, f"Compilation failed:\n{proc.stderr[:500]}"

            # Simulate
            proc = subprocess.run(
                ["vvp", sim_bin],
                capture_output=True, text=True,
                timeout=self.SIMULATION_TIMEOUT,
            )

            output = proc.stdout + "\n" + proc.stderr
            pass_count = len(re.findall(r"TEST\s+\S+\s+PASSED", output, re.I))
            fail_count = len(re.findall(r"TEST\s+\S+\s+FAILED", output, re.I))

            if pass_count == 0 and fail_count == 0:
                # No explicit markers — use exit code
                if proc.returncode == 0:
                    pass_count = 1
                else:
                    fail_count = 1

            return pass_count, fail_count, output

        except subprocess.TimeoutExpired:
            return 0, 1, "Simulation timed out"
        except FileNotFoundError:
            return 0, 1, "iverilog not found — EDA tools required"
        finally:
            if os.path.exists(sim_bin):
                os.unlink(sim_bin)

    def _run_synthesis(self, rtl_files: List[str]) -> Tuple[int, float]:
        """Run Yosys synthesis and return (num_cells, area_estimate)."""
        try:
            read_cmds = "; ".join(f"read_verilog -sv {f}" for f in rtl_files)
            yosys_cmd = f"{read_cmds}; synth; stat"

            proc = subprocess.run(
                ["yosys", "-p", yosys_cmd],
                capture_output=True, text=True,
                timeout=self.SYNTHESIS_TIMEOUT,
            )

            output = proc.stdout
            cells_match = re.search(r"Number of cells:\s+(\d+)", output)
            num_cells = int(cells_match.group(1)) if cells_match else 0

            # Estimate area from cell count
            area = num_cells * 2.0
            return num_cells, area

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return 0, 0.0
