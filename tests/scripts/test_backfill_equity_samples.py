"""v172: the equity backfill -- clamped day rows (V172-6); the CLI tests follow (V172-7)."""
from datetime import date, datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from scripts.data import backfill_equity_samples as bes
from swingbot.core.tracking import equity

START = Decimal("10000")
MON, TUE, WED = date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7)
TAG = "20261008T120000Z@bars-asof-2026-10-07"

# Long AAPL: entered Mon 10:00 NY, exited Wed 14:00 NY at 110 (+100).
AAPL = {"id": "a1", "ticker": "AAPL", "direction": "bullish", "status": "win",
        "entry": 100.0, "stop_loss": 95.0, "shares": 10.0, "exit_price": 110.0,
        "opened_at": "2026-10-05T14:00:00+00:00", "closed_at": "2026-10-07T18:00:00+00:00",
        "realized_pnl_amount": 100.0, "ledger": "main"}
# Short MSFT: entered Tue 11:00 NY, still open.
MSFT = {"id": "m1", "ticker": "MSFT", "direction": "bearish", "status": "open",
        "entry": 200.0, "stop_loss": 210.0, "shares": 5.0,
        "opened_at": "2026-10-06T15:00:00+00:00", "ledger": "main"}
TRADES = [AAPL, MSFT]


def _frame(bars):
    return pd.DataFrame([{"Open": o, "High": h, "Low": low, "Close": c}
                         for (o, h, low, c) in bars.values()],
                        index=pd.DatetimeIndex([pd.Timestamp(d) for d in bars]))


BARS = {
    "AAPL": _frame({MON: (99, 104, 98, 102), TUE: (102, 106, 101, 105), WED: (105, 112, 104, 111)}),
    "MSFT": _frame({TUE: (201, 203, 196, 198), WED: (198, 199, 194, 195)}),
}


def _rows(day, *, trades=TRADES, bars=BARS, allow_gaps=False):
    return bes.build_day_rows(day, bes.held_positions(trades, day), bars,
                              equity.realized_legs(trades), START, TAG, allow_gaps=allow_gaps)


def _kinds_and_equity(rows):
    return [(row["kind"], row["equity"]) for row in rows]


def test_session_bounds_are_new_york_open_and_close_in_utc():
    assert bes.session_bounds(MON) == (datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc),
                                       datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc))
    assert bes.session_bounds(date(2026, 12, 7)) == (       # EST, UTC-5
        datetime(2026, 12, 7, 14, 30, tzinfo=timezone.utc),
        datetime(2026, 12, 7, 21, 0, tzinfo=timezone.utc))


@pytest.mark.parametrize("day, expected", [
    # entry day of AAPL: path 100 -> 102; open contributes 0
    (MON, [("point", 10000), ("day_high", 10020), ("day_low", 10000), ("point", 10020)]),
    # AAPL full bar; MSFT entry day (short, path 200 -> 198)
    (TUE, [("point", 10020), ("day_high", 10070), ("day_low", 10010), ("point", 10060)]),
    # AAPL exit day (path 105 -> 110, net of the banked +100); MSFT full bar
    (WED, [("point", 10060), ("day_high", 10130), ("day_low", 10055), ("point", 10125)]),
])
def test_four_rows_a_day_with_clamped_extremes(day, expected):
    rows, skips = _rows(day)
    assert skips == []
    assert _kinds_and_equity(rows) == expected
    open_at, close_at = bes.session_bounds(day)
    assert [row["at"] for row in rows] == [open_at, open_at, open_at, close_at]
    assert {(row["source"], row["backfill_run"]) for row in rows} == {("backfill", TAG)}


def test_the_open_point_uses_yesterdays_realized_and_the_rest_todays():
    rows, _ = _rows(WED)
    assert [row["realized_balance"] for row in rows] == [10000, 10100, 10100, 10100]
    assert [row["unrealized_pnl"] for row in rows] == [60, 30, -45, 25]
    assert {(row["open_n"], row["skipped_n"]) for row in rows} == {(2, 0)}


def _pos(*, entry_day=MON, exit_day=None, exit_price=None, direction="bullish"):
    return {"trade_id": "x", "ticker": "X", "direction": direction, "entry": 100.0,
            "shares": 1.0, "entry_day": entry_day, "exit_day": exit_day, "exit_price": exit_price}


