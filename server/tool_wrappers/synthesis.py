"""
Synthesis Tool Wrapper.

Runs Yosys logic synthesis with 'synth' and extracts area/cell statistics
via 'stat -json'. Supports configurable effort levels and flatten options.
"""

import subprocess
import os
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

SYNTHESIS_TIMEOUT = 120  # seconds
MAX_OUTPUT_CHARS = 4000


@dataclass
class SynthesisStats:
    """Result of Yosys synthesis."""
    success: bool = False
    exit_code: int = -1
    num_cells: int = 0
    num_wires: int = 0
    area_estimate: float = 0.0
    cell_counts: Dict[str, int] = field(default_factory=dict)
    raw_json: Dict[str, Any] = field(default_factory=dict)
    raw_output: str = ""


def run_synthesis(
    workspace_dir: str,
    effort_level: str = "medium",
    flatten: bool = False,
    target_file: Optional[str] = None,
) -> SynthesisStats:
    """Run Yosys synthesis on Verilog files in the workspace.

    Args:
        workspace_dir: Root workspace directory.
        effort_level: Synthesis effort — "low", "medium", "high".
        flatten: Whether to flatten the design hierarchy.
        target_file: Specific Verilog file to synthesize (relative to workspace).
                     If None, synthesizes all .v files in rtl/ directory.

    Returns:
        SynthesisStats with cell counts, area estimate, and bounded output.
    """
    result = SynthesisStats()

    # Find Verilog files
    if target_file:
        verilog_files = [os.path.join(workspace_dir, target_file)]
    else:
        rtl_dir = os.path.join(workspace_dir, "rtl")
        if os.path.isdir(rtl_dir):
            verilog_files = [
                os.path.join(rtl_dir, f)
                for f in sorted(os.listdir(rtl_dir))
                if f.endswith(".v") or f.endswith(".sv")
            ]
        else:
            verilog_files = [
                os.path.join(workspace_dir, f)
                for f in sorted(os.listdir(workspace_dir))
                if f.endswith(".v") and not f.startswith("tb_")
            ]

    if not verilog_files:
        result.raw_output = "Error: No Verilog files found for synthesis"
        return result

    for vf in verilog_files:
        if not os.path.isfile(vf):
            result.raw_output = f"Error: File not found: {vf}"
            return result

    # Build Yosys script
    read_cmds = "\n".join(f"read_verilog -sv {vf}" for vf in verilog_files)

    # Effort-based optimization
    opt_cmds = {
        "low": "synth -run coarse",
        "medium": "synth",
        "high": "synth; opt -full; clean -purge",
    }.get(effort_level, "synth")

    flatten_cmd = "flatten;" if flatten else ""
    json_path = os.path.join(workspace_dir, "_synth_stats.json")

    yosys_script = f"""
{read_cmds}
{flatten_cmd}
{opt_cmds}
stat -json {json_path}
stat
"""

    try:
        proc = subprocess.run(
            ["yosys", "-p", yosys_script],
            capture_output=True,
            text=True,
            timeout=SYNTHESIS_TIMEOUT,
            cwd=workspace_dir,
        )

        result.exit_code = proc.returncode
        output = proc.stdout + "\n" + proc.stderr
        result.raw_output = output.strip()[:MAX_OUTPUT_CHARS]

        if proc.returncode != 0:
            return result

        result.success = True

        # Parse JSON stats if available
        if os.path.isfile(json_path):
            try:
                with open(json_path, "r") as f:
                    stats = json.load(f)
                result.raw_json = stats

                # Extract cell and wire counts from the stats
                if "modules" in stats:
                    for mod_name, mod_data in stats["modules"].items():
                        if "num_cells" in mod_data:
                            result.num_cells += mod_data["num_cells"]
                        if "num_wires" in mod_data:
                            result.num_wires += mod_data["num_wires"]
                        if "cell_types" in mod_data:
                            for ct, cnt in mod_data["cell_types"].items():
                                result.cell_counts[ct] = (
                                    result.cell_counts.get(ct, 0) + cnt
                                )
            except (json.JSONDecodeError, KeyError):
                pass
            finally:
                os.unlink(json_path)

        # Fallback: parse stat output from text
        if result.num_cells == 0:
            cells_match = re.search(
                r"Number of cells:\s+(\d+)", result.raw_output
            )
            wires_match = re.search(
                r"Number of wires:\s+(\d+)", result.raw_output
            )
            if cells_match:
                result.num_cells = int(cells_match.group(1))
            if wires_match:
                result.num_wires = int(wires_match.group(1))

        # Estimate area: simple model — each cell ≈ 1.0 unit area
        # More sophisticated estimation with cell type weighting
        area_weights = {
            "$_AND_": 1.0, "$_OR_": 1.0, "$_XOR_": 1.5,
            "$_NOT_": 0.5, "$_MUX_": 2.0, "$_NAND_": 1.0,
            "$_NOR_": 1.0, "$_XNOR_": 1.5, "$_DFF_": 4.0,
            "$_DFFE_": 5.0, "$_SDFF_": 5.5, "$_DLATCH_": 3.5,
        }
        if result.cell_counts:
            for cell_type, count in result.cell_counts.items():
                weight = area_weights.get(cell_type, 2.0)
                result.area_estimate += count * weight
        else:
            result.area_estimate = result.num_cells * 2.0

    except subprocess.TimeoutExpired:
        result.raw_output = f"Error: Synthesis timed out after {SYNTHESIS_TIMEOUT}s"
        result.exit_code = 124
    except FileNotFoundError:
        result.raw_output = (
            "Error: yosys not found. EDA tools are only available inside the Docker container."
        )
        result.exit_code = 127

    return result
