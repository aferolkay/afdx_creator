"""General simulation settings and machine-specific environment configuration.

Values here map onto the AFDX library's NED parameters. The *names* of those parameters live in
libraryprofile/profile.py -- this module only holds the values and their meaning.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeneralSettings(BaseModel):
    """Network-wide defaults, editable in the UI's settings panel."""

    # --- Token-bucket policing ------------------------------------------------------------
    # WARNING (empirical, not derived): the textbook AFDX arrival curve uses sigma = Lmax
    # exactly. That was measured to drop ~90% of frames from the second switch hop onward in a
    # 5-switch topology, because TrafficPolicy re-polices at EVERY hop and each hop's egress port
    # multiplexes several VLs, reshaping a VL away from perfectly-periodic spacing before the next
    # hop sees it. 4.0 was the smallest margin giving zero drops over a 5s run in THAT topology.
    # It is not a universal constant -- a denser or more heavily multiplexed network may need more.
    sigma_margin_factor: float = Field(default=4.0, gt=0)

    # Bytes AFDXMarshall adds on top of the application payload to form the wire frame.
    frame_header_length_bytes: int = Field(default=47, ge=0)

    # READ-ONLY in the UI. Hard-coded in the AFDX library's TrafficPolicy.cc as `20 * 8`; there is
    # no NED parameter exposing it, so it cannot be read at generation time. If that C++ constant
    # ever changes, this must be changed to match or every sigma/rho suggestion silently drifts.
    phy_overhead_bits: int = Field(default=160, ge=0)

    # --- Technological latencies ----------------------------------------------------------
    # WARNING (unverified): these were copied from an existing example project's convention. They
    # are NOT validated against any published AFDX delay model. When a generated network's
    # simulated end-to-end latency was compared against a paper's theoretical bounds, every VL
    # exceeded its bound by an amount not explained by hop count alone -- part real port-contention
    # queueing, part likely a mismatch in exactly these constants. Treat as a starting point.
    switch_fabric_delay_s: float = Field(default=50e-6, ge=0)
    latency_tech_tx_delay_s: float = Field(default=50e-6, ge=0)
    latency_tech_rx_delay_s: float = Field(default=50e-6, ge=0)

    # --- Queueing / scheduling ------------------------------------------------------------
    regulator_max_vlid_queue_size: int = Field(default=1000, gt=0)
    scheduler_service_time_s: float = Field(default=0.0, ge=0)

    # --- Redundancy -----------------------------------------------------------------------
    skew_max_s: float = Field(default=10e-3, ge=0)
    skew_max_test_enabled: bool = False
    redundancy_copy_to_link_a: bool = True
    redundancy_copy_to_link_b: bool = True

    # --- Physical defaults ----------------------------------------------------------------
    channel_datarate_bps: float = Field(default=100e6, gt=0)
    channel_length_m: float = Field(default=10.0, gt=0)

    # --- AFDX marshalling (cosmetic; only virtualLinkId affects routing/timing) ------------
    network_id: int = 0x99
    interface_id: int = 0
    udp_src_port: int = 0x1234
    udp_dest_port: int = 0x5678
    # A constant 0 for every frame is what the existing validated networks use, and it works:
    # RedundancyChecker only drops a frame when the seq number repeats *within* skewMax, which is
    # exactly the redundant-copy case. Changing this is not required and is not well understood --
    # leave it alone unless you have investigated RedundancyChecker.cc.
    seq_num_default: int = 0

    # --- Output ---------------------------------------------------------------------------
    # VLRouter opens its table file relative to the simulation process's working directory. The
    # generator writes bare filenames ("S1.txt") and the validation runner sets cwd to the output
    # directory, so they resolve. If you copy the generated folder into an OMNeT++ project and run
    # it from a different working directory, set this prefix accordingly
    # (e.g. "networks/MyNetwork/").
    route_table_path_prefix: str = ""

    # Simulated seconds the validation run should cover.
    validation_sim_time_limit_s: float = Field(default=1.0, gt=0)


class EnvironmentConfig(BaseModel):
    """Machine-specific paths needed to actually run the compiled simulator.

    Deliberately stored OUTSIDE the project file so a project stays portable between machines.
    """

    omnetpp_lib_dir: str = ""
    afdx_src_dir: str = ""
    queueinglib_dir: str = ""
    # The target OMNeT++ project's own src/ dir (for its package.ned).
    project_src_dir: str = ""
    binary_path: str = ""
    extra_ned_paths: list[str] = Field(default_factory=list)
    extra_ld_library_paths: list[str] = Field(default_factory=list)

    def is_configured(self) -> bool:
        return bool(self.binary_path)
