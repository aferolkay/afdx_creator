"""Where things live on disk."""

from __future__ import annotations

import os
from pathlib import Path

# Repo root (afdx_generator/afdx_generator/storage/paths.py -> up three).
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = PACKAGE_ROOT.parent


def projects_dir() -> Path:
    path = Path(os.environ.get("AFDX_GENERATOR_PROJECTS_DIR", REPO_ROOT / "projects"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir() -> Path:
    path = Path(os.environ.get("AFDX_GENERATOR_OUTPUT_DIR", REPO_ROOT / "output"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def env_config_file() -> Path:
    """Machine-specific paths. Deliberately outside project files so projects stay portable."""
    override = os.environ.get("AFDX_GENERATOR_ENV_FILE")
    if override:
        return Path(override)
    return REPO_ROOT / "env.json"


def static_dir() -> Path:
    return REPO_ROOT / "static"


def html_template_dir() -> Path:
    return REPO_ROOT / "templates_html"
