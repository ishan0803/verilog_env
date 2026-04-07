"""
RTL Modifier Tool Wrapper.

Applies unified diff patches or full file replacements to Verilog RTL files.
Triggers cache invalidation and git commit after modification.

NOTE: The manual patch fallback has been removed. If the `patch` binary is
unavailable, the agent receives an error and should use full file replacement.
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass

from .path_security import resolve_safe_path


@dataclass
class PatchResult:
    """Result of an RTL modification."""
    success: bool = False
    exit_code: int = -1
    raw_output: str = ""
    file_path: str = ""
    lines_added: int = 0
    lines_removed: int = 0


def modify_rtl(
    file_path: str,
    diff_patch: str,
    workspace_dir: str,
) -> PatchResult:
    """Apply a unified diff patch or full replacement to an RTL file.

    Supports two modes:
    1. Unified diff format (starts with --- or @@)
    2. Full file replacement (if diff doesn't look like a patch)

    Args:
        file_path: Path to the file to modify (relative to workspace_dir).
        diff_patch: Either a unified diff patch or full replacement content.
        workspace_dir: Root workspace directory.

    Returns:
        PatchResult with success flag and details.
    """
    result = PatchResult()
    result.file_path = file_path

    try:
        abs_path = resolve_safe_path(workspace_dir, file_path)
    except ValueError as e:
        result.raw_output = f"Error: {e}"
        return result

    if not os.path.isfile(abs_path):
        result.raw_output = f"Error: File not found: {file_path}"
        return result

    # Detect if this is a unified diff or full content replacement
    is_diff = any(
        diff_patch.lstrip().startswith(prefix)
        for prefix in ("---", "@@", "diff ", "+++")
    )

    if is_diff:
        # Apply unified diff using patch command
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False, dir=workspace_dir
            ) as pf:
                pf.write(diff_patch)
                patch_file = pf.name

            proc = subprocess.run(
                ["patch", "-p0", "--forward", abs_path, patch_file],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=workspace_dir,
            )
            result.exit_code = proc.returncode
            result.raw_output = (proc.stdout + "\n" + proc.stderr).strip()
            result.success = proc.returncode == 0

            # Count changes
            for line in diff_patch.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    result.lines_added += 1
                elif line.startswith("-") and not line.startswith("---"):
                    result.lines_removed += 1

            os.unlink(patch_file)

        except subprocess.TimeoutExpired:
            result.raw_output = "Error: Patch application timed out"
            result.exit_code = 124
        except FileNotFoundError:
            # patch binary not found — return error to agent instead of
            # using a broken manual fallback
            result.raw_output = (
                "Error: 'patch' command not found. Please provide the FULL "
                "updated file content in the diff_patch argument instead of "
                "a unified diff."
            )
            result.exit_code = 127
    else:
        # Full content replacement
        try:
            # Read original for line count
            with open(abs_path, "r") as f:
                original = f.readlines()

            with open(abs_path, "w") as f:
                f.write(diff_patch)

            new_lines = diff_patch.count("\n") + (
                1 if not diff_patch.endswith("\n") else 0
            )
            result.lines_added = new_lines
            result.lines_removed = len(original)
            result.success = True
            result.exit_code = 0
            result.raw_output = (
                f"File replaced: {result.lines_removed} lines removed, "
                f"{result.lines_added} lines added"
            )
        except OSError as e:
            result.raw_output = f"Error writing file: {e}"

    return result
