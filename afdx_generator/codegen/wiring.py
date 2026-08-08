"""Turn one logical topology into the two mirrored redundancy planes the AFDX library expects.

The user draws ONE network. AFDX is dual-redundant: every frame is transmitted on two physically
separate networks, and the receiving end system discards whichever copy arrives second. So the
generated .ned instantiates the drawn topology twice -- SwitchA[] and SwitchB[] -- with each end
system's ethPortA going to plane A and ethPortB to plane B.

Mirroring here rather than making the user draw both planes guarantees they are structurally
identical, which is what the library's RedundancyChecker assumes when it matches up frame pairs.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.graph import Graph
from ..routing.port_table import PortOrder, port_index


@dataclass(frozen=True)
class ModuleInstance:
    """One entry in the generated `submodules:` block."""

    vector_name: str      # e.g. "ES" or "SwitchA"
    index: int
    node_id: str
    label: str
    # Extra per-instance NED parameters, e.g. {"noOfPorts": 4}. Rendered inline in the submodule.
    params: dict[str, object]

    @property
    def ned_ref(self) -> str:
        return f"{self.vector_name}[{self.index}]"


@dataclass(frozen=True)
class ConnectionEnd:
    """One side of a `<-->` connection: a module and the gate to attach to."""

    module_ref: str   # e.g. "SwitchA[0]"
    gate: str         # e.g. "ethPort[2]" or "ethPortA"


@dataclass(frozen=True)
class Connection:
    a: ConnectionEnd
    b: ConnectionEnd
    plane: str        # "A" or "B" -- for grouping/commenting the generated output
    comment: str
    length_m: float
    datarate_bps: float | None


@dataclass(frozen=True)
class Wiring:
    end_systems: tuple[ModuleInstance, ...]
    switches_a: tuple[ModuleInstance, ...]
    switches_b: tuple[ModuleInstance, ...]
    connections: tuple[Connection, ...]
    # node id -> index within its vector. Needed by context.py to address instances in the ini.
    end_system_index: dict[str, int]
    switch_index: dict[str, int]


def build_wiring(
    graph: Graph,
    port_order: PortOrder,
    profile,
    vl_count_by_source: dict[str, int],
) -> Wiring:
    """Produce the module instances and connection list for both redundancy planes."""
    gates = profile.gates
    mparams = profile.module_params

    # Stable ordering so regenerating an unchanged project yields identical output.
    end_system_nodes = sorted(graph.end_systems(), key=lambda n: n.id)
    switch_nodes = sorted(graph.switches(), key=lambda n: n.id)

    es_index = {n.id: i for i, n in enumerate(end_system_nodes)}
    sw_index = {n.id: i for i, n in enumerate(switch_nodes)}

    end_systems = tuple(
        ModuleInstance(
            vector_name=profile.end_system_vector_name,
            index=i,
            node_id=n.id,
            label=n.label or n.id,
            # messageCount sizes the messageSource[]/afdxMarshall[] vectors. Receive-only end
            # systems get 0, which the library handles (a zero-length submodule vector is legal).
            params={mparams.end_system_message_count: vl_count_by_source.get(n.id, 0)},
        )
        for i, n in enumerate(end_system_nodes)
    )

    def switch_instances(vector_name: str) -> tuple[ModuleInstance, ...]:
        return tuple(
            ModuleInstance(
                vector_name=vector_name,
                index=i,
                node_id=n.id,
                label=n.label or n.id,
                # Port count is the node's degree -- inferred, never hand-entered.
                params={mparams.switch_port_count: len(port_order[n.id])},
            )
            for i, n in enumerate(switch_nodes)
        )

    switches_a = switch_instances(profile.switch_plane_a_vector_name)
    switches_b = switch_instances(profile.switch_plane_b_vector_name)

    connections: list[Connection] = []
    for plane, switch_vector, es_gate in (
        ("A", profile.switch_plane_a_vector_name, gates.end_system_port_a),
        ("B", profile.switch_plane_b_vector_name, gates.end_system_port_b),
    ):
        for edge in sorted(graph.edges, key=lambda e: e.id):
            ends: list[ConnectionEnd] = []
            labels: list[str] = []
            for node_id in edge.endpoints():
                node = graph.node(node_id)
                if node.kind == "end_system":
                    ends.append(
                        ConnectionEnd(
                            module_ref=f"{profile.end_system_vector_name}[{es_index[node_id]}]",
                            gate=es_gate,
                        )
                    )
                else:
                    port = port_index(port_order, node_id, edge.id)
                    ends.append(
                        ConnectionEnd(
                            module_ref=f"{switch_vector}[{sw_index[node_id]}]",
                            gate=f"{gates.switch_port_vector}[{port}]",
                        )
                    )
                labels.append(node.label or node.id)

            connections.append(
                Connection(
                    a=ends[0],
                    b=ends[1],
                    plane=plane,
                    comment=f"{labels[0]} - {labels[1]}",
                    length_m=edge.length_m,
                    datarate_bps=edge.datarate_bps,
                )
            )

    return Wiring(
        end_systems=end_systems,
        switches_a=switches_a,
        switches_b=switches_b,
        connections=tuple(connections),
        end_system_index=es_index,
        switch_index=sw_index,
    )
