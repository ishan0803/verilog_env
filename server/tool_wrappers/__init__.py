"""EDA Tool Wrappers — subprocess-based interfaces to EDA toolchain."""

from .path_security import resolve_safe_path
from .compile_lint import compile_and_lint
from .simulation import run_simulation
from .synthesis import run_synthesis
from .timing import run_timing_analysis
from .metrics import query_metrics
from .rtl_modifier import modify_rtl
from .constraint_adjuster import adjust_constraints

__all__ = [
    "resolve_safe_path",
    "compile_and_lint",
    "run_simulation",
    "run_synthesis",
    "run_timing_analysis",
    "query_metrics",
    "modify_rtl",
    "adjust_constraints",
]

