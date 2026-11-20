"""v238: book an arm row on a requested R basis.

``r_basis=None`` -- the default in every engine -- is today's booking and never reaches this
module: gross ``r_total`` for every row, Turtle Soup net through
``turtle_soup_research.net_r`` (v180). A requested basis books every row alike:
``"gross"`` is the walk's ``r_total``; ``"net"`` re-prices the row from its entry fill and
exit legs through ``frictions.net_r_legs`` -- planned risk, both sides slipped, one
round-trip commission, borrow over calendar days held on shorts only -- the one net-R
function v231 also books live journal rows with.

The basis is recorded on the arm FILE (``provenance["r_basis"]``, V238-3), never on a row:
``ArmTrade`` gains no field. A requested basis is refused under any non-v1 instrument, whose
fills and costs already shape ``r_total``.
"""
from __future__ import annotations

from swingbot.core.edge.frictions import net_r_legs

#: The bases an engine may book on (None = today's booking, outside this tuple).
R_BASES = ("net", "gross")


def holding_days(df, result) -> int:
    """Calendar days from the entry bar's date to the exit bar's date (the borrow clock)."""
    return int((df.index[result.exit_index] - df.index[result.entry_index]).days)


def check_basis(r_basis, *, instrument) -> None:
    """Refuse a basis an engine cannot honour: an unknown value, or any basis under an
    instrument other than v1. None always passes (today's booking)."""
    if r_basis is None:
        return
    if r_basis not in R_BASES:
        raise ValueError(f"unknown r_basis {r_basis!r}; expected one of {R_BASES} or None")
    version = "v1" if instrument is None else getattr(instrument, "version", None)
    if version != "v1":
        raise ValueError(f"r_basis={r_basis!r} needs the v1 instrument; instrument {version} "
                         "already prices its own fills and costs into r_total")


def booked_r(plan, result, df, *, r_basis: str) -> float:
    """The R one closed trade books on ``r_basis`` ("net" or "gross")."""
    if r_basis == "gross":
        return result.r_total
    if r_basis == "net":
        return net_r_legs(result.entry_price, plan.stop_loss, plan.direction, result.legs,
                          days=holding_days(df, result))
    raise ValueError(f"unknown r_basis {r_basis!r}; expected one of {R_BASES}")
