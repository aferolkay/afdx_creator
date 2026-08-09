"""Sporadic (randomly-spaced) traffic sources.

The library re-reads `interArrivalTime` before scheduling each frame, and the parameter is
`volatile` in NED, so a random expression is redrawn every time. That is what makes a sporadic
source expressible purely from the ini, with no code change to the AFDX library.
"""

from __future__ import annotations

import pytest

from afdx_generator.codegen.context import assemble
from afdx_generator.codegen.render import render_all
from afdx_generator.models.project import Project
from afdx_generator.models.topology import TopologyEdge, TopologyNode
from afdx_generator.models.virtual_link import VirtualLink


def _project(**vl_kwargs) -> Project:
    return Project(
        id="p", name="arrivalTest",
        nodes=[
            TopologyNode(id="es0", kind="end_system", label="E0"),
            TopologyNode(id="es1", kind="end_system", label="E1"),
            TopologyNode(id="sw1", kind="switch", label="S1"),
        ],
        edges=[
            TopologyEdge(id="e1", node_a_id="es0", node_b_id="sw1"),
            TopologyEdge(id="e2", node_a_id="sw1", node_b_id="es1"),
        ],
        virtual_links=[VirtualLink(
            id="v1", hex_vl_id="0x1", label="V1", frame_bytes=256,
            source_node_id="es0", destination_node_ids=["es1"],
            bag_s=vl_kwargs.pop("bag_s", 0.002), **vl_kwargs)],
    )


def _ini(project) -> str:
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp:
        result = render_all(assemble(project), pathlib.Path(tmp))
        return result.ini_file.read_text()


def test_periodic_is_the_default_and_unchanged():
    """Existing projects must keep generating exactly what they did before."""
    vl = _project().virtual_links[0]
    assert vl.arrival_pattern == "periodic"
    assert "interArrivalTime = 2ms" in _ini(_project())


def test_sporadic_emits_a_random_expression():
    ini = _ini(_project(arrival_pattern="uniform",
                        arrival_min_s=0.002, arrival_max_s=0.006))
    assert "interArrivalTime = uniform(2ms, 6ms)" in ini
    # BAG itself stays a fixed value -- only the offered rate is random.
    assert "BAG = 2ms" in ini


def test_sporadic_bounds_default_to_bag_and_double_bag():
    """Defaults must be safe: mean 1.5 x BAG is comfortably above the regulator's release rate."""
    vl = _project(arrival_pattern="uniform").virtual_links[0]
    assert vl.effective_arrival_bounds() == (0.002, 0.004)
    assert vl.mean_interarrival_s == pytest.approx(0.003)
    assert "interArrivalTime = uniform(2ms, 4ms)" in _ini(_project(arrival_pattern="uniform"))


def test_mean_at_or_below_bag_is_warned_about():
    """This configuration aborts the run partway through; the user must hear about it first."""
    context = assemble(_project(arrival_pattern="uniform",
                                arrival_min_s=0.0005, arrival_max_s=0.0015))
    assert any("queue will grow" in w for w in context.warnings)


def test_dipping_below_bag_warns_about_latency_but_is_allowed():
    context = assemble(_project(arrival_pattern="uniform",
                                arrival_min_s=0.001, arrival_max_s=0.010))
    assert any("latency" in w for w in context.warnings)
    assert not any("queue will grow" in w for w in context.warnings)


def test_comfortably_above_bag_produces_no_warning():
    context = assemble(_project(arrival_pattern="uniform",
                                arrival_min_s=0.002, arrival_max_s=0.006))
    assert context.warnings == []


def test_max_below_min_is_rejected_by_the_model():
    with pytest.raises(ValueError):
        VirtualLink(id="v", hex_vl_id="0x1", frame_bytes=100, source_node_id="a",
                    destination_node_ids=["b"], bag_s=0.002,
                    arrival_pattern="uniform", arrival_min_s=0.006, arrival_max_s=0.002)


def test_generated_ini_documents_the_pattern():
    ini = _ini(_project(arrival_pattern="uniform",
                        arrival_min_s=0.002, arrival_max_s=0.006))
    assert "sporadic" in ini and "mean 4ms" in ini
