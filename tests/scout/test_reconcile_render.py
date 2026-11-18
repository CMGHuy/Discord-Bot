"""v232 V232-14: report assembly and the results Markdown."""
import copy
import dataclasses
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import intervals, layer2, records, render, table  # noqa: E402
from tests.scout.test_reconcile_table import BOOK  # noqa: E402

EXPORT = records.Export(records=(), rejections=(), watchlist=(), deploys=(
    {"ts": "2026-10-01T12:00:00+00:00", "git_sha": "abc1234"},
    {"ts": "2026-08-01T12:00:00+00:00", "git_sha": "old0000"}))
META = {"window": ["2026-07-01", "2026-11-16"], "commit": "f00d", "params_digest": "d" * 64,
        "coverage": {"sessions": 40, "spy_missing": False, "base_missing_days": {"AAA": 2},
                     "panel_gaps": {}, "snapshot_missing": [], "extra_missing": {}}}


def _report(rows=BOOK):
    selection = layer2.selection_counts(layer2.MatchResult([], [], [], []), EXPORT)
    return render.build_report(rows, selection, EXPORT, meta=META, n_resamples=200, seed=42)


REPORT = _report()
MD = render.render_markdown(REPORT)


def test_every_block_holds_per_trade_sums_and_the_cost_check():
    assert all(set(REPORT["layer1"][s][e][m]["effects"]) == {"gap_net", "entry", "exit", "costs"}
               for s in layer2.SIDES for e in layer2.ERAS for m in ("v1", "v2"))
    block = REPORT["layer1"]["long"]["headline"]["v1"]
    assert (block["effects"]["exit"]["n"], block["effects"]["exit"]["total"]) == (3, -0.8)
    assert block["effects"]["costs"]["total"] == -0.4
    assert block["cost_check"] == {"zero_cost_backtest": -0.4, "equally_costed": 0.0}
    assert block["table"] == [dataclasses.asdict(line) for line in
                              table.build_table(BOOK, side="long", fill_model="v1")]


def test_sections_use_the_interval_helpers_and_the_headline_deploys():
    long_rows = [r for r in BOOK if r.side == "long" and r.era == "headline"]
    assert REPORT["populations"]["long"]["headline"] == intervals.population(long_rows)
    assert REPORT["slip"]["long"]["headline"] == intervals.slip(long_rows)
    assert REPORT["deploys"] == [{"ts": "2026-10-01T12:00:00+00:00", "git_sha": "abc1234"}]


def test_a_tampered_row_fails_the_self_check():
    rows = [dataclasses.replace(BOOK[0], r_live_net=BOOK[0].r_live_net + 0.3)] + BOOK[1:]
    with pytest.raises(table.ReconcileError):
        _report(rows)


def test_the_doc_opens_with_the_caveat_and_carries_the_labels():
    lines = MD.splitlines()
    assert lines[0] == f"# {render.TITLE}" and lines[2] == f"> {render.CAVEAT}"
    assert render.CAVEAT.startswith("The live book is a paper book.")
    assert "(includes code changes)" in MD and "(incl. intraday drift to the close)" in MD
    assert intervals.INTERVAL_LABEL in MD and "zero by construction" in MD
    assert f"Cells shown: {REPORT['cells']} " in MD
    assert "2026-10-01T12:00:00+00:00 abc1234" in MD


def test_coverage_counts_and_refused_tickers_are_listed():
    assert REPORT["meta"]["coverage"]["base_missing_days"] == {"AAA": 2} and "AAA 2" in MD
    assert REPORT["populations"]["long"]["headline"]["refused_tickers"]["split_in_window"] == ["AAA"]


def test_backtest_r_keyed_by_strategy_is_a_leak():
    assert render.leaks(REPORT, MD) == [] and "AAA 2" in MD     # coverage counts pass (Handoff)
    bad = copy.deepcopy(REPORT)
    bad["layer1"]["long"]["headline"]["v1"]["by_strategy"] = {"RSI": 0.4}
    assert any("by_strategy" in p for p in render.leaks(bad, MD))


def test_a_forbidden_key_or_backtest_key_outside_layer1_is_a_leak():
    bad = copy.deepcopy(REPORT)
    bad["populations"]["long"]["headline"]["ticker"] = "AAA"
    bad["selection"]["long"]["headline"]["r_as_backtest"] = 1.0
    problems = render.leaks(bad, MD)
    assert any("forbidden key" in p for p in problems)
    assert any("outside layer1" in p for p in problems)


def test_a_heading_with_backtest_r_by_ticker_is_a_leak():
    assert render.leaks(REPORT, MD + "\n## Backtest R by ticker\n")
    assert render.leaks(REPORT, MD + "\n| Strategy | exit effect |\n|---|---|\n")
    assert render.leaks(REPORT, MD + "\n## Live net R by ticker\n") == []


def test_the_run_line_counts_unserved_bars_too():
    bars = {"raw": {"sha256": "a" * 64, "start": "x", "end": "y", "n_ok": 85, "n_empty": 2,
                    "n_unserved": 1},
            "split": {"sha256": "b" * 64, "start": "x", "end": "y", "n_ok": 85, "n_empty": 2}}
    md = render.render_markdown({**REPORT, "meta": {**META, "bars": bars}})
    assert f"{'a' * 12} (85 ok, 2 empty, 1 unserved)" in md
    assert f"{'b' * 12} (85 ok, 2 empty, 0 unserved)" in md     # a summary without the count
