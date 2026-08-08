"""Unit tests for naming, graph validation, routing, traffic math, and persistence."""

from __future__ import annotations

import pytest

from afdx_generator.domain.graph import Graph, GraphError, validate_topology, validate_virtual_links
from afdx_generator.domain.naming import sanitize_ned_identifier, sanitize_path_segment
from afdx_generator.models.project import Project
from afdx_generator.models.topology import TopologyEdge, TopologyNode
from afdx_generator.models.virtual_link import VirtualLink
from afdx_generator.routing.pathfinder import path_from_edge_ids, resolve_paths, shortest_path
from afdx_generator.routing.port_table import canonical_port_order
from afdx_generator.trafficmath.rho_sigma import suggest, wire_frame_bits


# --------------------------------------------------------------------------- naming
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("simple-network", "simple_network"),   # the hyphen that breaks the NED loader
        ("my network", "my_network"),
        ("2fast", "fast"),                       # cannot start with a digit
        ("network", "network_"),                 # reserved word
        ("Good_Name1", "Good_Name1"),
        ("!!!", "Network"),                      # nothing usable left
    ],
)
def test_ned_identifier_sanitising(raw, expected):
    assert sanitize_ned_identifier(raw) == expected


def test_path_segment_never_escapes_a_directory():
    for hostile in ("../../etc/passwd", "/absolute", "..", "a/b"):
        result = sanitize_path_segment(hostile)
        assert "/" not in result and result not in ("", ".", "..")


# --------------------------------------------------------------------------- graph
def _line_graph():
    """E0 - S1 - S2 - E1"""
    nodes = [
        TopologyNode(id="es0", kind="end_system", label="E0"),
        TopologyNode(id="es1", kind="end_system", label="E1"),
        TopologyNode(id="sw1", kind="switch", label="S1"),
        TopologyNode(id="sw2", kind="switch", label="S2"),
    ]
    edges = [
        TopologyEdge(id="e1", node_a_id="es0", node_b_id="sw1"),
        TopologyEdge(id="e2", node_a_id="sw1", node_b_id="sw2"),
        TopologyEdge(id="e3", node_a_id="sw2", node_b_id="es1"),
    ]
    return Graph.build(nodes, edges)


def test_valid_topology_reports_no_problems():
    assert validate_topology(_line_graph()) == []


def test_disconnected_node_is_reported():
    graph = _line_graph()
    nodes = list(graph.nodes) + [TopologyNode(id="sw9", kind="switch", label="S9")]
    problems = validate_topology(Graph.build(nodes, graph.edges))
    assert any("not connected" in p for p in problems)


def test_end_system_with_two_links_is_reported():
    """An EndSystem has one physical port per plane; a second cable has nowhere to go."""
    graph = _line_graph()
    edges = list(graph.edges) + [TopologyEdge(id="e4", node_a_id="es0", node_b_id="sw2")]
    problems = validate_topology(Graph.build(graph.nodes, edges))
    assert any("exactly one" in p for p in problems)


def test_duplicate_link_between_same_pair_is_reported():
    graph = _line_graph()
    edges = list(graph.edges) + [TopologyEdge(id="e9", node_a_id="sw1", node_b_id="sw2")]
    problems = validate_topology(Graph.build(graph.nodes, edges))
    assert any("More than one link" in p for p in problems)


def test_dangling_edge_endpoint_is_reported():
    graph = _line_graph()
    edges = list(graph.edges) + [TopologyEdge(id="e9", node_a_id="sw1", node_b_id="ghost")]
    problems = validate_topology(Graph.build(graph.nodes, edges))
    assert any("no longer exists" in p for p in problems)


def test_virtual_link_pointing_at_a_switch_is_reported():
    graph = _line_graph()
    vl = VirtualLink(id="v", hex_vl_id="0x1", frame_bytes=100, source_node_id="es0",
                     destination_node_ids=["sw2"], bag_s=0.001)
    problems = validate_virtual_links(graph, [vl])
    assert any("destination" in p and "switch" in p for p in problems)


def test_duplicate_virtual_link_ids_are_reported():
    graph = _line_graph()
    vls = [
        VirtualLink(id="a", hex_vl_id="0x1", label="A", frame_bytes=100,
                    source_node_id="es0", destination_node_ids=["es1"], bag_s=0.001),
        VirtualLink(id="b", hex_vl_id="0x1", label="B", frame_bytes=100,
                    source_node_id="es1", destination_node_ids=["es0"], bag_s=0.001),
    ]
    assert any("must be unique" in p for p in validate_virtual_links(graph, vls))


# --------------------------------------------------------------------------- VL model
def test_virtual_link_id_must_be_valid_hex_in_range():
    for bad in ("", "zz", "0x0", "0x10000"):
        with pytest.raises(ValueError):
            VirtualLink(id="v", hex_vl_id=bad, frame_bytes=10,
                        source_node_id="a", destination_node_ids=["b"], bag_s=0.001)


def test_route_table_key_is_normalised_uppercase_hex():
    vl = VirtualLink(id="v", hex_vl_id="0xe", frame_bytes=10, source_node_id="a",
                     destination_node_ids=["b"], bag_s=0.001)
    assert vl.numeric_id == 14
    assert vl.route_table_key == "0xE"


