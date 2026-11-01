"""v192: the gap-reclaim veto's frozen scoring (spec § Gate).

The v192 arms are never a subset: a reclaimed trade fills at E in the component and at the open
in the baseline (same key, re-priced), and a cancelled baseline trade frees StrategyEngine's
``open_until`` for later signals (added). ``acceptance.population_split`` cannot tell re-priced
from unchanged, ``_clause_mechanism`` would return SKIPPED and ``_clause_volume`` nets added
trades against removed ones. The strata here are frozen before TRAIN:

- removed: baseline keys absent from the component (the gap_no_reclaim cancels);
- repriced: keys in the census's reclaimed set present in both arms (reported, decides nothing);
- added: component keys absent from the baseline;
- unchanged: every other paired key.

Clause 6 is removed vs unchanged; clause 4 is removed / baseline N; clauses 1-3 are acceptance's
own under the week-cluster bootstrap; a SKIPPED clause fails (the permutation clause is SKIPPED
by design below VALIDATION and is scored only there). Open-through-stop and risk-cap cancels are
absent from both arms (the engines drop not_triggered rows), so they are in no stratum.
"""
from __future__ import annotations

import dataclasses

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, VOLUME_MAX_CUT_PCT,
                                                  AcceptanceResult, ClauseResult, expectancy_r,
                                                  win_rate)

CLUSTER = "week"
STRATA = ("removed", "repriced", "added", "unchanged")


def strata_split(baseline, component, repriced: set) -> dict:
    """Label every trade of both arms with its frozen stratum. ``repriced`` is the census's
    reclaimed key set; a key with no baseline twin labels nothing. ``changed`` discloses the
    paired trades (re-priced or unchanged) whose outcome differs."""
    b_by = {t.key: t for t in baseline}
    c_by = {t.key: t for t in component}
    pairs = [(bt, c_by[key]) for key, bt in b_by.items() if key in c_by]
    return {"removed": _unmatched(b_by, c_by),
            "repriced": _pairs_where(pairs, lambda bt, _: bt.key in repriced),
            "added": _unmatched(c_by, b_by),
            "unchanged": _pairs_where(pairs, lambda bt, _: bt.key not in repriced),
            "changed": _pairs_where(pairs, lambda bt, ct: bt.outcome != ct.outcome),
            "is_subset": False}


def _pairs_where(pairs: list, keep) -> list:
    """The (baseline, component) pairs for which ``keep(bt, ct)`` holds, in order."""
    return [(bt, ct) for bt, ct in pairs if keep(bt, ct)]


def _unmatched(by_key: dict, other: dict) -> list:
    """The trades of ``by_key`` whose key has no twin in ``other``, in insertion order."""
    return [t for key, t in by_key.items() if key not in other]


def mechanism_clause(split: dict) -> ClauseResult:
    """v72 clause 6 on the v192 strata: are the trades the veto removed the bad ones? Removed WR
    must sit below the unchanged stratum's and removed ExpR at or below zero. Re-priced trades
    are excluded from the comparator (their R unit differs between the arms)."""
    removed, unchanged = split["removed"], [ct for _, ct in split["unchanged"]]
    r_wr, k_wr, r_exp = win_rate(removed), win_rate(unchanged), expectancy_r(removed)
    if r_wr is None or k_wr is None or r_exp is None:
        return ClauseResult("mechanism", "FAIL",
                            "removed or unchanged population has no decided trades to compare", None, None)
    ok = r_wr < k_wr and r_exp <= 0.0
    return ClauseResult(
        "mechanism", "PASS" if ok else "FAIL",
        f"removed WR {r_wr:.2f}% (n={len(removed)}) vs unchanged {k_wr:.2f}% (n={len(unchanged)}, "
        f"re-priced excluded), removed ExpR {r_exp:+.4f}R (must be <= 0)", r_wr, k_wr)


def volume_clause(baseline, split: dict) -> ClauseResult:
    """v72 clause 4 on the v192 strata: the alert cut is the removed trades over the baseline N;
    added trades never offset a removal."""
    if not baseline:
        return ClauseResult("volume", "FAIL", "empty baseline arm", None, VOLUME_MAX_CUT_PCT)
    cut = 100.0 * len(split["removed"]) / len(baseline)
    ok = cut <= VOLUME_MAX_CUT_PCT
    return ClauseResult("volume", "PASS" if ok else "FAIL",
                        f"removed {len(split['removed'])} of {len(baseline)} baseline trades: cut "
                        f"{cut:+.2f}% vs max {VOLUME_MAX_CUT_PCT:.1f}%", cut, VOLUME_MAX_CUT_PCT)


def _split_counts(split: dict) -> dict:
    return {**{name: len(split[name]) for name in STRATA}, "changed": len(split["changed"]),
            "is_subset": False}


def evaluate_gap_reclaim(baseline, component, repriced: set, *, stage: str, permutation_p=None,
                         n_resamples: int = BOOTSTRAP_RESAMPLES, seed: int = 42) -> AcceptanceResult:
    """The v192 gate: acceptance.evaluate's clauses 1-3 and 5 under ``cluster="week"``, clauses 4
    and 6 from the strata, and a SKIPPED clause fails. The permutation clause is SKIPPED by design
    below VALIDATION (``acceptance._clause_permutation``) and is scored only at VALIDATION."""
    base = acceptance.evaluate(baseline, component, stage=stage, permutation_p=permutation_p,
                               n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    split = strata_split(baseline, component, repriced)
    replaced = {"volume": volume_clause(baseline, split), "mechanism": mechanism_clause(split)}
    clauses = tuple(replaced.get(clause.name, clause) for clause in base.clauses)
    scored = clauses if stage == "validation" else tuple(c for c in clauses if c.name != "permutation")
    return dataclasses.replace(base, clauses=clauses, split=_split_counts(split),
                               verdict=acceptance.verdict_of(scored, skipped_fails=True))


def _row(name: str, trades, twins) -> dict:
    return {"stratum": name, "n": len(trades),
            "decided": sum(1 for t in trades if t.outcome in acceptance.DECIDED),
            "win_rate": win_rate(trades), "expectancy_r": expectancy_r(trades),
            "baseline_win_rate": None if twins is None else win_rate(twins),
            "baseline_expectancy_r": None if twins is None else expectancy_r(twins)}


def strata_rows(split: dict) -> list[dict]:
    """One reporting row per stratum, in STRATA order. Paired strata report the component
    version and, beside it, the baseline twins; removed rows are the baseline trades."""
    return [_row("removed", split["removed"], None),
            _row("repriced", [ct for _, ct in split["repriced"]], [bt for bt, _ in split["repriced"]]),
            _row("added", split["added"], None),
            _row("unchanged", [ct for _, ct in split["unchanged"]], [bt for bt, _ in split["unchanged"]])]
