"""Rows taken from a published avionics message set, to check the model can express it as written.

That table specifies, per virtual link, a BAG and a separate X (how often the source actually
offers a frame). X is sometimes a single value and sometimes a range, and the payload is sometimes
a range too. Every row satisfies min(X) >= BAG -- the rule the generator warns about.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from afdx_generator.codegen.context import assemble
from afdx_generator.codegen.render import render_all
from afdx_generator.models.project import Project
from afdx_generator.models.topology import TopologyEdge, TopologyNode
from afdx_generator.models.virtual_link import VirtualLink


def _project(*vls: VirtualLink) -> Project:
    return Project(
        id="t4", name="table4",
        nodes=[
            TopologyNode(id="es0", kind="end_system", label="E0"),
            TopologyNode(id="es1", kind="end_system", label="E1"),
            TopologyNode(id="es2", kind="end_system", label="E2"),
            TopologyNode(id="sw1", kind="switch", label="S1"),
        ],
        edges=[
            TopologyEdge(id="e1", node_a_id="es0", node_b_id="sw1"),
            TopologyEdge(id="e2", node_a_id="sw1", node_b_id="es1"),
            TopologyEdge(id="e3", node_a_id="sw1", node_b_id="es2"),
        ],
        virtual_links=list(vls),
    )


def _vl(hex_id, bag_ms, *, bytes_min, bytes_max=None, period_ms=None,
        gap_ms=None, dests=("es1",)) -> VirtualLink:
    return VirtualLink(
        id=f"vl{hex_id}", hex_vl_id=hex_id, label=hex_id,
        frame_bytes=bytes_min, frame_bytes_max=bytes_max,
        source_node_id="es0", destination_node_ids=list(dests),
        bag_s=bag_ms / 1000,
        arrival_pattern="uniform" if gap_ms else "periodic",
        period_s=period_ms / 1000 if period_ms else None,
        arrival_min_s=gap_ms[0] / 1000 if gap_ms else None,
        arrival_max_s=gap_ms[1] / 1000 if gap_ms else None,
    )


def _ini(project) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        return render_all(assemble(project), pathlib.Path(tmp)).ini_file.read_text()


def test_periodic_period_may_differ_from_bag():
    """Row 0x14: BAG 32ms but the source sends every 40ms.

    Tying the period to the BAG would generate 32ms and overstate this link's traffic.
    """
    vl = _vl("0x14", 32, bytes_min=53, period_ms=40)
    assert vl.effective_period_s == pytest.approx(0.040)
    ini = _ini(_project(vl))
    assert "interArrivalTime = 40ms" in ini
    assert "BAG = 32ms" in ini          # the contract is unchanged
    assert "slower than its 32ms BAG" in ini


def test_period_defaults_to_bag_when_unset():
    ini = _ini(_project(_vl("0x9", 4, bytes_min=17)))
    assert "interArrivalTime = 4ms" in ini
    assert "one frame every BAG" in ini


def test_row_0x18_has_both_a_slower_period_and_a_payload_range():
    """Row 0x18: BAG 8ms, X 40ms, p (683, 1183) -- every feature at once."""
    vl = _vl("0x18", 8, bytes_min=683, bytes_max=1183, period_ms=40, dests=("es1", "es2"))
    ini = _ini(_project(vl))

    assert "interArrivalTime = 40ms" in ini
    assert "packetLength = intuniform(683, 1183)" in ini
    # Policing must be sized for the LARGEST frame, not the smallest.
    assert "rho = " in ini and "sigma = " in ini


def test_traffic_parameters_use_the_largest_frame():
    small = assemble(_project(_vl("0x1", 8, bytes_min=683))).vl_plans[0]
    ranged = assemble(_project(_vl("0x1", 8, bytes_min=683, bytes_max=1183))).vl_plans[0]
    largest = assemble(_project(_vl("0x1", 8, bytes_min=1183))).vl_plans[0]

    # A range must be policed exactly as though every frame were the biggest one.
    assert ranged.lmax_bits == largest.lmax_bits
    assert ranged.lmax_bits > small.lmax_bits
    assert ranged.sigma_bits == largest.sigma_bits
    assert ranged.rho_bps == largest.rho_bps


def test_sporadic_row_with_range_far_above_bag():
    """Row 0x1: BAG 32ms, X (50, 100) -- sporadic and comfortably above the BAG."""
    context = assemble(_project(_vl("0x1", 32, bytes_min=28, gap_ms=(50, 100),
                                    dests=("es1", "es2"))))
    assert context.warnings == []
    assert "uniform(50ms, 100ms)" in _ini(_project(
        _vl("0x1", 32, bytes_min=28, gap_ms=(50, 100), dests=("es1", "es2"))))


def test_sporadic_row_whose_minimum_equals_the_bag():
    """Row 0x10: BAG 2ms, X (2, 5). The minimum sits exactly on the BAG, which is allowed."""
    context = assemble(_project(_vl("0x10", 2, bytes_min=1471, gap_ms=(2, 5))))
    assert context.warnings == []


def test_period_below_bag_is_warned_about():
    context = assemble(_project(_vl("0x1", 32, bytes_min=28, period_ms=8)))
    assert any("queue will grow" in w for w in context.warnings)


def test_payload_range_must_not_be_inverted():
    with pytest.raises(ValueError):
        _vl("0x1", 8, bytes_min=1183, bytes_max=683)


def test_whole_table4_subset_generates_without_warnings():
    """A representative slice of the real table must generate cleanly as written."""
    rows = [
        _vl("0x1", 32, bytes_min=28, gap_ms=(50, 100), dests=("es1", "es2")),
        _vl("0x5", 16, bytes_min=78, gap_ms=(60, 100), dests=("es1", "es2")),
        _vl("0x7", 64, bytes_min=453, gap_ms=(100, 150), dests=("es1", "es2")),
        _vl("0x9", 4, bytes_min=17),
        _vl("0x10", 2, bytes_min=1471, gap_ms=(2, 5)),
        _vl("0x14", 32, bytes_min=53, period_ms=40),
        _vl("0x18", 8, bytes_min=683, bytes_max=1183, period_ms=40, dests=("es1", "es2")),
        _vl("0x20", 1, bytes_min=1316, gap_ms=(1.6, 5)),
    ]
    context = assemble(_project(*rows))
    assert context.warnings == [], context.warnings
    assert len(context.vl_plans) == len(rows)
