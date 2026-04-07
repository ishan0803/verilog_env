"""
Observation Builder — Partial Observability Enforcement.

Projects internal EDA state into bounded agent observations.
Ensures the agent NEVER sees: ground truth ASTs, hidden constraints,
intermediate binary artifacts, or full system history directly.
"""

from typing import Any, Dict, List, Optional, Set

MAX_TOOL_OUTPUT = 4000  # Maximum characters in tool output


def build_observation(
    action_success: bool,
    exit_code: int,
    tool_output: str,
    step_number: int,
    task_name: str,
    task_description: str,
    workspace_files: List[str],
    dirty_files: Set[str],
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a bounded observation for the agent.

    This function enforces partial observability by:
    - Truncating tool output to MAX_TOOL_OUTPUT characters
    - Only including metrics if explicitly queried
    - Never including hidden constraints or ground truth
    - Providing workspace diff instead of full file contents

    Args:
        action_success: Whether the last tool call succeeded.
        exit_code: System exit code of last tool.
        tool_output: Raw text output from EDA tool.
        step_number: Current step number.
        task_name: Current task identifier.
        task_description: Task objective (non-empty only on reset).
        workspace_files: List of files in workspace.
        dirty_files: Set of files modified since last compile.
        metrics: PPA metrics dict (only if query_metrics was called).

    Returns:
        Dict matching EDAObservation fields.
    """
    # Truncate tool output to enforce bounded observability
    bounded_output = tool_output[:MAX_TOOL_OUTPUT]
    if len(tool_output) > MAX_TOOL_OUTPUT:
        bounded_output += "\n... [output truncated]"

    return {
        "action_success": action_success,
        "exit_code": exit_code,
        "tool_output": bounded_output,
        "step_number": step_number,
        "task_name": task_name,
        "task_description": task_description,
        "workspace_diff": sorted(dirty_files),
        "available_files": workspace_files,
        "metrics": metrics,
    }
