# v148 Ops hardening, part 3: remaining scan, marketdata and earnings conversions

> **For agentic workers:** pull one task at a time (`grep -n "^### Task OH12:" -A 260 <this file>`), never this file whole.

**Spec:** `docs/superpowers/specs/2026-10-09-v148-ops-hardening-design.md` (§ O5 "Conversion — this spec's ratchet step")
**Index:** `docs/superpowers/plans/2026-10-09-v148-ops-hardening_0-index.md` — Global Constraints, Parallelisation and the task ledger are binding here and are not repeated.
**Bump:** ui patch · bot patch (applied at close-out, never by a task)
**Edge:** none (integrity)

`$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening`. Never `cd`; use absolute paths and `git -C $WT`.

Shared rules for every conversion in this part (index § Global Constraints, "Behaviour-preserving conversion"; the same rules as OH9 in part 2):
- `swallowed()` (OH6) calls the logger's own level method (`log.warning`, `log.error`, `log.debug`, …) with the site's message, args and `exc_info`, plus `extra={"swallowed_tag": tag}` and `stacklevel=2`. A test that patches `log.warning` or reads `caplog` still sees the same call.
- Each handler's single log call becomes one `swallowed(log, "<tag>", <exc>, <same message>, <same args>, level=..., exc_info=...)` call. Omit `level=` for WARNING (the default) and omit `exc_info=` when it was absent. `log.exception(m, *a)` becomes `level=logging.ERROR, exc_info=True`. Every other statement in the handler (`return`, `continue`, assignments) stays exactly where it is.
- A handler that logged nothing (`pass`, `continue`, `return None`) gains `swallowed(log, "<tag>", exc, level=logging.DEBUG)` as its first statement and keeps the rest. With no message, OH6 logs `"swallowed <tag>: <Type: message>"` at DEBUG.
- A handler without `as` gains `as exc`. A handler that already binds a name (`as e`, `as _ce`, `as _je`) keeps that name and passes it.
- A handler containing a `raise` anywhere (even nested) is not converted.
- **Helper-logged sites.** Four handlers log through a throttling helper rather than `log` directly: `lifecycle_embeds._warn_throttled` (OH11) and `spot_metals._note_failure` (OH13). The throttle is behaviour, so the helper call stays exactly as it is. The handler gains `swallowed(log, "<tag>", exc, level=logging.DEBUG)` as its first statement, so every failure is counted while the WARNING output stays throttled as before. This is the "logged nothing directly" rule applied to the handler's own body; it adds a statement, never a branch.
- Tags are final once written: OH15's ratchet asserts that tags are unique per `except` handler repo-wide, and OH20's panel shows them. Part 2 already owns every `scan.run_scan.*`, `scan.unrealized_pnl.*`, `scan.scan_replay.regimes`, `scan.run_bounded` and the other OH9 tags. Every tag below is new.
- The import is `from swingbot.core.infra.swallowed import swallowed`. `swallowed.py` is a leaf module (no `swingbot` imports), so adding it to a low-level module such as `ticker_directory.py` creates no import cycle.
- A conversion adds no branch, so every function's radon score is unchanged. Each task proves this with a before/after `radon cc` diff.
- If a narrow test fails, the conversion changed behaviour: re-check the site against the task's table (level, message, args, `exc_info`, what follows the log call). The only new output allowed is one DEBUG record at a site that logged nothing, or at a helper-logged site. If a test fails only because it asserts the absence of that DEBUG record, stop and report it to the controller; do not edit the test.

# Phase C — remaining conversions

### Task OH10: Scan conversion B (`analyze`, `fetch`)

**Model:** sonnet — a mechanical one-for-one conversion of 18 handlers in two files, where each site's level, message and `exc_info` must be carried over exactly, and `fetch.py` already carries OH7's edits.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (12 handlers)
- Modify: `swingbot/core/scanning/fetch.py` (6 handlers; `_run_bounded`'s handler is OH7's and is not touched)

**Depends on:** OH7 (same file, `fetch.py`; OH7 already added `from swingbot.core.infra.swallowed import swallowed` to `fetch.py`, so this task adds no import there).

**Contract:** `scan.*` tags as listed in the tables below. No function signature, return value or fallback changes.

Line numbers below are HEAD before OH7. OH7 inserts about 29 lines above `_run_bounded` and inside it, so every `fetch.py` site at or after `_fetch_one_ticker` sits about 29 lines lower in the worktree. Find each site by its function and its log message, not by the number.

| File:line (pre-OH7 HEAD) | Function | Tag | Level / `exc_info` |
|---|---|---|---|
| `analyze.py:67` | `veto_bullish_for` | `scan.veto_bullish_for` | DEBUG / True |
| `analyze.py:156` | `build_decision_context` (weekly block) | `scan.decision_context.weekly` | DEBUG / — (logged nothing) |
| `analyze.py:174` | `build_decision_context` (avwaps block) | `scan.decision_context.avwaps` | DEBUG / — (logged nothing) |
| `analyze.py:181` | `build_decision_context` (rs block) | `scan.decision_context.rs` | DEBUG / — (logged nothing) |
| `analyze.py:186` | `build_decision_context` (regimes block) | `scan.decision_context.regimes` | DEBUG / — (logged nothing) |
| `analyze.py:195` | `build_decision_context` (gap block) | `scan.decision_context.gap` | DEBUG / — (logged nothing) |
| `analyze.py:207` | `build_decision_context` (outcomes block) | `scan.decision_context.outcomes` | DEBUG / — (logged nothing) |
| `analyze.py:239` | `build_decision_context` (sizing block) | `scan.decision_context.sizing` | DEBUG / — (logged nothing) |
| `analyze.py:254` | `build_decision_context` (quality block) | `scan.decision_context.quality` | DEBUG / — (logged nothing) |
| `analyze.py:326` | `_regime_at` | `scan.regime_at` | WARNING / True (inside the existing `if`) |
| `analyze.py:423` | `attach_plan_v2` (inner, risk_features) | `scan.attach_plan_v2.risk_features` | WARNING / True |
| `analyze.py:426` | `attach_plan_v2` (outer) | `scan.attach_plan_v2.build` | WARNING / True |
| `fetch.py:225` | `_fetch_one_ticker` | `scan.fetch_one_ticker` | ERROR / True (was `log.error(..., exc_info=True)`) |
| `fetch.py:242` | `_with_cached_depth` | `scan.with_cached_depth` | DEBUG / — |
| `fetch.py:369` | `_load_cached_daily` | `scan.load_cached_daily` | DEBUG / — |
| `fetch.py:485` | `_crawl_bounded` | `scan.crawl_bounded` | WARNING / True |
| `fetch.py:601` | `_daily_frame_for` | `scan.daily_frame_for` | WARNING / True |
| `fetch.py:621` | `map_tickers.safe` | `scan.map_tickers` | ERROR / True (was `log.exception`) |

`_regime_at` logs only when the regime series is non-empty (`if len(regimes) > 0:`). The `swallowed` call replaces the `log.warning` **inside** that `if`, so an empty series stays silent and uncounted, exactly as today, and no branch is added. `tests/scanning/test_engine_v2_plans.py::test_regime_at_logs_a_warning_on_a_real_lookup_miss` patches `analyze.log.warning` and still sees `_regime_at` in the call args.

- [ ] **Step 1: Record the before-state**

The verification is an AST count of untagged handlers, using OH15's rule: a handler is untagged if it catches `Exception` (alone or in a tuple), its body calls no `swallowed`, and it contains no `raise`. Save the scratch script (not committed):

```bash
mkdir -p /tmp/claude-oh10 && cat > /tmp/claude-oh10/untagged.py <<'PY'
"""Untagged except-Exception handlers per file (OH15's rule)."""
import ast
import sys
from pathlib import Path


def _untagged(h):
    if not isinstance(h, ast.ExceptHandler) or h.type is None:
        return False
    names = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    if not any(isinstance(n, ast.Name) and n.id == "Exception" for n in names):
        return False
    nodes = list(ast.walk(h))
    calls = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "swallowed"
                for n in nodes)
    return not calls and not any(isinstance(n, ast.Raise) for n in nodes)


for name in sys.argv[1:]:
    lines = sorted(h.lineno for h in ast.walk(ast.parse(Path(name).read_text(encoding="utf-8")))
                   if _untagged(h))
    print(f"{name}: {len(lines)} untagged {lines}")
PY
S=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/scanning
python /tmp/claude-oh10/untagged.py $S/analyze.py $S/fetch.py
```

