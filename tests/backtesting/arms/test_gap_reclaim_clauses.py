"""V192-16: the frozen v192 strata (removed / re-priced / added / unchanged), clause 6 scored
removed vs unchanged, clause 4 as removed / baseline N, and the SKIPPED-fails verdict."""
import datetime as dt

import pytest

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.backtesting.arms import gap_reclaim_clauses as grc

FAST = dict(n_resamples=300, seed=42)


def mk(ticker, outcome, date, *, r=None, rr=2.0, strategy="RSI", horizon="4w", direction="bullish"):
    r = {"win": 2.0, "loss": -1.0}.get(outcome, 0.0) if r is None else r
    return ArmTrade(ticker, strategy, horizon, date, outcome, r, rr, "strategy", direction)


def _date(i: int, extra_days: int = 0) -> str:
    """One ISO week per index, so the week-cluster bootstrap has hundreds of clusters."""
    return (dt.date(2021, 1, 4) + dt.timedelta(days=7 * i + extra_days)).isoformat()


def veto_arms(n_tickers=30, removed=(8, 9), repriced_r=2.2, added=True):
    """Per ticker ten baseline trades, indices 0-3 wins (+2R) and 4-9 losses (-1R). The veto
    removes ``removed``, re-prices index 0 (same outcome, the larger R a fill at E gives) and the
    strategy engine adds one later win. Returns (baseline, component, repriced keys)."""
    baseline, component, repriced = [], [], set()
    for t in range(n_tickers):
        ticker = f"T{t:02d}"
        for i in range(10):
            trade = mk(ticker, "win" if i < 4 else "loss", _date(t * 10 + i))
            baseline.append(trade)
            if i in removed:
                continue
            if i == 0:
                repriced.add(trade.key)
                component.append(mk(ticker, "win", trade.entry_date, r=repriced_r))
            else:
                component.append(trade)
        if added:
            component.append(mk(ticker, "win", _date(t * 10 + 9, extra_days=1)))
    return baseline, component, repriced


# --- strata_split ------------------------------------------------------------------------------

def _small():
    a, b, c = mk("A", "win", "2021-01-04"), mk("B", "loss", "2021-01-11"), mk("C", "win", "2021-01-18")
    a2, d = mk("A", "win", "2021-01-04", r=2.3), mk("D", "win", "2021-01-25")
    ghost = mk("Z", "win", "2021-02-01")
    return [a, b, c], [a2, c, d], {a.key, ghost.key}, (a, b, c, a2, d)


def test_strata_split_labels_the_four_strata():
    baseline, component, repriced, (a, b, c, a2, d) = _small()
    split = grc.strata_split(baseline, component, repriced)
    assert split["removed"] == [b] and split["added"] == [d]
    assert split["repriced"] == [(a, a2)] and split["unchanged"] == [(c, c)]
    assert split["changed"] == [] and split["is_subset"] is False


def test_a_repriced_key_without_a_baseline_twin_is_ignored():
    baseline, component, repriced, _ = _small()
    split = grc.strata_split(baseline, component, repriced)
    assert sum(len(split[name]) for name in grc.STRATA) == 4      # the ghost key labels nothing


def test_outcome_flips_are_disclosed_from_both_paired_strata():
    baseline, component, repriced, (a, b, c, a2, d) = _small()
    a_lost, c_lost = mk("A", "loss", a.entry_date), mk("C", "loss", c.entry_date)
    split = grc.strata_split(baseline, [a_lost, c_lost, d], repriced)
    assert split["changed"] == [(a, a_lost), (c, c_lost)]


def test_strata_rows_report_each_stratum_with_its_baseline_twin():
    baseline, component, repriced, _ = _small()
    rows = {row["stratum"]: row for row in grc.strata_rows(grc.strata_split(baseline, component, repriced))}
    assert list(rows) == list(grc.STRATA) == ["removed", "repriced", "added", "unchanged"]
    assert (rows["removed"]["n"], rows["removed"]["win_rate"], rows["removed"]["expectancy_r"]) == (1, 0.0, -1.0)
    assert rows["removed"]["baseline_win_rate"] is None
    assert rows["repriced"]["expectancy_r"] == pytest.approx(2.3)
    assert rows["repriced"]["baseline_expectancy_r"] == pytest.approx(2.0)
    assert rows["added"]["decided"] == 1 and rows["unchanged"]["win_rate"] == 100.0


