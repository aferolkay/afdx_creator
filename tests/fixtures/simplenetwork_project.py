"""The hand-built, simulator-validated reference network, expressed as an afdx_generator Project.

This is the golden fixture. The network it describes was built by hand, run through the real
OMNeT++ binary, and confirmed to produce zero policer drops and zero routing errors. If the
generator can reproduce its routing tables and traffic parameters, the pipeline is correct.

Source: 7 end systems (E0-E6), 5 switches (S1-S5), 11 virtual links, from a published example
network configuration figure and its accompanying message-set table.
"""

from __future__ import annotations

from afdx_generator.models.project import Project
from afdx_generator.models.settings import GeneralSettings
from afdx_generator.models.topology import TopologyEdge, TopologyNode
from afdx_generator.models.virtual_link import VirtualLink

# --- Topology -----------------------------------------------------------------------------
# E0, E1 -> S1;  E4, E5 -> S3;  S3 -> S1 -> S2;  S2 -> E3 and S2 -> S4;  S4 -> E2 and S4 -> S5;
# S5 -> E6.
_NODES = [
    ("es0", "end_system", "E0"),
    ("es1", "end_system", "E1"),
    ("es2", "end_system", "E2"),
    ("es3", "end_system", "E3"),
    ("es4", "end_system", "E4"),
    ("es5", "end_system", "E5"),
    ("es6", "end_system", "E6"),
    ("sw1", "switch", "S1"),
    ("sw2", "switch", "S2"),
    ("sw3", "switch", "S3"),
    ("sw4", "switch", "S4"),
    ("sw5", "switch", "S5"),
]

# Edge ids are chosen so that the natural-sort port ordering reproduces the hand-built port
# numbering exactly (S1: E0,E1,S2,S3 / S2: S1,S4,E3 / S3: S1,E4,E5 / S4: S2,S5,E2 / S5: S4,E6).
_EDGES = [
    ("e01", "es0", "sw1"),   # S1 port 0
    ("e02", "es1", "sw1"),   # S1 port 1
    ("e03", "sw1", "sw2"),   # S1 port 2 / S2 port 0
    ("e04", "sw1", "sw3"),   # S1 port 3 / S3 port 0
    ("e05", "sw2", "sw4"),   # S2 port 1 / S4 port 0
    ("e06", "sw2", "es3"),   # S2 port 2
    ("e07", "sw3", "es4"),   # S3 port 1
    ("e08", "sw3", "es5"),   # S3 port 2
    ("e09", "sw4", "sw5"),   # S4 port 1 / S5 port 0
    ("e10", "sw4", "es2"),   # S4 port 2
    ("e11", "sw5", "es6"),   # S5 port 1
]

# --- Virtual links (VL, payload bytes, source, destination, BAG ms, offset us) -------------
_VLS = [
    ("0x1", "V1", 1183, "es0", "es3", 1.0, 0.0),
    ("0x2", "V2", 572, "es0", "es2", 2.0, 1524.44),
    ("0x5", "V5", 375, "es1", "es0", 1.0, 0.0),
    ("0x6", "V6", 842, "es5", "es3", 1.0, 0.0),
    ("0x7", "V7", 750, "es5", "es2", 1.0, 503.68),
    ("0x8", "V8", 1042, "es4", "es2", 2.0, 482.84),
    ("0x9", "V9", 618, "es4", "es2", 1.0, 0.0),
    ("0xB", "V11", 240, "es2", "es3", 4.0, 0.0),
    ("0xC", "V12", 600, "es0", "es2", 2.0, 523.32),
    ("0xD", "V13", 618, "es4", "es2", 2.0, 1500.0),
    ("0xE", "V14", 240, "es6", "es1", 2.0, 0.0),
]


def build_simplenetwork_project() -> Project:
    return Project(
        id="simplenetwork",
        name="simpleNetwork",
        nodes=[TopologyNode(id=i, kind=k, label=l) for i, k, l in _NODES],
        edges=[TopologyEdge(id=i, node_a_id=a, node_b_id=b, length_m=10.0) for i, a, b in _EDGES],
        virtual_links=[
            VirtualLink(
                id=f"vl_{hex_id}",
                hex_vl_id=hex_id,
                label=label,
                frame_bytes=payload,
                source_node_id=src,
                destination_node_ids=[dst],
                bag_s=bag_ms / 1000.0,
                offset_s=offset_us / 1e6,
                partition_id=int(hex_id, 16),
            )
            for hex_id, label, payload, src, dst, bag_ms, offset_us in _VLS
        ],
        general_settings=GeneralSettings(),
    )


# The route tables from the hand-built, simulator-validated network.
# switch label -> {VL route key: (ports,)}
EXPECTED_ROUTE_TABLES = {
    "S1": {
        "0x1": (2,), "0x2": (2,), "0x5": (0,), "0x6": (2,), "0x7": (2,),
        "0x8": (2,), "0x9": (2,), "0xC": (2,), "0xD": (2,), "0xE": (1,),
    },
    "S2": {
        "0x1": (2,), "0x2": (1,), "0x6": (2,), "0x7": (1,), "0x8": (1,),
        "0x9": (1,), "0xB": (2,), "0xC": (1,), "0xD": (1,), "0xE": (0,),
    },
    "S3": {
        "0x6": (0,), "0x7": (0,), "0x8": (0,), "0x9": (0,), "0xD": (0,),
    },
    "S4": {
        "0x2": (2,), "0x7": (2,), "0x8": (2,), "0x9": (2,), "0xB": (0,),
        "0xC": (2,), "0xD": (2,), "0xE": (0,),
    },
    "S5": {
        "0xE": (0,),
    },
}

EXPECTED_PORT_COUNTS = {"S1": 4, "S2": 3, "S3": 3, "S4": 3, "S5": 2}

# End system label -> number of VLs it sources (drives messageCount).
EXPECTED_MESSAGE_COUNTS = {
    "E0": 3, "E1": 1, "E2": 1, "E3": 0, "E4": 3, "E5": 2, "E6": 1,
}
