# OpsGuard

OpsGuard is a zero-trust AI remediation engine.

It does not blindly fix code. It follows a strict verification loop:

1. Reproduce the bug.
2. Verify the reproduction.
3. Propose a fix.
4. Verify the fix in isolation.
5. Generate proof artifacts.

If a fix cannot be proven inside a sandbox, OpsGuard refuses to proceed.

## Problem Statement

Current tooling is fragmented:

- Monitoring tools detect failures.
- AI tools generate patches.
- There is no safe bridge between detection and verified remediation.

Raw LLM patches can hallucinate imports, break dependencies, or apply unsafe edits. OpsGuard closes this trust gap with deterministic enforcement.

## Solution

OpsGuard combines:

- LLM text generation for reproduction and fixes.
- Docker sandbox execution for ground-truth verification.
- Deterministic orchestration (LangGraph target architecture).

Core principle:

- The LLM proposes.
- Docker verifies.
- The orchestrator enforces control flow.

## High-Level Architecture

```text
+----------------------------+
|         CLI Layer          |
|  (Simulated Alert Trigger) |
+-------------+--------------+
              |
              v
+----------------------------+
|    Orchestration Layer     |
|         (LangGraph)        |
|   Deterministic State Flow |
+-------------+--------------+
              |
              v
+----------------------------+
|      Execution Layer       |
| Workspace + Patch Engine + |
|      Docker Sandbox        |
+-------------+--------------+
              |
              v
+----------------------------+
|      LLM Intelligence      |
|   Reproduce / Fix / PR     |
+----------------------------+
```

Important:

- LLM never executes code.
- LLM never controls workflow state.
- LLM only returns text artifacts.

## Error Classification Gate

OpsGuard classifies failures before remediation starts.

Proceed (code errors):

- `ValueError`
- `KeyError`
- `TypeError`
- `AttributeError`
- `IndexError`
- Workspace/path issues (for example `FileNotFoundError` in repo files)

Stop (infrastructure errors):

- `401 Unauthorized`
- `403 Forbidden`
- `Rate limit exceeded`
- `Connection refused`
- `Timeout`
- Missing credentials

For infra-level failures, OpsGuard generates an infra report and ends the workflow.

## Runtime Execution Flow

```text
CLI Trigger
  |
  v
setup_workspace (create isolated workspace copy)
  |
  v
classify_error
  |                     |
  v                     v
infra_error         code_error
  |                     |
  v                     v
generate_report   ensure_workspace_ready
  |                     |
  v                     v
 END            generate_reproduction_script
                        |
                        v
               execute_reproduction (Docker)
                        |
                        v
               reproduction_decision
                  |             |
                  v             v
                retry         proceed
                                |
                                v
                        generate_patch (LLM)
                                |
                                v
                           apply_patch
                                |
                                v
                        execute_fix_test (Docker)
                                |
                                v
                           fix_decision
                            |         |
                            v         v
                          retry     success
                                      |
                                      v
                                 generate_pr
                                      |
                                      v
                                     END
```

Retry limits:

- Reproduction attempts: 2
- Fix attempts: 3

On repeated failure, OpsGuard emits a structured failure report.

## Docker Sandbox Strategy

Docker is the trust boundary.

Base image:

- `python:3.11-slim`

For each execution:

- Mount an isolated workspace copy.
- Run the target script.
- Capture `exit_code`, `stdout`, `stderr`.
- Destroy the container after run (`--rm`).

No patch is accepted unless Docker confirms success.

## Verification Gates

Gate 1: Reproduction verification

- `exit_code != 0`
- Expected exception type appears in `stderr`

Gate 2: Fix verification

- `exit_code == 0`

Only Gate 2 success allows progression to PR artifact generation.

## Patch Strategy (Safe Mode)

OpsGuard does not trust LLM-generated line numbers.

Safe approach:

1. LLM returns full updated file content.
2. Engine computes unified diff with `difflib`.
3. Engine writes updated file content.
4. Docker re-runs verification.

This avoids fragile patch-position assumptions.

## GitHub Strategy (Hackathon Scope)

Hackathon scope avoids OAuth automation. Instead OpsGuard can produce:

- `patch.diff`
- `PR_DESCRIPTION.md`

Production extension:

- Open a GitHub pull request automatically after verification.

## Observability

OpsGuard logs deterministic state transitions, for example:

```text
[STATE] setup_workspace
[STATE] reproduce_attempt_1
[DOCKER] exit_code=1
[STATE] fix_attempt_1
[DOCKER] exit_code=0
[SUCCESS] Patch verified
```

Optional:

- Persist full run details as a JSON audit artifact.

## LangGraph State Schema (Target)

Core state fields:

- `repo_path`
- `workspace_path`
- `error_log`
- `error_type`
- `reproduction_script`
- `reproduction_result`
- `patch_content`
- `fix_result`
- `retries`
- `status`

LangGraph controls deterministic transitions across these fields.

## Zero-Trust Model

The LLM is constrained to text generation only.

Allowed:

- Reproduction script generation
- Modified file content generation
- PR description generation

Not allowed:

- Command execution
- Direct uncontrolled file mutation
- Workflow control decisions

Docker enforces truth. Orchestration enforces order.

## Why This Wins a Hackathon

Most projects say: "AI fixes code."

OpsGuard says: "AI must prove the fix in an isolated execution environment before approval."

This introduces:

- Determinism
- Verification gates
- Scientific-method remediation loop
- Trust-boundary enforcement

## 3-Week Execution Plan

Week 1:

- Stabilize Docker executor
- Stabilize workspace manager
- Manual reproduce and patch demo

Week 2:

- Integrate LLM calls
- Implement LangGraph state machine
- Add retry and decision logic

Week 3:

- Improve logs and reports
- Finalize demo repository
- Prepare slides and demo recording

## Demo Narrative

1. Show a broken repo and traceback.
2. Run OpsGuard from CLI.
3. Reproduce failure in Docker.
4. Apply candidate patch.
5. Re-run verification in Docker.
6. Show success artifacts and PR description.
7. Show logs proving before/after behavior.

## Final Positioning

OpsGuard is a deterministic, LangGraph-powered AI remediation engine that enforces zero-trust verification gates inside isolated Docker sandboxes before accepting any automated fix.

## Current Repository Status

Implemented modules in this repo:

- `core/workspace.py`: workspace copy and cleanup helpers.
- `core/docker_executor.py`: containerized Python execution.
- `core/patch_engine.py`: full-file patch apply + unified diff generation.
- `core/error_classifier.py`: early error classification for infra vs code issues.
- `test_docker.py`: end-to-end local flow (reproduce -> patch -> verify).

## Quick Start

Prerequisites:

- Docker installed and running.
- Python 3.11+ available locally.

Run the demo flow:

```bash
python test_docker.py
```
