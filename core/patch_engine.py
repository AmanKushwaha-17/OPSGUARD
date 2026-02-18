import os
import difflib


def apply_full_file_patch(workspace_path: str, filename: str, new_content: str) -> dict:
    """
    Replaces the entire file content inside the workspace.

    Returns:
        {
            "success": bool,
            "diff": str
        }
    """

    file_path = os.path.join(workspace_path, filename)

    if not os.path.exists(file_path):
        return {
            "success": False,
            "diff": ""
        }

    # Read original content
    with open(file_path, "r") as f:
        original_content = f.read()

    # Compute diff for logging (optional but useful)
    diff = difflib.unified_diff(
        original_content.splitlines(),
        new_content.splitlines(),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    )

    diff_text = "\n".join(diff)

    # Write new content
    with open(file_path, "w") as f:
        f.write(new_content)

    return {
        "success": True,
        "diff": diff_text
    }
