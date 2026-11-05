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
from collections import Counter

import numpy as np

from swingbot.core.backtesting import acceptance
from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, NON_INFERIORITY_R,
                                                  VOLUME_MAX_CUT_PCT, AcceptanceResult,
                                                  ClauseResult, bootstrap_delta,
                                                  delta_expectancy_r, delta_standardised_win_rate,
                                                  expectancy_r, win_rate)
from swingbot.core.backtesting.arms import gap_reclaim_census, selection

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


#: The v72 removal-label null's circular-shift range (permutation_test.SHIFT_RANGE): >= 20 so
#: nothing almost aligns.
SHIFT_RANGE = (20, 200)
SPLIT_FIELDS = ("source", "direction", "horizon_key")
EARNINGS_UNAVAILABLE = ("unavailable: the v1 replay row (ArmTrade) carries no earnings date and no "
                        "as-of earnings archive exists (compression_research.py:7-13); the earnings "
                        "CSVs hold final report dates, so a cut on them would be lookahead")


def _order(trade) -> tuple:
    return (trade.ticker, trade.entry_date, trade.strategy, trade.horizon_key,
            trade.source or "", trade.direction or "")


def _rotatable(baseline, held: set, removed_keys: set) -> list:
    """Per ticker, in date order, the baseline trades the null may relabel (every baseline trade
    except the held re-priced ones) and their real removal labels."""
    groups: dict = {}
    for trade in sorted((t for t in baseline if t.key not in held), key=_order):
        groups.setdefault(trade.ticker, []).append(trade)
    return [(trades, np.array([t.key in removed_keys for t in trades])) for trades in groups.values()]


def _null_arm(groups, fixed, c_by: dict, shift: int) -> list:
    """One null component: the fixed trades plus every rotatable trade whose shifted label keeps
    it, as its component version when it has one (else its baseline version)."""
    arm = list(fixed)
    for trades, labels in groups:
        rolled = np.roll(labels, shift % len(labels))
        arm.extend(c_by.get(t.key, t) for t, gone in zip(trades, rolled) if not gone)
    return arm


def _null_draws(baseline, component, split: dict, n_perm: int, seed: int, statistic) -> list:
    """The valid (non-None) null statistics: re-priced trades held at their component version,
    added trades in every draw, the removal labels rotated by one seeded shift per draw."""
    held = {bt.key for bt, _ in split["repriced"]}
    fixed = [ct for _, ct in split["repriced"]] + list(split["added"])
    groups = _rotatable(baseline, held, {t.key for t in split["removed"]})
    c_by = {t.key: t for t in component}
    shifts = np.random.default_rng(seed).integers(*SHIFT_RANGE, size=n_perm)
    null = [statistic(baseline, _null_arm(groups, fixed, c_by, int(shift))) for shift in shifts]
    return [value for value in null if value is not None]


def _p_value(observed, valid: list) -> float | None:
    """Share of valid null draws at or above the observed statistic; None when undefined."""
    if observed is None or not valid:
        return None
    return float(np.mean([value >= observed for value in valid]))


def repriced_permutation(baseline, component, repriced: set, *, n_perm: int = 200, seed: int = 42,
                         statistic=delta_standardised_win_rate) -> dict:
    """v72 clause 5 for the v192 arms: the removal-label null of
    permutation_test.arm_pair_permutation (ticker-circular shift of the removed labels over the
    baseline, one shift per draw), with the re-priced trades held at their component version and
    the added trades kept in every draw, so the null rotates only which trades the veto removes.
    p = share of valid null draws at or above the observed statistic."""
    split = strata_split(baseline, component, repriced)
    observed = statistic(baseline, component)
    valid = _null_draws(baseline, component, split, n_perm, seed, statistic)
    p = _p_value(observed, valid)
    return {"observed_delta_win_rate_pp": observed, "p_value": p, "n": int(n_perm), "n_valid": len(valid),
            "seed": seed, "shift_range": list(SHIFT_RANGE), "removed": len(split["removed"]),
            "repriced": len(split["repriced"]), "added": len(split["added"]),
            "statistic": getattr(statistic, "__name__", "custom"),
            "instrument": "v192: v72 removal-label null, re-priced trades held at their component "
                          "version and added trades kept in every draw"}


def _interval(baseline, component, statistic, n_resamples: int, seed: int) -> dict:
    res = bootstrap_delta(baseline, component, statistic, n_resamples=n_resamples, seed=seed, cluster=CLUSTER)
    return {"point": res.point, "lo": res.lo, "hi": res.hi, "p_greater_than_zero": res.p_greater_than_zero}


