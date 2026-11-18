# v232 — Live versus replay reconciliation: Part 1, foundations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V232-2" -A 400 <this file>`).

**Spec:** [2026-11-16-v232-live-replay-reconciliation-design.md](../specs/2026-11-16-v232-live-replay-reconciliation-design.md) — its `## Clarifications from the code brief` are binding.
**Index:** [2026-11-16-v232-live-replay-reconciliation_0-index.md](2026-11-16-v232-live-replay-reconciliation_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger (every cross-task name and signature) and `## Handoff` live there; every task below implicitly includes the Global Constraints.

Tasks in this part: V232-1 (export mode), V232-2 (v1 from-fill wrapper), V232-3 (v2 from-fill wrapper), V232-4 (raw bars), V232-5 (package, sessions, ignore rule). All five are mutually parallel (disjoint files); V232-4 and V232-5 both create `scripts/reports/reconcile/__init__.py` only if it is absent, with the identical content given in V232-5.

## Review Focus

- **A plan with two trades** (the live book has re-entries on one plan): the export's LEFT JOIN emits one `plan` line per (plan, trade) pair; V232-1 pins it so part 2's loader is not surprised.
- **A v180 Turtle Soup live fill:** the engine walks it with `next_open_entry.gap_aware_single_leg_walk`, which fills gaps at the open and walks the fill bar itself; `_walk_for` would score a gap stop at -1.0R instead of -1.333R. V232-2 routes it and pins the gap-stop case and the `fill_bar_check=False` case.
- **A v192 waiting plan's fill bar:** the engine checks it with `market_next_open.next_open_fill_bar` (TP1 at the open, stop, TP1), not `_fill_bar_exit`. V232-2 pins the fill-bar stop and fill-bar TP1 cases.
- **The 2026-11-01 clock change and pre-open stamps:** the same UTC minute (13:31Z) is after the open in EDT and before it in EST. V232-5 pins both sides, a weekend, Thanksgiving, an after-close stamp and the 2026-11-27 early close.
- **A split after the window but before the fetch:** the split-adjusted series then differs from the raw one by a constant factor; only a ratio that drifts inside the window is a split in the window. V232-4 pins the constant-ratio case as usable.

---

# Phase 1 — Foundations

### Task V232-1: `reconcile` export mode

**Model:** sonnet — a bounded shell + SQL addition with its tests fully specified; no cross-module design.

**Files:**
- Modify: `scripts/ops/export_book_rows.sh` (header comment :1-22; new functions `export_reconcile` and `export_deploys` after `export_rejections`; the `case` in `main`)
- Modify: `tests/scout/test_export_script.py` (append the reconcile tests; nothing existing changes)

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces (ledger contract, consumed by V232-6 `records.load_export`): `bash -s -- reconcile <since YYYY-MM-DD>`; a missing or malformed date exits 2 before any database call. Output is JSON lines, each tagged with `kind`:
  - `{"kind":"plan","plan":{plan doc},"trade":{trade doc}|null,"journal":{journal doc}|null}` — plans with `created_at >= since`, LEFT JOIN `trades` on `trades.doc->>'plan_id' = plans.plan_id`, LEFT JOIN `journal_entries` on `trade_id`. **A plan with two trades yields two `plan` lines.**
  - `{"kind":"rejection","ticker","gate","strategy","horizon","signal_date"}` — `gate_rejections` with `signal_date >= since`.
  - `{"kind":"watchlist","ticker","added_at"}` — every row of `watchlist`.
  - `{"kind":"deploy","entry":{one backups/deploys.jsonl object}}` — none when the file is absent; blank lines skipped.
  - `rows` mode, `EXPECTED_COLUMNS`, `SCRIPT` and `select_aliases` unchanged (`tests/scout/test_autopsy_rows.py` imports them).

**Traps (brief T1, T10, T11):** the whole script must keep exactly one `COPY (`, one `UNION ALL`, no word `python` and no SQL write keyword (`INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE`, comments included); `select_aliases` slices from the first `COPY (` to the first `) TO STDOUT`, so the new functions sit after `export_rows` and never contain either string. The last non-blank line stays `main "$@"`. The SQL heredoc stays quoted (`<<'SQL'`) and the date reaches SQL only as the psql variable `:'since'`. `row_to_json` emits ISO `+00:00` stamps (T10 does not apply to this mode).

- [ ] **Step 1: Write the failing tests** — append to `tests/scout/test_export_script.py`:

```python
# --- v232: the reconcile mode (JSON lines for live_replay_reconcile.py) -----------

READ_ONLY = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"


def reconcile_body(source: str) -> str:
    """export_reconcile and export_deploys: from the reconcile function to main."""
    return source[source.index("export_reconcile() {"):source.index("\nmain() {")]


def test_reconcile_has_its_own_read_only_guard_before_its_first_select(source):
    body = reconcile_body(source)
    assert READ_ONLY in body
    assert body.index(READ_ONLY) < body.index("SELECT")
    assert "SET TIME ZONE 'UTC';" in body


def test_reconcile_is_json_lines_not_a_second_copy(source):
    body = reconcile_body(source)
    assert "COPY (" not in body and "UNION ALL" not in body
    assert " -A -t " in body and " -X -q " in body and "ON_ERROR_STOP=1" in body
    assert body.count("SELECT row_to_json(x) FROM (") == 3
    assert "<<'SQL'" in body                # quoted: bash expands nothing in the SQL


def test_reconcile_plan_lines_join_trade_and_journal_docs(source):
    body = reconcile_body(source)
    assert "'plan'::text AS kind, p.doc AS plan, t.doc AS trade, j.doc AS journal" in body
    assert "LEFT JOIN trades t ON t.doc->>'plan_id' = p.plan_id" in body
    assert "LEFT JOIN journal_entries j ON j.trade_id = t.trade_id" in body
    assert "WHERE p.created_at >= (:'since')::timestamptz" in body


def test_reconcile_rejection_and_watchlist_lines(source):
    body = reconcile_body(source)
    assert ("'rejection'::text AS kind, r.ticker AS ticker, r.gate AS gate, "
            "r.strategy AS strategy, r.horizon AS horizon, r.signal_date AS signal_date") in body
    assert "FROM gate_rejections r" in body and "WHERE r.signal_date >= :'since'" in body
    assert "'watchlist'::text AS kind, w.ticker AS ticker, w.added_at AS added_at" in body
    watch = body[body.index("FROM watchlist w"):]
    assert "WHERE" not in watch.split(") x;")[0]          # the whole table


def test_reconcile_date_reaches_sql_only_as_a_psql_variable(source):
    body = reconcile_body(source)
    assert '-v since="$since"' in body
    sql = body[body.index("<<'SQL'"):body.rindex("\nSQL\n")]
    assert "$since" not in sql and "${" not in sql


def test_the_rows_copy_is_still_the_first_and_only_copy(source):
    assert source.index("COPY (") < source.index("export_reconcile() {")


PLAN_LINE = '{"kind":"plan","plan":{"plan_id":"P1"},"trade":null,"journal":null}'
WATCH_LINE = '{"kind":"watchlist","ticker":"AAA","added_at":"2026-09-01T00:00:00+00:00"}'
DOCKER_STUB = (
    'docker() { echo "ARGS $*" >&2; cat >/dev/null; '
    f"printf '%s\\n' '{PLAN_LINE}' '{WATCH_LINE}'; }}; export -f docker; "
)


def _run_reconcile(source, tmp_path, *args, stub=DOCKER_STUB):
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix())
    if not _seen_by_bash(env, "SWING_BOT_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    command = stub + "bash -s -- reconcile " + " ".join(args)
    return subprocess.run([_bash(), "-c", command], input=source.encode("utf-8"),
                          env=env, capture_output=True, timeout=60)


@pytest.mark.parametrize("since", ["", "2026-9-15", "yesterday", "'2026-09-15;'"])
def test_reconcile_refuses_a_missing_or_malformed_date_before_any_query(source, tmp_path, since):
    stub = 'docker() { echo CALLED >&2; return 9; }; export -f docker; '
    done = _run_reconcile(source, tmp_path, since, stub=stub)
    assert done.returncode == 2
    assert b"YYYY-MM-DD" in done.stderr
    assert b"CALLED" not in done.stderr and done.stdout == b""


def test_reconcile_streams_psql_then_wraps_each_deploy_line(source, tmp_path):
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "deploys.jsonl").write_bytes(
        b'{"at":"2026-09-15T08:54:50Z","commit":"abc1234"}\n'
        b"\n"
        b'{"at":"2026-10-02T10:00:00Z","commit":"def5678"}\r\n')
    done = _run_reconcile(source, tmp_path, "2026-09-15")
    assert done.returncode == 0, done.stderr
    assert done.stdout.decode("utf-8").splitlines() == [
        PLAN_LINE,
        WATCH_LINE,
        '{"kind":"deploy","entry":{"at":"2026-09-15T08:54:50Z","commit":"abc1234"}}',
        '{"kind":"deploy","entry":{"at":"2026-10-02T10:00:00Z","commit":"def5678"}}',
    ]
    args = done.stderr.decode("utf-8")
    assert "-A -t" in args and "since=2026-09-15" in args
    assert "compose exec -T db psql -U swingbot -d swingbot" in args


def test_reconcile_without_a_deploy_file_prints_no_deploy_line(source, tmp_path):
    done = _run_reconcile(source, tmp_path, "2026-09-15")
    assert done.returncode == 0, done.stderr
    assert b'"kind":"deploy"' not in done.stdout
    assert done.stdout.decode("utf-8").splitlines() == [PLAN_LINE, WATCH_LINE]


def test_reconcile_fails_when_psql_fails_and_prints_no_deploys(source, tmp_path):
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups" / "deploys.jsonl").write_bytes(b'{"at":"x","commit":"y"}\n')
    stub = 'docker() { cat >/dev/null; return 3; }; export -f docker; '
    done = _run_reconcile(source, tmp_path, "2026-09-15", stub=stub)
    assert done.returncode != 0
    assert b'"kind":"deploy"' not in done.stdout


def test_the_usage_line_names_the_reconcile_mode(source, tmp_path):
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix())
    if not _seen_by_bash(env, "SWING_BOT_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    done = subprocess.run([_bash(), "-s", "--", "nope"], input=source, env=env,
                          text=True, capture_output=True, timeout=30)
    assert done.returncode == 2
    assert "rows|rejections|reconcile <since YYYY-MM-DD>" in done.stderr
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_export_script.py`
Expected: the new tests FAIL (`ValueError: substring not found` from `reconcile_body`, the usage line); every existing test still passes.

- [ ] **Step 3: Implement the mode in `scripts/ops/export_book_rows.sh`**

Add to the header comment, after the `rejections:` paragraph (no word the guards ban):

```bash
#   bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- reconcile 2026-07-01" \
#       < scripts/ops/export_book_rows.sh > "$SCRATCH/reconcile.jsonl"
# reconcile:  v232. JSON lines from one psql session opened READ ONLY,
#             unaligned tuples only (-A -t), each line built by row_to_json and
#             tagged with "kind": plan (plan doc + trade doc + journal doc, one
#             line per plan-trade pair), rejection (gate_rejections), watchlist
#             (the whole table); then each line of backups/deploys.jsonl wrapped
#             as {"kind":"deploy","entry":...}. The since date (YYYY-MM-DD)
#             reaches SQL only as the psql variable :'since'.
```

Add these two functions after `export_rejections` (exact SQL; the tests pin these strings):

```bash
export_reconcile() {
  local since="${1:-}"
  if ! [[ "$since" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
    echo "export_book_rows: reconcile needs a since date as YYYY-MM-DD" >&2
    return 2
  fi
  docker compose exec -T db psql -U swingbot -d swingbot -X -q -A -t -v ON_ERROR_STOP=1 \
    -v since="$since" <<'SQL'
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
SET TIME ZONE 'UTC';
SELECT row_to_json(x) FROM (
  SELECT 'plan'::text AS kind, p.doc AS plan, t.doc AS trade, j.doc AS journal
  FROM plans p
  LEFT JOIN trades t ON t.doc->>'plan_id' = p.plan_id
  LEFT JOIN journal_entries j ON j.trade_id = t.trade_id
  WHERE p.created_at >= (:'since')::timestamptz
  ORDER BY p.created_at, p.plan_id, t.trade_id
) x;
SELECT row_to_json(x) FROM (
  SELECT 'rejection'::text AS kind, r.ticker AS ticker, r.gate AS gate, r.strategy AS strategy, r.horizon AS horizon, r.signal_date AS signal_date
  FROM gate_rejections r
  WHERE r.signal_date >= :'since'
  ORDER BY r.signal_date, r.ticker, r.gate, r.strategy, r.horizon
) x;
SELECT row_to_json(x) FROM (
  SELECT 'watchlist'::text AS kind, w.ticker AS ticker, w.added_at AS added_at
  FROM watchlist w
  ORDER BY w.ticker
) x;
SQL
  export_deploys
}

export_deploys() {
  local file="backups/deploys.jsonl"
  [ -f "$file" ] || return 0
  sed -e 's/\r$//' -n -e 's/^[[:space:]]*\({.*}\)[[:space:]]*$/{"kind":"deploy","entry":\1}/p' "$file"
}
```

The `main` case becomes:

```bash
    rows) export_rows ;;
    rejections) export_rejections ;;
    reconcile) export_reconcile "${2:-}" ;;
    *) echo "usage: bash -s -- rows|rejections|reconcile <since YYYY-MM-DD>" >&2; exit 2 ;;
```

`return 2` inside `export_reconcile` ends the script with 2 under `set -e`; `export_deploys` runs only after psql succeeded. The existing `test_an_unknown_mode_exits_two` keeps passing (its `"rows|rejections"` is a substring of the new usage line).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_export_script.py`
Expected: all PASS (the bash-run tests may SKIP on a WSL bash; Git Bash runs them).
Run: `python scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Expected: all PASS (it imports `EXPECTED_COLUMNS`, `SCRIPT`, `select_aliases`).

- [ ] **Step 5: Commit**

```bash
git add scripts/ops/export_book_rows.sh tests/scout/test_export_script.py
git commit -m "feat(v232): read-only reconcile export mode"
```


### Task V232-2: `simulate_exit_from_fill` (v1) and parity

**Model:** opus — a new public entry into the v1 exit engine whose parity with `simulate_exit` across five entry paths (incl. v180 and v192 routing) is the correctness contract every layer-1 number rests on.

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py` (append after `simulate_exit`, end of file; nothing existing changes)
- Create: `tests/planning/test_exit_sim_from_fill.py` (suite `planning`)

**Interfaces:**
- Consumes: existing `exit_sim._hold_cap_bars` (:836), `_walk_for` (:741), `_fill_bar_exit` (:752), `gap_reclaim.waits_for_open`, `next_open_entry.uses_next_open_fill` / `gap_aware_single_leg_walk` (:89), `market_next_open.next_open_fill_bar` (:120). All verified present.
- Produces (ledger contract, consumed by V232-7 `layer1.score`): `exit_sim.simulate_exit_from_fill(df, fill_index: int, fill_price: float, plan: TradePlanV2, *, scale_out: bool, fill_bar_check: bool = False, max_holding_days: int | None = None) -> ExitResult`.
  - hold cap = `_hold_cap_bars(plan, max_holding_days if given else HORIZONS[plan.horizon_key]["max_holding_days"])`, the same resolution `simulate_exit` applies;
  - a v180 next-open strategy (Turtle Soup) walks with `next_open_entry.gap_aware_single_leg_walk` (gap fills at the open; it reads the fill bar itself, so `fill_bar_check=False` walks a copy whose fill bar is one flat print at the fill);
  - otherwise `fill_bar_check=True` runs the engine's own fill-bar rule first (`market_next_open.next_open_fill_bar` for a v192 waiting plan, else `_fill_bar_exit`), then `_walk_for(plan, scale_out)(df, fill_index, fill_price, plan, cap)`;
  - the walk starts at the bar **after** `fill_index` for every non-v180 plan (the private walkers scan `entry_index+1 ..`).

**Why the routing (Review Focus):** `_walk_for` alone would score a Turtle Soup gap stop at -1.0R where the engine books `(open − entry)/risk` (-1.333R in the test), and would skip the v192 fill-bar order (open beyond TP1, stop, TP1). The compression short's risk-cap cancel is an entry decision, not a fill-bar rule: the wrapper starts from a fill that already happened, so it does not re-apply it (the parity fixture uses a stop inside the ceiling).

**Traps:** brief T6 — never `dataclasses.replace`/`asdict` an `ExitResult` (`tp1_index` is a plain class attribute); the tests compare `vars(a) == vars(b)`, which includes any instance-set `tp1_index`/`exit_reason`. Brief T7 — do not touch `simulate_exit` (CC 13) or `_single_leg_exit_walk` (CC 14). `next_open_entry` and `market_next_open` import this module: import them lazily inside the functions, as `_market_exit` does.

- [ ] **Step 1: Write the failing tests** — create `tests/planning/test_exit_sim_from_fill.py`:

```python
"""v232: exit_sim.simulate_exit_from_fill -- the v1 exit walk from a given fill.

Parity: handed the engine's own entry bar and price, and the engine's own
fill-bar setting for the entry type, the wrapper returns exactly what
simulate_exit returns. Layer 1 (scripts/reports/reconcile/layer1.py) always
passes fill_bar_check=False: the fill day is the day the daily walk never sees.
"""
import pytest

from swingbot.core.market.strategy_types import COMPRESSION_SHORT, TURTLE_SOUP
from swingbot.core.planning.exit_sim import _walk_for, simulate_exit, simulate_exit_from_fill
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
                strategy="Fibonacci", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
                stop_loss=95.0, tp1=106.0, tp1_fraction=0.5, tp2=110.0,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


SIGNAL = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
PATHS = {
    "win": [SIGNAL, (100.0, 101.0, 99.0, 100.5), (100.5, 103.0, 100.0, 102.5),
            (102.5, 107.0, 102.0, 106.5), (106.5, 109.0, 106.0, 108.5),
            (108.5, 111.0, 108.0, 110.5), (110.5, 111.0, 104.0, 104.5)] + [FLAT] * 8,
    "loss": [SIGNAL, (100.0, 100.5, 98.0, 99.0), (99.0, 99.5, 94.0, 94.5)] + [FLAT] * 8,
    "timeout": [SIGNAL] + [FLAT] * 14,
}


def _mirror(bars):
    """Reflect a path around 100, so a bearish plan sees what a bullish one sees."""
    return [(200.0 - o, 200.0 - l, 200.0 - h, 200.0 - c) for o, h, l, c in bars]


BEAR = dict(direction="bearish", stop_loss=105.0, tp1=94.0, tp2=90.0)
# (case id, plan overrides, mirrored path?, the engine's own fill-bar setting)
CASES = [
    ("market", {}, False, False),
    ("market_short", BEAR, True, False),
    ("stop_entry", dict(entry_type="stop_entry", trigger_price=100.4), False, False),
    ("limit", dict(entry_type="limit", trigger_price=99.5, expiry_bars=1), False, True),
    ("compression_short", dict(BEAR, strategy=COMPRESSION_SHORT, entry_type="stop_entry",
                               trigger_price=99.6, stop_ceiling_pct=10.0), True, True),
]


def _engine_and_wrapper(bars, kw, *, scale_out, fill_bar_check, signal=0, **extra):
    df = make_ohlcv(bars)
    engine = simulate_exit(df, signal, _plan(**kw), scale_out=scale_out, **extra)
    assert engine.entry_index is not None, engine.outcome
    wrapped = simulate_exit_from_fill(df, engine.entry_index, engine.entry_price, _plan(**kw),
                                      scale_out=scale_out, fill_bar_check=fill_bar_check,
                                      **extra)
    return engine, wrapped


@pytest.mark.parametrize("scale_out", [False, True])
@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_with_simulate_exit_for_every_entry_type(case, path, scale_out):
    _, kw, mirrored, check = case
    bars = _mirror(PATHS[path]) if mirrored else PATHS[path]
    engine, wrapped = _engine_and_wrapper(bars, kw, scale_out=scale_out, fill_bar_check=check)
    assert vars(wrapped) == vars(engine)


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_holds_under_a_plan_hold_cap(case):
    _, kw, mirrored, check = case
    bars = _mirror(PATHS["timeout"]) if mirrored else PATHS["timeout"]
    engine, wrapped = _engine_and_wrapper(bars, dict(kw, hold_cap_bars=3), scale_out=False,
                                          fill_bar_check=check)
    assert engine.outcome == "timeout"
    assert vars(wrapped) == vars(engine)


def test_parity_with_an_explicit_max_holding_days():
    engine, wrapped = _engine_and_wrapper(PATHS["timeout"], {}, scale_out=True,
                                          fill_bar_check=False, max_holding_days=2)
    assert engine.exit_index == 2
    assert vars(wrapped) == vars(engine)


LIMIT = dict(entry_type="limit", trigger_price=99.5, expiry_bars=1)
STOPPED_FILL_BAR = [SIGNAL, (100.0, 100.5, 94.0, 96.0)] + PATHS["win"][2:]


def test_limit_fill_bar_stop_matches_the_engine_when_checked():
    engine, wrapped = _engine_and_wrapper(STOPPED_FILL_BAR, LIMIT, scale_out=False,
                                          fill_bar_check=True)
    assert (engine.outcome, engine.exit_index, engine.r_total) == ("loss", 1, -1.0)
    assert vars(wrapped) == vars(engine)


def test_unchecked_fill_bar_is_never_read():
    df = make_ohlcv(STOPPED_FILL_BAR)
    res = simulate_exit_from_fill(df, 1, 99.5, _plan(**LIMIT), scale_out=False)
    assert res.entry_index == 1 and res.exit_index != 1


def test_a_checked_fill_at_the_stop_is_a_flat_scratch():
    df = make_ohlcv(PATHS["win"])
    res = simulate_exit_from_fill(df, 1, 95.0, _plan(), scale_out=False, fill_bar_check=True)
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == ("scratch", 0.0,
                                                                "gap_through_stop")


# --- v180 Turtle Soup: the gap-aware walk ------------------------------------

TS = dict(strategy=TURTLE_SOUP, stop_loss=97.0, tp1=106.0, tp1_fraction=1.0, tp2=None,
          stop_ceiling_pct=10.0)
TS_GAP_STOP = [SIGNAL, (100.0, 101.0, 99.0, 100.5), (100.5, 101.0, 99.5, 100.0),
               (96.0, 97.5, 95.0, 96.5)] + [FLAT] * 6
TS_FILL_BAR_STOP = [SIGNAL, (100.0, 101.0, 96.5, 99.0), (99.0, 106.5, 98.5, 106.0)] + [FLAT] * 6


def test_turtle_soup_gap_stop_books_the_open_not_the_stop():
    df = make_ohlcv(TS_GAP_STOP)
    engine = simulate_exit(df, 0, _plan(**TS))
    wrapped = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS), scale_out=False,
                                      fill_bar_check=True)
    assert (engine.entry_index, engine.entry_price, engine.r_total) == (1, 100.0, -1.333)
    assert vars(wrapped) == vars(engine)
    plain = _walk_for(_plan(**TS), False)(df, 1, 100.0, _plan(**TS), 10)
    assert plain.r_total != engine.r_total          # why the wrapper routes v180


