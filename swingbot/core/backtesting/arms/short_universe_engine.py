"""The v118 population engine: a whole-window scan replay, not one ticker.

`run_population` replays the base lane (identical whatever the mode) and, unless
`mode == "off"`, the SHORT extra lane in that one weakness mode, through
`scanning/scan_replay.py` -- the live selector, scenario scoring and
`qualify_short_item` gates. Rows are the standard `ArmTrade` schema, closed
trades only (the same SKIPPED outcomes the confluence engine drops), so
`validate_component.py` and the acceptance clauses read them unchanged.
"""
from __future__ import annotations

from swingbot.core.backtesting.arms.confluence_engine import SKIPPED
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
from swingbot.core.scanning import scan_replay


class ShortUniverseEngine:
    engine_id = "short_universe"

    def __init__(self, base_tickers=(), horizons=ALL_HORIZONS, track_record=scan_replay.no_track_record):
        self.spec = scan_replay.ReplaySpec(base_tickers=tuple(base_tickers), horizons=tuple(horizons),
                                           track_record=track_record)

    def replay(self, frames: dict, window: tuple[str, str], params, *, mode: str) -> scan_replay.ScanReplay:
        return scan_replay.replay_short_universe(frames, window, params, mode=mode, spec=self.spec)

    def run_population(self, frames: dict, window: tuple[str, str], params, *, mode: str) -> list:
        measured = self.replay(frames, window, params, mode=mode)
        return [alert.arm_trade() for alert in measured.base_alerts + measured.added
                if alert.outcome not in SKIPPED]
