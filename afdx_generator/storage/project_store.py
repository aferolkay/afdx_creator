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


# Long enough to stay descriptive, short enough to keep filenames manageable.
_MAX_ID_LENGTH = 60


def new_project_id(name: str = "") -> str:
    """Pick an id for a new project, derived from its name where possible.

    The id IS the filename (see `_project_file`), so deriving it from the name means
    `projects/realisticNetwork.json` rather than `projects/f0a2eb5fa15d.json`. Ids still have to
    be unique, so a name already in use gets a numeric suffix.

    Falls back to a random id when the name has nothing usable in it (e.g. "***"), because an
    unreadable id is much better than a collision or an empty filename.
    """
    from ..domain.naming import sanitize_path_segment

    base = sanitize_path_segment(name, fallback="")[:_MAX_ID_LENGTH].strip("._-")
    if not base:
        return uuid.uuid4().hex[:12]

    taken = _existing_ids()
    if base.lower() not in taken:
        return base

    # "project", "project-2", "project-3", ... The bound is a safety net, not a real limit.
    for suffix in range(2, 1000):
        candidate = f"{base}-{suffix}"
        if candidate.lower() not in taken:
            return candidate
    return uuid.uuid4().hex[:12]


def _existing_ids() -> set[str]:
    """Ids already on disk, lowercased.

    Compared case-insensitively on purpose: Linux would happily keep `Net.json` and `net.json`
    side by side, but a project file copied to a case-insensitive filesystem (macOS, Windows)
    would then silently overwrite its twin.
    """
    return {p.stem.lower() for p in projects_dir().glob("*.json")}


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
