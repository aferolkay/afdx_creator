"""Token-bucket (rho, sigma) sizing for the AFDX traffic policer.

Background, because the naive formula is a trap
----------------------------------------------
Each switch port polices every VL against a token bucket. The textbook AFDX arrival curve is

    rho   = Lmax / BAG        (sustained rate)
    sigma = Lmax              (burst allowance: exactly one maximum-size frame)

`sigma = Lmax` is the theoretically tight value for a *perfectly periodic* source, and it fails in
practice. Measured on a real 5-switch network: ~90% of frames were dropped from the second hop
onward, reported as `TOKEN_INSUFFICIENT` in the simulator output.

The reason is that the policer runs at EVERY hop, not just at ingress. Between hops, a VL's frames
share an egress port with other VLs; that multiplexing delays some frames relative to others, so by
the time a VL reaches the next policer its spacing is no longer exactly periodic. With a burst
allowance of precisely one frame there is zero slack to absorb that, and the bucket underruns.

So the burst allowance is scaled by a margin factor. 4.0 was the smallest value giving zero drops
over a 5-second run on the topology it was measured on. It is NOT a universal constant -- it is a
property of how heavily that particular network multiplexes VLs onto shared links. A denser network
may need more. The validation run is what tells you.
"""

from __future__ import annotations

from dataclasses import dataclass


def wire_frame_bits(payload_bytes: int, frame_header_bytes: int, phy_overhead_bits: int) -> int:
    """Lmax: the full on-the-wire size of one frame, in bits.

    Mirrors what the library's TrafficPolicy actually measures a frame against:
    the AFDX frame (payload + header) plus a fixed physical-layer overhead.
    """
    return (payload_bytes + frame_header_bytes) * 8 + phy_overhead_bits


@dataclass(frozen=True)
class TokenBucket:
    rho_bps: float
    sigma_bits: float
    lmax_bits: int


def suggest(
    payload_bytes: int,
    bag_s: float,
    frame_header_bytes: int,
    phy_overhead_bits: int,
    margin_factor: float,
) -> TokenBucket:
    """Suggested (rho, sigma) for one VL.

    rho is the true sustained rate and is not padded -- inflating it would let a genuinely
    misbehaving source through the policer unnoticed, which defeats the point of policing.
    Only the burst allowance (sigma) carries the margin.
    """
    if bag_s <= 0:
        raise ValueError("BAG must be greater than zero")
    if margin_factor <= 0:
        raise ValueError("sigma margin factor must be greater than zero")

    lmax = wire_frame_bits(payload_bytes, frame_header_bytes, phy_overhead_bits)
    return TokenBucket(
        rho_bps=lmax / bag_s,
        sigma_bits=float(lmax * margin_factor),
        lmax_bits=lmax,
    )
