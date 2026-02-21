from core.state import OpsGuardState, Status, ErrorType
from core.workspace import create_workspace
from core.docker_executor import execute_python
from core.patch_engine import apply_full_file_patch
from core.error_classifier import classify_error
import ast
import difflib
import os
import json
import subprocess
import sys
from datetime import datetime


from core.logger import log_event

def classify_error_node(state: OpsGuardState) -> OpsGuardState:
    log_event("classify_error", "Starting error classification")

    result = classify_error(state.error_log)
    state.error_type = ErrorType(result["type"])

    log_event(
        "classify_error",
        "Error classified",
        {"error_type": state.error_type.value}
    )

    return state


def generate_infra_report_node(state: OpsGuardState) -> OpsGuardState:
    # In production this would generate structured report
    state.status = Status.INFRA_STOP
    return state



def setup_workspace_node(state: OpsGuardState) -> OpsGuardState:
    log_event("setup_workspace", "Creating isolated workspace")

    state.workspace_path = create_workspace(state.repo_path)

    log_event(
        "setup_workspace",
        "Workspace created",
        {"workspace_path": state.workspace_path}
    )

    entry_path = os.path.join(state.workspace_path, state.entry_file)
    if not os.path.exists(entry_path):
        state.status = Status.FAILED
        state.error_type = ErrorType.CODE_ERROR

        log_event(
            "setup_workspace",
            "Entry file not found -- aborting",
            {
                "entry_file": state.entry_file,
                "workspace_path": state.workspace_path,
            }
        )

        return state

    if state.verification_mode == "pytest":
        tests_path = os.path.join(state.workspace_path, "tests")
        if not os.path.exists(tests_path):
            state.status = Status.FAILED
            state.error_type = ErrorType.CODE_ERROR

            log_event(
                "setup_workspace",
                "Pytest mode selected but no tests/ folder found",
                {"workspace_path": state.workspace_path}
            )

            return state

    return state



def generate_reproduction_script_node(state: OpsGuardState) -> OpsGuardState:
    state.reproduction_script_path = state.entry_file

    return state



def execute_reproduction_node(state: OpsGuardState) -> OpsGuardState:
    log_event("execute_reproduction", "Running reproduction inside Docker")

    result = execute_python(
        state.workspace_path,
        state.reproduction_script_path
    )

    state.reproduction_result = result
    state.error_log = result["stderr"]

    log_event(
        "execute_reproduction",
        "Docker execution completed",
        {
            "exit_code": result["exit_code"],
            "stderr_present": bool(result["stderr"])
        }
    )

    return state



def reproduction_decision_node(state: OpsGuardState) -> OpsGuardState:
    if state.reproduction_result["exit_code"] != 0:
        state.reproduction_verified = True

        log_event(
            "reproduction_decision",
            "Reproduction successful",
            {"exit_code": state.reproduction_result["exit_code"]}
        )
    else:
        state.reproduce_retries += 1

        log_event(
            "reproduction_decision",
            "Reproduction failed to trigger error",
            {"retry_count": state.reproduce_retries}
        )

    return state





