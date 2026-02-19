from core.workspace import create_workspace, cleanup_workspace
from core.docker_executor import execute_python
from core.patch_engine import apply_full_file_patch


workspace = create_workspace("demo_repo")

print("Workspace:", workspace)

# Step 1 — Reproduce failure
print("\n[STEP 1] Reproduction run...")
result = execute_python(workspace, "app.py")
print("Exit Code:", result["exit_code"])
print("STDERR:", result["stderr"])


# Step 2 — Apply patch using patch engine
print("\n[STEP 2] Applying patch via Patch Engine...")

new_content = """def parse_input(value):
    try:
        return int(value)
    except ValueError:
        return 0

if __name__ == "__main__":
    print(parse_input("abc"))
"""

patch_result = apply_full_file_patch(workspace, "app.py", new_content)

print("Patch applied:", patch_result["success"])
print("Generated Diff:\n", patch_result["diff"])


# Step 3 — Re-run after patch
print("\n[STEP 3] Re-run after patch...")
result = execute_python(workspace, "app.py")
print("Exit Code:", result["exit_code"])
print("STDOUT:", result["stdout"])
print("STDERR:", result["stderr"])

cleanup_workspace(workspace)

print("\nWorkspace cleaned up.")
