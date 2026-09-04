# tests/backtesting/test_acceptance_render.py
from swingbot.core.backtesting.acceptance import (
    ArmTrade, evaluate, render_json, render_markdown,
)


def arms():
    b, c = [], []
    for t in range(20):
        for i in range(10):
            trade = ArmTrade(ticker=f"T{t}", strategy="MACD", horizon_key="3m",
                             entry_date=f"2021-03-{i + 1:02d}",
                             outcome="win" if i < 4 else "loss",
                             r_multiple=2.0 if i < 4 else -1.0, planned_rr=2.0)
            b.append(trade)
            if i < 8:
                c.append(trade)
    return b, c


def test_markdown_carries_every_clause_and_the_verdict():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    md = render_markdown(res, title="v99 test component",
                         window="2021-01-01..2021-12-31")
    for name in ("win_rate", "profit_floor", "geometry", "volume",
                 "permutation", "mechanism"):
        assert name in md
    assert "v99 test component" in md
    assert "2021-01-01..2021-12-31" in md
    assert res.verdict in md


def test_markdown_records_the_procedure_version_and_seed():
    """A results doc that does not say which procedure produced it cannot
    be re-read safely two quarters later."""
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=7)
    md = render_markdown(res, title="t", window="w")
    assert "acceptance v2" in md
    assert "seed 7" in md


def test_markdown_includes_the_per_stratum_table():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    md = render_markdown(res, title="t", window="w")
    assert "MACD" in md and "3m" in md


def test_notes_are_rendered_when_given():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    md = render_markdown(res, title="t", window="w",
                         notes="Cell selected on fold-train only.")
    assert "Cell selected on fold-train only." in md


def test_render_json_round_trips_the_clause_verdicts():
    res = evaluate(*arms(), stage="walkforward", n_resamples=200, seed=42)
    blob = render_json(res)
    assert blob["verdict"] == res.verdict
    assert blob["acceptance_version"] == 2
    assert {c["name"] for c in blob["clauses"]} == {
        "win_rate", "profit_floor", "geometry", "volume", "permutation",
        "mechanism"}
