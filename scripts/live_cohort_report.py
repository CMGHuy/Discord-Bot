"""Live-cohort report (plan v8 Task V8) -- the permanent "learn from live
mistakes" loop, re-run weekly by V29.

Slices the live paper book by strategy / tier / badge / horizon / direction /
source and reports n, win rate (with a Wilson lower bound), avg win %, avg
loss %, payoff ratio, expectancy R and total % for each cohort.

Every stat comes from the canonical definitions -- `analytics/metrics.py`
(`r_multiple`, `win_rate`, `expectancy_r`, `profit_factor`) and
`core/gate/wr_math.py` (`wilson_lower_bound`). No stat math is re-derived
here; that is the one rule this script exists under, so its numbers always
agree with the admin UI and the gate surfaces.

Usage:

    python scripts/live_cohort_report.py                       # local data/
    python scripts/live_cohort_report.py --data /opt/swing-bot/data
    python scripts/live_cohort_report.py --since 2026-08-01    # closed on/after
    python scripts/live_cohort_report.py --json out.json       # machine-readable
    python scripts/live_cohort_report.py \
        --baseline /opt/swing-bot/archive/2026-07-31-pre-v8/trades.json

`--baseline` takes either an archived `trades.json` (e.g. the frozen v8
baseline) or a snapshot previously emitted by `--json`, and prints a
per-cohort delta against it. Percentage-point deltas are shown for rates,
absolute deltas for everything else. Cohorts present on only one side are
listed separately rather than silently dropped -- a cohort that appeared or
vanished is usually the finding.

Informational only: always exits 0.
"""
import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swingbot.core.analytics.metrics import (  # noqa: E402
    expectancy_r, profit_factor, r_multiple, win_rate,
)
from swingbot.core.gate.wr_math import wilson_lower_bound  # noqa: E402

CLOSED_STATUSES = ("win", "loss", "closed")

# Every dimension the report slices by, as (heading, key-function). `source`
# and `badge` are None for legacy (pre-plan-engine) trades, which is itself
# the signal that separates the two engine paths -- so None is rendered as a
# real cohort, never dropped.
DIMENSIONS = [
    ("Engine path", lambda t: "v2" if t.get("plan_id") else "legacy"),
    ("Strategy", lambda t: t.get("strategy") or "(none)"),
    ("Tier", lambda t: str(t.get("tier"))),
    ("Badge", lambda t: str(t.get("badge"))),
    ("Horizon", lambda t: str(t.get("horizon_key"))),
    ("Direction", lambda t: str(t.get("direction"))),
    ("Source", lambda t: str(t.get("source"))),
    # V29. NOT the same question as "Source" (which strategy family found it)
    # -- this is how the close came to be written. A `reconcile` close replays
    # missed bars after downtime and resolves a bar spanning both levels as
    # the stop, so it books the full gap move instead of a managed 1.75%
    # stop-out; pooling it with live closes makes an outage read as strategy
    # decay. Trades closed before the stamp existed (2026-08-06) report
    # `unstamped` rather than being assumed live -- the field genuinely does
    # not know, and quietly defaulting them to `live` would put the Aug-4
    # outage's 32 reconciled closes into the cohort the rollback trigger
    # watches.
    ("Close source", lambda t: str(t.get("close_source") or "unstamped")),
    # V4 Step 3. Scale-out was dead in the live log until 2026-07-31 -- the
    # legacy SL/TP loops closed 100% of a v2 position the first time price
    # touched TP1, so `append_leg_by_plan` no-opped and only 24 of 475 trades
    # ever recorded a leg. Post-fix that runs at 16 of 18 v2 wins carrying two
    # legs. Kept as a standing cohort because the failure mode is silent:
    # nothing errors when a runner is lost, the trade just settles at TP1.
    # A win appearing under `0 legs` means some path closed it without the
    # manager -- in every measured case so far, an orphaned plan_id.
    #
    # READ THIS COHORT AS A DIAGNOSTIC, NOT AS EVIDENCE. Its expectancy
    # column is close to tautological: a 2-leg trade banked TP1, so it is a
    # win by construction, and a 1-leg trade is the synthesized fraction=1.0
    # leg of a pre-TP1 loss. The 2026-08-01+ read (2+ legs: WR 100%, +1.180R;
    # 1 leg: WR 0%, -1.783R) is therefore NOT a measurement that scale-out
    # earns anything -- it is win/loss restated. The only load-bearing number
    # here is the COUNT under `0 legs`.
    ("Legs", lambda t: f"{min(len(t.get('legs') or []), 2)}"
                       f"{'+' if len(t.get('legs') or []) >= 2 else ''} legs"),
]