Expected: `analyze.py: 12 untagged`, `fetch.py: 6 untagged` (OH7 already tagged `_run_bounded`'s handler). If `fetch.py` shows 7, OH7 has not landed: stop, OH10 depends on it. If another count differs, the file has drifted since the brief (2026-10-10): convert what the AST lists, keeping the same rules.

- [ ] **Step 2: Convert `analyze.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.jsonio import read_json` (`:25`). `analyze.py` already has `import logging` (`:9`) and `log = logging.getLogger(__name__)` (`:49`), and no function in it imports `logging` locally.

`:67` (`veto_bullish_for`):
```python
    except Exception as exc:
        swallowed(log, "scan.veto_bullish_for", exc, "dead-cat-bounce check failed; not vetoing",
                  level=logging.DEBUG, exc_info=True)
        return False
```

`build_decision_context`, the eight `except Exception: pass` blocks, in order (one listing; each `# :NNN` comment only names the site and is not written into the file). Each handler becomes these two lines with its own tag; the `try` bodies are untouched:

```python
    # :156 (weekly block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.weekly", exc, level=logging.DEBUG)

    # :174 (avwaps block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.avwaps", exc, level=logging.DEBUG)

    # :181 (rs block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.rs", exc, level=logging.DEBUG)

    # :186 (regimes block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.regimes", exc, level=logging.DEBUG)

    # :195 (gap block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.gap", exc, level=logging.DEBUG)

    # :207 (outcomes block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.outcomes", exc, level=logging.DEBUG)

    # :239 (sizing block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.sizing", exc, level=logging.DEBUG)

    # :254 (quality block)
    except Exception as exc:
        swallowed(log, "scan.decision_context.quality", exc, level=logging.DEBUG)
```

`:326` (`_regime_at`). The comment block stays; only the `as exc` and the log call change:
```python
    except Exception as exc:
        # A real regimes series was supplied but the lookup itself blew up
        # (bad index dtype, tz mismatch, etc.) -- every such miss silently
        # became COHORT_UNKNOWN with no way to tell "no data" apart from
        # "broken lookup" until now.
        if len(regimes) > 0:
            swallowed(log, "scan.regime_at", exc,
                      "_regime_at lookup raised for bar %s (regime series has %d rows)",
                      when, len(regimes), exc_info=True)
        return None
```

`:423` (`attach_plan_v2`, the inner `risk_features` handler):
```python
        except Exception as exc:
            swallowed(log, "scan.attach_plan_v2.risk_features", exc,
                      "risk_features stamping failed for %s/%s -- plan_v2 still posts, "
                      "risk_features left at its default", ticker, horizon_key, exc_info=True)
```

`:426` (`attach_plan_v2`, the outer handler):
```python
    except Exception as exc:
        swallowed(log, "scan.attach_plan_v2.build", exc, "plan_v2 construction failed for %s/%s",
                  ticker, horizon_key, exc_info=True)
```

The inner handler's `exc` and the outer handler's `exc` are separate handler-local names (Python deletes each at the end of its handler), and neither function reads `exc` after either handler.

- [ ] **Step 3: Convert `fetch.py`**

No import change: OH7 added `from swingbot.core.infra.swallowed import swallowed`. Check it is there:

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -n "^from swingbot.core.infra.swallowed import swallowed" -- swingbot/core/scanning/fetch.py
```

Expected: one line. Then convert the six sites. Leave `_run_bounded` exactly as OH7 left it.

`_fetch_one_ticker`:
```python
    except Exception as exc:
        swallowed(log, "scan.fetch_one_ticker", exc, "Crawl: error fetching data for %s: %s",
                  ticker, exc, level=logging.ERROR, exc_info=True)
        return ticker, None
```

`_with_cached_depth`:
```python
    except Exception as exc:
        swallowed(log, "scan.with_cached_depth", exc, "Crawl: cache splice skipped for %s (%s)",
                  ticker, exc, level=logging.DEBUG)
        return live
```

`_load_cached_daily`:
```python
    except Exception as exc:
        swallowed(log, "scan.load_cached_daily", exc,
                  "Crawl: cache lookup failed for %s (%s) -- treating as cold", ticker, exc,
                  level=logging.DEBUG)
        return None
```

`_crawl_bounded` (the SHORT crawl chunk handler, inside its loop):
```python
        except Exception as exc:
            swallowed(log, "scan.crawl_bounded", exc,
                      "SHORT crawl: chunk of %d failed -- ending the extra queue", len(batch),
                      exc_info=True)
            return frames, "fetch_failed"
```

`_daily_frame_for`:
```python
    except Exception as exc:
        swallowed(log, "scan.daily_frame_for", exc, "Could not resolve daily frame for %s: %s",
                  symbol, exc, exc_info=True)
        return None
```

`map_tickers`'s nested `safe`:
```python
    def safe(t):
        try:
            return fn(t)
        except Exception as exc:
            swallowed(log, "scan.map_tickers", exc, "scan worker failed for %s", t,
                      level=logging.ERROR, exc_info=True)
            return None
```

`safe` runs on `ThreadPoolExecutor` threads in the parent process (not spawned children), so its counts land in the parent's counter directly.

- [ ] **Step 4: Verify nothing is left untagged and the tags are unique**

```bash
S=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/scanning
python /tmp/claude-oh10/untagged.py $S/analyze.py $S/fetch.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -hoE 'swallowed\((log|_?[a-z_]+), "[a-z_.]+"' -- swingbot | sed -E 's/.*"([a-z_.]+)"/\1/' | sort | uniq -d
```

Expected: `analyze.py: 0 untagged []`, `fetch.py: 0 untagged []`. The `uniq -d` line prints only `scan.run_bounded`, which OH7 uses twice inside `_run_bounded` on purpose (the handler and the timeout path). Any other duplicate is a tag clash: rename the newer tag with a suffix naming what failed.

Then prove converted sites still behave and now count, in a throwaway process that imports the worktree copy:

```bash
cd /tmp && python - <<'PY'
import sys, types
sys.path.insert(0, "/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening")
from swingbot.core.infra import swallowed as sw
from swingbot.core.scanning import analyze, fetch

def boom(*a, **k):
    raise RuntimeError("probe")

analyze.load_account_config = boom          # keeps the sizing block away from the database
item = types.SimpleNamespace(plan_v2=None, plan=None, result=types.SimpleNamespace(ticker="AAPL"))
ctx = analyze.build_decision_context(item, {}, None)
assert "weekly" not in ctx and "quality" not in ctx, ctx
assert fetch.map_tickers(lambda t: 1 / 0, ["A", "B"], workers=1) == [None, None]
snap = sw.snapshot()
for tag in ("scan.decision_context.weekly", "scan.decision_context.rs",
            "scan.decision_context.outcomes", "scan.decision_context.sizing",
            "scan.decision_context.quality"):
    assert snap[tag]["count"] == 1, (tag, snap)
assert snap["scan.map_tickers"]["count"] == 2, snap
assert snap["scan.map_tickers"]["last_error"] == "ZeroDivisionError: division by zero", snap
print("OK", sorted(snap))
PY
```

Expected: a line starting `OK [` that lists at least the six tags asserted above. With `plan=None`, the weekly, rs, outcomes, sizing and quality blocks raise for certain; avwaps, regimes and gap may or may not raise on a `None` frame, so the probe does not assert them.

- [ ] **Step 5: Run the narrow tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_analyze_dcb_veto.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_decision_debug_logs.py
python $WT/scripts/dev/testrun.py file tests/charts/test_decision_chart.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_cold_fetch_pool.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_cold_fetch_splice.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_crawl_cache_first.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_crawl_spot.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_map_tickers_context.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_no_cross_ticker_mixing.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py
python $WT/scripts/dev/testrun.py file tests/infra/test_swallowed.py
python $WT/scripts/dev/testrun.py changed
```

Expected: every run `0 failed`, `0 xfailed`. `test_crawl_spot.py::test_a_failed_worker_is_a_skip` reads `fetch`'s caplog records and must still find the worker failure line, which proves `_fetch_one_ticker`'s ERROR record is unchanged. `changed` widens to every test reaching `analyze.py` and `fetch.py`. If it escalates to the full suite, let it run: that is the selector's call, not a re-run.

- [ ] **Step 6: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/core/scanning/analyze.py $WT/swingbot/core/scanning/fetch.py > /tmp/claude-oh10/cc_after.txt
for f in analyze fetch; do git -C $WT show HEAD:swingbot/core/scanning/$f.py > /tmp/claude-oh10/$f.py; done
python -m radon cc -s -n C /tmp/claude-oh10/analyze.py /tmp/claude-oh10/fetch.py > /tmp/claude-oh10/cc_before.txt
norm() { sed -E 's#.*/##; s/ [0-9]+:[0-9]+ / /' "$1"; }   # basename only, line:col dropped (conversions shift lines)
diff <(norm /tmp/claude-oh10/cc_before.txt) <(norm /tmp/claude-oh10/cc_after.txt) && echo "complexity unchanged"
```

Expected: `complexity unchanged`. `HEAD` here is the branch tip after OH7, so the comparison isolates this task. `build_decision_context` and `attach_plan_v2` may be listed (each `except` already counts in radon's score); they are listed in both files with the same score.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/scanning/analyze.py swingbot/core/scanning/fetch.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH10: count swallowed errors in analyze and fetch"
```

### Task OH11: Scan conversion C (`lifecycle_embeds`, `short_run`, `outlook_run`, `progress_store`)

**Model:** sonnet — a mechanical one-for-one conversion of 25 handlers across four files, including three throttled-helper sites and one re-raising handler that must be left alone.

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py` (11 handlers)
- Modify: `swingbot/core/scanning/short_run.py` (7 handlers)
- Modify: `swingbot/core/scanning/outlook_run.py` (4 of its 5 handlers; `_fill_keeping_issued` re-raises and is not converted)
- Modify: `swingbot/core/scanning/progress_store.py` (3 handlers)

**Contract:** `scan.*` tags as listed in the table below. No function signature, return value or fallback changes. `lifecycle_embeds._warn_throttled`, `_last_warned` and `_WARN_EVERY_SECONDS` are untouched (`tests/scanning/test_execution_feed_routing.py` monkeypatches `_last_warned`).

All four files already have `import logging` and `log = logging.getLogger(__name__)`, and none imports `logging` inside a function. Each gains only the `swallowed` import.

`short_run` and `outlook_run` have functions whose names repeat elsewhere in the scan scope (`_fit_trendline`, `_render_chart`, `_regimes`, `_stamp_context`), so their tags carry the module name: `scan.short_run.*`, `scan.outlook_run.*`. `scan.outlook_run.regimes` is distinct from part 2's `scan.scan_replay.regimes`.

| File:line (today) | Function | Tag | Level / `exc_info` |
|---|---|---|---|
| `lifecycle_embeds.py:60` | `regenerate_chart_for_trade` (MFE/MAE markers) | `scan.regenerate_chart.markers` | DEBUG / — |
| `lifecycle_embeds.py:84` | `regenerate_chart_for_trade` (outer) | `scan.regenerate_chart` | WARNING / True |
| `lifecycle_embeds.py:165` | `build_closed_trade_embed` ("Held" field) | `scan.closed_trade_embed.held` | DEBUG / — (logged nothing) |
| `lifecycle_embeds.py:198` | `build_closed_trade_embed` (held phrase) | `scan.closed_trade_embed.held_phrase` | DEBUG / — (logged nothing) |
| `lifecycle_embeds.py:229` | `notify_closed_trades` (channel) | `scan.notify_closed_trades.channel` | WARNING / True |
| `lifecycle_embeds.py:241` | `notify_closed_trades` (post) | `scan.notify_closed_trades.post` | WARNING / True |
| `lifecycle_embeds.py:277` | `notify_near_close` (channel) | `scan.notify_near_close.channel` | WARNING / True |
| `lifecycle_embeds.py:285` | `notify_near_close` (post) | `scan.notify_near_close.post` | WARNING / True |
| `lifecycle_embeds.py:483` | `notify_plan_events` (feed send) | `scan.notify_plan_events.feed` | DEBUG count + `_warn_throttled` kept |
| `lifecycle_embeds.py:492` | `notify_plan_events` (history send) | `scan.notify_plan_events.history` | DEBUG count + `_warn_throttled` kept |
| `lifecycle_embeds.py:502` | `notify_plan_events` (outer, per event) | `scan.notify_plan_events.event` | DEBUG count + `_warn_throttled` kept |
| `short_run.py:55` | `_stamp_context` | `scan.short_run.stamp_context` | ERROR / True (was `log.exception`) |
| `short_run.py:167` | `_fit_trendline` | `scan.short_run.fit_trendline` | WARNING / True |
| `short_run.py:218` | `_render_chart` | `scan.short_run.render_chart` | WARNING / True |
| `short_run.py:264` | `_stamp_intraday` | `scan.short_run.stamp_intraday` | DEBUG / — |
| `short_run.py:353` | `_lane_state` | `scan.short_run.lane_state` | DEBUG / True |
| `short_run.py:377` | `_log_funnel` | `scan.short_run.log_funnel` | ERROR / True (was `log.exception`) |
| `short_run.py:434` | `run_short_universe_scan` | `scan.short_run.extra_lane` | WARNING / True |
| `outlook_run.py:128` | `_sector_inputs` | `scan.outlook_run.sector_inputs` | WARNING / True |
| `outlook_run.py:136` | `_regimes` | `scan.outlook_run.regimes` | DEBUG / — (logged nothing) |
| `outlook_run.py:199` | `_risk_dollars` | `scan.outlook_run.risk_dollars` | DEBUG / — (logged nothing) |
| `outlook_run.py:247` | `_hourly` | `scan.outlook_run.hourly` | DEBUG / — (logged nothing) |
| `progress_store.py:85` | `_write_row` | `scan.progress_store.write` | DEBUG / True |
| `progress_store.py:98` | `_read_row` | `scan.progress_store.read` | DEBUG / True |
| `progress_store.py:117` | `clear` | `scan.progress_store.clear` | DEBUG / True |

Not converted: `outlook_run.py:309` (`_fill_keeping_issued`) contains `raise` three times. `short_run.py:432`'s `except write_failure.StoreWriteHalt: raise` does not catch `Exception` and is not a swallow; the `except Exception` right after it (`:434`) is converted.

- [ ] **Step 1: Record the before-state**

Save the scratch script (OH15's rule; not committed). It is the same script as OH10 Step 1; recreate it here so this task stands alone:

```bash
mkdir -p /tmp/claude-oh11 && cat > /tmp/claude-oh11/untagged.py <<'PY'
"""Untagged except-Exception handlers per file (OH15's rule)."""
import ast
import sys
from pathlib import Path


def _untagged(h):
    if not isinstance(h, ast.ExceptHandler) or h.type is None:
        return False
    names = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    if not any(isinstance(n, ast.Name) and n.id == "Exception" for n in names):
        return False
    nodes = list(ast.walk(h))
    calls = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "swallowed"
                for n in nodes)
    return not calls and not any(isinstance(n, ast.Raise) for n in nodes)


for name in sys.argv[1:]:
    lines = sorted(h.lineno for h in ast.walk(ast.parse(Path(name).read_text(encoding="utf-8")))
                   if _untagged(h))
    print(f"{name}: {len(lines)} untagged {lines}")
PY
S=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/scanning
python /tmp/claude-oh11/untagged.py $S/lifecycle_embeds.py $S/short_run.py $S/outlook_run.py $S/progress_store.py
```

Expected: `lifecycle_embeds.py: 11 untagged`, `short_run.py: 7`, `outlook_run.py: 4` (the re-raising `:309` is already excluded by the rule), `progress_store.py: 3`. That makes 25. If a count differs, the file has drifted since the brief (2026-10-10): convert what the AST lists, keeping the same rules.

- [ ] **Step 2: Convert `lifecycle_embeds.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.posted_log import log_posted` (`:14`).

`:60` (`regenerate_chart_for_trade`, MFE/MAE markers):
```python
        except Exception as _je:
            swallowed(log, "scan.regenerate_chart.markers", _je,
                      "Could not compute MFE/MAE markers for trade %s: %s", trade.get("id"), _je,
                      level=logging.DEBUG)
```

`:84` (`regenerate_chart_for_trade`, outer):
```python
    except Exception as e:
        swallowed(log, "scan.regenerate_chart", e, "Could not regenerate chart for trade %s: %s",
                  trade.get("id"), e, exc_info=True)
        return None
```

One listing for these sites; each `# :NNN` comment only names the site and is not written into the file:
```python
    # :165 (build_closed_trade_embed, the "Held" field)
    except Exception as exc:
        swallowed(log, "scan.closed_trade_embed.held", exc, level=logging.DEBUG)

    # :198 (build_closed_trade_embed, the held phrase)
    except Exception as exc:
        swallowed(log, "scan.closed_trade_embed.held_phrase", exc, level=logging.DEBUG)
```

`:229` (`notify_closed_trades`, channel resolution):
```python
        except Exception as _ce:
            swallowed(log, "scan.notify_closed_trades.channel", _ce,
                      "Could not resolve closed-trades channel %s: %s",
                      config.DISCORD_CHANNEL_TRADES_HISTORY_ID, _ce, exc_info=True)
            return
```

`:241` (`notify_closed_trades`, per-trade post):
```python
        except Exception as e:
            swallowed(log, "scan.notify_closed_trades.post", e,
                      "Could not post closed-trade notification for %s: %s", trade.get("id"), e,
                      exc_info=True)
```

`:277` (`notify_near_close`, channel resolution):
```python
        except Exception as _ce:
            swallowed(log, "scan.notify_near_close.channel", _ce,
                      "Could not resolve closed-trades channel %s: %s",
                      config.DISCORD_CHANNEL_TRADES_HISTORY_ID, _ce, exc_info=True)
            return
```

`:285` (`notify_near_close`, per-warning post):
```python
        except Exception as e:
            swallowed(log, "scan.notify_near_close.post", e,
                      "Could not post near-close warning for %s: %s", warning["trade"].get("id"), e,
                      exc_info=True)
```

The three `notify_plan_events` handlers are helper-logged sites (see the shared rules at the top of this part). `_warn_throttled` logs one WARNING per plan per 15 minutes while an undelivered event is retried every minute; that throttle stays. Each handler gains one DEBUG `swallowed` line as its first statement, so every failure is counted:

`:483` (feed send):
```python
                except Exception as exc:
                    swallowed(log, "scan.notify_plan_events.feed", exc, level=logging.DEBUG)
                    _warn_throttled(plan.plan_id, "execution feed: %s for plan %s failed "
                                    "on feed (%s); history will notify instead",
                                    event.transition, plan.plan_id, exc)
```

`:492` (history send):
```python
                except Exception as exc:
                    swallowed(log, "scan.notify_plan_events.history", exc, level=logging.DEBUG)
                    _warn_throttled(plan.plan_id, "execution feed: history copy of %s for "
                                    "plan %s failed: %s", event.transition, plan.plan_id, exc)
```

`:502` (outer, per event):
```python
        except Exception as exc:
            swallowed(log, "scan.notify_plan_events.event", exc, level=logging.DEBUG)
            _warn_throttled(event.plan_id, "execution feed: could not post %s for plan %s: %s",
                            event.transition, event.plan_id, exc)
```

The non-handler `_warn_throttled` call at `:500` ("reached no channel; it will be re-sent") is not an exception site and stays as is.

- [ ] **Step 3: Convert `short_run.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.notifier import notify_secondary` (`:27`).

`:55` (`_stamp_context`):
```python
        except Exception as exc:
            swallowed(log, "scan.short_run.stamp_context", exc,
                      "market_context.attach failed for %s", ticker,
                      level=logging.ERROR, exc_info=True)
            stamped[ticker] = df
```

`:167` (`_fit_trendline`):
```python
    except Exception as exc:
        swallowed(log, "scan.short_run.fit_trendline", exc, "Trendline fit failed for %s", plan,
                  exc_info=True)
        return None
```

`:218` (`_render_chart`):
```python
    except Exception as exc:
        swallowed(log, "scan.short_run.render_chart", exc,
                  "Could not generate trade chart for %s: %s", result.ticker, exc, exc_info=True)
        return None, None
```

`:264` (`_stamp_intraday`):
```python
    except Exception as exc:
        swallowed(log, "scan.short_run.stamp_intraday", exc,
                  "Intraday confirmation unavailable for %s: %s", item.result.ticker, exc,
                  level=logging.DEBUG)
        item.intraday = None
```

`:353` (`_lane_state`):
```python
    except Exception as exc:
        swallowed(log, "scan.short_run.lane_state", exc, "regime_series computation failed",
                  level=logging.DEBUG, exc_info=True)
```

`:377` (`_log_funnel`):
```python
    except Exception as exc:
        swallowed(log, "scan.short_run.log_funnel", exc,
                  "SHORT funnel telemetry failed -- not blocking the lane",
                  level=logging.ERROR, exc_info=True)
```

`:434` (`run_short_universe_scan`; the `except write_failure.StoreWriteHalt: raise` above it and the `finally:` below it are untouched):
```python
            except Exception as exc:
                swallowed(log, "scan.short_run.extra_lane", exc,
                          "SHORT extra lane failed -- base scan unaffected", exc_info=True)
                return []
```

- [ ] **Step 4: Convert `outlook_run.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.edge import regime2` (`:28`).

`:128` (`_sector_inputs`):
```python
    except Exception as exc:
        swallowed(log, "scan.outlook_run.sector_inputs", exc,
                  "outlook: sector ETFs unavailable -- ticker-only RS", exc_info=True)
        return {}, {}, {}
```

`:136` (`_regimes`):
```python
def _regimes(spy):
    try:
        return regime2.regime_series(spy)
    except Exception as exc:
        swallowed(log, "scan.outlook_run.regimes", exc, level=logging.DEBUG)
        return None
```

One listing for these sites; each `# :NNN` comment only names the site and is not written into the file:
```python
    # :199 (_risk_dollars)
    except Exception as exc:
        swallowed(log, "scan.outlook_run.risk_dollars", exc, level=logging.DEBUG)
        return None

    # :247 (_hourly)
    except Exception as exc:
        swallowed(log, "scan.outlook_run.hourly", exc, level=logging.DEBUG)
        return None                    # display-only context; never fails a card
```

Leave `_fill_keeping_issued`'s handler (`:309-320`) exactly as it is.

- [ ] **Step 5: Convert `progress_store.py`**

The file has no `swingbot` imports today. Add, after `from datetime import datetime, timezone` (`:15`), one blank line and then `from swingbot.core.infra.swallowed import swallowed`, so the block reads:

```python
import contextlib
import logging
import threading
from datetime import datetime, timezone

from swingbot.core.infra.swallowed import swallowed

log = logging.getLogger(__name__)
```

One listing for these sites; each `# :NNN` comment only names the site and is not written into the file:
```python
    # :85 (_write_row)
    except Exception as exc:  # noqa: BLE001
        swallowed(log, "scan.progress_store.write", exc,
                  "Could not publish scan progress to the database",
                  level=logging.DEBUG, exc_info=True)

    # :98 (_read_row)
    except Exception as exc:  # noqa: BLE001
        swallowed(log, "scan.progress_store.read", exc,
                  "Could not read scan progress from the database",
                  level=logging.DEBUG, exc_info=True)
        return None

    # :117 (clear)
    except Exception as exc:  # noqa: BLE001
        swallowed(log, "scan.progress_store.clear", exc,
                  "Could not clear scan progress in the database",
                  level=logging.DEBUG, exc_info=True)
```

`progress_store` is also imported by the admin (`/api/v1/system/scan`), so a failed read there counts in the admin process's own counter, which OH20 reports under `process: "admin"`.

- [ ] **Step 6: Verify nothing is left untagged and the tags are unique**

```bash
S=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/scanning
python /tmp/claude-oh11/untagged.py $S/lifecycle_embeds.py $S/short_run.py $S/outlook_run.py $S/progress_store.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -hoE 'swallowed\((log|_?[a-z_]+), "[a-z_.]+"' -- swingbot | sed -E 's/.*"([a-z_.]+)"/\1/' | sort | uniq -d
```

Expected: `0 untagged []` for every file. The `uniq -d` line prints nothing, or only `scan.run_bounded` once OH7 has landed (used twice inside `_run_bounded` on purpose).

Then prove converted sites still behave and now count, in a throwaway process that imports the worktree copy:

```bash
cd /tmp && python - <<'PY'
import asyncio, sys, types
sys.path.insert(0, "/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening")
from swingbot import config
from swingbot.core.infra import swallowed as sw
from swingbot.core.db.repositories import scan_progress
from swingbot.core.scanning import lifecycle_embeds, outlook_run, progress_store, short_run

def boom(*a, **k):
    raise RuntimeError("probe")

async def aboom(*a, **k):
    raise RuntimeError("probe")

outlook_run.data_store.load_from_disk = boom
assert outlook_run._hourly("AAPL") is None
short_run.fit_trendline = boom
assert short_run._fit_trendline(object(), types.SimpleNamespace(entry=1.0), {}, "bullish") is None
scan_progress.scan_progress_repo = boom
assert progress_store._read_row() is None
config.DISCORD_CHANNEL_TRADES_HISTORY_ID = "1"
bot = types.SimpleNamespace(get_channel=lambda _id: None, fetch_channel=aboom)
assert asyncio.run(lifecycle_embeds.notify_near_close(bot, [{"trade": {}}])) is None
snap = sw.snapshot()
for tag in ("scan.outlook_run.hourly", "scan.short_run.fit_trendline",
            "scan.progress_store.read", "scan.notify_near_close.channel"):
    assert snap[tag]["count"] == 1 and snap[tag]["last_error"] == "RuntimeError: probe", (tag, snap)
print("OK", sorted(snap))
PY
```

Expected: `OK ['scan.notify_near_close.channel', 'scan.outlook_run.hourly', 'scan.progress_store.read', 'scan.short_run.fit_trendline']`. `_read_row` imports `scan_progress_repo` from the repository module at call time, so patching the module attribute reaches it.

- [ ] **Step 7: Run the narrow tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/scanning/test_execution_feed_routing.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_lifecycle_push.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_outlook_cancel_notices.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py
python $WT/scripts/dev/testrun.py file tests/tracking/test_near_tp_bypass.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_scan.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_short_funnel.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_short_lane_admission.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_outlook_run.py
python $WT/scripts/dev/testrun.py file tests/commands/test_outlook_loops.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_progress_store.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_progress_store_db.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_system_scan.py
python $WT/scripts/dev/testrun.py changed
```

Expected: every run `0 failed`, `0 xfailed`. `test_execution_feed_routing.py` drives the feed and history failure paths with a channel that raises; it passing unchanged shows the throttled WARNING output kept its shape. `changed` widens to every test reaching the four files; if it escalates to the full suite, let it run.

- [ ] **Step 8: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
F="lifecycle_embeds short_run outlook_run progress_store"
python -m radon cc -s -n C $(for f in $F; do echo $WT/swingbot/core/scanning/$f.py; done) > /tmp/claude-oh11/cc_after.txt
for f in $F; do git -C $WT show HEAD:swingbot/core/scanning/$f.py > /tmp/claude-oh11/$f.py; done
python -m radon cc -s -n C $(for f in $F; do echo /tmp/claude-oh11/$f.py; done) > /tmp/claude-oh11/cc_before.txt
norm() { sed -E 's#.*/##; s/ [0-9]+:[0-9]+ / /' "$1"; }   # basename only, line:col dropped (conversions shift lines)
diff <(norm /tmp/claude-oh11/cc_before.txt) <(norm /tmp/claude-oh11/cc_after.txt) && echo "complexity unchanged"
```

Expected: `complexity unchanged`. `notify_plan_events` gains three plain statements, no branch, so its score is the same before and after.

- [ ] **Step 9: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/scanning/lifecycle_embeds.py swingbot/core/scanning/short_run.py swingbot/core/scanning/outlook_run.py swingbot/core/scanning/progress_store.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH11: count swallowed errors in lifecycle_embeds, short_run, outlook_run and progress_store"
```

### Task OH12: Marketdata conversion A (`data`, `data_refresh`)

**Model:** sonnet — a mechanical one-for-one conversion of 18 handlers in two files, most of them silent `continue`/`pass` sites in candidate loops that must stay loops.

**Files:**
- Modify: `swingbot/core/marketdata/data.py` (11 handlers)
- Modify: `swingbot/core/marketdata/data_refresh.py` (7 handlers)

**Contract:** `marketdata.*` tags as listed in the table below, including `marketdata.price_batch` (spec § O5 names it). No function signature, return value or fallback changes. Both files already have `import logging` and `log = logging.getLogger(__name__)`, and neither imports `logging` inside a function.

| File:line (today) | Function | Tag | Level / `exc_info` |
|---|---|---|---|
| `data.py:56` | `get_daily_data` (candidate loop) | `marketdata.daily_data.candidate` | DEBUG / — (logged nothing; `continue` kept) |
| `data.py:124` | `_yf_daily_batch` | `marketdata.daily_batch` | ERROR / True (was `log.error(..., exc_info=True)`) |
| `data.py:235` | `_yf_batch_prices` | `marketdata.price_batch` | ERROR / True (was `log.error(..., exc_info=True)`) |
| `data.py:283` | `warm_batch_price_cache_background._run` | `marketdata.price_warmup` | DEBUG / True |
| `data.py:365` | `_save_ticker_meta_cache` | `marketdata.save_ticker_meta` | DEBUG / True |
| `data.py:403` | `get_company_name` (candidate loop) | `marketdata.company_name` | DEBUG / — (logged nothing; `continue` kept) |
| `data.py:421` | `_resolve_currency_code` (candidate loop) | `marketdata.currency_code` | DEBUG / — (logged nothing; `continue` kept) |
| `data.py:496` | `_fast_info_price` (attribute loop) | `marketdata.fast_info_price` | DEBUG / — (logged nothing; `continue` kept) |
| `data.py:587` | `get_current_price_detail` (1m history) | `marketdata.price_detail.history` | DEBUG / — (logged nothing; `pass` dropped) |
| `data.py:597` | `get_current_price_detail` (fast_info) | `marketdata.price_detail.fast_info` | DEBUG / — (logged nothing; `continue` kept) |
| `data.py:667` | `prefetch_prices` | `marketdata.prefetch_prices` | WARNING / True |
| `data_refresh.py:75` | `load_state` | `marketdata.load_state` | WARNING / True |
| `data_refresh.py:107` | `save_state` | `marketdata.save_state` | WARNING / True |
| `data_refresh.py:278` | `refresh_symbol` (cold/forced full pull) | `marketdata.refresh_symbol.full` | WARNING / True |
| `data_refresh.py:291` | `refresh_symbol` (warm incremental pull) | `marketdata.refresh_symbol.incremental` | WARNING / True |
| `data_refresh.py:352` | `_record` (coverage read) | `marketdata.record_coverage` | DEBUG / — (logged nothing; `pass` dropped) |
| `data_refresh.py:394` | `refresh_all` (per-pair crash) | `marketdata.refresh_all.pair` | WARNING / True |
| `data_refresh.py:407` | `refresh_all` (`on_progress` callback) | `marketdata.refresh_all.on_progress` | DEBUG / — (logged nothing; `pass` dropped) |

A `pass` that is a handler's only statement is replaced by the `swallowed` call (a handler body needs one statement, and `swallowed(...)` is it). A `continue` or `return` stays after the call. The two `except yf_safe.DownloadBusy` handlers in front of `:124` and `:235` do not catch `Exception` and stay as they are (INFO, not a swallow).

`get_daily_data`, `get_company_name`, `_resolve_currency_code`, `_fast_info_price` and `get_current_price_detail` loop over candidate symbols or attribute names, so one call can count several times under one tag. That is the intended reading: the count is "how often this fallback path ate an exception".

- [ ] **Step 1: Record the before-state**

Save the scratch script (OH15's rule; not committed). It is the same script as OH10 Step 1; recreate it here so this task stands alone:

```bash
mkdir -p /tmp/claude-oh12 && cat > /tmp/claude-oh12/untagged.py <<'PY'
"""Untagged except-Exception handlers per file (OH15's rule)."""
import ast
import sys
from pathlib import Path


def _untagged(h):
    if not isinstance(h, ast.ExceptHandler) or h.type is None:
        return False
    names = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    if not any(isinstance(n, ast.Name) and n.id == "Exception" for n in names):
        return False
    nodes = list(ast.walk(h))
    calls = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "swallowed"
                for n in nodes)
    return not calls and not any(isinstance(n, ast.Raise) for n in nodes)


