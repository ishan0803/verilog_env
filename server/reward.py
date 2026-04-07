"""
Reward Function for EDA Hardware Optimization.

Implements: R_t = F_correct(t) * [α * δ_PPA(t) + T_closure(t) + I_progress(t)] - P_invalid(t)

Components:
- F_correct: Multiplicative gate [0.0, 1.0] — test pass rate
- δ_PPA: Normalized area/power improvement vs baseline
- T_closure: Sparse bonus for timing closure (WNS >= 0)
- I_progress: Dense micro-rewards for incremental progress
- P_invalid: Penalties for regressions and error loops
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set


@dataclass
class RewardConfig:
    """Configurable reward coefficients."""
    alpha_area: float = 0.6
    alpha_power: float = 0.4
    timing_closure_bonus: float = 5.0
    syntax_fix_reward: float = 0.1
    successful_synthesis_reward: float = 0.05
    new_error_penalty: float = -0.5
    regression_penalty: float = -1.0
    error_loop_penalty: float = -0.3


def compute_f_correct(
    simulation_result: Optional[Dict[str, Any]],
    simulation_stale: bool = False,
) -> float:
    """Compute functional correctness multiplier [0.0, 1.0].

    If simulation cache is stale (RTL was modified since last simulation)
    or no simulation has been run, returns 0.0 — the agent must prove
    functional correctness before unlocking any PPA rewards.

    If simulation failed entirely, returns 0.0.
    Otherwise returns the pass rate.
    """
    if simulation_result is None or simulation_stale:
        return 0.0  # Unverified correctness — no PPA reward

    pass_rate = simulation_result.get("pass_rate", 0.0)
    return max(0.0, min(1.0, pass_rate))


def compute_delta_ppa(
    current_stats: Optional[Dict[str, Any]],
    baseline_metrics: Dict[str, Any],
    config: RewardConfig,
) -> float:
    """Compute normalized PPA improvement.

    Returns positive value if PPA improved, negative if degraded.
    Formula: α_area * (baseline_area - current_area) / baseline_area
           + α_power * (baseline_power - current_power) / baseline_power
    """
    if current_stats is None or not baseline_metrics:
        return 0.0

    delta = 0.0
    baseline_area = baseline_metrics.get("area", 0.0)
    baseline_power = baseline_metrics.get("power", 0.0)
    current_area = current_stats.get("area_estimate", 0.0)
    current_power = current_stats.get("power_estimate", 0.0)

    if baseline_area > 0:
        area_improvement = (baseline_area - current_area) / baseline_area
        delta += config.alpha_area * area_improvement

    if baseline_power > 0:
        power_improvement = (baseline_power - current_power) / baseline_power
        delta += config.alpha_power * power_improvement

    return delta


def compute_timing_closure_bonus(
    timing_report: Optional[Dict[str, Any]],
    config: RewardConfig,
) -> float:
    """Sparse bonus if timing closure achieved (WNS >= 0)."""
    if timing_report is None:
        return 0.0

    wns = timing_report.get("wns", -1.0)
    if wns >= 0.0:
        return config.timing_closure_bonus
    return 0.0


def compute_incremental_progress(
    action_type: str,
    action_success: bool,
    previous_errors: Set[str],
    current_errors: Set[str],
    config: RewardConfig,
) -> float:
    """Dense micro-rewards for incremental progress.

    Awards:
    - Fixing a previously identified syntax error
    - Successful synthesis invocation
    """
    reward = 0.0

    # Reward for fixing errors
    fixed_errors = previous_errors - current_errors
    if fixed_errors:
        reward += config.syntax_fix_reward * len(fixed_errors)

    # Reward for successful synthesis
    if action_type == "run_synthesis" and action_success:
        reward += config.successful_synthesis_reward

    return reward


def compute_penalty(
    action_type: str,
    action_success: bool,
    previous_errors: Set[str],
    current_errors: Set[str],
    action_history: List[Dict[str, Any]],
    config: RewardConfig,
) -> float:
    """Compute penalties for invalid actions.

    Penalties:
    - Introducing new errors into previously compiling code
    - Loop detection: compile -> same error -> compile pattern
    """
    penalty = 0.0

    # New errors introduced
    new_errors = current_errors - previous_errors
    if new_errors and previous_errors != current_errors:
        # Only penalize if code was previously compiling (no errors)
        if len(previous_errors) == 0 and len(new_errors) > 0:
            penalty += config.regression_penalty
        else:
            penalty += config.new_error_penalty * min(len(new_errors), 3)

    # Error loop detection: same error appearing repeatedly
    if len(action_history) >= 3:
        recent = action_history[-3:]
        if all(
            a.get("tool_name") == "compile_and_lint"
            and not a.get("success", True)
            for a in recent
        ):
            penalty += config.error_loop_penalty

    return penalty  # Already negative from config


def compute_reward(
    action_type: str,
    action_success: bool,
    current_synthesis: Optional[Dict[str, Any]],
    current_timing: Optional[Dict[str, Any]],
    current_simulation: Optional[Dict[str, Any]],
    baseline_metrics: Dict[str, Any],
    previous_errors: Set[str],
    current_errors: Set[str],
    action_history: List[Dict[str, Any]],
    simulation_stale: bool = False,
    config: Optional[RewardConfig] = None,
) -> float:
    """Compute total reward for a step.

    R_t = F_correct(t) * [α * δ_PPA(t) + T_closure(t) + I_progress(t)] - P_invalid(t)

    Args:
        action_type: Name of the tool invoked.
        action_success: Whether the tool call succeeded.
        current_synthesis: Latest synthesis stats (or None if stale).
        current_timing: Latest timing report (or None if stale).
        current_simulation: Latest simulation result (or None).
        baseline_metrics: Baseline PPA from initial synthesis.
        previous_errors: Set of error strings from previous compile.
        current_errors: Set of error strings from latest compile.
        action_history: List of all previous actions in this episode.
        simulation_stale: True if RTL was modified since last simulation.
        config: Reward configuration (uses defaults if None).

    Returns:
        Total reward (float, can be negative).
    """
    if config is None:
        config = RewardConfig()

    # 1. Functional correctness multiplier
    # Agent must prove correctness (run simulation) after modifying RTL
    f_correct = compute_f_correct(current_simulation, simulation_stale)

    # 2. PPA improvement
    delta_ppa = compute_delta_ppa(current_synthesis, baseline_metrics, config)

    # 3. Timing closure bonus
    t_closure = compute_timing_closure_bonus(current_timing, config)

    # 4. Incremental progress
    i_progress = compute_incremental_progress(
        action_type, action_success, previous_errors, current_errors, config
    )

    # 5. Penalty
    p_invalid = compute_penalty(
        action_type, action_success, previous_errors, current_errors,
        action_history, config
    )

    # Final reward
    reward = f_correct * (delta_ppa + t_closure + i_progress) + p_invalid

    return round(reward, 4)

