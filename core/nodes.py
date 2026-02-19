from core.state import OpsGuardState, Status, ErrorType
from core.workspace import create_workspace
from core.docker_executor import execute_python
from core.patch_engine import apply_full_file_patch
from core.error_classifier import classify_error
import os


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

    return state



def generate_reproduction_script_node(state: OpsGuardState) -> OpsGuardState:
    script_path = os.path.join(state.workspace_path, "reproduce_issue.py")

    # Placeholder deterministic reproduction
    script_content = state.error_log  # Later replaced by LLM logic

    # For now assume app.py reproduction
    state.reproduction_script_path = "app.py"

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

    # LLM later
    state.patch_content = """def parse_input(value):
    try:
        return int(value)
    except ValueError:
        return 0

if __name__ == "__main__":
    print(parse_input("abc"))
"""

    return state




def apply_patch_node(state: OpsGuardState) -> OpsGuardState:
    patch_result = apply_full_file_patch(
        state.workspace_path,
        "app.py",
        state.patch_content
    )
    state.patch_diff = patch_result["diff"]
    return state


import subprocess

def syntax_check_node(state: OpsGuardState) -> OpsGuardState:
    process = subprocess.run(
        ["python", "-m", "py_compile", "app.py"],
        cwd=state.workspace_path,
        capture_output=True,
        text=True
    )

    if process.returncode != 0:
        state.fix_retries += 1

    return state


def execute_fix_test_node(state: OpsGuardState) -> OpsGuardState:
    result = execute_python(state.workspace_path, "app.py")
    state.fix_result = result
    return state




def fix_decision_node(state: OpsGuardState) -> OpsGuardState:
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
            {"retry_count": state.fix_retries}
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
