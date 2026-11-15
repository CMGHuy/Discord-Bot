# v228 — Intraday MFE/MAE for the journal: Part 5, upgrade pass (V228-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V228-5" -A 400 <this file>`); never read the part whole.

**Spec:** [2026-11-14-v228-intraday-excursion-design.md](../specs/2026-11-14-v228-intraday-excursion-design.md)
**Index:** [2026-11-14-v228-intraday-excursion_0-index.md](2026-11-14-v228-intraday-excursion_0-index.md) — Goal, Architecture, **Global Constraints**, Review Focus, Parallelisation and the Task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: the upgrade pass (V228-5). It was written for part 1 and moved here because part 1 would have passed 1500 lines; in execution order it still runs after V228-4 and V228-3 and before V228-6 and V228-8.

Shared notes: run tests with `python scripts/dev/testrun.py file <test file>` only. V228-5 reaches the local Postgres: run `/replicate-prod-db` first (shared `swing-db` container, port 56789); a skipped DB test is not a pass.

### Task V228-5: `upgrade_excursions`: join trades, finer-only conditional patch, report

**Model:** opus — the write path that touches every journal row in production; never-downgrade, note safety and the skip accounting must all hold.

**Files:**
- Create: `swingbot/core/analytics/excursion_upgrade.py`
- Create: `tests/excursion/test_excursion_upgrade.py`

**Interfaces:**
- Consumes: V228-2 — `EXCURSION_SOURCES`, `source_rank`, `coarser_sources`, `compute_excursion`, `frame_verdicts`; V228-3 — `JournalRepository.patch_if_coarser(trade_id, changes, *, coarser, conn=None) -> dict | None` via `journal_repo()`; V228-4 — `FrameSet`, `load_frames(ticker, *, daily=None, daily_from_archive=False, base_dir=DATA_DIR)`; existing — `journal.tags_for(trade, m)`, `journal._auto_lesson(outcome, mfe_r, mae_r, exit_efficiency, r_realized)`, `JournalStore().entries(since=..., cohort=origin.ALL)`, `TradeLog().get_trades(status=None, limit=None)` (the `rejournal_fill_mismatch.py` precedent).
- Produces (final, consumed by V228-6 and V228-8):
  - `@dataclass class UpgradeReport` — `read`, `upgraded: dict[str, int]` (one key per `EXCURSION_SOURCES`), `no_trade`, `no_file`, `unreadable`, `no_coverage`, `density`, `no_inputs`, `lost_race`: int; `budget_hit: bool`; `line() -> str` (starts `excursion upgrade: `); `as_dict() -> dict`; `absorb(counts: dict) -> None` (adds an `as_dict()` shape)
  - `pending_by_ticker(since: str | None, until: str | None = None) -> dict[str, list[tuple[dict, dict | None]]]` — entries closed in the window with `source_rank(excursion_source) > 0`, paired with their trade (or `None`), grouped by ticker, tickers sorted
  - `upgrade_ticker(ticker, pairs, report, *, base_dir=DATA_DIR, deadline: float | None = None) -> bool` — `False` (and `report.budget_hit = True`) when `time.monotonic()` has passed `deadline` before the ticker starts
  - `upgrade_excursions(since, until=None, *, budget_seconds=None, base_dir=DATA_DIR) -> UpgradeReport`

**Rules:** the patch carries exactly `mfe_r`, `mae_r`, `exit_efficiency`, `excursion_source`, `tags`, `auto_lesson`, through `patch_if_coarser(..., coarser=coarser_sources(new_source))` only — never `JournalStore.add` or `build_entry` (which writes `"note": ""`). A result whose source is not finer than the stored one is not written. Each entry read counts exactly one outcome: `upgraded[<source>]`, `lost_race` (the guarded `UPDATE` matched nothing because a finer write landed first), `no_trade`, `no_inputs` (no usable risk or dates), or — judged on the `5min` rung, the finest any pending entry can reach — `no_file`, `unreadable`, `no_coverage` (also an empty frame) or `density`. The daily rung reads the `market_data/daily` archive (`daily_from_archive=True`).

Run `/replicate-prod-db` before Step 2 (the tests write journal rows through `JournalStore`; `TradeLog` is replaced by a fixture).

- [ ] **Step 1: Write the failing tests**

Create `tests/excursion/test_excursion_upgrade.py`:

