"""Topology graph: the physical network as the user draws it.

This is the *single-plane* logical topology. The dual-redundant A/B planes the AFDX library
expects are produced at codegen time by mirroring this graph -- see codegen/wiring.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

NodeKind = Literal["end_system", "switch"]


class TopologyNode(BaseModel):
    id: str
    kind: NodeKind
    label: str = ""
    # Canvas position. Purely cosmetic -- carries no simulation meaning, but is persisted so
    # reopening a project doesn't scramble the layout the user arranged.
    x: float = 0.0
    y: float = 0.0

    @field_validator("label")
    @classmethod
    def _default_label(cls, v: str, info) -> str:
        return v or info.data.get("id", "")


class TopologyEdge(BaseModel):
    """A physical cable between two nodes.

    Undirected: AFDX links are full duplex, and the NED `<-->` connection is bidirectional.
    """

    id: str
    node_a_id: str
    node_b_id: str
    length_m: float = Field(default=10.0, gt=0)
    # None means "inherit GeneralSettings.channel_datarate_bps".
    datarate_bps: float | None = Field(default=None, gt=0)

    def endpoints(self) -> tuple[str, str]:
        return (self.node_a_id, self.node_b_id)

    def other_end(self, node_id: str) -> str:
        if node_id == self.node_a_id:
            return self.node_b_id
        if node_id == self.node_b_id:
            return self.node_a_id
        raise ValueError(f"node {node_id!r} is not an endpoint of edge {self.id!r}")
