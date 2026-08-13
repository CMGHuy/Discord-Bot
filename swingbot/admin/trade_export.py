"""CSV export of the trade log — one definition, two callers.

The Jinja route (`app.export_trades_csv`) and the v1 route
(`api_v1.trade_export`) both serve this file during the Angular migration,
and sub-project 6's acceptance walk byte-compares them. A second copy of
the field list would drift, and the drift would only show up at cutover.

Deliberately outside `api_v1/`: this module imports nothing from
`swingbot.admin`, so `app.py` can import it at module level without the
circular-import deadlock that api_v1's endpoint modules are subject to.
When the Jinja route is deleted at cutover, this module stays and only the
caller goes away.
"""
from __future__ import annotations

import csv
import io

# Order is part of the contract -- a spreadsheet built against this export
# breaks if columns move, so new fields append rather than insert.
CSV_FIELDS = [
    "id", "ticker", "strategy", "horizon_key", "direction",
    "confidence_level", "confidence_label", "confidence_score",
    "entry", "stop_loss", "take_profit", "target2", "risk_reward_ratio",
    "status", "opened_at", "closed_at", "exit_price", "close_reason",
]

FILENAME = "trades.csv"


def trades_csv_bytes(trades) -> bytes:
    """Serialise trade records to CSV.

    `extrasaction="ignore"` so a record carrying fields beyond CSV_FIELDS
    (every real one does) exports the declared columns instead of raising.
    The header row is always written, so an empty export is still a valid
    CSV that shows its schema rather than a zero-byte file.
    """
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for t in (trades or []):
        writer.writerow(t)
    return output.getvalue().encode("utf-8")
