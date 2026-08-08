"""Virtual link: one periodic traffic stream from one end system to one or more others."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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