for name in sys.argv[1:]:
    lines = sorted(h.lineno for h in ast.walk(ast.parse(Path(name).read_text(encoding="utf-8")))
                   if _untagged(h))
    print(f"{name}: {len(lines)} untagged {lines}")
PY
M=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/marketdata
python /tmp/claude-oh12/untagged.py $M/data.py $M/data_refresh.py
```

Expected: `data.py: 11 untagged`, `data_refresh.py: 7 untagged`. If a count differs, the file has drifted since the brief (2026-10-10): convert what the AST lists, keeping the same rules.

- [ ] **Step 2: Convert `data.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.retry import with_retry` (`:12`).

The five silent candidate-loop sites all keep their `continue` (one listing; each `# :NNN` comment only names the site and is not written into the file):
```python
        # :56 (get_daily_data)
        except Exception as exc:
            swallowed(log, "marketdata.daily_data.candidate", exc, level=logging.DEBUG)
            continue

        # :403 (get_company_name)
        except Exception as exc:
            swallowed(log, "marketdata.company_name", exc, level=logging.DEBUG)
            continue

        # :421 (_resolve_currency_code)
        except Exception as exc:
            swallowed(log, "marketdata.currency_code", exc, level=logging.DEBUG)
            continue

        # :496 (_fast_info_price)
        except Exception as exc:
            swallowed(log, "marketdata.fast_info_price", exc, level=logging.DEBUG)
            continue

        # :597 (get_current_price_detail)
        except Exception as exc:
            swallowed(log, "marketdata.price_detail.fast_info", exc, level=logging.DEBUG)
            continue
```

