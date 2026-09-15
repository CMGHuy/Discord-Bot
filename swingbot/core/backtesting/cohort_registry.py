"""Frozen cohort lookup for measured trade outcomes.

This registry is deliberately a lookup rather than a score: it describes the
base rate for a plan shape without changing its confidence, gate, sizing, or
exit behaviour.  The committed JSON is generated once and plans retain the
verdict they received at creation time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


K = 100
N_FLOOR = 50
BAND_R = 0.15

_PATH = Path(__file__).with_name("cohort_registry.json")
_CACHE: dict | None = None


@dataclass
class Cohort:
    label: str
    n_live: int = 0
    n_backtest: int = 0
    win_rate: float = 0.0
    expectancy_r: float = 0.0
    window: str = ""
    run_date: str = ""


def cohort_key(direction: str, regime2_state: str) -> str:
    """Return the registry key for the plan's directional/regime cell."""
    return f"{direction}|{regime2_state}"


def blend(p_live: float | None, n_live: int, p_backtest: float | None, k: int = K) -> float:
    """Shrink a live estimate toward the frozen backtest prior.

    A cell the backtest never occupied has no prior to shrink toward --
    the live estimate stands alone rather than being dragged toward a
    fabricated zero (which would masquerade as "measured breakeven").
    """
    if p_backtest is None:
        return float(p_live) if p_live is not None else 0.0
    if p_live is None or n_live <= 0:
        return float(p_backtest)
    return (n_live * float(p_live) + k * float(p_backtest)) / (n_live + k)


def band(expectancy_r: float, pool_mean_r: float) -> str:
    """Classify a cell relative to the pooled expectancy."""
    if expectancy_r <= pool_mean_r - BAND_R:
        return "COHORT_POOR"
    if expectancy_r >= pool_mean_r + BAND_R:
        return "COHORT_STRONG"
    return "COHORT_TYPICAL"


def load_registry(path: Path | None = None) -> dict:
    """Load the committed registry, or an empty registry before generation."""
    global _CACHE
    if _CACHE is None or path is not None:
        src = path or _PATH
        _CACHE = (
            json.loads(src.read_text(encoding="utf-8"))
            if src.exists()
            else {"run_date": "", "window": "", "pool_mean_r": 0.0, "cells": {}}
        )
    return _CACHE


def reload_registry() -> None:
    """Clear the cached registry for tests or an explicit refresh."""
    global _CACHE
    _CACHE = None


def get_cohort(direction: str, regime2_state: str | None) -> Cohort:
    """Return the cell verdict, falling back safely to ``COHORT_UNKNOWN``."""
    if not regime2_state:
        return Cohort(label="COHORT_UNKNOWN")

    registry = load_registry()
    cell = (registry.get("cells") or {}).get(cohort_key(direction, regime2_state))
    if not cell:
        return Cohort(label="COHORT_UNKNOWN")

    n_live = int(cell.get("n_live", 0))
    n_backtest = int(cell.get("n_backtest", 0))
    win_rate = blend(cell.get("win_rate_live"), n_live, cell.get("win_rate_backtest"))
    expectancy_r = blend(
        cell.get("expectancy_r_live"), n_live, cell.get("expectancy_r_backtest")
    )
    label = (
        "COHORT_UNKNOWN"
        if n_live + n_backtest < N_FLOOR
        else band(expectancy_r, float(registry.get("pool_mean_r", 0.0)))
    )
    return Cohort(
        label=label,
        n_live=n_live,
        n_backtest=n_backtest,
        win_rate=win_rate,
        expectancy_r=expectancy_r,
        window=registry.get("window", ""),
        run_date=registry.get("run_date", ""),
    )
