#!/usr/bin/env python3
"""Quarterly re-validation ritual (Task E96).

Deliberately a human-run script, not a cron job -- re-validation results
demand a reader, not a silent log line. Run it the first weekend of
Jan/Apr/Jul/Oct (see README's "The growth playbook"), read the output,
and prune anything that's degraded.

Orchestrates:
    1. Refresh the OHLCV cache (scripts/fetch_backtest_data.py --force)
    2. Data quality sweep over every cached ticker (universe.data_quality_issues)
    3. Check whether the anchored fold set is due for a rollover (flagged
       only -- ANCHORED_FOLDS is a frozen, pre-registered constant per the
       plan's Global Constraints; extending it is a deliberate, reviewed
       code change, never something a script does unattended)
    4. Re-run the full-system fold sweep + permutation test
    5. Diff against the previous quarter's recorded numbers, print a
       PASS/DEGRADED verdict

Usage:
    python scripts/quarterly_revalidation.py
    python scripts/quarterly_revalidation.py --skip-refresh   # cache already fresh
    python scripts/quarterly_revalidation.py --permutation-n 200
"""
import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

HISTORY_PATH = ROOT / "docs" / "superpowers" / "results" / "quarterly_revalidation_history.json"
ADOPTED_PATH = ROOT / "docs" / "superpowers" / "results" / "adopted_components.json"

# Numbers that matter enough to gate a PASS/DEGRADED verdict on. Anything
# else in the run's output is printed for a human to read but not diffed.
TRACKED_KEYS = ("pooled_delta_expectancy_r", "p_value", "p_ruin", "p_10x", "max_dd_p95")
DEGRADE_TOLERANCE = {
    "pooled_delta_expectancy_r": 0.03,   # matches PLATEAU_TOLERANCE_R
    "p_value": 0.05,
    "p_ruin": 0.05,
    "p_10x": -0.05,   # a DROP of more than 5 points in p(10x) is a degrade
    "max_dd_p95": 0.05,
}


def load_history() -> list:
    if HISTORY_PATH.exists():
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    return []


def save_history(history: list) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, indent=1), encoding="utf-8")


def refresh_cache() -> None:
    print("\n[1/5] Refreshing the OHLCV cache (this re-fetches every watchlist ticker)...")
    subprocess.run([sys.executable, "scripts/data/fetch_backtest_data.py", "--force"],
                   cwd=ROOT, check=True)


def data_quality_sweep() -> dict:
    print("\n[2/5] Data quality sweep over cached tickers...")
    import pandas as pd
    from swingbot.core.backtest_cache import CACHE_DIR
    from swingbot.core.universe import data_quality_issues

    issues = {}
    csvs = sorted(CACHE_DIR.glob("*.csv")) if CACHE_DIR.exists() else []
    for path in csvs:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        found = data_quality_issues(df, path.stem)
        if found:
            issues[path.stem] = found
    if issues:
        print(f"  {len(issues)}/{len(csvs)} ticker(s) with data quality issues:")
        for ticker, found in issues.items():
            print(f"    {ticker}: {'; '.join(found)}")
    else:
        print(f"  clean -- {len(csvs)} cached ticker(s), no data quality issues found")
    return issues


def check_fold_rollover() -> None:
    print("\n[3/5] Checking whether the anchored fold set is due for a rollover...")
    from swingbot.core.backtest_wf import ANCHORED_FOLDS

    last_test_year = int(ANCHORED_FOLDS[-1][3][:4])
    current_year = datetime.date.today().year
    if current_year > last_test_year + 1:
        print(f"  NOTE: current year {current_year} is more than one year past the last "
              f"anchored fold's test year ({last_test_year}). ANCHORED_FOLDS in "
              f"backtest_wf.py is a frozen, pre-registered constant -- rolling it forward "
              f"(e.g. adding a 2019-anchored fold once 2026 fully completes) is a "
              f"deliberate, reviewed code change for a human to make, not something this "
              f"script does automatically.")
    else:
        print(f"  fold set current (last test year {last_test_year}, current year {current_year})")


def run_full_system_and_permutation(permutation_n: int) -> dict:
    print("\n[4/5] Re-running the full-system fold sweep + permutation test...")
    adopted = json.loads(ADOPTED_PATH.read_text(encoding="utf-8")) if ADOPTED_PATH.exists() else {}
    print(f"  adopted components: {adopted or '(none)'}")

    wf = subprocess.run([sys.executable, "scripts/backtest/wf_run.py", "--full", "--portfolio",
                        "--json", str(ROOT / "docs" / "superpowers" / "results" /
                                     "_quarterly_wf_result.json")],
                        cwd=ROOT, capture_output=True, text=True)
    print(wf.stdout[-3000:])
    if wf.returncode != 0:
        print(wf.stderr[-2000:], file=sys.stderr)

    perm = subprocess.run([sys.executable, "scripts/backtest/permutation_test.py",
                           "--component-json", json.dumps(adopted),
                           "--n", str(permutation_n)],
                          cwd=ROOT, capture_output=True, text=True)
    print(perm.stdout[-3000:])
    if perm.returncode != 0:
        print(perm.stderr[-2000:], file=sys.stderr)

    result_path = ROOT / "docs" / "superpowers" / "results" / "_quarterly_wf_result.json"
    wf_result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}

    return {
        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "adopted_components": adopted,
        "wf_stdout_tail": wf.stdout[-3000:],
        "perm_stdout_tail": perm.stdout[-3000:],
        "wf_result": wf_result,
    }


def diff_and_verdict(history: list, latest: dict) -> str:
    print("\n[5/5] Diffing against the previous quarter's numbers...")
    if not history:
        print("  no previous quarter recorded -- this run becomes the baseline.")
        return "BASELINE (no prior quarter to compare)"

    prev = history[-1]
    prev_result = prev.get("wf_result", {})
    cur_result = latest.get("wf_result", {})
    verdict = "PASS"
    for key in TRACKED_KEYS:
        prev_v, cur_v = prev_result.get(key), cur_result.get(key)
        if prev_v is None or cur_v is None:
            continue
        delta = cur_v - prev_v
        tol = DEGRADE_TOLERANCE.get(key, 0.0)
        degraded = (delta < -abs(tol)) if tol >= 0 else (delta < tol)
        flag = "DEGRADED" if degraded else "ok"
        print(f"    {key}: {prev_v!r} -> {cur_v!r} (delta {delta:+.4f}) [{flag}]")
        if degraded:
            verdict = "DEGRADED"
    print(f"  VERDICT: {verdict}")
    return verdict


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skip-refresh", action="store_true",
                   help="skip the cache refresh step (already fresh)")
    p.add_argument("--permutation-n", type=int, default=200)
    args = p.parse_args()

    print(f"=== Quarterly re-validation, {datetime.date.today().isoformat()} ===")
    if not args.skip_refresh:
        refresh_cache()
    else:
        print("\n[1/5] Skipped (--skip-refresh)")

    data_quality_sweep()
    check_fold_rollover()
    latest = run_full_system_and_permutation(args.permutation_n)

    history = load_history()
    verdict = diff_and_verdict(history, latest)
    latest["verdict"] = verdict
    history.append(latest)
    save_history(history)
    print(f"\nAppended to {HISTORY_PATH.relative_to(ROOT)}")
    return 0 if verdict != "DEGRADED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
