from pydantic import BaseModel, Field
from typing import Optional, Dict
from enum import Enum


class Status(str, Enum):
    RUNNING = "RUNNING"
    INFRA_STOP = "INFRA_STOP"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    NOT_REPRODUCIBLE = "NOT_REPRODUCIBLE"


class ErrorType(str, Enum):
    CODE_ERROR = "CODE_ERROR"
    INFRA_ERROR = "INFRA_ERROR"
    NO_ERROR = "NO_ERROR"


class OpsGuardState(BaseModel):
    # ---- Input ----
    repo_path: str
    error_log: str
    entry_file: str = "app.py"
    verification_mode: str = "entry"

    # ---- Classification ----
    error_type: Optional[ErrorType] = None

    # ---- Workspace ----
    workspace_path: Optional[str] = None

    # ---- Reproduction Phase ----
    reproduction_script_path: Optional[str] = None
    reproduction_result: Optional[Dict] = None
    reproduction_verified: bool = False
    reproduce_retries: int = 0

    # ---- Fix Phase ----
    patch_content: Optional[str] = None
    patch_diff: Optional[str] = None
    human_readable_changes: Optional[list] = None
    fix_result: Optional[Dict] = None
    fix_verified: bool = False
    fix_retries: int = 0

    # ---- Final Status ----
    status: Status = Field(default=Status.RUNNING)
    report: Optional[Dict] = None
