# v100 standard arm producer — instrument proof

**Scope:** Instrument proof only — no selection decision taken, no
pre-registration opened or reopened, and no VALIDATION shot spent.

## Commands and verdicts

`STALL_EXIT_ENABLED=true` and `DATA_DRIVEN_STOPS_ENABLED=true` are closed,
journal-dependent knobs. The proof did not invoke either live command; the
producer's before-compute refusal is covered by
`tests/scripts/test_measure_arms.py::test_static_refusal_happens_before_any_compute`.

```text
python scripts/backtest/measure_arms.py --knob MIN_STOP_DISTANCE_PCT=2.5 --stage pilot --out data/arms/v100_minstop_pilot.json
  pilot: 10 of 74 cached tickers; baseline N=431; component N=329;
  changed outcomes=138; exit 0

python scripts/backtest/validate_component.py --stage reachability --arms data/arms/v100_minstop_pilot.json --title "v100 proof" --window pilot
  REACHABLE; exit 0

python scripts/backtest/validate_component.py --stage mde --arms data/arms/v100_minstop_pilot.json --title "v100 proof" --window pilot --train-effect-pp 1.0
  refused:stage-mismatch; exit 1; budget intact

python scripts/backtest/validate_component.py --stage mde --arms data/arms/v100_minstop_pilot.json --title "v100 proof" --window pilot --train-effect-pp 1.0 --bespoke-instrument "v100 instrument proof on the pilot slice -- not a hypothesis test"
  observed N=330 over 945d; projected N=255 over 730d;
  paired MDE=13.0724pp; unpaired MDE=30.2231pp;
  REFUSED: 1.0pp below MDE; exit 1; budget intact
```

`MIN_STOP_DISTANCE_PCT` was confirmed reachable and absent from the closed
pre-registration table before the pilot ran. The progress counter reached
20/20 ticker-arms and its temporary progress file was removed.

## Planning deviations implemented

1. `ArmTrade` carries the pairing key, plus optional `source` and `direction`; no `keys.py` or `KeyedTrade` was needed.
2. Knob deltas are applied inside each producer worker; direct config reads in strategy filters need no separate ScanParams plumbing task.
3. The registry uses `reachable`, `live_scan_only`, `journal_dependent`, and `outside_replay`; exit outcomes remain reachable.
4. Paired MDE uses the ticker-cluster bootstrap SE and square-root projection, not a closed-form McNemar estimator.
5. Stamps isolate signal windows only; exit walks intentionally continue beyond the signal window.
6. `refused:stage-mismatch` rejects a producer file at the wrong funnel stage.
7. Validation production requires and records a `--preregistration` path.

## Parity and fixture findings

The strategy engine's 11-strategy × two-horizon parity suite passed all 25
checks; no constructor divergence was found. Outcome-level v74 fixture
observability retained all reachable classifications. MA Ribbon confirmation
bars and Support/Resistance minimum touches are not observable in that
two-ticker fixture and are explicitly marked `fixture_observable=False`; they
remain reachable in the standard producer.
