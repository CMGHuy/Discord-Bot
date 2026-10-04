"""V119-10: the compression short's research measurement through the standard producer.

The knob COMPRESSION_SHORT_RESEARCH_MODE (off|broad|isolated) adds the masked strategy to
StrategyEngine inside its scoped ("bearish", "2w") research cell; each mode is its own
cohort. Supplemental per-signal diagnostics (signal date, entry date, mode, exit reason,
exclusion totals) stay off the stamped ArmTrade rows, whose schema has neither field.

The world is the V119-9 one (tests/backtesting/test_compression_reachability.py) re-dated
into the Stage -1 pilot window, so the stamped blob is a genuine pilot-stage blob:
  the stock compresses, releases bearish on SIGNAL_DAY (a Friday), the resting sell-stop
  fills on the next bar, neither stop nor target prints, and the tenth session closes it.
"""
import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import compression_research as cr
from swingbot.core.backtesting.arms import reachability
from swingbot.core.backtesting.arms.knobs import parse_knob
from swingbot.core.backtesting.arms.strategy_engine import CompressionResearchContext
from swingbot.core.market import levels as levels_mod
from swingbot.core.market.events import EarningsSnapshot
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import COMPRESSION_SHORT, STRATEGY_GATES
from tests.backtesting import test_compression_reachability as world
from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
import measure_arms as ma  # noqa: E402

KNOB = "COMPRESSION_SHORT_RESEARCH_MODE"
SIGNAL_POS = len(world.STOCK) - 1
SIGNAL_DAY = dt.date(2019, 3, 1)
_INDEX = pd.bdate_range(end=pd.Timestamp(SIGNAL_DAY), periods=SIGNAL_POS + 1).append(
    pd.bdate_range(start=pd.Timestamp(SIGNAL_DAY) + pd.offsets.BDay(1),
                   periods=len(world.FULL_PATH) - SIGNAL_POS - 1))
WINDOW = ("2018-06-01", "2020-12-31")          # the Stage -1 pilot window, unchanged


def _redate(frame):
    out = frame.copy()
    out.index = _INDEX[:len(frame)]
    return out


FULL_PATH = _redate(world.FULL_PATH)
FILL_DAY = FULL_PATH.index[SIGNAL_POS + 1].date()
TENTH_BAR = FULL_PATH.index[SIGNAL_POS + 10].date()


def _series(step, level=300.0, n=260):
    start = (pd.Timestamp(SIGNAL_DAY) - pd.offsets.BDay(n - 1)).date().isoformat()
    return make_ohlcv([level + step * i for i in range(n)], start=start)


FALLING_SPY, RISING_SPY, SECTOR = _series(-0.5), _series(0.5), _series(1.0, level=100.0)


def _clear(ticker, decided_at):
    return EarningsSnapshot(observed_at=decided_at, reports=(), query_ok=True, source="test")


