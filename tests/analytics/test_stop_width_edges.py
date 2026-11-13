"""v226: TRAIN-frozen stop_atr quartile edges -- outcome-blind, merged when
they coincide, never an empty bucket, edge values to the upper bucket, live
rows bucketed on the TRAIN edges."""
from __future__ import annotations

import random

import pytest

from swingbot.core.analytics import expectancy_attribution as ea


def _row(stop_atr, r=0.0, **over) -> dict:
    row = {"r": r, "r_gross": r, "week": "2021-03-01", "direction": "bullish",
           "horizon": "2w", "stop_atr": stop_atr, "atr_pct": None, "stop_clamped": None}
    row.update(over)
    return row


EIGHT = [_row(float(v), r=(v - 4) / 4) for v in range(1, 9)]          # stop_atr 1..8


def test_edges_are_the_linear_train_quartiles():
    assert ea.frozen_edges(EIGHT, "stop_atr") == pytest.approx([2.75, 4.5, 6.25])


def test_edges_are_outcome_blind():
    shuffled_r = [row["r"] for row in EIGHT]
    random.Random(7).shuffle(shuffled_r)
    shuffled = [dict(row, r=r) for row, r in zip(EIGHT, shuffled_r)]
    no_r = [{key: value for key, value in row.items() if key not in ("r", "r_gross")}
            for row in EIGHT]
    expected = ea.frozen_edges(EIGHT, "stop_atr")
    assert ea.frozen_edges(shuffled, "stop_atr") == expected
    assert ea.frozen_edges(no_r, "stop_atr") == expected     # never reads r at all


def test_unknown_values_are_left_out_of_the_quantiles():
    noisy = EIGHT + [_row(None), _row(0), _row(-1.0), _row("2.0"), _row(True),
                     {"r": 1.0}]
    assert ea.frozen_edges(noisy, "stop_atr") == ea.frozen_edges(EIGHT, "stop_atr")


@pytest.mark.parametrize("values, expected", [
    ([1.0] * 6 + [5.0] * 2, [2.0]),           # q25 = q50 = min: both dropped
    ([1.0, 1.0, 1.0, 5.0, 5.0, 5.0], [3.0]),  # [3, 5) would be empty: 5 dropped
    ([2.0] * 5, []),                          # one value: a single bucket
    ([3.0], []),                              # fewer than two known values
    ([], []),
], ids=["low-tie", "empty-middle", "constant", "one", "none"])
def test_coinciding_edges_merge(values, expected):
    assert ea.frozen_edges([_row(v) for v in values], "stop_atr") == pytest.approx(expected)


@pytest.mark.parametrize("values", [
    [float(v) for v in range(1, 9)],
    [1.0] * 6 + [5.0] * 2,
    [1.0, 1.0, 1.0, 5.0, 5.0, 5.0],
    [0.2, 0.2, 0.2, 0.2, 0.3, 0.9, 0.9, 0.9, 0.9, 0.9],
    [0.5 + (i % 7) * 0.05 for i in range(200)],
])
def test_no_train_bucket_is_ever_empty(values):
    rows = [_row(v) for v in values]
    groups = ea.stop_width_groups(rows, [])
    assert groups["edges"] == sorted(set(groups["edges"]))           # strictly increasing
    assert all(groups["train"]["buckets"][label] for label in groups["labels"])
    assert sum(len(b) for b in groups["train"]["buckets"].values()) == len(values)


def test_labels_name_the_edges():
    assert ea.edge_labels([2.75, 4.5, 6.25]) == [
        "Q1 (<2.75)", "Q2 (2.75–4.50)", "Q3 (4.50–6.25)", "Q4 (≥6.25)"]
    assert ea.edge_labels([0.4]) == ["Q1 (<0.40)", "Q2 (≥0.40)"]
    assert ea.edge_labels([]) == ["Q1 (all)"]


@pytest.mark.parametrize("value, label", [
    (1.0, "Q1 (<2.75)"), (2.75, "Q2 (2.75–4.50)"), (4.5, "Q3 (4.50–6.25)"),
    (6.25, "Q4 (≥6.25)"), (99.0, "Q4 (≥6.25)"), (None, "unknown"), (0, "unknown"),
    (-2.0, "unknown"), ("3.0", "unknown"), (True, "unknown")])
def test_a_value_on_an_edge_goes_to_the_upper_bucket(value, label):
    assert ea.edge_label(value, [2.75, 4.5, 6.25]) == label


def test_one_bucket_when_there_is_no_edge():
    assert ea.edge_label(0.3, []) == "Q1 (all)"
    assert ea.edge_label(None, []) == ea.UNKNOWN == "unknown"


def test_live_rows_use_the_train_edges_and_unknowns_are_counted_not_bucketed():
    train = EIGHT + [_row(None), _row(0)]
    live = [_row(0.35), _row(0.5), _row(0.75), _row(7.0), _row(None),
            {"r": -1.0}]                                             # live quartiles differ
    groups = ea.stop_width_groups(train, live)
    assert groups["edges"] == pytest.approx([2.75, 4.5, 6.25])
    assert groups["labels"] == ea.edge_labels(groups["edges"])
    assert groups["edges"] == ea.stop_width_groups(train, [])["edges"]   # live never moves them
    tr, lv = groups["train"], groups["live"]
    assert list(tr["buckets"]) == list(lv["buckets"]) == groups["labels"]
    assert tr["unknown"] == 2 and len(tr["known"]) == 8
    assert [len(tr["buckets"][label]) for label in groups["labels"]] == [2, 2, 2, 2]
    assert lv["unknown"] == 2 and len(lv["known"]) == 4
    assert [len(lv["buckets"][label]) for label in groups["labels"]] == [3, 0, 0, 1]
    assert all(row in lv["known"] for row in lv["buckets"]["Q1 (<2.75)"])
    assert tr["buckets"]["Q1 (<2.75)"][0] is train[0]               # the input dicts themselves


def test_empty_populations_give_one_empty_bucket():
    groups = ea.stop_width_groups([], [])
    assert groups["edges"] == [] and groups["labels"] == ["Q1 (all)"]
    assert groups["train"] == {"buckets": {"Q1 (all)": []}, "known": [], "unknown": 0}
