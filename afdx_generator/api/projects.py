"""Project CRUD, plus the topology/VL/settings edits that operate on a loaded project."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..domain.graph import Graph, validate_topology, validate_virtual_links
from ..models.project import Project
from ..models.settings import GeneralSettings
from ..models.topology import TopologyEdge, TopologyNode
from ..models.virtual_link import VirtualLink
from ..storage import project_store

router = APIRouter(prefix="/api/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str


class ProjectUpdate(BaseModel):
    """A whole-document save. The UI keeps the authoritative copy and posts it back."""

    name: str | None = None
    nodes: list[TopologyNode] | None = None
    edges: list[TopologyEdge] | None = None
    virtual_links: list[VirtualLink] | None = None
    general_settings: GeneralSettings | None = None


def get_project_or_404(project_id: str) -> Project:
    try:
        return project_store.load_project(project_id)
    except project_store.ProjectNotFound:
        raise HTTPException(status_code=404, detail=f"No project with id {project_id!r}")


@router.get("")
def list_projects():
    return project_store.list_projects()


@router.post("", status_code=201)
def create_project(request: CreateProjectRequest):
    name = request.name.strip() or "Untitled"
    # The id becomes the filename, so derive it from the name to keep projects/ readable.
    project = Project(id=project_store.new_project_id(name), name=name)
    project_store.save_project(project)
    return project


@router.get("/{project_id}")
def get_project(project_id: str):
    return get_project_or_404(project_id)


@router.put("/{project_id}")
def update_project(project_id: str, update: ProjectUpdate):
    project = get_project_or_404(project_id)

    for field in ("name", "nodes", "edges", "virtual_links", "general_settings"):
        value = getattr(update, field)
        if value is not None:
            setattr(project, field, value)

    project_store.save_project(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str):
    try:
        project_store.delete_project(project_id)
    except project_store.ProjectNotFound:
        raise HTTPException(status_code=404, detail=f"No project with id {project_id!r}")


@router.get("/{project_id}/problems")
def get_problems(project_id: str):
    """Non-blocking validation, so the UI can warn while editing rather than only on generate."""
    project = get_project_or_404(project_id)
    graph = Graph.build(project.nodes, project.edges)
    problems = validate_topology(graph)
    problems += validate_virtual_links(graph, project.virtual_links)
    return {"problems": problems}
