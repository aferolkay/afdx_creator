"""EVERY name this generator borrows from the AFDX OMNeT++ library lives in this file.

>>> If the afdx library renames something, THIS is the file you edit. <<<

Nothing outside `codegen/` reads this module, and nothing upstream of `codegen/context.py` knows
any AFDX-specific name at all. The topology model, routing, and traffic math are written purely in
terms of "nodes", "links" and "virtual links".

Read `README.md` in this directory before editing -- there is an important limit to what this file
can absorb (renames: yes; structural changes: no).

Verified against the library source at AFDX-master/afdx/src on 2026-08-09.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class NedTypes:
    """Fully-qualified NED type names, as written in `import` and submodule declarations."""

    package: str = "afdx"
    end_system: str = "afdx.EndSystem"
    switch: str = "afdx.Switch"
    cable: str = "afdx.Cable"


@dataclass(frozen=True)
class Gates:
    """Gate names on the library's modules."""

    # EndSystem has two independent ethernet interfaces, one per redundant plane.
    end_system_port_a: str = "ethPortA"
    end_system_port_b: str = "ethPortB"
    # Switch exposes a gate vector sized by its noOfPorts parameter.
    switch_port_vector: str = "ethPort"


@dataclass(frozen=True)
class ModuleParams:
    """Parameter names set directly on a module instance."""

    switch_port_count: str = "noOfPorts"
    end_system_message_count: str = "messageCount"


@dataclass(frozen=True)
class SubmodulePaths:
    """Relative paths to submodules whose parameters we set from the ini."""

    # Switch -> switchFabric -> router (a VLRouter), which reads the per-switch VL table file.
    switch_router_config_table: str = "switchFabric.router.configTableName"

    # Submodule vectors inside EndSystem, both sized by messageCount. Index i of one corresponds
    # to index i of the other (one traffic source feeding one marshaller).
    message_source_vector: str = "messageSource"
    marshall_vector: str = "afdxMarshall"


@dataclass(frozen=True)
class SourceParams:
    """Parameters of Source_ext -- the application-level traffic generator."""

    packet_length: str = "packetLength"
    inter_arrival_time: str = "interArrivalTime"
    start_time: str = "startTime"
    partition_id: str = "partitionId"
    baudrate: str = "baudrate"
    cable_length: str = "cableLength"


@dataclass(frozen=True)
class MarshallParams:
    """Parameters of AFDXMarshall -- builds the AFDX frame and carries the policing parameters."""

    virtual_link_id: str = "virtualLinkId"
    bag: str = "BAG"
    rho: str = "rho"
    sigma: str = "sigma"
    network_id: str = "networkId"
    equipment_id: str = "equipmentId"
    interface_id: str = "interfaceId"
    seq_num: str = "seqNum"
    udp_src_port: str = "udpSrcPort"
    udp_dest_port: str = "udpDestPort"
    frame_header_length: str = "frameHeaderLength"


@dataclass(frozen=True)
class WildcardParams:
    """Network-wide settings, addressed with `**.` wildcard patterns in the ini."""

    redundancy_checker_skew_max: str = "**.redundancyChecker.skewMax"
    regulator_max_queue: str = "**.regulatorLogic.maxVLIDQueueSize"
    scheduler_service_time: str = "**.scheduler.serviceTime"
    switch_fabric_delay: str = "**.switchFabric.delay.delay"
    latency_tech_tx: str = "**.ES[*].latencyTechTx.delay"
    latency_tech_rx: str = "**.ES[*].latencyTechRx.delay"
    skew_max_test_enabled: str = "**.skewMaxTester.skewMaxTestEnabled"
    channel_datarate: str = "**.channel.datarate"
    channel_length: str = "**.channel.length"
    redundancy_copy_a: str = "**.redundancyController.copyToLinkA"
    redundancy_copy_b: str = "**.redundancyController.copyToLinkB"


@dataclass(frozen=True)
class RouteTableFormat:
    """The switch VL-table text format, as parsed by the library's hand-written C++ (VLRouter.cc).

    Verified behaviour of that parser -- these are constraints, not style choices:

    * A comment line must begin with '*' **at column 0**. There is no inline comment support:
      the parser only skips a line whose *first character* is '*'.
    * Blank lines are skipped.
    * Any other line must contain ':' then '{' then '}', else it throws "Invalid VL Table!".
    * The key is parsed with base-16 `stoi`, so "0x1" and "1" are both accepted.
    * Ports are comma-separated inside the braces; MULTIPLE PORTS WORK, which is what makes
      multicast possible (`0x1 : {2,3}` duplicates the frame out both ports).

    * NO TRAILING COMMENTS. This one is a trap, verified by re-implementing the parser:
      text after '}' *usually* parses fine, so `0x1 : {2}   * some note` works -- but the
      port-scanning loop searches for the next ',' without stopping at '}', so a comma anywhere
      after the braces makes it run past the end and throw "Invalid VL Table!". Compare:

          0xB : {0,1,2} * three-way multicast      -> parses (no comma in the comment)
          0xE : {0,1}   * multicast, two ports     -> THROWS (comma in the comment)

      Since a user-supplied VL label can contain a comma, trailing comments are never emitted.
      All commentary goes in the leading '*' block instead, which is unconditionally safe.
    """

    comment_prefix: str = "*"
    key_value_separator: str = " : "
    ports_open: str = "{"
    ports_close: str = "}"
    port_separator: str = ","
    file_suffix: str = ".txt"


@dataclass(frozen=True)
class LibraryProfile:
    ned: NedTypes = field(default_factory=NedTypes)
    gates: Gates = field(default_factory=Gates)
    module_params: ModuleParams = field(default_factory=ModuleParams)
    submodules: SubmodulePaths = field(default_factory=SubmodulePaths)
    source: SourceParams = field(default_factory=SourceParams)
    marshall: MarshallParams = field(default_factory=MarshallParams)
    wildcards: WildcardParams = field(default_factory=WildcardParams)
    route_table: RouteTableFormat = field(default_factory=RouteTableFormat)

    # --- Structural naming chosen by THIS generator, not by the library ---------------------
    # The library does not dictate these; they are the names our templates emit. Changing them is
    # safe as long as the .ned and .ini agree, which they do because both read these fields.
    end_system_vector_name: str = "ES"
    switch_plane_a_vector_name: str = "SwitchA"
    switch_plane_b_vector_name: str = "SwitchB"

    # --- Hard-coded in the library's C++, unreadable at generation time --------------------
    # TrafficPolicy.cc: `const int phyOverhead_bit = 20 * 8;`
    # There is no NED parameter for this. It is duplicated in GeneralSettings.phy_overhead_bits
    # (so it is visible and adjustable in the UI); if the C++ changes, change it there.
    phy_overhead_bits_reference: int = 160


DEFAULT_PROFILE = LibraryProfile()
