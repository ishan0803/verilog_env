"""
Data models for the EDA Hardware Optimization Environment.

Defines the Action and Observation types for the RTL-to-GDSII POMDP.
The agent interacts via 8 tool interfaces; observations are bounded
text projections of internal EDA state (partial observability).
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from openenv.core.env_server.types import Action, Observation
from pydantic import Field


class ToolName(str, Enum):
    """Available EDA tool interfaces."""
    COMPILE_AND_LINT = "compile_and_lint"
    RUN_SIMULATION = "run_simulation"
    RUN_SYNTHESIS = "run_synthesis"
    RUN_TIMING_ANALYSIS = "run_timing_analysis"
    QUERY_METRICS = "query_metrics"
    MODIFY_RTL = "modify_rtl"
    ADJUST_CONSTRAINTS = "adjust_constraints"
    ROLLBACK_VERSION = "rollback_version"


class EDAAction(Action):
    """Action for the EDA environment — invoke one of 8 tool interfaces.

    Attributes:
        tool_name: Which EDA tool to invoke.
        tool_args: Tool-specific keyword arguments.
            - compile_and_lint: {target_file: str}
            - run_simulation: {testbench_file: str}
            - run_synthesis: {effort_level: "low"|"medium"|"high", flatten: bool}
            - run_timing_analysis: {clock_period_ns: float}
            - query_metrics: {metric_type: "area"|"power"|"timing"|"all"}
            - modify_rtl: {file_path: str, diff_patch: str}
            - adjust_constraints: {constraint_file: str, modifications: str}
            - rollback_version: {step_id: int}
    """

    tool_name: ToolName = Field(
        ..., description="Name of the EDA tool to invoke"
    )
    tool_args: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific keyword arguments",
    )


class EDAObservation(Observation):
    """Observation from the EDA environment — bounded partial view of state.

    The agent NEVER sees: ground truth ASTs, hidden constraints,
    intermediate binary artifacts, or full system history.

    Attributes:
        action_success: Whether the last tool invocation succeeded.
        exit_code: System exit code of the last tool call.
        tool_output: Bounded text output from the EDA tool (max 4000 chars).
        metrics: Partial PPA metrics if explicitly queried via query_metrics.
        workspace_diff: Files modified since last compile/synthesis.
        step_number: Current step in the episode.
        task_name: Name of the current task.
        task_description: Human-readable task objective (only on reset).
        available_files: List of files in the workspace.
    """

    action_success: bool = Field(
        default=True, description="Whether the last tool call succeeded"
    )
    exit_code: int = Field(
        default=0, description="Exit code of the last tool invocation"
    )
    tool_output: str = Field(
        default="", description="Bounded text output from the EDA tool"
    )
    metrics: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Partial PPA metrics (only if queried via query_metrics)",
    )
    workspace_diff: List[str] = Field(
        default_factory=list,
        description="Files modified since last compile/synthesis",
    )
    step_number: int = Field(default=0, description="Current episode step")
    task_name: str = Field(default="", description="Current task name")
    task_description: str = Field(
        default="", description="Task objective description"
    )
    available_files: List[str] = Field(
        default_factory=list, description="Files in workspace"
    )
