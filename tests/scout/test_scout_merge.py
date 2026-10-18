"""scout_merge drops, pinning, ranking and the slate (v161 TS9).

Parsing (parse_rows, closed_names, ledger_names, closed_match) is pinned in
test_scout_merge_parse.py. Here rows are built directly, so each drop and
ranking rule is tested alone; the CLI test runs the whole merge against the
real ledger and the real closed pre-registrations table."""
import json
import sys

import pytest
from dataclasses import fields
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import scout_merge as merge  # noqa: E402

GOOD_EVIDENCE = "cell regime=risk_on; N 40; weeks 12; Δ net ExpR 0.200 [0.050, 0.350]; q 0.040"


def _row(**kw):
    base = {f.name: "" for f in fields(merge.ScoutRow)}
    base.update(role="setup-scout", idea="idea-a", claim="A claim.", evidence=GOOD_EVIDENCE,
                exploratory="yes", edge="expectancy", mechanism="Why it pays.",
                order_form="stop-buy above the signal high, day order", manual_actions="none",
                pairs_with="n/a", divergence="no", route="/prereg")
    base.update(kw)
    return merge.ScoutRow(**base)


def _cell(cid, *, n=40, weeks=12, lo=0.05, hi=0.35, thin=False):
    cut, value = cid.split("=", 1)
    ci = None if lo is None else [lo, hi]
    delta = None if lo is None else (lo + hi) / 2
    return {"id": cid, "cut": cut, "value": value, "n": n, "weeks": weeks, "win_rate": 0.5,
            "net_expr": 0.2, "gross_expr": 0.22, "delta": delta, "ci": ci, "p": 0.01,
            "q": 0.04, "thin": thin, "bar_covered_n": None, "extra": {}}


CELLS = {c["id"]: c for c in (
    _cell("regime=risk_on"),
    _cell("strategy_horizon=RSI|1m", n=90, weeks=20, lo=0.10, hi=0.30),
    _cell("weekday=Fri", n=12, weeks=5, thin=True),
    _cell("ticker=AAA", lo=-0.10, hi=0.30),
    _cell("direction=bearish", lo=None),
)}


def _screen(rows, *, closed=(), ledger=None, cells=CELLS):
    return merge.screen_rows(list(rows), closed=set(closed), ledger=dict(ledger or {}), cells=cells)


def _reasons(drops):
    return {d.idea: d.reason for d in drops}


# ---- drops ---------------------------------------------------------------

def test_a_supported_row_is_kept_without_a_drop():
    kept, drops = _screen([_row()])
    assert [r.idea for r in kept] == ["idea-a"] and drops == []


def test_a_ledger_id_is_dropped_naming_the_id():
    kept, drops = _screen([_row(idea="e33-avwap-levels")], ledger={"e33-avwap-levels": "e33-avwap-levels"})
    assert kept == []
    assert "ledger" in drops[0].reason and "e33-avwap-levels" in drops[0].reason
    assert drops[0].role == "setup-scout"


def test_a_closed_name_is_dropped_naming_the_closed_row():
    kept, drops = _screen([_row(idea="regime-allow")], closed={"regime-allow"})
    assert kept == []
    assert "closed pre-registration" in drops[0].reason


def test_a_second_row_with_the_same_idea_is_a_duplicate():
    kept, drops = _screen([_row(idea="idea-a"), _row(idea="Idea_A", role="regime-desk")])
    assert [r.role for r in kept] == ["setup-scout"]
    assert "duplicate" in drops[0].reason and drops[0].role == "regime-desk"


def test_an_unknown_edge_is_dropped():
    _, drops = _screen([_row(edge="integrity")])
    assert "edge" in drops[0].reason


def test_a_thin_cell_is_dropped():
    _, drops = _screen([_row(evidence="cell weekday=Fri; N 12; weeks 5; Δ net ExpR 0.2 [0.05, 0.35]; q 0.04")])
    assert "thin" in drops[0].reason


def test_a_cell_missing_from_the_autopsy_is_an_invented_figure():
    _, drops = _screen([_row(evidence="cell weekday=Mon; N 50; weeks 15; Δ net ExpR 0.3 [0.1, 0.5]; q 0.01")])
    assert "not in the autopsy" in drops[0].reason


def test_a_row_citing_no_cell_and_no_playbook_screen_is_dropped():
    _, drops = _screen([_row(evidence="the book looks weak on Mondays")])
    assert "no autopsy cell" in drops[0].reason


def test_a_quoted_n_that_differs_from_the_cell_is_an_invented_figure():
    _, drops = _screen([_row(evidence="cell regime=risk_on; N 400; weeks 12; Δ net ExpR 0.2 [0.05, 0.35]; q 0.04")])
    assert "quoted N 400" in drops[0].reason


def test_autopsy_evidence_not_marked_exploratory_is_dropped():
    _, drops = _screen([_row(exploratory="no")])
    assert "exploratory" in drops[0].reason


