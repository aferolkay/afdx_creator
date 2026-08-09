"""Assemble everything the templates need. This is the seam where domain data meets library names.

Upstream of this module nothing knows what "afdxMarshall" is. Downstream (templates) nothing knows
what a "shortest path" is. Keeping that boundary sharp is what makes a library rename a one-file
change.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.graph import Graph, GraphError, validate_topology, validate_virtual_links
from ..models.project import Project
from ..routing.pathfinder import Path, resolve_paths
from ..routing.port_table import (
    PortOrder,
    SwitchRouteTable,
    build_switch_route_tables,
    canonical_port_order,
)
from ..trafficmath.rho_sigma import suggest
from ..libraryprofile.profile import DEFAULT_PROFILE, LibraryProfile


class GenerationError(ValueError):
    """Generation cannot proceed. `problems` holds the user-facing reasons."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass
class VLPlan:
    """One VL, fully resolved: routing done, traffic parameters settled, index assigned."""

    vl_id: str
    route_key: str            # "0x1"
    numeric_id: int
    label: str
    source_ref: str           # "ES[0]"
    source_label: str
    stream_index: int         # index into messageSource[] / afdxMarshall[] on that end system
    destination_labels: list[str]
    payload_bytes: int
    bag_s: float
    offset_s: float | None
    rho_bps: float
    sigma_bits: float
    lmax_bits: int
    partition_id: int
    frame_header_bytes: int
    rho_was_auto: bool
    sigma_was_auto: bool
    arrival_pattern: str = "periodic"
    # Right-hand sides written for Source_ext. Either fixed values or random expressions the
    # simulator redraws for every frame.
    arrival_expression: str = ""
    arrival_description: str = ""
    packet_length_expression: str = ""
    frame_size_description: str = ""
    paths: list[Path] = field(default_factory=list)

    @property
    def path_description(self) -> str:
        return " | ".join("->".join(p.node_ids) for p in self.paths)


@dataclass
class RenderContext:
    project: Project
    profile: LibraryProfile
    graph: Graph
    port_order: PortOrder
    wiring: object
    vl_plans: list[VLPlan]
    route_tables: dict[str, SwitchRouteTable]
    # switch node id -> the route-table filename generated for it
    route_table_files: dict[str, str]
    warnings: list[str] = field(default_factory=list)


