from __future__ import annotations

import re

_DURATION_RE = re.compile(r"^(\d+)\s*([dhw])$", re.IGNORECASE)
_UNIT_HOURS = {"h": 1, "d": 24, "w": 24 * 7}


def parse_duration_hours(spec: str) -> int:
    """Parse "30d" / "12h" / "2w" into hours. Bare integers are treated as days."""
    spec = spec.strip().lower()
    m = _DURATION_RE.match(spec)
    if m:
        n, unit = m.groups()
        return int(n) * _UNIT_HOURS[unit]
    if spec.isdigit():
        return int(spec) * 24
    raise ValueError(f"invalid duration: {spec!r} (expected e.g. '30d', '12h', '2w')")