```python
"""v228 V228-5: the upgrade pass -- finer only, note kept, every skip counted."""
from __future__ import annotations

import time

import pandas as pd
import pytest

from swingbot.core.analytics import excursion_upgrade as eu
from swingbot.core.analytics.excursion_upgrade import (
    UpgradeReport, pending_by_ticker, upgrade_excursions, upgrade_ticker,
)
from swingbot.core.analytics.journal import JournalStore

DAY = "2026-11-12"
RULE3 = "Entry was wrong from the first bar — review the trigger, not the exit."


def _trade(tid="u1", ticker="AAPL", **kw):
    t = {"id": tid, "ticker": ticker, "strategy": "RSI", "direction": "bullish", "status": "loss",
         "entry": 100.0, "stop_loss": 96.0, "take_profit": 108.0, "exit_price": 96.0,
         "opened_at": f"{DAY}T15:02:00+00:00", "closed_at": f"{DAY}T15:31:00+00:00"}
    t.update(kw)
    return t


def _entry(tid="u1", ticker="AAPL", **kw):
    e = {"trade_id": tid, "ticker": ticker, "strategy": "RSI", "outcome": "loss",
         "r_realized": -1.0, "mfe_r": 1.24, "mae_r": 1.1, "exit_efficiency": -0.8065,
         "excursion_source": "daily", "tags": ["near_miss_tp"],
         "auto_lesson": "Trade went 1.2R in favor before stopping out — exit management, not entry, cost this one.",
         "note": "partner note", "holding_days": 0.02,
         "opened_at": f"{DAY}T15:02:00+00:00", "closed_at": f"{DAY}T15:31:00+00:00"}
    e.update(kw)
    return e


def _archive(base, folder, stem="AAPL", start=f"{DAY} 14:30", end=f"{DAY} 20:55",
             freq="5min", drop=()):
    idx = pd.date_range(start, end, freq=freq, tz="UTC", name="Datetime")
    df = pd.DataFrame({"Close": 100.0, "High": 100.5, "Low": 99.5, "Open": 100.0,
                       "Volume": 1000.0}, index=idx)
    if len(drop):
        df = df.drop(pd.DatetimeIndex(drop).tz_localize("UTC"))
    (base / folder).mkdir(parents=True, exist_ok=True)
    df.to_csv(base / folder / f"{stem}.csv")


@pytest.fixture
def book(monkeypatch):
    trades: dict[str, dict] = {}
    monkeypatch.setattr(eu, "_trades_by_id", lambda: dict(trades))
    return trades


def test_a_daily_entry_is_upgraded_to_5min_and_keeps_the_note(tmp_path, book):
    JournalStore().add(_entry())
    book["u1"] = _trade()
    _archive(tmp_path, "5min")
    report = upgrade_excursions(None, base_dir=str(tmp_path))
    stored = JournalStore().get("u1")
    assert (stored["excursion_source"], stored["mfe_r"], stored["mae_r"]) == ("5min", 0.125, 1.0)
    assert stored["exit_efficiency"] == -5.0
    assert stored["note"] == "partner note"
    assert "near_miss_tp" not in stored["tags"]
    assert stored["auto_lesson"] == RULE3
    assert (stored["r_realized"], stored["outcome"], stored["holding_days"]) == (-1.0, "loss", 0.02)
    assert report.read == 1 and report.upgraded["5min"] == 1


def test_a_second_run_is_idempotent(tmp_path, book):
    JournalStore().add(_entry())
    book["u1"] = _trade()
    _archive(tmp_path, "5min")
    upgrade_excursions(None, base_dir=str(tmp_path))
    again = upgrade_excursions(None, base_dir=str(tmp_path))
    assert again.read == 0 and sum(again.upgraded.values()) == 0


def test_never_downgrades_and_an_unchanged_entry_is_not_written(tmp_path, book):
    JournalStore().add(_entry(excursion_source="15min", mfe_r=0.4))
    book["u1"] = _trade()
    _archive(tmp_path, "hourly", freq="60min", end=f"{DAY} 20:30")
    report = upgrade_excursions(None, base_dir=str(tmp_path))
    stored = JournalStore().get("u1")
    assert (stored["excursion_source"], stored["mfe_r"]) == ("15min", 0.4)
    assert report.no_file == 1 and sum(report.upgraded.values()) == 0


def test_every_skip_is_counted_apart(tmp_path, book):
    for tid, ticker in (("nf", "AAPL"), ("nt", "AMD"), ("ni", "IBM"), ("ur", "MSFT"),
                        ("dn", "NVDA"), ("nc", "TSLA")):
        JournalStore().add(_entry(tid, ticker))
    book.update({"nf": _trade("nf"), "ni": _trade("ni", "IBM", stop_loss=None),
                 "ur": _trade("ur", "MSFT"), "dn": _trade("dn", "NVDA"), "nc": _trade("nc", "TSLA")})
    (tmp_path / "5min").mkdir()
    (tmp_path / "5min" / "MSFT.csv").write_text("Datetime,Close\nnot-a-date,1\n", encoding="utf-8")
    _archive(tmp_path, "5min", "NVDA", drop=pd.date_range(f"{DAY} 15:05", f"{DAY} 15:20", freq="5min"))
    _archive(tmp_path, "5min", "TSLA", start=f"{DAY} 15:10")
    r = upgrade_excursions(None, base_dir=str(tmp_path))
    assert (r.read, r.no_file, r.no_trade, r.no_inputs, r.unreadable, r.density, r.no_coverage) == (
        6, 1, 1, 1, 1, 1, 1)


def test_a_coarser_write_after_a_finer_one_counts_lost_race(tmp_path, book):
    JournalStore().add(_entry(excursion_source="5min", mfe_r=0.2))
    stale = _entry(excursion_source="daily")          # what the pass read before the backfill wrote
    _archive(tmp_path, "15min", freq="15min", end=f"{DAY} 20:45")
    report = UpgradeReport()
    assert upgrade_ticker("AAPL", [(stale, _trade())], report, base_dir=str(tmp_path)) is True
    assert report.lost_race == 1 and report.upgraded["15min"] == 0
    stored = JournalStore().get("u1")
    assert (stored["excursion_source"], stored["mfe_r"]) == ("5min", 0.2)


def test_a_null_source_without_mfe_can_reach_daily(tmp_path, book):
    JournalStore().add(_entry(excursion_source=None, mfe_r=None, mae_r=None, exit_efficiency=None))
    book["u1"] = _trade()
    _archive(tmp_path, "daily", start=DAY, end=DAY, freq="1D")
    report = upgrade_excursions(None, base_dir=str(tmp_path))
    assert report.upgraded["daily"] == 1
    assert JournalStore().get("u1")["excursion_source"] == "daily"


def test_the_budget_stops_before_the_next_ticker(tmp_path, book):
    report = UpgradeReport()
    assert upgrade_ticker("AAPL", [(_entry(), _trade())], report, base_dir=str(tmp_path),
                          deadline=time.monotonic() - 1) is False
    assert report.budget_hit is True and report.read == 0
    JournalStore().add(_entry())
    book["u1"] = _trade()
    assert upgrade_excursions(None, budget_seconds=-1, base_dir=str(tmp_path)).budget_hit is True


def test_pending_by_ticker_filters_window_and_rank(book):
    store = JournalStore()
    store.add(_entry("fine", excursion_source="5min"))
    store.add(_entry("in", "MSFT", closed_at="2026-11-12T15:31:00+00:00"))
    store.add(_entry("late", closed_at="2026-11-14T15:31:00+00:00"))
    store.add(_entry("early", closed_at="2026-11-01T15:31:00+00:00"))
    book["in"] = _trade("in", "MSFT")
    pending = pending_by_ticker("2026-11-10T00:00:00+00:00", "2026-11-13T00:00:00+00:00")
    assert list(pending) == ["MSFT"]
    assert [(e["trade_id"], t["id"]) for e, t in pending["MSFT"]] == [("in", "in")]
    assert pending_by_ticker("2026-12-01T00:00:00+00:00") == {}


def test_report_line_dict_and_absorb():
    report = UpgradeReport()
    report.absorb({"read": 3, "no_trade": 1, "upgraded": {"5min": 2}})
    report.absorb({"read": 1, "lost_race": 1, "budget_hit": True})
    assert report.as_dict()["read"] == 4 and report.upgraded["5min"] == 2
    assert report.line() == (
        "excursion upgrade: read 4, upgraded 5min=2 15min=0 hourly=0 daily=0, no_trade 1, "
        "no_file 0, unreadable 0, no_coverage 0, density 0, no_inputs 0, lost_race 1, budget_hit yes")
    assert UpgradeReport().as_dict() == {
        "read": 0, "no_trade": 0, "no_file": 0, "unreadable": 0, "no_coverage": 0, "density": 0,
        "no_inputs": 0, "lost_race": 0,
        "upgraded": {"5min": 0, "15min": 0, "hourly": 0, "daily": 0}, "budget_hit": False}
```

