"""Turning free-text user names into identifiers OMNeT++ will actually accept.

This exists because of a concrete, verified failure: a directory named `simple-network` containing
a .ned file makes the NED loader hard-error --

    Declared package 'x' does not match expected package 'x.networks.simple-network'

-- because every dot-separated segment of a NED package must be a valid NED identifier, and a
hyphen is not. `opp_nedtool` reports it as a bare "syntax error" with no hint about the cause,
which is unpleasant to debug. So: sanitize once, here, and never hand a raw name to codegen.
"""

from __future__ import annotations

import re

_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_]")
_LEADING_NON_ALPHA = re.compile(r"^[^A-Za-z_]+")

# Not exhaustive -- just the NED/C++ keywords a network name might plausibly collide with.
_RESERVED = {
    "network", "module", "simple", "channel", "package", "import", "parameters", "gates",
    "submodules", "connections", "types", "extends", "like", "if", "for", "int", "double",
    "string", "bool", "xml", "const", "volatile", "default", "class", "struct", "namespace",
}


def sanitize_ned_identifier(name: str, fallback: str = "Network") -> str:
    """Coerce `name` into a valid NED identifier.

    Replaces every illegal character with '_', strips leading characters that cannot start an
    identifier, and suffixes reserved words. Returns `fallback` if nothing usable remains.

    >>> sanitize_ned_identifier("simple-network")
    'simple_network'
    >>> sanitize_ned_identifier("2fast")
    'fast'
    >>> sanitize_ned_identifier("network")
    'network_'
    >>> sanitize_ned_identifier("!!!")
    'Network'
    """
    cleaned = _INVALID_CHARS.sub("_", name.strip())
    cleaned = _LEADING_NON_ALPHA.sub("", cleaned)
    if not cleaned.strip("_"):
        return fallback
    if cleaned in _RESERVED:
        cleaned += "_"
    return cleaned


def sanitize_path_segment(name: str, fallback: str = "network") -> str:
    """Coerce `name` into a safe single filesystem path segment.

    Note this is deliberately a separate function from `sanitize_ned_identifier` even though the
    current implementation happens to produce path-safe output too. "Valid NED identifier" and
    "safe path segment" are different guarantees; relying on their incidental overlap would be a
    trap the first time either definition changes.
    """
    cleaned = _INVALID_CHARS.sub("_", name.strip())
    cleaned = cleaned.strip("._")
    return cleaned or fallback
