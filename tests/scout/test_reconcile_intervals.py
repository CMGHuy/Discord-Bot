"""v232 V232-13: intervals, cells, confusion, distributions, tag means, populations, slip."""
import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import intervals, layer1, layer1_run, tags  # noqa: E402

FAST = {"n_resamples": 500, "seed": 42}
MONDAYS = ["2026-09-21", "2026-09-28", "2026-10-05", "2026-10-12"]


def _items(values, days):
    return [intervals.WeekItem(day, value) for value, day in zip(values, days)]


def _row(live="win", exit_only="loss", exit_effect=0.5, tags_=(), model="v1", scored=True):
    return layer1_run.TradeRow.from_dict({
        "plan_id": "P", "side": "long", "era": "headline",
        "klass": "closed" if scored else "manual", "entry_date": "2026-10-06",
        "live_class": live,
        "values": {model: {"exit_only_class": exit_only, "r_exit_only": 0.1}} if scored else {},
        "effects": {model: {"exit": exit_effect, "entry": 0.0}} if scored else {},
        "tags": list(tags_)})


def _full(**kw):
    base = {"plan_id": "P", "ticker": "AAA", "side": "long", "era": "headline", "klass": "closed",
            "entry_date": "2026-10-06", "ledger": "main", "r_live_net": 0.5,
            "values": {"v1": {}}, "effects": {"v1": {}}}
    return layer1_run.TradeRow.from_dict({**base, **kw})


def test_the_label_is_the_spec_text():
    assert intervals.INTERVAL_LABEL == "descriptive; under-covers below 20 clusters"


def test_one_arm_interval_brackets_the_mean_and_is_seeded():
    items = _items([1.0, 2.0, 3.0, 4.0], MONDAYS)
    low, high = intervals.one_arm_interval(items, **FAST)
    assert 1.0 <= low <= 2.5 <= high <= 4.0
    assert intervals.one_arm_interval(items, **FAST) == (low, high)


def test_one_arm_interval_needs_two_weeks():
    assert intervals.one_arm_interval(_items([1.0, 3.0], ["2026-09-21", "2026-09-23"]), **FAST) is None
    assert intervals.one_arm_interval([], **FAST) is None


def test_cell_stats_reads_n_weeks_total_share_and_thin():
    cell = intervals.cell_stats(_items([1.0, -0.5, 2.0], ["2026-09-21", "2026-09-22", "2026-09-28"]),
                                **FAST)
    assert (cell.n, cell.weeks, cell.total) == (3, 2, 2.5)
    assert cell.mean == pytest.approx(2.5 / 3)
    assert cell.largest_week_share == pytest.approx(0.8)       # |2.0| / (|0.5| + |2.0|)
    assert cell.thin is True and cell.interval is not None


def test_an_empty_cell_has_no_mean_share_or_interval():
    cell = intervals.cell_stats([], **FAST)
    assert (cell.n, cell.weeks, cell.total, cell.mean) == (0, 0, 0.0, None)
    assert (cell.largest_week_share, cell.interval, cell.thin) == (None, None, True)


def test_a_cell_without_interval_skips_the_bootstrap():
    cell = intervals.cell_stats(_items([1.0, 2.0], MONDAYS[:2]), with_interval=False, **FAST)
    assert cell.interval is None and cell.n == 2


def test_thin_follows_the_autopsy_rule():
    days = [(dt.date(2026, 8, 3) + dt.timedelta(weeks=i % 8)).isoformat() for i in range(30)]
    assert intervals.cell_stats(_items([0.1] * 30, days), **FAST).thin is False
    assert intervals.cell_stats(_items([0.1] * 29, days), **FAST).thin is True


def test_to_dict_rounds_and_lists_the_interval():
    out = intervals.cell_stats(_items([1.0, 2.0, 3.0, 4.0], MONDAYS), **FAST).to_dict()
    assert set(out) == {"n", "weeks", "total", "mean", "largest_week_share", "interval", "thin"}
    assert isinstance(out["interval"], list) and out["mean"] == 2.5


def test_confusion_is_live_against_exit_only_with_zero_cells():
    rows = [_row("win", "loss"), _row("win", "loss"), _row("loss", "loss"),
            _row("win", "loss", scored=False), _row("win", "win", model="v2")]
    grid = intervals.confusion(rows, "v1")
    assert set(grid) == set(layer1.OUTCOME_CLASSES)
    assert all(set(cols) == set(layer1.OUTCOME_CLASSES) for cols in grid.values())
    assert (grid["win"]["loss"], grid["loss"]["loss"]) == (2, 1)
    assert sum(sum(cols.values()) for cols in grid.values()) == 3


