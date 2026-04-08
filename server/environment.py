"""
EDA Hardware Optimization Environment.

Core OpenEnv Environment implementation modeling RTL-to-GDSII as a POMDP.
Agents interact through 8 tool interfaces to optimize Verilog RTL for
Power, Performance, and Area (PPA) while maintaining functional correctness.
"""

import os
import uuid
from typing import Any, Dict, Optional

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import State

try:
    from ..models import EDAAction, EDAObservation, ToolName
except ImportError:
    from models import EDAAction, EDAObservation, ToolName

from .state_manager import (
    StateManager,
    EpisodeState,
    CompileCache,
    SynthesisCache,
    TimingCache,
    SimulationCache,
)
from .reward import compute_reward, RewardConfig
from .observation import build_observation

# Tool wrapper imports
from .tool_wrappers.compile_lint import compile_and_lint
from .tool_wrappers.simulation import run_simulation
from .tool_wrappers.synthesis import run_synthesis
from .tool_wrappers.timing import run_timing_analysis
from .tool_wrappers.metrics import query_metrics
from .tool_wrappers.rtl_modifier import modify_rtl
from .tool_wrappers.constraint_adjuster import adjust_constraints


# Base directory for tasks
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(_BASE_DIR, "tasks")

MAX_STEPS = 200

# Task configurations
TASK_CONFIGS = {
    "task_1": {
        "name": "ALU Area Optimization",
        "description": (
            "Optimize a 16-bit ALU to minimize total cell area and leakage power. "
            "The baseline uses redundant hardware — separate adder and subtractor "
            "instead of a shared adder with invert control, and duplicated comparison "
            "circuits. Your goal: refactor to share resources while preserving "
            "functional correctness across all 16 operations. Use compile_and_lint "
            "to check syntax, run_simulation to verify correctness, run_synthesis "
            "to measure area, and modify_rtl to apply changes."
        ),
        "baseline_dir": "task_1/baseline_rtl",
        "testbench": "task_1/testbenches/tb_alu.v",
        "constraints": "task_1/constraints/alu.sdc",
        "hidden_constraints": {
            "max_fanout": 16,
            "max_transition": 0.5,
        },
        "clock_period_ns": None,  # Combinational
    },
    "task_2": {
        "name": "Pipeline Timing Closure",
        "description": (
            "A 4-stage RISC-V-style pipeline has a timing violation — the execute "
            "stage combinational path is too long for the 4ns clock target. Your goal: "
            "achieve timing closure (WNS >= 0.0ns) by inserting pipeline registers "
            "to split the critical path, while minimizing area overhead. Use "
            "run_timing_analysis to identify the critical path, modify_rtl to insert "
            "registers, and run_synthesis + run_timing_analysis to verify."
        ),
        "baseline_dir": "task_2/baseline_rtl",
        "testbench": "task_2/testbenches/tb_pipeline.v",
        "constraints": "task_2/constraints/pipeline.sdc",
        "hidden_constraints": {
            "max_fanout": 16,
            "max_transition": 0.4,
        },
        "clock_period_ns": 4.0,
    },
    "task_3": {
        "name": "Memory Controller Power Optimization",
        "description": (
            "A memory controller wastes dynamic power with always-active counters, "
            "ungated read pipeline registers, and redundant prefetch logic. Your goal: "
            "reduce dynamic power via clock gating and removing unused logic — but "
            "beware of hidden constraints on read latency and functional correctness. "
            "Use query_metrics to check power, run_simulation to verify operations, "
            "and rollback_version if optimizations break functionality."
        ),
        "baseline_dir": "task_3/baseline_rtl",
        "testbench": "task_3/testbenches/tb_mem_ctrl.v",
        "constraints": "task_3/constraints/mem_ctrl.sdc",
        "hidden_constraints": {
            "max_fanout": 12,
            "max_transition": 0.3,
            "max_read_latency_cycles": 3,
        },
        "clock_period_ns": 5.0,
    },
}


