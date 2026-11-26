"""The open-position status-bar arithmetic, as pure functions.

`trades.py` is the caller (it attaches the five bar keys to every row);
`frontend/src/app/ui/position-progress.ts` mirrors these functions so the
client can redraw the bar when a live overlay replaces the price, and
`tests/fixtures/v248/progress_cases.json` is the contract both sides must
satisfy. A bar drawn from yesterday's close (`PRICE_PREV_CLOSE`) keeps its
positions but is never urgent: neutral band, no blink, a "not live" label.
"""
from __future__ import annotations

from swingbot.core.tracking.performance import trade_proximity

PRICE_LIVE = "live"
PRICE_PREV_CLOSE = "prev_close"
PREV_CLOSE_LABEL = "At prev close (not live)"
TERMINAL_STATUSES = frozenset({"CLOSED", "CANCELLED"})


def _prev_close_bar(fields: dict, price_kind: str) -> dict:
    """Index Decision 2: a bar drawn from yesterday's close is never urgent."""
    if price_kind != PRICE_PREV_CLOSE or fields["progress_pct"] is None:
        return fields
    return {**fields, "progress_band": "neutral", "blink_seconds": None,
            "status_label": PREV_CLOSE_LABEL}


def status_fields(row: dict, price: float | None, *, price_kind: str = PRICE_LIVE) -> dict:
    """The status-bar numbers, from the two functions that already own them.

    `trade_proximity` (core/performance.py) owns urgency and the label -- it
    is the same computation the bot's own near-close alerts use, so a second
    implementation here could make the UI and the alerts disagree about how
    close a trade is to its stop. The 0..100 position is the dashboard's
    (`admin/dashboard.py`, `pos_pct`), restated here rather than imported
    because that module builds a whole Jinja view model to produce it -- and
    that module is deleted at NG57.

    No colour is returned. The band names which pair of tokens the client
    interpolates between; the palette lives in tokens.css, so a repaint is a
    CSS change and never an API change. See spec v18 Decision 5.
    """
    entry, sl, tp = row.get("entry"), row.get("stop_loss"), row.get("target")
    direction = row.get("direction") or "bullish"
    label_only = {"progress_pct": None, "entry_pct": None, "progress_band": None,
                  "blink_seconds": None, "status_label": "No live price"}

    if price is None or not all(isinstance(v, (int, float)) for v in (entry, sl, tp)):
        return label_only

    prox = trade_proximity(direction, entry, sl, tp, price)
    is_bull = direction == "bullish"
    span = (tp - sl) if is_bull else (sl - tp)
    if span <= 0:
        # Malformed record -- stop on the wrong side of the target. Degrade to
        # a label rather than render a bar that is confidently backwards.
        return label_only

    pos = ((price - sl) if is_bull else (sl - price)) / span * 100
    ent = ((entry - sl) if is_bull else (sl - entry)) / span * 100
    band = ("toward_target" if prox["proximity"] > 0.15
            else "toward_stop" if prox["proximity"] < -0.15
            else "neutral")
    return _prev_close_bar({
        # Clamped: price runs past the stop or target all the time, and a bar
        # is 0..100 by definition. The band and label still carry "past it".
        "progress_pct": max(0.0, min(100.0, round(pos, 1))),
        "entry_pct": max(0.0, min(100.0, round(ent, 1))),
        "progress_band": band,
        "blink_seconds": prox["blink_seconds"],
        "status_label": prox["label"],
    }, price_kind)


def trailing_bar_fields(row: dict, price: float | None, *, price_kind: str = PRICE_LIVE) -> dict:
    """The status bar for a PARTIAL runner that has no TP2.

    There is no target to measure toward, so the bar runs from the trailing
    stop (0% -- one more tick against the runner and it is stopped out) to the
    best price since TP1 (100% -- a new extreme). Without a live price or a
    recorded best price there is nothing honest to draw, and the cell falls
    back to its chip.
    """
    chip = {"progress_pct": None, "entry_pct": None, "progress_band": None,
            "blink_seconds": None, "status_label": row["status"]}
    stop, best = row.get("stop_loss"), row.get("runner_best")
    if price is None or not all(isinstance(v, (int, float)) for v in (stop, best)):
        return chip
    is_bull = row.get("direction") != "bearish"
    span = (best - stop) if is_bull else (stop - best)
    if span <= 0:
        return chip
    pos = max(0.0, min(100.0, ((price - stop) if is_bull else (stop - price)) / span * 100))
    leg = row.get("banked_exit_price")
    ent = ((leg - stop) if is_bull else (stop - leg)) / span * 100 if isinstance(leg, (int, float)) else 0.0
    band = "toward_target" if pos >= 66 else "toward_stop" if pos <= 33 else "neutral"
    label = ("Near trailing stop" if band == "toward_stop"
             else "Near best price" if band == "toward_target" else "Trailing")
    # Pulse faster the nearer the stop, same urgency scale as trade_proximity.
    urgency = max(0.0, 1.0 - pos / 50.0)
    return _prev_close_bar({
        "progress_pct": round(pos, 1),
        "entry_pct": max(0.0, min(100.0, round(ent, 1))),
        "progress_band": band, "blink_seconds": round(2.2 - 1.6 * urgency, 2),
        "status_label": label}, price_kind)


def uses_trailing_bar(row: dict) -> bool:
    return row.get("bar_kind") == "trailing" and row["status"] not in TERMINAL_STATUSES


def row_progress(row: dict, price: float | None, *, price_kind: str = PRICE_LIVE) -> dict:
    """The five bar keys for one row, whichever kind of bar it carries."""
    if uses_trailing_bar(row):
        return trailing_bar_fields(row, price, price_kind=price_kind)
    if row["status"] in TERMINAL_STATUSES or row["status"] == "PENDING":
        # Nothing has opened, or it is already over: the chip is the status.
        return {"progress_pct": None, "entry_pct": None, "progress_band": None,
                "blink_seconds": None, "status_label": row["status"]}
    return status_fields(row, price, price_kind=price_kind)
