"""Adjacency view over the topology, plus the checks that must pass before generating anything.

Catching these here is the whole point: most of them would otherwise surface as a cryptic C++
runtime throw several minutes into a simulation run, or -- worse -- as a silently wrong network.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..models.topology import TopologyEdge, TopologyNode
from ..models.virtual_link import VirtualLink


class GraphError(ValueError):
    """A topology problem that makes generation impossible or meaningless."""


@dataclass(frozen=True)
class Graph:
    """Immutable adjacency wrapper. Built once per generation, passed down the pipeline."""

    nodes: tuple[TopologyNode, ...]
    edges: tuple[TopologyEdge, ...]

    @classmethod
    def build(cls, nodes, edges) -> "Graph":
        return cls(tuple(nodes), tuple(edges))

    # --- lookups --------------------------------------------------------------------------
    @property
    def node_ids(self) -> set[str]:
        return {n.id for n in self.nodes}

    def node(self, node_id: str) -> TopologyNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise GraphError(f"unknown node id {node_id!r}")

    def edge(self, edge_id: str) -> TopologyEdge:
        for e in self.edges:
            if e.id == edge_id:
                return e
        raise GraphError(f"unknown edge id {edge_id!r}")

    def incident_edges(self, node_id: str) -> list[TopologyEdge]:
        return [e for e in self.edges if node_id in e.endpoints()]

    def degree(self, node_id: str) -> int:
        return len(self.incident_edges(node_id))

    def neighbours(self, node_id: str) -> list[tuple[str, TopologyEdge]]:
        return [(e.other_end(node_id), e) for e in self.incident_edges(node_id)]

    def switches(self) -> list[TopologyNode]:
        return [n for n in self.nodes if n.kind == "switch"]

    def end_systems(self) -> list[TopologyNode]:
        return [n for n in self.nodes if n.kind == "end_system"]


def validate_topology(graph: Graph) -> list[str]:
    """Return a list of human-readable problems. Empty list means the topology is usable."""
    problems: list[str] = []
    ids = graph.node_ids

    if not graph.nodes:
        return ["Topology is empty: add at least two end systems and a switch."]

    # Dangling edge endpoints.
    for e in graph.edges:
        for endpoint in e.endpoints():
            if endpoint not in ids:
                problems.append(f"Link {e.id!r} refers to a node {endpoint!r} that no longer exists.")
    if problems:
        # Everything below assumes edges reference real nodes.
        return problems

    # Self loops.
    for e in graph.edges:
        if e.node_a_id == e.node_b_id:
            problems.append(f"Link {e.id!r} connects node {e.node_a_id!r} to itself.")

    # Duplicate parallel links. Two cables between the same pair would give a switch two ports to
    # the same neighbour, which the port-index model has no way to express meaningfully.
    seen: set[frozenset[str]] = set()
    for e in graph.edges:
        key = frozenset(e.endpoints())
        if key in seen:
            a, b = sorted(e.endpoints())
            problems.append(f"More than one link connects {a!r} and {b!r}.")
        seen.add(key)

    # End systems have exactly one cable. The library's EndSystem has one ethPortA/ethPortB pair,
    # so a second link has nowhere to attach.
    for n in graph.end_systems():
        d = graph.degree(n.id)
        if d == 0:
            problems.append(f"End system {n.label or n.id!r} is not connected to anything.")
        elif d > 1:
            problems.append(
                f"End system {n.label or n.id!r} has {d} links; an end system supports exactly one."
            )

    for n in graph.switches():
        if graph.degree(n.id) == 0:
            problems.append(f"Switch {n.label or n.id!r} is not connected to anything.")

    # Connectivity: anything unreachable can never carry a VL.
    if graph.nodes:
        reachable = _reachable_from(graph, graph.nodes[0].id)
        stranded = sorted(ids - reachable)
        if stranded:
            names = ", ".join(repr(graph.node(s).label or s) for s in stranded[:5])
            more = f" (and {len(stranded) - 5} more)" if len(stranded) > 5 else ""
            problems.append(f"Topology is not fully connected; unreachable: {names}{more}.")

    return problems


def validate_virtual_links(graph: Graph, virtual_links) -> list[str]:
    """Check VLs against the topology: real endpoints, right node kinds, unique ids."""
    problems: list[str] = []
    ids = graph.node_ids

    seen_vl: dict[int, str] = {}
    for vl in virtual_links:
        name = vl.label or vl.hex_vl_id

        if vl.numeric_id in seen_vl:
            problems.append(
                f"Virtual link id {vl.route_table_key} is used by both "
                f"{seen_vl[vl.numeric_id]!r} and {name!r}; ids must be unique."
            )
        else:
            seen_vl[vl.numeric_id] = name

        if vl.source_node_id not in ids:
            problems.append(f"VL {name!r} has a source node that no longer exists.")
        elif graph.node(vl.source_node_id).kind != "end_system":
            problems.append(f"VL {name!r} has a switch as its source; sources must be end systems.")

        for dest in vl.destination_node_ids:
            if dest not in ids:
                problems.append(f"VL {name!r} has a destination node that no longer exists.")
            elif graph.node(dest).kind != "end_system":
                problems.append(
                    f"VL {name!r} has a switch as a destination; destinations must be end systems."
                )
            elif dest == vl.source_node_id:
                problems.append(f"VL {name!r} has its own source as a destination.")

        if len(set(vl.destination_node_ids)) != len(vl.destination_node_ids):
            problems.append(f"VL {name!r} lists the same destination more than once.")

        if vl.explicit_path_edge_ids:
            for edge_id in vl.explicit_path_edge_ids:
                if edge_id not in {e.id for e in graph.edges}:
                    problems.append(
                        f"VL {name!r} has an explicit route using link {edge_id!r}, "
                        "which no longer exists."
                    )
                    break

    return problems


def _reachable_from(graph: Graph, start: str) -> set[str]:
    seen = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for neighbour, _edge in graph.neighbours(current):
            if neighbour not in seen:
                seen.add(neighbour)
                queue.append(neighbour)
    return seen
