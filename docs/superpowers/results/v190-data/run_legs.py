"""V190-23 driver: legs A and B, one strategy per chunk, resumable. Plumbing only: no WR/ExpR is printed."""
import re, subprocess, sys, time, datetime as dt
from pathlib import Path
sys.path.insert(0, ".")
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
OUT = Path("E:/Documents/Private/Projects/Discord-Bot/data/backtest_results/v190")
log = open(OUT / "legs.log", "a", buffering=1, encoding="utf-8")
def say(m): log.write(f"{dt.datetime.utcnow():%FT%TZ} {m}\n")
jobs = []
for leg in ("A", "B"):
    for name in ALL_STRATEGIES:
        jobs.append((leg, name, re.sub("[^a-z0-9]+", "-", name.lower()).strip("-")))
for i, (leg, name, slug) in enumerate(jobs, 1):
    jl, js = OUT / f"leg-{leg}-{slug}.jsonl", OUT / f"leg-{leg}-{slug}.json"
    if jl.exists() and Path(str(jl) + ".provenance.json").exists():
        say(f"[{i}/{len(jobs)}] {leg} {slug} already done"); continue
    base = ["--instrument", "v3", "--tp2", "none"] if leg == "A" else \
           ["--instrument", "v1", "--data-source", "alpaca", "--tickers-file", str(OUT / "watchlist.txt")]
    cmd = [sys.executable, str(OUT / "run_smoke_local.py"), *base, "--train", "--exit-model", "v2", "--scale-out",
           "--strategy", name, "--json", str(js), "--trades-jsonl", str(jl)]
    t0 = time.time(); say(f"[{i}/{len(jobs)}] {leg} {slug} start ({100*(i-1)//len(jobs)}% done)")
    with open(OUT / f"leg-{leg}-{slug}.log", "w", encoding="utf-8") as lf:
        rc = subprocess.call(cmd, stdout=lf, stderr=subprocess.STDOUT)
    wrote = next((l.strip() for l in open(OUT / f"leg-{leg}-{slug}.log", encoding="utf-8", errors="replace") if l.startswith("Wrote") and "trade rows" in l), "no 'Wrote' line")
    say(f"[{i}/{len(jobs)}] {leg} {slug} exit {rc} {wrote} wall {int(time.time()-t0)}s")
say("ALL CHUNKS ATTEMPTED")
