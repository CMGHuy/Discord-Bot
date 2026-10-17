"""v164 live loss watch: the D1 matcher (LW1) and the D2 loss rule (LW2).

Pure functions, plain dict fixtures, no DB. Trade timestamps are UTC ISO like
`performance.log_trade` writes them; every day boundary is a Berlin date."""
import datetime as dt

import numpy as np
import pytest

from swingbot.core.analytics import calibration, metrics
from swingbot.core.analytics.calibration import (
    EXPR_WATCH_CONFIDENCE,
    EXPR_WATCH_LIVE_N_FLOOR,
    EXPR_WATCH_RESAMPLES,
    EXPR_WATCH_START,
    LIVE_LOSS_LOOKS_CAVEAT,
    LIVE_LOSS_MEANING,
    REGISTRY_CONTEXT_LABEL,
    WATCH_COUNT_KEYS,
    LiveTrade,
    MatchResult,
    badge_drift,
    berlin_entry_date,
    live_expr_bound,
    live_loss_row,
    live_loss_watch,
    loss_rule_trips,
    match_live_rows,
    order_live_loss_rows,
    registry_window_kind,
    row_key,
)

CONF_HORIZONS = ("2w", "4w", "2m")


def _reg(source, strategy, horizon, status="WEAK", expr=-0.2,
         window="2024-01-01..2025-12-31", run_date="2026-07-17"):
    return {"source": source, "strategy": strategy, "horizon": horizon, "status": status,
            "n": 400, "win_rate": 48.8, "expectancy_r": expr, "window": window,
            "run_date": run_date}


def _registry():
    rows = [_reg("confluence", "ALL", h) for h in CONF_HORIZONS]
    rows.append(_reg("confluence", "ALL", None))
    rows.append(_reg("strategy", "Fibonacci", None, status="VALIDATED", expr=0.105))
    return rows


def _trade(**over):
    """A closed, regular-lane, post-start confluence 4w win of +2R."""
    base = {"status": "win", "source": "confluence", "strategy": "S/R Confluence",
            "horizon_key": "4w", "opened_at": "2026-10-19T14:00:00+00:00",
            "closed_at": "2026-10-23T14:00:00+00:00", "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0, "legs": [],
            "ledger": "main"}
    base.update(over)
    return base


CONF_4W = ("confluence", "ALL", "4w")
CONF_POOLED = ("confluence", "ALL", None)
FIB_POOLED = ("strategy", "Fibonacci", None)


def _sizes(result: MatchResult) -> dict:
    return {key: len(bucket) for key, bucket in result.buckets.items()}


def _zero_counts() -> dict:
    return dict.fromkeys(WATCH_COUNT_KEYS, 0)


def test_start_date_is_the_pre_registered_constant():
    assert EXPR_WATCH_START == dt.date(2026, 10, 16)
    assert WATCH_COUNT_KEYS == ("no_source", "unknown_strategy", "no_r",
                                "manual_close", "no_entry_date")


def test_every_registry_row_gets_a_bucket_even_when_empty():
    result = match_live_rows([], _registry())
    assert set(result.buckets) == {row_key(e) for e in _registry()}
    assert all(bucket == [] for bucket in result.buckets.values())
    assert result.counts == _zero_counts()


def test_row_key_reads_source_strategy_horizon():
    assert row_key(_reg("confluence", "ALL", "4w")) == CONF_4W
    assert row_key(_reg("strategy", "Fibonacci", None)) == FIB_POOLED


def test_confluence_trade_feeds_its_horizon_row_and_the_pooled_row():
    result = match_live_rows([_trade()], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_4W] == 1
    assert sizes[CONF_POOLED] == 1
    assert sizes[("confluence", "ALL", "2w")] == 0
    assert result.counts == _zero_counts()


def test_confluence_is_matched_on_source_not_on_strategy_name():
    # builders.py:687 path: a confluence plan carries its primary strategy.
    result = match_live_rows([_trade(strategy="Fibonacci")], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_4W] == 1 and sizes[CONF_POOLED] == 1
    assert sizes[FIB_POOLED] == 0


def test_strategy_trade_feeds_the_pooled_row_only():
    result = match_live_rows([_trade(source="strategy", strategy="Fibonacci")], _registry())
    sizes = _sizes(result)
    assert sizes[FIB_POOLED] == 1
    assert sizes[CONF_4W] == 0 and sizes[CONF_POOLED] == 0


