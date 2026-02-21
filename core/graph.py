from langgraph.graph import StateGraph, END

from core.state import OpsGuardState, Status, ErrorType
from core.nodes import (
    classify_error_node,
    generate_infra_report_node,
    setup_workspace_node,
    generate_reproduction_script_node,
    execute_reproduction_node,
    reproduction_decision_node,
    generate_patch_node,
    apply_patch_node,
    syntax_check_node,
    execute_fix_test_node,
    fix_decision_node,
    generate_fail_report_node,
    generate_not_reproducible_node,
    generate_final_report_node,
)

def build_graph():
    graph = StateGraph(OpsGuardState)

    # Nodes
    graph.add_node("classify_error", classify_error_node)
    graph.add_node("generate_infra_report", generate_infra_report_node)

    graph.add_node("setup_workspace", setup_workspace_node)
    graph.add_node("generate_reproduction_script", generate_reproduction_script_node)
    graph.add_node("execute_reproduction", execute_reproduction_node)
    graph.add_node("reproduction_decision", reproduction_decision_node)

    graph.add_node("generate_patch", generate_patch_node)
    graph.add_node("apply_patch", apply_patch_node)
    graph.add_node("syntax_check", syntax_check_node)
    graph.add_node("execute_fix_test", execute_fix_test_node)
    graph.add_node("fix_decision", fix_decision_node)

    graph.add_node("generate_fail_report", generate_fail_report_node)
    graph.add_node("generate_not_reproducible", generate_not_reproducible_node)
    graph.add_node("generate_final_report", generate_final_report_node)

    graph.set_entry_point("setup_workspace")

    graph.add_edge("generate_infra_report", "generate_final_report")

    # Early validation: if entry file is missing, skip straight to final report
    def setup_router(state: OpsGuardState):
        if state.status == Status.FAILED:
            return "generate_final_report"
        return "generate_reproduction_script"

    graph.add_conditional_edges(
        "setup_workspace",
        setup_router,
        {
            "generate_final_report": "generate_final_report",
            "generate_reproduction_script": "generate_reproduction_script",
        },
    )

    # Reproduction Flow
    graph.add_edge("generate_reproduction_script", "execute_reproduction")
    graph.add_edge("execute_reproduction", "classify_error")
    graph.add_edge("classify_error", "reproduction_decision")

    def reproduction_router(state: OpsGuardState):
        if state.error_type == ErrorType.INFRA_ERROR:
            return "generate_infra_report"

        if state.reproduction_verified:
            return "generate_patch"

        if state.reproduce_retries >= 2:
            return "generate_not_reproducible"

        return "generate_reproduction_script"


    graph.add_conditional_edges(
        "reproduction_decision",
        reproduction_router,
        {
            "generate_patch": "generate_patch",
            "generate_not_reproducible": "generate_not_reproducible",
            "generate_reproduction_script": "generate_reproduction_script",
            "generate_infra_report": "generate_infra_report",
        },
    )


    # Fix Flow
    graph.add_edge("generate_patch", "apply_patch")
    graph.add_edge("apply_patch", "syntax_check")
    graph.add_edge("syntax_check", "execute_fix_test")
    graph.add_edge("execute_fix_test", "fix_decision")

    def fix_router(state: OpsGuardState):
        if state.status == Status.SUCCESS:
            return "generate_final_report"
        if state.fix_retries >= 3:
            return "generate_fail_report"
        return "generate_patch"

    graph.add_conditional_edges(
        "fix_decision",
        fix_router,
        {
            "generate_final_report": "generate_final_report",
            "generate_fail_report": "generate_fail_report",
            "generate_patch": "generate_patch",
        },
    )

    graph.add_edge("generate_fail_report", "generate_final_report")
    graph.add_edge("generate_not_reproducible", "generate_final_report")
    graph.add_edge("generate_final_report", END)

    return graph.compile()
