"""Build the simulator invocation. Pure -- returns argv/env/cwd, runs nothing.

The path handling here is the fiddly part of driving OMNeT++ from outside its IDE. The IDE
resolves project references itself; from a shell you must spell out both the NED search path and
the shared-library path, and a missing entry produces an unhelpful error a long way from the cause.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from ..models.settings import EnvironmentConfig


class EnvironmentNotConfigured(RuntimeError):
    """The environment lacks something required to run the simulator."""


@dataclass(frozen=True)
class Invocation:
    argv: list[str]
    env: dict[str, str]
    cwd: str


def build_invocation(
    config: EnvironmentConfig,
    generated_dir: Path,
    ini_filename: str,
    config_name: str,
    sim_time_limit_s: float,
    run_number: int = 0,
) -> Invocation:
    if not config.binary_path:
        raise EnvironmentNotConfigured(
            "No simulator binary configured. Set the path to the compiled OMNeT++ executable "
            "in the environment settings."
        )

    binary = Path(config.binary_path).expanduser()
    if not binary.exists():
        raise EnvironmentNotConfigured(f"Simulator binary not found: {binary}")
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise EnvironmentNotConfigured(f"Simulator binary is not executable: {binary}")

    generated_dir = Path(generated_dir).resolve()
    if not (generated_dir / ini_filename).exists():
        raise EnvironmentNotConfigured(
            f"Generated ini not found: {generated_dir / ini_filename}. Generate the network first."
        )

    # NED search path. "." is the generated directory itself (we run with cwd set there), which is
    # what lets the route-table files resolve as bare filenames too.
    ned_paths = ["."]
    for candidate in (config.project_src_dir, config.afdx_src_dir, config.queueinglib_dir,
                      *config.extra_ned_paths):
        if candidate and candidate not in ned_paths:
            ned_paths.append(str(Path(candidate).expanduser()))

    ld_paths = [
        str(Path(p).expanduser())
        for p in (config.omnetpp_lib_dir, config.afdx_src_dir, config.queueinglib_dir,
                  *config.extra_ld_library_paths)
        if p
    ]
    existing_ld = os.environ.get("LD_LIBRARY_PATH", "")
    if existing_ld:
        ld_paths.append(existing_ld)

    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = os.pathsep.join(ld_paths)

    argv = [
        str(binary),
        "-n", os.pathsep.join(ned_paths),
        "-u", "Cmdenv",
        "-c", config_name,
        "-r", str(run_number),
        f"--sim-time-limit={sim_time_limit_s}s",
        ini_filename,
    ]

    return Invocation(argv=argv, env=env, cwd=str(generated_dir))
