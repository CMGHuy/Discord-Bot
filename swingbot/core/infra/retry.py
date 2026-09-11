"""Generic transient-fault retry with exponential backoff.

Promoted out of marketdata/data_refresh.py (its original, single caller) so
the live scan's cold-fetch path (marketdata/data.py) can share the same
retry semantics instead of re-implementing them -- see that module's
get_daily_data/get_daily_data_batch.

Only worth using for TRANSIENT faults -- curl timeouts, rate limiting, a
momentarily empty response. A provider depth/permission limit is a refusal,
not a fault: it returns the same error every time, so retrying it is pure
waste.
"""
import logging
import time

log = logging.getLogger(__name__)

DEFAULT_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 2.0


def with_retry(fn, *args, attempts: int = None, base_delay: float = None,
               label: str = "", **kwargs):
    """Call fn(*args, **kwargs) with exponential backoff. Raises the last
    error if every attempt fails."""
    attempts = attempts or DEFAULT_ATTEMPTS
    base_delay = base_delay if base_delay is not None else DEFAULT_BASE_DELAY
    last = None
    for i in range(attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                delay = base_delay * (2 ** i)
                log.info("retry %s in %.1fs (attempt %d/%d): %s",
                         label, delay, i + 1, attempts, str(exc)[:120])
                time.sleep(delay)
    raise last
