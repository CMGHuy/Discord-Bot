import sys
from pathlib import Path
from types import SimpleNamespace as T
import pandas as pd
from tests.helpers import make_ohlcv
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

def test_laggard_rule_and_bearish_only(monkeypatch):
    import measure_bearish_arms as mba
    rows=[{"ticker":"AAA","horizon_key":"3m","trade":T(context={"rs_combined":10.},outcome="win",r_multiple=1.)},{"ticker":"BBB","horizon_key":"3m","trade":T(context={"rs_combined":80.},outcome="loss",r_multiple=-1.)}]
    assert [r["ticker"] for r in mba.apply_laggard_rule(rows)] == ["AAA"]
    frame=make_ohlcv([100.]*300); monkeypatch.setattr(mba,"run_backtest",lambda *a,**kw:T(trades=[T(direction="bearish",entry_date="2021-01-01",outcome="win",r_multiple=1.,context={}),T(direction="bullish",entry_date="2021-01-01",outcome="loss",r_multiple=-1.,context={})]))
    out=mba.bearish_arm_trades("MACD", {"AAA":frame}, {}, date_from="2020-01-01",date_to="2023-12-31",horizons=("3m",))
    assert out and all(r["trade"].direction=="bearish" for r in out)

def test_evaluate_shape():
    import measure_bearish_arms as mba
    rows=[{"ticker":"A","horizon_key":"3m","trade":T(outcome="win",r_multiple=1.)} for _ in range(35)]
    out=mba.evaluate("MACD",rows,{"2021":rows},horizons_mask=("3m",))
    assert set(out)>={"strategy","stage1","stage2","decision"}
