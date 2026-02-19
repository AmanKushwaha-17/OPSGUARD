# OpsGuard

**A zero-trust AI remediation engine that refuses to ship a fix it cannot prove.**

OpsGuard doesn't blindly patch code. It follows a strict scientific-method loop — reproduce the bug in an isolated Docker sandbox, propose a fix via LLM, verify the fix passes in the same sandbox, and only then generate proof artifacts. If a fix cannot be proven, OpsGuard refuses to proceed.

---

## Why OpsGuard?

Current tooling is fragmented:

- Monitoring tools **detect** failures.
- AI tools **generate** patches.
- But there is **no safe bridge** between detection and verified remediation.

Raw LLM patches can hallucinate imports, break dependencies, or silently introduce regressions. OpsGuard closes this trust gap with **deterministic enforcement** — the LLM proposes, Docker verifies, the orchestrator enforces control flow.

---

## High-Level Architecture

```mermaid
flowchart TD
    subgraph CLI_LAYER["CLI Layer — Simulated Alert Trigger"]
        CLI["cli.py"]
    end

    subgraph ORCH_LAYER["Orchestration Layer — LangGraph Deterministic State Flow"]
        GRAPH["core/graph.py"]
        STATE["core/state.py"]
    end

    subgraph EXEC_LAYER["Execution Layer — Workspace + Patch Engine + Docker Sandbox"]
        WORKSPACE["core/workspace.py"]
        DOCKER["core/docker_executor.py"]
        PATCH["core/patch_engine.py"]
        CLASSIFIER["core/error_classifier.py"]
    end

    subgraph LLM_LAYER["LLM Intelligence — Reproduce / Fix / PR"]
        LLM_CLIENT["core/llm_client.py"]
    end

    CLI_LAYER --> ORCH_LAYER
    ORCH_LAYER --> EXEC_LAYER
    EXEC_LAYER --> LLM_LAYER
```

**Important constraints:**

- LLM **never** executes code.
- LLM **never** controls workflow state.
- LLM **only** returns text artifacts.

All LLM output passes through `validate_llm_patch()` — a strict gate that rejects markdown fences, explanatory text, and code that fails `ast.parse()`.

---

## Error Classification Gate

Before remediation begins, OpsGuard classifies the failure to decide the workflow path.

```mermaid
flowchart TD
    STDERR["Captured stderr"] --> CLASSIFY{"classify_error()"}

    CLASSIFY -->|"Infra keywords detected"| INFRA["INFRA_ERROR"]
    CLASSIFY -->|"Python exception detected"| CODE["CODE_ERROR"]
    CLASSIFY -->|"Empty stderr"| NONE["NO_ERROR"]

    INFRA --> INFRA_REPORT["Generate Infra Report"]
    INFRA_REPORT --> END_INFRA(["END — INFRA_STOP"])

    CODE --> REPRO["Enter Reproduction + Fix Loop"]
    NONE --> RETRY["Enter Reproduction Retry Flow"]
```

**Infra keywords** (early exit): `401`, `403`, `unauthorized`, `forbidden`, `rate limit`, `timeout`, `connection refused`, `ssl error`, `credential`, `access denied`

**Code errors** (proceed to fix): `ValueError`, `KeyError`, `TypeError`, `AttributeError`, `IndexError`, and general Python exceptions.

---

## Runtime Execution Flow

```mermaid
flowchart TD
    START(["CLI Trigger"]) --> SETUP["Setup Workspace"]

    subgraph REPRODUCE["Reproduction Phase"]
        GEN_SCRIPT["Generate Reproduction Script"]
        EXEC_REPRO["Execute in Docker"]
        CLASSIFY["Classify Error"]
        REPRO_DECISION{"Reproduction\nDecision"}
    end

    SETUP --> GEN_SCRIPT
    GEN_SCRIPT --> EXEC_REPRO
    EXEC_REPRO --> CLASSIFY
    CLASSIFY --> REPRO_DECISION

    REPRO_DECISION -->|"INFRA_ERROR"| INFRA_REPORT["Infra Report"]
    INFRA_REPORT --> FINAL_1["Final Report"]
    FINAL_1 --> END_1(["END — INFRA_STOP"])

    REPRO_DECISION -->|"Reproduced"| GEN_PATCH

    REPRO_DECISION -->|"retries >= 2"| NOT_REPRO["Not Reproducible"]
    NOT_REPRO --> FINAL_2["Final Report"]
    FINAL_2 --> END_2(["END — NOT_REPRODUCIBLE"])

    REPRO_DECISION -->|"Retry"| GEN_SCRIPT

    subgraph FIX["Fix Phase"]
        GEN_PATCH["Generate Patch via LLM"]
        APPLY["Apply Patch + Compute Diff"]
        SYNTAX["Syntax Check"]
        EXEC_FIX["Execute Fix Test in Docker"]
        FIX_DECISION{"Fix\nDecision"}
    end

    GEN_PATCH --> APPLY
    APPLY --> SYNTAX
    SYNTAX --> EXEC_FIX
    EXEC_FIX --> FIX_DECISION

    FIX_DECISION -->|"exit_code == 0"| FINAL_3["Final Report"]
    FINAL_3 --> END_3(["END — SUCCESS"])

    FIX_DECISION -->|"retries >= 3"| FAIL_REPORT["Failure Report"]
    FAIL_REPORT --> FINAL_4["Final Report"]
    FINAL_4 --> END_4(["END — FAILED"])

    FIX_DECISION -->|"Retry"| GEN_PATCH
```