def _context(*, spy=FALLING_SPY, snapshot_of=_clear, member_on=None, sector_on=None):
    return CompressionResearchContext(spy=spy, sector_of=lambda ticker: SECTOR, snapshot_of=snapshot_of,
                                      member_on=member_on, sector_on=sector_on)


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    for name in ("LEVEL_LIFECYCLE_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                 "REGIME_GATES_ENABLED", "DATA_DRIVEN_STOPS_ENABLED"):
        monkeypatch.setattr(config, name, False, raising=False)
    monkeypatch.setattr(levels_mod, "build_level_map",
                        lambda *a, **k: ([Level(price=world.TARGET, sources=["Swing low", "Pivot low"])], []))


def _measure(mode="broad", frames=None, context=None, horizons=("2w",)):
    return cr.measure_compression_short(frames or {"ABC": FULL_PATH}, WINDOW, mode=mode,
                                        context=context or _context(), horizons=horizons)


# -- the knob ------------------------------------------------------------------------------------------

def test_knob_is_a_research_select_defaulting_off():
    field = next(f for f in config.FIELDS if f.attr == KNOB)
    assert field.default == "off" and [v for v, _ in field.options] == ["off", "broad", "isolated"]
    assert config.COMPRESSION_SHORT_RESEARCH_MODE == "off"
    assert parse_knob(f"{KNOB}=isolated") == (KNOB, "isolated")
    with pytest.raises(ValueError):
        parse_knob(f"{KNOB}=sideways")


def test_knob_is_reachable_through_the_strategy_engine_only():
    reach = reachability.REGISTRY[KNOB]
    assert reach.cls == reachability.REACHABLE
    assert reach.observed_by == frozenset({"strategy"})


# -- the measured cohort ----------------------------------------------------------------------------------

def test_one_mode_cohort_with_supplemental_diagnostics_off_the_stamped_rows():
    def snapshot_of(ticker, decided_at):
        return _clear(ticker, decided_at) if ticker == "ABC" else None     # XYZ: no as-of archive

    measured = _measure(frames={"ABC": FULL_PATH, "XYZ": FULL_PATH}, context=_context(snapshot_of=snapshot_of))
    assert measured.mode in {"broad", "isolated"} and measured.mode == "broad"
    assert all(row["entry_date"] > row["signal_date"] for row in measured.signal_diagnostics)
    assert measured.diagnostics["earnings_unknown"] == 1
    assert measured.exit_reasons["time_exit"] == 1
    (row,) = measured.signal_diagnostics
    assert row["ticker"] == "ABC" and row["mode"] == "broad"
    assert row["signal_date"] == SIGNAL_DAY.isoformat() and row["entry_date"] == FILL_DAY.isoformat()
    assert row["exit_date"] == TENTH_BAR.isoformat() and row["hold_sessions"] == 10
    assert row["price_basis"] == measured.close_price_basis == "daily_close_proxy"
    (trade,) = measured.trades
    assert isinstance(trade, ArmTrade) and trade.strategy == COMPRESSION_SHORT and trade.horizon_key == "2w"
    names = {f.name for f in dataclasses.fields(ArmTrade)}
    assert not names & {"mode", "signal_date", "exit_reason"}       # the stamped schema is unchanged


def test_the_target_is_lower_support_only_never_a_synthetic_one(monkeypatch):
    (row,) = _measure().signal_diagnostics
    assert row["tp1"] == world.TARGET
    monkeypatch.setattr(levels_mod, "build_level_map", lambda *a, **k: ([], []))
    measured = _measure()
    assert measured.trades == [] and measured.diagnostics == {"no_support": 1}


def test_per_mode_exclusion_totals_split_the_two_cohorts():
    broad, isolated = _measure("broad"), _measure("isolated")           # SPY falling: a broad candidate
    assert len(broad.trades) == 1 and broad.diagnostics == {}
    assert isolated.trades == [] and isolated.diagnostics == {"mode_not_allowed": 1}
    rising = _context(spy=RISING_SPY)                                     # SPY rising, stock lags: isolated
    assert len(_measure("isolated", context=rising).trades) == 1
    assert _measure("broad", context=rising).diagnostics == {"mode_not_allowed": 1}


def test_off_is_not_a_measurable_cohort():
    with pytest.raises(ValueError):
        _measure("off")


def test_only_the_bearish_2w_research_cell_is_opened(monkeypatch):
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.market import entry_filters
    from swingbot.core.market.strategy_types import admits
    seen, real = {}, entry_filters.entries_for

    def spy_on_mask(strategy, df, horizon_key, *a, **k):
        seen[horizon_key] = {d for d in ("bullish", "bearish") if admits(COMPRESSION_SHORT, d, horizon_key)}
        return real(strategy, df, horizon_key, *a, **k)

    monkeypatch.setattr(entry_filters, "entries_for", spy_on_mask)
    engine = StrategyEngine((COMPRESSION_SHORT,), compression_context=_context())
    for horizon in ("1w", "2w", "4w", "3m", "1y"):
        engine._entries(FULL_PATH, COMPRESSION_SHORT, horizon)
    assert seen == {"1w": set(), "2w": {"bearish"}, "4w": set(), "3m": set(), "1y": set()}
    assert [t.horizon_key for t in _measure(horizons=("2w", "4w", "3m")).trades] == ["2w"]
    assert STRATEGY_GATES[COMPRESSION_SHORT] == {"directions": ()}       # the live mask is untouched


def test_a_snapshot_observed_after_the_decision_is_never_known():
    def later(ticker, decided_at):
        return _clear(ticker, decided_at + dt.timedelta(hours=1))
    measured = _measure(context=_context(snapshot_of=later))
    assert measured.trades == [] and measured.diagnostics == {"earnings_stale": 1}


# -- point-in-time membership and sector -------------------------------------------------------------------

def test_a_non_member_on_the_signal_date_is_excluded_by_name():
    measured = _measure(context=_context(member_on=lambda ticker, day: day < dt.date(2019, 2, 1)))
    assert measured.trades == [] and measured.diagnostics == {"not_pit_member": 1}


def test_the_isolated_arm_reads_the_sector_mapped_on_the_signal_date():
    unmapped = _context(spy=RISING_SPY, sector_on=lambda ticker, day: None)
    measured = _measure("isolated", context=unmapped)
    assert measured.trades == [] and measured.diagnostics == {"missing_sector": 1}
    dated = _context(spy=RISING_SPY, sector_on=lambda ticker, day: SECTOR if day == SIGNAL_DAY else None)
    assert len(_measure("isolated", context=dated).trades) == 1


@pytest.fixture
def universe_dir(tmp_path, monkeypatch):
    from swingbot.core.marketdata import universe
    (tmp_path / "sp500_membership.csv").write_text(
        "ticker,start_date,end_date\nABC,2010-01-04,2019-02-01\nXYZ,2010-01-04,\n", encoding="utf-8")
    (tmp_path / "sp500_sector_history.csv").write_text(
        "ticker,start_date,end_date,sector\nXYZ,2010-01-04,2019-01-15,Energy\n"
        "XYZ,2019-01-15,,Information Technology\n", encoding="utf-8")
    (tmp_path / "etfs.json").write_text(json.dumps([
        {"symbol": "XLE", "name": "Energy", "sector": "Energy", "etf": True},
        {"symbol": "XLK", "name": "Tech", "sector": "Information Technology", "etf": True}]), encoding="utf-8")
    monkeypatch.setattr(universe, "UNIVERSE_DIR", str(tmp_path))
    frames = {"SPY": FALLING_SPY, "XLE": SECTOR.iloc[:-5], "XLK": SECTOR}
    monkeypatch.setattr(cr, "_cached_frame", lambda symbol: frames.get(symbol))
    cr.clear_offline_caches()
    yield tmp_path
    cr.clear_offline_caches()


def test_offline_context_reads_dated_membership_and_dated_sector(universe_dir):
    context = cr.offline_context()
    assert context.is_member("XYZ", SIGNAL_DAY) and not context.is_member("ABC", SIGNAL_DAY)
    assert context.is_member("ABC", dt.date(2019, 1, 31))
    assert not context.is_member("QQQ", SIGNAL_DAY)                        # never a member: excluded, not assumed
    assert len(context.sector_for("XYZ", dt.date(2019, 1, 10))) == len(SECTOR) - 5     # Energy then
    assert len(context.sector_for("XYZ", SIGNAL_DAY)) == len(SECTOR)                    # Technology now
    assert context.sector_for("ABC", SIGNAL_DAY) is None


def test_offline_context_never_backfills_earnings_from_final_report_dates(universe_dir):
    """No as-of snapshot archive exists; final report dates (market_data/earnings) are not what was
    known on the signal date, so every lookup is None and the candidate is excluded earnings_unknown."""
    context = cr.offline_context()
    decided = dt.datetime(2019, 3, 1, 22, tzinfo=dt.timezone.utc)
    assert context.snapshot_of("AAPL", decided) is None and context.snapshot_of("XYZ", decided) is None
    measured = _measure(context=dataclasses.replace(context, member_on=None, sector_on=None))
    assert measured.trades == [] and measured.diagnostics == {"earnings_unknown": 1}


def test_offline_context_without_a_sector_history_rejects_isolated_with_a_reason(universe_dir):
    (universe_dir / "sp500_sector_history.csv").unlink()
    cr.clear_offline_caches()
    assert cr.offline_context().sector_for("XYZ", SIGNAL_DAY) is None


# -- Stage -1 through the standard producer ------------------------------------------------------------

@pytest.fixture
def producer(monkeypatch):
    monkeypatch.setattr(ma, "load_frame", lambda ticker: {"ABC": FULL_PATH}.get(ticker))
    monkeypatch.setattr(cr, "offline_context", lambda: _context())


def test_stamped_strategy_engine_knob_changes_outcomes_on_the_pilot_fixture(producer):
    blob = ma.produce("pilot", {KNOB: "broad"}, universe=["ABC"], horizons=("2w",),
                      engines=("strategy",), workers=1)
    stamp = blob["provenance"]
    assert stamp["stage"] == "pilot" and stamp["knob_delta"] == {KNOB: "broad"}
    assert stamp["engine_hash"]["baseline"] == stamp["engine_hash"]["component"]
    assert stamp["changed_outcomes"] == 1
    added = [row for row in blob["component"] if row not in blob["baseline"]]
    assert [(row["strategy"], row["direction"], row["horizon_key"]) for row in added] == \
        [(COMPRESSION_SHORT, "bearish", "2w")]
    assert all(row in blob["component"] for row in blob["baseline"])      # other strategies' rows untouched
    assert not any(row["strategy"] == COMPRESSION_SHORT for row in blob["baseline"])


def test_stage_minus_one_fixture_reads_reachable_in_validate_component(producer, tmp_path, capsys):
    import validate_component as vc
    arms = tmp_path / "v119-fixture-pilot.json"
    arms.write_text(json.dumps(ma.produce("pilot", {KNOB: "isolated"}, universe=["ABC"], horizons=("2w",),
                                          engines=("strategy",), workers=1)), encoding="utf-8")
    assert vc.main(["--stage", "reachability", "--arms", str(arms), "--title", "v119 fixture",
                    "--window", "fixture"]) == 1        # SPY falling: no isolated candidate -> zero-diff
    assert "refused:zero-diff" in capsys.readouterr().err
    arms.write_text(json.dumps(ma.produce("pilot", {KNOB: "broad"}, universe=["ABC"], horizons=("2w",),
                                          engines=("strategy",), workers=1)), encoding="utf-8")
    assert vc.main(["--stage", "reachability", "--arms", str(arms), "--title", "v119 fixture",
                    "--window", "fixture"]) == 0
    assert "REACHABLE" in capsys.readouterr().out
