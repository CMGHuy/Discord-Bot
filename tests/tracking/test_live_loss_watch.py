"""v164 D3: the live loss watch's both-ledger loader and its scheduled_jobs latch.

The latch tests use the real scheduled_repo(): the autouse _store_database
fixture (tests/conftest.py) gives each test a truncated Postgres database.
"""
import datetime as dt

from swingbot.core.analytics import calibration
from swingbot.core.db.repositories.scheduled import scheduled_repo
from swingbot.core.tracking import live_loss_watch as lw

FLAG_DAY = dt.date(2026, 10, 20)


def _row(horizon="4w", *, bound=-0.2, alert=True, source="confluence", strategy="ALL"):
    return {"source": source, "strategy": strategy, "horizon": horizon, "live_n": 25,
            "live_wr": 40.0, "live_expr": -0.3, "bound_upper": bound, "alert": alert,
            "registry_status": "WEAK", "registry_window_kind": "TRAIN",
            "registry_run_date": "2026-09-01", "registry_expr": -0.05}


def _trade(status, *, ledger="main", origin=None):
    trade = {"status": status, "ledger": ledger, "source": "confluence", "strategy": "MACD",
             "horizon_key": "4w", "opened_at": "2026-10-19T14:00:00+00:00",
             "closed_at": "2026-10-23T14:00:00+00:00", "direction": "bullish",
             "entry": 100.0, "stop_loss": 95.0, "exit_price": 96.0, "legs": []}
    if origin is not None:
        trade["origin"] = origin
    return trade


def _reg(horizon):
    return {"source": "confluence", "strategy": "ALL", "horizon": horizon, "status": "WEAK",
            "n": 300, "win_rate": 45.0, "expectancy_r": -0.05,
            "window": "2020-01-01..2023-12-31", "run_date": "2026-09-01"}


def test_latch_job_names_exact_and_pooled_rows():
    assert lw.latch_job(_row("4w")) == "live_loss_watch:confluence/ALL/4w"
    assert lw.latch_job(_row(None)) == "live_loss_watch:confluence/ALL/pooled"
    assert (lw.latch_job(_row(None, source="strategy", strategy="MACD"))
            == "live_loss_watch:strategy/MACD/pooled")


def test_latch_marks_reads_and_clears():
    row = _row()
    assert lw.is_latched(row) is False
    lw.mark_latched(row, FLAG_DAY)
    assert scheduled_repo().fired_on(lw.latch_job(row)) == "2026-10-20"
    assert lw.is_latched(row) is True

    recovered = _row(bound=0.0, alert=False)          # boundary: 0 counts as recovered
    assert lw.clear_latches([recovered]) == [lw.latch_job(row)]
    assert scheduled_repo().fired_on(lw.latch_job(row)) == lw.LATCH_CLEARED == "cleared"
    assert lw.is_latched(row) is False


def test_clear_latches_keeps_rows_still_below_zero_or_without_a_bound():
    below, unbounded = _row("2w", bound=-0.01), _row("3m", bound=None, alert=False)
    for row in (below, unbounded):
        lw.mark_latched(row, FLAG_DAY)
    assert lw.clear_latches([below, unbounded]) == []
    assert lw.is_latched(below) and lw.is_latched(unbounded)


def test_clear_latches_never_writes_an_unlatched_row():
    row = _row("5m", bound=0.4, alert=False)
    assert lw.clear_latches([row]) == []
    assert scheduled_repo().fired_on(lw.latch_job(row)) is None


def test_latch_namespace_leaves_the_daily_recap_job_alone():
    scheduled_repo().mark("daily_recap", "2026-10-20")
    lw.mark_latched(_row(), dt.date(2026, 10, 21))
    lw.clear_latches([_row(bound=0.5, alert=False)])
    assert scheduled_repo().fired_on("daily_recap") == "2026-10-20"


def test_load_watch_feeds_closed_trades_of_both_ledgers_only(monkeypatch):
    trades = [_trade("loss"), _trade("win", ledger="weak"), _trade("closed"),
              _trade("open"), _trade("loss", origin="next_session")]
    registry = [_reg("4w"), _reg(None)]
    seen = {}

    def fake_rule(trades_in, registry_in, *, n_resamples):
        seen.update(trades=trades_in, registry=registry_in, n=n_resamples)
        return {"rows": [], "counts": {}}

    monkeypatch.setattr(lw, "_all_trades", lambda: trades)
    monkeypatch.setattr(lw, "_registry_entries", lambda: registry)
    monkeypatch.setattr(lw.calibration, "live_loss_watch", fake_rule)

    assert lw.load_watch(n_resamples=300) == {"rows": [], "counts": {}}
    # main ledger first (loss, closed), then weak (win); open and outlook trades dropped
    assert [t["status"] for t in seen["trades"]] == ["loss", "closed", "win"]
    assert {t["ledger"] for t in seen["trades"]} == {"main", "weak"}
    assert seen["registry"] is registry
    assert seen["n"] == 300


def test_load_watch_default_resamples_is_the_pre_registered_constant(monkeypatch):
    seen = {}
    monkeypatch.setattr(lw, "_all_trades", lambda: [])
    monkeypatch.setattr(lw, "_registry_entries", lambda: [])
    def fake_rule(trades_in, registry_in, *, n_resamples):
        seen["n"] = n_resamples
        return {"rows": [], "counts": {}}

    monkeypatch.setattr(lw.calibration, "live_loss_watch", fake_rule)
    lw.load_watch()
    assert seen["n"] == calibration.EXPR_WATCH_RESAMPLES == 10_000


def test_load_watch_runs_the_real_rule_over_both_ledgers(monkeypatch):
    trades = [_trade("loss") for _ in range(3)] + [_trade("win", ledger="weak")]
    monkeypatch.setattr(lw, "_all_trades", lambda: trades)
    monkeypatch.setattr(lw, "_registry_entries", lambda: [_reg("4w"), _reg(None)])

    watch = lw.load_watch(n_resamples=200)

    rows = {row["horizon"]: row for row in watch["rows"]}
    assert rows["4w"]["live_n"] == 4          # main + weak ledger
    assert rows[None]["live_n"] == 4          # and the pooled row
    assert set(watch["counts"]) <= set(calibration.WATCH_COUNT_KEYS)
