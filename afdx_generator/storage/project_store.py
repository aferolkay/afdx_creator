"""Project persistence: one JSON file per project.

No database: this is a local, single-user tool. The tradeoff is no concurrent-write protection --
two browser tabs editing the same project will last-write-wins.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from ..models.project import Project
from ..models.settings import EnvironmentConfig
from .paths import env_config_file, projects_dir


class ProjectNotFound(KeyError):
    pass


def _project_file(project_id: str) -> Path:
    # Never let an id escape the projects directory.
    safe = "".join(ch for ch in project_id if ch.isalnum() or ch in "-_")
    if not safe:
        raise ProjectNotFound(project_id)
    return projects_dir() / f"{safe}.json"


def new_project_id() -> str:
    return uuid.uuid4().hex[:12]


def save_project(project: Project) -> Path:
    project.touch()
    path = _project_file(project.id)
    # Write via a temporary file so an interrupted save cannot truncate a good project.
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_project(project_id: str) -> Project:
    path = _project_file(project_id)
    if not path.exists():
        raise ProjectNotFound(project_id)
    return Project.model_validate_json(path.read_text(encoding="utf-8"))


def delete_project(project_id: str) -> None:
    path = _project_file(project_id)
    if not path.exists():
        raise ProjectNotFound(project_id)
    path.unlink()


def list_projects() -> list[dict]:
    summaries: list[dict] = []
    for path in sorted(projects_dir().glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # a corrupt file should not break the project list
        summaries.append(
            {
                "id": data.get("id", path.stem),
                "name": data.get("name", path.stem),
                "node_count": len(data.get("nodes", [])),
                "virtual_link_count": len(data.get("virtual_links", [])),
                "updated_at": data.get("updated_at"),
            }
        )
    summaries.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
    return summaries


# --- environment config (machine-specific, not part of any project) ------------------------
def load_environment() -> EnvironmentConfig:
    path = env_config_file()
    if not path.exists():
        return EnvironmentConfig()
    try:
        return EnvironmentConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return EnvironmentConfig()


def save_environment(config: EnvironmentConfig) -> Path:
    path = env_config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2), encoding="utf-8")
    return path
