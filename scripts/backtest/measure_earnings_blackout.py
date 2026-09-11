#!/usr/bin/env python3
"""Build and score the pre-registered v82 earnings-blackout exposure table."""
import argparse, dataclasses, json, sys
from concurrent.futures import ProcessPoolExecutor
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
import pandas as pd
from swingbot.core.backtesting import earnings_blackout as eb
from swingbot.core.backtesting.acceptance import arm_trade_from_backtest, arm_trade_from_plan, delta_standardised_win_rate
from swingbot.core.market.earnings_calendar import EARNINGS_CSV_DIR, UNCONFIRMED, CsvSource, next_reaction_distance, reaction_session
from swingbot.core.market.session import SessionCalendar
from swingbot.core.market.strategy_types import HORIZONS
CACHE_DIR, OUT_ROOT=ROOT / "data" / "backtest_cache", ROOT / "data" / "v82"
RUNS={"run1": eb.RUN1_WINDOW, "run2": eb.VALIDATION_WINDOW}; STAGE2_PASS_MARKER="**Overall: PASS**"
def load_frame(cache_dir, symbol):
    path=Path(cache_dir) / f"{symbol}.csv"
    return pd.read_csv(path, index_col="Date", parse_dates=True) if path.exists() else None
def load_calendar(cache_dir):
    frame=load_frame(cache_dir, "SPY")
    if frame is None or frame.empty: raise SystemExit(f"SPY.csv missing from {cache_dir}")
    return SessionCalendar.from_bar_index(frame.index)
def calendar_meta(calendar): return {"first":calendar.first.isoformat(),"last":calendar.last.isoformat(),"sessions":len(calendar)}
def reaction_positions(ticker, source, calendar):
    return sorted({position for report in source.reports(ticker) if (session:=reaction_session(report, calendar)) is not None and (position:=calendar.position_on_or_after(session)) is not None})
def exposure_row(trade, population, signal_date, *, is_etf, positions, calendar):
    pos=calendar.position_on_or_before(date.fromisoformat(signal_date)); covered=not is_etf and bool(positions) and pos is not None and positions[0] <= pos <= positions[-1]
    return eb.ExposureRow(trade, population, is_etf, covered, -1 if pos is None else pos, next_reaction_distance(pos, positions) if covered else None)
def ticker_rows(ticker, frame, window, horizons, strategies, *, is_etf, positions, calendar):
    from swingbot.core.backtesting.backtest import run_backtest
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.planning.plan_engine import simulate_exit
    rows=[]; lo,hi=window
    for horizon in horizons:
        for index, plan in replay_scenarios(ticker, frame, horizon):
            signal_date=str(frame.index[index].date())
            if lo <= signal_date <= hi:
                result=simulate_exit(frame,index,plan,scale_out=True); trade=dataclasses.replace(arm_trade_from_plan(plan,entry_date=signal_date,outcome=result.outcome,r_multiple=result.r_total),strategy=f"confluence:{plan.strategy}")
                rows.append(exposure_row(trade,"confluence",signal_date,is_etf=is_etf,positions=positions,calendar=calendar))
    for strategy in strategies:
        for horizon in horizons:
            for trade0 in run_backtest(ticker,frame,strategy,horizon,exit_model="v2",scale_out=True,tp2_mode="levels",frictions=True).trades:
                if lo <= trade0.entry_date <= hi:
                    trade=arm_trade_from_backtest(trade0,ticker=ticker,strategy=strategy,horizon_key=horizon); rows.append(exposure_row(trade,"strategy",trade0.entry_date,is_etf=is_etf,positions=positions,calendar=calendar))
    return rows
def _worker(task):
    ticker,cache,csv_dir,window,horizons,strategies,is_etf=task; calendar=load_calendar(cache); frame=load_frame(cache,ticker)
    if frame is None or frame.empty:return ticker,[]
    positions=[] if is_etf else reaction_positions(ticker,CsvSource(csv_dir),calendar)
    return ticker,[row.to_dict() for row in ticker_rows(ticker,frame,window,horizons,strategies,is_etf=is_etf,positions=positions,calendar=calendar)]
def write_shard(path, rows):
    path=Path(path); temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text("".join(json.dumps(row)+"\n" for row in rows),encoding="utf-8"); temporary.replace(path)
def read_rows(run_dir):
    return [eb.ExposureRow.from_dict(json.loads(line)) for shard in sorted(Path(run_dir).glob("*.jsonl")) for line in shard.read_text(encoding="utf-8").splitlines() if line]
def _coverage(rows):
    coverage=eb.coverage_pct(rows); return coverage is not None and coverage >= eb.COVERAGE_FLOOR_PCT
