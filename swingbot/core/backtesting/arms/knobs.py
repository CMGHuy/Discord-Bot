"""Per-arm config deltas, applied inside a producer worker (v100)."""
from __future__ import annotations

from contextlib import contextmanager

from swingbot import config


def _field(attr: str):
    for field in config.FIELDS:
        if field.attr == attr:
            return field
    raise ValueError(f"{attr} is not a config field")


def parse_knob(text: str) -> tuple[str, object]:
    """Parse an ``ATTR=value`` CLI value using its canonical field caster."""
    attr, separator, raw = text.partition("=")
    if not separator or not attr:
        raise ValueError(f"--knob must be ATTR=value, got {text!r}")
    field = _field(attr)
    allowed = [value for value, _label in field.options]
    if allowed and raw not in allowed:
        # A select's caster may fall back to a default ("off"); a measurement
        # must never silently run a different arm than the one it named.
        raise ValueError(f"{attr} must be one of {allowed}, got {raw!r}")
    return attr, config._cast(field, raw)


#: v192: the veto decides at the next open, which only MARKET_ENTRY_NEXT_OPEN creates.
GAP_RECLAIM_NEEDS_NEXT_OPEN = "GAP_RECLAIM_ATR > 0 needs MARKET_ENTRY_NEXT_OPEN on"


def _check_coupling() -> None:
    """Refuse an arm whose merged config would run the veto without the next-open fill."""
    if getattr(config, "GAP_RECLAIM_ATR", 0.0) > 0 and not getattr(config, "MARKET_ENTRY_NEXT_OPEN", False):
        raise ValueError(GAP_RECLAIM_NEEDS_NEXT_OPEN)


@contextmanager
def apply_knobs(delta: dict):
    """Temporarily apply config-global deltas and restore them reliably."""
    missing = object()
    saved = {attr: getattr(config, attr, missing) for attr in delta}
    try:
        for attr, value in delta.items():
            setattr(config, attr, value)
        _check_coupling()
        yield
    finally:
        for attr, value in saved.items():
            if value is missing:
                delattr(config, attr)
            else:
                setattr(config, attr, value)
