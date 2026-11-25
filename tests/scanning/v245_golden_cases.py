"""v245 characterisation goldens for analyze._scan_one (spec § Testing).

Pins today's per-ticker analysis output byte for byte before any v245
change. Every later v245 task that touches analysis keeps
tests/fixtures/scanning/v245_scan_one_golden.json unchanged: a task that
needs to regenerate it has found a behaviour change and stops.

Regenerate only on unchanged analysis code (index Decision 2, a platform
float difference), never to absorb a refactor:
    V245_REGEN_GOLDEN=1 python -m pytest tests/scanning/test_v245_scan_one_golden.py -p no:xdist -q
"""
from __future__ import annotations

import dataclasses
import functools
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market.strategy_types import LEGACY_HORIZONS
from swingbot.core.scanning import analyze

GOLDEN_NOW = datetime(2024, 3, 15, 19, 0, tzinfo=timezone.utc)   # 15:00 New York, regular session
GOLDEN_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "scanning" / "v245_scan_one_golden.json"
REGEN_ENV = "V245_REGEN_GOLDEN"
TICKER = "GOLD"
FORMING_DAY = "2024-03-15"     # a forming frame's last row; its completed twin ends 2024-03-14
MIN_CONFLUENCE = 2             # mid thresholds: some requirements pass, some fail
MIN_CONFIDENCE = 2
# Loose enough that most horizons build a scenario, so confluence,
# confidence and requirements are all exercised (pattern: test_rescenario.HF).
GOLDEN_HARD_FILTERS = {
    "min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
    "min_risk_reward_ratio": 0.01, "confluence_deviation_pct": 1.0,
}
# Config fields run_case leaves alone: secrets and connection strings.
_UNPINNED = frozenset({"DATABASE_URL"})

HERMETIC_IO = analyze.ScanIO(
    stop_requested=lambda: False,
    monitor_scan=lambda ticker, df, current_price: ([], []),
    monitor_open=lambda ticker, df, live_price=None: ([], []),
    track_record=lambda base_level: (None, 0),
)

# ScanItem fields the snapshot reads, named so that a field added later
# (V245-9's prefix_results) never changes the golden.
ITEM_FIELDS = (
    "result", "plan", "conf", "requirements", "target_confluence", "stop_confluence",
    "combined_from", "htf_info", "previous_confirmed", "htf_bias", "level_map",
    "rs_percentile", "trendline_candidates", "scan_price", "hard_filters", "candidate_context",
)
STAT_KEYS = (
    "checked", "no_entry_point", "scenarios_found", "fully_qualifying", "mtf_misaligned",
    "failed_counts", "conf_level_counts", "data_quality_failed", "funnel_events",
)


@dataclass(frozen=True)
class GoldenCase:
    name: str
    frame: Callable[[], pd.DataFrame | None]
    horizons: tuple[str, ...]
    allowed_directions: object
    mtf_adjacent_gate: bool
    live_price: Callable[[pd.DataFrame], float | None]
    atr_stop_floor: float = 0.0


def _wave_frame(n: int, *, seed: int, drift: float, end: str) -> pd.DataFrame:
    """Random walk times a 37-bar wave, 2.5x volume on every ±5-bar extreme."""
    rng = np.random.RandomState(seed)
    base = 100.0 * np.exp(np.cumsum(rng.normal(drift, 0.012, n)))
    close = np.round(base * (1.0 + 0.06 * np.sin(2 * np.pi * np.arange(n) / 37.0)), 4)
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.round(np.maximum(open_, close) * 1.01, 4)
    low = np.round(np.minimum(open_, close) * 0.99, 4)
    volume = np.full(n, 1_000_000.0)
    for i in range(n):
        window = close[max(0, i - 5): i + 6]
        if close[i] in (window.max(), window.min()):
            volume[i] = 2_500_000.0
    index = pd.bdate_range(end=end, periods=n)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                         "Volume": volume}, index=index)


def _forming(n: int, seed: int, drift: float) -> Callable[[], pd.DataFrame]:
    """n completed bars plus a forming row dated FORMING_DAY at 40% volume."""
    def build() -> pd.DataFrame:
        df = _wave_frame(n + 1, seed=seed, drift=drift, end=FORMING_DAY)
        df.iloc[-1, df.columns.get_loc("Volume")] = round(float(df["Volume"].iloc[-2]) * 0.4)
        return df
    return build


def _completed(n: int, seed: int, drift: float) -> Callable[[], pd.DataFrame]:
    """The forming frame minus its forming row: ends 2024-03-14."""
    forming = _forming(n, seed, drift)
    return lambda: forming().iloc[:-1].copy()


def _at_close(df: pd.DataFrame) -> float | None:
    return None                       # no live print: _scan_one falls back to the last close


def _times(mult: float) -> Callable[[pd.DataFrame], float]:
    return lambda df: round(float(df["Close"].iloc[-1]) * mult, 4)


def _case(name, frame, *, live=_at_close, directions=None, gate=False,
          horizons=LEGACY_HORIZONS, floor=0.0) -> GoldenCase:
    return GoldenCase(name, frame, tuple(horizons), directions, gate, live, floor)


_WAVE = dict(n=420, seed=11, drift=0.0004)    # 420 >= MIN_BARS["9m"] (390)
_DOWN = dict(n=420, seed=23, drift=-0.0006)
_LONG = dict(n=1560, seed=37, drift=0.0003)   # longer than MAX_PIVOT_SCAN_BARS: the 1500-bar trim runs
_SHORT = dict(n=150, seed=11, drift=0.0004)   # passes 2w..3m, below MIN_BARS for 4m..9m

