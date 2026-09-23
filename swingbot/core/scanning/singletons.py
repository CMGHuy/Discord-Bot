"""Process-wide singletons for the scanning package.

Split out of engine.py (2026-09-23) to break a circular import: engine.py's
facade re-exports analyze.py's and scan_run.py's symbols, while analyze.py
and scan_run.py each imported `trade_log`/`state` back FROM engine. That
works only if something imports engine before analyze/scan_run ever get
imported directly -- the singleton assignments below ran (as part of
engine.py) before its re-export lines, so the circle closed successfully.
Import analyze or scan_run FIRST instead, and Python hits `from .engine
import trade_log` mid-import of engine, which then hits `from .analyze
import ScanItem` (or `from .scan_run import ScanProgress`) on the
still-executing original module and fails with "cannot import name ...
from partially initialized module".

This was invisible for a year because the full test suite ran as one
process and something always imported engine first. It broke live in CI
2026-09-23 when per-shard test isolation (each backend-test-* job its own
process) put tests/charts/ -- which imports scan_run directly, never
engine -- in a shard with nothing to establish that lucky order.

This module has no sibling imports, so it cannot be part of any cycle --
engine.py, analyze.py and scan_run.py all import `state`/`trade_log` from
HERE now, never from each other.
"""
from swingbot.core.infra.state import StateStore
from swingbot.core.tracking.performance import TradeLog

state = StateStore()
trade_log = TradeLog()