`:124` (`_yf_daily_batch`):
```python
    except Exception as exc:
        swallowed(log, "marketdata.daily_batch", exc,
                  "get_daily_data_batch failed for %d ticker(s) after %d attempt(s): %s",
                  len(tickers), FETCH_RETRY_ATTEMPTS, exc, level=logging.ERROR, exc_info=True)
        return {}
```

`:235` (`_yf_batch_prices`):
```python
    except Exception as exc:
        swallowed(log, "marketdata.price_batch", exc,
                  "get_current_price_batch failed for %d ticker(s): %s", len(tickers), exc,
                  level=logging.ERROR, exc_info=True)
        return {}
```

`:283` (the nested `_run` of the background price warm-up):
```python
        except Exception as exc:
            swallowed(log, "marketdata.price_warmup", exc,
                      "background price warm-up failed for %d ticker(s)", len(tickers),
                      level=logging.DEBUG, exc_info=True)
```

`:365` (`_save_ticker_meta_cache`):
```python
    except Exception as exc:
        swallowed(log, "marketdata.save_ticker_meta", exc, "Could not save ticker_meta_cache.json",
                  level=logging.DEBUG, exc_info=True)
```

`:587` (`get_current_price_detail`, the 1-minute history attempt). The `pass` goes; execution still falls through to the fast_info attempt below:
```python
        except Exception as exc:
            swallowed(log, "marketdata.price_detail.history", exc, level=logging.DEBUG)
```