def test_entry_day_reads_no_bar_data_from_before_the_entry():
    bar = bes.Bar(open=50.0, high=999.0, low=1.0, close=101.0)
    assert bes.position_day(_pos(), bar, MON) == {
        "open_u": 0, "high_u": 1, "low_u": 0, "close_u": 1}


def test_exit_day_reads_no_bar_data_from_after_the_exit():
    bar = bes.Bar(open=102.0, high=999.0, low=1.0, close=50.0)
    assert bes.position_day(_pos(exit_day=WED, exit_price=105.0), bar, WED) == {
        "open_u": 2, "high_u": 0, "low_u": -3, "close_u": 0}


def test_a_same_day_round_trip_runs_entry_to_exit_only():
    bar = bes.Bar(open=90.0, high=999.0, low=1.0, close=80.0)
    assert bes.position_day(_pos(exit_day=MON, exit_price=103.0), bar, MON) == {
        "open_u": 0, "high_u": 0, "low_u": -3, "close_u": 0}


def test_a_short_on_a_full_day_favours_the_low():
    bar = bes.Bar(open=98.0, high=99.0, low=94.0, close=95.0)
    assert bes.position_day(_pos(entry_day=MON, direction="bearish"), bar, TUE) == {
        "open_u": 2, "high_u": 6, "low_u": 1, "close_u": 5}


def test_a_tp1_partial_is_two_slices_and_its_banked_leg_is_counted_once():
    leg = {"fraction": 0.5, "exit_price": 106.0, "r": 1.2, "reason": "tp1",
           "closed_at": "2026-10-06T16:00:00+00:00"}               # Tue 12:00 NY, at the bar high
    trade = {**AAPL, "id": "p1", "status": "open", "exit_price": None, "closed_at": None,
             "realized_pnl_amount": None, "legs": [leg]}
    held = bes.held_positions([trade], TUE)
    assert [(p["shares"], p["exit_day"], p["exit_price"]) for p in held] == [
        (5.0, TUE, 106.0), (5.0, None, None)]
    assert [(p["shares"], p["exit_day"]) for p in bes.held_positions([trade], WED)] == [(5.0, None)]
    rows, _ = _rows(TUE, trades=[trade])
    # Banked +30 at 106. Both halves at 106 is the reachable high: 10000 + 30 + 30 = 10060.
    # Adding the banked half's full pnl on top of realized(D) would read 10090.
    assert _kinds_and_equity(rows) == [
        ("point", 10020), ("day_high", 10060), ("day_low", 10015), ("point", 10055)]


def test_weak_and_outlook_trades_never_enter_a_day():
    weak = {**MSFT, "id": "w1", "ledger": "weak"}
    outlook = {**MSFT, "id": "o1", "origin": "next_session"}
    assert bes.held_positions([weak, outlook], TUE) == []


def test_filled_trades_drops_pending_placeholders_only():
    pending = {**MSFT, "id": "pp", "plan_id": "P1"}
    active = {**MSFT, "id": "pa", "plan_id": "P2"}
    closed = {**AAPL, "plan_id": "P3"}
    plans = {"P1": {"status": "PENDING"}, "P2": {"status": "ACTIVE"}, "P3": {"status": "CLOSED"}}
    kept = bes.filled_trades([pending, active, closed, MSFT], plans)
    assert [t["id"] for t in kept] == ["pa", "a1", "m1"]


def test_a_missing_bar_is_a_gap_refused_unless_allowed():
    bars = {"AAPL": BARS["AAPL"], "MSFT": _frame({TUE: (201, 203, 196, 198)})}
    with pytest.raises(bes.CoverageGap):
        _rows(WED, bars=bars)
    rows, skips = _rows(WED, bars=bars, allow_gaps=True)
    assert skips == [bes.Skip(WED, "m1", "MSFT", "no bar")]
    assert {(row["open_n"], row["skipped_n"]) for row in rows} == {(1, 1)}
    assert rows[-1]["equity"] == 10100                     # AAPL realized, MSFT left out


def test_a_ticker_with_no_frame_is_a_fetch_failure_gap():
    _, skips = _rows(WED, bars={"AAPL": BARS["AAPL"]}, allow_gaps=True)
    assert [s.reason for s in skips] == ["fetch failed"]


def test_an_unsized_position_is_skipped_but_is_not_a_gap():
    unsized = {**MSFT, "shares": None}
    rows, skips = _rows(WED, trades=[AAPL, unsized])          # allow_gaps=False: no raise
    assert skips == [bes.Skip(WED, "m1", "MSFT", "no size")]
    assert rows[0]["skipped_n"] == 1


