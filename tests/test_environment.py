"""Unit tests for environment reset/step API compliance."""

import pytest
from models import EDAAction, EDAObservation, ToolName


class TestModels:
    """Test Pydantic model validation."""

    def test_action_valid(self):
        action = EDAAction(
            tool_name=ToolName.COMPILE_AND_LINT,
            tool_args={"target_file": "rtl/alu.v"},
        )
        assert action.tool_name == ToolName.COMPILE_AND_LINT
        assert action.tool_args["target_file"] == "rtl/alu.v"

    def test_action_all_tools(self):
        for tool in ToolName:
            action = EDAAction(tool_name=tool, tool_args={})
            assert action.tool_name == tool

    def test_observation_defaults(self):
        obs = EDAObservation()
        assert obs.done is False
        assert obs.reward is None
        assert obs.action_success is True
        assert obs.exit_code == 0
        assert obs.tool_output == ""
        assert obs.step_number == 0

    def test_observation_with_metrics(self):
        obs = EDAObservation(
            action_success=True,
            metrics={"area": 100.0, "power": 0.5},
            step_number=5,
            task_name="ALU Optimization",
        )
        assert obs.metrics["area"] == 100.0
        assert obs.step_number == 5

    def test_action_json_schema(self):
        schema = EDAAction.model_json_schema()
        assert "tool_name" in schema.get("properties", {})
        assert "tool_args" in schema.get("properties", {})


class TestEnvironment:
    """Test environment initialization (no EDA tools needed)."""

    def test_environment_import(self):
        from server.environment import VerilogEnvironment
        assert VerilogEnvironment is not None

    def test_environment_creates(self):
        from server.environment import VerilogEnvironment
        env = VerilogEnvironment()
        assert env is not None
        assert env.state is not None

    def test_reset_returns_observation(self):
        from server.environment import VerilogEnvironment
        env = VerilogEnvironment()
        obs = env.reset(seed=42)
        assert isinstance(obs, EDAObservation)
        assert obs.done is False
        assert obs.step_number == 0
        assert obs.task_name != ""
        env.close()

    def test_deterministic_task_selection(self):
        """Same seed must produce same task."""
        from server.environment import VerilogEnvironment
        env1 = VerilogEnvironment()
        obs1 = env1.reset(seed=42)
        env1.close()

        env2 = VerilogEnvironment()
        obs2 = env2.reset(seed=42)
        env2.close()

        assert obs1.task_name == obs2.task_name

    def test_different_seeds_different_tasks(self):
        """Different seeds should map to different tasks."""
        from server.environment import VerilogEnvironment
        tasks = set()
        for seed in range(3):
            env = VerilogEnvironment()
            obs = env.reset(seed=seed)
            tasks.add(obs.task_name)
            env.close()
        assert len(tasks) == 3  # All 3 tasks should be different

    def test_step_requires_reset(self):
        """Step without reset should return error."""
        from server.environment import VerilogEnvironment
        env = VerilogEnvironment()
        action = EDAAction(
            tool_name=ToolName.QUERY_METRICS,
            tool_args={"metric_type": "all"},
        )
        obs = env.step(action)
        assert obs.done is True
        assert "not initialized" in obs.tool_output.lower() or "reset" in obs.tool_output.lower()
