"""Render the assembled context to files. The only filesystem I/O in the codegen pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path as FsPath

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .context import RenderContext

_TEMPLATE_DIR = FsPath(__file__).parent / "templates"


@dataclass
class GeneratedFiles:
    directory: FsPath
    ned_file: FsPath
    ini_file: FsPath
    route_table_files: list[FsPath]
    warnings: list[str]

    @property
    def all_files(self) -> list[FsPath]:
        return [self.ned_file, self.ini_file, *self.route_table_files]


def _format_time(seconds: float) -> str:
    """Render a duration with a unit OMNeT++ accepts, preferring a readable magnitude.

    Exact values matter here: writing 0.0005s as "500us" must not introduce rounding, so the
    chosen unit is checked to round-trip before it is used.
    """
    if seconds == 0:
        return "0s"
    for factor, unit in ((1.0, "s"), (1e-3, "ms"), (1e-6, "us"), (1e-9, "ns")):
        scaled = seconds / factor
        if scaled >= 1.0:
            text = f"{scaled:.10g}"
            if abs(float(text) * factor - seconds) <= abs(seconds) * 1e-12:
                return f"{text}{unit}"
    return f"{seconds:.12g}s"


def _format_rate(bps: float) -> str:
    if bps >= 1e6:
        value = bps / 1e6
        text = f"{value:.10g}"
        if abs(float(text) * 1e6 - bps) <= abs(bps) * 1e-12:
            return f"{text}Mbps"
    if bps >= 1e3:
        value = bps / 1e3
        text = f"{value:.10g}"
        if abs(float(text) * 1e3 - bps) <= abs(bps) * 1e-12:
            return f"{text}kbps"
    return f"{bps:.10g}bps"


def _format_number(value: float) -> str:
    """Whole numbers without a trailing '.0' -- sigma is a bit count and reads better as an int."""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.10g}"


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(_TEMPLATE_DIR),
        undefined=StrictUndefined,  # a typo in a template should fail loudly, not render blank
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def render_all(context: RenderContext, output_dir: FsPath) -> GeneratedFiles:
    env = _environment()
    profile = context.profile
    project = context.project
    settings = project.general_settings
    wiring = context.wiring

    output_dir = FsPath(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    network_name = project.ned_network_name
    # No package declaration: the generated folder is standalone, so the .ned sits in the default
    # package and the ini refers to the network by bare name. This sidesteps the requirement that
    # every path segment be a valid NED identifier for a directory we do not control.
    ned_package = ""

    def route_table_path(switch_node_id: str) -> str:
        return f"{settings.route_table_path_prefix}{context.route_table_files[switch_node_id]}"

    # --- network.ned ---
    ned_text = env.get_template("network.ned.j2").render(
        project=project,
        profile=profile,
        wiring=wiring,
        network_name=network_name,
        ned_package=ned_package,
    )
    ned_file = output_dir / f"{network_name}.ned"
    ned_file.write_text(ned_text, encoding="utf-8")

    # --- omnetpp.ini ---
    switch_pairs = list(zip(wiring.switches_a, wiring.switches_b))
    ini_text = env.get_template("omnetpp.ini.j2").render(
        project=project,
        profile=profile,
        wiring=wiring,
        s=settings,
        net=network_name,
        network_fqn=network_name,
        config_name=project.ini_config_name,
        switch_pairs=switch_pairs,
        vl_plans=context.vl_plans,
        route_table_path=route_table_path,
        fmt_time=_format_time,
        fmt_rate=_format_rate,
        fmt_number=_format_number,
    )
    ini_file = output_dir / f"{network_name}.ini"
    ini_file.write_text(ini_text, encoding="utf-8")

    # --- one route table per switch ---
    fmt = profile.route_table
    label_by_key = {plan.route_key: plan.label for plan in context.vl_plans}
    route_files: list[FsPath] = []
    template = env.get_template("route_table.txt.j2")

    for switch in sorted(context.graph.switches(), key=lambda n: n.id):
        table = context.route_tables[switch.id]

        port_map = []
        for port, edge_id in enumerate(context.port_order[switch.id]):
            peer_id = context.graph.edge(edge_id).other_end(switch.id)
            peer = context.graph.node(peer_id)
            port_map.append((port, peer.label or peer.id))

        entries = [
            {
                "key": key,
                "ports": list(ports),
                "label": label_by_key.get(key, key),
            }
            for key, ports in table.entries.items()
        ]

        text = template.render(
            c=fmt.comment_prefix,
            sep=fmt.key_value_separator,
            open_brace=fmt.ports_open,
            close_brace=fmt.ports_close,
            port_sep=fmt.port_separator,
            switch_label=switch.label or switch.id,
            port_map=port_map,
            entries=entries,
        )
        path = output_dir / context.route_table_files[switch.id]
        path.write_text(text, encoding="utf-8")
        route_files.append(path)

    return GeneratedFiles(
        directory=output_dir,
        ned_file=ned_file,
        ini_file=ini_file,
        route_table_files=route_files,
        warnings=list(context.warnings),
    )
