# Smoke-run wrapper: stubs the DB-backed watchlist (plumbing check only; watchlist slice not meaningful).
import runpy, sys
sys.path[:0] = [".", "scripts/data"]
import fetch_backtest_data
fetch_backtest_data.load_watchlist = lambda: []
sys.argv = ["run_backtest_range.py"] + sys.argv[1:]
runpy.run_path("scripts/backtest/run_backtest_range.py", run_name="__main__")
