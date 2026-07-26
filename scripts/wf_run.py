"""CLI for the walk-forward harness (Task E39).

Run: python scripts/wf_run.py --component-json '{"REGIME_GATES_ENABLED": true}'
     python scripts/wf_run.py --full     # everything adopted, portfolio mode

WARNING -- this is a LONG run. The default sweep is every cached universe
symbol x every strategy x every horizon, twice (baseline + component) per
fold, over three folds. Narrow it with --strategy/--horizon while
iterating; run the full sweep deliberately, not casually.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.backtest_wf import _default_run, _guarded, gate, run_folds  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--component-json", default="{}",
                   help='config overrides for the component leg, e.g. \'{"FLAG": true}\'')
    p.add_argument("--full", action="store_true",
                   help="run the full adopted system (reads adopted defaults)")
    p.add_argument("--strategy", action="append", default=None,
                   help="limit to one strategy (repeatable) -- for iteration, not decisions")
    p.add_argument("--horizon", action="append", default=None,
                   help="limit to one horizon key (repeatable)")
    p.add_argument("--json", default=None, help="write the raw result dict here")
    args = p.parse_args()

    overrides = {} if args.full else json.loads(args.component_json)
    if args.full and args.component_json != "{}":
        print("--full ignores --component-json (it measures the adopted defaults)",
              file=sys.stderr)

    def run(start, end, over):
        return _default_run(start, end, over, strategies=args.strategy,
                            horizons=args.horizon)

    result = run_folds(overrides, run_fn=_guarded(run))
    verdict = gate(result)

    print(f"component overrides: {overrides or '(none -- adopted defaults)'}")
    print(f"{'fold':<6}{'N':>8}{'baseline':>12}{'component':>12}{'delta':>10}")
    for f in result["folds"]:
        b = f["baseline"]["expectancy_r"]
        c = f["component"]["expectancy_r"]
        d = f["delta_expectancy_r"]
        fmt = lambda v: "     n/a" if v is None else f"{v:8.4f}"
        print(f"{f['test_years']:<6}{f['n']:>8}{fmt(b):>12}{fmt(c):>12}{fmt(d):>10}")
    pooled = result["pooled_delta_expectancy_r"]
    print(f"pooled delta expectancy_r: "
          f"{'n/a' if pooled is None else f'{pooled:+.4f}'}")
    print(f"PRE-REGISTERED GATE: {verdict}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"overrides": overrides, "result": result, "gate": verdict},
                      fh, indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
