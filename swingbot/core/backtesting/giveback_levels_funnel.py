"""v178 funnel logic: stages 0-2, the stage-3 pick, Holm, cells looked at.

Pure functions over the v178 row contract (one row per entry, the result of
every arm under ``row["arms"][arm_id]``; plan v178 index, "Row contract").
Every comparison is paired on the same entries against control A, the live
fixed 5%. The rules are the spec's, frozen 2026-10-19
(docs/superpowers/specs/implemented/2026-10-19-v178-runner-giveback-levels-preregistration-design.md
§ The test). Nothing here simulates and nothing reads past the walk-forward
windows: VALIDATION is the script's one shot through validate_component.py.
"""
from __future__ import annotations

import numpy as np

from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, CLOSED, ArmTrade,
                                                  bootstrap_delta, delta_expectancy_r,
                                                  mde_paired)
from swingbot.core.backtesting.arms.windows import STAGES
from swingbot.core.backtesting.backtest_wf import (GATE_MIN_IMPROVING_FOLDS, gate,
                                                   plateau_report)
from swingbot.core.backtesting.instrument.stats import (WEEK_BOOTSTRAP_RESAMPLES,
                                                        week_cluster_bootstrap)

#: Control A's fixed give-back, percent of the best close (the live v176 rule).
PCT = 5.0
#: The frozen arms. No other value is ever run (spec § The rules).
ARMS: dict[str, dict] = {
    "A": {"enabled": True, "mode": "pct"},
    "B": {"enabled": False, "mode": "pct"},
    "R0.75": {"enabled": True, "mode": "range", "k": 0.75},
    "R1.00": {"enabled": True, "mode": "range", "k": 1.0},
    "R1.25": {"enabled": True, "mode": "range", "k": 1.25},
    "S0.25": {"enabled": True, "mode": "profit_share", "f": 0.25},
    "S0.33": {"enabled": True, "mode": "profit_share", "f": 0.33},
    "S0.50": {"enabled": True, "mode": "profit_share", "f": 0.50},
}
CONTROLS = ("A", "B")
CANDIDATES = ("R0.75", "R1.00", "R1.25", "S0.25", "S0.33", "S0.50")
FAMILIES = {"R": ("R0.75", "R1.00", "R1.25"), "S": ("S0.25", "S0.33", "S0.50")}
FAMILY_PARAM = {"R": ("k", (0.75, 1.0, 1.25)), "S": ("f", (0.25, 0.33, 0.50))}
#: Stage 2: a fold counts as improving only with this many changed exits.
MIN_CHANGED_PER_FOLD = 30
#: Stage 1: fold-train windows each family arm must share the adopted sign on.
SAME_SIGN_MIN_WINDOWS = 2


def pooled_window() -> tuple[str, str]:
    """The union of the three nested fold-train windows (all from 2018-06-01)."""
    return STAGES["selection"].signal_window


def _labelled(stage: str) -> list[tuple[str, tuple[str, str]]]:
    return [(label, (lo, hi)) for label, lo, hi in STAGES[stage].folds]


def fold_train_windows() -> list[tuple[str, tuple[str, str]]]:
    return _labelled("selection")


def fold_test_windows() -> list[tuple[str, tuple[str, str]]]:
    return _labelled("walkforward")


def rows_in(rows: list[dict], window: tuple[str, str]) -> list[dict]:
    """Rows whose signal date lies in the window, both ends included."""
    lo, hi = window
    return [r for r in rows if lo <= r["signal_date"] <= hi]


def arm_trades(rows: list[dict], arm: str) -> list[ArmTrade]:
    """One ArmTrade per row for ``arm``, R net of frictions."""
    return [ArmTrade(ticker=r["ticker"], strategy=r["strategy"], horizon_key=r["horizon_key"],
                     entry_date=r["signal_date"], outcome=r["arms"][arm]["outcome"],
                     r_multiple=r["arms"][arm]["r_net"], planned_rr=r["planned_rr"],
                     source=r["source"], direction=r["direction"])
            for r in rows]


def _exit(row: dict, arm: str) -> tuple:
    res = row["arms"][arm]
    return res["exit_index"], res["exit_price"]


def changed_count(rows: list[dict], arm: str, *, against: str = "A") -> int:
    """Rows whose exit (bar, price) differs between ``arm`` and ``against``."""
    return sum(_exit(r, arm) != _exit(r, against) for r in rows)