def test_bar_for_matches_by_date_and_rejects_nan():
    frame = _frame({MON: (1, 2, 0.5, float("nan"))})
    assert bes.bar_for(frame, MON) is None
    assert bes.bar_for(BARS["AAPL"], MON) == bes.Bar(99.0, 104.0, 98.0, 102.0)
    assert bes.bar_for(BARS["AAPL"], date(2026, 10, 8)) is None
    assert bes.bar_for(None, MON) is None


# --- V172-7: the CLI -------------------------------------------------------------
from swingbot.core.db.repositories.equity_samples import EquitySampleRepository  # noqa: E402
from tests.store_seed import seed_store  # noqa: E402

TODAY = date(2026, 10, 8)            # Thursday, no live rows: days covered are Mon..Wed
RUN = "20261008T120000Z"


@pytest.fixture
def account():
    seed_store("account", {"base_balance": 10000.0, "balance": 10000.0, "risk_pct": 1.0,
                           "max_position_pct": 20.0, "sizing_mode": "risk_pct",
                           "balance_history": []})


@pytest.fixture
def repo():
    return EquitySampleRepository()


def _bars_fn(frames, calls):
    def fetch(ticker, start, end):
        calls.append((ticker, start, end))
        if ticker not in frames:
            raise OSError("HTTP 404")
        return frames[ticker].copy()
    return fetch


def _main(monkeypatch, argv, repo, tmp_path, *, frames=BARS, calls=None, run_id=RUN, trades=None):
    monkeypatch.setattr(bes, "new_run_id", lambda: run_id)
    return bes.main(argv, bars_fn=_bars_fn(frames, [] if calls is None else calls), repo=repo,
                    trades_fn=lambda: list(TRADES if trades is None else trades),
                    plans_fn=lambda: {}, today=TODAY, out_dir=tmp_path / run_id)


def _live(at, realized, unrealized):
    return {"at": at, "realized_balance": Decimal(str(realized)),
            "unrealized_pnl": Decimal(str(unrealized)),
            "equity": Decimal(str(realized)) + Decimal(str(unrealized)), "open_n": 1,
            "skipped_n": 0, "source": "live", "kind": "point", "backfill_run": None}


def test_dry_run_reports_coverage_and_writes_nothing(monkeypatch, repo, account, tmp_path, capsys):
    calls = []
    assert _main(monkeypatch, [], repo, tmp_path, calls=calls) == {
        "run_id": RUN, "bars_asof": "2026-10-07", "days": 3, "rows": 12, "written": 0,
        "gaps": 0, "skipped": 0, "recomputed": 0}
    assert repo.list_rows() == []
    out = capsys.readouterr().out
    for line in (f"run id: {RUN}", "bars as-of: 2026-10-07",
                 "days covered: 3 (2026-10-05..2026-10-07)", "DRY RUN: rows=12 gaps=0 skipped=0",
                 "Dry run only -- pass --apply to write."):
        assert line in out
    assert sorted(calls) == [("AAPL", MON, WED), ("MSFT", TUE, WED)]     # held days only
    assert (tmp_path / RUN / "AAPL.csv").exists() and (tmp_path / RUN / "MSFT.csv").exists()


def test_apply_writes_four_rows_a_day_and_a_rerun_writes_nothing_new(
        monkeypatch, repo, account, tmp_path):
    assert _main(monkeypatch, ["--apply"], repo, tmp_path)["written"] == 12
    rows = repo.list_rows(sources=("backfill",))
    assert {r["backfill_run"] for r in rows} == {f"{RUN}@bars-asof-2026-10-07"}
    assert sorted(r["equity"] for r in rows if bes.ny_day(r["at"]) == WED) == [
        10055.0, 10060.0, 10125.0, 10130.0]
    assert _main(monkeypatch, ["--apply"], repo, tmp_path, run_id="20261009T090000Z")["written"] == 0
    assert len(repo.list_rows()) == 12


def test_replace_rewrites_every_backfill_row_with_the_new_run(monkeypatch, repo, account, tmp_path):
    _main(monkeypatch, ["--apply"], repo, tmp_path)
    assert _main(monkeypatch, ["--apply", "--replace"], repo, tmp_path,
                 run_id="20261009T090000Z")["written"] == 12
    rows = repo.list_rows(sources=("backfill",))
    assert len(rows) == 12
    assert {r["backfill_run"] for r in rows} == {"20261009T090000Z@bars-asof-2026-10-07"}