def test_a_lower_bound_at_or_below_zero_is_dropped():
    rows = [_row(idea="neg", evidence="cell ticker=AAA; N 40; weeks 12; Δ net ExpR 0.1 [-0.1, 0.3]; q 0.2"),
            _row(idea="none", evidence="cell direction=bearish; N 40; weeks 12; Δ net ExpR n/a; q n/a")]
    kept, drops = _screen(rows)
    assert kept == []
    reasons = _reasons(drops)
    assert "at or below zero" in reasons["neg"] and "at or below zero" in reasons["none"]


def test_a_playbook_screen_row_needs_no_cell():
    row = _row(idea="gap-and-hold", evidence="playbook gap-and-hold", route="/screen gap-and-hold")
    kept, drops = _screen([row])
    assert [r.idea for r in kept] == ["gap-and-hold"] and drops == []


def test_a_playbook_reference_does_not_exempt_a_quoted_thin_cell():
    evidence = ("cell weekday=Fri; N 12; weeks 5; Δ net ExpR 0.2 "
                "[0.05, 0.35]; q 0.04 | playbook gap-and-hold")
    row = _row(idea="gap-and-hold", evidence=evidence, route="/screen gap-and-hold")
    kept, drops = _screen([row])
    assert kept == []
    assert "thin" in drops[0].reason


def test_a_playbook_row_routed_to_prereg_still_needs_a_cell():
    row = _row(idea="gap-and-hold", evidence="playbook gap-and-hold", route="/prereg")
    _, drops = _screen([row])
    assert "no autopsy cell" in drops[0].reason



@pytest.mark.parametrize("old,new,label", [
    ("N 40", "N 400", "N"),
    ("weeks 12", "weeks 120", "weeks"),
    ("0.200", "0.900", "Δ"),
    ("0.050", "0.500", "CI lower"),
    ("0.350", "0.900", "CI upper"),
    ("q 0.040", "q 0.001", "q"),
])
def test_fabricated_evidence_figures_are_dropped(old, new, label):
    kept, drops = _screen([_row(evidence=GOOD_EVIDENCE.replace(old, new))])
    assert kept == []
    assert label in drops[0].reason and "invented figure" in drops[0].reason


@pytest.mark.parametrize("evidence", [
    "cell regime=risk_on",
    GOOD_EVIDENCE.replace("N 40; ", ""),
    GOOD_EVIDENCE.replace("weeks 12; ", ""),
    GOOD_EVIDENCE.replace("; q 0.040", ""),
    GOOD_EVIDENCE.replace("q 0.040", "q NaN"),
    GOOD_EVIDENCE + "; q 0.001",
])
def test_incomplete_or_ambiguous_evidence_is_dropped(evidence):
    kept, drops = _screen([_row(evidence=evidence)])
    assert kept == []
    assert "evidence format" in drops[0].reason


@pytest.mark.parametrize("q", [0.10001, None, float("nan"), float("inf")])
def test_q_cutoff_uses_unrounded_json_and_requires_finite_q(q):
    cell = dict(CELLS["regime=risk_on"], q=q)
    evidence = GOOD_EVIDENCE.replace("q 0.040", "q 0.100")
    kept, drops = _screen([_row(evidence=evidence)], cells={cell["id"]: cell})
    assert kept == []
    assert "q" in drops[0].reason and "0.10" in drops[0].reason


def test_printed_rounding_and_q_at_cutoff_are_accepted():
    cell = dict(CELLS["regime=risk_on"], delta=0.20049, ci=[0.05049, 0.35049], q=0.1)
    evidence = GOOD_EVIDENCE.replace("0.200", "+0.200").replace("q 0.040", "q 0.100")
    kept, drops = _screen([_row(evidence=evidence)], cells={cell["id"]: cell})
    assert len(kept) == 1 and drops == []


# ---- ranking -------------------------------------------------------------

def test_rank_orders_by_edge_then_lower_bound_then_n():
    rows = [
        _row(idea="vol", edge="volume"),
        _row(idea="harv", edge="harvest"),
        _row(idea="exp-low", evidence=GOOD_EVIDENCE),
        _row(idea="exp-high", evidence="cell strategy_horizon=RSI|1m; N 90; weeks 20; Δ net ExpR 0.2 [0.10, 0.30]; q 0.01"),
    ]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["exp-high", "exp-low", "harv", "vol"]


def test_equal_lower_bounds_break_on_n_then_name():
    cells = dict(CELLS, **{"regime=risk_off": _cell("regime=risk_off", n=80)})
    rows = [_row(idea="b-small"), _row(idea="a-small"),
            _row(idea="big", evidence="cell regime=risk_off; N 80; weeks 12; Δ net ExpR 0.2 [0.05, 0.35]; q 0.04")]
    assert [r.idea for r in merge.rank(rows, cells)] == ["big", "a-small", "b-small"]


def test_divergence_rows_are_pinned_above_every_edge_class():
    rows = [_row(idea="exp"), _row(idea="div", edge="volume", divergence="yes")]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["div", "exp"]


def test_manual_action_ranks_a_row_down_within_its_edge_class():
    rows = [_row(idea="manual", manual_actions="move the stop to breakeven after the first target",
                 evidence="cell strategy_horizon=RSI|1m; N 90; weeks 20; Δ net ExpR 0.2 [0.10, 0.30]; q 0.01"),
            _row(idea="plain"),
            _row(idea="harv", edge="harvest")]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["plain", "manual", "harv"]