### Retry Limits

| Phase | Max Retries | On Exhaustion |
|:---|:---:|:---|
| Reproduction | 2 | Marks `NOT_REPRODUCIBLE`, generates report |
| Fix | 3 | Marks `FAILED`, generates failure report |

---

## Verification Gates

OpsGuard enforces two mandatory verification gates — both run inside Docker.

- **Gate 1 — Reproduction**: `exit_code != 0` and expected exception in stderr. Pass = proceed to fix loop.
- **Gate 2 — Fix Verification**: `exit_code == 0`. Only Gate 2 success allows progression to artifact generation.

---

## Docker Sandbox Strategy

Docker is the **trust boundary**. No LLM output is accepted without Docker confirmation.

| Aspect | Detail |
|:---|:---|
| **Base image** | `python:3.11-slim` |
| **Isolation** | Each run mounts an isolated workspace copy via `-v` |
| **Capture** | `exit_code`, `stdout`, `stderr` |
| **Cleanup** | Container destroyed after run (`--rm`) |
| **Trust rule** | No patch is accepted unless Docker confirms `exit_code == 0` |

---

## Patch Strategy

OpsGuard does **not** trust LLM-generated line numbers or fragile patch positions.

1. LLM returns the **full updated file content**.
2. `patch_engine.py` computes a **unified diff** via `difflib`.
3. Engine writes the updated file.
4. Docker **re-runs verification**.

This avoids fragile patch-position assumptions and provides full auditability.

---

## Current Scope

This codebase is intentionally narrow right now:

- **Single-file workflow**: `app.py` is hardcoded for reproduce/fix.
- **Patch strategy**: full-file replacement (not line-level edits).
- **Reproduction script**: placeholder logic that runs `app.py`.
- **Error classification**: keyword heuristics on captured stderr.
- **GitHub integration**: produces `patch.diff` and summary artifacts (no OAuth/PR automation yet).

---

## Artifacts

Generated under `artifacts/`:

| File | Purpose |
|:---|:---|
| `final_report.json` | Structured result payload with status, retries, diff summary |
| `internal/latest_patch.py` | Latest LLM-generated file content |
| `internal/patch.diff` | Unified diff for the final patch |
| `internal/run.log` | Structured JSON event log |
| `presentation/judge_summary.txt` | Human-readable remediation report |

---

## Requirements

- Python 3.11+
- Docker daemon running locally
- Dependencies: `langgraph`, `pydantic`, `openai`, `python-dotenv`
- At least one LLM key in `.env`:

```env
NVIDIA_API_KEY=your_nvidia_key
GROQ_API_KEY=your_groq_key
```


The CLI outputs:
- Final status (`SUCCESS`, `FAILED`, `INFRA_STOP`, `NOT_REPRODUCIBLE`)
- Paths to generated report artifacts
- When `OPSGUARD_VERBOSE=1`: full JSON report, diff summary, and human-readable changes

### Quick Test

Run the demo pipeline end-to-end with a single command:

```bash
python cli.py --repo demo_repo --error "ValueError"
```

---

## Project Layout

```
opsguard/
├── cli.py                      # Entrypoint — graph invoke, output, cleanup
├── core/
│   ├── graph.py                # LangGraph state machine wiring
│   ├── nodes.py                # Node implementations (classify/reproduce/patch/report)
│   ├── state.py                # OpsGuardState model + Status/ErrorType enums
│   ├── docker_executor.py      # Containerized Python execution
│   ├── llm_client.py           # NVIDIA + Groq LLM clients + patch validator
│   ├── patch_engine.py         # Full-file patch apply + unified diff
│   ├── error_classifier.py     # Stderr keyword classification
│   ├── workspace.py            # Temp workspace create/cleanup
│   └── logger.py               # Structured JSON event logger
├── demo_repo/
│   └── app.py                  # Sample failing application
├── artifacts/                  # Generated reports, diffs, logs
└── test_docker.py              # Local smoke test for the full pipeline
```

---

## Limitations

- Assumes target repo contains `app.py`.
- Does not currently run project-specific test suites.
- Fix loop uses runtime execution of `app.py` only.
- `NO_ERROR` classification follows reproduction retry flow unless infra keywords are detected.
- GitHub PR automation is out of current scope (produces artifacts only).
