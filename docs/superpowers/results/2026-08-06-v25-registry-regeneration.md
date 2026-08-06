# V25 — re-emit the badge registry

**Date:** 2026-08-06
**Task:** plan v8 V25
**Provenance:** `docs/superpowers/results/2026-08-06-v25-registry-provenance.json`
**No backtest was run. V24's reserved validation shot is untouched.**

---

## 1. What V25 turned out to be

The task reads as bookkeeping — *"`run_backtest_range.py --emit-registry`, then
commit the generated registry immediately"*. Executing it surfaced a defect of
exactly the shape V49 was created for, in the one place it matters most.

`build_registry_records` decided VALIDATED with its own private test:

```python
validated = (wr >= pass_wr          # pass_wr=80.0
             and er > 0 and s["n"] >= min_n)
```

`win_rate >= 80` is **the gate V6 Step 3 voided** ("void under a 2.5% floor").
V49 replaced it with `passes()` — `expectancy_r > 0`, `n_eval >= min_n`,
`excluded_share <= 0.5` — and fixed the PASS/FAIL report column in five
scripts. It did not touch the registry emitter **sitting in the same file**,
so `run_backtest_range.py` has since printed PASS for a strategy while writing
WEAK into the registry for the same numbers on the same run.

**Why this one is worse than the report column V49 caught.** The report is
read by people. The registry is read by the **live bot** —
`registry.get_badge` → `plan_engine` → `WEAK_CAUTION_TEXT` on the alert, and
`quality.component_badge`'s 20 points of quality score.

## 2. Fix

- `build_registry_records` now delegates to `passes()`. No second copy of the
  rule survives in the file.
- `passes()` needs `excluded_share`, which the old summary shape dropped. Both
  emit sites and `run_confluence_validation.py` now forward it, and a summary
  without it **raises** rather than silently applying two of three criteria —
  defaulting a missing one to `0.0` would assert "no dead trades", the most
  permissive possible answer, for a shape that cannot answer.
- 6 tests, 4 of which fail against the pre-fix emitter.

## 3. Regeneration — without spending the validation shot

The registry's window is `2024-01-01..2025-12-31`, and V24 reserves the **one
permitted reuse** of it. Re-running to fix a *rule* would have burned that.

`--from-json` exists precisely for this ("registry regeneration WITHOUT
re-running the window") and returns before any backtest. Provenance was
recovered and **verified field-by-field against the committed registry**:

| source JSON | strategies | match |
|---|---|---|
| `exit_v2_validation.json` | 9 | exact on `n` and `expectancy_r` |
| `rescue_ema_validation.json` | EMA Crossover | exact |
| `rescue_elliott_validation.json` | Elliott Wave | exact |

`exit_v2_validation.json` also carries EMA Crossover and Elliott Wave, and for
those two it does **not** match — they were superseded by the rescue runs. The
merge takes the rescue values, which is what the committed registry holds.

Result: **4 status changes, every `n` / `win_rate` / `expectancy_r`
byte-identical.**

| strategy | was | now | n | WR | ExpR |
|---|---|---|---|---|---|
| EMA Crossover | WEAK | VALIDATED | 36 | 75.0 | +0.061 |
| Elliott Wave | WEAK | VALIDATED | 75 | 77.3 | +0.064 |
| MA Ribbon | WEAK | VALIDATED | 137 | 78.1 | +0.213 |
| RSI Divergence | WEAK | VALIDATED | 1099 | 75.8 | +0.208 |

No row loses its badge. `run_date` moves to 2026-08-06 on the 11 `strategy`
rows; **`window` is unchanged**, which is the field that says what was
measured.

## 4. The consequence, stated plainly

**All 11 strategies are now VALIDATED, so the badge no longer discriminates.**
`WEAK_CAUTION_TEXT` can never render for a recognised strategy, and
`component_badge` returns a constant +20 on every live plan. The only
surviving WEAK path is the unregistered fallback (`n=0`), which is what a
newly-added strategy gets.

This is the honest output of the corrected rule — all 11 really do clear V6's
gate on that window, with `excluded_share` between 0.00 and 0.31 against a
0.50 ceiling. But it retires a live discriminator that was carrying real
signal: V7's frozen baseline measured **WEAK at −0.213R (n=385) against
VALIDATED at +0.781R (n=14)**. That split has no successor.

**Not fixed here, because choosing its replacement is a design decision:** a
discriminator the V6 rule does not flatten — Wilson lower bound, an N floor,
or expectancy bands — would restore the signal. Pinned by
`test_every_registered_strategy_is_now_validated` so the flattening cannot be
rediscovered by accident.

**Two further limits, recorded rather than fixed:**

1. **The measurements are pre-v8.** They come from the 2024-2025 window run in
   July, before the 1.75% cap, the 2.5% floor and the current exit model.
   Correcting the *rule* does not refresh the *numbers*; that needs a re-run,
   which is V24's shot.
2. **RSI is VALIDATED on n=30 at a 100% win rate.** That is exactly the kind
   of figure V49's Wilson-bound work exists to distrust, and it was VALIDATED
   under the old rule too. Left as-is: `registry.py` forbids hand-edits
   outside the round-1 seed, and an N floor is part of the design decision
   above, not a one-off patch.