def generate_patch_node(state: OpsGuardState) -> OpsGuardState:
    log_event(
        "generate_patch",
        "Generating patch",
        {"fix_retry": state.fix_retries}
    )

    original_file_path = os.path.join(state.workspace_path, state.entry_file)
    with open(original_file_path, "r", encoding="utf-8") as f:
        original_code = f.read()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior Python engineer. "
                "Fix ONLY the runtime error shown. "
                "Make the smallest possible change required to stop the crash. "
                "Do not refactor unrelated logic. "
                "Do not add new third-party imports or environment checks. "
                "Do not modify the __main__ block unless the crash is there. "
                "Return ONLY the full updated file. "
                "No explanations. No markdown."
            ),
        },
        {
            "role": "user",
            "content": f"""
Error:
{state.error_log}

Original File:
{original_code}

Fix the bug and return the full corrected file.
""",
        },
    ]

    from core.llm_client import call_groq_llm, call_nvidia_llm, validate_llm_patch

    def extract_top_level_symbols(source: str) -> set[tuple[str, str]]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()

        symbols = set()
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                symbols.add(("function", node.name))
            elif isinstance(node, ast.AsyncFunctionDef):
                symbols.add(("async_function", node.name))
            elif isinstance(node, ast.ClassDef):
                symbols.add(("class", node.name))
        return symbols

    def extract_import_roots(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()

        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    roots.add(node.module.split(".")[0])
        return roots

    stdlib_modules = set(getattr(sys, "stdlib_module_names", set()))
    stdlib_modules.update(sys.builtin_module_names)

    def has_new_third_party_imports(original: str, candidate: str) -> tuple[bool, list[str]]:
        original_imports = extract_import_roots(original)
        candidate_imports = extract_import_roots(candidate)
        new_imports = candidate_imports - original_imports
        third_party_imports = sorted(
            module for module in new_imports if module and module not in stdlib_modules
        )
        return bool(third_party_imports), third_party_imports

    def looks_incomplete_patch(original: str, candidate: str) -> bool:
        if not candidate.strip():
            return True

        original_len = len(original)
        candidate_len = len(candidate)
        original_lines = len(original.splitlines())
        candidate_lines = len(candidate.splitlines())

        # For large files, full-file strategy should preserve most of the file.
        if original_len >= 2000 and candidate_len < int(original_len * 0.9):
            return True
        if original_lines >= 120 and candidate_lines < int(original_lines * 0.9):
            return True

        original_symbols = extract_top_level_symbols(original)
        candidate_symbols = extract_top_level_symbols(candidate)
        if original_symbols:
            preserved = len(original_symbols & candidate_symbols) / len(original_symbols)
            if preserved < 0.9:
                return True

        # Big one-way deletions are typically truncation in this workflow.
        matcher = difflib.SequenceMatcher(
            None,
            original.splitlines(),
            candidate.splitlines(),
        )
        removed_lines = 0
        added_lines = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("replace", "delete"):
                removed_lines += (i2 - i1)
            if tag in ("replace", "insert"):
                added_lines += (j2 - j1)
        if removed_lines >= 80 and removed_lines > added_lines * 3:
            return True

        return False

    def try_provider(provider_name: str, provider_fn):
        llm_output = ""
        rejection_reason = "unknown"

        for attempt in range(3):
            attempt_messages = messages
            if attempt > 0:
                previous_output = llm_output
                if len(previous_output) > 10000:
                    previous_output = previous_output[:10000]

                original_line_count = len(original_code.splitlines())
                previous_line_count = len(llm_output.splitlines()) if llm_output else 0
                attempt_messages = messages + [
                    {"role": "assistant", "content": previous_output},
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was rejected. "
                            f"Reason: {rejection_reason}. "
                            f"Original file lines: {original_line_count}. "
                            f"Previous response lines: {previous_line_count}. "
                            "Return ONLY raw Python code for the full corrected file. "
                            "Do not drop unrelated functions/classes from the original file. "
                            "Preserve all existing functions/classes unless required for the fix. "
                            "Do not include explanations or markdown."
                        ),
                    },
                ]

            try:
                llm_output = provider_fn(attempt_messages)
            except Exception as error:
                log_event(
                    "generate_patch",
                    "LLM provider call failed",
                    {
                        "provider": provider_name,
                        "attempt": attempt + 1,
                        "error": str(error),
                    }
                )
                return None

            llm_output = llm_output.replace("```python", "").replace("```", "").strip()

            is_valid_patch = validate_llm_patch(llm_output)
            is_incomplete = looks_incomplete_patch(original_code, llm_output)
            has_unwanted_imports, third_party_imports = has_new_third_party_imports(
                original_code,
                llm_output,
            )

            if is_valid_patch and not is_incomplete and not has_unwanted_imports:
                return llm_output

            if not is_valid_patch:
                rejection_reason = "invalid_python_or_format"
            elif is_incomplete:
                rejection_reason = "possible_truncation_or_major_content_loss"
            else:
                rejection_reason = "new_third_party_imports"
            log_event(
                "generate_patch",
                "LLM output rejected by validator",
                {
                    "provider": provider_name,
                    "attempt": attempt + 1,
                    "reason": rejection_reason,
                    "possible_truncation": is_incomplete,
                    "third_party_imports": third_party_imports,
                }
            )

        return None

    llm_output = try_provider("nvidia", call_nvidia_llm)

    if llm_output is None:
        llm_output = try_provider("groq", call_groq_llm)

    if llm_output is None:
        state.fix_retries += 1
        state.patch_content = ""
        log_event(
            "generate_patch",
            "LLM failed validation after reprompt",
            {"fix_retry": state.fix_retries}
        )
        return state

    state.patch_content = llm_output

    return state