def selection_cell(value, baseline, component, *, resolvable: bool, n_resamples: int,
                   seed: int) -> selection.CellEval:
    """Stage 1's cell for one g: eligible iff the point dExpR is at or above the -0.01R floor
    and Stage 0 found it resolvable. dWR is the standardised whole-window statistic; the
    expectancy is the component's (what select_cell's plateau check scores)."""
    d_exp = delta_expectancy_r(baseline, component)
    failed = [] if d_exp is not None and d_exp >= NON_INFERIORITY_R else ["expectancy_floor"]
    if not resolvable:
        failed.append("mde")
    ci = _interval(baseline, component, delta_standardised_win_rate, n_resamples, seed)
    disclosure = {"delta_expectancy_r": d_exp, "delta_win_rate_ci": [ci["lo"], ci["hi"]],
                  **selection.removed_disclosure(baseline, component)}
    return selection.CellEval(value, not failed, delta_standardised_win_rate(baseline, component),
                              acceptance.expectancy_r(component), failed, disclosure)


def _reading(baseline, component) -> dict:
    return {"component_n": len(component), "win_rate": win_rate(component),
            "expectancy_r": expectancy_r(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component)}


def ambiguous_sensitivity(baseline, component, ambiguous: set) -> dict:
    """The component with ambiguous reclaim bars read two ways: as booked (filled at E, then
    stopped, -1R) and as gap_no_reclaim cancels (the trade dropped)."""
    kept = [t for t in component if t.key not in ambiguous]
    return {"ambiguous_n": len(component) - len(kept), "as_fills": _reading(baseline, component),
            "as_cancels": _reading(baseline, kept)}


def _dollars(trade, fill: float, row: dict, shares: float) -> float:
    return trade.r_multiple * abs(fill - row["stop"]) * shares


def repriced_dollars(split: dict, census_rows, *, reference_account: float, risk_pct: float) -> dict:
    """Re-priced trades in dollars on a fixed reference account. Both arms hold the plan's own
    size, risk$ / |E - stop|; the baseline twin filled at the open, the re-priced trade at the
    reclaim fill, so each R converts at its own risk unit."""
    rows = {gap_reclaim_census.row_key(row): row for row in census_rows if row["reclaimed"]}
    risk = reference_account * risk_pct / 100.0
    base_total = comp_total = 0.0
    n = 0
    for bt, ct in split["repriced"]:
        row = rows.get(bt.key)
        if row is None or bt.r_multiple is None or ct.r_multiple is None:
            continue
        shares = risk / abs(row["entry"] - row["stop"])
        base_total += _dollars(bt, row["open_price"], row, shares)
        comp_total += _dollars(ct, row["fill_price"], row, shares)
        n += 1
    delta = comp_total - base_total
    return {"n": n, "reference_account": reference_account, "risk_pct": risk_pct, "risk_dollars": risk,
            "baseline_dollars": round(base_total, 2), "component_dollars": round(comp_total, 2),
            "delta_dollars": round(delta, 2), "mean_delta_dollars": round(delta / n, 2) if n else None}


def _pair_row(baseline, component) -> dict:
    return {"n_baseline": len(baseline), "n_component": len(component),
            "baseline_win_rate": win_rate(baseline), "component_win_rate": win_rate(component),
            "baseline_expectancy_r": expectancy_r(baseline), "component_expectancy_r": expectancy_r(component),
            "delta_win_rate_pp": delta_standardised_win_rate(baseline, component),
            "delta_expectancy_r": delta_expectancy_r(baseline, component)}


def _split_by(baseline, component, field: str) -> dict:
    """Descriptive split; it cannot rescue a pooled fail (spec § Gate)."""
    label = lambda trade: str(getattr(trade, field))       # noqa: E731
    values = sorted({label(t) for t in [*baseline, *component]})
    return {value: _pair_row([t for t in baseline if label(t) == value],
                             [t for t in component if label(t) == value]) for value in values}


def _top2_share(trades) -> float:
    counts = Counter(t.horizon_key for t in trades)
    return sum(n for _, n in counts.most_common(2)) / len(trades) if trades else 0.0


def report(baseline, component, census_rows, *, n_resamples: int, seed: int,
           reference_account: float = 100_000.0, risk_pct: float = 1.0) -> dict:
    """Every number spec § Reporting asks for at one stage, from one arm pair and its census."""
    split = strata_split(baseline, component, gap_reclaim_census.repriced_keys(census_rows))
    return {"n": {"baseline": len(baseline), "component": len(component)},
            "win_rate": {"baseline": win_rate(baseline), "component": win_rate(component)},
            "expectancy_r": {"baseline": expectancy_r(baseline), "component": expectancy_r(component)},
            "delta_win_rate_pp": _interval(baseline, component, delta_standardised_win_rate, n_resamples, seed),
            "delta_expectancy_r": _interval(baseline, component, delta_expectancy_r, n_resamples, seed),
            "outcome_flips": len(split["changed"]),
            "strata": strata_rows(split),
            "repriced_dollars": repriced_dollars(split, census_rows, reference_account=reference_account,
                                                 risk_pct=risk_pct),
            "ambiguous_sensitivity": ambiguous_sensitivity(baseline, component,
                                                           gap_reclaim_census.ambiguous_keys(census_rows)),
            "census": gap_reclaim_census.reachability_summary(census_rows),
            "splits": {field: _split_by(baseline, component, field) for field in SPLIT_FIELDS},
            "removed_top2_horizon_share": _top2_share(split["removed"]),
            "earnings_proximity": EARNINGS_UNAVAILABLE}
