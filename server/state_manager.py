"""
Git-backed Episodic State Manager.

Provides isolated workspaces per episode with git-based versioning
for rollback support. Each step that modifies files is committed,
enabling rollback_version(step_id) to restore exact prior states.

Uses Pydantic models for all internal caches to prevent KeyError crashes
from untyped dict access.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


# ─── Typed Cache Models ────────────────────────────────────────────────
# These replace raw Dict[str, Any] to prevent KeyError crashes and
# enforce type safety across the reward function, tools, and environment.


class CompileCache(BaseModel):
    """Cached result from compile_and_lint."""
    success: bool = False
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class SynthesisCache(BaseModel):
    """Cached result from run_synthesis."""
    num_cells: int = 0
    num_wires: int = 0
    area_estimate: float = 0.0
    cell_counts: Dict[str, int] = Field(default_factory=dict)


class TimingCache(BaseModel):
    """Cached result from run_timing_analysis."""
    wns: float = 0.0
    tns: float = 0.0
    timing_met: bool = False
    critical_path_delay_ns: float = 0.0


class SimulationCache(BaseModel):
    """Cached result from run_simulation."""
    success: bool = False
    pass_rate: float = 0.0
    passed: int = 0
    failed: int = 0
    total: int = 0


@dataclass
class EpisodeState:
    """Internal state for one episode."""
    episode_id: str = ""
    task_id: str = ""
    task_name: str = ""
    step_count: int = 0
    workspace_dir: str = ""

    # Cached EDA results (invalidated on RTL modification)
    # Using typed Pydantic models instead of raw dicts
    compile_result: Optional[CompileCache] = None
    synthesis_stats: Optional[SynthesisCache] = None
    timing_report: Optional[TimingCache] = None
    simulation_result: Optional[SimulationCache] = None

    # Baseline metrics (set on reset)
    baseline_metrics: Dict[str, Any] = field(default_factory=dict)

    # History
    action_history: List[Dict[str, Any]] = field(default_factory=list)
    reward_history: List[float] = field(default_factory=list)

    # Error tracking for loop detection
    previous_errors: Set[str] = field(default_factory=set)
    current_errors: Set[str] = field(default_factory=set)

    # Hidden constraints (never exposed to agent)
    hidden_constraints: Dict[str, Any] = field(default_factory=dict)

    # Files modified since last compile
    dirty_files: Set[str] = field(default_factory=set)

    # Stale cache flags
    compile_stale: bool = True
    synthesis_stale: bool = True
    timing_stale: bool = True
    simulation_stale: bool = True

    done: bool = False


class StateManager:
    """Manages isolated workspaces with git-backed versioning.

    Each episode gets a dedicated workspace directory with its own
    git repository. Temp directories are scoped per-instance to avoid
    concurrency conflicts with the global /tmp.
    """

    def __init__(self, base_temp_dir: Optional[str] = None):
        # Scope the temp directory per-instance to avoid concurrency issues
        # with multiple agents sharing the global /tmp
        if base_temp_dir:
            self._base_dir = base_temp_dir
        else:
            self._base_dir = tempfile.mkdtemp(prefix="eda_env_")
        os.makedirs(self._base_dir, exist_ok=True)
        self._episodes: Dict[str, EpisodeState] = {}

    def create_episode(
        self,
        episode_id: str,
        task_id: str,
        task_name: str,
        source_dir: str,
        hidden_constraints: Optional[Dict[str, Any]] = None,
    ) -> EpisodeState:
        """Create a new episode workspace.

        Args:
            episode_id: Unique episode identifier.
            task_id: Task identifier (task_1, task_2, task_3).
            task_name: Human-readable task name.
            source_dir: Path to task's baseline_rtl directory.
            hidden_constraints: Hidden design constraints (never sent to agent).

        Returns:
            Initialized EpisodeState.
        """
        workspace = os.path.join(self._base_dir, f"eda_ws_{episode_id[:8]}")

        # Create workspace structure
        os.makedirs(workspace, exist_ok=True)
        rtl_dest = os.path.join(workspace, "rtl")
        os.makedirs(rtl_dest, exist_ok=True)

        # Copy baseline RTL files
        if os.path.isdir(source_dir):
            for f in os.listdir(source_dir):
                src = os.path.join(source_dir, f)
                dst = os.path.join(rtl_dest, f)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)

        # Initialize git repo
        self._git_init(workspace)

        state = EpisodeState(
            episode_id=episode_id,
            task_id=task_id,
            task_name=task_name,
            workspace_dir=workspace,
            hidden_constraints=hidden_constraints or {},
        )

        self._episodes[episode_id] = state
        return state

    def get_state(self, episode_id: str) -> Optional[EpisodeState]:
        """Get the current state for an episode."""
        return self._episodes.get(episode_id)

    def increment_step(self, episode_id: str) -> int:
        """Increment and return the step count."""
        state = self._episodes.get(episode_id)
        if state:
            state.step_count += 1
            return state.step_count
        return 0

    def invalidate_caches(self, episode_id: str, file_path: str) -> None:
        """Mark all cached EDA results as stale after a file modification."""
        state = self._episodes.get(episode_id)
        if state:
            state.compile_stale = True
            state.synthesis_stale = True
            state.timing_stale = True
            state.simulation_stale = True
            state.dirty_files.add(file_path)

    def commit_step(self, episode_id: str, message: str) -> bool:
        """Git commit the current workspace state.

        Args:
            episode_id: Episode identifier.
            message: Commit message (includes step number).

        Returns:
            True if commit succeeded.
        """
        state = self._episodes.get(episode_id)
        if not state:
            return False

        try:
            ws = state.workspace_dir
            subprocess.run(
                ["git", "add", "-A"],
                cwd=ws, capture_output=True, timeout=5,
            )
            subprocess.run(
                ["git", "commit", "-m", message, "--allow-empty"],
                cwd=ws, capture_output=True, timeout=5,
            )
            # Tag with step number for rollback
            subprocess.run(
                ["git", "tag", f"step_{state.step_count}"],
                cwd=ws, capture_output=True, timeout=5,
            )
            state.dirty_files.clear()
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def rollback(self, episode_id: str, step_id: int) -> bool:
        """Rollback workspace to state at step_id.

        Restores tracked files via git checkout AND removes untracked files
        via git clean to prevent workspace pollution from agent-created
        garbage files.

        Args:
            episode_id: Episode identifier.
            step_id: Step number to rollback to.

        Returns:
            True if rollback succeeded.
        """
        state = self._episodes.get(episode_id)
        if not state:
            return False

        tag = f"step_{step_id}"
        try:
            # Restore tracked files to the tagged state
            proc = subprocess.run(
                ["git", "checkout", tag, "--", "."],
                cwd=state.workspace_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode != 0:
                return False

            # Remove untracked files and directories to prevent
            # workspace pollution from agent-created artifacts
            clean_proc = subprocess.run(
                ["git", "clean", "-fd"],
                cwd=state.workspace_dir,
                capture_output=True,
                text=True,
                timeout=10,
            )
            # git clean failure is non-fatal but logged
            if clean_proc.returncode != 0:
                pass  # Best-effort cleanup

            # Invalidate all caches after rollback
            state.compile_stale = True
            state.synthesis_stale = True
            state.timing_stale = True
            state.simulation_stale = True
            state.dirty_files.clear()
            return True

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def get_workspace_diff(self, episode_id: str) -> List[str]:
        """Get list of files modified since last commit."""
        state = self._episodes.get(episode_id)
        if not state:
            return []

        try:
            proc = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=state.workspace_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if proc.returncode == 0:
                return [f.strip() for f in proc.stdout.strip().splitlines() if f.strip()]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return list(state.dirty_files)

    def list_workspace_files(self, episode_id: str) -> List[str]:
        """List all files in the workspace."""
        state = self._episodes.get(episode_id)
        if not state:
            return []

        files = []
        for root, _, filenames in os.walk(state.workspace_dir):
            for fn in filenames:
                rel = os.path.relpath(os.path.join(root, fn), state.workspace_dir)
                if not rel.startswith(".git"):
                    files.append(rel)
        return sorted(files)

    def record_action(
        self, episode_id: str, action: Dict[str, Any], reward: float
    ) -> None:
        """Record an action and reward in the episode history."""
        state = self._episodes.get(episode_id)
        if state:
            state.action_history.append(action)
            state.reward_history.append(reward)

    def cleanup_episode(self, episode_id: str) -> None:
        """Clean up workspace for an episode."""
        state = self._episodes.pop(episode_id, None)
        if state and os.path.isdir(state.workspace_dir):
            shutil.rmtree(state.workspace_dir, ignore_errors=True)

    def _git_init(self, workspace: str) -> None:
        """Initialize a git repo in the workspace."""
        try:
            subprocess.run(
                ["git", "init"],
                cwd=workspace, capture_output=True, timeout=5,
            )
            # Use repo-level config (not global) to avoid concurrency conflicts
            subprocess.run(
                ["git", "config", "user.email", "eda-env@openenv.local"],
                cwd=workspace, capture_output=True, timeout=5,
            )
            subprocess.run(
                ["git", "config", "user.name", "EDA-Env"],
                cwd=workspace, capture_output=True, timeout=5,
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=workspace, capture_output=True, timeout=5,
            )
            subprocess.run(
                ["git", "commit", "-m", "Initial baseline", "--allow-empty"],
                cwd=workspace, capture_output=True, timeout=5,
            )
            subprocess.run(
                ["git", "tag", "step_0"],
                cwd=workspace, capture_output=True, timeout=5,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass  # Git not available — state tracking via dirty_files fallback
