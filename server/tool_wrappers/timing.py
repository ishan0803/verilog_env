"""
Timing Analysis Tool Wrapper.

Performs analytical timing estimation from Yosys synthesis output.
Estimates critical path delay by separating combinational and sequential
elements: DFFs reduce effective path depth (pipelining), while combinational
cells contribute to it.

NOTE: This remains a heuristic model. Real STA requires liberty (.lib) files
and a proper timing graph. This model is designed to not *actively punish*
correct optimizations (e.g., pipelining) as the previous sqrt(N) model did.
"""

import math
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TimingReport:
    """Result of timing analysis."""
    success: bool = False
    clock_period_ns: float = 0.0
    critical_path_delay_ns: float = 0.0
    wns: float = 0.0  # Worst Negative Slack
    tns: float = 0.0  # Total Negative Slack
    timing_met: bool = False
    critical_path_cells: List[str] = field(default_factory=list)
    fanout_violations: List[str] = field(default_factory=list)
    raw_output: str = ""


# Cell delay model (in nanoseconds) — simplified NanGate45
CELL_DELAYS = {
    "$_AND_": 0.04, "$_OR_": 0.04, "$_XOR_": 0.08,
    "$_NOT_": 0.02, "$_MUX_": 0.06, "$_NAND_": 0.03,
    "$_NOR_": 0.03, "$_XNOR_": 0.08, "$_DFF_": 0.10,
    "$_DFFE_": 0.12, "$_SDFF_": 0.12, "$_DLATCH_": 0.08,
    "$_BUF_": 0.02, "$_AOI3_": 0.05, "$_OAI3_": 0.05,
    "$_AOI4_": 0.06, "$_OAI4_": 0.06,
    # Arithmetic cells (larger delays)
    "$add": 0.15, "$sub": 0.15, "$mul": 0.50,
    "$div": 1.00, "$mod": 1.00, "$shl": 0.10,
    "$shr": 0.10, "$sshl": 0.12, "$sshr": 0.12,
    # Comparison
    "$eq": 0.10, "$ne": 0.10, "$lt": 0.12,
    "$le": 0.12, "$gt": 0.12, "$ge": 0.12,
    # Logic
    "$and": 0.04, "$or": 0.04, "$xor": 0.08,
    "$not": 0.02, "$reduce_and": 0.06, "$reduce_or": 0.06,
    "$mux": 0.06, "$pmux": 0.10,
    # Memory
    "$mem": 0.50, "$memrd": 0.30, "$memwr": 0.30,
}

# Sequential element types — these define pipeline stage boundaries
SEQUENTIAL_CELLS = {"$_DFF_", "$_DFFE_", "$_SDFF_", "$_DLATCH_"}

MAX_FANOUT = 16


def run_timing_analysis(
    clock_period_ns: float,
    workspace_dir: str,
    synthesis_stats: Optional[Dict] = None,
    hidden_constraints: Optional[Dict] = None,
) -> TimingReport:
    """Perform analytical timing analysis.

    Estimates critical path delay by separating sequential (DFF) elements
    from combinational logic. Pipeline stages (DFF boundaries) divide
    the combinational depth, so adding DFFs correctly reduces the critical
    path delay — matching the expected behavior when an agent pipelines.

    Args:
        clock_period_ns: Target clock period in nanoseconds.
        workspace_dir: Root workspace directory.
        synthesis_stats: Cell count dict from synthesis (if available).
        hidden_constraints: Hidden design rules (max_fanout, max_slew, etc.)

    Returns:
        TimingReport with WNS, TNS, and fanout violations.
    """
    report = TimingReport()
    report.clock_period_ns = clock_period_ns

    if synthesis_stats is None:
        report.raw_output = (
            "Error: No synthesis data available. Run synthesis first."
        )
        return report

    cell_counts = synthesis_stats.get("cell_counts", {})
    num_cells = synthesis_stats.get("num_cells", 0)

    if num_cells == 0:
        report.raw_output = "Error: Design has no cells. Nothing to analyze."
        return report

    # ─── Separate combinational and sequential cells ───────────────
    comb_delay_total = 0.0
    comb_cell_count = 0
    seq_cell_count = 0
    critical_cells = []

    for cell_type, count in cell_counts.items():
        delay = CELL_DELAYS.get(cell_type, 0.05)

        if cell_type in SEQUENTIAL_CELLS:
            # Sequential elements define pipeline stage boundaries
            seq_cell_count += count
        else:
            # Combinational cells contribute to path delay
            comb_delay_total += delay * count
            comb_cell_count += count

        if delay > 0.10:
            critical_cells.append(f"{cell_type} (x{count}, {delay:.2f}ns each)")

    # ─── Estimate critical path delay ──────────────────────────────
    # Pipeline stages = max(1, number of DFF boundaries)
    # Each stage gets a proportional share of the combinational depth.
    pipeline_stages = max(1, seq_cell_count)

    # Combinational depth per stage: sqrt of comb cells / pipeline stages
    # Using sqrt because not all comb cells are on the critical path
    if comb_cell_count > 0:
        avg_comb_delay = comb_delay_total / comb_cell_count
        comb_depth_per_stage = math.sqrt(comb_cell_count / pipeline_stages) * 0.8
        estimated_path_delay = comb_depth_per_stage * avg_comb_delay
    else:
        estimated_path_delay = 0.0

    # Add DFF setup time for sequential designs (one DFF on the path)
    if seq_cell_count > 0:
        dff_setup = CELL_DELAYS.get("$_DFF_", 0.10)
        estimated_path_delay += dff_setup

    report.critical_path_delay_ns = round(estimated_path_delay, 3)
    report.critical_path_cells = critical_cells[:10]

    # WNS = clock_period - critical_path_delay (positive = timing met)
    report.wns = round(clock_period_ns - report.critical_path_delay_ns, 3)
    report.tns = min(0.0, report.wns)  # Only negative slack contributes
    report.timing_met = report.wns >= 0.0

    # Check hidden constraints
    if hidden_constraints:
        max_fanout = hidden_constraints.get("max_fanout", MAX_FANOUT)
        # Estimate fanout from cell ratios
        if num_cells > 0:
            num_wires = synthesis_stats.get("num_wires", num_cells)
            avg_fanout = num_wires / max(num_cells, 1)
            if avg_fanout > max_fanout:
                report.fanout_violations.append(
                    f"Average fanout {avg_fanout:.1f} exceeds max {max_fanout}"
                )

    # Build human-readable report
    lines = [
        f"=== Timing Analysis Report ===",
        f"Target Clock Period: {clock_period_ns:.3f} ns",
        f"Estimated Critical Path Delay: {report.critical_path_delay_ns:.3f} ns",
        f"WNS (Worst Negative Slack): {report.wns:.3f} ns",
        f"TNS (Total Negative Slack): {report.tns:.3f} ns",
        f"Timing Met: {'YES' if report.timing_met else 'NO'}",
        f"Pipeline Stages (DFF boundaries): {seq_cell_count}",
        f"Combinational Cells: {comb_cell_count}",
        f"",
        f"Critical Path Contributors:",
    ]
    for cc in report.critical_path_cells:
        lines.append(f"  - {cc}")

    if report.fanout_violations:
        lines.append("")
        lines.append("DRC Violations:")
        for v in report.fanout_violations:
            lines.append(f"  - {v}")

    report.raw_output = "\n".join(lines)
    report.success = True

    return report