def cmd_replay(args):
    if args.run=="run2":
        document=Path(args.stage2_doc) if args.stage2_doc else None
        if document is None or not document.exists() or STAGE2_PASS_MARKER not in document.read_text(encoding="utf-8"): return 3
    from swingbot.core.backtesting.backtest import ALL_STRATEGIES
    from swingbot.core.marketdata.universe import is_etf
    cache=Path(args.cache_dir); calendar=load_calendar(cache); run_dir=Path(args.out_root)/args.run; run_dir.mkdir(parents=True,exist_ok=True); meta=calendar_meta(calendar); previous=run_dir/"calendar.json"
    if previous.exists() and json.loads(previous.read_text()) != meta:return 4
    previous.write_text(json.dumps(meta)); symbols=args.tickers.split(",") if args.tickers else sorted(path.stem for path in cache.glob("*.csv")); todo=[symbol for symbol in symbols if not (run_dir/f"{symbol}.jsonl").exists()]; horizons=args.horizons.split(",") if args.horizons else list(HORIZONS); strategies=args.strategies.split("|") if args.strategies else list(ALL_STRATEGIES)
    progress=run_dir/"progress.txt"; tasks=[(symbol,str(cache),str(args.csv_dir),RUNS[args.run],horizons,strategies,is_etf(symbol)) for symbol in todo]
    try:
        iterator=map(_worker,tasks) if args.workers==1 else ProcessPoolExecutor(max_workers=args.workers).map(_worker,tasks)
        for done,(ticker,rows) in enumerate(iterator,1): write_shard(run_dir/f"{ticker}.jsonl",rows); progress.write_text(f"{done}/{len(todo)} tickers ({100*done//len(todo) if todo else 100}%)\n"); print(f"[{done}/{len(todo)}] {ticker}: {len(rows)} rows",flush=True)
    finally: progress.unlink(missing_ok=True)
    print(f"complete: {len(read_rows(run_dir))} rows",flush=True); return 0
def cmd_coverage(args):
    lo,hi=args.window.split(".."); rows=eb.in_window(read_rows(Path(args.out_root)/args.run),(lo,hi)); return 0 if _coverage(rows) else 2
def cmd_select(args):
    rows=eb.in_window(read_rows(Path(args.out_root)/"run1"),eb.SELECTION_WINDOW)
    if not _coverage(rows): return 2
    selection=eb.select_k(rows); payload={"verdict":selection.verdict,"selected_k":selection.selected_k,"candidates":[dataclasses.asdict(c) for c in selection.candidates],"plateau":selection.plateau};
    if args.out_json:Path(args.out_json).write_text(json.dumps(payload,indent=1));
    if args.out_md:Path(args.out_md).write_text(f"# v82 earnings blackout — Stage 1 selection\n\n**Verdict: {selection.verdict}**\n")
    return 0 if selection.verdict==eb.SELECTED else 1
def cmd_arms(args):
    root=Path(args.out_root); rows=eb.in_window(read_rows(root/("run2" if args.stage=="validation" else "run1")), eb.VALIDATION_WINDOW if args.stage=="validation" else eb.SELECTION_WINDOW)
    if args.stage=="walkforward":
        all_rows=read_rows(root/"run1");
        if not all(_coverage(eb.in_year(all_rows,year)) for year in eb.FOLD_TEST_YEARS):return 2
        blob=eb.folds_blob(all_rows,args.k)
    else:
        if not _coverage(rows):return 2
        blob=eb.arms_blob(rows,args.k)
    Path(args.out).write_text(json.dumps(blob)); return 0
def cmd_permute(args):
    calendar=load_calendar(args.cache_dir); run_dir=Path(args.out_root)/"run2"; meta=run_dir/"calendar.json"
    if not meta.exists() or json.loads(meta.read_text()) != calendar_meta(calendar):return 4
    rows=eb.in_window(read_rows(run_dir),eb.VALIDATION_WINDOW); source=CsvSource(args.csv_dir); reactions={ticker:reaction_positions(ticker,source,calendar) for ticker in {row.trade.ticker for row in rows if row.covered}}; result=eb.permutation_test(rows,args.k,reactions,len(calendar));
    if args.out_json:Path(args.out_json).write_text(json.dumps(result,indent=1)); return 0
def main(argv=None):
    parser=argparse.ArgumentParser(); sub=parser.add_subparsers(dest="command",required=True)
    def common(p):p.add_argument("--cache-dir",default=str(CACHE_DIR));p.add_argument("--csv-dir",default=str(EARNINGS_CSV_DIR));p.add_argument("--out-root",default=str(OUT_ROOT))
    p=sub.add_parser("replay");common(p);p.add_argument("--run",choices=RUNS,required=True);p.add_argument("--tickers");p.add_argument("--horizons");p.add_argument("--strategies");p.add_argument("--workers",type=int,default=1);p.add_argument("--stage2-doc")
    p=sub.add_parser("coverage");common(p);p.add_argument("--run",choices=RUNS,required=True);p.add_argument("--window",required=True)
    p=sub.add_parser("select");common(p);p.add_argument("--out-md");p.add_argument("--out-json")
    p=sub.add_parser("arms");common(p);p.add_argument("--stage",choices=("mde","walkforward","validation"),required=True);p.add_argument("--k",type=int,choices=eb.GRID,required=True);p.add_argument("--out",required=True)
    p=sub.add_parser("permute");common(p);p.add_argument("--k",type=int,choices=eb.GRID,required=True);p.add_argument("--out-json")
    return {"replay":cmd_replay,"coverage":cmd_coverage,"select":cmd_select,"arms":cmd_arms,"permute":cmd_permute}[parser.parse_args(argv).command](parser.parse_args(argv))
if __name__=="__main__":raise SystemExit(main())