def test_turtle_soup_checked_fill_bar_is_walked_as_session_one():
    df = make_ohlcv(TS_FILL_BAR_STOP)
    engine = simulate_exit(df, 0, _plan(**TS))
    wrapped = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS), scale_out=False,
                                      fill_bar_check=True)
    assert (engine.outcome, engine.exit_index) == ("loss", 1)
    assert vars(wrapped) == vars(engine)


def test_turtle_soup_unchecked_fill_bar_is_skipped_and_df_untouched():
    df = make_ohlcv(TS_FILL_BAR_STOP)
    before = df.copy()
    res = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS), scale_out=False)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("win", 1, 2, 2.0)
    assert df.equals(before)


@pytest.mark.parametrize("check", [False, True])
def test_turtle_soup_hold_cap_counts_the_fill_session(check):
    df = make_ohlcv(PATHS["timeout"])
    engine = simulate_exit(df, 0, _plan(**TS, hold_cap_bars=3))
    wrapped = simulate_exit_from_fill(df, 1, 100.0, _plan(**TS, hold_cap_bars=3),
                                      scale_out=False, fill_bar_check=check)
    assert engine.exit_index == 3                    # fill bar 1 is session 1 of 3
    assert vars(wrapped) == vars(engine)


# --- v192 waiting plan: the next-open fill-bar order -------------------------

