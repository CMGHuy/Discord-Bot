"""v200 Part 5.2: every autopsy cut says when its value is known -- entry, fill or outcome.

The audit records which BookRow attributes and bars keys each cut key reads on a fully
populated row, and derives the tag from them, so a new cut, or a key that starts reading an
outcome field, fails here instead of reaching the merge as known-at-entry evidence."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from autopsy import bars, cells, cuts, exits, report  # noqa: E402
from autopsy.rows import BookRow  # noqa: E402

SECTORS = {"AAA": "Technology"}
OUTCOME_FIELDS = frozenset({
    "exit_date", "exit_price", "close_reason", "outcome", "gross_r", "net_r", "mfe_r",
    "mae_r", "exit_efficiency", "holding_days", "bars.reversal", "bars.wider_stop_lost"})
# bars.gapped_through is read on the fill-day bar too, but the fill happens at that open
# (spec Part 5.2), so it is not a fill field. entry_date is known at the moment of entry.
FILL_FIELDS = frozenset({"bars.open_gap_pct", "bars.fill_day_open"})
CUT_NAMES = [name for name, _ in report._all_cuts(SECTORS)]


class _Bars(dict):
    def __init__(self, data: dict, seen: set):
        super().__init__(data)
        self._seen = seen

    def get(self, key, default=None):
        self._seen.add(f"bars.{key}")
        return super().get(key, default)

    def __getitem__(self, key):
        self._seen.add(f"bars.{key}")
        return super().__getitem__(key)


class _Recorder:
    """Delegates to a BookRow and records every attribute and bars key read."""

    def __init__(self, row: BookRow):
        self._row = row
        self.seen: set[str] = set()

    def __getattr__(self, name):
        if name == "bars":
            return _Bars(self._row.bars, self.seen)
        self.seen.add(name)
        return getattr(self._row, name)


def _full_row() -> BookRow:
    """Every field set, with values that walk each key past its early returns."""
    return BookRow(
        row_kind="trade", trade_id="t1", plan_id="p1", ticker="AAA", strategy="RSI",
        horizon="2w", direction="bullish", plan_date="2026-03-02", plan_hour=9,
        entry_type="limit", planned_entry=100.0, entry_date="2026-03-03", entry=100.0,
        stop=95.0, take_profit=110.0, exit_date="2026-03-12", exit_price=94.0,
        close_reason="loss", outcome="loss", gross_r=-1.2, net_r=-1.25, mfe_r=0.5,
        mae_r=-1.2, exit_efficiency=0.1, holding_days=7.0, stop_width_atr=1.5, atr_pct=2.0,
        days_to_earnings=10.0, regime2_state="bull_quiet", session_bucket="open",
        bars={"covered": True, "open_gap_pct": 0.5, "gapped_through": False,
              "dollar_volume": 3e7, "reversal": False, "wider_stop_lost": True})


def _expected(seen: set[str]) -> str:
    if seen & OUTCOME_FIELDS:
        return "outcome"
    return "fill" if seen & FILL_FIELDS else "entry"


def test_every_cut_has_one_known_tag_in_cut_order():
    tags = report.cut_defined_at(SECTORS)
    assert list(tags) == CUT_NAMES and len(CUT_NAMES) == 22
    assert cuts.DEFINED_AT_TAGS == ("entry", "fill", "outcome")
    assert set(tags.values()) <= set(cuts.DEFINED_AT_TAGS)


@pytest.mark.parametrize("name", CUT_NAMES)
def test_each_cut_tag_matches_the_fields_its_key_reads(name):
    key = dict(report._all_cuts(SECTORS))[name]
    recorder = _Recorder(_full_row())
    key(recorder)
    assert recorder.seen, name
    assert report.cut_defined_at(SECTORS)[name] == _expected(recorder.seen), \
        (name, sorted(recorder.seen))


def test_the_spec_named_cuts_carry_their_tags():
    tags = report.cut_defined_at(SECTORS)
    for name in ("exit_reason", "near_tp_close", "gap_through_stop", "holding_bucket",
                 "weekend_hold", "fomc_proximity", "near_stop_reversal"):
        assert tags[name] == "outcome", name
    assert tags["open_gap_bucket"] == "fill"
    assert tags["gapped_through_entry"] == "entry"
    assert sorted(n for n, t in tags.items() if t == "entry") == sorted((
        "strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday",
        "friday_entry", "earnings_proximity", "opex_week", "atr_pct_bucket", "session_bucket",
        "alert_hour", "gapped_through_entry", "dollar_volume_bucket"))


def test_an_untagged_cut_fails_loudly(monkeypatch):
    monkeypatch.setattr(exits, "EXIT_DEFINED_AT",
                        {k: v for k, v in exits.EXIT_DEFINED_AT.items() if k != "holding_bucket"})
    with pytest.raises(ValueError, match="holding_bucket"):
        report.cut_defined_at(SECTORS)


def test_an_unknown_tag_fails_loudly(monkeypatch):
    monkeypatch.setattr(bars, "BAR_DEFINED_AT", dict(bars.BAR_DEFINED_AT, open_gap_bucket="later"))
    with pytest.raises(ValueError, match="open_gap_bucket"):
        report.cut_defined_at(SECTORS)


def test_cell_json_carries_defined_at():
    cell = cells.CellStats(id="a=b", cut="a", value="b", n=1, weeks=1, win_rate=1.0,
                           net_expr=1.0, gross_expr=1.0, delta=None, ci=None, p=None, q=None,
                           thin=True)
    assert cell.to_json()["defined_at"] is None
    cell.defined_at = "fill"
    assert cell.to_json()["defined_at"] == "fill"


@pytest.mark.parametrize("tag, flagged", [
    ("outcome", True), ("fill", True), ("entry", False), (None, False)])
def test_the_notes_column_flags_cells_not_known_at_entry(tag, flagged):
    c = {"extra": {"tickers": 1, "top_ticker_share": 1.0}, "bar_covered_n": None, "notes": []}
    if tag is not None:
        c["defined_at"] = tag
    text = report._extra_text(c)
    assert (f"{tag}-defined (not known at entry)" in text) is flagged
    assert ("not known at entry" in text) is flagged