def pnl_pct(t: dict) -> float | None:
    """Percent return on the trade, sign-flipped for bearish so positive
    always means "in the trade's favor" -- the same convention r_multiple()
    uses for R. None when entry or exit is missing."""
    entry, exit_price = t.get("entry"), t.get("exit_price")
    if not entry or exit_price is None:
        return None
    sign = 1 if t.get("direction") == "bullish" else -1
    return (exit_price - entry) / entry * 100 * sign


def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def cohort_stats(trades: list[dict]) -> dict:
    """Every number this report knows how to compute, for one cohort."""
    wins = [t for t in trades if t.get("status") == "win"]
    losses = [t for t in trades if t.get("status") == "loss"]
    win_pcts = [pnl_pct(t) for t in wins]
    loss_pcts = [pnl_pct(t) for t in losses]
    all_pcts = [p for p in (pnl_pct(t) for t in trades) if p is not None]

    avg_win, avg_loss = _mean(win_pcts), _mean(loss_pcts)
    payoff = (abs(avg_win / avg_loss) if avg_win is not None
              and avg_loss not in (None, 0) else None)
    rs = [r for t in trades if (r := r_multiple(t)) is not None]

    return {
        "n": len(trades),
        "n_win": len(wins),
        "n_loss": len(losses),
        "win_rate": win_rate(trades),
        # The methodology doc requires a Wilson lower bound beside every
        # rate: a point estimate on a small cohort is a hypothesis, not a
        # finding (tier A moved 6.6 pts on 5 trades in the v8 baseline).
        "wilson_lb": (wilson_lower_bound(len(wins), len(wins) + len(losses)) * 100
                      if wins or losses else None),
        "avg_win_pct": avg_win,
        "avg_loss_pct": avg_loss,
        "payoff": payoff,
        "expectancy_r": expectancy_r(trades),
        "median_r": statistics.median(rs) if rs else None,
        "profit_factor": profit_factor(trades),
        "total_pct": sum(all_pcts) if all_pcts else 0.0,
    }


def build_report(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("status") in CLOSED_STATUSES]
    report = {
        "n_records": len(trades),
        "n_closed": len(closed),
        "n_open": sum(1 for t in trades if t.get("status") == "open"),
        "overall": cohort_stats(closed),
        "dimensions": {},
    }
    for heading, keyfn in DIMENSIONS:
        buckets: dict[str, list] = defaultdict(list)
        for t in closed:
            buckets[keyfn(t)].append(t)
        report["dimensions"][heading] = {
            k: cohort_stats(v) for k, v in buckets.items()
        }
    return report


# -- rendering --------------------------------------------------------------

def _fmt(value, spec="{:.2f}", dash="--"):
    return dash if value is None else spec.format(value)


HEADER = (f"{'cohort':<32} {'n':>5} {'WR%':>7} {'Wlb%':>7} {'avgW%':>8} "
          f"{'avgL%':>8} {'payoff':>7} {'expR':>7} {'total%':>9}")


def _row(name: str, s: dict) -> str:
    return (f"{name[:32]:<32} {s['n']:>5} {_fmt(s['win_rate']):>7} "
            f"{_fmt(s['wilson_lb']):>7} {_fmt(s['avg_win_pct'], '{:+.2f}'):>8} "
            f"{_fmt(s['avg_loss_pct'], '{:+.2f}'):>8} {_fmt(s['payoff']):>7} "
            f"{_fmt(s['expectancy_r'], '{:+.3f}'):>7} "
            f"{_fmt(s['total_pct'], '{:+.1f}'):>9}")


def render(report: dict, min_n: int) -> None:
    print(f"records {report['n_records']}  closed {report['n_closed']}  "
          f"open {report['n_open']}")
    print()
    print(HEADER)
    print("-" * len(HEADER))
    print(_row("ALL CLOSED", report["overall"]))

    for heading, cohorts in report["dimensions"].items():
        shown = {k: v for k, v in cohorts.items() if v["n"] >= min_n}
        if not shown:
            continue
        print(f"\n-- {heading} " + "-" * (len(HEADER) - len(heading) - 4))
        # Worst total first: this report exists to find what is losing money.
        for name, stats in sorted(shown.items(), key=lambda kv: kv[1]["total_pct"]):
            print(_row(name, stats))
        hidden = len(cohorts) - len(shown)
        if hidden:
            print(f"   ({hidden} cohort(s) below --min-n {min_n} hidden)")