`:667` (`prefetch_prices`):
```python
    except Exception as exc:
        swallowed(log, "marketdata.prefetch_prices", exc, "prefetch_prices batch failed: %s", exc,
                  exc_info=True)
        return
```

- [ ] **Step 3: Convert `data_refresh.py`**

Add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.retry import with_retry` (`:23`).

`:75` (`load_state`):
```python
    except Exception as exc:            # never let bookkeeping break a refresh
        swallowed(log, "marketdata.load_state", exc, "could not read market-data state: %s", exc,
                  exc_info=True)
        return {}
```

`:107` (`save_state`):
```python
    except Exception as exc:            # never let bookkeeping break a refresh
        swallowed(log, "marketdata.save_state", exc, "could not save market-data state: %s", exc,
                  exc_info=True)
```

`:278` (`refresh_symbol`, cold or forced full pull):
```python
        except Exception as exc:
            swallowed(log, "marketdata.refresh_symbol.full", exc,
                      "refresh %s/%s failed after retries: %s", symbol, tf, exc, exc_info=True)
            return {**out, "status": "failed", "rows": have, "error": str(exc)[:200]}
```

`:291` (`refresh_symbol`, warm incremental pull):
```python
    except Exception as exc:
        swallowed(log, "marketdata.refresh_symbol.incremental", exc,
                  "incremental %s/%s failed after retries: %s", symbol, tf, exc, exc_info=True)
        return {**out, "status": "failed", "rows": have, "error": str(exc)[:200]}
