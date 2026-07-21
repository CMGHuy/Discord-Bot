"""The honest 10x math.

Risking `risk_pct` percent of equity per trade with expectancy
`expectancy_r` (in R) grows equity by risk_pct/100 * expectancy_r per
closed trade:

    equity_after = equity_before * (1 + risk_pct/100 * expectancy_r)

10x therefore takes ln(10) / ln(1 + g) closed trades. At 1% risk and
+0.10R that is ~2303 trades. There is no honest shortcut -- only three
levers: expectancy up, valid-trade frequency up, and drawdowns bounded
so compounding never has to restart. This module is the reality check
every other Edge component is measured against.
"""
from __future__ import annotations

import math

AVG_DAYS_PER_MONTH = 30.44  # 365.25 / 12


def per_trade_growth(risk_pct: float, expectancy_r: float) -> float:
    """Expected fractional equity growth per closed trade."""
    return (risk_pct / 100.0) * expectancy_r


def trades_to_multiple(multiple: float, risk_pct: float, expectancy_r: float) -> int | None:
    """Closed trades needed to multiply equity by `multiple`.

    Returns None when per-trade growth <= 0: a negative edge never
    compounds toward a target, it compounds toward zero.
    """
    g = per_trade_growth(risk_pct, expectancy_r)
    if g <= 0:
        return None
    if multiple <= 1:
        return 0
    return int(math.log(multiple) / math.log(1.0 + g))


def eta_days(trades_needed: int | None, trades_per_month: float) -> int | None:
    """Calendar days to complete `trades_needed` at the observed pace."""
    if trades_needed is None or trades_per_month <= 0:
        return None
    return int(math.ceil(trades_needed / trades_per_month * AVG_DAYS_PER_MONTH))


def growth_table(expectancies: tuple = (0.05, 0.10, 0.15, 0.20),
                 risks: tuple = (0.5, 1.0, 1.5, 2.0)) -> list[dict]:
    """The sensitivity grid `!growth` prints: what each (risk, expectancy)
    pair means in trades-to-10x. Sorted by expectancy, then risk."""
    rows = []
    for e in expectancies:
        for r in risks:
            rows.append({
                "risk_pct": r,
                "expectancy_r": e,
                "growth_per_trade": per_trade_growth(r, e),
                "trades_to_10x": trades_to_multiple(10, r, e),
            })
    return rows
