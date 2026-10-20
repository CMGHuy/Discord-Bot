"""v171 D6: one token bucket and breaker per provider, shared by every process.

Money first: a tier may take a token only while the bucket keeps its reserve
after the take. Tiers 1-3 reserve nothing, tier 4 keeps a quarter of the bucket
and tier 5 (every admin request, fresh reloads included) keeps half, so no admin
storm can ever spend budget the stop monitor, re-quote or scan need.

The per-minute knob is both the bucket size and its refill rate. ``take`` answers
honestly for every tier; only tiers 4-5 are ever deferred, by the caller.

Only ``MARKETDATA_LAYER == "on"`` touches the store; ``off``/``count`` always
allow. Any store error fails open (allow) with a rate-limited warning.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.db.repositories.market_shared import market_shared_repo
from swingbot.core.db.side_engine import side_connection
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata.shared import counters
from swingbot.core.marketdata.shared.kinds import (
    PROVIDER_ALPACA,
    PROVIDER_YF,
    Asker,
    resolve_asker,
)

log = logging.getLogger(__name__)

#: Share of the bucket that must remain after a take, by asker priority.
RESERVE_FRACTION = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.25, 5: 0.50}

_CAPACITY_ATTR = {
    PROVIDER_ALPACA: "ALPACA_BUDGET_PER_MINUTE",
    PROVIDER_YF: "YF_BUDGET_PER_MINUTE",
}


class BudgetDeferred(RuntimeError):
    """A tier 4-5 provider call was refused by the shared budget; the layer serves the freshest cached value with its age instead."""


def _on() -> bool:
    return config.MARKETDATA_LAYER == "on"


def capacity(provider: str) -> float:
    """Bucket size (and per-minute refill) for ``provider``; ValueError for an unknown one."""
    attr = _CAPACITY_ATTR.get(provider)
    if attr is None:
        raise ValueError(f"no shared budget for provider {provider!r}")
    return float(getattr(config, attr))


def take(provider: str, asker: Asker) -> bool:
    """Take one shared token for ``asker``; False only when its tier's reserve would be breached."""
    if not _on():
        return True
    asker = resolve_asker(asker)
    cap = capacity(provider)
    reserve = cap * RESERVE_FRACTION[asker.priority]
    try:
        with side_connection() as conn:
            return bool(market_shared_repo().take_token(provider, cap, cap, reserve, conn=conn))
    except Exception as exc:  # noqa: BLE001 - the layer fails open
        swallowed(log, "marketdata.budget.take", exc, level=logging.DEBUG)
        counters.warn_fail_open("budget take", exc)
        return True


def breaker_allows(provider: str) -> bool:
    """False only while the provider's shared breaker window is open."""
    if not _on():
        return True
    try:
        with side_connection() as conn:
            _fails, open_until = market_shared_repo().breaker_state(provider, conn=conn)
    except Exception as exc:  # noqa: BLE001 - the layer fails open
        swallowed(log, "marketdata.budget.breaker_read", exc, level=logging.DEBUG)
        counters.warn_fail_open("breaker read", exc)
        return True
    return open_until is None or open_until <= datetime.now(timezone.utc)


def breaker_record(provider: str, ok: bool) -> None:
    """Record one provider call's verdict in the shared breaker (Alpaca breaker knobs)."""
    if not _on():
        return
    try:
        with side_connection() as conn:
            market_shared_repo().breaker_record(
                provider, ok, int(config.ALPACA_BREAKER_FAILURES),
                float(config.ALPACA_BREAKER_COOLDOWN_SECONDS), conn=conn)
    except Exception as exc:  # noqa: BLE001 - the layer fails open
        swallowed(log, "marketdata.budget.breaker_write", exc, level=logging.DEBUG)
        counters.warn_fail_open("breaker write", exc)
