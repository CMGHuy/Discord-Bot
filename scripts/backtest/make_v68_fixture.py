#!/usr/bin/env python3
"""Regenerate v68's VALIDATION population as a committed test fixture.

WHY THIS EXISTS: `data/v68_validation_dcb.json` was gitignored and is not
on this machine; neither is the `.log` the v68 results doc cites. The v72
acceptance gate uses that population as its regression anchor -- the new
gate must FAIL v68 -- so the population has to be reproducible and
committed rather than sitting in a gitignored path.

THIS IS NOT A RE-RUN OF THE PRE-REGISTRATION. v68's verdict is final and
unchanged: DEAD_CAT_BOUNCE_VETO's default stays false. Regenerating a
population to test an *instrument* makes no selection decision.

Reads its constants from measure_dcb_veto.py rather than restating them, so
the fixture cannot silently describe a different run than the one that
fired. Emits the richer ArmTrade shape (strategy + planned RR), which that
script's own row dialect does not carry.

Run: python scripts/backtest/make_v68_fixture.py   (~5-6 minutes)
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

from measure_dcb_veto import (  # noqa: E402
    BASE_GATES, CACHE_DIR, HORIZONS_TO_TEST, SAMPLE_EVERY, VALIDATION,
    load_frames,
)

from swingbot.core.backtesting.acceptance import arm_trade_from_plan  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios  # noqa: E402
from swingbot.core.market.chart_patterns import dead_cat_bounce  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402

#: The one cell v68's TRAIN selected and VALIDATION spent its shot on.
CELL = {"decline_pct": 15.0, "gap_required": False, "volume_ratio": None}
CELL_ID = "d15_gN_voff"
OUT = ROOT / "tests" / "backtesting" / "fixtures" / "v68_validation_arms.json"


def main() -> int:
    frames = load_frames(CACHE_DIR, ROOT / "data" / "watchlist.json",
                         None, SAMPLE_EVERY)
    print(f"{len(frames)} tickers | horizons {HORIZONS_TO_TEST} | "
          f"window {VALIDATION}", flush=True)
    baseline, component = [], []
    for n, (ticker, df) in enumerate(sorted(frames.items()), 1):
        kept = 0
        for hk in HORIZONS_TO_TEST:
            for i, plan in replay_scenarios(ticker, df, hk, gates=BASE_GATES,
                                            dcb_params=None):
                entry_date = str(df.index[i].date())
                if not (VALIDATION[0] <= entry_date <= VALIDATION[1]):
                    continue
                result = simulate_exit(df, i, plan, scale_out=True)
                trade = arm_trade_from_plan(plan, entry_date=entry_date,
                                            outcome=result.outcome,
                                            r_multiple=result.r_total)
                baseline.append(trade)
                vetoed = (plan.direction == "bullish" and
                          dead_cat_bounce(df.iloc[:i + 1], CELL)["detected"])
                if not vetoed:
                    component.append(trade)
                    kept += 1
        print(f"[{n}/{len(frames)}] {ticker}: kept {kept}", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "baseline": [asdict(t) for t in baseline],
        "component": [asdict(t) for t in component],
        "meta": {"cell": CELL_ID, "cell_params": CELL,
                 "window": list(VALIDATION), "horizons": HORIZONS_TO_TEST,
                 "sample_every": SAMPLE_EVERY, "gates": BASE_GATES,
                 "generated_by": "scripts/backtest/make_v68_fixture.py",
                 "note": "regenerated to test an instrument; v68's verdict "
                         "is unchanged and its budget stays spent"},
    }, indent=1))
    print(f"\nwrote {OUT} | baseline={len(baseline)} "
          f"component={len(component)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
