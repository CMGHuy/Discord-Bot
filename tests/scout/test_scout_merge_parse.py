"""v161 TS8: scout_merge parsing -- role-output rows, malformed and duplicate drops,
and the two 'already decided' name sources (closed table, ledger). The closed-table
parse is also pinned against the REAL backtest-methodology.md (spec § 6), so a
rewording of that section fails here instead of silently disabling the drops."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "dev"))
import scout_merge as sm  # noqa: E402

BASE = {
    "claim": "One sentence.",
    "evidence": "cell direction=bullish; N 40; weeks 10; Δ net ExpR 0.20 [0.05, 0.35]; q 0.05",
    "exploratory": "yes", "edge": "expectancy", "mechanism": "Why a trader expects it to pay.",
    "order_form": "stop-buy above the signal high, one session", "manual_actions": "none",
    "pairs_with": "n/a", "divergence": "no", "route": "/prereg"}
PLAYBOOK_IDS = ("gap-and-hold", "gap-fill-reversal", "tight-base-breakout",
                "rs-leader-index-pullback", "failed-breakdown-reclaim", "atr-reentry-after-stop",
                "three-bar-weekly-reversal")


def _block(idea: str, drop=(), extra: str = "", **over) -> str:
    fields = dict(BASE, **over)
    lines = [f"- idea: {idea}"] + [f"  {k}: {v}" for k, v in fields.items() if k not in drop]
    return "\n".join(lines) + "\n" + extra


def _doc(*sections) -> str:
    return "# Scout role outputs\n\n" + "\n".join(
        f"## role: {role}\n\n" + "\n".join(blocks) for role, blocks in sections)


def test_row_fields_are_the_row_format_keys_in_order():
    assert sm.ROW_FIELDS == ("idea", "claim", "evidence", "exploratory", "edge", "mechanism",
                             "order_form", "manual_actions", "pairs_with", "divergence", "route")


def test_parse_rows_reads_each_row_under_its_role():
    text = _doc(("exit-harvester", [_block("near-tp-stall-trail", edge="harvest")]),
                ("setup-scout", [_block("gap-and-hold", evidence="playbook gap-and-hold",
                                        route="/screen gap-and-hold"),
                                 _block("break-retest-two-week")]))
    rows, drops = sm.parse_rows(text)
    assert drops == []
    assert [(r.role, r.idea) for r in rows] == [
        ("exit-harvester", "near-tp-stall-trail"), ("setup-scout", "gap-and-hold"),
        ("setup-scout", "break-retest-two-week")]
    assert rows[0].edge == "harvest" and rows[1].route == "/screen gap-and-hold"


def test_crlf_text_parses_like_lf():
    text = _doc(("regime-desk", [_block("friday-entry-skip")])).replace("\n", "\r\n")
    rows, drops = sm.parse_rows(text)
    assert [r.idea for r in rows] == ["friday-entry-skip"] and drops == []


@pytest.mark.parametrize("evidence, cell, playbook, n", [
    ("cell near_tp_close=near_tp_stall; N 41; weeks 12; Δ net ExpR 0.21 [0.05, 0.37]; q 0.06",
     "near_tp_close=near_tp_stall", None, 41),
    ("cell strategy_horizon=Break & Retest|2w; N 33; weeks 9; Δ net ExpR 0.30 [0.10, 0.50]; q 0.04",
     "strategy_horizon=Break & Retest|2w", None, 33),
    ("playbook gap-and-hold", None, "gap-and-hold", None),
    ("playbook: tight-base-breakout", None, "tight-base-breakout", None),
    ("cell weekday=Fri; N 31; weeks 8; Δ net ExpR 0.10 [0.01, 0.20]; q 0.09   |   "
     "playbook gap-fill-reversal", "weekday=Fri", "gap-fill-reversal", 31)])
def test_evidence_properties(evidence, cell, playbook, n):
    rows, _ = sm.parse_rows(_doc(("setup-scout", [_block("x-idea", evidence=evidence)])))
    assert (rows[0].cell_id, rows[0].playbook_id, rows[0].quoted_n) == (cell, playbook, n)


@pytest.mark.parametrize("kw, reason", [
    ({"drop": ("order_form",)}, "missing order_form"),
    ({"pairs_with": ""}, "missing pairs_with"),
    ({"exploratory": "no"}, "boundary 5"),
    ({"edge": "expectancy | harvest | volume"}, "edge must be"),
    ({"divergence": "maybe"}, "divergence must be yes or no"),
    ({"extra": "  confidence: high\n"}, "unknown field confidence"),
    ({"extra": "  Confidence: high\n"}, "unknown field Confidence"),
    ({"extra": "  confidence-score: high\n"}, "unknown field confidence-score"),
    ({"extra": "  claim: again\n"}, "repeated field claim")])
def test_malformed_rows_are_dropped_with_the_reason(kw, reason):
    rows, drops = sm.parse_rows(_doc(("regime-desk", [_block("opex-week-skip", **kw)])))
    assert rows == []
    assert len(drops) == 1 and drops[0].idea == "opex-week-skip" and drops[0].role == "regime-desk"
    assert drops[0].reason.startswith("malformed: ") and reason in drops[0].reason


def test_a_row_before_any_role_heading_is_malformed():
    rows, drops = sm.parse_rows("# outputs\n\n" + _block("orphan-idea"))
    assert rows == [] and "no '## role:' heading" in drops[0].reason


def test_a_duplicate_idea_keeps_the_first_and_drops_the_rest():
    text = _doc(("exit-harvester", [_block("Gap-Fill")]), ("setup-scout", [_block("gap_fill")]))
    rows, drops = sm.parse_rows(text)
    assert [r.role for r in rows] == ["exit-harvester"]
    assert drops == [sm.Drop("gap_fill", "setup-scout", "duplicate of exit-harvester/Gap-Fill")]


@pytest.mark.parametrize("raw, norm", [
    ("REGIME_ALLOW", "regime-allow"), ("uptrend_pullback", "uptrend-pullback"),
    ("  High52w ", "high52w"), ("Break & Retest|2w", "break-retest-2w"), ("--a--b--", "a-b")])
def test_normalise(raw, norm):
    assert sm.normalise(raw) == norm


FIXTURE_DOC = """\
# Methodology