WAIT = dict(source="confluence", strategy="S/R Confluence", stop_loss=98.5, tp1=103.0,
            tp2=105.0, waits_next_open=True)
WAIT_PATHS = {
    "fill_bar_stop": [SIGNAL, (100.0, 100.5, 98.0, 99.0)] + [FLAT] * 6,
    "fill_bar_tp1": [SIGNAL, (100.0, 103.5, 99.5, 103.2), (103.2, 104.0, 102.5, 103.8),
                     (103.8, 105.5, 103.5, 105.2)] + [FLAT] * 6,
    "clean": PATHS["win"],
    "timeout": PATHS["timeout"],
}


@pytest.mark.parametrize("scale_out", [False, True])
@pytest.mark.parametrize("path", sorted(WAIT_PATHS))
def test_v192_waiting_plan_parity(path, scale_out):
    engine, wrapped = _engine_and_wrapper(WAIT_PATHS[path], WAIT, scale_out=scale_out,
                                          fill_bar_check=True)
    assert (engine.entry_index, engine.entry_price) == (1, 100.0)
    assert vars(wrapped) == vars(engine)


def test_v192_fill_bar_stop_and_tp1_are_the_engines():
    stop, _ = _engine_and_wrapper(WAIT_PATHS["fill_bar_stop"], WAIT, scale_out=False,
                                  fill_bar_check=True)
    tp1, _ = _engine_and_wrapper(WAIT_PATHS["fill_bar_tp1"], WAIT, scale_out=False,
                                 fill_bar_check=True)
    assert (stop.outcome, stop.exit_index, stop.r_total) == ("loss", 1, -1.0)
    assert (tp1.outcome, tp1.exit_index) == ("win", 1)


