"""The golden test: does the generator reproduce the hand-built, simulator-validated network?

This is the strongest correctness signal available without running the simulator, because the
reference network was verified end to end against the real OMNeT++ binary.
"""

from __future__ import annotations

from afdx_generator.codegen.context import assemble
from afdx_generator.codegen.render import render_all
from fixtures.simplenetwork_project import (
    EXPECTED_MESSAGE_COUNTS,
    EXPECTED_PORT_COUNTS,
    EXPECTED_ROUTE_TABLES,
    build_simplenetwork_project,
)


def _label_of(context, node_id):
    node = context.graph.node(node_id)
    return node.label or node.id


def test_route_tables_match_hand_built_network():
    context = assemble(build_simplenetwork_project())

    actual = {
        _label_of(context, switch_id): table.entries
        for switch_id, table in context.route_tables.items()
    }

    assert set(actual) == set(EXPECTED_ROUTE_TABLES)
    for switch_label, expected in EXPECTED_ROUTE_TABLES.items():
        assert actual[switch_label] == expected, f"route table mismatch for switch {switch_label}"


def test_pass_through_virtual_links_are_present():
    """A VL merely transiting a switch still needs an entry, or the router aborts the run."""
    context = assemble(build_simplenetwork_project())
    by_label = {
        _label_of(context, switch_id): table.entries
        for switch_id, table in context.route_tables.items()
    }
    # V6/V7/V8/V9/V13 originate behind S3 and only pass through S1 on their way to S2.
    for key in ("0x6", "0x7", "0x8", "0x9", "0xD"):
        assert key in by_label["S1"], f"{key} missing from S1 (pass-through link)"


def test_switch_port_counts_are_inferred_from_topology():
    context = assemble(build_simplenetwork_project())
    profile = context.profile
    actual = {
        sw.label: sw.params[profile.module_params.switch_port_count]
        for sw in context.wiring.switches_a
    }
    assert actual == EXPECTED_PORT_COUNTS


def test_message_counts_match_sourced_virtual_links():
    context = assemble(build_simplenetwork_project())
    profile = context.profile
    actual = {
        es.label: es.params[profile.module_params.end_system_message_count]
        for es in context.wiring.end_systems
    }
    assert actual == EXPECTED_MESSAGE_COUNTS


def test_traffic_parameters_match_validated_values():
    """rho/sigma for a sample of VLs, against the values that ran clean in the real simulator."""
    context = assemble(build_simplenetwork_project())
    by_label = {plan.label: plan for plan in context.vl_plans}

    expected = {  # label: (rho bps, sigma bits, Lmax bits)
        "V1": (10e6, 40000, 10000),
        "V2": (2.556e6, 20448, 5112),
        "V5": (3.536e6, 14144, 3536),
        "V8": (4.436e6, 35488, 8872),
        "V11": (0.614e6, 9824, 2456),
        "V14": (1.228e6, 9824, 2456),
    }
    for label, (rho, sigma, lmax) in expected.items():
        plan = by_label[label]
        assert plan.lmax_bits == lmax, f"{label} Lmax"
        assert abs(plan.rho_bps - rho) < 1.0, f"{label} rho"
        assert abs(plan.sigma_bits - sigma) < 0.5, f"{label} sigma"


def test_both_redundancy_planes_are_wired_identically():
    context = assemble(build_simplenetwork_project())
    conns = context.wiring.connections
    plane_a = [(c.a.module_ref, c.a.gate, c.b.module_ref, c.b.gate) for c in conns if c.plane == "A"]
    plane_b = [(c.a.module_ref, c.a.gate, c.b.module_ref, c.b.gate) for c in conns if c.plane == "B"]

    assert len(plane_a) == len(plane_b) == 11  # one per physical link, per plane

    profile = context.profile
    normalise = lambda items, vec: [  # noqa: E731
        (a.replace(vec, "SW"), ag.replace("ethPortA", "P").replace("ethPortB", "P"),
         b.replace(vec, "SW"), bg.replace("ethPortA", "P").replace("ethPortB", "P"))
        for a, ag, b, bg in items
    ]
    assert normalise(plane_a, profile.switch_plane_a_vector_name) == normalise(
        plane_b, profile.switch_plane_b_vector_name
    )


def test_generated_files_are_written(tmp_path):
    context = assemble(build_simplenetwork_project())
    result = render_all(context, tmp_path)

    assert result.ned_file.exists()
    assert result.ini_file.exists()
    assert len(result.route_table_files) == 5
    assert not result.warnings

    ned = result.ned_file.read_text()
    assert "network simpleNetwork" in ned
    assert "SwitchA[5]" in ned and "SwitchB[5]" in ned and "ES[7]" in ned
