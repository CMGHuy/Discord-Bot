"""Module-level workers for tests/infra/test_swallowed.py's real-process
_run_bounded round trips. Spawn pickles a function by its module path, so
these cannot be lambdas or test-local closures."""
import logging
import time

from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)


def count_then_return(x):
    """Swallows twice under one tag, then returns x * 2."""
    for _ in range(2):
        try:
            raise ValueError("probe")
        except ValueError as exc:
            swallowed(log, "probe.count_then_return", exc, "probe %s", x,
                      level=logging.DEBUG)
    return x * 2


def sleep_forever():
    """Outlives any test budget, so _run_bounded's kill path runs."""
    time.sleep(3600)