def test_a_playbook_row_sorts_last_in_its_edge_class():
    rows = [_row(idea="pb", evidence="playbook gap-and-hold", route="/screen pb"), _row(idea="cell-backed")]
    assert [r.idea for r in merge.rank(rows, CELLS)] == ["cell-backed", "pb"]


# ---- slate ---------------------------------------------------------------

HEADER = {"window": ["2026-01-05", "2026-10-09"], "n": 212, "pooled_net_expr": 0.11,
          "pooled_win_rate": 0.52, "net_of_frictions": "modelled", "cells_tested": 147,
          "bar_covered_n": 190, "resamples": 10000, "seed": 42, "notes": []}


def test_the_slate_copies_the_header_and_carries_both_boundaries():
    text = merge.render_slate([_row()], [], HEADER, date="2026-10-16",
                              autopsy_path="docs/superpowers/results/2026-10-16-book-autopsy.json")
    assert text.startswith("# Scout slate 2026-10-16\n")
    assert "2026-01-05 to 2026-10-09" in text
    assert "**N:** 212" in text and "**Cells tested:** 147" in text and "modelled" in text
    assert "`docs/superpowers/results/2026-10-16-book-autopsy.json`" in text
    assert merge.HOLDOUT_REMINDER in text and merge.BOUNDARY_NOTE in text
    assert text.index("## Ranked") < text.index("## Dropped")
    assert "### 1. idea-a (setup-scout)" in text


def test_the_slate_renders_all_row_fields_and_an_empty_drops_section():
    text = merge.render_slate([_row()], [], HEADER, date="2026-10-16", autopsy_path="a.json")
    for name in merge.ROW_FIELDS[1:]:
        assert f"- {name}: " in text, name
    assert text.rstrip().endswith("None.")


def test_the_holdout_reminder_states_boundary_five():
    reminder = merge.HOLDOUT_REMINDER
    for phrase in ("exploratory", "holdout", "contaminated", "TRAIN/VALIDATION", "2026-01-01", "/screen"):
        assert phrase in reminder, phrase


def test_every_drop_is_listed_with_its_reason_and_pipes_are_escaped():
    drops = [merge.Drop(idea="x", role="regime-desk", reason="cell strategy_horizon=RSI|1m is thin")]
    text = merge.render_slate([], drops, HEADER, date="2026-10-16", autopsy_path="a.json")
    assert "No row survived the merge." in text
    assert "| x | regime-desk | cell strategy_horizon=RSI\\|1m is thin |" in text


def test_a_pinned_row_says_so_in_its_heading():
    text = merge.render_slate([_row(divergence="yes")], [], HEADER, date="2026-10-16", autopsy_path="a.json")
    assert "### 1. idea-a (setup-scout) — pinned: live diverges from the plan" in text


# ---- CLI, against the real ledger and the real closed table ----------------

def _block(idea, evidence=GOOD_EVIDENCE, route="/prereg", edge="expectancy"):
    return (f"- idea: {idea}\n"
            f"  claim: One sentence.\n"
            f"  evidence: {evidence}\n"
            f"  exploratory: yes\n"
            f"  edge: {edge}\n"
            f"  mechanism: Why a trader expects it to pay.\n"
            f"  order_form: stop-buy above the signal high, day order\n"
            f"  manual_actions: none\n"
            f"  pairs_with: n/a\n"
            f"  divergence: no\n"
            f"  route: {route}\n")


def test_the_cli_drops_ledger_closed_and_renamed_ideas_and_writes_the_slate(tmp_path, capsys):
    role_output = tmp_path / "roles.md"
    role_output.write_text(
        "## role: setup-scout\n\n"
        + _block("kept-idea") + "\n"
        + _block("screen-high52w") + "\n"     # a ledger id
        + _block("gap-volume-continuation") + "\n"   # SCREEN-FAIL `gap_volume` renamed (closed_match)
        + "## role: regime-desk\n\n"
        + _block("regime-allow") + "\n",       # closed table: `REGIME_ALLOW`
        encoding="utf-8")
    autopsy = tmp_path / "autopsy.json"
    autopsy.write_text(json.dumps({"header": HEADER, "cells": list(CELLS.values()),
                                   "tallies": [], "giveback": {"n": 0, "mean": 0.0, "median": 0.0}}),
                       encoding="utf-8")
    out_dir = tmp_path / "results"
    code = merge.main([str(role_output), "--autopsy", str(autopsy),
                       "--out-dir", str(out_dir), "--date", "2026-10-16"])
    assert code == 0
    slate = (out_dir / "2026-10-16-scout-slate.md").read_text(encoding="utf-8")
    ranked, dropped = slate.split("## Dropped")
    assert "### 1. kept-idea (setup-scout)" in ranked
    for idea in ("screen-high52w", "gap-volume-continuation", "regime-allow"):
        assert idea not in ranked, idea
        assert f"| {idea} |" in dropped, idea
    assert "1 ranked, 3 dropped" in capsys.readouterr().out
