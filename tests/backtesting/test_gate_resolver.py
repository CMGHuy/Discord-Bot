"""v147 V147-11: the nightly gate-rejection resolver core."""
import datetime as dt

import pytest

from swingbot.core.backtesting import gate_counterfactual as gc
from swingbot.core.backtesting import gate_resolver as gr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from tests.helpers import make_ohlcv

HOLD = int(HORIZONS["2w"]["max_holding_days"])
SIGNAL_DATE = "2024-01-04"              # index 2 of a frame starting 2024-01-02
LATE = "2024-12-31"                     # every walk window below has closed
RESOLVED_AT = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
FLAT = (100.2, 100.6, 99.8, 100.3)      # no stop, no TP1
WIN = (100.5, 103.0, 100.4, 102.5)      # TP1 (102) touched


def _plan(**kw):
    base = dict(plan_id="p1", ticker="AAPL", created_at=SIGNAL_DATE, source="confluence",
                strategy="Fibonacci", horizon_key="2w", direction="bullish", entry_type="market",
                trigger_price=100.0, entry_price=100.0, expiry_bars=3, stop_loss=95.0, tp1=102.0,
                tp1_fraction=0.5, tp2=105.0, breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return plan_to_dict(TradePlanV2(**base))


def _frame(after=(WIN,), *, n_after=HOLD + 5, scale=1.0, start="2024-01-02"):
    rows = [(100.0, 100.5, 99.5, 100.0)] * 3 + list(after)
    rows += [FLAT] * max(0, n_after - len(after))
    return make_ohlcv([tuple(x * scale for x in r) for r in rows], start=start)


def _row(row_id=1, **over):
    base = {"id": row_id, "ticker": "AAPL", "gate": "plan_rejected", "reason": "risk_cap",
            "source": "confluence", "strategy": "Fibonacci", "horizon": "2w",
            "direction": "bullish", "signal_date": SIGNAL_DATE, "cf_status": "pending",
            "plan": _plan(), "scenario": None, "scan_params": None, "signal_close": 100.0,
            "margin": 0.3}
    base.update(over)
    return base


class FakeRepo:
    def __init__(self, rows):
        self.rows = {r["id"]: r for r in rows}
        self.calls = []

    def pending(self, *, limit):
        return [dict(r) for r in self.rows.values() if r["cf_status"] == "pending"][:limit]

    def resolve(self, row_id, *, cf_status, resolved_at, outcome):
        row = self.rows[row_id]
        if row["cf_status"] != "pending":
            return False
        self.calls.append((row_id, cf_status))
        row.update(outcome, cf_status=cf_status, resolved_at=resolved_at)
        return True


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(gr, "_utc_now", lambda: RESOLVED_AT)


def _bars(frame, seen=None):
    def load(ticker):
        if seen is not None:
            seen.append(ticker)
        return frame
    return load


def test_frozen_constants():
    assert gr.RESOLVE_BATCH_CAP == 200 and gr.GRACE_SESSIONS == 5


def test_due_bars_is_the_pending_window_plus_the_hold():
    assert gr.due_bars("2w", None) == HOLD
    assert gr.due_bars("2w", 3) == HOLD + 3


def test_last_session_is_strictly_before_today():
    assert gr._last_session_before("2024-12-30") == dt.date(2024, 12, 27)    # Monday -> Friday
    assert gr._last_session_before("2024-12-26") == dt.date(2024, 12, 24)    # skips Christmas


def test_a_row_whose_window_is_open_is_untouched():
    seen, repo = [], FakeRepo([_row()])
    assert gr.resolve_due("2024-01-09", repo=repo, load_bars=_bars(_frame(), seen)) == {}
    assert repo.calls == [] and seen == []


def test_an_expired_row_resolves_once_with_a_reproducible_hash():
    frame, repo = _frame(), FakeRepo([_row()])
    assert gr.resolve_due(LATE, repo=repo, load_bars=_bars(frame)) == {"filled": 1}
    row = repo.rows[1]
    used = frame.iloc[:2 + gc.bars_needed(plan_from_dict(_plan())) + 1]
    assert row["cf_status"] == "filled" and row["win"] is True and row["cf_r"] > 0
    assert row["resolved_at"] == RESOLVED_AT and row["reanchored"] is False
    assert row["bars_sha256"] == gc.bars_sha256(used)
    assert row["last_bar_date"] == used.index[-1].date().isoformat()
    assert row["cf_plan"]["tp1"] == 102.0
    assert gr.resolve_due(LATE, repo=repo, load_bars=_bars(frame)) == {}     # never re-resolved
    assert repo.calls == [(1, "filled")]


def test_it_reads_the_live_cache_and_never_a_cold_fetch(monkeypatch):
    from swingbot.core.marketdata import data, data_store
    seen = []
    monkeypatch.setattr(data_store, "load_normalized",
                        lambda ticker, interval, **kw: seen.append((ticker, interval)) or _frame())
    monkeypatch.setattr(data, "get_daily_data_batch",
                        lambda *a, **k: pytest.fail("the resolver must never cold-fetch"))
    assert gr.resolve_due(LATE, repo=FakeRepo([_row()])) == {"filled": 1}
    assert seen == [("AAPL", "daily")]


SESSIONS = ["2024-12-03", "2024-12-04", "2024-12-05", "2024-12-06", "2024-12-09", "2024-12-10"]


def test_a_short_cache_stays_pending_through_the_grace_window_then_no_data():
    short, repo = _frame(after=(), n_after=3), FakeRepo([_row()])
    counts = [gr.resolve_due(today, repo=repo, load_bars=_bars(short)) for today in SESSIONS]
    assert counts == [{"pending": 1}] * 5 + [{"no-data": 1}]
    row = repo.rows[1]
    assert row["cf_status"] == "no-data" and row["pending_checks"] == 6
    assert row["resolved_at"] == RESOLVED_AT


def test_a_second_run_on_the_same_session_counts_no_extra_grace():
    short, repo = _frame(after=(), n_after=3), FakeRepo([_row()])
    assert gr.resolve_due(SESSIONS[0], repo=repo, load_bars=_bars(short)) == {"pending": 1}
    assert gr.resolve_due(SESSIONS[0], repo=repo, load_bars=_bars(short)) == {}
    assert repo.rows[1]["pending_checks"] == 1
    assert repo.rows[1]["pending_checked_on"] == "2024-12-02"


def test_a_missing_cache_file_waits_like_a_short_cache():
    repo = FakeRepo([_row()])
    assert gr.resolve_due(LATE, repo=repo, load_bars=lambda ticker: None) == {"pending": 1}
    assert repo.rows[1]["cf_status"] == "pending" and repo.rows[1]["pending_checks"] == 1


def test_a_missing_signal_bar_is_no_data_at_once():
    no_signal_bar = _frame(start="2024-01-05")
    assert gr.resolve_due(LATE, repo=FakeRepo([_row()]), load_bars=_bars(no_signal_bar)) == {
        "no-data": 1}


def test_the_batch_cap_bounds_one_night():
    repo = FakeRepo([_row(1), _row(2, ticker="MSFT"), _row(3, ticker="NVDA")])
    assert gr.resolve_due(LATE, limit=2, repo=repo, load_bars=_bars(_frame())) == {"filled": 2}
    assert [row_id for row_id, _ in repo.calls] == [1, 2]
    assert gr.resolve_due(LATE, limit=2, repo=repo, load_bars=_bars(_frame())) == {"filled": 1}


def test_one_failing_row_never_stops_the_batch():
    def load(ticker):
        if ticker == "BAD":
            raise OSError("unreadable cache file")
        return _frame()
    repo = FakeRepo([_row(1, ticker="BAD"), _row(2)])
    assert gr.resolve_due(LATE, repo=repo, load_bars=load) == {"error": 1, "filled": 1}
    assert repo.rows[1]["cf_status"] == "pending"


@pytest.mark.parametrize("scale, reanchored", [(0.5, True), (1.0, False)])
def test_an_intraday_write_is_reanchored_from_its_basis_bar(scale, reanchored):
    row = _row(signal_close=None, basis_date="2024-01-03", basis_close=100.0)
    repo = FakeRepo([row])
    assert gr.resolve_due(LATE, repo=repo, load_bars=_bars(_frame(scale=scale))) == {"filled": 1}
    resolved = repo.rows[1]
    assert resolved["reanchored"] is reanchored and resolved["win"] is True
    assert resolved["cf_plan"]["tp1"] == pytest.approx(102.0 * scale)


def test_against_the_real_repository():
    from swingbot.core.db.repositories.gate_rejections import gate_rejections_repo
    repo = gate_rejections_repo()
    record = {k: v for k, v in _row().items() if k != "id"}
    record.update(created_at=dt.datetime(2024, 1, 4, 21, 0, tzinfo=dt.timezone.utc),
                  resolved_at=None, entry_context={}, heat_before=None, heat_cap=None)
    assert repo.insert_ignore(record)
    assert gr.resolve_due(LATE, load_bars=_bars(_frame())) == {"filled": 1}
    (stored,) = repo.list_since()
    assert stored["cf_status"] == "filled" and stored["win"] is True
    assert stored["resolved_at"] == RESOLVED_AT
    assert gr.resolve_due(LATE, load_bars=_bars(_frame())) == {}