def render_diff(report: dict, baseline: dict, min_n: int) -> None:
    print("\n" + "=" * len(HEADER))
    print("DELTA vs baseline  (rates in percentage points, totals absolute)")
    print(f"baseline: {baseline['n_closed']} closed   current: {report['n_closed']} closed")
    print("=" * len(HEADER))

    def _delta(cur, base, key):
        a, b = cur.get(key), base.get(key)
        return None if a is None or b is None else a - b

    print(f"\n{'cohort':<32} {'dn':>5} {'dWR':>7} {'dexpR':>8} {'dtotal%':>9}")
    print("-" * 64)
    o_cur, o_base = report["overall"], baseline["overall"]
    print(f"{'ALL CLOSED':<32} {o_cur['n'] - o_base['n']:>+5} "
          f"{_fmt(_delta(o_cur, o_base, 'win_rate'), '{:+.2f}'):>7} "
          f"{_fmt(_delta(o_cur, o_base, 'expectancy_r'), '{:+.3f}'):>8} "
          f"{_fmt(_delta(o_cur, o_base, 'total_pct'), '{:+.1f}'):>9}")

    for heading, cohorts in report["dimensions"].items():
        base_cohorts = baseline["dimensions"].get(heading, {})
        both = {k: v for k, v in cohorts.items()
                if k in base_cohorts and max(v["n"], base_cohorts[k]["n"]) >= min_n}
        appeared = [k for k, v in cohorts.items()
                    if k not in base_cohorts and v["n"] >= min_n]
        vanished = [k for k, v in base_cohorts.items()
                    if k not in cohorts and v["n"] >= min_n]
        if not (both or appeared or vanished):
            continue
        print(f"\n-- {heading} " + "-" * (64 - len(heading) - 4))
        for name, stats in sorted(both.items(),
                                  key=lambda kv: _delta(kv[1], base_cohorts[kv[0]],
                                                        "total_pct") or 0):
            b = base_cohorts[name]
            print(f"{name[:32]:<32} {stats['n'] - b['n']:>+5} "
                  f"{_fmt(_delta(stats, b, 'win_rate'), '{:+.2f}'):>7} "
                  f"{_fmt(_delta(stats, b, 'expectancy_r'), '{:+.3f}'):>8} "
                  f"{_fmt(_delta(stats, b, 'total_pct'), '{:+.1f}'):>9}")
        # Never silently dropped: a cohort that appeared or disappeared
        # between two runs is usually the actual finding.
        if appeared:
            print(f"   NEW in current: {', '.join(sorted(appeared))}")
        if vanished:
            print(f"   GONE from current: {', '.join(sorted(vanished))}")


# -- input ------------------------------------------------------------------

def load_trades(path: Path) -> list[dict]:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit(f"{path}: expected a list of trade records")
    return data


def load_baseline(path: Path) -> dict:
    """Accepts either an archived trades.json or a snapshot emitted by
    --json, so the frozen v8 baseline can be diffed against directly with
    no conversion step."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return build_report(data)
    if "dimensions" in data and "overall" in data:
        return data
    raise SystemExit(f"{path}: neither a trades.json nor a --json snapshot")


def filter_since(trades: list[dict], since: str) -> list[dict]:
    """Trades CLOSED on or after `since` (ISO date). Filtering on close is
    what makes weekly runs comparable -- a trade opened in the window but
    still open has no outcome to report, and one opened earlier that closed
    inside the window is exactly the result that window produced."""
    kept = []
    for t in trades:
        closed_at = t.get("closed_at")
        if closed_at and closed_at[:10] >= since:
            kept.append(t)
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=None,
                    help="data directory holding trades.json (default: repo data/)")
    ap.add_argument("--trades", default=None,
                    help="path to a trades.json directly (overrides --data)")
    ap.add_argument("--since", default=None, metavar="YYYY-MM-DD",
                    help="only trades closed on or after this date")
    ap.add_argument("--baseline", default=None, metavar="PATH",
                    help="archived trades.json or --json snapshot to diff against")
    ap.add_argument("--json", dest="json_out", default=None, metavar="PATH",
                    help="write the full report as JSON (for a later --baseline)")
    ap.add_argument("--min-n", type=int, default=5,
                    help="hide cohorts smaller than this (default 5)")
    args = ap.parse_args()

    if args.trades:
        trades_path = Path(args.trades)
    else:
        data_dir = Path(args.data) if args.data else \
            Path(__file__).resolve().parent.parent / "data"
        trades_path = data_dir / "trades.json"
    if not trades_path.exists():
        raise SystemExit(f"no trades.json at {trades_path}")

    trades = load_trades(trades_path)
    if args.since:
        before = len(trades)
        trades = filter_since(trades, args.since)
        print(f"--since {args.since}: {len(trades)} of {before} records "
              f"closed on or after that date\n")

    report = build_report(trades)
    report["source"] = str(trades_path)
    report["since"] = args.since
    render(report, args.min_n)

    if args.baseline:
        render_diff(report, load_baseline(Path(args.baseline)), args.min_n)

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(report, f, indent=2)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
