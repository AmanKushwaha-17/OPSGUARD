import argparse
import json
import os
from core.state import OpsGuardState
from core.graph import build_graph
from core.logger import log_event
from core.workspace import cleanup_workspace


def _extract_workspace_path(state_candidate) -> str | None:
    if isinstance(state_candidate, OpsGuardState):
        return state_candidate.workspace_path
    if isinstance(state_candidate, dict):
        return state_candidate.get("workspace_path")
    return None


def _print_change_summary(report: dict | None):
    print("\n====== CHANGES ======")

    if not report:
        print("No report generated.")
        print("=====================\n")
        return

    patch_diff = report.get("patch_diff", "")
    patch_diff_summary = report.get("patch_diff_summary")

    if patch_diff_summary:
        print(
            "Diff summary:",
            f"+{patch_diff_summary.get('lines_added', 0)}",
            f"-{patch_diff_summary.get('lines_removed', 0)}",
        )

    if patch_diff:
        print(patch_diff)
    else:
        print("No patch diff available for this run.")

    print("=====================\n")

    changes = report.get("human_readable_changes")
    if changes:
        print("\n====== HUMAN READABLE CHANGES ======")
        for change in changes:
            print(f"\nLine {change['line_number']}")
            print("Before:")
            print(change["before"] or "(none)")
            print("After:")
            print(change["after"] or "(none)")
        print("====================================")


def run_command(repo_path: str, error_log: str):
    verbose = os.getenv("OPSGUARD_VERBOSE") == "1"
    log_event("CLI", "Starting OpsGuard run")

    # Initialize state
    initial_state = OpsGuardState(
        repo_path=repo_path,
        error_log=error_log,
    )

    # Build graph
    app = build_graph()

    raw_final_state = None
    final_state = None

    try:
        # Execute graph. LangGraph may return a raw dict state, so normalize it.
        raw_final_state = app.invoke(initial_state)

        if isinstance(raw_final_state, OpsGuardState):
            final_state = raw_final_state
        elif isinstance(raw_final_state, dict):
            if hasattr(OpsGuardState, "model_validate"):
                final_state = OpsGuardState.model_validate(raw_final_state)
            else:
                final_state = OpsGuardState.parse_obj(raw_final_state)
        else:
            raise TypeError(
                f"Unexpected graph state type: {type(raw_final_state).__name__}"
            )

        log_event(
            "CLI",
            "OpsGuard execution completed",
            {
                "final_status": final_state.status.value,
                "reproduce_retries": final_state.reproduce_retries,
                "fix_retries": final_state.fix_retries,
            },
        )

        if verbose:
            print("\n====== OPSGUARD RESULT ======")
            if final_state.report:
                print(json.dumps(final_state.report, indent=2))
            else:
                print(f"Status: {final_state.status.value}")
            print("=============================\n")
            _print_change_summary(final_state.report)
        else:
            print("OpsGuard execution complete.")
            print(f"Status: {final_state.status.value}")
            print("Presentation report saved to: artifacts/presentation/judge_summary.txt")
            print("Machine report: artifacts/final_report.json")
    finally:
        workspace_path = (
            _extract_workspace_path(final_state)
            or _extract_workspace_path(raw_final_state)
            or initial_state.workspace_path
        )

        if workspace_path:
            log_event(
                "CLI",
                "Cleaning up workspace",
                {"workspace_path": workspace_path},
            )
            try:
                cleanup_workspace(workspace_path)
                log_event(
                    "CLI",
                    "Workspace cleanup complete",
                    {"workspace_path": workspace_path},
                )
            except Exception as cleanup_error:
                log_event(
                    "CLI",
                    "Workspace cleanup failed",
                    {
                        "workspace_path": workspace_path,
                        "error": str(cleanup_error),
                    },
                )


def main():
    parser = argparse.ArgumentParser(description="OpsGuard CLI")

    parser.add_argument(
        "--repo",
        required=True,
        help="Path to target repository"
    )

    parser.add_argument(
        "--error",
        required=True,
        help="Raw error traceback string"
    )

    args = parser.parse_args()

    run_command(args.repo, args.error)


if __name__ == "__main__":
    main()