def test_v192_hold_cap_parity():
    engine, wrapped = _engine_and_wrapper(PATHS["timeout"], dict(WAIT, hold_cap_bars=3),
                                          scale_out=False, fill_bar_check=True)
    assert engine.exit_index == 3
    assert vars(wrapped) == vars(engine)


def test_v192_unchecked_fill_bar_is_never_read():
    df = make_ohlcv(WAIT_PATHS["fill_bar_stop"])
    res = simulate_exit_from_fill(df, 1, 100.0, _plan(**WAIT), scale_out=False)
    assert res.exit_index != 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_from_fill.py`
Expected: collection error — `ImportError: cannot import name 'simulate_exit_from_fill'`.

- [ ] **Step 3: Implement** — append to the end of `swingbot/core/planning/exit_sim.py`:

```python
# --- v232: the exit walk from a given fill -------------------------------------

def _from_fill_bar(df, fill_index: int, fill_price: float, plan: TradePlanV2,
                   scale_out: bool, cap: int) -> ExitResult | None:
    """The engine's own fill-bar exit for this plan, or None when the bar is clean.
    A v192 waiting plan takes market_next_open's order (open beyond TP1, stop, TP1);
    every other plan the v113 stop-first check (_fill_bar_exit)."""
    if gap_reclaim.waits_for_open(plan):
        from .market_next_open import next_open_fill_bar   # it imports this module
        return next_open_fill_bar(df, fill_index, fill_price, plan, scale_out, cap)
    return _fill_bar_exit(df, fill_index, fill_price, plan)


def _flat_fill_bar(df, fill_index: int, fill_price: float):
    """A copy of df whose fill bar is one flat print at the fill price, so a walk
    that reads the fill bar itself (v180's gap-aware walk) books nothing there
    unless the fill already sits at a level. The caller's frame is untouched."""
    frame = df.copy()
    for col in ("Open", "High", "Low", "Close"):
        frame.iloc[fill_index, frame.columns.get_loc(col)] = fill_price
    return frame


def _gap_aware_from_fill(df, fill_index: int, fill_price: float, plan: TradePlanV2,
                         cap: int, fill_bar_check: bool) -> ExitResult:
    """v180 next-open strategies: the gap-aware single-leg walk, which walks the
    fill bar as session 1. Unchecked, that bar is flattened first."""
    from .next_open_entry import gap_aware_single_leg_walk   # it imports this module
    frame = df if fill_bar_check else _flat_fill_bar(df, fill_index, fill_price)
    return gap_aware_single_leg_walk(frame, fill_index, fill_price, plan, cap)


def simulate_exit_from_fill(
    df,
    fill_index: int,
    fill_price: float,
    plan: TradePlanV2,
    *,
    scale_out: bool,
    fill_bar_check: bool = False,
    max_holding_days: int | None = None,
) -> ExitResult:
    """v232: the v1 exit walk from a fill that already happened (bar ``fill_index``
    at ``fill_price``), for a live trade's own fill.

    The hold cap is resolved exactly as simulate_exit resolves it. A v180
    next-open strategy walks with next_open_entry's gap-aware walk; every other
    plan with ``_walk_for(plan, scale_out)``, which starts at the bar after the
    fill. ``fill_bar_check`` first runs the engine's own fill-bar rule (the v192
    next-open order for a waiting plan, else ``_fill_bar_exit``); simulate_exit
    applies it to limit and compression-short fills and to v192 waiting plans,
    and the parity tests pass that setting. Live-replay reconciliation passes
    False: the fill day is the day the daily walk never sees. The compression
    short's risk-cap cancel is an entry decision and is not re-applied here.
    """
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]
    cap = _hold_cap_bars(plan, max_holding_days)
    from .next_open_entry import uses_next_open_fill   # it imports this module
    if uses_next_open_fill(plan):
        return _gap_aware_from_fill(df, fill_index, fill_price, plan, cap, fill_bar_check)
    if fill_bar_check:
        early = _from_fill_bar(df, fill_index, fill_price, plan, scale_out, cap)
        if early is not None:
            return early
    return _walk_for(plan, scale_out)(df, fill_index, fill_price, plan, cap)
```

If a parity case fails, the wrapper is wrong, never the engine: re-read the engine branch the case takes (`_market_exit`, `_limit_entry_exit`, `_compression_fill`, `next_open_exit`, `market_next_open._filled`) and match it. Never edit an existing function to make a test pass. If a fixture itself does not fill (the `entry_index is not None` assertion fires) or does not reach the outcome a test names, adjust the fixture's bars or levels, not the wrapper, and keep the case's intent (the -1.333R gap stop needs fill 100, stop 97, a later open at 96).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_from_fill.py`
Expected: all PASS.
Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_entry.py` and `python scripts/dev/testrun.py file tests/planning/test_exit_sim_hold_cap.py`
Expected: all PASS (nothing existing changed).
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (every new function far below 15).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/exit_sim.py tests/planning/test_exit_sim_from_fill.py
git commit -m "feat(v232): simulate_exit_from_fill, the v1 walk from a given fill"
```

### Task V232-3: `simulate_exit_v2_from_fill` and parity

**Model:** opus — the v2 twin of V232-2: a public entry into the cost-booking v2 walk whose parity with `simulate_exit_v2` (both cost models, every entry type) layer 1's second fill model rests on.

**Files:**
- Modify: `swingbot/core/planning/exit_sim_v2.py` (append after `simulate_exit_v2`, end of file :451; nothing existing changes)
- Create: `tests/planning/test_exit_sim_v2_from_fill.py` (suite `planning`)

**Interfaces:**
- Consumes: existing `exit_sim_v2.fill_bar_exit` (:284, public since v173), `walk_v2` (:245), `_hold_cap_bars` (already imported from `exit_sim`, :28-29), `fills.require_supported`, `HORIZONS`. All verified present. Nothing from V232-2 (disjoint file).
- Produces (ledger contract, consumed by V232-7 `layer1.score`): `exit_sim_v2.simulate_exit_v2_from_fill(df, fill_index: int, fill_price: float, plan: TradePlanV2, instrument: InstrumentSpec, *, scale_out: bool, fill_bar_check: bool = False, max_holding_days: int | None = None, indicator_df=None) -> ExitResult` — `fills.require_supported(instrument.fill_model)`; hold cap resolved exactly as `simulate_exit_v2` resolves it; `fill_bar_exit` first when `fill_bar_check`; then `walk_v2(df, fill_index, fill_price, plan, cap, instrument, scale_out=scale_out, indicator_df=indicator_df)`.

**Why so small (spec clarification 1):** v2 has no v180 or v192 routing — every v2 entry (market at the next open, limit, stop entry, compression short) ends in `_filled`, which is `fill_bar_exit` then `walk_v2`; the v173 precedent `analytics/override_fidelity.py:engine_path` is the same two calls. The parity tests therefore pass `fill_bar_check=True` for every entry type, and layer 1 passes `False`. The v212 arm limit's gap-stopped fill (`_gap_stopped_exit`) is not a fill path (filled and stopped at one open) and has no from-fill form; a normal arm-limit fill ends in `_filled` like the rest.

**Traps:** brief T6 — compare `vars(a) == vars(b)`, never copy an `ExitResult`; `walk_v2` sets `tp1_index` on the instance, and `vars` sees it. Do not touch `simulate_exit_v2` or `override_fidelity`.

- [ ] **Step 1: Write the failing tests** — create `tests/planning/test_exit_sim_v2_from_fill.py`:

