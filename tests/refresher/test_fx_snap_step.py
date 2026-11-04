"""v205 L1-a: the refresher's FX snap step runs every cycle and never fails one."""
from datetime import date, datetime, timezone

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import fx, fx_snap
from swingbot.refresher import loop, quotes
from swingbot.refresher.symbols import SymbolSet
from tests.marketdata.test_fx_snap import FRAME, FakeCodes, FakeDaily

UTC = timezone.utc


def _ctx(now):
    return loop.CycleContext(now, "closed", SymbolSet((), ()), [], [], False,
                             loop.CycleReport("closed", 1800.0))


def test_the_step_snaps_at_the_cycles_own_now(monkeypatch):
    seen = []
    monkeypatch.setattr(quotes.fx_snap, "snap", lambda now: seen.append(now) or 0)
    ctx = _ctx(datetime(2026, 11, 4, 7, 0, tzinfo=UTC))
    quotes.fx_snap_step(ctx)
    assert seen == [ctx.now]


def test_a_failing_snap_is_swallowed_and_leaves_the_cycle_error_alone(monkeypatch):
    def missing_table(now):
        raise RuntimeError('relation "fx_daily_rates" does not exist')
    monkeypatch.setattr(quotes.fx_snap, "snap", missing_table)
    before = sw.snapshot().get("ops.refresher.fx_snap", {}).get("count", 0)
    ctx = _ctx(datetime(2026, 11, 4, 7, 0, tzinfo=UTC))
    quotes.fx_snap_step(ctx)
    assert ctx.report.error is None
    assert sw.snapshot()["ops.refresher.fx_snap"]["count"] == before + 1


def test_the_snap_step_follows_the_fx_step():
    assert loop.STEPS.index(quotes.fx_snap_step) == loop.STEPS.index(quotes.fx_step) + 1


def test_the_snap_runs_even_when_the_fx_step_returns_early(monkeypatch):
    seen = []

    def no_codes(*args, **kwargs):
        raise AssertionError("fx_step resolved codes on an empty cycle")
    monkeypatch.setattr(quotes.fx, "refresh_quote_codes", no_codes)
    monkeypatch.setattr(quotes.fx_snap, "snap", lambda now: seen.append(now) or 0)
    monkeypatch.setattr(loop, "STEPS", [quotes.fx_step, quotes.fx_snap_step])
    ctx = _ctx(datetime(2026, 11, 4, 7, 0, tzinfo=UTC))
    loop._run_steps(ctx)
    assert seen == [ctx.now] and ctx.report.error is None


def test_two_cycles_on_one_berlin_day_insert_the_row_once(monkeypatch):
    daily = FakeDaily()
    monkeypatch.setattr(fx_snap, "fx_daily_rate_repo", lambda: daily)
    monkeypatch.setattr(fx_snap, "quote_currency_repo", lambda: FakeCodes({"USD"}))
    monkeypatch.setattr(fx, "account_currency_code", lambda: "EUR")
    monkeypatch.setattr(fx, "_pair_frame", lambda pair, *, refresh=True: FRAME)
    quotes.fx_snap_step(_ctx(datetime(2026, 11, 4, 7, 5, tzinfo=UTC)))
    quotes.fx_snap_step(_ctx(datetime(2026, 11, 4, 7, 10, tzinfo=UTC)))
    assert [len(batch) for batch in daily.inserts] == [1, 0]
    assert daily.rows[("USD", "EUR", date(2026, 11, 4))]["snapped_at"] == datetime(
        2026, 11, 4, 7, 5, tzinfo=UTC)
