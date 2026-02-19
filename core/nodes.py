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

    original_file_path = os.path.join(state.workspace_path, "app.py")
    with open(original_file_path, "r", encoding="utf-8") as f:
        original_code = f.read()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a senior Python engineer. "
                "Fix the bug based on the error provided. "
                "Return ONLY the full updated file content. "
                "Do not include explanations. "
                "Do not include markdown. "
                "Return raw Python code only."
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

    def try_provider(provider_name: str, provider_fn):
        llm_output = ""

        for attempt in range(2):
            attempt_messages = messages
            if attempt == 1:
                previous_output = llm_output
                if len(previous_output) > 10000:
                    previous_output = previous_output[:10000]

                attempt_messages = messages + [
                    {"role": "assistant", "content": previous_output},
                    {
                        "role": "user",
                        "content": (
                            "Your previous response violated format requirements. "
                            "Return ONLY raw Python code for the full corrected file. "
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

            if validate_llm_patch(llm_output):
                return llm_output

            log_event(
                "generate_patch",
                "LLM output rejected by validator",
                {
                    "provider": provider_name,
                    "attempt": attempt + 1,
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
        log_event(
            "apply_patch",
            "Skipping patch apply due to invalid LLM output"
        )
        return state

    patch_result = apply_full_file_patch(
        state.workspace_path,
        "app.py",
        state.patch_content
    )
    state.patch_diff = patch_result["diff"]

    artifacts_dir = os.path.join(os.getcwd(), "artifacts")
    os.makedirs(artifacts_dir, exist_ok=True)

    patch_file = os.path.join(artifacts_dir, "latest_patch.py")
    diff_file = os.path.join(artifacts_dir, "latest_patch.diff")

    with open(patch_file, "w", encoding="utf-8") as f:
        f.write(state.patch_content or "")

    with open(diff_file, "w", encoding="utf-8") as f:
        f.write(state.patch_diff or "")

    log_event(
        "apply_patch",
        "Saved patch artifacts",
        {
            "patch_file": patch_file,
            "diff_file": diff_file
        }
    )

    return state


import subprocess

def syntax_check_node(state: OpsGuardState) -> OpsGuardState:
    if not state.patch_content:
        return state

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
    if not state.patch_content:
        state.fix_result = {
            "exit_code": 1,
            "stdout": "",
            "stderr": "Patch generation failed validation",
        }
        return state

    result = execute_python(state.workspace_path, "app.py")
    state.fix_result = result
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