class VerilogEnvironment(Environment):
    """EDA Hardware Optimization POMDP Environment.

    Models the RTL-to-GDSII pipeline. The agent interacts through 8 tools:
    compile_and_lint, run_simulation, run_synthesis, run_timing_analysis,
    query_metrics, modify_rtl, adjust_constraints, rollback_version.

    State is partially observable — the agent sees bounded tool outputs
    and explicitly queried metrics, never ground truth or hidden constraints.
    """

    # Properly scoped per-instance via StateManager's mkdtemp
    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        super().__init__()
        self._state_manager = StateManager()
        self._state = State(episode_id=str(uuid.uuid4()), step_count=0)
        self._episode: Optional[EpisodeState] = None
        self._reward_config = RewardConfig()

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs,
    ) -> EDAObservation:
        """Reset environment with a new task.

        Task selection: seed % 3 maps to task_1/task_2/task_3.
        Same seed always produces the same task.
        """
        # Clean up previous episode
        if self._episode:
            self._state_manager.cleanup_episode(self._episode.episode_id)

        eid = episode_id or str(uuid.uuid4())
        self._state = State(episode_id=eid, step_count=0)

        # Deterministic task selection
        task_idx = (seed % 3) if seed is not None else 0
        task_id = f"task_{task_idx + 1}"
        task_config = TASK_CONFIGS[task_id]

        # Create episode workspace
        source_dir = os.path.join(TASKS_DIR, task_config["baseline_dir"])
        self._episode = self._state_manager.create_episode(
            episode_id=eid,
            task_id=task_id,
            task_name=task_config["name"],
            source_dir=source_dir,
            hidden_constraints=task_config["hidden_constraints"],
        )

        # Copy testbench and constraints to workspace
        self._setup_workspace(task_config)

        # Run baseline synthesis to establish PPA metrics
        baseline_ppa = self._run_baseline_synthesis()
        self._episode.baseline_metrics = baseline_ppa

        # Build initial observation
        workspace_files = self._state_manager.list_workspace_files(eid)
        obs_data = build_observation(
            action_success=True,
            exit_code=0,
            tool_output=(
                f"Environment reset. Task: {task_config['name']}\n\n"
                f"Baseline synthesis complete.\n"
                f"Baseline area: {baseline_ppa.get('area', 'N/A')} units\n"
                f"Baseline cells: {baseline_ppa.get('num_cells', 'N/A')}\n"
                f"Files in workspace: {', '.join(workspace_files)}\n\n"
                f"Available tools: compile_and_lint, run_simulation, "
                f"run_synthesis, run_timing_analysis, query_metrics, "
                f"modify_rtl, adjust_constraints, rollback_version"
            ),
            step_number=0,
            task_name=task_config["name"],
            task_description=task_config["description"],
            workspace_files=workspace_files,
            dirty_files=set(),
        )

        return EDAObservation(
            done=False,
            reward=0.0,
            **obs_data,
        )

    def step(
        self,
        action: EDAAction,
        timeout_s: Optional[float] = None,
        **kwargs,
    ) -> EDAObservation:
        """Execute one tool action and return observation + reward."""
        if self._episode is None:
            return EDAObservation(
                done=True,
                reward=0.0,
                action_success=False,
                tool_output="Error: Environment not initialized. Call reset() first.",
            )

        ep = self._episode
        step_num = self._state_manager.increment_step(ep.episode_id)
        self._state.step_count = step_num

        # Check max steps
        if step_num > MAX_STEPS:
            ep.done = True
            return EDAObservation(
                done=True,
                reward=0.0,
                action_success=False,
                step_number=step_num,
                task_name=ep.task_name,
                tool_output=f"Episode ended: maximum {MAX_STEPS} steps reached.",
            )

        # Route to tool wrapper
        tool_name = action.tool_name.value
        tool_args = action.tool_args
        success = False
        exit_code = -1
        output = ""
        metrics_data = None

        try:
            if tool_name == "compile_and_lint":
                result = compile_and_lint(
                    target_file=tool_args.get("target_file", ""),
                    workspace_dir=ep.workspace_dir,
                )
                success = result.success
                exit_code = result.exit_code
                output = result.raw_output

                # Update error tracking
                ep.previous_errors = ep.current_errors.copy()
                ep.current_errors = set(result.errors)
                ep.compile_result = CompileCache(
                    success=success,
                    errors=result.errors,
                    warnings=result.warnings,
                )
                ep.compile_stale = False

            elif tool_name == "run_simulation":
                tb_file = tool_args.get("testbench_file", "testbenches/tb.v")
                result = run_simulation(
                    testbench_file=tb_file,
                    workspace_dir=ep.workspace_dir,
                )
                success = result.success
                exit_code = result.exit_code
                output = result.raw_output

                ep.simulation_result = SimulationCache(
                    success=success,
                    pass_rate=result.pass_rate,
                    passed=result.passed_tests,
                    failed=result.failed_tests,
                    total=result.total_tests,
                )
                ep.simulation_stale = False

            elif tool_name == "run_synthesis":
                result = run_synthesis(
                    workspace_dir=ep.workspace_dir,
                    effort_level=tool_args.get("effort_level", "medium"),
                    flatten=tool_args.get("flatten", False),
                )
                success = result.success
                exit_code = result.exit_code
                output = result.raw_output

                if success:
                    ep.synthesis_stats = SynthesisCache(
                        num_cells=result.num_cells,
                        num_wires=result.num_wires,
                        area_estimate=result.area_estimate,
                        cell_counts=result.cell_counts,
                    )
                    ep.synthesis_stale = False

            elif tool_name == "run_timing_analysis":
                clock_ns = tool_args.get("clock_period_ns", 5.0)
                # Convert SynthesisCache to dict for timing analysis
                synth_dict = (
                    ep.synthesis_stats.model_dump()
                    if ep.synthesis_stats
                    else None
                )
                result = run_timing_analysis(
                    clock_period_ns=clock_ns,
                    workspace_dir=ep.workspace_dir,
                    synthesis_stats=synth_dict,
                    hidden_constraints=ep.hidden_constraints,
                )
                success = result.success
                output = result.raw_output

                if success:
                    ep.timing_report = TimingCache(
                        wns=result.wns,
                        tns=result.tns,
                        timing_met=result.timing_met,
                        critical_path_delay_ns=result.critical_path_delay_ns,
                    )
                    ep.timing_stale = False

            elif tool_name == "query_metrics":
                metric_type = tool_args.get("metric_type", "all")
                # Convert typed caches to dicts for metrics query
                synth_dict = (
                    ep.synthesis_stats.model_dump()
                    if ep.synthesis_stats
                    else None
                )
                timing_dict = (
                    ep.timing_report.model_dump()
                    if ep.timing_report
                    else None
                )
                result = query_metrics(
                    metric_type=metric_type,
                    synthesis_stats=synth_dict,
                    timing_report=timing_dict,
                    baseline_metrics=ep.baseline_metrics,
                )
                success = result.success
                output = result.raw_output
                metrics_data = {
                    "area": result.area,
                    "area_delta_pct": result.area_delta_pct,
                    "power": result.power_estimate,
                    "power_delta_pct": result.power_delta_pct,
                    "wns": result.wns,
                    "timing_met": result.timing_met,
                }

            elif tool_name == "modify_rtl":
                file_path = tool_args.get("file_path", "")
                diff_patch = tool_args.get("diff_patch", "")

                if not file_path or not diff_patch:
                    output = "Error: file_path and diff_patch are required"
                else:
                    result = modify_rtl(
                        file_path=file_path,
                        diff_patch=diff_patch,
                        workspace_dir=ep.workspace_dir,
                    )
                    success = result.success
                    exit_code = result.exit_code
                    output = result.raw_output

                    if success:
                        # Invalidate all caches
                        self._state_manager.invalidate_caches(
                            ep.episode_id, file_path
                        )
                        # Git commit
                        self._state_manager.commit_step(
                            ep.episode_id,
                            f"Step {step_num}: modify {file_path}",
                        )

            elif tool_name == "adjust_constraints":
                constraint_file = tool_args.get("constraint_file", "")
                modifications = tool_args.get("modifications", "")

                if not constraint_file or not modifications:
                    output = "Error: constraint_file and modifications are required"
                else:
                    result = adjust_constraints(
                        constraint_file=constraint_file,
                        modifications=modifications,
                        workspace_dir=ep.workspace_dir,
                    )
                    success = result.success
                    output = result.raw_output

                    if success:
                        self._state_manager.commit_step(
                            ep.episode_id,
                            f"Step {step_num}: adjust constraints",
                        )

            elif tool_name == "rollback_version":
                step_id = tool_args.get("step_id", 0)
                rollback_ok = self._state_manager.rollback(
                    ep.episode_id, step_id
                )
                success = rollback_ok
                exit_code = 0 if rollback_ok else 1
                output = (
                    f"Rollback to step {step_id}: {'SUCCESS' if rollback_ok else 'FAILED'}"
                )

            else:
                output = f"Error: Unknown tool '{tool_name}'"

        except Exception as e:
            output = f"Error executing {tool_name}: {str(e)[:500]}"
            success = False

        # Compute reward — convert typed caches to dicts for reward function
        action_record = {
            "tool_name": tool_name,
            "success": success,
            "step": step_num,
        }

        synth_for_reward = (
            ep.synthesis_stats.model_dump()
            if ep.synthesis_stats and not ep.synthesis_stale
            else None
        )
        timing_for_reward = (
            ep.timing_report.model_dump()
            if ep.timing_report and not ep.timing_stale
            else None
        )
        sim_for_reward = (
            ep.simulation_result.model_dump()
            if ep.simulation_result and not ep.simulation_stale
            else None
        )

        reward = compute_reward(
            action_type=tool_name,
            action_success=success,
            current_synthesis=synth_for_reward,
            current_timing=timing_for_reward,
            current_simulation=sim_for_reward,
            baseline_metrics=ep.baseline_metrics,
            previous_errors=ep.previous_errors,
            current_errors=ep.current_errors,
            action_history=ep.action_history,
            simulation_stale=ep.simulation_stale,
            config=self._reward_config,
        )

        # Record action
        self._state_manager.record_action(ep.episode_id, action_record, reward)

        # Build observation
        workspace_files = self._state_manager.list_workspace_files(ep.episode_id)
        workspace_diff = self._state_manager.get_workspace_diff(ep.episode_id)

        obs_data = build_observation(
            action_success=success,
            exit_code=exit_code,
            tool_output=output,
            step_number=step_num,
            task_name=ep.task_name,
            task_description="",  # Only provided on reset
            workspace_files=workspace_files,
            dirty_files=set(workspace_diff),
            metrics=metrics_data,
        )

        return EDAObservation(
            done=ep.done,
            reward=reward,
            **obs_data,
        )

    @property
    def state(self) -> State:
        """Get current environment state (internal, not sent to agent)."""
        return self._state

    def close(self) -> None:
        """Clean up resources."""
        if self._episode:
            self._state_manager.cleanup_episode(self._episode.episode_id)
            self._episode = None

    def _setup_workspace(self, task_config: Dict[str, Any]) -> None:
        """Copy testbench and constraint files into workspace."""
        if not self._episode:
            return

        ws = self._episode.workspace_dir

        # Copy testbench
        tb_src = os.path.join(TASKS_DIR, task_config["testbench"])
        if os.path.isfile(tb_src):
            tb_dest_dir = os.path.join(ws, "testbenches")
            os.makedirs(tb_dest_dir, exist_ok=True)
            import shutil
            shutil.copy2(tb_src, os.path.join(tb_dest_dir, os.path.basename(tb_src)))

        # Copy constraints
        sdc_src = os.path.join(TASKS_DIR, task_config["constraints"])
        if os.path.isfile(sdc_src):
            sdc_dest_dir = os.path.join(ws, "constraints")
            os.makedirs(sdc_dest_dir, exist_ok=True)
            import shutil
            shutil.copy2(sdc_src, os.path.join(sdc_dest_dir, os.path.basename(sdc_src)))

        # Commit the full workspace
        self._state_manager.commit_step(
            self._episode.episode_id, "Initial workspace setup"
        )

    def _run_baseline_synthesis(self) -> Dict[str, Any]:
        """Run synthesis on baseline RTL to establish PPA metrics."""
        if not self._episode:
            return {}

        result = run_synthesis(workspace_dir=self._episode.workspace_dir)

        if result.success:
            # Estimate power
            from .tool_wrappers.metrics import (
                DYNAMIC_POWER_PER_CELL,
                LEAKAGE_POWER_PER_CELL,
            )
            power = result.num_cells * (
                DYNAMIC_POWER_PER_CELL + LEAKAGE_POWER_PER_CELL
            )

            metrics = {
                "area": result.area_estimate,
                "power": power,
                "num_cells": result.num_cells,
                "num_wires": result.num_wires,
            }

            self._episode.synthesis_stats = SynthesisCache(
                num_cells=result.num_cells,
                num_wires=result.num_wires,
                area_estimate=result.area_estimate,
                cell_counts=result.cell_counts,
            )
            self._episode.synthesis_stale = False

            return metrics

        return {"area": 0.0, "power": 0.0, "num_cells": 0}
