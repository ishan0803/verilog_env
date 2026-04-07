"""
Metrics Query Tool Wrapper.

Aggregates PPA (Power, Performance, Area) metrics from the latest
synthesis and timing analysis results into a normalized dashboard.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class PPADashboard:
    """Aggregated PPA metrics dashboard."""
    success: bool = False
    area: float = 0.0
    area_delta_pct: float = 0.0  # vs baseline
    power_estimate: float = 0.0
    power_delta_pct: float = 0.0
    wns: float = 0.0
    timing_met: bool = False
    num_cells: int = 0
    num_wires: int = 0
    raw_output: str = ""


# Simple power model coefficients
DYNAMIC_POWER_PER_CELL = 0.001  # mW per cell (estimated)
LEAKAGE_POWER_PER_CELL = 0.0002  # mW per cell (estimated)

# Higher-power cell types
HIGH_POWER_CELLS = {
    "$_DFF_": 5.0, "$_DFFE_": 6.0, "$_SDFF_": 6.0,
    "$_DLATCH_": 4.0, "$mem": 10.0, "$memrd": 5.0,
    "$memwr": 5.0, "$mul": 8.0, "$div": 12.0,
}


def query_metrics(
    metric_type: str,
    synthesis_stats: Optional[Dict[str, Any]] = None,
    timing_report: Optional[Dict[str, Any]] = None,
    baseline_metrics: Optional[Dict[str, Any]] = None,
) -> PPADashboard:
    """Query aggregated PPA metrics.

    Args:
        metric_type: Type of metric — "area", "power", "timing", or "all".
        synthesis_stats: Latest synthesis statistics dict.
        timing_report: Latest timing report dict.
        baseline_metrics: Baseline PPA for delta computation.

    Returns:
        PPADashboard with requested metrics.
    """
    dashboard = PPADashboard()

    if synthesis_stats is None and metric_type in ("area", "power", "all"):
        dashboard.raw_output = (
            "Error: No synthesis data available. Run run_synthesis first."
        )
        return dashboard

    if timing_report is None and metric_type in ("timing", "all"):
        dashboard.raw_output = (
            "Error: No timing data available. Run run_timing_analysis first."
        )
        return dashboard

    # Area metrics
    if metric_type in ("area", "all") and synthesis_stats:
        dashboard.num_cells = synthesis_stats.get("num_cells", 0)
        dashboard.num_wires = synthesis_stats.get("num_wires", 0)
        dashboard.area = synthesis_stats.get("area_estimate", 0.0)

        if baseline_metrics and baseline_metrics.get("area", 0) > 0:
            dashboard.area_delta_pct = (
                (dashboard.area - baseline_metrics["area"])
                / baseline_metrics["area"]
                * 100.0
            )

    # Power metrics
    if metric_type in ("power", "all") and synthesis_stats:
        cell_counts = synthesis_stats.get("cell_counts", {})
        total_power = 0.0
        for cell_type, count in cell_counts.items():
            multiplier = HIGH_POWER_CELLS.get(cell_type, 1.0)
            total_power += count * (
                DYNAMIC_POWER_PER_CELL * multiplier
                + LEAKAGE_POWER_PER_CELL
            )
        if total_power == 0.0:
            total_power = dashboard.num_cells * (
                DYNAMIC_POWER_PER_CELL + LEAKAGE_POWER_PER_CELL
            )
        dashboard.power_estimate = round(total_power, 4)

        if baseline_metrics and baseline_metrics.get("power", 0) > 0:
            dashboard.power_delta_pct = (
                (dashboard.power_estimate - baseline_metrics["power"])
                / baseline_metrics["power"]
                * 100.0
            )

    # Timing metrics
    if metric_type in ("timing", "all") and timing_report:
        dashboard.wns = timing_report.get("wns", 0.0)
        dashboard.timing_met = timing_report.get("timing_met", False)

    # Build output
    lines = ["=== PPA Metrics Dashboard ==="]
    if metric_type in ("area", "all"):
        lines.extend([
            f"Area: {dashboard.area:.1f} units ({dashboard.area_delta_pct:+.1f}% vs baseline)",
            f"Cells: {dashboard.num_cells}, Wires: {dashboard.num_wires}",
        ])
    if metric_type in ("power", "all"):
        lines.extend([
            f"Power: {dashboard.power_estimate:.4f} mW ({dashboard.power_delta_pct:+.1f}% vs baseline)",
        ])
    if metric_type in ("timing", "all"):
        lines.extend([
            f"WNS: {dashboard.wns:.3f} ns",
            f"Timing Met: {'YES' if dashboard.timing_met else 'NO'}",
        ])

    dashboard.raw_output = "\n".join(lines)
    dashboard.success = True

    return dashboard