By hand for the first test: entry 100, stop 96 (risk 4), bars 100.5/99.5, exit 96 → mfe 0.125, mae 1.0, efficiency −1 / 0.125 → −5.0; `near_miss_tp` needs mfe ≥ 0.8 × tp1_r (tp1 2R here) so it drops; lesson rule 3. The skip test: AAPL has no 5min file (`no_file`), AMD has no trade, IBM has no stop (`no_inputs`), MSFT's file is unusable, NVDA's 5min has a 25-minute hole inside the hold, TSLA's 5min starts after the fill.

- [ ] **Step 2: Run to see them fail**

Run: `python scripts/dev/testrun.py file tests/excursion/test_excursion_upgrade.py`
Expected: `ModuleNotFoundError: No module named 'swingbot.core.analytics.excursion_upgrade'`. A skip means the database is down — start it and re-run.

- [ ] **Step 3: Create `swingbot/core/analytics/excursion_upgrade.py`**

```python
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
```

`journal_repo` is imported at module level; importing it opens no connection.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/excursion/test_excursion_upgrade.py`
Expected: all pass.
Run: `python scripts/dev/testrun.py file tests/excursion/test_excursion_frames.py`
Expected: all pass.
Run: `python -m radon cc -s -n C swingbot/core/analytics/excursion_upgrade.py` → no output. `python scripts/dev/complexity_gate.py` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/analytics/excursion_upgrade.py tests/excursion/test_excursion_upgrade.py
git commit -m "feat(v228): upgrade_excursions -- finer-only conditional patch, trades joined by id, every skip counted

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