CASES: tuple[GoldenCase, ...] = (
    _case("wave_completed", _completed(**_WAVE)),
    _case("wave_completed_gate", _completed(**_WAVE), gate=True),
    _case("wave_forming", _forming(**_WAVE), live=_times(1.0)),
    _case("wave_forming_gate", _forming(**_WAVE), live=_times(1.0), gate=True),
    _case("wave_bullish_only", _completed(**_WAVE), directions=frozenset({"bullish"})),
    _case("wave_bearish_only", _completed(**_WAVE), directions=frozenset({"bearish"})),
    # Live prices relative to the close: +-1.2% gaps through a near entry,
    # +-4% and +-8% through the nearer and farther stop/target levels.
    _case("wave_forming_gap_up_1", _forming(**_WAVE), live=_times(1.012)),
    _case("wave_forming_gap_dn_1", _forming(**_WAVE), live=_times(0.988)),
    _case("wave_forming_gap_up_4", _forming(**_WAVE), live=_times(1.04)),
    _case("wave_forming_gap_dn_4", _forming(**_WAVE), live=_times(0.96)),
    _case("wave_forming_gap_up_8", _forming(**_WAVE), live=_times(1.08)),
    _case("wave_forming_gap_dn_8", _forming(**_WAVE), live=_times(0.92)),
    _case("wave_completed_stale_print", _completed(**_WAVE), live=_times(0.70)),
    _case("wave_completed_band", _completed(**_WAVE), floor=1.0),
    _case("wave_forming_band", _forming(**_WAVE), live=_times(1.0), floor=1.0),
    _case("down_completed", _completed(**_DOWN)),
    _case("down_forming", _forming(**_DOWN), live=_times(1.0)),
    _case("long_completed", _completed(**_LONG)),
    _case("long_forming", _forming(**_LONG), live=_times(1.0)),
    _case("short_history_completed", _completed(**_SHORT)),
    _case("short_history_forming", _forming(**_SHORT), live=_times(1.0)),
    _case("no_frame", lambda: None),
)
CASE_BY_NAME = {case.name: case for case in CASES}


class _FrozenDatetime(datetime):
    frozen = GOLDEN_NOW

    @classmethod
    def now(cls, tz=None):
        return cls.frozen if tz is None else cls.frozen.astimezone(tz)


def frozen_clock(monkeypatch, now: datetime = GOLDEN_NOW) -> None:
    """Every datetime.now() analyze makes returns `now` (index Decision 1)."""
    monkeypatch.setattr(analyze, "datetime", type("_Frozen", (_FrozenDatetime,), {"frozen": now}))


def _pin_config_defaults(mp) -> None:
    for f in config.FIELDS:
        if f.sensitive or f.attr in _UNPINNED or not hasattr(config, f.attr):
            continue
        mp.setattr(config, f.attr, config._cast(f, f.default))


def run_case(case: GoldenCase, *, structure=None) -> dict:
    """Run `_scan_one` on the case, hermetically, and return its snapshot."""
    df = case.frame()
    live = case.live_price(df) if df is not None else None
    hard_filters = {**GOLDEN_HARD_FILTERS, "mtf_adjacent_gate": case.mtf_adjacent_gate,
                    "confluence_atr_stop_floor": case.atr_stop_floor}
    extra = {} if structure is None else {"structure": structure}
    with pytest.MonkeyPatch.context() as mp:
        _pin_config_defaults(mp)
        stats = analyze._scan_one(
            TICKER, df, list(case.horizons), None, None, MIN_CONFLUENCE, MIN_CONFIDENCE,
            live_prices={TICKER: live} if live else None, hard_filters=hard_filters,
            allowed_directions=case.allowed_directions, io=HERMETIC_IO, **extra)
    return snapshot(stats)


def _canon(obj):
    """JSON-able, exact: floats as float.hex, containers recursed, keys sorted."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, np.generic):
        return _canon(obj.item())
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return float.hex(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _canon(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _canon(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_canon(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    raise TypeError(f"v245 golden: no exact form for {type(obj).__name__}")


def _item(item) -> dict:
    doc = {name: _canon(getattr(item, name)) for name in ITEM_FIELDS}
    doc["all_requirements_met"] = item.all_requirements_met
    doc["risk_reward_ratio"] = _canon(item.plan.risk_reward_ratio)
    return doc


def snapshot(stats: dict) -> dict:
    """The exact, JSON-able projection of one `_scan_one` stats dict."""
    out = {key: _canon(stats[key]) for key in STAT_KEYS}
    out["newly_closed"] = len(stats["newly_closed"])
    out["near_close_warnings"] = len(stats["near_close_warnings"])
    out["items"] = [_item(item) for item in stats["items"]]
    return out


def first_diff(a, b, path: str = "$") -> str | None:
    """Path of the first difference between two snapshots, or None."""
    if type(a) is not type(b):
        return f"{path}: {a!r} != {b!r}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                return f"{path}.{key}: present on one side only"
            found = first_diff(a[key], b[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        return next((d for i, (x, y) in enumerate(zip(a, b))
                     if (d := first_diff(x, y, f"{path}[{i}]"))), None)
    return None if a == b else f"{path}: {a!r} != {b!r}"


@functools.lru_cache(maxsize=1)
def _golden_text() -> str:
    return GOLDEN_PATH.read_text(encoding="utf-8")


def load_golden() -> dict:
    """A fresh dict per call (the parsed text is cached, never the dict)."""
    return json.loads(_golden_text())


def write_golden(doc: dict) -> None:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    _golden_text.cache_clear()