# --------------------------------------------------------------------------- routing
def test_shortest_path_finds_the_expected_walk():
    path = shortest_path(_line_graph(), "es0", "es1")
    assert path.node_ids == ("es0", "sw1", "sw2", "es1")
    assert path.edge_ids == ("e1", "e2", "e3")
    assert path.switch_hops == ("sw1", "sw2")


def test_no_route_raises():
    nodes = [TopologyNode(id="a", kind="end_system"), TopologyNode(id="b", kind="end_system")]
    with pytest.raises(GraphError):
        shortest_path(Graph.build(nodes, []), "a", "b")


def test_explicit_route_is_accepted_when_it_is_a_real_walk():
    path = path_from_edge_ids(_line_graph(), "es0", "es1", ["e1", "e2", "e3"])
    assert path.node_ids == ("es0", "sw1", "sw2", "es1")


def test_explicit_route_with_a_gap_is_rejected():
    with pytest.raises(GraphError, match="broken"):
        path_from_edge_ids(_line_graph(), "es0", "es1", ["e1", "e3"])


def test_explicit_route_ending_somewhere_else_is_rejected():
    with pytest.raises(GraphError, match="ends at"):
        path_from_edge_ids(_line_graph(), "es0", "es1", ["e1", "e2"])


def test_explicit_route_referencing_a_deleted_link_is_rejected():
    with pytest.raises(GraphError, match="unknown link"):
        path_from_edge_ids(_line_graph(), "es0", "es1", ["e1", "gone", "e3"])


def test_explicit_route_is_preferred_over_shortest_path():
    """The whole point of the override: the designer's choice must win."""
    # Diamond: es0 -> sw1 -> {sw2 | sw3} -> sw4 -> es1. Both branches are equal length,
    # so pinning one must be honoured rather than silently re-decided.
    nodes = [
        TopologyNode(id="es0", kind="end_system"), TopologyNode(id="es1", kind="end_system"),
        TopologyNode(id="sw1", kind="switch"), TopologyNode(id="sw2", kind="switch"),
        TopologyNode(id="sw3", kind="switch"), TopologyNode(id="sw4", kind="switch"),
    ]
    edges = [
        TopologyEdge(id="e1", node_a_id="es0", node_b_id="sw1"),
        TopologyEdge(id="e2", node_a_id="sw1", node_b_id="sw2"),
        TopologyEdge(id="e3", node_a_id="sw1", node_b_id="sw3"),
        TopologyEdge(id="e4", node_a_id="sw2", node_b_id="sw4"),
        TopologyEdge(id="e5", node_a_id="sw3", node_b_id="sw4"),
        TopologyEdge(id="e6", node_a_id="sw4", node_b_id="es1"),
    ]
    graph = Graph.build(nodes, edges)

    vl = VirtualLink(id="v", hex_vl_id="0x1", frame_bytes=100, source_node_id="es0",
                     destination_node_ids=["es1"], bag_s=0.001,
                     explicit_path_edge_ids=["e1", "e3", "e5", "e6"])  # via sw3
    assert resolve_paths(graph, vl)[0].node_ids == ("es0", "sw1", "sw3", "sw4", "es1")


def test_port_order_is_deterministic_and_numerically_sorted():
    """e2 must come before e10 -- plain string sort would put e10 first."""
    nodes = [TopologyNode(id="sw", kind="switch")] + [
        TopologyNode(id=f"es{i}", kind="end_system") for i in range(3)
    ]
    edges = [
        TopologyEdge(id="e10", node_a_id="sw", node_b_id="es0"),
        TopologyEdge(id="e2", node_a_id="sw", node_b_id="es1"),
        TopologyEdge(id="e1", node_a_id="sw", node_b_id="es2"),
    ]
    order = canonical_port_order(Graph.build(nodes, edges))
    assert order["sw"] == ("e1", "e2", "e10")


# --------------------------------------------------------------------------- traffic math
def test_wire_frame_includes_header_and_physical_overhead():
    assert wire_frame_bits(1183, 47, 160) == 10000


def test_rho_is_not_padded_by_the_margin():
    """Only the burst allowance carries margin; inflating rho would hide a misbehaving source."""
    a = suggest(1000, 0.001, 47, 160, margin_factor=1.0)
    b = suggest(1000, 0.001, 47, 160, margin_factor=8.0)
    assert a.rho_bps == b.rho_bps
    assert b.sigma_bits == 8 * a.sigma_bits


def test_invalid_traffic_inputs_are_rejected():
    with pytest.raises(ValueError):
        suggest(100, 0, 47, 160, 4.0)
    with pytest.raises(ValueError):
        suggest(100, 0.001, 47, 160, 0)


# --------------------------------------------------------------------------- persistence
def test_project_survives_a_json_round_trip():
    project = Project(
        id="p1",
        name="test-network",
        nodes=[TopologyNode(id="a", kind="end_system", label="E0", x=1.5, y=-2.5)],
        edges=[],
        virtual_links=[],
    )
    restored = Project.model_validate_json(project.model_dump_json())
    assert restored.name == "test-network"
    assert restored.ned_network_name == "test_network"   # hyphen sanitised for NED
    assert restored.nodes[0].x == 1.5
