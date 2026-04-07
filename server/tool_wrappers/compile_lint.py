"""
Compile and Lint Tool Wrapper.

Runs Icarus Verilog (iverilog -t null) for syntax checking and
optionally Verilator (--lint-only) for deeper static analysis.
"""

import subprocess
import os
from dataclasses import dataclass, field
from typing import List, Optional

from .path_security import resolve_safe_path

COMPILE_TIMEOUT = 30  # seconds
MAX_OUTPUT_CHARS = 4000


@dataclass
class CompileLintResult:
    """Result of compile and lint operation."""
    success: bool = False
    exit_code: int = -1
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    raw_output: str = ""


def compile_and_lint(
    target_file: str,
    workspace_dir: str,
    include_dirs: Optional[List[str]] = None,
) -> CompileLintResult:
    """Compile and lint a Verilog file using iverilog.

    Args:
        target_file: Path to the Verilog file (relative to workspace_dir).
        workspace_dir: Root workspace directory.
        include_dirs: Optional list of include directories.

    Returns:
        CompileLintResult with success flag, errors, warnings, and bounded output.
    """
    result = CompileLintResult()

    try:
        abs_path = resolve_safe_path(workspace_dir, target_file)
    except ValueError as e:
        result.raw_output = f"Error: {e}"
        result.errors = [result.raw_output]
        return result

    if not os.path.isfile(abs_path):
        result.raw_output = f"Error: File not found: {target_file}"
        result.errors = [result.raw_output]
        return result

    # Build iverilog command
    cmd = ["iverilog", "-t", "null"]
    if include_dirs:
        for d in include_dirs:
            cmd.extend(["-I", os.path.join(workspace_dir, d)])
    cmd.append(abs_path)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=COMPILE_TIMEOUT,
            cwd=workspace_dir,
        )
        result.exit_code = proc.returncode
        output = (proc.stdout + "\n" + proc.stderr).strip()
        result.raw_output = output[:MAX_OUTPUT_CHARS]

        # Parse errors and warnings
        for line in output.splitlines():
            line_lower = line.lower()
            if "error" in line_lower:
                result.errors.append(line.strip())
            elif "warning" in line_lower:
                result.warnings.append(line.strip())

        result.success = proc.returncode == 0

    except subprocess.TimeoutExpired:
        result.raw_output = f"Error: Compilation timed out after {COMPILE_TIMEOUT}s"
        result.errors = [result.raw_output]
        result.exit_code = 124
    except FileNotFoundError:
        result.raw_output = (
            "Error: iverilog not found. EDA tools are only available inside the Docker container."
        )
        result.errors = [result.raw_output]
        result.exit_code = 127

    return result
