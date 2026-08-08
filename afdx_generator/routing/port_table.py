"""Port numbering, and the per-switch VL routing tables derived from it.

THE CENTRAL INVARIANT OF THIS TOOL
----------------------------------
A switch's port index means two things that must agree exactly:

  1. which gate a cable is wired to in the generated .ned  (`SwitchA[2].ethPort[0] <--> ...`)
  2. which port a VL is sent out of in that switch's route table  (`0x1 : {0}`)

If they disagree, the simulation still runs -- it just delivers frames to the wrong places, which
is far harder to notice than a crash. The mechanism that prevents this is simply that both come
from ONE call to `canonical_port_order()`, threaded through the pipeline. Never recompute it
independently, and never sort edges ad hoc anywhere else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..domain.graph import Graph
from .pathfinder import Path

_NUM_CHUNK = re.compile(r"(\d+)")


def _natural_key(text: str) -> tuple:
    """Sort key so that e2 < e10 (plain string sort would give e10 < e2)."""
    return tuple(int(part) if part.isdigit() else part for part in _NUM_CHUNK.split(text))


# node id -> ordered tuple of edge ids; the index in that tuple IS the port number.
PortOrder = dict[str, tuple[str, ...]]


def canonical_port_order(graph: Graph) -> PortOrder:
    """Assign every node a deterministic ordering of its incident links.

    Deterministic across runs and machines (natural sort on edge id) so regenerating an unchanged
    project produces byte-identical output, which makes diffs meaningful.
    """
    order: PortOrder = {}
    for node in graph.nodes:
        incident = graph.incident_edges(node.id)
        order[node.id] = tuple(sorted((e.id for e in incident), key=_natural_key))
    return order


def port_index(port_order: PortOrder, node_id: str, edge_id: str) -> int:
    try:
        return port_order[node_id].index(edge_id)
    except (KeyError, ValueError) as exc:
        raise KeyError(f"link {edge_id!r} is not connected to node {node_id!r}") from exc


@dataclass(frozen=True)
class SwitchRouteTable:
    switch_id: str
    # VL route-table key ("0x1") -> sorted output port indices. More than one port = multicast.
    entries: dict[str, tuple[int, ...]]


def build_switch_route_tables(
    graph: Graph,
    port_order: PortOrder,
    resolved: dict[str, list[Path]],
) -> dict[str, SwitchRouteTable]:
    """Build every switch's VL table from the resolved per-VL paths.

    `resolved` maps a VL's route-table key ("0x1") to its resolved paths (one per destination).

    Crucially this includes **pass-through** VLs -- a VL merely transiting a switch on its way
    elsewhere still needs an entry there. The library's VLRouter throws

        Key Not Found in VL Table!

    and aborts the run for any VL id that arrives at a switch with no entry, so an omission here
    is fatal at runtime rather than merely suboptimal.
    """
    # switch id -> vl key -> set of output ports
    accumulator: dict[str, dict[str, set[int]]] = {sw.id: {} for sw in graph.switches()}

    for vl_key, paths in resolved.items():
        for path in paths:
            # Walk every node that has an outgoing hop -- i.e. all but the final destination.
            # node_ids[i] is followed by edge_ids[i], so bounding by len(edge_ids) is what keeps
            # this in range regardless of what kind of node the path happens to end on.
            for position in range(len(path.edge_ids)):
                node_id = path.node_ids[position]
                if node_id not in accumulator:
                    continue  # an end system, not a switch -- it has no routing table
                next_edge_id = path.edge_ids[position]  # edge leaving this node toward the dest
                port = port_index(port_order, node_id, next_edge_id)
                accumulator[node_id].setdefault(vl_key, set()).add(port)

    return {
        switch_id: SwitchRouteTable(
            switch_id=switch_id,
            entries={key: tuple(sorted(ports)) for key, ports in sorted(entries.items())},
        )
        for switch_id, entries in accumulator.items()
    }
