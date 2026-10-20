"""v175 § Testing, calibration: the per-look ``outside`` rate.

Each simulated book has a known daily R process. Its first 30 weeks (150
close days) build the 50-day band exactly as ``horizon_band`` does (week
blocks, the module's sampler and statistics, seed ``SEED``; 2 000 paths
per book to keep the file fast). The next 10 weeks (50 close days) are
the "look": the current run at their end and the window drawdown over
them, compared with the band's p95 through ``zone_of``. The rate is the
share of books whose look lands ``outside``.

Two processes, close-day R in {-1, +1.5, 0}:
  * i.i.d.: P = (0.50, 0.40, 0.10) every day;
  * week-correlated: each week is "bad" with probability 0.3
    (P = 0.75, 0.20, 0.05) else (0.40, 0.50, 0.10), days i.i.d. inside it.

Measured (400 books per process, generator seed 2026):
  * i.i.d.:          run 1.00%, drawdown 2.50%
  * week-correlated: run 0.75%, drawdown 3.25%
The current statistics are peak-to-now and the run in progress at one
moment, while the band holds the worst run and the deepest drawdown of a
whole path, so a look falls at or below the band's 5%. The panel caption
("Checked continuously, so 'beyond 95%' will sometimes appear by chance
alone") rests on these per-look rates: a single look is rarely outside,
and many looks over months make one more likely.
"""
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay

pytestmark = pytest.mark.slow

BOOKS = 400
HIST_WEEKS = 30
LOOK_WEEKS = 10
BAND_PATHS = 2_000
VALUES = np.array([-1.0, 1.5, 0.0])
START = date(2025, 1, 6)


def _iid_week(rng):
    return rng.choice(VALUES, size=5, p=[0.50, 0.40, 0.10])


def _correlated_week(rng):
    p = [0.75, 0.20, 0.05] if rng.random() < 0.3 else [0.40, 0.50, 0.10]
    return rng.choice(VALUES, size=5, p=p)


def _close_days(rs):
    return [CloseDay(START + timedelta(days=i), float(r), vb.day_kind(float(r)))
            for i, r in enumerate(rs)]


def _band_p95(blocks):
    paths = vb.sample_paths(blocks, vb.WINDOW, BAND_PATHS, np.random.default_rng(vb.SEED))
    run = int(np.percentile(vb.path_longest_runs(paths), vb.OUTSIDE_PCT, method="higher"))
    drawdown = round(float(np.percentile(vb.path_max_drawdowns(paths), vb.OUTSIDE_PCT)), 2)
    return run, drawdown


def _outside_rates(week):
    rng = np.random.default_rng(2026)
    run_out = drawdown_out = 0
    for _ in range(BOOKS):
        run_p95, drawdown_p95 = _band_p95([week(rng) for _ in range(HIST_WEEKS)])
        look = _close_days(np.concatenate([week(rng) for _ in range(LOOK_WEEKS)]))
        run, _ = vb.current_run(look)
        drawdown, _ = vb.window_drawdown(look)
        run_out += vb.zone_of(run, run_p95, run_p95) == "outside"
        drawdown_out += vb.zone_of(drawdown, drawdown_p95, drawdown_p95) == "outside"
    return run_out / BOOKS, drawdown_out / BOOKS


@pytest.mark.parametrize("week", [_iid_week, _correlated_week], ids=["iid", "week-correlated"])
def test_per_look_outside_rate(week):
    run_rate, drawdown_rate = _outside_rates(week)
    print(f"{week.__name__}: run {run_rate:.4f}, drawdown {drawdown_rate:.4f}")
    assert run_rate <= 0.05
    assert 0.01 <= drawdown_rate <= 0.08
