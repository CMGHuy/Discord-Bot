import datetime as dt
import sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"scripts"/"backtest"))
import measure_earnings_blackout as meb
from swingbot.core.backtesting.acceptance import ArmTrade
from swingbot.core.market.earnings_calendar import CsvSource
from swingbot.core.market.session import SessionCalendar

def calendar(): return SessionCalendar(ts.date() for ts in pd.bdate_range("2019-01-01","2019-12-31"))
def test_positions_and_exposure_row(tmp_path):
    (tmp_path/"AAA.csv").write_text("report_date,timing,report_ts_et\n2019-05-02,after_close,x\n2019-02-01,before_open,x\n")
    cal=calendar();positions=meb.reaction_positions("AAA",CsvSource(tmp_path),cal)
    assert [cal.sessions(cal.first,cal.last)[position] for position in positions] == [dt.date(2019,2,1),dt.date(2019,5,3)]
    row=meb.exposure_row(ArmTrade("AAA","S","4w","2019-04-30","win",1.5,2.0),"strategy","2019-04-30",is_etf=False,positions=positions,calendar=cal)
    assert row.covered and row.distance == 3
def test_run2_is_locked_without_stage2_pass(tmp_path):
    cache=tmp_path/"cache";cache.mkdir();(cache/"SPY.csv").write_text("Date,Close\n2019-01-02,1\n")
    assert meb.main(["replay","--run","run2","--cache-dir",str(cache),"--out-root",str(tmp_path/"out")]) == 3