```

`:352` (`_record`, the coverage read):
```python
        except Exception as exc:
            swallowed(log, "marketdata.record_coverage", exc, level=logging.DEBUG)
```

`:394` (`refresh_all`, belt-and-braces per pair):
```python
            except Exception as exc:      # belt-and-braces: loop must survive
                swallowed(log, "marketdata.refresh_all.pair", exc, "refresh %s/%s crashed: %s",
                          symbol, tf, exc, exc_info=True)
                r = {"symbol": symbol, "timeframe": tf, "status": "failed",
                     "rows": 0, "added": 0, "error": str(exc)[:200]}
```

`:407` (`refresh_all`, the `on_progress` callback):
```python
                except Exception as exc:
                    swallowed(log, "marketdata.refresh_all.on_progress", exc, level=logging.DEBUG)
```

`refresh_all` runs `refresh_symbol` in the bot process (the `market_data_refresh` loop), so these counts reach the heartbeat directly.

- [ ] **Step 4: Verify nothing is left untagged and the tags are unique**

```bash
M=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/marketdata
python /tmp/claude-oh12/untagged.py $M/data.py $M/data_refresh.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -hoE 'swallowed\((log|_?[a-z_]+), "[a-z_.]+"' -- swingbot | sed -E 's/.*"([a-z_.]+)"/\1/' | sort | uniq -d
```

Expected: `0 untagged []` for both files. The `uniq -d` line prints nothing, or only `scan.run_bounded` once OH7 has landed.

Then prove converted sites still behave and now count, in a throwaway process that imports the worktree copy:

```bash
cd /tmp && python - <<'PY'
import sys
sys.path.insert(0, "/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening")
from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import data, data_refresh

def boom(*a, **k):
    raise RuntimeError("probe")

class _FastInfo:
    def get(self, attr):
        raise KeyError(attr)

assert data._fast_info_price(_FastInfo()) is None
data.yf_safe.download = boom
assert data._yf_batch_prices(["AAA", "BBB"]) == {}
data_refresh.load_from_disk = boom
state = {}
data_refresh._record(state, "AAA", "daily", {"status": "fresh", "rows": 1}, "/nonexistent")
assert state, "the record is still written after the coverage read fails"
snap = sw.snapshot()
assert snap["marketdata.fast_info_price"]["count"] == 7, snap
assert snap["marketdata.price_batch"]["last_error"] == "RuntimeError: probe", snap
assert snap["marketdata.record_coverage"]["count"] == 1, snap
print("OK", sorted(snap))
PY
```

Expected: `OK ['marketdata.fast_info_price', 'marketdata.price_batch', 'marketdata.record_coverage']`. `_fast_info_price` tries seven attribute names, each raising, so its tag counts 7 and the function still returns `None`.

- [ ] **Step 5: Run the narrow tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/marketdata/test_data.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_current_price_staleness.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_data_alpaca_routing.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_data_spot.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_alpaca_killswitch.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_data_refresh.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_market_data_state_db.py
python $WT/scripts/dev/testrun.py file tests/commands/test_market_data_refresh_task.py
python $WT/scripts/dev/testrun.py file tests/scanning/test_log_levels_v111.py
python $WT/scripts/dev/testrun.py changed
```

