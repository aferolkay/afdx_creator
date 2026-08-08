"""Result types for a validation run."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IssueKind = Literal[
    "policer_drop",      # TOKEN_INSUFFICIENT -- token bucket underran, frame discarded
    "missing_vl_entry",  # a switch received a VL id absent from its routing table
    "queue_overflow",    # a per-VL queue exceeded its configured limit
    "simulation_error",  # any other error the simulator reported
    "launch_failure",    # the binary could not be started at all
]


class ValidationIssue(BaseModel):
    kind: IssueKind
    message: str
    count: int = 1
    virtual_link: str | None = None
    switch: str | None = None
    hint: str | None = None


class ValidationResult(BaseModel):
    passed: bool
    exit_code: int | None = None
    issues: list[ValidationIssue] = Field(default_factory=list)
    command: list[str] = Field(default_factory=list)
    stdout_tail: str = ""
    duration_s: float = 0.0
    timed_out: bool = False

    @property
    def summary(self) -> str:
        if self.passed:
            return "Validation passed: no drops or errors reported."
        if not self.issues:
            return f"Validation failed (exit code {self.exit_code})."
        return "; ".join(f"{i.message} (x{i.count})" if i.count > 1 else i.message
                         for i in self.issues[:5])
