"""v239: the bear-regime pass -- every wiring decision of the daily trend engine.

`regime_mode` reads BEAR_REGIME_MODE; an unknown value is `off`, the
byte-identical kill switch (no fetch, no row, no stamp, no line, no notice).
`live` behaves exactly like `shadow` in v239. V239-8 adds regime_for_pass.

Spec: docs/superpowers/specs/2026-11-23-v239-bear-regime-engine-shadow-design.md
"""
from __future__ import annotations

from swingbot import config

MODES = ("off", "shadow", "live")


def regime_mode() -> str:
    mode = str(getattr(config, "BEAR_REGIME_MODE", "off") or "off").strip().lower()
    return mode if mode in MODES else "off"