def test_one_week_confluence_trade_feeds_pooled_only_and_is_not_unmatched():
    result = match_live_rows([_trade(horizon_key="1w")], _registry())
    sizes = _sizes(result)
    assert sizes[CONF_POOLED] == 1
    assert sum(sizes.values()) == 1
    assert result.counts == _zero_counts()


def test_trade_without_horizon_key_is_appended_once():
    result = match_live_rows([_trade(horizon_key=None)], _registry())
    assert _sizes(result)[CONF_POOLED] == 1
    assert sum(_sizes(result).values()) == 1


def test_trade_entered_before_start_is_excluded_and_not_counted():
    # 21:00 UTC on 15 Oct is 23:00 Berlin on 15 Oct: before the start.
    result = match_live_rows([_trade(opened_at="2026-10-15T21:00:00+00:00")], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


def test_start_boundary_is_the_berlin_date_not_the_utc_date():
    # 22:30 UTC on 15 Oct is 00:30 Berlin on 16 Oct: on the start date.
    result = match_live_rows([_trade(opened_at="2026-10-15T22:30:00+00:00")], _registry())
    assert _sizes(result)[CONF_POOLED] == 1
    assert result.buckets[CONF_POOLED][0].entry_date == "2026-10-16"


def test_cohort_trade_is_excluded():
    result = match_live_rows([_trade(origin="next_session")], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


def test_weak_ledger_trade_is_included():
    result = match_live_rows([_trade(ledger="weak")], _registry())
    assert _sizes(result)[CONF_4W] == 1


def test_open_trade_is_not_in_the_population():
    result = match_live_rows([_trade(status="open", exit_price=None)], _registry())
    assert sum(_sizes(result).values()) == 0
    assert result.counts == _zero_counts()


@pytest.mark.parametrize("over, reason", [
    ({"source": None}, "no_source"),
    ({"source": ""}, "no_source"),
    ({"source": "strategy", "strategy": "Not In Registry"}, "unknown_strategy"),
    ({"source": "mystery"}, "unknown_strategy"),
    ({"exit_price": None}, "no_r"),
    ({"opened_at": None}, "no_entry_date"),
    ({"opened_at": "not a timestamp"}, "no_entry_date"),
])
def test_each_exclusion_is_counted_and_never_bucketed(over, reason):
    result = match_live_rows([_trade(**over)], _registry())
    assert sum(_sizes(result).values()) == 0
    expected = _zero_counts()
    expected[reason] = 1
    assert result.counts == expected


def test_missing_source_key_counts_as_no_source():
    trade = _trade()
    del trade["source"]
    result = match_live_rows([trade], _registry())
    assert result.counts["no_source"] == 1


def test_manual_close_is_included_and_counted():
    result = match_live_rows([_trade(status="closed", exit_price=101.0)], _registry())
    assert _sizes(result)[CONF_4W] == 1
    assert result.counts["manual_close"] == 1


def test_live_trade_carries_berlin_date_r_and_status():
    result = match_live_rows([_trade(status="loss", exit_price=96.0)], _registry())
    live = result.buckets[CONF_4W][0]
    assert isinstance(live, LiveTrade)
    assert live == LiveTrade("2026-10-19", -0.8, "loss")


def test_berlin_entry_date_handles_naive_z_and_garbage():
    assert berlin_entry_date({"opened_at": "2026-10-15T23:30:00"}) == "2026-10-16"  # naive = UTC
    assert berlin_entry_date({"opened_at": "2026-10-19T10:00:00Z"}) == "2026-10-19"
    assert berlin_entry_date({"opened_at": ""}) is None
    assert berlin_entry_date({}) is None
    assert berlin_entry_date({"opened_at": "garbage"}) is None


def test_calibration_does_not_import_the_retrospective():
    # retrospective.py:29 imports calibration; the reverse would be a cycle.
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(calibration))
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names]
    assert not any("retrospective" in name for name in imported)


# ---------------------------------------------------------------------------
# LW2: the D2 loss rule (pre-registered), ordering, goldens, null simulation
# ---------------------------------------------------------------------------
FAST = 500   # test-sized resamples; production stays EXPR_WATCH_RESAMPLES
ROW_KEYS = {"source", "strategy", "horizon", "live_n", "live_wr", "live_expr",
            "bound_upper", "alert", "registry_status", "registry_window_kind",
            "registry_run_date", "registry_expr"}
FIRST_MONDAY = dt.date(2026, 10, 19)


def _week(i: int) -> str:
    """Monday of the i-th ISO week from the first Monday after the start."""
    return (FIRST_MONDAY + dt.timedelta(weeks=i)).isoformat()