# --- clauses 4 and 6 ---------------------------------------------------------------------------

def test_mechanism_passes_when_the_veto_removes_losers():
    baseline, component, repriced = veto_arms()
    clause = grc.mechanism_clause(grc.strata_split(baseline, component, repriced))
    assert clause.name == "mechanism" and clause.verdict == "PASS"
    assert clause.value == 0.0 and clause.threshold == pytest.approx(300 / 7)   # 3 wins of 7 unchanged
    assert "unchanged" in clause.detail and "re-priced excluded" in clause.detail


def test_mechanism_fails_when_the_veto_removes_winners():
    baseline, component, repriced = veto_arms(removed=(2, 3))
    assert grc.mechanism_clause(grc.strata_split(baseline, component, repriced)).verdict == "FAIL"


def test_mechanism_fails_when_the_removed_population_is_empty():
    baseline, component, repriced = veto_arms(removed=())
    clause = grc.mechanism_clause(grc.strata_split(baseline, component, repriced))
    assert clause.verdict == "FAIL" and "no decided" in clause.detail


def test_volume_counts_removed_trades_only_added_ones_never_offset_them():
    baseline, component, repriced = veto_arms(removed=(7, 8, 9))
    clause = grc.volume_clause(baseline, grc.strata_split(baseline, component, repriced))
    assert clause.name == "volume" and clause.value == pytest.approx(30.0) and clause.verdict == "FAIL"
    netted = acceptance.evaluate(baseline, component, stage="walkforward", **FAST).clause("volume")
    assert netted.value == pytest.approx(20.0) and netted.verdict == "PASS"   # why the strata version exists


def test_volume_fails_an_empty_baseline():
    assert grc.volume_clause([], grc.strata_split([], [], set())).verdict == "FAIL"


# --- evaluate_gap_reclaim ----------------------------------------------------------------------

def test_a_loser_removing_veto_passes_validation_with_a_permutation_p():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    assert result.verdict == "PASS", [(c.name, c.verdict, c.detail) for c in result.clauses]
    assert [c.name for c in result.clauses] == ["win_rate", "profit_floor", "geometry", "volume",
                                                "permutation", "mechanism"]
    assert result.cluster == grc.CLUSTER == "week"
    assert result.split == {"removed": 60, "repriced": 30, "added": 30, "unchanged": 210,
                            "changed": 0, "is_subset": False}


def test_the_stock_gate_would_have_skipped_clause_six_on_the_same_arms():
    baseline, component, _ = veto_arms()
    stock = acceptance.evaluate(baseline, component, stage="validation", permutation_p=0.01, **FAST)
    assert stock.clause("mechanism").verdict == "SKIPPED"


def test_validation_without_a_permutation_p_fails():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation", **FAST)
    assert result.clause("permutation").verdict == "FAIL" and result.verdict == "FAIL"


def test_below_validation_the_by_design_permutation_skip_does_not_fail():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="walkforward", **FAST)
    assert result.clause("permutation").verdict == "SKIPPED" and result.verdict == "PASS"


def test_any_other_skipped_clause_fails_the_gate(monkeypatch):
    baseline, component, repriced = veto_arms()
    skipped = acceptance.ClauseResult("geometry", "SKIPPED", "no planned RR or win R on either arm")
    monkeypatch.setattr(acceptance, "_clause_geometry", lambda b, c: skipped)
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    assert result.clause("geometry").verdict == "SKIPPED" and result.verdict == "FAIL"


def test_a_winner_removing_veto_fails_on_the_mechanism():
    baseline, component, repriced = veto_arms(removed=(2, 3))
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    assert result.clause("mechanism").verdict == "FAIL" and result.verdict == "FAIL"


def test_an_unknown_stage_is_refused():
    baseline, component, repriced = veto_arms(n_tickers=2)
    with pytest.raises(ValueError, match="stage must be one of"):
        grc.evaluate_gap_reclaim(baseline, component, repriced, stage="selection", **FAST)


def test_the_result_renders_through_the_stock_renderers():
    baseline, component, repriced = veto_arms()
    result = grc.evaluate_gap_reclaim(baseline, component, repriced, stage="validation",
                                      permutation_p=0.01, **FAST)
    payload = acceptance.render_json(result)
    assert payload["cluster"] == "week" and payload["split"]["repriced"] == 30
    assert "- removed: 60" in acceptance.render_markdown(result, title="v192", window="2024..2025")
