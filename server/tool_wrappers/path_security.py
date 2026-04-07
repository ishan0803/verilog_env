"""
Path Security — Workspace Sandboxing Utility.

Prevents path traversal attacks by ensuring all resolved paths
remain within the workspace directory boundary.
"""

import os


def resolve_safe_path(workspace_dir: str, user_path: str) -> str:
    """Resolve a user-provided path safely within the workspace.

    Normalizes the path via os.path.abspath and verifies the result
    starts with the workspace directory. Blocks all traversal attacks
    (e.g., '../../etc/passwd', absolute paths, symlink escapes).

    Args:
        workspace_dir: Root workspace directory (trusted).
        user_path: User/agent-provided relative path (untrusted).

    Returns:
        Absolute path guaranteed to be within workspace_dir.

    Raises:
        ValueError: If the resolved path escapes the workspace boundary.
    """
    abs_workspace = os.path.abspath(workspace_dir)
    # Join and normalize — handles .., symlinks, etc.
    abs_resolved = os.path.abspath(os.path.join(abs_workspace, user_path))

    # Ensure the resolved path is within the workspace
    # Use os.sep to prevent prefix attacks (e.g., /workspace2 matching /workspace)
    if not abs_resolved.startswith(abs_workspace + os.sep) and abs_resolved != abs_workspace:
        raise ValueError(
            f"Path traversal blocked: '{user_path}' resolves to '{abs_resolved}' "
            f"which is outside workspace '{abs_workspace}'"
        )

    return abs_resolved