```python
"""v232: exit_sim_v2.simulate_exit_v2_from_fill -- the v2 walk from a given fill.

Parity: handed simulate_exit_v2's own entry bar and price, with the fill-bar
check every v2 entry applies, the wrapper returns exactly what the engine
returns, under the costed v2 instrument and a zero-cost copy. Layer 1 passes
fill_bar_check=False.
"""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.exit_sim_v2 import (ENTRY_GAP_SCRATCH, simulate_exit_v2,
                                                simulate_exit_v2_from_fill, walk_v2)
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
INSTRUMENTS = {"costed": V2, "free": FREE}


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
                strategy="Fibonacci", horizon_key="2w", direction="bullish",
                entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
                stop_loss=95.0, tp1=106.0, tp1_fraction=0.5, tp2=110.0,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
                quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
                status=PlanStatus.PENDING, status_history=[])
    base.update(kw)
    return TradePlanV2(**base)


SIGNAL = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
PATHS = {
    "win": [SIGNAL, (100.0, 101.0, 99.0, 100.5), (100.5, 103.0, 100.0, 102.5),
            (102.5, 107.0, 102.0, 106.5), (106.5, 109.0, 106.0, 108.5),
            (108.5, 111.0, 108.0, 110.5), (110.5, 111.0, 104.0, 104.5)] + [FLAT] * 8,
    "loss": [SIGNAL, (100.0, 100.5, 98.0, 99.0), (99.0, 99.5, 94.0, 94.5)] + [FLAT] * 8,
    "timeout": [SIGNAL] + [FLAT] * 14,
}


def _mirror(bars):
    """Reflect a path around 100, so a bearish plan sees what a bullish one sees."""
    return [(200.0 - o, 200.0 - l, 200.0 - h, 200.0 - c) for o, h, l, c in bars]


BEAR = dict(direction="bearish", stop_loss=105.0, tp1=94.0, tp2=90.0)
# (case id, plan overrides, mirrored path?)
CASES = [
    ("market", {}, False),
    ("market_short", BEAR, True),
    ("stop_entry", dict(entry_type="stop_entry", trigger_price=100.4), False),
    ("limit", dict(entry_type="limit", trigger_price=99.5, expiry_bars=1), False),
    ("compression_short", dict(BEAR, strategy=COMPRESSION_SHORT, entry_type="stop_entry",
                               trigger_price=99.6, stop_ceiling_pct=10.0), True),
    ("v192_waiting", dict(source="confluence", strategy="S/R Confluence", stop_loss=98.5,
                          tp1=103.0, tp2=105.0, waits_next_open=True), False),
]


def _engine_and_wrapper(bars, kw, instrument, *, scale_out, fill_bar_check=True, **extra):
    df = make_ohlcv(bars)
    engine = simulate_exit_v2(df, 0, _plan(**kw), instrument, scale_out=scale_out, **extra)
    assert engine.entry_index is not None, (engine.outcome, engine.cancel_reason)
    wrapped = simulate_exit_v2_from_fill(df, engine.entry_index, engine.entry_price,
                                         _plan(**kw), instrument, scale_out=scale_out,
                                         fill_bar_check=fill_bar_check, **extra)
    return engine, wrapped


@pytest.mark.parametrize("instrument", sorted(INSTRUMENTS))
@pytest.mark.parametrize("scale_out", [False, True])
@pytest.mark.parametrize("path", sorted(PATHS))
@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_with_simulate_exit_v2_for_every_entry_type(case, path, scale_out, instrument):
    _, kw, mirrored = case
    bars = _mirror(PATHS[path]) if mirrored else PATHS[path]
    engine, wrapped = _engine_and_wrapper(bars, kw, INSTRUMENTS[instrument],
                                          scale_out=scale_out)
    assert vars(wrapped) == vars(engine)


@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_parity_holds_under_a_plan_hold_cap(case):
    _, kw, mirrored = case
    bars = _mirror(PATHS["timeout"]) if mirrored else PATHS["timeout"]
    engine, wrapped = _engine_and_wrapper(bars, dict(kw, hold_cap_bars=3), V2,
                                          scale_out=False)
    assert engine.outcome == "timeout"
    assert vars(wrapped) == vars(engine)


def test_parity_with_an_explicit_max_holding_days():
    engine, wrapped = _engine_and_wrapper(PATHS["timeout"], {}, FREE, scale_out=True,
                                          max_holding_days=2)
    assert (engine.entry_index, engine.exit_index) == (1, 3)
    assert vars(wrapped) == vars(engine)


STOPPED_FILL_BAR = [SIGNAL, (100.0, 100.5, 94.0, 96.0)] + PATHS["win"][2:]


def test_checked_fill_bar_stop_matches_the_engine():
    engine, wrapped = _engine_and_wrapper(STOPPED_FILL_BAR, {}, FREE, scale_out=False)
    assert (engine.outcome, engine.exit_index) == ("loss", 1)
    assert vars(wrapped) == vars(engine)


def test_unchecked_fill_bar_is_never_read():
    df = make_ohlcv(STOPPED_FILL_BAR)
    res = simulate_exit_v2_from_fill(df, 1, 100.0, _plan(), FREE, scale_out=False)
    assert res.entry_index == 1 and res.exit_index != 1


def test_a_checked_fill_at_the_stop_is_the_entry_gap_scratch():
    df = make_ohlcv(PATHS["win"])
    res = simulate_exit_v2_from_fill(df, 1, 95.0, _plan(), V2, scale_out=False,
                                     fill_bar_check=True)
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == ("scratch", 0.0,
                                                                ENTRY_GAP_SCRATCH)


def test_unchecked_equals_walk_v2_with_the_resolved_cap_and_indicator_frame():
    df = make_ohlcv(PATHS["win"])
    indicators = df.copy()
    res = simulate_exit_v2_from_fill(df, 1, 100.0, _plan(), V2, scale_out=True,
                                     indicator_df=indicators)
    direct = walk_v2(df, 1, 100.0, _plan(), 14, V2, scale_out=True, indicator_df=indicators)
    assert vars(res) == vars(direct)                 # 2w horizon: max_holding_days 14


def test_the_indicator_frame_reaches_walk_v2():
    df = make_ohlcv(PATHS["win"])
    with pytest.raises(ValueError, match="same index and length"):
        simulate_exit_v2_from_fill(df, 1, 100.0, _plan(), V2, scale_out=True,
                                   indicator_df=df.iloc[:-1])


def test_an_unsupported_fill_model_is_refused_like_the_engine():
    v1_fills = resolve("v1").fill_model
    bad = dataclasses.replace(V2, fill_model=v1_fills)
    with pytest.raises(ValueError, match="next_open"):
        simulate_exit_v2_from_fill(make_ohlcv(PATHS["win"]), 1, 100.0, _plan(), bad,
                                   scale_out=False)
```

`HORIZONS["2w"]["max_holding_days"]` is 14 (`strategy_types.py:90`) and `resolve("v1").fill_model` is `V1_FILLS` (`market_entry="signal_close"`, `contract.py:106`), which `require_supported` refuses.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_from_fill.py`
Expected: collection error — `ImportError: cannot import name 'simulate_exit_v2_from_fill'`.

- [ ] **Step 3: Implement** — append to the end of `swingbot/core/planning/exit_sim_v2.py`:

```python
def simulate_exit_v2_from_fill(df, fill_index: int, fill_price: float, plan: TradePlanV2,
                               instrument: InstrumentSpec, *, scale_out: bool,
                               fill_bar_check: bool = False,
                               max_holding_days: int | None = None,
                               indicator_df: pd.DataFrame | None = None) -> ExitResult:
    """v232: the v2 exit walk from a fill that already happened (bar ``fill_index``
    at ``fill_price``), for a live trade's own fill.

    The same hold-cap resolution as simulate_exit_v2. ``fill_bar_check`` runs
    fill_bar_exit first, exactly as every v2 entry's _filled does (the v173
    override_fidelity.engine_path precedent); then walk_v2 from the bar after
    the fill. Live-replay reconciliation passes False: the fill day is the day
    the daily walk never sees. ``indicator_df`` is handed to walk_v2 unchanged.
    """
    fills.require_supported(instrument.fill_model)
    if max_holding_days is None:
        max_holding_days = HORIZONS[plan.horizon_key]["max_holding_days"]
    cap = _hold_cap_bars(plan, max_holding_days)
    if fill_bar_check:
        early = fill_bar_exit(df, fill_index, fill_price, plan, instrument)
        if early is not None:
            return early
    return walk_v2(df, fill_index, fill_price, plan, cap, instrument,
                   scale_out=scale_out, indicator_df=indicator_df)
```

If a parity case fails, the wrapper is wrong, never the engine: compare with the engine branch the case takes (`_market_entry_v2`, `_limit_entry_v2`, `_stop_entry_v2`, each ending in `_filled`). Never edit an existing function. If a fixture does not fill (the `entry_index is not None` assertion fires; the v192 waiting plan's 1.5% stop sits inside the 2% non-strategy ceiling, and v2 does not route it), adjust the fixture's bars or levels, not the wrapper.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_from_fill.py`
Expected: all PASS.
Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_entry.py` and `python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_walk.py`
Expected: all PASS (nothing existing changed).
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/exit_sim_v2.py tests/planning/test_exit_sim_v2_from_fill.py
git commit -m "feat(v232): simulate_exit_v2_from_fill, the v2 walk from a given fill"
```