def _live(n, r, status=None, per_week=4):
    status = status or ("win" if r > 0 else "loss")
    return [LiveTrade(_week(i // per_week), r, status) for i in range(n)]


def test_rule_constants_are_the_pre_registered_values():
    assert EXPR_WATCH_LIVE_N_FLOOR == 20
    assert EXPR_WATCH_CONFIDENCE == 0.90
    assert EXPR_WATCH_RESAMPLES == 10_000
    assert LIVE_LOSS_MEANING == ('live ExpR for this row is below zero with ~90% one-sided '
                                 'confidence — not "the edge decayed versus its backtest"')
    assert LIVE_LOSS_LOOKS_CAVEAT == ("11 correlated looks per week; flags are prompts to "
                                      "investigate, not verdicts")
    assert REGISTRY_CONTEXT_LABEL == "backtest context — not comparable"


@pytest.mark.parametrize("window, kind", [
    ("2020-01-01..2023-12-31", "TRAIN"),
    ("2024-01-01..2025-12-31", "VALIDATION"),
    ("2019-01-01..2025-12-31", None),
    ("", None),
    (None, None),
])
def test_registry_window_kind_maps_exact_windows_only(window, kind):
    assert registry_window_kind(window) == kind


def test_bound_is_none_for_an_empty_population():
    assert live_expr_bound([], n_resamples=FAST) is None


def test_bound_is_identical_across_runs_and_input_order():
    rs = [-1.0, 0.0, 0.5, -1.0, 2.0, -1.0, 0.0, 1.0, -1.0, 3.0]
    live = [LiveTrade(_week(i % 6), r, "win" if r > 0 else "loss")
            for i, r in enumerate(rs * 3)]
    first = live_expr_bound(live, n_resamples=FAST)
    assert first is not None
    assert live_expr_bound(live, n_resamples=FAST) == first
    assert live_expr_bound(list(reversed(live)), n_resamples=FAST) == first
    assert live_expr_bound(sorted(live, key=lambda t: -t.r), n_resamples=FAST) == first


def test_same_week_trades_move_together():
    # Week A: five +1R, week B: five -1R. Whole weeks are resampled, so every
    # draw's mean is +1 (AA), 0 (AB) or -1 (BB); P(+1) = 0.25 puts the 90th
    # percentile at exactly +1. A per-trade bootstrap would land near +0.4.
    live = ([LiveTrade("2026-10-19", 1.0, "win")] * 5
            + [LiveTrade("2026-10-26", -1.0, "loss")] * 5)
    assert live_expr_bound(live, n_resamples=2000) == 1.0


@pytest.mark.parametrize("live_n, bound, trips", [
    (19, -0.5, False),
    (20, -0.5, True),
    (20, -1e-9, True),
    (20, 0.0, False),
    (20, 0.3, False),
    (100, None, False),
])
def test_rule_boundaries(live_n, bound, trips):
    assert loss_rule_trips(live_n, bound) is trips


def test_row_below_the_floor_never_alerts_even_when_every_trade_lost():
    row = live_loss_row(_reg("confluence", "ALL", "4w"), _live(19, -0.8), n_resamples=FAST)
    assert row["live_n"] == 19
    assert row["bound_upper"] == pytest.approx(-0.8)
    assert row["alert"] is False


def test_row_at_the_floor_alerts_when_bound_is_below_zero():
    row = live_loss_row(_reg("confluence", "ALL", "4w"), _live(20, -0.8), n_resamples=FAST)
    assert row["live_n"] == 20
    assert row["alert"] is True


def test_row_with_bound_exactly_zero_does_not_alert():
    row = live_loss_row(_reg("confluence", "ALL", "4w"), _live(40, 0.0, status="closed"),
                        n_resamples=FAST)
    assert row["bound_upper"] == 0.0
    assert row["alert"] is False


def test_row_shape_and_registry_context_columns():
    entry = _reg("strategy", "Fibonacci", None, status="VALIDATED", expr=0.105,
                 window="2020-01-01..2023-12-31", run_date="2026-05-01")
    live = _live(3, 2.0) + _live(1, -1.0)
    row = live_loss_row(entry, live, n_resamples=FAST)
    assert set(row) == ROW_KEYS
    assert (row["source"], row["strategy"], row["horizon"]) == ("strategy", "Fibonacci", None)
    assert row["live_n"] == 4
    assert row["live_wr"] == 75.0
    assert row["live_expr"] == pytest.approx(1.25)
    assert row["registry_status"] == "VALIDATED"
    assert row["registry_window_kind"] == "TRAIN"
    assert row["registry_run_date"] == "2026-05-01"
    assert row["registry_expr"] == 0.105


def test_empty_row_reports_n_zero_and_no_numbers():
    row = live_loss_row(_reg("strategy", "Fibonacci", None), [], n_resamples=FAST)
    assert row["live_n"] == 0
    assert row["live_wr"] is None and row["live_expr"] is None
    assert row["bound_upper"] is None and row["alert"] is False


def test_manual_closes_count_in_n_and_expr_but_not_in_win_rate():
    live = _live(2, 1.0) + _live(1, -1.0) + [LiveTrade(_week(0), 0.25, "closed")]
    row = live_loss_row(_reg("confluence", "ALL", None), live, n_resamples=FAST)
    assert row["live_n"] == 4
    assert row["live_wr"] == pytest.approx(200 / 3)
    assert row["live_expr"] == pytest.approx(1.25 / 4)


def _losing_trades(n, horizon_key):
    return [_trade(status="loss", exit_price=96.0, horizon_key=horizon_key,
                   opened_at=f"{_week(i // 4)}T14:00:00+00:00") for i in range(n)]


def test_watch_orders_alerts_then_confluence_by_horizon_then_strategies():
    registry = [_reg("confluence", "ALL", None), _reg("strategy", "RSI", None),
                _reg("confluence", "ALL", "2m"), _reg("strategy", "Fibonacci", None),
                _reg("confluence", "ALL", "4w"), _reg("confluence", "ALL", "2w")]
    watch = live_loss_watch(_losing_trades(20, "2m"), registry, n_resamples=FAST)
    keys = [(r["source"], r["strategy"], r["horizon"]) for r in watch["rows"]]
    assert keys == [
        ("confluence", "ALL", "2m"), ("confluence", "ALL", None),   # alerts
        ("confluence", "ALL", "2w"), ("confluence", "ALL", "4w"),
        ("strategy", "Fibonacci", None), ("strategy", "RSI", None),
    ]
    assert [r["alert"] for r in watch["rows"]] == [True, True, False, False, False, False]


def test_order_without_alerts_puts_pooled_last_among_confluence_rows():
    rows = [{"source": "confluence", "strategy": "ALL", "horizon": h, "alert": False}
            for h in (None, "9m", "1w", "2m")]
    ordered = order_live_loss_rows(rows)
    assert [r["horizon"] for r in ordered] == ["1w", "2m", "9m", None]


def test_watch_passes_counts_through_and_dedupes_registry_keys():
    registry = _registry() + [_reg("confluence", "ALL", "4w", status="VALIDATED")]
    trades = [_trade(), _trade(source=None), _trade(status="closed", exit_price=101.0)]
    watch = live_loss_watch(trades, registry, n_resamples=FAST)
    assert set(watch) == {"rows", "counts"}
    assert len(watch["rows"]) == len({row_key(e) for e in registry})
    four_week = next(r for r in watch["rows"] if r["horizon"] == "4w")
    assert four_week["registry_status"] == "WEAK"   # first occurrence wins
    assert four_week["live_n"] == 2
    assert watch["counts"] == {"no_source": 1, "unknown_strategy": 0, "no_r": 0,
                               "manual_close": 1, "no_entry_date": 0}


def test_watch_covers_every_row_of_the_committed_registry():
    from swingbot.core.backtesting.registry import load_registry
    entries = load_registry()
    watch = live_loss_watch([], entries, n_resamples=FAST)
    assert len(watch["rows"]) == len({row_key(e) for e in entries})
    assert all(r["live_n"] == 0 and r["alert"] is False for r in watch["rows"])
    confluence = [r for r in watch["rows"] if r["source"] == "confluence"]
    assert confluence and confluence[-1]["horizon"] is None


# --- goldens -----------------------------------------------------------------

def test_r_multiple_golden_with_legs():
    # Legged R is rounded to 2 dp by r_multiple; single-exit R is not.
    legged = {"entry": 100.0, "stop_loss": 97.0, "direction": "bullish",
              "legs": [{"fraction": 0.5, "r": 1.0}, {"fraction": 0.5, "exit_price": 101.0}]}
    single = {"entry": 100.0, "stop_loss": 97.0, "direction": "bullish", "exit_price": 101.0}
    bear = {"entry": 50.0, "stop_loss": 53.0, "direction": "bearish",
            "legs": [{"fraction": 0.5, "exit_price": 47.0}, {"fraction": 0.5, "exit_price": 52.0}]}
    assert metrics.r_multiple(legged) == 0.67
    assert metrics.r_multiple(single) == 0.3333333333333333
    assert metrics.r_multiple(bear) == 0.17


def test_watch_uses_r_multiple_exactly_as_written():
    legged = _trade(entry=100.0, stop_loss=97.0, exit_price=None,
                    legs=[{"fraction": 0.5, "r": 1.0}, {"fraction": 0.5, "exit_price": 101.0}])
    single = _trade(entry=100.0, stop_loss=97.0, exit_price=101.0)
    watch = live_loss_watch([legged, single], _registry(), n_resamples=FAST)
    pooled = next(r for r in watch["rows"] if r["horizon"] is None and r["source"] == "confluence")
    assert pooled["live_expr"] == (0.3333333333333333 + 0.67) / 2


def _drift_reg(strategy, wr, n=206, status="VALIDATED", run_date="2026-07-17"):
    return {"source": "strategy", "strategy": strategy, "horizon": None, "status": status,
            "n": n, "win_rate": wr, "expectancy_r": 0.105,
            "window": "2024-01-01..2025-12-31", "run_date": run_date}


def _drift_t(strategy, sources, status):
    return {"strategy": strategy, "target_sources": sources, "status": status,
            "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 104.0 if status == "win" else 96.0}


def test_badge_drift_golden_is_unchanged():
    registry = [_drift_reg("Fibonacci", 81.6), _drift_reg("Fibonacci", 70.0),
                _drift_reg("RSI", 60.0, status="WEAK"),
                _drift_reg("Volume Profile", 55.0, n=88, run_date="2026-08-01")]
    closed = ([_drift_t("S/R Confluence", ["Fib 61.8%"], "win") for _ in range(16)]
              + [_drift_t("S/R Confluence", ["Fib 61.8%"], "loss") for _ in range(9)]
              + [_drift_t("Volume Profile", [], "win") for _ in range(3)]
              + [_drift_t("Volume Profile", [], "loss")])
    assert badge_drift(closed, registry) == [
        {"strategy": "Fibonacci", "oos_n": 206, "oos_wr": 81.6, "oos_run_date": "2026-07-17",
         "live_n": 25, "live_wr": 64.0, "delta_wr": 64.0 - 81.6, "drift_alert": True},
        {"strategy": "Volume Profile", "oos_n": 88, "oos_wr": 55.0,
         "oos_run_date": "2026-08-01", "live_n": 4, "live_wr": 75.0, "delta_wr": 20.0,
         "drift_alert": False},
    ]


# --- operating characteristic (spec D2): null populations, true mean R 0 ------

NULL_R_VALUES = (-1.0, 0.0, 0.5, 1.0, 2.0, 3.0)        # -1R mass, BE scratch, right tail
NULL_R_PROBS = (0.43, 0.27, 0.10, 0.08, 0.06, 0.06)    # mean exactly 0
SIM_POPULATIONS = 400
SIM_RESAMPLES = 500        # test-sized; production stays EXPR_WATCH_RESAMPLES = 10_000
SIM_TRADES_PER_WEEK = 4
SIM_SEED = 164
#: Measured per-look false-flag rates (documented behaviour, spec D2). Above the
#: nominal 0.10: the percentile bootstrap under-covers at small skewed N. A
#: change here means the bound changed; it is not a number to tune.
NULL_FALSE_FLAG_RATES = {20: 0.165, 50: 0.1175, 100: 0.135}


def _null_population(rng, n):
    rs = rng.choice(NULL_R_VALUES, size=n, p=NULL_R_PROBS)
    return [LiveTrade(_week(i // SIM_TRADES_PER_WEEK), float(r), "win" if r > 0 else "loss")
            for i, r in enumerate(rs)]


def _false_flag_rate(n: int) -> float:
    rng = np.random.default_rng(SIM_SEED)
    flags = 0
    for _ in range(SIM_POPULATIONS):
        bound = live_expr_bound(_null_population(rng, n), n_resamples=SIM_RESAMPLES)
        flags += loss_rule_trips(n, bound)
    return flags / SIM_POPULATIONS


def test_null_distribution_has_mean_zero():
    assert sum(v * p for v, p in zip(NULL_R_VALUES, NULL_R_PROBS)) == pytest.approx(0.0, abs=1e-12)
    assert sum(NULL_R_PROBS) == pytest.approx(1.0)


@pytest.mark.slow
@pytest.mark.parametrize("n", [20, 50, 100])
def test_null_false_flag_rate_is_the_documented_behaviour(n):
    assert _false_flag_rate(n) == pytest.approx(NULL_FALSE_FLAG_RATES[n], abs=1e-9)
