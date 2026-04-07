"""EDA Hardware Optimization Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult
from openenv.core.env_server.types import State

from .models import EDAAction, EDAObservation


class VerilogEnv(EnvClient[EDAAction, EDAObservation, State]):
    """
    Client for the EDA Hardware Optimization Environment.

    Maintains a persistent WebSocket connection for efficient multi-step
    interactions. Each client instance has its own dedicated environment session.

    Example:
        >>> async with VerilogEnv(base_url="http://localhost:8000") as env:
        ...     result = await env.reset(seed=42)
        ...     print(result.observation.task_name)
        ...
        ...     action = EDAAction(tool_name="compile_and_lint",
        ...                        tool_args={"target_file": "rtl/alu.v"})
        ...     result = await env.step(action)
        ...     print(result.observation.tool_output)
    """

    def _step_payload(self, action: EDAAction) -> Dict:
        """Convert EDAAction to JSON payload."""
        return {
            "tool_name": action.tool_name.value,
            "tool_args": action.tool_args,
        }

    def _parse_result(self, payload: Dict) -> StepResult[EDAObservation]:
        """Parse server response into StepResult[EDAObservation]."""
        obs_data = payload.get("observation", {})
        observation = EDAObservation(
            action_success=obs_data.get("action_success", True),
            exit_code=obs_data.get("exit_code", 0),
            tool_output=obs_data.get("tool_output", ""),
            metrics=obs_data.get("metrics"),
            workspace_diff=obs_data.get("workspace_diff", []),
            step_number=obs_data.get("step_number", 0),
            task_name=obs_data.get("task_name", ""),
            task_description=obs_data.get("task_description", ""),
            available_files=obs_data.get("available_files", []),
            done=payload.get("done", False),
            reward=payload.get("reward"),
            metadata=obs_data.get("metadata", {}),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> State:
        """Parse server response into State object."""
        return State(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
        )