def test_distribution_reads_median_and_p90():
    assert intervals.distribution([1.0, 2.0, 3.0, 4.0, None]) == {"n": 4, "median": 2.5, "p90": 3.7}
    assert intervals.distribution([]) == {"n": 0, "median": None, "p90": None}


def test_tag_means_keep_every_tag_and_read_the_exit_effect():
    rows = [_row(exit_effect=0.5, tags_=("same_day_exit",)),
            _row(exit_effect=-0.1, tags_=("same_day_exit", "wick_missed")),
            _row(exit_effect=9.0, tags_=("same_day_exit",), scored=False)]
    means = intervals.tag_means(rows, "v1")
    assert list(means) == list(tags.TAGS) and len(means) == 17
    assert means["same_day_exit"] == {"n": 2, "mean_exit_effect": 0.2}
    assert means["wick_missed"] == {"n": 1, "mean_exit_effect": -0.1}
    assert means["gap_through"] == {"n": 0, "mean_exit_effect": None}


def test_population_counts_classes_refusals_and_would_fill():
    rows = [_full(), _full(klass="manual"), _full(refusal="split_in_window", ticker="CCC"),
            _full(klass="unfilled", unfilled_reason="expired", would_fill={"v1": True, "v2": None}),
            _full(klass="unfilled", unfilled_reason=None, would_fill={"v1": False, "v2": False})]
    pop = intervals.population(rows)
    assert pop["classes"] == {"closed": 2, "manual": 1, "still_open": 0, "unfilled": 2}
    assert pop["scored"] == 1 and pop["refusals"]["split_in_window"] == 1
    assert pop["refused_tickers"] == {"no_bars": [], "split_in_window": ["CCC"],
                                      "bars_end_early": []}
    assert pop["unfilled_reasons"] == {"expired": 1, "unknown": 1}
    assert pop["would_fill"] == {"v1": {"yes": 1, "no": 1, "unknown": 0},
                                 "v2": {"yes": 0, "no": 1, "unknown": 1}}


def test_population_counts_each_live_r_source_with_measured_zeros():
    rows = [_full(r_source="journal"), _full(r_source="trade"),
            _full(klass="manual", r_source="trade"),
            _full(refusal="no_journal", r_live_net=None), _full(klass="unfilled")]
    assert intervals.population(rows)["r_source"] == {"journal": 1, "trade": 2}
    assert intervals.population([])["r_source"] == {"journal": 0, "trade": 0}


def test_slip_reads_both_measures_and_the_gap_detail():
    gap = {"gap_r": -1.2, "gap_pct": -2.0, "exit_vs_open_r": 0.1, "exit_vs_stop_r": -1.1}
    rows = [_full(entry_slip=[10.0, 0.06], poll_fill=[5.0, 0.02], gap=gap),
            _full(entry_slip=[20.0, 0.1]), _full(klass="manual", entry_slip=[99.0, 9.0])]
    out = intervals.slip(rows)
    assert out["entry_slip_bps"] == {"n": 2, "median": 15.0, "p90": 19.0}
    assert out["poll_fill_r"]["n"] == 1 and out["gap_pct"]["median"] == -2.0


def test_ledger_cells_are_live_only_without_interval():
    rows = [_full(), _full(ledger="weak", r_live_net=-1.0),
            _full(klass="still_open", r_live_net=None), _full(refusal="no_journal", r_live_net=None)]
    cells = intervals.ledger_cells(rows, **FAST)
    assert set(cells) == {"main", "weak"}
    assert (cells["main"]["total"], cells["weak"]["total"]) == (0.5, -1.0)
    assert cells["main"]["interval"] is None


def test_cell_count_reads_effects_tags_and_sub_reasons():
    report = {"layer1": {"long": {"headline": {"v1": {"effects": {"a": {}, "b": {}},
                                                      "tags": {"t": {}}}}}},
              "selection": {"long": {"headline": {"live_only": {"by_bucket": {"x": 0, "y": 0}},
                                                  "replay_only": {"by_reason": {"z": 0}}}}}}
    assert intervals.cell_count(report) == 6
    assert intervals.cell_count({}) == 0
