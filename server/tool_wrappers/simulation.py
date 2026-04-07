"""
Simulation Tool Wrapper.

Compiles RTL + testbench with iverilog, runs with vvp,
and parses stdout for PASS/FAIL test vector results.
"""

import subprocess
import os
import re
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from .path_security import resolve_safe_path

SIMULATION_TIMEOUT = 60  # seconds
MAX_OUTPUT_CHARS = 4000


@dataclass
class SimulationResult:
    """Result of a simulation run."""
    success: bool = False
    exit_code: int = -1
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    pass_rate: float = 0.0
    failures: List[str] = field(default_factory=list)
    raw_output: str = ""


def run_simulation(
    testbench_file: str,
    workspace_dir: str,
    rtl_files: Optional[List[str]] = None,
) -> SimulationResult:
    """Run Verilog testbench simulation.

    Compiles the testbench with iverilog, runs it with vvp, and parses
    PASS/FAIL markers from stdout.

    Convention: Testbenches emit lines matching:
        TEST <name> PASSED
        TEST <name> FAILED
        ALL TESTS PASSED  (optional summary)

    Args:
        testbench_file: Path to testbench file (relative to workspace_dir).
        workspace_dir: Root workspace directory.
        rtl_files: Optional list of RTL source files to include.

    Returns:
        SimulationResult with pass rate, failure details, and bounded output.
    """
    result = SimulationResult()

    try:
        tb_abs = resolve_safe_path(workspace_dir, testbench_file)
    except ValueError as e:
        result.raw_output = f"Error: {e}"
        return result

    if not os.path.isfile(tb_abs):
        result.raw_output = f"Error: Testbench not found: {testbench_file}"
        return result

    # Determine RTL files — look for them in the workspace if not specified
    if rtl_files is None:
        rtl_files = []
        rtl_dir = os.path.join(workspace_dir, "rtl")
        if os.path.isdir(rtl_dir):
            for f in os.listdir(rtl_dir):
                if f.endswith(".v") or f.endswith(".sv"):
                    rtl_files.append(os.path.join("rtl", f))

    # Build iverilog compile command
    with tempfile.NamedTemporaryFile(suffix=".vvp", delete=False, dir=workspace_dir) as tmp:
        sim_binary = tmp.name

    try:
        compile_cmd = ["iverilog", "-o", sim_binary, "-g2012"]
        for rf in rtl_files:
            compile_cmd.append(os.path.join(workspace_dir, rf))
        compile_cmd.append(tb_abs)

        proc = subprocess.run(
            compile_cmd,
            capture_output=True,
            text=True,
            timeout=SIMULATION_TIMEOUT // 2,
            cwd=workspace_dir,
        )

        if proc.returncode != 0:
            output = (proc.stdout + "\n" + proc.stderr).strip()
            result.raw_output = f"Compilation failed:\n{output}"[:MAX_OUTPUT_CHARS]
            result.exit_code = proc.returncode
            return result

        # Run simulation
        sim_proc = subprocess.run(
            ["vvp", sim_binary],
            capture_output=True,
            text=True,
            timeout=SIMULATION_TIMEOUT,
            cwd=workspace_dir,
        )

        result.exit_code = sim_proc.returncode
        output = (sim_proc.stdout + "\n" + sim_proc.stderr).strip()
        result.raw_output = output[:MAX_OUTPUT_CHARS]

        # Parse test results
        pass_pattern = re.compile(r"TEST\s+(.+?)\s+PASSED", re.IGNORECASE)
        fail_pattern = re.compile(r"TEST\s+(.+?)\s+FAILED", re.IGNORECASE)

        passes = pass_pattern.findall(output)
        fails = fail_pattern.findall(output)

        result.passed_tests = len(passes)
        result.failed_tests = len(fails)
        result.total_tests = result.passed_tests + result.failed_tests
        result.failures = [f"FAILED: {f}" for f in fails]

        if result.total_tests > 0:
            result.pass_rate = result.passed_tests / result.total_tests
        else:
            # If no explicit markers, check exit code
            result.pass_rate = 1.0 if sim_proc.returncode == 0 else 0.0
            result.total_tests = 1
            result.passed_tests = 1 if sim_proc.returncode == 0 else 0
            result.failed_tests = 0 if sim_proc.returncode == 0 else 1

        result.success = result.pass_rate == 1.0

    except subprocess.TimeoutExpired:
        result.raw_output = f"Error: Simulation timed out after {SIMULATION_TIMEOUT}s"
        result.exit_code = 124
    except FileNotFoundError:
        result.raw_output = (
            "Error: iverilog/vvp not found. EDA tools are only available inside the Docker container."
        )
        result.exit_code = 127
    finally:
        if os.path.exists(sim_binary):
            os.unlink(sim_binary)

    return result
