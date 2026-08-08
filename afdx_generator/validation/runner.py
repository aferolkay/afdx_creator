"""Run the simulator. The only place in the codebase that spawns a subprocess."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from ..models.settings import EnvironmentConfig
from .command_builder import EnvironmentNotConfigured, build_invocation
from .models import ValidationIssue, ValidationResult
from .parser import parse_output


def run_validation(
    config: EnvironmentConfig,
    generated_dir: Path,
    ini_filename: str,
    config_name: str,
    sim_time_limit_s: float,
    timeout_s: float = 300.0,
) -> ValidationResult:
    """Generate-then-run check. Never raises for an ordinary failure -- returns a result instead."""
    try:
        invocation = build_invocation(
            config=config,
            generated_dir=generated_dir,
            ini_filename=ini_filename,
            config_name=config_name,
            sim_time_limit_s=sim_time_limit_s,
        )
    except EnvironmentNotConfigured as exc:
        return ValidationResult(
            passed=False,
            issues=[ValidationIssue(kind="launch_failure", message=str(exc))],
        )

    started = time.monotonic()
    try:
        completed = subprocess.run(
            invocation.argv,
            env=invocation.env,
            cwd=invocation.cwd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        result = parse_output(partial, exit_code=None, timed_out=True)
        result.command = invocation.argv
        result.duration_s = time.monotonic() - started
        return result
    except OSError as exc:
        return ValidationResult(
            passed=False,
            command=invocation.argv,
            issues=[
                ValidationIssue(
                    kind="launch_failure",
                    message=f"Could not start the simulator: {exc}",
                )
            ],
        )

    # The simulator writes findings to stdout; genuine crashes land on stderr.
    combined = (completed.stdout or "") + "\n" + (completed.stderr or "")
    result = parse_output(combined, exit_code=completed.returncode)
    result.command = invocation.argv
    result.duration_s = time.monotonic() - started
    return result
