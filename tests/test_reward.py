"""Unit tests for the reward function."""

import pytest
from server.reward import (
    compute_reward,
    compute_f_correct,
    compute_delta_ppa,
    compute_timing_closure_bonus,
    compute_incremental_progress,
    compute_penalty,
    RewardConfig,
)


class TestFCorrect:
    """Tests for functional correctness multiplier."""

    def test_no_simulation_returns_zero(self):
        """Unverified correctness must block all PPA rewards (fixes reward hacking)."""
        assert compute_f_correct(None) == 0.0

    def test_stale_simulation_returns_zero(self):
        """Stale simulation (RTL modified since last sim) must return 0.0."""
        assert compute_f_correct({"pass_rate": 1.0}, simulation_stale=True) == 0.0

    def test_zero_pass_rate(self):
        assert compute_f_correct({"pass_rate": 0.0}) == 0.0

    def test_full_pass_rate(self):
        assert compute_f_correct({"pass_rate": 1.0}) == 1.0

    def test_partial_pass(self):
        assert compute_f_correct({"pass_rate": 0.8}) == 0.8


class TestDeltaPPA:
    """Tests for PPA improvement calculation."""

    def test_no_data(self):
        config = RewardConfig()
        assert compute_delta_ppa(None, {}, config) == 0.0

    def test_area_improvement(self):
        config = RewardConfig(alpha_area=1.0, alpha_power=0.0)
        current = {"area_estimate": 80.0}
        baseline = {"area": 100.0}
        delta = compute_delta_ppa(current, baseline, config)
        assert delta == pytest.approx(0.2)  # 20% improvement

    def test_area_degradation(self):
        config = RewardConfig(alpha_area=1.0, alpha_power=0.0)
        current = {"area_estimate": 120.0}
        baseline = {"area": 100.0}
        delta = compute_delta_ppa(current, baseline, config)
        assert delta == pytest.approx(-0.2)  # 20% worse


class TestTimingClosure:
    """Tests for timing closure bonus."""

    def test_timing_met(self):
        config = RewardConfig(timing_closure_bonus=5.0)
        assert compute_timing_closure_bonus({"wns": 0.5}, config) == 5.0

    def test_timing_not_met(self):
        config = RewardConfig(timing_closure_bonus=5.0)
        assert compute_timing_closure_bonus({"wns": -0.5}, config) == 0.0

    def test_exact_zero_wns(self):
        config = RewardConfig(timing_closure_bonus=5.0)
        assert compute_timing_closure_bonus({"wns": 0.0}, config) == 5.0

    def test_no_timing_data(self):
        config = RewardConfig()
        assert compute_timing_closure_bonus(None, config) == 0.0


class TestComputeReward:
    """Integration tests for the full reward function."""

    def test_zero_correctness_zeros_reward(self):
        """Design with 0% test pass rate must get <= 0 reward."""
        reward = compute_reward(
            action_type="run_synthesis",
            action_success=True,
            current_synthesis={"area_estimate": 50.0, "cell_counts": {}},
            current_timing={"wns": 1.0, "timing_met": True},
            current_simulation={"pass_rate": 0.0},
            baseline_metrics={"area": 100.0, "power": 1.0},
            previous_errors=set(),
            current_errors=set(),
            action_history=[],
        )
        assert reward <= 0.0

    def test_perfect_correctness_with_ppa_gain(self):
        """Perfect correctness + area improvement = positive reward."""
        reward = compute_reward(
            action_type="run_synthesis",
            action_success=True,
            current_synthesis={"area_estimate": 80.0, "cell_counts": {}},
            current_timing=None,
            current_simulation={"pass_rate": 1.0},
            baseline_metrics={"area": 100.0, "power": 1.0},
            previous_errors=set(),
            current_errors=set(),
            action_history=[],
        )
        assert reward > 0.0

    def test_timing_closure_adds_bonus(self):
        """Timing closure should add significant bonus."""
        reward_no_timing = compute_reward(
            action_type="run_synthesis",
            action_success=True,
            current_synthesis={"area_estimate": 100.0, "cell_counts": {}},
            current_timing={"wns": -1.0, "timing_met": False},
            current_simulation={"pass_rate": 1.0},
            baseline_metrics={"area": 100.0, "power": 1.0},
            previous_errors=set(),
            current_errors=set(),
            action_history=[],
        )
        reward_with_timing = compute_reward(
            action_type="run_synthesis",
            action_success=True,
            current_synthesis={"area_estimate": 100.0, "cell_counts": {}},
            current_timing={"wns": 0.5, "timing_met": True},
            current_simulation={"pass_rate": 1.0},
            baseline_metrics={"area": 100.0, "power": 1.0},
            previous_errors=set(),
            current_errors=set(),
            action_history=[],
        )
        assert reward_with_timing > reward_no_timing

    def test_regression_penalized(self):
        """Breaking previously compiling code should be penalized."""
        reward = compute_reward(
            action_type="compile_and_lint",
            action_success=False,
            current_synthesis=None,
            current_timing=None,
            current_simulation=None,
            baseline_metrics={"area": 100.0},
            previous_errors=set(),  # Was compiling fine
            current_errors={"syntax error line 42"},  # Now broken
            action_history=[],
        )
        assert reward < 0.0

    def test_error_loop_penalized(self):
        """Repeated compile failures should be penalized."""
        history = [
            {"tool_name": "compile_and_lint", "success": False},
            {"tool_name": "compile_and_lint", "success": False},
            {"tool_name": "compile_and_lint", "success": False},
        ]
        reward = compute_reward(
            action_type="compile_and_lint",
            action_success=False,
            current_synthesis=None,
            current_timing=None,
            current_simulation=None,
            baseline_metrics={"area": 100.0},
            previous_errors={"error1"},
            current_errors={"error1"},
            action_history=history,
        )
        assert reward < 0.0
