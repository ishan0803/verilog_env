"""Grader determinism tests."""

import pytest


class TestGraderDeterminism:
    """Graders must produce identical scores for identical inputs."""

    def test_task1_grader_import(self):
        from graders import Task1Grader
        assert Task1Grader is not None

    def test_task2_grader_import(self):
        from graders import Task2Grader
        assert Task2Grader is not None

    def test_task3_grader_import(self):
        from graders import Task3Grader
        assert Task3Grader is not None

    def test_base_grader_scoring_weights(self):
        from graders.grader_base import BaseGrader
        total = (
            BaseGrader.W_FUNCTIONAL
            + BaseGrader.W_PPA
            + BaseGrader.W_TIMING
            + BaseGrader.W_STABILITY
        )
        assert total == pytest.approx(1.0)

    def test_trajectory_stability_full_score(self):
        """Empty history should get full stability score."""
        from graders.grader_base import BaseGrader
        import os
        grader = BaseGrader(
            task_dir=os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "tasks", "task_1"
            )
        )
        score = grader._evaluate_trajectory_stability([])
        assert score == 1.0

    def test_trajectory_stability_penalizes_loops(self):
        """Compile-error loops should reduce stability score."""
        from graders.grader_base import BaseGrader
        import os
        grader = BaseGrader(
            task_dir=os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "tasks", "task_1"
            )
        )
        history = [
            {"tool_name": "compile_and_lint", "success": False},
            {"tool_name": "compile_and_lint", "success": False},
            {"tool_name": "compile_and_lint", "success": False},
            {"tool_name": "compile_and_lint", "success": False},
            {"tool_name": "compile_and_lint", "success": False},
            {"tool_name": "compile_and_lint", "success": False},
        ]
        score = grader._evaluate_trajectory_stability(history)
        assert score < 1.0