Expected: every run `0 failed`, `0 xfailed`. `test_log_levels_v111.py::test_prefetch_batch_failure_is_a_warning` pins `prefetch_prices`'s WARNING record, and `test_data_refresh.py` patches `refresh_mod.log.error`/`warning` and reads `call_args`; both pass unchanged because `swallowed` calls the same level method with the same message. `changed` widens to every test reaching `data.py`, which is most of the suite's market-data surface; if it escalates to the full suite, let it run.

- [ ] **Step 6: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
python -m radon cc -s -n C $WT/swingbot/core/marketdata/data.py $WT/swingbot/core/marketdata/data_refresh.py > /tmp/claude-oh12/cc_after.txt
for f in data data_refresh; do git -C $WT show HEAD:swingbot/core/marketdata/$f.py > /tmp/claude-oh12/$f.py; done
python -m radon cc -s -n C /tmp/claude-oh12/data.py /tmp/claude-oh12/data_refresh.py > /tmp/claude-oh12/cc_before.txt
norm() { sed -E 's#.*/##; s/ [0-9]+:[0-9]+ / /' "$1"; }   # basename only, line:col dropped (conversions shift lines)
diff <(norm /tmp/claude-oh12/cc_before.txt) <(norm /tmp/claude-oh12/cc_after.txt) && echo "complexity unchanged"
```

Expected: `complexity unchanged`.

- [ ] **Step 7: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/marketdata/data.py swingbot/core/marketdata/data_refresh.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH12: count swallowed errors in marketdata data and data_refresh"
```

### Task OH13: Marketdata conversion B (seven files)

**Model:** sonnet — a mechanical one-for-one conversion of 16 handlers across six files, with one helper-logged site and one re-raising handler that must be left alone.

**Files:**
- Modify: `swingbot/core/marketdata/data_store.py` (5 handlers)
- Modify: `swingbot/core/marketdata/ticker_directory.py` (4 handlers)
- Modify: `swingbot/core/marketdata/export_data.py` (3 handlers; adds `import logging` and `log`)
- Modify: `swingbot/core/marketdata/backtest_cache.py` (2 handlers)
- Modify: `swingbot/core/marketdata/providers/router.py` (1 handler)
- Modify: `swingbot/core/marketdata/spot_metals.py` (1 handler, helper-logged)
- No edit: `swingbot/core/marketdata/providers/alpaca_provider.py`. The ledger lists it because it holds one `except Exception`, but that handler (`_call`, `:88`) re-raises (`AlpacaAuthError` / `AlpacaMiss`), so it is not a swallow and the file is not touched.

**Contract:** `marketdata.*` tags as listed below. No function signature, return value or fallback changes. `spot_metals._note_failure` and `_failing` are untouched (`tests/marketdata/test_spot_metals.py::test_http_error_logged_once_per_failure_streak` counts its WARNING records at INFO level).

| File:line (today) | Function | Tag | Level / `exc_info` |
|---|---|---|---|
| `data_store.py:184` | `fetch_interval_data` (candidate loop) | `marketdata.fetch_interval.candidate` | DEBUG / — (logged nothing; `continue` kept) |
| `data_store.py:310` | `load_normalized` (cache read) | `marketdata.load_normalized.read` | WARNING / True |
| `data_store.py:326` | `load_normalized` (index parse) | `marketdata.load_normalized.index` | WARNING / True |
| `data_store.py:381` | `_default_ranged_fetch` | `marketdata.ranged_fetch` | WARNING / True |
| `data_store.py:474` | `get_intraday` | `marketdata.get_intraday` | WARNING / True |
| `ticker_directory.py:94` | `_build_directory` | `marketdata.ticker_directory.download` | WARNING / True |
| `ticker_directory.py:105` | `_save_cache` | `marketdata.ticker_directory.save` | WARNING / True |
| `ticker_directory.py:122` | `_load_cache` | `marketdata.ticker_directory.load` | WARNING / True |
| `ticker_directory.py:210` | `_search_db` | `marketdata.ticker_directory.search` | WARNING / True |
| `export_data.py:65` | `fetch_full_history` (candidate loop) | `marketdata.full_history.candidate` | DEBUG / — (logged nothing; `continue` kept) |
| `export_data.py:215` | `scrape_watchlist_history._worker` (export) | `marketdata.export_worker` | DEBUG / — (logged nothing; assignments kept) |
| `export_data.py:221` | `scrape_watchlist_history._worker` (`on_ticker_done`) | `marketdata.export_worker.progress` | DEBUG / — (logged nothing; `pass` dropped) |
| `backtest_cache.py:95` | `fetch` (candidate loop) | `marketdata.backtest_cache.candidate` | WARNING / True |
| `backtest_cache.py:114` | `ensure_cached` | `marketdata.backtest_cache.ensure` | WARNING / True |
| `providers/router.py:154` | `_wait` | `marketdata.router.wait` | DEBUG / — (logged nothing; `return None, exc` kept) |
| `spot_metals.py:126` | `_fetch_quote` | `marketdata.spot_quote` | DEBUG count + `_note_failure` kept |

`router._wait` hands the exception back to its caller, which records the breaker and stats outcome; it still logged nothing itself, so it gains the DEBUG count like any silent site. Its earlier `except FutureTimeout` handler does not catch `Exception` and stays as is.

- [ ] **Step 1: Record the before-state**

