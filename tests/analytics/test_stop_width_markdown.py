"""v226: the Markdown body of the stop-width results doc -- verdict, the six
clauses per bucket, both populations side by side (live never gates), the
volatility sentence only when flagged, and the two fixed paragraphs."""
from __future__ import annotations

import pytest

from swingbot.core.analytics import expectancy_attribution as ea
from tests.analytics.test_stop_width_report import STAMP, stop_width_rows


@pytest.fixture(autouse=True)
def few_resamples(monkeypatch):
    monkeypatch.setattr(ea, "N_RESAMPLES", 200)


def _report(train=None, live=None) -> dict:
    return ea.build_stop_width_report(
        stop_width_rows(800) if train is None else train,
        stop_width_rows(120, live=True) if live is None else live,
        seed=42, generated_at=STAMP)


def test_the_markdown_carries_verdict_clauses_both_populations_and_the_tail():
    report = _report()
    md = ea.stop_width_markdown(report)
    assert md.startswith("# v226 stop-width attribution (2026-11-12, seed 42)\n")
    assert f"**Verdict: {report['verdict']['verdict']}**" in md
    for label in report["labels"]:
        # clause table, year table, TRAIN and live bucket tables, two removal tables
        assert md.count(f"| {label} |") == 6
    assert "| Bucket | N | ExpR | Δ | 95% CI | p | q | years Δ<0 |" in md
    assert "| Bucket | 2020 | 2021 | 2022 | 2023 |" in md
    assert "same-day loss share" in md and "never gates" in md
    assert "## What this is" in md and "Descriptive, not a veto." in md
    assert "## What each verdict buys" in md
    for name in ea.STUDY_VERDICTS:
        assert f"- **{name}**" in md
    assert md == ea.stop_width_markdown(report)          # deterministic


def test_sections_come_in_the_fixed_order():
    md = ea.stop_width_markdown(_report())
    order = ["## Verdict", "## TRAIN: the six pre-registered clauses", "## TRAIN buckets",
             "## Live buckets", "## stop_atr against atr_pct", "## What this is",
             "## What each verdict buys"]
    positions = [md.index(heading) for heading in order]
    assert positions == sorted(positions)


def test_the_markdown_names_the_candidates_or_none():
    report = _report()
    first = report["labels"][0]
    report["verdict"] = dict(report["verdict"], verdict="VETO-CANDIDATE", candidates=[first])
    md = ea.stop_width_markdown(report)
    assert f"Candidates: {first}." in md
    assert "**Verdict: VETO-CANDIDATE** -- licenses a veto idea, not a veto" in md
    report["verdict"] = dict(report["verdict"], verdict="NO CANDIDATE", candidates=[])
    assert "Candidates: none." in ea.stop_width_markdown(report)


def test_the_markdown_states_the_power_line():
    report = _report()
    report["verdict"] = dict(report["verdict"], verdict="UNDERPOWERED", powered=1)
    md = ea.stop_width_markdown(report)
    assert "**Verdict: UNDERPOWERED** -- leaves the question open" in md
    assert f"Powered buckets (N ≥ 300): 1 of {report['verdict']['family_size']}" in md


def test_the_edges_line_prints_two_decimals_or_none():
    report = _report()
    report["edges"] = [0.4149, 0.6]
    assert "outcome-blind): 0.41, 0.60." in ea.stop_width_markdown(report)
    report["edges"] = []
    assert "outcome-blind): none." in ea.stop_width_markdown(report)


def test_the_volatility_sentence_appears_only_when_flagged():
    sentence = "about ticker volatility, not stop placement"
    assert sentence in ea.stop_width_markdown(_report(train=stop_width_rows(800)))
    assert sentence not in ea.stop_width_markdown(_report(train=stop_width_rows(800, atr=False)))


def test_missing_numbers_render_as_n_a_and_bools_as_words():
    md = ea.stop_width_markdown(_report(live=[]))
    assert "n/a" in md
    assert "None" not in md.replace("clamped None", "").replace("None rows", "")
    assert "| yes |" in md or "| no |" in md
    assert "True" not in md and "False" not in md