def apply_patch_node(state: OpsGuardState) -> OpsGuardState:
    if not state.patch_content:
        state.patch_diff = ""
        state.human_readable_changes = []
        log_event(
            "apply_patch",
            "Skipping patch apply due to invalid LLM output"
        )
        return state

    patch_result = apply_full_file_patch(
        state.workspace_path,
        state.entry_file,
        state.patch_content
    )
    state.patch_diff = patch_result["diff"]
    state.human_readable_changes = patch_result.get("changed_blocks", [])

    artifacts_dir = os.path.join(os.getcwd(), "artifacts")
    internal_dir = os.path.join(artifacts_dir, "internal")
    os.makedirs(internal_dir, exist_ok=True)

    patch_file = os.path.join(internal_dir, "latest_patch.py")

    with open(patch_file, "w", encoding="utf-8") as f:
        f.write(state.patch_content or "")

    log_event(
        "apply_patch",
        "Saved patch artifacts",
        {
            "patch_file": patch_file,
        }
    )

    return state


def syntax_check_node(state: OpsGuardState) -> OpsGuardState:
    if not state.patch_content:
        return state

    process = subprocess.run(
        ["python", "-m", "py_compile", state.entry_file],
        cwd=state.workspace_path,
        capture_output=True,
        text=True
    )

    if process.returncode != 0:
        state.fix_retries += 1

    return state


def execute_fix_test_node(state: OpsGuardState) -> OpsGuardState:
    if not state.patch_content:
        state.fix_result = {
            "exit_code": 1,
            "stdout": "",
            "stderr": "Patch generation failed validation",
        }
        log_event(
            "execute_fix_test",
            "Skipping fix execution due to invalid patch generation",
        )
        return state

    from core.docker_executor import execute_pytest

    if state.verification_mode == "pytest":
        result = execute_pytest(state.workspace_path)
    else:
        result = execute_python(state.workspace_path, state.entry_file)

    state.fix_result = result
    stderr_preview = (result.get("stderr") or "").splitlines()
    log_event(
        "execute_fix_test",
        "Fix test execution completed",
        {
            "mode": state.verification_mode,
            "exit_code": result.get("exit_code"),
            "stderr_preview": stderr_preview[0] if stderr_preview else "",
        },
    )
    return state




def fix_decision_node(state: OpsGuardState) -> OpsGuardState:
    if (
        state.fix_result
        and state.fix_result.get("stderr") == "Patch generation failed validation"
    ):
        log_event(
            "fix_decision",
            "Skipping extra retry increment after patch validation failure",
            {"retry_count": state.fix_retries}
        )
        return state

    if state.fix_result["exit_code"] == 0:
        state.fix_verified = True
        state.status = Status.SUCCESS

        log_event(
            "fix_decision",
            "Fix verified successfully",
            {"status": state.status.value}
        )
    else:
        state.fix_retries += 1

        log_event(
            "fix_decision",
            "Fix failed, retrying",
            {
                "retry_count": state.fix_retries,
                "exit_code": state.fix_result.get("exit_code"),
                "stderr_preview": (state.fix_result.get("stderr") or "").splitlines()[0]
                if state.fix_result.get("stderr")
                else "",
            }
        )

    return state



