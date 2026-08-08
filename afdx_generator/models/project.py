"""The top-level saved document: one AFDX network design."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..domain.naming import sanitize_ned_identifier, sanitize_path_segment
from .settings import GeneralSettings
from .topology import TopologyEdge, TopologyNode
from .virtual_link import VirtualLink

SCHEMA_VERSION = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(BaseModel):
    schema_version: int = SCHEMA_VERSION
    id: str
    # Raw, as typed by the user -- may contain spaces, hyphens, anything.
    name: str
    nodes: list[TopologyNode] = Field(default_factory=list)
    edges: list[TopologyEdge] = Field(default_factory=list)
    virtual_links: list[VirtualLink] = Field(default_factory=list)
    general_settings: GeneralSettings = Field(default_factory=GeneralSettings)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def ned_network_name(self) -> str:
        """The NED `network` type name, and the .ned/.ini filename stem."""
        return sanitize_ned_identifier(self.name)

    @property
    def output_dir_name(self) -> str:
        return sanitize_path_segment(self.name)

    @property
    def ini_config_name(self) -> str:
        """The [ConfigName] section in the generated ini, passed to the simulator via -c."""
        return self.ned_network_name

    def node_by_id(self, node_id: str) -> TopologyNode | None:
        return next((n for n in self.nodes if n.id == node_id), None)

    def edge_by_id(self, edge_id: str) -> TopologyEdge | None:
        return next((e for e in self.edges if e.id == edge_id), None)

    def touch(self) -> None:
        self.updated_at = _utcnow()
