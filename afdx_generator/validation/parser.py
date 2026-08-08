"""Turn simulator console output into structured findings.

Pure text in, structured result out -- no subprocess, no filesystem -- so it can be tested against
canned output without OMNeT++ installed.
"""

from __future__ import annotations

import re

from .models import ValidationIssue, ValidationResult

# "TOKEN_INSUFFICIENT (VL:7) SW:0" -- the traffic policer discarded a frame.
_TOKEN_RE = re.compile(r"TOKEN_INSUFFICIENT\s*\(VL:\s*(\d+)\s*\)\s*SW:\s*(\d+)")

# The VL router aborts when a frame arrives for an id absent from that switch's table.
_MISSING_VL_RE = re.compile(r"Key Not Found in VL Table", re.IGNORECASE)

# RegulatorLogic gives up when a per-VL queue exceeds maxVLIDQueueSize.
_QUEUE_RE = re.compile(r"Max limit for VLID queue is reached\.?\s*\(vlid:\s*(\d+)\s*\)", re.IGNORECASE)

# OMNeT++ reports fatal problems as "<!> Error: ..." on its own line.
_ERROR_RE = re.compile(r"<!>\s*Error:\s*(.+)")

# Benign: these are cleanup diagnostics the AFDX library emits at the end of every run, including
# runs that are entirely healthy. Treating them as failures would make every run look broken.
_IGNORABLE = (
    "undisposed object",
    "check module destructor",
)


def parse_output(stdout: str, exit_code: int | None, timed_out: bool = False) -> ValidationResult:
    issues: list[ValidationIssue] = []

    # --- policer drops, aggregated per (VL, switch) so 400 identical lines become one finding ---
    token_counts: dict[tuple[str, str], int] = {}
    for match in _TOKEN_RE.finditer(stdout):
        key = (match.group(1), match.group(2))
        token_counts[key] = token_counts.get(key, 0) + 1

    for (vl, switch), count in sorted(token_counts.items(), key=lambda kv: -kv[1]):
        issues.append(
            ValidationIssue(
                kind="policer_drop",
                message=f"Traffic policer dropped frames on VL {vl} at switch {switch}",
                count=count,
                virtual_link=vl,
                switch=switch,
                hint=(
                    "The token bucket underran. Raise the sigma margin factor (general settings), "
                    "or raise sigma for this virtual link specifically. This is expected if sigma "
                    "is close to a single frame size -- policing happens at every hop, and traffic "
                    "from other links perturbs this one's spacing along the way."
                ),
            )
        )

    if _MISSING_VL_RE.search(stdout):
        issues.append(
            ValidationIssue(
                kind="missing_vl_entry",
                message="A switch received a virtual link that is missing from its routing table",
                hint=(
                    "This normally means generation and the simulation run are out of sync -- "
                    "regenerate the network. Every switch along a link's route needs an entry, "
                    "including switches the link only passes through."
                ),
            )
        )

    queue_vls = {m.group(1) for m in _QUEUE_RE.finditer(stdout)}
    for vl in sorted(queue_vls):
        issues.append(
            ValidationIssue(
                kind="queue_overflow",
                message=f"Per-link queue overflowed for VL {vl}",
                virtual_link=vl,
                hint=(
                    "Frames are arriving faster than the BAG lets them out. Check this link's BAG "
                    "against its actual send rate, or raise the queue limit in general settings."
                ),
            )
        )

    for match in _ERROR_RE.finditer(stdout):
        text = match.group(1).strip()
        if any(token in text.lower() for token in _IGNORABLE):
            continue
        # "simulation time limit reached" is how a successful bounded run ends, not a failure.
        if "time limit reached" in text.lower():
            continue
        issues.append(ValidationIssue(kind="simulation_error", message=text))

    if timed_out:
        issues.append(
            ValidationIssue(
                kind="simulation_error",
                message="The simulation did not finish within the allowed time and was stopped",
                hint="Lower the simulated time limit, or investigate why the run is not progressing.",
            )
        )

    passed = not issues and exit_code == 0 and not timed_out

    tail_lines = [
        line for line in stdout.splitlines()
        if not any(token in line.lower() for token in _IGNORABLE)
    ]
    return ValidationResult(
        passed=passed,
        exit_code=exit_code,
        issues=issues,
        stdout_tail="\n".join(tail_lines[-40:]),
        timed_out=timed_out,
    )