def assemble(project: Project, profile: LibraryProfile = DEFAULT_PROFILE) -> RenderContext:
    from .wiring import build_wiring  # local import: wiring imports nothing from here

    graph = Graph.build(project.nodes, project.edges)

    problems = validate_topology(graph)
    problems += validate_virtual_links(graph, project.virtual_links)
    if problems:
        raise GenerationError(problems)

    port_order = canonical_port_order(graph)
    settings = project.general_settings

    # --- Resolve routing for every VL --------------------------------------------------------
    resolved: dict[str, list[Path]] = {}
    routing_problems: list[str] = []
    for vl in project.virtual_links:
        try:
            resolved[vl.route_table_key] = resolve_paths(graph, vl)
        except GraphError as exc:
            routing_problems.append(f"VL {vl.label or vl.hex_vl_id}: {exc}")
    if routing_problems:
        raise GenerationError(routing_problems)

    route_tables = build_switch_route_tables(graph, port_order, resolved)

    # --- Assign each VL its slot in its source end system's submodule vectors ----------------
    # The library only says these vectors are sized by messageCount; the ORDER is our convention.
    # Defined here, once, so the .ned instantiation and the .ini parameters cannot disagree.
    by_source: dict[str, list] = {}
    for vl in project.virtual_links:
        by_source.setdefault(vl.source_node_id, []).append(vl)
    for vls in by_source.values():
        vls.sort(key=lambda v: v.numeric_id)

    stream_index: dict[str, int] = {}
    for vls in by_source.values():
        for index, vl in enumerate(vls):
            stream_index[vl.id] = index

    vl_count_by_source = {node_id: len(vls) for node_id, vls in by_source.items()}
    wiring = build_wiring(graph, port_order, profile, vl_count_by_source)

    # --- Traffic parameters -------------------------------------------------------------------
    warnings: list[str] = []
    vl_plans: list[VLPlan] = []
    for vl in project.virtual_links:
        header = (
            vl.frame_header_length_override
            if vl.frame_header_length_override is not None
            else settings.frame_header_length_bytes
        )
        margin = vl.sigma_margin_factor_override or settings.sigma_margin_factor
        # Sized from the LARGEST frame the link can emit. The policer checks each frame as it
        # arrives, so a bucket sized for a typical frame silently discards the big ones.
        auto = suggest(
            payload_bytes=vl.max_frame_bytes,
            bag_s=vl.bag_s,
            frame_header_bytes=header,
            phy_overhead_bits=settings.phy_overhead_bits,
            margin_factor=margin,
        )

        rho = vl.rho_bps if vl.rho_bps is not None else auto.rho_bps
        sigma = vl.sigma_bits if vl.sigma_bits is not None else auto.sigma_bits

        if vl.sigma_bits is not None and vl.sigma_bits < auto.lmax_bits:
            warnings.append(
                f"VL {vl.label or vl.hex_vl_id}: sigma ({vl.sigma_bits:.0f} bits) is smaller than "
                f"one frame ({auto.lmax_bits} bits), so every frame will be dropped by the policer."
            )
        if vl.rho_bps is not None and vl.rho_bps < auto.rho_bps:
            warnings.append(
                f"VL {vl.label or vl.hex_vl_id}: rho ({vl.rho_bps/1e6:.3f} Mbps) is below the VL's "
                f"own sustained rate ({auto.rho_bps/1e6:.3f} Mbps); the policer will drop frames."
            )

        # --- arrival pattern -----------------------------------------------------------------
        # Sporadic sources rely on the library re-reading a `volatile` NED parameter before every
        # frame, so a random expression is redrawn each time rather than fixed at startup.
        from .render import format_time  # local import: render imports this module

        name = vl.label or vl.hex_vl_id
        if vl.arrival_pattern == "uniform":
            low, high = vl.effective_arrival_bounds()
            arrival_expression = f"uniform({format_time(low)}, {format_time(high)})"
            arrival_description = (
                f"sporadic, gap drawn uniformly from {format_time(low)}..{format_time(high)} "
                f"(mean {format_time((low + high) / 2)})"
            )

            if high < low:
                raise GenerationError(
                    [f"VL {name}: arrival max ({format_time(high)}) is below arrival min "
                     f"({format_time(low)})."]
                )
            # The BAG regulator releases at most one frame per BAG. If the source *averages*
            # faster than that, its queue grows without bound and the run aborts partway through
            # with "Max limit for VLID queue is reached" -- confirmed by running it.
            mean = (low + high) / 2
            if mean <= vl.bag_s:
                warnings.append(
                    f"VL {name}: mean arrival gap ({format_time(mean)}) is not above BAG "
                    f"({format_time(vl.bag_s)}), so frames are generated faster than the BAG "
                    f"regulator can release them. Its queue will grow until the simulation "
                    f"aborts. Raise the arrival bounds."
                )
            elif low < vl.bag_s:
                # Legal and often intended, but it is where latency tails come from.
                warnings.append(
                    f"VL {name}: arrival min ({format_time(low)}) is below BAG "
                    f"({format_time(vl.bag_s)}). Bursts will be held back by the BAG regulator, "
                    f"so expect end-to-end latency well above the periodic case."
                )
        else:
            period = vl.effective_period_s
            arrival_expression = format_time(period)
            arrival_description = (
                "periodic, one frame every BAG"
                if vl.period_s is None or period == vl.bag_s
                else f"periodic every {format_time(period)} (slower than its {format_time(vl.bag_s)} BAG)"
            )
            if period < vl.bag_s:
                warnings.append(
                    f"VL {name}: period ({format_time(period)}) is shorter than BAG "
                    f"({format_time(vl.bag_s)}), so frames are offered faster than the regulator "
                    f"can release them. Its queue will grow until the simulation aborts."
                )

        # --- frame size ------------------------------------------------------------------------
        if vl.has_variable_frame_size:
            # intuniform is inclusive at both ends, matching a payload range like (683, 1183).
            packet_length_expression = f"intuniform({vl.frame_bytes}, {vl.frame_bytes_max})"
            frame_size_description = (
                f"payload varies uniformly over {vl.frame_bytes}..{vl.frame_bytes_max} bytes; "
                f"rho/sigma sized for the largest"
            )
        else:
            packet_length_expression = str(vl.frame_bytes)
            frame_size_description = f"{vl.frame_bytes} byte payload"

        source_node = graph.node(vl.source_node_id)
        vl_plans.append(
            VLPlan(
                vl_id=vl.id,
                route_key=vl.route_table_key,
                numeric_id=vl.numeric_id,
                label=vl.label or vl.hex_vl_id,
                source_ref=(
                    f"{profile.end_system_vector_name}"
                    f"[{wiring.end_system_index[vl.source_node_id]}]"
                ),
                source_label=source_node.label or source_node.id,
                stream_index=stream_index[vl.id],
                destination_labels=[
                    (graph.node(d).label or d) for d in vl.destination_node_ids
                ],
                payload_bytes=vl.frame_bytes,
                bag_s=vl.bag_s,
                offset_s=vl.offset_s,
                arrival_pattern=vl.arrival_pattern,
                arrival_expression=arrival_expression,
                arrival_description=arrival_description,
                packet_length_expression=packet_length_expression,
                frame_size_description=frame_size_description,
                rho_bps=rho,
                sigma_bits=sigma,
                lmax_bits=auto.lmax_bits,
                partition_id=vl.partition_id if vl.partition_id is not None else vl.numeric_id,
                frame_header_bytes=header,
                rho_was_auto=vl.rho_bps is None,
                sigma_was_auto=vl.sigma_bits is None,
                paths=resolved[vl.route_table_key],
            )
        )

    vl_plans.sort(key=lambda p: (p.source_ref, p.stream_index))

    route_table_files = {
        sw.id: f"{_route_table_stem(graph, sw.id)}{profile.route_table.file_suffix}"
        for sw in graph.switches()
    }

    return RenderContext(
        project=project,
        profile=profile,
        graph=graph,
        port_order=port_order,
        wiring=wiring,
        vl_plans=vl_plans,
        route_tables=route_tables,
        route_table_files=route_table_files,
        warnings=warnings,
    )


def _route_table_stem(graph: Graph, switch_id: str) -> str:
    from ..domain.naming import sanitize_path_segment

    node = graph.node(switch_id)
    return sanitize_path_segment(node.label or node.id, fallback=switch_id)
