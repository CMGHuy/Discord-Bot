"""v230: golden draws -- one v1 draw (null.draw_groups, next-open) and one
v2 draw (null_v2.draw_ticker_scope), captured once at V234-2 and compared
exactly. Never regenerate the file to make this pass: a changed draw is a
changed null, and v1 is frozen.

    python tests/backtesting/screen/test_null_golden.py --write   # V234-2 only

Inputs are integer draws and exact divisions, the same bits on every OS.
k = 3 / 4 keeps every pool larger than the draw, so the generator is pinned."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.screen import null, null_v2  # noqa: E402

GOLDEN_PATH = Path(__file__).with_name("golden") / "null_draws.json"
IDEA = "golden"
V1_K, V2_K = 3, 4
V2_TICKERS, V2_DATES, EVENT_TICKERS = 60, 24, 6


def v1_draw() -> dict:
    rng = np.random.default_rng(230)
    idx = pd.bdate_range("2019-01-01", "2019-03-29")
    df = pd.DataFrame({"Close": np.full(len(idx), 100.0)}, index=idx)
    event_pos = np.array([5, 20, 33, 47])
    eligible = rng.integers(0, 4, len(idx)) > 0
    eligible[event_pos] = False
    trend = rng.integers(0, 2, len(idx)) == 1
    g = null.draw_groups(df, event_pos, eligible, V1_K, null.null_seed(IDEA, "AAA"),
                         atr=None, trend=trend)
    return {"event_pos": g.event_pos.tolist(), "groups": [x.tolist() for x in g.groups]}


def v2_panels() -> dict:
    rng = np.random.default_rng(231)
    dates = pd.bdate_range("2016-01-04", periods=V2_DATES).to_numpy()
    panels = {}
    for i in range(V2_TICKERS):
        ticker = f"T{i:02d}"
        event = rng.integers(0, 6, V2_DATES) == 0
        eligible = (rng.integers(0, 5, V2_DATES) > 0) & ~event
        trend = rng.integers(0, 2, V2_DATES) == 1
        atr_pct = rng.integers(10, 60, V2_DATES) / 1000.0
        panels[ticker] = null_v2.TickerPanel(ticker, dates, eligible, trend, atr_pct, event)
    return panels


def v2_draw() -> list:
    panels = v2_panels()
    booked = {t: np.flatnonzero(panels[t].event) for t in sorted(panels)[:EVENT_TICKERS]}
    table = null_v2.draw_ticker_scope(null_v2.cross_section(panels), booked,
                                      idea=IDEA, k=V2_K).table
    return [[r.event_ticker, int(r.event_pos), r.event_date.strftime("%Y-%m-%d"),
             r.null_ticker, int(r.null_pos)] for r in table.itertuples(index=False)]


def capture() -> dict:
    return {"v1": v1_draw(), "v2": v2_draw()}


def _golden() -> dict:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_the_v1_draw_is_unchanged():
    assert v1_draw() == _golden()["v1"]


def test_the_v2_draw_is_unchanged():
    assert v2_draw() == _golden()["v2"]


def test_the_golden_draws_exercise_the_generators():
    golden = _golden()
    assert len(golden["v1"]["groups"]) >= 3
    assert all(len(g) == V1_K for g in golden["v1"]["groups"])
    assert len(golden["v2"]) >= 10 * V2_K


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    if not parser.parse_args(argv).write:
        parser.error("pass --write to capture the golden draws (V234-2 only)")
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(json.dumps(capture(), indent=1) + "\n",
                           encoding="utf-8", newline="\n")
    print(f"wrote {GOLDEN_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