def paired_delta(rows, arm, *, against="A", n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict:
    """ΔExpR (arm - against) with the ticker-cluster bootstrap; ``p`` is the
    one-sided share of draws at or below zero."""
    boot = bootstrap_delta(arm_trades(rows, against), arm_trades(rows, arm),
                           delta_expectancy_r, n_resamples=n_resamples, seed=seed)
    return {"arm": arm, "against": against, "n": len(rows),
            "changed": changed_count(rows, arm, against=against), "delta_r": boot.point,
            "ci_lo": boot.lo, "ci_hi": boot.hi, "p": boot.p_greater_than_zero}


def week_interval(rows, arm, *, against="A", n_resamples=WEEK_BOOTSTRAP_RESAMPLES) -> dict:
    """The week-clustered 95% interval of ΔExpR. Descriptive, never gating."""
    draws = week_cluster_bootstrap(arm_trades(rows, against), arm_trades(rows, arm),
                                   delta_expectancy_r, n_resamples=n_resamples)
    if draws.size == 0:
        return {"lo": None, "hi": None}
    return {"lo": float(np.percentile(draws, 2.5)), "hi": float(np.percentile(draws, 97.5))}


def _resolvable(effect: float | None, mde: float | None) -> bool:
    """Refused when the measured effect is below the paired MDE. An effect at
    or below zero is refused as well; that only matters when the MDE is zero."""
    return effect is not None and mde is not None and effect > 0 and effect >= mde


def stage0(rows, arm, *, n_resamples=BOOTSTRAP_RESAMPLES) -> dict:
    """Stage 0 on the pooled fold-train window: the measured paired ΔExpR
    (arm - A) against acceptance.mde_paired on the same pairs."""
    pooled = rows_in(rows, pooled_window())
    out = paired_delta(pooled, arm, n_resamples=n_resamples)
    mde = mde_paired(arm_trades(pooled, "A"), arm_trades(pooled, arm), delta_expectancy_r,
                     observed_n=len(pooled), target_n=len(pooled), n_resamples=n_resamples)
    return {**out, "mde_paired": mde,
            "verdict": "RESOLVABLE" if _resolvable(out["delta_r"], mde) else "REFUSED"}


def fold_train_deltas(rows, arm) -> list[float | None]:
    """ΔExpR (arm - A) on each fold-train window, in fold order."""
    return [delta_expectancy_r(arm_trades(sub, "A"), arm_trades(sub, arm))
            for sub in (rows_in(rows, window) for _, window in fold_train_windows())]


def _sign(value: float | None) -> int:
    if value is None:
        return 0
    return (value > 0) - (value < 0)


def _same_sign(sign: int, deltas_by_arm: dict[str, list]) -> dict:
    counts = {arm: sum(1 for d in deltas if d is not None and _sign(d) == sign)
              for arm, deltas in deltas_by_arm.items()}
    passed = sign != 0 and all(c >= SAME_SIGN_MIN_WINDOWS for c in counts.values())
    return {"sign": sign, "windows_by_arm": counts, "pass": passed}


def _adopt(family: str, stage0_by_arm: dict[str, dict]) -> str | None:
    """Highest pooled ΔExpR among the family's arms still open after stage 0."""
    open_arms = [a for a in FAMILIES[family] if stage0_by_arm[a]["verdict"] == "RESOLVABLE"]
    if not open_arms:
        return None
    return max(open_arms, key=lambda a: stage0_by_arm[a]["delta_r"])


def _plateau(family: str, pooled: dict, adopted: str) -> dict:
    param, grid = FAMILY_PARAM[family]
    arms = FAMILIES[family]
    if any(pooled[a] is None for a in arms):
        return {"param": param, "grid": list(grid), "adopted": grid[arms.index(adopted)],
                "is_plateau": False, "reason": "an arm has no pooled ΔExpR"}
    return plateau_report(param, list(grid), [pooled[a] for a in arms],
                          grid[arms.index(adopted)])


def stage1(rows, family: str, stage0_by_arm: dict[str, dict]) -> dict:
    """Stage 1 per family: plateau_report on the pooled ΔExpR, plus every
    family arm sharing the adopted arm's sign on >= 2 of 3 fold-train windows."""
    arms = FAMILIES[family]
    pooled = {a: stage0_by_arm[a]["delta_r"] for a in arms}
    fold_train = {a: fold_train_deltas(rows, a) for a in arms}
    adopted = _adopt(family, stage0_by_arm)
    out = {"family": family, "adopted": adopted, "pooled": pooled, "fold_train": fold_train,
           "plateau": None, "same_sign": None}
    if adopted is None:
        return {**out, "verdict": "NO-CANDIDATE"}
    plateau = _plateau(family, pooled, adopted)
    same = _same_sign(_sign(pooled[adopted]), fold_train)
    verdict = "PASS" if plateau["is_plateau"] and same["pass"] else "FAIL"
    return {**out, "plateau": plateau, "same_sign": same, "verdict": verdict}


def _closed(trades) -> int:
    return sum(t.outcome in CLOSED for t in trades)


def _fold(rows, arm, label, window) -> dict:
    sub = rows_in(rows, window)
    base, comp = arm_trades(sub, "A"), arm_trades(sub, arm)
    delta = delta_expectancy_r(base, comp)
    changed = changed_count(sub, arm)
    return {"test_year": label, "delta_expectancy_r": delta,
            "n": min(_closed(base), _closed(comp)), "changed": changed,
            "improving": delta is not None and delta > 0 and changed >= MIN_CHANGED_PER_FOLD}


def stage2(rows, arm) -> dict:
    """Stage 2: backtest_wf.gate on the fold-test years (>= 2 of 3 improving,
    none below -0.05R, n >= 30), with improving counted only on folds that
    have >= MIN_CHANGED_PER_FOLD changed exits."""
    folds = [_fold(rows, arm, label, window) for label, window in fold_test_windows()]
    gate_verdict = gate({"folds": folds})
    improving = sum(f["improving"] for f in folds)
    deltas = [f["delta_expectancy_r"] for f in folds]
    mean = None if any(d is None for d in deltas) else float(np.mean(deltas))
    passed = gate_verdict == "PASS" and improving >= GATE_MIN_IMPROVING_FOLDS
    return {"arm": arm, "folds": folds, "gate": gate_verdict, "improving_folds": improving,
            "mean_delta_r": mean, "verdict": "PASS" if passed else "FAIL"}


def pick_stage3(stage2_by_arm: dict[str, dict]) -> str | None:
    """The one arm for VALIDATION: best stage-2 mean ΔExpR among passes; a
    tie goes to the simpler rule, family R."""
    passed = _stage2_passes(stage2_by_arm)
    if not passed:
        return None
    best = max(passed.values())
    tied = sorted(arm for arm, mean in passed.items() if mean == best)
    family_r = [arm for arm in tied if arm in FAMILIES["R"]]
    return (family_r or tied)[0]


def _stage2_passes(stage2_by_arm: dict[str, dict]) -> dict[str, float]:
    """arm -> stage-2 mean ΔExpR, for the passes that carry a mean."""
    return {arm: r["mean_delta_r"] for arm, r in stage2_by_arm.items()
            if r["verdict"] == "PASS" and r["mean_delta_r"] is not None}


def holm(pvalues: dict[str, float | None]) -> dict[str, float | None]:
    """Holm step-down adjusted p values; None passes through and is not counted."""
    present = sorted((p, arm) for arm, p in pvalues.items() if p is not None)
    m = len(present)
    out: dict[str, float | None] = {arm: None for arm in pvalues}
    running = 0.0
    for i, (p, arm) in enumerate(present):
        running = max(running, min(1.0, (m - i) * p))
        out[arm] = running
    return out


def cells_looked_at(*, arms=6, fold_train=3, fold_test_arms=6, fold_test=3, horizons=10,
                    control_b=6, blocks=7, regime_arms=3, sensitivity=0) -> int:
    """The spec's frozen count: 36 gating + 60 per-horizon + 6 control-B + 42
    block + 6 regime cells = 150, plus the sensitivity cells if they run."""
    return (arms * fold_train + fold_test_arms * fold_test + arms * horizons + control_b
            + arms * blocks + regime_arms * 2 + sensitivity)


def run_funnel(rows, *, n_resamples=BOOTSTRAP_RESAMPLES) -> dict:
    """Stages 0-2 on TRAIN-side rows, stopping at the first stage that closes
    every arm; ``stage3_arm`` is the single VALIDATION candidate or None."""
    out = _stage0_summary(rows, n_resamples)
    if not any(r["verdict"] == "RESOLVABLE" for r in out["stage0"].values()):
        return {**out, "stopped_at": "stage0"}
    out["stage1"] = {family: stage1(rows, family, out["stage0"]) for family in FAMILIES}
    adopted = [r["adopted"] for r in out["stage1"].values() if r["verdict"] == "PASS"]
    if not adopted:
        return {**out, "stopped_at": "stage1"}
    out["stage2"] = {arm: stage2(rows, arm) for arm in adopted}
    pick = pick_stage3(out["stage2"])
    return {**out, "stopped_at": None if pick else "stage2", "stage3_arm": pick}


def _stage0_summary(rows, n_resamples: int) -> dict:
    """Stage 0 for every candidate, its Holm-adjusted p values and the
    descriptive week-clustered intervals on the pooled fold-train window."""
    s0 = {arm: stage0(rows, arm, n_resamples=n_resamples) for arm in CANDIDATES}
    pooled = rows_in(rows, pooled_window())
    return {"stage0": s0, "stage1": {}, "stage2": {}, "stopped_at": None, "stage3_arm": None,
            "holm": holm({arm: s0[arm]["p"] for arm in CANDIDATES}),
            "week_interval": {arm: week_interval(pooled, arm, n_resamples=n_resamples)
                              for arm in CANDIDATES}}
