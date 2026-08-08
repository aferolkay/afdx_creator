"""Per-VL path resolution: shortest path by default, explicit override when the designer knows better.

Why an override exists: shortest hop count is not the same as lowest latency. Once several VLs
multiplex onto one egress port, that port's queueing can dominate; routing the long way round an
uncongested path can genuinely win. The tool must not silently overrule that judgement.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..domain.graph import Graph, GraphError


@dataclass(frozen=True)
class Path:
    """A resolved walk from a source end system to one destination end system."""

    source_id: str
    destination_id: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]

    @property
    def switch_hops(self) -> tuple[str, ...]:
        """Intermediate nodes -- i.e. the switches this VL traverses."""
        return self.node_ids[1:-1]


def shortest_path(graph: Graph, source_id: str, destination_id: str) -> Path:
    """BFS by hop count. Ties broken by edge id, so the result is deterministic across runs."""
    if source_id == destination_id:
        raise GraphError(f"source and destination are the same node ({source_id!r})")

    previous: dict[str, tuple[str, str]] = {}  # node -> (prev_node, edge_used)
    seen = {source_id}
    queue = deque([source_id])

    while queue:
        current = queue.popleft()
        if current == destination_id:
            break
        for neighbour, edge in sorted(graph.neighbours(current), key=lambda pair: pair[1].id):
            if neighbour not in seen:
                seen.add(neighbour)
                previous[neighbour] = (current, edge.id)
                queue.append(neighbour)

    if destination_id not in previous:
        raise GraphError(
            f"no route exists from {source_id!r} to {destination_id!r}; the topology is disconnected"
        )

    nodes: list[str] = [destination_id]
    edges: list[str] = []
    cursor = destination_id
    while cursor != source_id:
        prev_node, edge_id = previous[cursor]
        edges.append(edge_id)
        nodes.append(prev_node)
        cursor = prev_node

    return Path(
        source_id=source_id,
        destination_id=destination_id,
        node_ids=tuple(reversed(nodes)),
        edge_ids=tuple(reversed(edges)),
    )


def path_from_edge_ids(graph: Graph, source_id: str, destination_id: str, edge_ids) -> Path:
    """Build a Path from a designer-supplied edge list, verifying it is a real, connected walk.

    Rejects: unknown edges, a first edge not touching the source, a break in the chain, an end
    that isn't the destination, and revisiting a node (a loop would make the route table ambiguous,
    since a switch would need two different next-hop ports for one VL).
    """
    edge_ids = list(edge_ids)
    if not edge_ids:
        raise GraphError("explicit route is empty")

    nodes: list[str] = [source_id]
    cursor = source_id

    for position, edge_id in enumerate(edge_ids):
        try:
            edge = graph.edge(edge_id)
        except GraphError as exc:
            raise GraphError(f"explicit route step {position + 1} uses unknown link {edge_id!r}") from exc

        if cursor not in edge.endpoints():
            raise GraphError(
                f"explicit route is broken at step {position + 1}: link {edge_id!r} does not "
                f"touch {cursor!r}"
            )
        cursor = edge.other_end(cursor)
        if cursor in nodes:
            raise GraphError(
                f"explicit route revisits {cursor!r}; a route may not contain a loop"
            )
        nodes.append(cursor)

    if cursor != destination_id:
        raise GraphError(
            f"explicit route ends at {cursor!r} but the destination is {destination_id!r}"
        )

    return Path(
        source_id=source_id,
        destination_id=destination_id,
        node_ids=tuple(nodes),
        edge_ids=tuple(edge_ids),
    )


def resolve_paths(graph: Graph, virtual_link) -> list[Path]:
    """Resolve one VL to one Path per destination.

    An explicit override applies to a single-destination VL only: with several destinations there
    is no unambiguous way to say which branch a flat edge list describes. Multicast VLs therefore
    always use shortest paths (per destination) in this version.
    """
    destinations = list(virtual_link.destination_node_ids)

    if virtual_link.explicit_path_edge_ids:
        if len(destinations) != 1:
            raise GraphError(
                f"VL {virtual_link.label or virtual_link.hex_vl_id!r} has an explicit route but "
                f"{len(destinations)} destinations; explicit routes are supported for "
                "single-destination virtual links only"
            )
        return [
            path_from_edge_ids(
                graph, virtual_link.source_node_id, destinations[0], virtual_link.explicit_path_edge_ids
            )
        ]

    return [shortest_path(graph, virtual_link.source_node_id, dest) for dest in destinations]