### Closed pre-registrations — do not re-run these

| Component | Outcome | Record |
|---|---|---|
| `REGIME_ALLOW` regime gate (v17 P2a) | **No gate justified** | ledger `v17-regime-allow` |
| Idea screen `gap_volume` — open gaps up | **SCREEN-FAIL.** N=10 | ledger `screen-gap_volume` |
| Idea screen `uptrend_pullback` — RSI(2) | **SCREEN-PASS.** N=1 | ledger `screen-uptrend_pullback` |
| Headroom, `h ∈ {0.5, 1.0}` (v135) | **NO-LIFT** | x |

## Later section

| `LATER_KNOB` (v999) | **NO-LIFT** | y |
"""


def test_closed_names_reads_the_table_and_stops_at_the_first_non_table_line(tmp_path):
    doc = tmp_path / "methodology.md"
    doc.write_text(FIXTURE_DOC, encoding="utf-8")
    assert sm.closed_names(doc) == {
        "regime-allow", "v17", "gap-volume", "screen-gap-volume", "v135",
        "=uptrend-pullback", "=screen-uptrend-pullback"}


def test_closed_names_fails_loudly_without_the_heading(tmp_path):
    doc = tmp_path / "methodology.md"
    doc.write_text("# Methodology\n\nno table here\n", encoding="utf-8")
    with pytest.raises(ValueError):
        sm.closed_names(doc)


def test_closed_names_against_the_real_methodology_doc():
    names = sm.closed_names()
    assert {"v129", "v135", "high52w", "regime-allow", "gap-volume", "turn-of-month"} <= names
    assert "=uptrend-pullback" in names and "uptrend-pullback" not in names


@pytest.mark.parametrize("idea, match", [
    ("high52w-volume-confirm", "high52w"), ("gap-volume-continuation", "gap-volume"),
    ("turn-of-month-v2", "turn-of-month"), ("regime_allow_by_sector", "regime-allow"),
    ("v129-arm-c", "v129"), ("uptrend-pullback", "uptrend-pullback"),
    ("uptrend-pullback-gap-entry", None), ("regime-allowance", None),
    ("atr-reentry-after-stop", None)])
def test_closed_match_against_the_real_table(idea, match):
    assert sm.closed_match(idea, sm.closed_names()) == match


def test_no_playbook_seed_is_closed():
    names = sm.closed_names()
    assert {pid: sm.closed_match(pid, names) for pid in PLAYBOOK_IDS} == dict.fromkeys(PLAYBOOK_IDS)


def test_ledger_names_map_ids_screen_names_heads_and_knobs(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    rows = [{"id": "v17-regime-allow", "hypothesis": "REGIME_ALLOW regime gate (v17 P2a)"},
            {"id": "screen-high52w", "hypothesis": "high52w: close >= 0.95 x the 252-bar high"},
            {"id": "v99-other", "hypothesis": "Another REGIME_ALLOW mention"}]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n\n", encoding="utf-8")
    assert sm.ledger_names(ledger) == {
        "v17-regime-allow": "v17-regime-allow", "regime-allow": "v17-regime-allow",
        "screen-high52w": "screen-high52w", "high52w": "screen-high52w",
        "v99-other": "v99-other", "other": "v99-other"}


def test_ledger_names_against_the_real_ledger():
    names = sm.ledger_names()
    assert names["high52w"] == "screen-high52w"
    assert names["regime-allow"] == "v17-regime-allow"
    assert names["uptrend-pullback"] == "screen-uptrend_pullback"
    assert names["screen-uptrend-pullback"] == "screen-uptrend_pullback"
    assert names["e33-avwap-levels"] == "e33-avwap-levels"