### Task V232-4: Raw daily bars: provider `adjustment` keyword and the scratch stores

**Model:** sonnet — one defaulted keyword threaded through a provider plus a small, fully specified file-store module; no engine logic.

**Files:**
- Modify: `swingbot/core/marketdata/providers/alpaca_provider.py` (`_bars` :106-113, `daily_bars_between` :120-125 only)
- Modify: `tests/marketdata/test_alpaca_provider.py` (append two tests after `test_daily_bars_between_sends_the_range_on_sip_all`)
- Create: `scripts/reports/reconcile/__init__.py` **only if absent** (content below, identical to V232-5's)
- Create: `scripts/reports/reconcile/raw_bars.py`
- Create: `tests/scout/test_reconcile_raw_bars.py` (suite `scout`)

**Split:** this task passed 20 KB and is split: V232-4 builds the provider keyword and the stores (fetch, write, read back); **V232-4b** appends `refusal`, `bars_manifest`, `SPLIT_DRIFT` and `REFUSALS` to the same two files and runs after it.

**Interfaces:**
- Consumes: existing `history_store.load` / `ENV_VAR` (`"HISTORY_STORE_DIR"`) / `MANIFEST_NAME` / `OHLCV_COLUMNS`, `data_store.safe_symbol`, `alpaca.data.enums.Adjustment`. Nothing from other v232 tasks.
- Produces (ledger contract):
  - `AlpacaProvider._bars(tickers, timeframe, start, end=None, *, adjustment=Adjustment.ALL)`; `daily_bars_between(tickers, start, end, *, adjustment=Adjustment.ALL)` — default byte-identical.
  - `raw_bars.KINDS = ("raw", "split")`; `store_dir(root: Path, kind: str) -> Path` (`root / kind`; unknown kind: `ValueError`).
  - `use_store(path: Path)` — context manager; sets `HISTORY_STORE_DIR` to the absolute path, restores the previous value (or unsets) on exit.
  - `write_frame(store: Path, ticker: str, frame: pd.DataFrame) -> str` — writes `<store>/daily/<SAFE>.csv` (naive `Date` index, OHLCV, `\n` line ends), returns the file's SHA-256.
  - `fetch_bars(tickers, start: date, end: date, root: Path, *, provider, out=print) -> dict` — `{kind: manifest}`; one request per ticker and kind; the manifest (`<root>/<kind>/daily/_manifest.json`: `kind`, `start`, `end`, `tickers: {T: {"status": "ok", "sha256", "rows", "first", "last"} | {"status": "empty"}}`) is rewritten atomically after each ticker, so a restart skips finished tickers; a store fetched for another window raises `ValueError` ("use a new --bars-root").
  - `load_bars(ticker: str, root: Path, kind: str = "raw") -> pd.DataFrame | None` — `history_store.load(ticker, "daily")` under `use_store`.

**Traps:** brief T12 — Alpaca returns tz-aware UTC with lowercase columns; `daily_bars_between` already normalises through `to_yf_daily` (naive NY dates, `Open..Volume`), and `write_frame` refuses a tz-aware index. The adjusted watchlist store (`data/market_data/`) is never written or read here. Never edit `history_bars` or `daily_bars` (they stay `Adjustment.ALL`). The Alpaca free plan rate-limits; an `AlpacaMiss` mid-fetch propagates and a re-run resumes from the manifests.

- [ ] **Step 1: Write the failing tests**

Append to `tests/marketdata/test_alpaca_provider.py`:

```python
# --- v232: a requested adjustment for the reconciliation's raw bars ------------------

@pytest.mark.parametrize("adjustment, wire", [(ap.Adjustment.RAW, "raw"),
                                              (ap.Adjustment.SPLIT, "split")])
def test_daily_bars_between_passes_a_requested_adjustment(adjustment, wire):
    from datetime import date
    c = FakeClient(bars=_barset(["AAPL"]))
    out = _prov(c).daily_bars_between(["AAPL"], date(2026, 9, 20), date(2026, 9, 25),
                                      adjustment=adjustment)
    assert str(c.requests[0].adjustment.value) == wire
    assert str(c.requests[0].feed.value) == "sip"
    assert list(out["AAPL"].columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_the_other_bar_paths_stay_fully_adjusted():
    c = FakeClient(bars=_barset(["AAPL"]))
    _prov(c).daily_bars(["AAPL"], "1y")
    _prov(c).intraday_bars("AAPL", "1h")
    assert [str(r.adjustment.value) for r in c.requests] == ["all", "all"]
```

Create `tests/scout/test_reconcile_raw_bars.py`:

```python
"""v232: raw and split-adjusted daily bars in two scratch history stores."""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))
from reconcile import raw_bars  # noqa: E402

START, END = date(2026, 9, 1), date(2026, 9, 30)


@pytest.fixture(autouse=True)
def _no_override(monkeypatch):
    monkeypatch.delenv("HISTORY_STORE_DIR", raising=False)


def _frame(closes, start="2026-09-01"):
    idx = pd.bdate_range(start=start, periods=len(closes), name="Date")
    rows = [(c, c * 1.01, c * 0.99, c, 1_000_000.0) for c in closes]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=idx)


class FakeProvider:
    """daily_bars_between keyed by (ticker, adjustment value)."""

    def __init__(self, frames):
        self.frames, self.calls = frames, []

    def daily_bars_between(self, tickers, start, end, *, adjustment):
        self.calls.append((tuple(tickers), start, end, adjustment.value))
        return {t: self.frames[(t, adjustment.value)] for t in tickers
                if (t, adjustment.value) in self.frames}


def _both(ticker, closes, factor=1.0):
    return {(ticker, "raw"): _frame(closes), (ticker, "split"): _frame([c * factor for c in closes])}


def test_store_dir_names_each_kind_and_refuses_others(tmp_path):
    assert raw_bars.store_dir(tmp_path, "raw") == tmp_path / "raw"
    assert raw_bars.store_dir(tmp_path, "split") == tmp_path / "split"
    with pytest.raises(ValueError, match="unknown bar kind"):
        raw_bars.store_dir(tmp_path, "all")


def test_use_store_sets_then_restores_the_override(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_STORE_DIR", "elsewhere")
    with raw_bars.use_store(tmp_path / "raw"):
        assert os.environ["HISTORY_STORE_DIR"] == str((tmp_path / "raw").resolve())
    assert os.environ["HISTORY_STORE_DIR"] == "elsewhere"
    monkeypatch.delenv("HISTORY_STORE_DIR")
    with raw_bars.use_store(tmp_path / "raw"):
        pass
    assert "HISTORY_STORE_DIR" not in os.environ


def test_write_frame_round_trips_through_the_store_reader(tmp_path):
    frame = _frame([100.0, 101.0, 102.0])
    sha = raw_bars.write_frame(tmp_path / "raw", "AAA", frame)
    path = tmp_path / "raw" / "daily" / "AAA.csv"
    assert sha == hashlib.sha256(path.read_bytes()).hexdigest()
    assert b"\r\n" not in path.read_bytes()
    back = raw_bars.load_bars("AAA", tmp_path, "raw")
    pd.testing.assert_frame_equal(back, frame, check_freq=False)


def test_write_frame_refuses_a_tz_aware_index(tmp_path):
    frame = _frame([100.0])
    frame.index = frame.index.tz_localize("UTC")
    with pytest.raises(ValueError, match="tz-aware"):
        raw_bars.write_frame(tmp_path / "raw", "AAA", frame)


def test_fetch_bars_writes_both_kinds_with_a_manifest_each(tmp_path):
    provider = FakeProvider(_both("AAA", [100.0, 101.0], factor=0.5))
    seen = []
    got = raw_bars.fetch_bars(["aaa"], START, END, tmp_path, provider=provider, out=seen.append)
    assert sorted(got) == ["raw", "split"]
    assert [c[3] for c in provider.calls] == ["raw", "split"]
    entry = got["raw"]["tickers"]["AAA"]
    assert (entry["status"], entry["rows"], entry["first"], entry["last"]) == (
        "ok", 2, "2026-09-01", "2026-09-02")
    assert (got["raw"]["start"], got["raw"]["end"]) == ("2026-09-01", "2026-09-30")
    assert (tmp_path / "split" / "daily" / "_manifest.json").is_file()
    assert raw_bars.load_bars("AAA", tmp_path, "split")["Close"].tolist() == [50.0, 50.5]
    assert any("(100%)" in line for line in seen)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["raw", "split"]


def test_fetch_bars_resumes_per_ticker(tmp_path):
    frames = {**_both("AAA", [100.0]), **_both("BBB", [50.0])}
    raw_bars.fetch_bars(["AAA"], START, END, tmp_path, provider=FakeProvider(frames),
                        out=lambda _: None)
    again = FakeProvider(frames)
    raw_bars.fetch_bars(["AAA", "BBB"], START, END, tmp_path, provider=again,
                        out=lambda _: None)
    assert [c[0] for c in again.calls] == [("BBB",), ("BBB",)]


def test_a_ticker_without_bars_is_recorded_empty_and_loads_as_none(tmp_path):
    got = raw_bars.fetch_bars(["ZZZ"], START, END, tmp_path, provider=FakeProvider({}),
                              out=lambda _: None)
    assert got["raw"]["tickers"]["ZZZ"] == {"status": "empty"}
    assert raw_bars.load_bars("ZZZ", tmp_path) is None


def test_a_store_fetched_for_another_window_is_refused(tmp_path):
    provider = FakeProvider(_both("AAA", [100.0]))
    raw_bars.fetch_bars(["AAA"], START, END, tmp_path, provider=provider, out=lambda _: None)
    with pytest.raises(ValueError, match="new --bars-root"):
        raw_bars.fetch_bars(["AAA"], START, date(2026, 10, 30), tmp_path, provider=provider,
                            out=lambda _: None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
Expected: the two new tests FAIL (`TypeError: ... unexpected keyword argument 'adjustment'`); the rest PASS.
Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_raw_bars.py`
Expected: collection error — `ModuleNotFoundError: No module named 'reconcile'` (or `cannot import name 'raw_bars'` when V232-5 created the package first).

- [ ] **Step 3: Implement**

In `swingbot/core/marketdata/providers/alpaca_provider.py`, `_bars` and `daily_bars_between` become (nothing else changes):

```python
    def _bars(self, tickers, timeframe, start, end=None, *, adjustment=Adjustment.ALL):
        latest = self._now() - SIP_DELAY
        by_symbol = {to_alpaca_symbol(t): t for t in tickers}
        req = StockBarsRequest(symbol_or_symbols=list(by_symbol), timeframe=timeframe,
                               start=start, end=latest if end is None else min(end, latest),
                               feed=DataFeed.SIP, adjustment=adjustment)
        raw = self._call("get_stock_bars", req, self._bars_client) or {}
        return {by_symbol[s]: df for s, df in _frames_from_raw(raw).items() if s in by_symbol}
```

```python
    def daily_bars_between(self, tickers, start, end, *, adjustment=Adjustment.ALL):
        """v171 D4: daily bars dated start..end (inclusive), SIP, Adjustment.ALL.
        v232: ``adjustment`` (default ALL, unchanged) lets the live-replay
        reconciliation ask for RAW and SPLIT bars; nothing else passes it."""
        lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        hi = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)
        raw = self._bars(tickers, TimeFrame.Day, lo, hi, adjustment=adjustment)
        return {t: to_yf_daily(df) for t, df in raw.items() if not df.empty}
```

If `scripts/reports/reconcile/__init__.py` does not exist yet, create it with exactly this content (V232-5 creates the same file):

```python
"""v232: live versus replay reconciliation (scripts/reports/live_replay_reconcile.py)."""
from pathlib import Path

#: Git-ignored work directory: per-trade rows, layer 2 checkpoints, raw bars.
WORK_DIR = Path("data/v232")
```

Create `scripts/reports/reconcile/raw_bars.py` (V232-4b appends the refusal section to its end):

```python
"""v232: unadjusted daily bars for layer 1, in two scratch history stores.

Live fills are real quotes; the v162 store's bars are split- and dividend-
adjusted (Adjustment.ALL). Layer 1 walks RAW bars. The SPLIT-adjusted copy
exists only to find a split inside the window: split.Close / raw.Close is
constant unless a split falls inside the bars compared (a split after the
window, before the fetch, shifts every bar alike and is usable).

Layout: <root>/<kind>/daily/<SAFE>.csv and <root>/<kind>/daily/_manifest.json
for kind in KINDS, read back with history_store.load(ticker, "daily") while
HISTORY_STORE_DIR points at <root>/<kind> (use_store). The adjusted watchlist
store is never written or read here.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
from alpaca.data.enums import Adjustment

from swingbot.core.marketdata import history_store
from swingbot.core.marketdata.data_store import safe_symbol

KINDS = ("raw", "split")
ADJUSTMENTS = {"raw": Adjustment.RAW, "split": Adjustment.SPLIT}
OK, EMPTY = "ok", "empty"


def store_dir(root: Path, kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown bar kind {kind!r}; expected one of {KINDS}")
    return Path(root) / kind


@contextlib.contextmanager
def use_store(path: Path):
    """Point history_store at one scratch store; restore the previous override."""
    previous = os.environ.get(history_store.ENV_VAR)
    os.environ[history_store.ENV_VAR] = str(Path(path).resolve())
    try:
        yield Path(path)
    finally:
        if previous is None:
            os.environ.pop(history_store.ENV_VAR, None)
        else:
            os.environ[history_store.ENV_VAR] = previous


def _daily_dir(store: Path) -> Path:
    return Path(store) / "daily"


def write_frame(store: Path, ticker: str, frame: pd.DataFrame) -> str:
    """One ticker's daily bars as the store's CSV (naive Date index); its SHA-256."""
    out = frame[history_store.OHLCV_COLUMNS].astype("float64")
    index = pd.DatetimeIndex(out.index)
    if index.tz is not None:
        raise ValueError(f"{ticker}: tz-aware index; the store holds naive New York dates")
    out.index = index.normalize()
    out.index.name = "Date"
    data = out.to_csv(lineterminator="\n", date_format="%Y-%m-%d").encode("utf-8")
    path = _daily_dir(store) / f"{safe_symbol(ticker)}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _manifest_path(store: Path) -> Path:
    return _daily_dir(store) / history_store.MANIFEST_NAME


def _read_manifest(store: Path, kind: str, start: dt.date, end: dt.date) -> dict:
    path = _manifest_path(store)
    window = (start.isoformat(), end.isoformat())
    if not path.is_file():
        return {"kind": kind, "start": window[0], "end": window[1], "tickers": {}}
    found = json.loads(path.read_text(encoding="utf-8"))
    if (found.get("start"), found.get("end")) != window:
        raise ValueError(f"{path} holds bars for {found.get('start')}..{found.get('end')}, "
                         f"not {window[0]}..{window[1]}; use a new --bars-root")
    return found


def _write_manifest(store: Path, manifest: dict) -> None:
    path = _manifest_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _fetch_one(provider, ticker: str, start, end, kind: str, store: Path) -> dict:
    got = provider.daily_bars_between([ticker], start, end,
                                      adjustment=ADJUSTMENTS[kind]).get(ticker)
    if got is None or got.empty:
        return {"status": EMPTY}
    return {"status": OK, "sha256": write_frame(store, ticker, got), "rows": int(len(got)),
            "first": got.index.min().date().isoformat(),
            "last": got.index.max().date().isoformat()}


def fetch_bars(tickers, start: dt.date, end: dt.date, root: Path, *, provider,
               out=print) -> dict:
    """Fetch each ticker's RAW and SPLIT bars once. The manifest is rewritten
    after every ticker, so an interrupted fetch resumes where it stopped."""
    wanted = sorted({t.upper().strip() for t in tickers})
    manifests = {}
    for kind in KINDS:
        store = store_dir(root, kind)
        manifest = _read_manifest(store, kind, start, end)
        todo = [t for t in wanted if t not in manifest["tickers"]]
        for done, ticker in enumerate(todo, 1):
            manifest["tickers"][ticker] = _fetch_one(provider, ticker, start, end, kind, store)
            _write_manifest(store, manifest)
            out(f"{kind} bars: {done}/{len(todo)} ({100 * done // len(todo)}%) {ticker}")
        _write_manifest(store, manifest)
        manifests[kind] = manifest
    return manifests


def load_bars(ticker: str, root: Path, kind: str = "raw") -> pd.DataFrame | None:
    with use_store(store_dir(root, kind)):
        return history_store.load(ticker, "daily")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_alpaca_provider.py`
Expected: all PASS (the existing `test_daily_bars_between_sends_the_range_on_sip_all` still sees `"all"`).
Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_raw_bars.py`
Expected: all PASS.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/marketdata/providers/alpaca_provider.py tests/marketdata/test_alpaca_provider.py scripts/reports/reconcile/__init__.py scripts/reports/reconcile/raw_bars.py tests/scout/test_reconcile_raw_bars.py
git commit -m "feat(v232): raw and split-adjusted daily bar stores for the reconciliation"
```

(If V232-5 already committed `__init__.py`, it is unchanged and `git add` is a no-op for it.)

### Task V232-4b: Raw bars: split and short-bars refusals, the bars manifest

**Model:** sonnet — two small pure functions over two frames and a manifest summary, rules frozen below.

**Files:**
- Modify: `scripts/reports/reconcile/raw_bars.py` (append the refusal section at the end; nothing V232-4 wrote changes)
- Modify: `tests/scout/test_reconcile_raw_bars.py` (append the tests below)

**Interfaces:**
- Consumes (V232-4): `raw_bars.KINDS`, `store_dir`, `_manifest_path`, `OK`, `EMPTY`, `fetch_bars`, and the test file's `_frame`, `_both`, `FakeProvider`, `START`, `END`.
- Produces (ledger contract, consumed by V232-9 `layer1_run` and V232-15 the CLI):
  - `raw_bars.SPLIT_DRIFT = 0.01`; `REFUSALS = ("no_bars", "split_in_window", "bars_end_early")`.
  - `refusal(raw, split, *, start: date, last_exit: date | None) -> str | None` — the first of `REFUSALS` that applies, else None.
  - `bars_manifest(root: Path) -> dict` — `{kind: None | {"sha256", "start", "end", "n_ok", "n_empty"}}`; no ticker names (it goes into the committed JSON, which the leak guard reads).

**Rules this task freezes:** a split inside the window shows as a drift in `split.Close / raw.Close` over the bars dated `>= start` above `SPLIT_DRIFT` (max/min − 1; exactly 1% is usable). A split after the window but before the fetch shifts every bar by the same factor and is usable (Review Focus); a split before `start` is outside the bars compared. Dividends are in neither series. `bars_end_early`: the raw series' last date is before the ticker's last live exit date (`last_exit=None`, a ticker with no closed trade, never refuses on this). `no_bars`: either series missing or empty, or no common bar on or after `start`. Order: `no_bars`, `split_in_window`, `bars_end_early`.

- [ ] **Step 1: Write the failing tests** — append to `tests/scout/test_reconcile_raw_bars.py`:

```python
# --- v232-4b: refusals and the bars manifest --------------------------------------

def test_bars_manifest_hashes_each_manifest_and_names_no_ticker(tmp_path):
    assert raw_bars.bars_manifest(tmp_path) == {"raw": None, "split": None}
    provider = FakeProvider(_both("AAA", [100.0]))
    raw_bars.fetch_bars(["AAA", "ZZZ"], START, END, tmp_path, provider=provider,
                        out=lambda _: None)
    got = raw_bars.bars_manifest(tmp_path)
    path = tmp_path / "raw" / "daily" / "_manifest.json"
    assert got["raw"] == {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "start": "2026-09-01", "end": "2026-09-30", "n_ok": 1, "n_empty": 1}
    assert "AAA" not in repr(got) and "ZZZ" not in repr(got)


def test_the_refusal_vocabulary_is_frozen():
    assert raw_bars.REFUSALS == ("no_bars", "split_in_window", "bars_end_early")
    assert raw_bars.SPLIT_DRIFT == 0.01


CLOSES = [100.0 + i for i in range(10)]          # 2026-09-01 .. 2026-09-14


def test_no_bars_when_either_series_is_missing_or_ends_before_the_window():
    assert raw_bars.refusal(None, _frame(CLOSES), start=START, last_exit=None) == "no_bars"
    assert raw_bars.refusal(_frame(CLOSES), None, start=START, last_exit=None) == "no_bars"
    empty = _frame(CLOSES).iloc[0:0]
    assert raw_bars.refusal(empty, _frame(CLOSES), start=START, last_exit=None) == "no_bars"
    early = _frame(CLOSES, start="2026-08-03")
    assert raw_bars.refusal(early, early, start=START, last_exit=None) == "no_bars"


def test_a_split_after_the_window_is_a_constant_ratio_and_usable():
    raw, split = _frame(CLOSES), _frame([c / 4 for c in CLOSES])
    assert raw_bars.refusal(raw, split, start=START, last_exit=date(2026, 9, 14)) is None


def test_a_split_inside_the_window_is_refused():
    split = _frame([c / 2 if i < 5 else c for i, c in enumerate(CLOSES)])
    assert raw_bars.refusal(_frame(CLOSES), split, start=START,
                            last_exit=None) == "split_in_window"


def test_a_split_before_the_window_start_is_not_in_the_window():
    split = _frame([c / 2 if i < 3 else c for i, c in enumerate(CLOSES)])
    assert raw_bars.refusal(_frame(CLOSES), split, start=date(2026, 9, 4),
                            last_exit=None) is None


def test_drift_at_the_cut_off_is_usable_and_above_it_refused():
    at = _frame([c * (1.01 if i == 9 else 1.0) for i, c in enumerate(CLOSES)])
    above = _frame([c * (1.0101 if i == 9 else 1.0) for i, c in enumerate(CLOSES)])
    raw = _frame(CLOSES)
    assert raw_bars.refusal(raw, at, start=START, last_exit=None) is None
    assert raw_bars.refusal(raw, above, start=START, last_exit=None) == "split_in_window"


def test_a_split_wins_over_short_bars():
    split = _frame([c / 2 if i < 5 else c for i, c in enumerate(CLOSES)])
    assert raw_bars.refusal(_frame(CLOSES), split, start=START,
                            last_exit=date(2026, 12, 1)) == "split_in_window"


def test_bars_that_end_before_the_last_live_exit_are_refused():
    raw = _frame(CLOSES)
    assert raw_bars.refusal(raw, raw, start=START,
                            last_exit=date(2026, 9, 15)) == "bars_end_early"
    assert raw_bars.refusal(raw, raw, start=START, last_exit=date(2026, 9, 14)) is None
    assert raw_bars.refusal(raw, raw, start=START, last_exit=None) is None
```

`test_drift_at_the_cut_off_is_usable_and_above_it_refused` pins "exactly 1% is usable": `1.01 * c / c - 1` lands a few ULPs either side of 0.01 in floating point, which is why `refusal` compares against `SPLIT_DRIFT + 1e-12`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_raw_bars.py`
Expected: the new tests FAIL with `AttributeError: module 'reconcile.raw_bars' has no attribute 'bars_manifest'` / `'refusal'` / `'REFUSALS'`; V232-4's tests still PASS.

- [ ] **Step 3: Implement** — append to the end of `scripts/reports/reconcile/raw_bars.py`:

```python
# --- refusals and the bars manifest (V232-4b) -------------------------------------

SPLIT_DRIFT = 0.01
REFUSALS = ("no_bars", "split_in_window", "bars_end_early")


def _missing(frame) -> bool:
    return frame is None or frame.empty


def _window_ratio(raw: pd.DataFrame, split: pd.DataFrame, start: dt.date) -> pd.Series:
    """split.Close / raw.Close on the bars both series hold dated on or after start."""
    both = pd.concat([raw["Close"], split["Close"]], axis=1, keys=["raw", "split"],
                     join="inner")
    both = both[both.index >= pd.Timestamp(start)]
    ratio = both["split"] / both["raw"]
    return ratio[ratio.notna() & (ratio > 0) & (ratio != float("inf"))]


def refusal(raw, split, *, start: dt.date, last_exit: dt.date | None) -> str | None:
    """Why a ticker's bars cannot score its trades (REFUSALS order), or None."""
    if _missing(raw) or _missing(split):
        return "no_bars"
    ratio = _window_ratio(raw, split, start)
    if ratio.empty:
        return "no_bars"
    if float(ratio.max()) / float(ratio.min()) - 1.0 > SPLIT_DRIFT + 1e-12:
        return "split_in_window"
    if last_exit is not None and raw.index.max().date() < last_exit:
        return "bars_end_early"
    return None


def _summary(path: Path) -> dict:
    data = path.read_bytes()
    manifest = json.loads(data)
    statuses = [e.get("status") for e in manifest.get("tickers", {}).values()]
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "start": manifest.get("start"), "end": manifest.get("end"),
            "n_ok": statuses.count(OK), "n_empty": statuses.count(EMPTY)}


def bars_manifest(root: Path) -> dict:
    """Per kind: the manifest's SHA-256, window and counts -- no ticker names."""
    out = {}
    for kind in KINDS:
        path = _manifest_path(store_dir(root, kind))
        out[kind] = _summary(path) if path.is_file() else None
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scout/test_reconcile_raw_bars.py`
Expected: all PASS.
Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/reconcile/raw_bars.py tests/scout/test_reconcile_raw_bars.py
git commit -m "feat(v232): split-in-window and short-bars refusals, bars manifest summary"
```
