"""
Constraint Adjuster Tool Wrapper.

Modifies SDC (Synopsys Design Constraints) files —
clock period, max fanout, max transition, and other constraints.
"""

import os
import re
from dataclasses import dataclass, field
from typing import List

from .path_security import resolve_safe_path


@dataclass
class ValidationLog:
    """Result of constraint adjustment."""
    success: bool = False
    raw_output: str = ""
    modifications_applied: List[str] = field(default_factory=list)
    validation_warnings: List[str] = field(default_factory=list)


def adjust_constraints(
    constraint_file: str,
    modifications: str,
    workspace_dir: str,
) -> ValidationLog:
    """Modify an SDC constraint file.

    Supports modifications in the format:
        set_clock_period <value_ns>
        set_max_fanout <value>
        set_max_transition <value_ns>
        add_constraint <raw SDC command>
        remove_constraint <pattern>

    Args:
        constraint_file: Path to SDC file (relative to workspace_dir).
        modifications: Newline-separated modification commands.
        workspace_dir: Root workspace directory.

    Returns:
        ValidationLog with applied modifications and any warnings.
    """
    result = ValidationLog()

    try:
        abs_path = resolve_safe_path(workspace_dir, constraint_file)
    except ValueError as e:
        result.raw_output = f"Error: {e}"
        return result

    if not os.path.isfile(abs_path):
        result.raw_output = f"Error: Constraint file not found: {constraint_file}"
        return result

    try:
        with open(abs_path, "r") as f:
            content = f.read()
            lines = content.splitlines()
    except OSError as e:
        result.raw_output = f"Error reading file: {e}"
        return result

    new_lines = list(lines)

    for mod_line in modifications.strip().splitlines():
        mod_line = mod_line.strip()
        if not mod_line or mod_line.startswith("#"):
            continue

        if mod_line.startswith("set_clock_period"):
            # Modify create_clock -period
            parts = mod_line.split()
            if len(parts) >= 2:
                try:
                    new_period = float(parts[1])
                    for i, line in enumerate(new_lines):
                        if "create_clock" in line and "-period" in line:
                            new_lines[i] = re.sub(
                                r"-period\s+[\d.]+",
                                f"-period {new_period}",
                                line,
                            )
                            result.modifications_applied.append(
                                f"Clock period set to {new_period} ns"
                            )
                            break
                    else:
                        # Add new clock constraint
                        new_lines.append(
                            f"create_clock -period {new_period} [get_ports clk]"
                        )
                        result.modifications_applied.append(
                            f"Added clock constraint: {new_period} ns"
                        )
                except ValueError:
                    result.validation_warnings.append(
                        f"Invalid clock period: {parts[1]}"
                    )

        elif mod_line.startswith("set_max_fanout"):
            parts = mod_line.split()
            if len(parts) >= 2:
                try:
                    fanout = int(parts[1])
                    # Remove existing max_fanout
                    new_lines = [
                        l for l in new_lines if "set_max_fanout" not in l
                    ]
                    new_lines.append(
                        f"set_max_fanout {fanout} [current_design]"
                    )
                    result.modifications_applied.append(
                        f"Max fanout set to {fanout}"
                    )
                except ValueError:
                    result.validation_warnings.append(
                        f"Invalid fanout value: {parts[1]}"
                    )

        elif mod_line.startswith("set_max_transition"):
            parts = mod_line.split()
            if len(parts) >= 2:
                try:
                    transition = float(parts[1])
                    new_lines = [
                        l for l in new_lines if "set_max_transition" not in l
                    ]
                    new_lines.append(
                        f"set_max_transition {transition} [current_design]"
                    )
                    result.modifications_applied.append(
                        f"Max transition set to {transition} ns"
                    )
                except ValueError:
                    result.validation_warnings.append(
                        f"Invalid transition value: {parts[1]}"
                    )

        elif mod_line.startswith("add_constraint"):
            raw_cmd = mod_line[len("add_constraint"):].strip()
            if raw_cmd:
                new_lines.append(raw_cmd)
                result.modifications_applied.append(f"Added: {raw_cmd}")
            else:
                result.validation_warnings.append(
                    "Empty add_constraint command"
                )

        elif mod_line.startswith("remove_constraint"):
            pattern = mod_line[len("remove_constraint"):].strip()
            if pattern:
                original_count = len(new_lines)
                new_lines = [
                    l for l in new_lines
                    if pattern not in l
                ]
                removed = original_count - len(new_lines)
                result.modifications_applied.append(
                    f"Removed {removed} line(s) matching '{pattern}'"
                )
            else:
                result.validation_warnings.append(
                    "Empty remove_constraint pattern"
                )
        else:
            result.validation_warnings.append(
                f"Unknown modification command: {mod_line}"
            )

    # Write modified file
    try:
        with open(abs_path, "w") as f:
            f.write("\n".join(new_lines) + "\n")
        result.success = True

        # Build output
        lines_out = ["=== Constraint Modification Report ==="]
        for m in result.modifications_applied:
            lines_out.append(f"  ✓ {m}")
        for w in result.validation_warnings:
            lines_out.append(f"  ⚠ {w}")
        result.raw_output = "\n".join(lines_out)

    except OSError as e:
        result.raw_output = f"Error writing file: {e}"

    return result
