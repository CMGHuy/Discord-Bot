"""v228: raise journal excursions to finer bars once the archives hold them.

At close the 5min/15min archives are up to a day stale, so most entries are
journaled from daily bars. This pass re-measures entries closed in a window
whose excursion_source is coarser than 5min and rewrites six fields (mfe_r,
mae_r, exit_efficiency, excursion_source, tags, auto_lesson) when -- and only
when -- a finer frame covers the trade. The write is
JournalRepository.patch_if_coarser: the rank guard is in the UPDATE, so the
bot's nightly pass and scripts/ops/backfill_excursions.py cannot downgrade
each other, and the partner's note is never touched. A journal entry has no
prices, so each one is joined to its TradeLog trade by id."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from swingbot.core.analytics.excursion_frames import FrameSet, load_frames
from swingbot.core.analytics.journal import _auto_lesson, tags_for
from swingbot.core.analytics.mfe_mae import (
    EXCURSION_SOURCES, coarser_sources, compute_excursion, frame_verdicts, source_rank,
)
from swingbot.core.db.repositories.journal import journal_repo
from swingbot.core.marketdata.data_store import DATA_DIR

_COUNTS = ("read", "no_trade", "no_file", "unreadable", "no_coverage", "density",
           "no_inputs", "lost_race")
_VERDICT_REASON = {"coverage": "no_coverage", "empty": "no_coverage", "density": "density"}
#: Every pending entry is coarser than 5min, so 5min is the rung a skip is judged on.
_FINEST = EXCURSION_SOURCES[0]


@dataclass
class UpgradeReport:
    read: int = 0
    upgraded: dict[str, int] = field(default_factory=lambda: dict.fromkeys(EXCURSION_SOURCES, 0))
    no_trade: int = 0
    no_file: int = 0
    unreadable: int = 0
    no_coverage: int = 0
    density: int = 0
    no_inputs: int = 0
    lost_race: int = 0
    budget_hit: bool = False

    def as_dict(self) -> dict:
        return {**{key: getattr(self, key) for key in _COUNTS},
                "upgraded": dict(self.upgraded), "budget_hit": self.budget_hit}

    def absorb(self, counts: dict) -> None:
        for key in _COUNTS:
            setattr(self, key, getattr(self, key) + int(counts.get(key, 0)))
        for source, n in (counts.get("upgraded") or {}).items():
            self.upgraded[source] = self.upgraded.get(source, 0) + int(n)
        self.budget_hit = self.budget_hit or bool(counts.get("budget_hit"))

    def line(self) -> str:
        upgraded = " ".join(f"{s}={self.upgraded.get(s, 0)}" for s in EXCURSION_SOURCES)
        rest = ", ".join(f"{key} {getattr(self, key)}" for key in _COUNTS[1:])
        return (f"excursion upgrade: read {self.read}, upgraded {upgraded}, {rest}, "
                f"budget_hit {'yes' if self.budget_hit else 'no'}")


def _trades_by_id() -> dict[str, dict]:
    from swingbot.core.tracking.performance import TradeLog
    return {t.get("id"): t for t in TradeLog().get_trades(status=None, limit=None) or []}


def _utc(iso: str | None) -> datetime | None:
    try:
        value = datetime.fromisoformat(str(iso))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _closed_by(entry: dict, until: datetime | None) -> bool:
    if until is None:
        return True
    closed = _utc(entry.get("closed_at"))
    return closed is not None and closed <= until


def pending_by_ticker(since: str | None, until: str | None = None
                      ) -> dict[str, list[tuple[dict, dict | None]]]:
    """Entries closed in [since, until] still coarser than 5min, with their trade."""
    from swingbot.core.analytics.journal import JournalStore
    from swingbot.core.tracking.origin import ALL
    until_dt = _utc(until) if until else None
    entries = [e for e in JournalStore().entries(since=since, cohort=ALL)
               if source_rank(e.get("excursion_source")) > 0 and _closed_by(e, until_dt)]
    trades = _trades_by_id() if entries else {}
    grouped: dict[str, list[tuple[dict, dict | None]]] = {}
    for entry in entries:
        trade = trades.get(entry.get("trade_id"))
        ticker = entry.get("ticker") or (trade or {}).get("ticker") or ""
        grouped.setdefault(ticker, []).append((entry, trade))
    return dict(sorted(grouped.items()))


def _skip_reason(trade: dict, fs: FrameSet) -> str:
    verdicts = frame_verdicts(trade, {**fs.frames, _FINEST: fs.frames.get(_FINEST)})
    if not verdicts:
        return "no_inputs"
    if _FINEST in fs.missing:
        return "no_file"
    if _FINEST in fs.unreadable:
        return "unreadable"
    return _VERDICT_REASON.get(verdicts.get(_FINEST), "no_coverage")


def _changes(entry: dict, trade: dict, m: dict) -> dict:
    return {"mfe_r": m["mfe_r"], "mae_r": m["mae_r"], "exit_efficiency": m["exit_efficiency"],
            "excursion_source": m["excursion_source"], "tags": tags_for(trade, m),
            "auto_lesson": _auto_lesson(entry.get("outcome"), m["mfe_r"], m["mae_r"],
                                        m["exit_efficiency"], entry.get("r_realized"))}


def _upgrade_one(entry: dict, trade: dict | None, fs: FrameSet) -> str:
    if trade is None:
        return "no_trade"
    m = compute_excursion(trade, fs.frames)
    if m is None or source_rank(m["excursion_source"]) >= source_rank(entry.get("excursion_source")):
        return _skip_reason(trade, fs)
    written = journal_repo().patch_if_coarser(
        entry["trade_id"], _changes(entry, trade, m), coarser=coarser_sources(m["excursion_source"]))
    return "lost_race" if written is None else f"upgraded:{m['excursion_source']}"


def _tally(report: UpgradeReport, outcome: str) -> None:
    if outcome.startswith("upgraded:"):
        source = outcome.split(":", 1)[1]
        report.upgraded[source] = report.upgraded.get(source, 0) + 1
    else:
        setattr(report, outcome, getattr(report, outcome) + 1)


def upgrade_ticker(ticker: str, pairs: list[tuple[dict, dict | None]], report: UpgradeReport, *,
                   base_dir: str = DATA_DIR, deadline: float | None = None) -> bool:
    """Re-measure one ticker's pending entries; False when the budget ran out first."""
    if deadline is not None and time.monotonic() > deadline:
        report.budget_hit = True
        return False
    fs = load_frames(ticker, daily_from_archive=True, base_dir=base_dir)
    for entry, trade in pairs:
        report.read += 1
        _tally(report, _upgrade_one(entry, trade, fs))
    return True


def upgrade_excursions(since: str | None, until: str | None = None, *,
                       budget_seconds: float | None = None,
                       base_dir: str = DATA_DIR) -> UpgradeReport:
    """The whole pass: one load_frames per ticker, tickers in name order."""
    report = UpgradeReport()
    deadline = None if budget_seconds is None else time.monotonic() + budget_seconds
    for ticker, pairs in pending_by_ticker(since, until).items():
        if not upgrade_ticker(ticker, pairs, report, base_dir=base_dir, deadline=deadline):
            break
    return report
