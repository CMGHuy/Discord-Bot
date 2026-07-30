import datetime as dt
import statistics
import time

import pytest

from swingbot.core.gate import run_checklist
from tests.fixtures.gate import uptrend_daily
from tests.fixtures.gate.plans import make_plan

EVENING = dt.datetime(2026, 7, 14, 23, 0, tzinfo=dt.timezone.utc)
QUIET_SNAP = {"built_at": "2026-07-14T22:00:00+00:00", "stale": False,
              "events": {"next_high_impact": None, "within_24h": [], "today": []}}


@pytest.mark.perf   # match the repo's existing perf marker name — verify at execution
def test_run_checklist_median_under_50ms():
    df = uptrend_daily(n=500)
    plan = make_plan(created_at="2026-07-13",
                     trigger_price=float(df["Close"].iloc[-1]))
    run_checklist("TEST", plan.strategy, plan, df,
                  macro_snap=QUIET_SNAP, now=EVENING)          # warm-up
    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        run_checklist("TEST", plan.strategy, plan, df,
                      macro_snap=QUIET_SNAP, now=EVENING)
        times.append(time.perf_counter() - t0)
    median = statistics.median(times)
    # 50 ms pure-compute budget/ticker -> a 60-ticker scan adds < 3 s.
    assert median < 0.050, f"median {median * 1000:.1f} ms — cache the swing_levels/" \
                           f"htf_trend calls per frame (they run in 4+ checks)"