def test_the_coverage_gate_refuses_a_gap_unless_allowed(monkeypatch, repo, account, tmp_path, capsys):
    short = {"AAPL": BARS["AAPL"], "MSFT": _frame({TUE: (201, 203, 196, 198)})}
    summary = _main(monkeypatch, ["--apply"], repo, tmp_path, frames=short)
    assert (summary["gaps"], summary["written"]) == (1, 0)
    assert repo.list_rows() == []
    assert "REFUSED: 1 coverage gap(s)" in capsys.readouterr().out
    assert _main(monkeypatch, ["--apply", "--allow-gaps"], repo, tmp_path, frames=short)["written"] == 12
    wed = [r for r in repo.list_rows() if bes.ny_day(r["at"]) == WED]
    assert {r["skipped_n"] for r in wed} == {1}


def test_a_failed_fetch_is_a_gap_and_is_reported(monkeypatch, repo, account, tmp_path, capsys):
    summary = _main(monkeypatch, [], repo, tmp_path, frames={"AAPL": BARS["AAPL"]})
    assert summary["gaps"] == 2                               # MSFT on Tue and on Wed
    out = capsys.readouterr().out
    assert "MSFT: fetch failed (HTTP 404)" in out
    assert "skipped 2026-10-06 MSFT trade m1: fetch failed" in out


def test_days_stop_at_the_session_before_the_first_live_sample(monkeypatch, repo, account, tmp_path):
    repo.insert_sample(_live(datetime(2026, 10, 7, 14, 0, tzinfo=timezone.utc), 10000, 0))
    assert _main(monkeypatch, [], repo, tmp_path)["days"] == 2   # Mon, Tue


def test_fetch_raw_bars_asks_yfinance_for_unadjusted_daily_bars(monkeypatch):
    seen = {}

    def fake_download(ticker, **kwargs):
        seen.update(ticker=ticker, **kwargs)
        frame = BARS["AAPL"].copy()
        frame.columns = pd.MultiIndex.from_product([frame.columns, [ticker]])
        frame[("Adj Close", ticker)] = 1.0
        return frame

    monkeypatch.setattr(bes.yf, "download", fake_download)
    frame = bes.fetch_raw_bars("AAPL", MON, WED)
    assert seen["auto_adjust"] is False
    assert (seen["ticker"], seen["interval"], seen["progress"]) == ("AAPL", "1d", False)
    assert (seen["start"], seen["end"]) == ("2026-10-05", "2026-10-08")  # yfinance's end is exclusive
    assert list(frame.columns) == ["Open", "High", "Low", "Close"]


def test_recompute_realized_rewrites_only_the_realized_columns_of_live_rows(
        monkeypatch, repo, account, tmp_path):
    at = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
    repo.insert_sample(_live(at, 9000.0, 25.0))                       # stale: AAPL's +100 missing
    repo.upsert_many([{**_live(at, 1.0, 0.0), "source": "backfill", "backfill_run": "old@bars-asof-x"}])
    assert _main(monkeypatch, ["--recompute-realized"], repo, tmp_path)["recomputed"] == 1
    assert repo.list_rows(sources=("live",))[0]["realized_balance"] == 9000.0   # dry run
    assert _main(monkeypatch, ["--recompute-realized", "--apply"], repo, tmp_path)["recomputed"] == 1
    (live,) = repo.list_rows(sources=("live",))
    assert (live["realized_balance"], live["unrealized_pnl"], live["equity"]) == (10100.0, 25.0, 10125.0)
    (old,) = repo.list_rows(sources=("backfill",))
    assert old["realized_balance"] == 1.0
    assert _main(monkeypatch, ["--recompute-realized", "--apply"], repo, tmp_path)["recomputed"] == 0


def test_a_pending_placeholder_is_never_fetched_or_written(monkeypatch, repo, account, tmp_path):
    pending = {**MSFT, "id": "p1", "ticker": "NVDA", "status": "PENDING"}
    calls = []
    summary = _main(monkeypatch, ["--apply"], repo, tmp_path, calls=calls,
                    trades=[AAPL, MSFT, pending], frames={**BARS})
    assert summary["written"] == 12 and summary["gaps"] == 0
    assert "NVDA" not in {c[0] for c in calls}