Save the scratch script (OH15's rule, the same as OH10 Step 1; not committed):

```bash
mkdir -p /tmp/claude-oh13 && cat > /tmp/claude-oh13/untagged.py <<'PY'
"""Untagged except-Exception handlers per file (OH15's rule)."""
import ast
import sys
from pathlib import Path


def _untagged(h):
    if not isinstance(h, ast.ExceptHandler) or h.type is None:
        return False
    names = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
    if not any(isinstance(n, ast.Name) and n.id == "Exception" for n in names):
        return False
    nodes = list(ast.walk(h))
    calls = any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "swallowed"
                for n in nodes)
    return not calls and not any(isinstance(n, ast.Raise) for n in nodes)


for name in sys.argv[1:]:
    lines = sorted(h.lineno for h in ast.walk(ast.parse(Path(name).read_text(encoding="utf-8")))
                   if _untagged(h))
    print(f"{name}: {len(lines)} untagged {lines}")
PY
M=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/marketdata
python /tmp/claude-oh13/untagged.py $M/data_store.py $M/ticker_directory.py $M/export_data.py $M/backtest_cache.py $M/providers/router.py $M/spot_metals.py $M/providers/alpaca_provider.py
```

Expected: `data_store.py: 5`, `ticker_directory.py: 4`, `export_data.py: 3`, `backtest_cache.py: 2`, `router.py: 1`, `spot_metals.py: 1`, `alpaca_provider.py: 0` (its one handler re-raises). That makes 16. If a count differs, the file has drifted since the brief (2026-10-10): convert what the AST lists, keeping the same rules.

- [ ] **Step 2: Convert `data_store.py`**

Add `from swingbot.core.infra.swallowed import swallowed` before `from swingbot.core.marketdata import spot_metals, yf_safe` (`:36`).

One listing for these sites; each `# :NNN` comment only names the site and is not written into the file:
```python
        # :184 (fetch_interval_data)
        except Exception as exc:
            swallowed(log, "marketdata.fetch_interval.candidate", exc, level=logging.DEBUG)
            continue

    # :310 (load_normalized, cache read)
    except Exception as exc:
        swallowed(log, "marketdata.load_normalized.read", exc, "cache read failed for %s/%s: %s",
                  ticker, interval, exc, exc_info=True)
        return None

        # :326 (load_normalized, index parse)
        except Exception as exc:
            swallowed(log, "marketdata.load_normalized.index", exc,
                      "cached frame for %s/%s has an unparseable index: %s",
                      ticker, interval, exc, exc_info=True)
            return None

    # :381 (_default_ranged_fetch)
    except Exception as exc:  # network flake: skip symbol this run
        swallowed(log, "marketdata.ranged_fetch", exc, "ranged fetch %s failed: %s", symbol, exc,
                  exc_info=True)
        return None

    # :474 (get_intraday)
    except Exception as exc:
        swallowed(log, "marketdata.get_intraday", exc, "intraday fetch %s failed: %s", symbol, exc,
                  exc_info=True)
        df = None
```

- [ ] **Step 3: Convert `ticker_directory.py`**

The file imports only the standard library. Add, after `import urllib.request` (`:22`), one blank line and `from swingbot.core.infra.swallowed import swallowed`, so `log = logging.getLogger(__name__)` follows after one blank line as today. `swallowed.py` imports nothing from `swingbot`, so this adds no cycle.

One listing for these sites; each `# :NNN` comment only names the site and is not written into the file:
```python
        # :94 (_build_directory)
        except Exception as exc:
            swallowed(log, "marketdata.ticker_directory.download", exc,
                      "Could not download ticker directory from %s: %s", url, exc, exc_info=True)

    # :105 (_save_cache)
    except Exception as exc:
        swallowed(log, "marketdata.ticker_directory.save", exc,
                  "Could not write ticker directory cache to the database", exc_info=True)

    # :122 (_load_cache)
    except Exception as exc:
        swallowed(log, "marketdata.ticker_directory.load", exc,
                  "ticker directory cache unreadable from the database; "
                  "will re-download", exc_info=True)
        return [], 0.0

    # :210 (_search_db)
    except Exception as exc:
        swallowed(log, "marketdata.ticker_directory.search", exc,
                  "ticker directory search failed in the database; "
                  "using the in-memory copy", exc_info=True)
        return None
```

- [ ] **Step 4: Convert `export_data.py`**

The file has no logger. Make the standard-library block (`:32-34`) read `import concurrent.futures`, `import logging`, `import os`, `import time`. Add `from swingbot.core.infra.swallowed import swallowed` before `from swingbot.core.marketdata import yf_safe` (`:42`). Add `log = logging.getLogger(__name__)` on its own line after `from swingbot.core.marketdata.ticker_utils import candidate_symbols` (`:43`), with one blank line before it and two after it.

`:65` (`fetch_full_history`):
```python
        except Exception as exc:
            swallowed(log, "marketdata.full_history.candidate", exc, level=logging.DEBUG)
            continue
```

`:215` and `:221` (`scrape_watchlist_history`'s nested `_worker`):
```python
        except Exception as e:
            swallowed(log, "marketdata.export_worker", e, level=logging.DEBUG)
            info = {"ticker": ticker, "error": str(e)}
            ok = False
        if on_ticker_done:
            try:
                on_ticker_done(ticker, ok)
            except Exception as exc:
                swallowed(log, "marketdata.export_worker.progress", exc, level=logging.DEBUG)
        return i, info
```

- [ ] **Step 5: Convert `backtest_cache.py`, `router.py` and `spot_metals.py`**

`backtest_cache.py`: add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot import config` (`:25`).

`:95` (`fetch`):
```python
        except Exception as e:
            swallowed(log, "marketdata.backtest_cache.candidate", e,
                      "backtest cache: candidate %s failed for %s: %s", candidate, ticker, e,
                      exc_info=True)
            continue
```

`:114` (`ensure_cached`):
```python
    except Exception as e:  # network / bad symbol / yfinance internals
        swallowed(log, "marketdata.backtest_cache.ensure", e,
                  "backtest cache fetch failed for %s: %s", ticker, e, exc_info=True)
        return CacheResult(ticker, "failed", note=str(e))
```

`providers/router.py`: add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot.core.infra.logsetup import with_current_context` (`:16`). Then `_wait`'s last handler (`:154`):
```python
    except Exception as exc:  # AlpacaMiss, anything the provider raised
        swallowed(log, "marketdata.router.wait", exc, level=logging.DEBUG)
        return None, exc
```

`spot_metals.py`: add `from swingbot.core.infra.swallowed import swallowed` after `from swingbot import config` (`:22`). Then `_fetch_quote` (`:126`), a helper-logged site:
```python
    except Exception as exc:
        swallowed(log, "marketdata.spot_quote", exc, level=logging.DEBUG)
        _note_failure(key, f"{type(exc).__name__}: {exc}")
        return None
```

- [ ] **Step 6: Verify nothing is left untagged and the tags are unique**

```bash
M=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening/swingbot/core/marketdata
python /tmp/claude-oh13/untagged.py $M/data_store.py $M/ticker_directory.py $M/export_data.py $M/backtest_cache.py $M/providers/router.py $M/spot_metals.py $M/providers/alpaca_provider.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening grep -hoE 'swallowed\((log|_?[a-z_]+), "[a-z_.]+"' -- swingbot | sed -E 's/.*"([a-z_.]+)"/\1/' | sort | uniq -d
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening diff --quiet -- swingbot/core/marketdata/providers/alpaca_provider.py && echo "alpaca_provider untouched"
```

Expected: `0 untagged []` for every file, an empty `uniq -d` (or only `scan.run_bounded` once OH7 has landed), and `alpaca_provider untouched`.

Then prove converted sites still behave and now count, in a throwaway process that imports the worktree copy:

```bash
cd /tmp && python - <<'PY'
import sys, time
from concurrent.futures import Future
sys.path.insert(0, "/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening")
from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import spot_metals, ticker_directory
from swingbot.core.marketdata.providers import router

def boom(*a, **k):
    raise RuntimeError("probe")

failed = Future()
failed.set_exception(RuntimeError("probe"))
result, exc = router._wait(failed, time.monotonic() + 1)
assert result is None and isinstance(exc, RuntimeError)
ticker_directory._download = boom
assert ticker_directory._build_directory() == []
spot_metals._raw_get = boom
assert spot_metals._fetch_quote(next(iter(spot_metals.SPOT_PAIRS))) is None
snap = sw.snapshot()
assert snap["marketdata.router.wait"]["count"] == 1, snap
assert snap["marketdata.ticker_directory.download"]["count"] == 2, snap
assert snap["marketdata.spot_quote"]["last_error"] == "RuntimeError: probe", snap
print("OK", sorted(snap))
PY
```

Expected: `OK ['marketdata.router.wait', 'marketdata.spot_quote', 'marketdata.ticker_directory.download']`. `_build_directory` tries both listing URLs, so its tag counts 2.

- [ ] **Step 7: Run the narrow tests**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python $WT/scripts/dev/testrun.py file tests/marketdata/test_frame_equivalence.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_spot_cache_rule.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_ticker_directory_db.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_backtest_cache.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_backtest_cache_dir.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_provider_router.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_provider_router_robust.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_provider_router_spot.py
python $WT/scripts/dev/testrun.py file tests/marketdata/test_spot_metals.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_intraday_archive_coverage.py
python $WT/scripts/dev/testrun.py changed
```

Expected: every run `0 failed`, `0 xfailed`. `export_data.py` has no direct test; `python -m py_compile $WT/swingbot/core/marketdata/export_data.py` must succeed, and the probe above does not need it. `changed` widens to every test reaching these modules; if it escalates to the full suite, let it run.

- [ ] **Step 8: Complexity**

```bash
WT=/home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening
python -m radon --version >/dev/null 2>&1 || python -m pip install radon
F="data_store ticker_directory export_data backtest_cache providers/router spot_metals"
python -m radon cc -s -n C $(for f in $F; do echo $WT/swingbot/core/marketdata/$f.py; done) > /tmp/claude-oh13/cc_after.txt
for f in $F; do git -C $WT show HEAD:swingbot/core/marketdata/$f.py > /tmp/claude-oh13/$(basename $f).py; done
python -m radon cc -s -n C $(for f in $F; do echo /tmp/claude-oh13/$(basename $f).py; done) > /tmp/claude-oh13/cc_before.txt
norm() { sed -E 's#.*/##; s/ [0-9]+:[0-9]+ / /' "$1"; }   # basename only, line:col dropped (conversions shift lines)
diff <(norm /tmp/claude-oh13/cc_before.txt) <(norm /tmp/claude-oh13/cc_after.txt) && echo "complexity unchanged"
```

Expected: `complexity unchanged`.

- [ ] **Step 9: Commit on the branch**

```bash
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening add swingbot/core/marketdata/data_store.py swingbot/core/marketdata/ticker_directory.py swingbot/core/marketdata/export_data.py swingbot/core/marketdata/backtest_cache.py swingbot/core/marketdata/providers/router.py swingbot/core/marketdata/spot_metals.py
git -C /home/user/Discord-Bot/.claude/worktrees/2026-10-09-v148-ops-hardening commit -m "v148 OH13: count swallowed errors in the remaining marketdata modules"
```

