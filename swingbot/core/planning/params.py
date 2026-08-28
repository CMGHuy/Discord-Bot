"""Frozen v2 exit parameters, adaptive resolvers, and badge/quality helpers."""
from __future__ import annotations

import logging

from swingbot import config
from swingbot.core.backtesting.registry import Badge, decay_note, get_badge
from .plan_types import TradePlanV2

log = logging.getLogger("swing-bot.plan_engine")
# Same numbers backtest.py used before the extraction (parity-critical).
STRUCTURE_BUFFER_ATR = 0.25   # cushion beyond swing high/low, in ATR units
SR_VOLUME_STRENGTH_CEILING = 3.0
TRAIL_ATR_MULT = 2.5          # chandelier default; finalized by the Task 30 TRAIN grid
TP1_FRACTION = 0.5            # fixed by spec §5
RUNNER_FLOOR_FRACTION = 2.0 / 3.0   # v39: the runner's stop the instant TP1 fires locks
                                    # in this fraction of the entry->TP1 move (was 0.0,
                                    # i.e. plain breakeven). Spec:
                                    # docs/superpowers/specs/implemented/2026-08-20-v39-runner-floor-protection-design.md
DEFAULT_EXPIRY_BARS = 5

# Per-strategy exit-v2 overrides chosen by the Task 30 TRAIN grid under the
# pre-registered rule "WR>=80 and ExpR>0 and N>=30 and excl<=50%; max ExpR
# wins; else keep defaults" (docs/superpowers/results/2026-07-exit-v2-train-grid.txt).
# Missing key = defaults (trail 2.5, tp2 on). NEVER edit from validation data.
# Support/Resistance's winner (trail=2.5, tp2=levels) equals the defaults;
# EMA Crossover and Elliott Wave had no qualifying config. stop_entry won for
# no breakout-class strategy, so STRATEGY_ENTRY_TYPE stays empty.
# Applies to strategy-source plans only: the confluence pipeline ran its
# one-shot OOS validation (Task 41) with the defaults, so its behavior is
# pinned — build_confluence_plan deliberately does not read this table.
EXIT_V2_PARAMS: dict[str, dict] = {
    "VWAP":           {"trail_atr_mult": 2.5, "tp2": False},  # N=136  WR=83.1 ExpR=+0.216
    "Fibonacci":      {"trail_atr_mult": 3.0, "tp2": False},  # N=279  WR=81.7 ExpR=+0.183
    "RSI":            {"trail_atr_mult": 2.0, "tp2": False},  # N=608  WR=85.2 ExpR=+0.218
    "MACD":           {"trail_atr_mult": 2.0, "tp2": True},   # N=145  WR=83.4 ExpR=+0.090
    "MA Ribbon":      {"trail_atr_mult": 2.5, "tp2": False},  # N=259  WR=81.1 ExpR=+0.186
    "Break & Retest": {"trail_atr_mult": 3.0, "tp2": False},  # N=355  WR=80.3 ExpR=+0.085
    "RSI Divergence": {"trail_atr_mult": 2.0, "tp2": False},  # N=1702 WR=81.0 ExpR=+0.218
    "Volume Profile": {"trail_atr_mult": 3.0, "tp2": False},  # N=73   WR=82.2 ExpR=+0.180
}


def exit_params_for(strategy: str) -> dict:
    p = EXIT_V2_PARAMS.get(strategy, {})
    return {"trail_atr_mult": p.get("trail_atr_mult", TRAIL_ATR_MULT),
            "tp2": p.get("tp2", True)}


def _journal_entries() -> list:
    """Every journal entry, for the MAE-informed stop lookup (edge E31).
    Split out as a module-level seam so the lookup can be stubbed in tests
    without touching disk, and so the import stays lazy -- plan_engine has
    no business depending on the analytics package at import time."""
    from swingbot.core.analytics.journal import JournalStore
    return JournalStore().entries()


def _resolve_stop_mult(strategy: str) -> float | None:
    """Live-path resolution of E31's MAE-informed stop factor. Returns None
    -- meaning "size exactly as before" -- when the flag is off, when the
    strategy has fewer than stops.MIN_SAMPLE journaled winners, or when
    reading the journal fails at all. Sizing must never depend on an
    analytics file being readable."""
    if not config.DATA_DRIVEN_STOPS_ENABLED:
        return None
    try:
        from swingbot.core.edge.stops import mae_informed_stop_mult
        return mae_informed_stop_mult(_journal_entries(), strategy)
    except Exception as exc:
        log.warning("MAE-informed stop lookup failed for %s: %s -- sizing unchanged",
                    strategy, exc)
        return None


def _resolve_tp2_r(strategy: str) -> float | None:
    """Live-path resolution of E32's MFE-informed TP2 R-multiple. Same
    flag, same degrade-to-None contract as _resolve_stop_mult."""
    if not config.DATA_DRIVEN_STOPS_ENABLED:
        return None
    try:
        from swingbot.core.edge.stops import mfe_informed_tp2_r
        return mfe_informed_tp2_r(_journal_entries(), strategy)
    except Exception as exc:
        log.warning("MFE-informed TP2 lookup failed for %s: %s -- TP2 unchanged",
                    strategy, exc)
        return None


def _resolve_time_stop_days(strategy: str) -> int | None:
    """Live-path resolution of E32's time stop. Recorded on the plan for
    E48's recycler; it closes nothing by itself."""
    if not config.DATA_DRIVEN_STOPS_ENABLED:
        return None
    try:
        from swingbot.core.edge.stops import optimal_time_stop_days
        return optimal_time_stop_days(_journal_entries(), strategy)
    except Exception as exc:
        log.warning("Time-stop lookup failed for %s: %s -- not recorded", strategy, exc)
        return None


def _apply_quality(plan: TradePlanV2, quality_inputs: dict | None) -> None:
    if quality_inputs is None:
        return
    from swingbot.core.planning.quality import score_plan
    # confidence_level rides along in quality_inputs (set by
    # _build_quality_inputs from the live scan's item.conf.level) but is
    # not one of score_plan()'s own kwargs -- pop it before the **spread,
    # a plain dict passthrough would raise TypeError otherwise.
    quality_inputs = dict(quality_inputs)
    plan.confidence_level = quality_inputs.pop("confidence_level", None)
    q = score_plan(direction=plan.direction, badge_status=plan.badge, **quality_inputs)
    plan.quality_score = q.score
    plan.quality_breakdown = q.breakdown


def stamp_badge(plan: TradePlanV2) -> None:
    """Set badge + badge_stats from the committed validation registry."""
    b = get_badge(plan.source, plan.strategy, plan.horizon_key)
    plan.badge = b.status
    # run_date only -- badge_stats is persisted to plans.json, and a stored
    # decay verdict is wrong the day after it is written. Nothing here branches
    # on staleness: a stale badge and a fresh one with identical numbers build
    # byte-identical plans (tests/admin/test_badge_decay_surface.py).
    plan.badge_stats = {"status": b.status, "n": b.n, "win_rate": b.win_rate,
                        "expectancy_r": b.expectancy_r, "window": b.window,
                        "run_date": b.run_date}


def badge_stats_line(badge: Badge) -> str:
    window = badge.window.replace("-01-01..", "-").replace("-12-31", "") or "n/a"
    return (f"OOS {window}: N={badge.n}, WR {badge.win_rate:.1f}%, "
            f"ExpR {badge.expectancy_r:+.3f}{decay_note(badge.decay)}")



