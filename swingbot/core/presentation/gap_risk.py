"""The one wording of the v183 gap-risk line.

Every alert channel (full embed, simple mirror, v81 ticket, email/push) and the
plan page take the line from here, so the copy cannot drift between them. Pure
text: imports nothing from ``scanning``.
"""
GAP_CUT_TEXT = "size cut for gap risk"
GAP_NA_TEXT = "gap risk n/a"


def _money(amount, currency: str) -> str:
    """Whole currency units with thousands separators; ``n/a`` for None."""
    return "n/a" if amount is None else f"{currency}{amount:,.0f}"


def gap_risk_line(sizing: dict | None, *, currency: str = "$") -> str | None:
    """``Risk $50 at stop · $100 on a p99 gap (4.0%) · size cut for gap risk``.

    None when the sizing carries no gap stamp (longs, rule-stop shorts,
    pre-v183 plans), so nothing new is printed for them.
    """
    if not sizing or "gap_sized" not in sizing:
        return None
    head = f"Risk {_money(sizing.get('risk_amount'), currency)} at stop"
    gap_amount, floor_pct = sizing.get("gap_risk_amount"), sizing.get("gap_floor_pct")
    if gap_amount is None or floor_pct is None:
        return f"{head} · {GAP_NA_TEXT}"
    line = f"{head} · {_money(gap_amount, currency)} on a p99 gap ({floor_pct:.1f}%)"
    return f"{line} · {GAP_CUT_TEXT}" if sizing["gap_sized"] else line
