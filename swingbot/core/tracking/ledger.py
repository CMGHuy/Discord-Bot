"""v93: the main/weak P&L ledger rule.

A trade's ledger is frozen at creation and never rewritten. ``main`` is
computed as "not weak" so records written before this field existed remain
where they always were. The two ledgers are never summed.
"""

MAIN = "main"
WEAK = "weak"


def ledger_for(source: str | None, badge_status: str | None) -> str:
    """Return the frozen ledger for a newly created plan or trade."""
    if source == "strategy" and badge_status == "WEAK":
        return WEAK
    return MAIN


def is_weak(trade: dict) -> bool:
    return trade.get("ledger") == WEAK


def is_main(trade: dict) -> bool:
    return not is_weak(trade)


def split_by_ledger(trades: list) -> tuple[list, list]:
    return ([trade for trade in trades if is_main(trade)],
            [trade for trade in trades if is_weak(trade)])