def generate_fail_report_node(state: OpsGuardState) -> OpsGuardState:
    state.status = Status.FAILED

    log_event(
        "generate_fail_report",
        "Retries exhausted, remediation failed",
        {
            "reproduce_retries": state.reproduce_retries,
            "fix_retries": state.fix_retries
        }
    )

    return state


def generate_not_reproducible_node(state: OpsGuardState) -> OpsGuardState:
    state.status = Status.NOT_REPRODUCIBLE

    log_event(
        "generate_not_reproducible",
        "Issue could not be reproduced in sandbox",
        {
            "reproduce_retries": state.reproduce_retries
        }
    )

    return state


def generate_final_report_node(state: OpsGuardState) -> OpsGuardState:
    artifacts_dir = os.path.join(os.getcwd(), "artifacts")
    internal_dir = os.path.join(artifacts_dir, "internal")
    presentation_dir = os.path.join(artifacts_dir, "presentation")
    os.makedirs(internal_dir, exist_ok=True)
    os.makedirs(presentation_dir, exist_ok=True)

    report = {
        "status": state.status.value,
        "error_type": state.error_type.value if state.error_type else None,
        "reproduce_retries": state.reproduce_retries,
        "fix_retries": state.fix_retries,
        "workspace_path": state.workspace_path,
        "timestamp": datetime.utcnow().isoformat(),
        "patch_diff_summary": None,
        "patch_diff_file": None,
        "judge_summary_file": None,
        "patch_diff": state.patch_diff or "",
        "human_readable_changes": state.human_readable_changes or [],
    }

    if state.patch_diff:
        lines = state.patch_diff.splitlines()
        added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
        report["patch_diff_summary"] = {
            "lines_added": added,
            "lines_removed": removed,
        }

    state.report = report

    if state.patch_diff:
        patch_diff_path = os.path.join(internal_dir, "patch.diff")
        with open(patch_diff_path, "w", encoding="utf-8") as f:
            f.write(state.patch_diff)
        report["patch_diff_file"] = patch_diff_path

    summary_path = os.path.join(presentation_dir, "judge_summary.txt")

    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("====================================================\n")
        f.write("                OPSGUARD REMEDIATION REPORT\n")
        f.write("====================================================\n\n")

        f.write(f"STATUS        : {state.status.value}\n")
        f.write(f"ERROR TYPE    : {state.error_type.value if state.error_type else 'Unknown'}\n")

        if report.get("patch_diff_summary"):
            added = report["patch_diff_summary"]["lines_added"]
            removed = report["patch_diff_summary"]["lines_removed"]
            f.write(f"IMPACT        : +{added} lines, -{removed} line{'s' if removed != 1 else ''}\n")

        f.write("\n")
        f.write("----------------------------------------------------\n")
        f.write(f"CHANGED FILE  : {state.entry_file}\n")
        f.write("----------------------------------------------------\n\n")

        for change in state.human_readable_changes or []:
            f.write(f"Change at Line {change['line_number']}\n")
            f.write("----------------------------------------------------\n\n")

            f.write("BEFORE\n")
            for line in change["before"].splitlines():
                f.write(f"    {line}\n")

            f.write("\nAFTER\n")
            for line in change["after"].splitlines():
                f.write(f"    {line}\n")

            f.write("\n")

        f.write("====================================================\n")
        f.write("Generated by OpsGuard\n")
        f.write("====================================================\n")

    report["judge_summary_file"] = summary_path
    report_path = os.path.join(artifacts_dir, "final_report.json")

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    log_event(
        "generate_final_report",
        "Final structured report generated",
        {"report_path": report_path, "summary_path": summary_path},
    )

    return state

