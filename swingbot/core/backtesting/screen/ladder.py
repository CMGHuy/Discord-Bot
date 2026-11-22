"""v238 replication ladder rules (v230 spec Part B): ids, windows, the hold
rule, the paired difference, refusals, next step. Races: ``ladder_race`` /
``ladder_bot``; CLI: scripts/backtest/replicate_idea.py. Rung 1 uses the v1
null (index ruling 1). The ladder never reads 2021+."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from swingbot.core.backtesting.instrument import stats
from swingbot.core.backtesting.screen import verdict as screen_verdict

LADDER_INSTRUMENT = "ladder-v1"
RUNGS = (1, 2, 3, 4)
RUNG_NAMES = {1: "robustness", 2: "orderable", 3: "bot stop", 4: "bot target"}
STORE_START = "2016-01-04"
EVENT_START = "2017-03-01"
READ_END = "2020-12-31"
HOLD_N = 300
HOLD = "LADDER-HOLD"
FAIL = "LADDER-FAIL"
UNDERPOWERED = "LADDER-UNDERPOWERED"
UNAVAILABLE = "LADDER-UNAVAILABLE"   # a refusal before any outcome is read; never a row
_LABELS = (HOLD, FAIL, UNDERPOWERED)
INPUT_INSTRUMENTS = ("screen-v1", "screen-v2")
_INPUT_PREFIXES = ("screen2-", "screen-")   # a re-screen row governs the first screen
NULL_VERSION = "v1"
BIASED_NULL_NOTE = ("biased null (v230 placebo): the v1 null itself reads +0.27..+0.37R "
                    "on next-open longs, so rung 1's delta against it is not evidence "
                    "on its own; see docs/superpowers/results/2026-11-18-v230-null-placebo.md")
RESAMPLES = 10_000
SEED = 42
_NO_SHOT = "No row, no shot spent."
NEXT_STEPS = {
    "pending": "run the next rung",
    "non_replication": "idea closed as a non-replication; later rungs do not run",
    "partner_open": "rung 1 holds, rung 2 does not: the partner decides (v230 spec, Open)",
    "orderable_shape": ("a strategy spec in the orderable screened shape (rung 2), sized to "
                        "the 2% dollar-risk rule; the failed rung closes that bot stop or "
                        "target for this idea"),
    "bot_shape": "a strategy spec in the bot's shape",
}


def _check_rung(rung: int) -> None:
    if rung not in RUNGS:
        raise ValueError(f"rung {rung!r} is not one of {RUNGS}")


def ladder_id(name: str, rung: int) -> str:
    _check_rung(rung)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("a ladder id needs an idea name")
    return f"ladder-{name}-r{rung}"


@dataclass(frozen=True)
class LadderEvent:
    ticker: str
    signal_date: str      # bar t, known at its close
    entry_date: str       # bar t+1, the open fill
    exit_date: str
    r: float              # net R against the planned risk
    gross_r: float
    outcome: str          # a race.OUTCOMES code
    r_null: float | None = None    # rung 1: the v1 null's mean net R for this event
    r_stress: float | None = None  # net R at 2 x slippage (printed, never gating)

    @property
    def key(self) -> tuple[str, str]:
        return (self.ticker, self.signal_date)


@dataclass(frozen=True)
class HoldResult:
    verdict: str
    n: int
    mean: float | None
    lo: float | None
    hi: float | None
    p: float | None
    delta_null: float | None


@dataclass(frozen=True)
class PairedDiff:
    n: int
    mean: float | None
    lo: float | None
    hi: float | None
    wholly_below_zero: bool


def _week_draws(pairs: Sequence[tuple[str, float]], *, n_resamples: int,
                seed: int) -> np.ndarray:
    """Week-clustered bootstrap of the pooled mean of ``(entry_date, value)``."""
    weeks = screen_verdict.week_sums([screen_verdict.PairedEvent(d, v) for d, v in pairs])
    return stats.week_cluster_bootstrap([], weeks, screen_verdict.pooled_mean,
                                        n_resamples=n_resamples, seed=seed)


def _interval(draws: np.ndarray) -> tuple[float | None, float | None, float | None]:
    """(2.5th percentile, 97.5th percentile, share of draws <= 0)."""
    if draws.size == 0:
        return None, None, None
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return float(lo), float(hi), float(np.mean(draws <= 0.0))


def _delta_null(events: Sequence[LadderEvent]) -> float | None:
    if not events or any(e.r_null is None for e in events):
        return None
    return float(np.mean([e.r - e.r_null for e in events]))


def hold_verdict(n: int, lo: float | None, *, rung: int, delta: float | None = None) -> str:
    if n < HOLD_N:
        return UNDERPOWERED
    if lo is None or not lo > 0.0:
        return FAIL
    if rung == 1 and (delta is None or not delta > 0.0):
        return FAIL
    return HOLD


def hold(events: Iterable[LadderEvent], *, rung: int, n_resamples: int = RESAMPLES,
         seed: int = SEED) -> HoldResult:
    _check_rung(rung)
    events = list(events)
    if not events:
        return HoldResult(UNDERPOWERED, 0, None, None, None, None, None)
    lo, hi, p = _interval(_week_draws([(e.entry_date, e.r) for e in events],
                                      n_resamples=n_resamples, seed=seed))
    delta = _delta_null(events) if rung == 1 else None
    return HoldResult(hold_verdict(len(events), lo, rung=rung, delta=delta), len(events),
                      float(np.mean([e.r for e in events])), lo, hi, p, delta)


def _by_key(events: Iterable[LadderEvent]) -> dict:
    out: dict = {}
    for event in events:
        if event.key in out:
            raise ValueError(f"duplicate ladder event {event.key}")
        out[event.key] = event
    return out


def paired_difference(upper: Iterable[LadderEvent], lower: Iterable[LadderEvent], *,
                      n_resamples: int = RESAMPLES, seed: int = SEED) -> PairedDiff:
    """Lower rung minus the rung above, on the events both rungs traded."""
    above, below = _by_key(upper), _by_key(lower)
    pairs = [(e.entry_date, e.r - above[k].r) for k, e in below.items() if k in above]
    if not pairs:
        return PairedDiff(0, None, None, None, False)
    lo, hi, _ = _interval(_week_draws(pairs, n_resamples=n_resamples, seed=seed))
    return PairedDiff(len(pairs), float(np.mean([d for _, d in pairs])), lo, hi,
                      hi is not None and hi < 0.0)


def _row_of(rows: Iterable[Mapping], row_id: str) -> Mapping | None:
    return next((row for row in rows if row.get("id") == row_id), None)


def input_row(name: str, rows: Iterable[Mapping]) -> Mapping | None:
    """The governing screen row if it is a SCREEN-PASS on an input instrument."""
    rows = list(rows)
    for prefix in _INPUT_PREFIXES:
        row = _row_of(rows, prefix + name)
        if row is not None:
            ok = row.get("verdict") == "SCREEN-PASS" and row.get("instrument") in INPUT_INSTRUMENTS
            return row if ok else None
    return None


def input_refusal(name: str, rows: Iterable[Mapping]) -> str | None:
    if input_row(name, rows) is not None:
        return None
    return (f"refused: {name} has no governing SCREEN-PASS row (screen2-{name}, else "
            f"screen-{name}) on {' or '.join(INPUT_INSTRUMENTS)}. {_NO_SHOT}")


def rung_refusal(name: str, rung: int, rows: Iterable[Mapping]) -> str | None:
    if rung not in RUNGS:
        return f"refused: rung {rung!r} is not one of {RUNGS}. {_NO_SHOT}"
    rows = list(rows)
    own = ladder_id(name, rung)
    if _row_of(rows, own) is not None:
        return f"refused: {own} already has a ledger row (one shot per id). {_NO_SHOT}"
    if rung == 1:
        return None
    above_id = ladder_id(name, rung - 1)
    above = _row_of(rows, above_id)
    found = "no row" if above is None else above.get("verdict")
    if found == HOLD:
        return None
    return f"refused: rung {rung} needs {HOLD} on {above_id} (found {found}). {_NO_SHOT}"


def shape_refusal(idea, rung: int) -> str | None:
    if rung == 1 or (idea.race_shape == "fixed" and idea.entry == "next_open"):
        return None
    return (f"{UNAVAILABLE}: rung {rung} needs the fixed next-open shape "
            f"({idea.name} races {idea.race_shape} / {idea.entry}). {_NO_SHOT}")


def context_refusal(idea, store_dir) -> str | None:
    missing = [s for s in idea.context if not (Path(store_dir) / f"{s}.csv").is_file()]
    if not missing:
        return None
    return f"{UNAVAILABLE}: context series {', '.join(missing)} missing from {store_dir}. {_NO_SHOT}"


def membership_coverage(members: Iterable[str], store_dir) -> dict:
    """Printed and recorded before a run; never a refusal (index decision)."""
    names = sorted(set(members))
    missing = [t for t in names if not (Path(store_dir) / f"{t}.csv").is_file()]
    return {"members": len(names), "in_store": len(names) - len(missing),
            "missing_count": len(missing), "missing": missing}


def _check_holds(holds: Mapping[int, str]) -> None:
    bad = [r for r in holds if r not in RUNGS] + [v for v in holds.values() if v not in _LABELS]
    if bad:
        raise ValueError(f"next_step: unknown rung or verdict {bad!r}")


def _early_step(holds: Mapping[int, str]) -> str | None:
    if 1 not in holds:
        return "pending"
    if holds[1] != HOLD:
        return "non_replication"
    if 2 not in holds:
        return "pending"
    return None if holds[2] == HOLD else "partner_open"


def _late_step(holds: Mapping[int, str], diff: PairedDiff | None) -> str:
    for rung in (3, 4):
        if rung not in holds:
            return "pending"
        if holds[rung] != HOLD:
            return "orderable_shape"
    if diff is None:
        raise ValueError("rungs 1-4 hold: next_step needs rung 4's paired difference to rung 2")
    return "orderable_shape" if diff.wholly_below_zero else "bot_shape"


def next_step(holds: Mapping[int, str], diff_4_vs_2: PairedDiff | None) -> str:
    _check_holds(holds)
    return _early_step(holds) or _late_step(holds, diff_4_vs_2)
