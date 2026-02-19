import os
import difflib


def apply_full_file_patch(workspace_path: str, filename: str, new_content: str) -> dict:
    file_path = os.path.join(workspace_path, filename)

    if not os.path.exists(file_path):
        return {
            "success": False,
            "diff": "",
            "changed_blocks": [],
        }

    with open(file_path, "r", encoding="utf-8") as f:
        original_content = f.read()

    original_lines = original_content.splitlines()
    new_lines = new_content.splitlines()

    diff = list(
        difflib.unified_diff(
            original_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )
    diff_text = "\n".join(diff)

    changed_blocks = []
    matcher = difflib.SequenceMatcher(None, original_lines, new_lines)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete", "insert"):
            before_block = "\n".join(original_lines[i1:i2]).strip()
            after_block = "\n".join(new_lines[j1:j2]).strip()

            changed_blocks.append(
                {
                    "line_number": i1 + 1,
                    "before": before_block,
                    "after": after_block,
                }
            )

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    return {
        "success": True,
        "diff": diff_text,
        "changed_blocks": changed_blocks,
    }
