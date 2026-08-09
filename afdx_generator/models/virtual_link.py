"""Virtual link: one periodic traffic stream from one end system to one or more others."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# How the source spaces successive frames.
#
#   periodic - one frame exactly every BAG. The classic AFDX assumption.
#   uniform  - the gap is drawn uniformly at random from [min, max] for every frame, which is
#              what the literature calls a *sporadic* source.
#
# This works because the library's Source_ext re-reads `interArrivalTime` before scheduling each
# frame, and the parameter is declared `volatile` in NED -- so a random expression is redrawn every
# time rather than fixed at startup.
#
# Note: the library also declares `deltaInterArrivalTimeMaxLimit`, which looks like it is for this.
# It is not implemented -- no C++ file reads it -- so setting it does nothing. Do not use it.
ArrivalPattern = Literal["periodic", "uniform"]


class VirtualLink(BaseModel):
    id: str
    # Canonical VL identity. Stored as a string so "0x1" round-trips exactly as the user typed it;
    # `numeric_id` is the value actually written into NED/route tables.
    hex_vl_id: str
    label: str = ""

    # Application payload length -> Source_ext.packetLength. The wire frame is this plus
    # frame_header_length (see trafficmath.rho_sigma.wire_frame_bits).
    frame_bytes: int = Field(gt=0)

    source_node_id: str
    # Multicast from day one: AFDX VLs are natively one-to-many, and the library's route-table
    # parser genuinely supports multiple ports per VL (`0x1 : {2,3}`).
    destination_node_ids: list[str] = Field(min_length=1)

    # One field feeding BOTH AFDXMarshall.BAG and Source_ext.interArrivalTime. They are the same
    # physical quantity on two modules; keeping them as one field means they cannot disagree.
    bag_s: float = Field(gt=0)

    # Source_ext.startTime. None -> omit, letting the library default it to interArrivalTime.
    offset_s: float | None = Field(default=None, ge=0)

    # How the source spaces frames. "periodic" reproduces the previous behaviour exactly.
    arrival_pattern: ArrivalPattern = "periodic"
    # Bounds for the "uniform" pattern. None -> derived from BAG (see effective_arrival_bounds).
    arrival_min_s: float | None = Field(default=None, gt=0)
    arrival_max_s: float | None = Field(default=None, gt=0)

    def effective_arrival_bounds(self) -> tuple[float, float]:
        """The [min, max] actually used for a uniform source.

        Defaults are chosen to be safe rather than merely plausible: min = BAG (never faster than
        the link is allowed to emit) and max = 2 x BAG, giving a mean of 1.5 x BAG, comfortably
        under the rate at which the BAG regulator's queue would grow without bound.
        """
        low = self.arrival_min_s if self.arrival_min_s is not None else self.bag_s
        high = self.arrival_max_s if self.arrival_max_s is not None else self.bag_s * 2
        return low, high

    @property
    def mean_interarrival_s(self) -> float:
        if self.arrival_pattern == "uniform":
            low, high = self.effective_arrival_bounds()
            return (low + high) / 2
        return self.bag_s

    # Token-bucket policing. None -> auto-suggested by trafficmath.rho_sigma at generation time.
    rho_bps: float | None = Field(default=None, gt=0)
    sigma_bits: float | None = Field(default=None, gt=0)
    sigma_margin_factor_override: float | None = Field(default=None, gt=0)

    # None -> shortest path (BFS). Otherwise an explicit ordered list of edge ids, which the
    # designer may prefer when the shortest hop-count path is not the lowest-latency one.
    explicit_path_edge_ids: list[str] | None = None

    partition_id: int | None = None
    frame_header_length_override: int | None = Field(default=None, ge=0)

    @field_validator("hex_vl_id")
    @classmethod
    def _validate_hex(cls, v: str) -> str:
        raw = v.strip()
        if not raw:
            raise ValueError("hex_vl_id must not be empty")
        try:
            value = int(raw, 16)
        except ValueError as exc:
            raise ValueError(f"hex_vl_id {v!r} is not valid hexadecimal") from exc
        if value <= 0:
            # 0 is reserved/meaningless as a VL id, and the library keys maps on it.
            raise ValueError("hex_vl_id must be greater than zero")
        if value > 0xFFFF:
            # AFDX carries the VL id in the low 16 bits of the destination MAC address.
            raise ValueError(f"hex_vl_id {v!r} exceeds the 16-bit AFDX virtual-link id range")
        return raw

    @property
    def numeric_id(self) -> int:
        return int(self.hex_vl_id, 16)

    @property
    def route_table_key(self) -> str:
        """The exact token written as the key in a switch route-table file."""
        return f"0x{self.numeric_id:X}"

    @field_validator("arrival_max_s")
    @classmethod
    def _max_above_min(cls, v, info):
        low = info.data.get("arrival_min_s")
        if v is not None and low is not None and v < low:
            raise ValueError("arrival max must not be smaller than arrival min")
        return v
