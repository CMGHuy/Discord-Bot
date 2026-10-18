# v161 Trade scout, part 1: VM export and autopsy core (TS1–TS3; TS4 is in `2026-10-15-v161-trade-scout_1b-categorical-cuts.md`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task TS3" -A 400 docs/superpowers/plans/implemented/2026-10-15-v161-trade-scout_1-export-autopsy-core.md`.

**Spec:** [`docs/superpowers/specs/implemented/2026-10-15-v161-trade-scout-design.md`](../../specs/implemented/2026-10-15-v161-trade-scout-design.md)
**Index:** [`2026-10-15-v161-trade-scout_0-index.md`](2026-10-15-v161-trade-scout_0-index.md) — Global Constraints, Parallelisation, Shared contracts and the Task ledger live there and bind every task below.
**Bump:** none
**Edge:** none (integrity)

Paths: `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-15-v161-trade-scout` (the branch). Never `cd`; use absolute paths and `git -C $WT`.

**Import convention for the autopsy package (all tasks):** `scripts/reports/autopsy/` is imported as the top-level package `autopsy` with `scripts/reports` on `sys.path` (the TS7 CLI inserts it; tests insert it at module top). Modules inside the package use relative imports (`from .rows import BookRow`). `swingbot` is importable because pytest's rootdir is the repo root.

**`BookRow` construction (TS2, used by every test from TS3 on):** every field has a default (`None`, `close_reason` `""`, `bars` an empty dict), so tests build rows by keyword, e.g. `BookRow(row_kind="trade", ticker="AAA", entry_date="2026-03-02", gross_r=1.0, net_r=0.98)`.

# Phase A: VM export, test directory and suite

### Task TS1: Read-only VM export script, `tests/scout/`, suite `scout`

**Model:** sonnet — a bash/SQL script with a text-pinning test and a manifest edit; the column mapping needs care but no statistics.

**Files:**
- Create: `scripts/ops/export_book_rows.sh`
- Create: `tests/scout/__init__.py`
- Create: `tests/scout/test_export_script.py`
- Modify: `tests/suites.toml` (append a `[suites.scout]` table)

**Interfaces:**
- Consumes: nothing from earlier tasks. Schema facts (verified at HEAD 35a36cdb): `journal_entries` promotes `trade_id, strategy, outcome, closed_at, created_at` plus `doc` (`swingbot/core/db/schema.py:130`); `trades` promotes `trade_id, ticker, strategy, horizon, direction, status, opened_at, closed_at, entry, stop_loss` plus `doc` (`schema.py:70-90`); `plans` promotes `plan_id, ticker, strategy, horizon_key, status, created_at, valid_session` plus `doc` (`schema.py:93-111`). Plan doc keys `direction, entry_type, trigger_price, expiry_bars, status_history[{status, reason, at}]` (`swingbot/core/planning/plan_types.py:22-50`; `at` is `datetime.now(timezone.utc).isoformat()`, `plan_manager.py:390`). Trade doc keys `plan_id, take_profit, target2, exit_price, close_reason, legs[{reason, ...}]`. Journal doc keys `r_realized, mfe_r, mae_r, exit_efficiency, holding_days, risk_features{stop_width_atr, atr_pct, regime2_state, session_bucket, days_to_earnings, rs_percentile}`.
- Produces: the VM commands (run only in TS13, after the partner's go)
  `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" < scripts/ops/export_book_rows.sh > $SCRATCH/rows.csv` and
  `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rejections" < scripts/ops/export_book_rows.sh > $SCRATCH/rejections.csv`.
  `rows` CSV header = the index's **Export columns**, this exact order (36 columns). `rejections` CSV header `date,reason,count`. Test seams: env `SWING_BOT_DIR` (default `/opt/swing-bot`) and `BOOK_LOGS_DIR` (default `/opt/swing-bot/logs`). Suite `[suites.scout] paths = ["tests/scout/"]`. The test module's `EXPECTED_COLUMNS` tuple and `select_aliases(source) -> tuple[list[str], list[str]]` helper are what TS2's test cross-checks against.

**Why `COPY ... TO STDOUT` and not `\copy`:** psql's `\copy` meta-command must fit on one line, and the column list does not. `COPY (SELECT ...) TO STDOUT` sent from psql is the same client-side stream `\copy ... TO STDOUT` produces, and a `COPY ... TO` is a read, permitted inside a `READ ONLY` transaction (a `COPY ... FROM` would be refused). The spec's guarantee (one READ ONLY session, one SELECT, nothing written on the VM) is unchanged.

- [ ] **Step 0: Create the worktree (once, for the whole plan)**

Load the `worktree-lifecycle` skill and follow it. The commands it ends with for this plan:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch origin
git -C E:/Documents/Private/Projects/Discord-Bot worktree add E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout -b 2026-10-15-v161-trade-scout main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout log --oneline -1
```

Expected: the last command prints the `main` HEAD that carries this plan. Every later path in this plan is under `$WT`.

- [ ] **Step 1: Create the test directory and register its suite**

Create `$WT/tests/scout/__init__.py` as an empty file.

Append to `$WT/tests/suites.toml` (after the `[suites.config]` table, one blank line before it):

```toml

[suites.scout]
description = "v161 trade scout: book export, autopsy, merge, generator roles"
paths = ["tests/scout/"]
```

`tooling` already counts about 1 139 test functions against `max_tests = 1200`; the scout tests (~90) get their own suite instead of pushing it over (`docs/claude/testing-cost.md` § Test suites). CI picks the new suite up from the manifest with no workflow edit.

- [ ] **Step 2: Write the failing test**

Create `$WT/tests/scout/test_export_script.py`:

```python
"""scripts/ops/export_book_rows.sh runs only on the VM, piped through
ssh-hetzner.sh, so CI cannot run its psql half. What is pinned is what a broken
edit would remove: the READ ONLY session, the absence of every write keyword,
the fixed column list, the host log path, and the rejections reducer (run
locally against fake logs through the SWING_BOT_DIR / BOOK_LOGS_DIR seams)."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "export_book_rows.sh"

EXPECTED_COLUMNS = (
    "row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction",
    "plan_created_at", "plan_first_status_at", "plan_status", "plan_status_reason",
    "entry_type", "expiry_bars", "valid_session", "planned_entry", "opened_at", "entry",
    "stop_loss", "take_profit", "target2", "closed_at", "exit_price", "close_reason",
    "last_leg_reason", "outcome", "r_realized", "mfe_r", "mae_r", "exit_efficiency",
    "holding_days", "stop_width_atr", "atr_pct", "regime2_state", "session_bucket",
    "days_to_earnings", "rs_percentile",
)

# Word-bounded and case-sensitive: `updated_at` / `created_at` must not trip it,
# a real SQL write keyword (even in a comment) must.
WRITE_KEYWORDS = re.compile(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP|CREATE)\b")
ALIAS = re.compile(r"\bAS ([a-z][a-z0-9_]*)\b")


@pytest.fixture(scope="module")
def source() -> str:
    assert SCRIPT.exists(), "scripts/ops/export_book_rows.sh is missing"
    return SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")


def select_aliases(source: str) -> tuple[list[str], list[str]]:
    """The output aliases of the trade SELECT and of the plan SELECT, in order."""
    body = source[source.index("COPY ("):source.index(") TO STDOUT")]
    trade_part, plan_part = body.split("UNION ALL")
    return ALIAS.findall(trade_part), ALIAS.findall(plan_part)


def test_it_fails_fast(source):
    assert re.search(r"^set -euo pipefail$", source, re.M)


def test_the_session_is_read_only_before_the_query(source):
    guard = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;"
    assert guard in source
    assert source.index(guard) < source.index("COPY (")


def test_no_write_keyword_appears_anywhere(source):
    assert WRITE_KEYWORDS.findall(source) == []


def test_the_keyword_guard_itself_catches_a_write():
    assert WRITE_KEYWORDS.findall("x; DELETE FROM plans; updated_at created_at") == ["DELETE"]


def test_the_export_is_one_copy_to_stdout_with_a_header(source):
    assert source.count("COPY (") == 1
    assert ") TO STDOUT WITH (FORMAT csv, HEADER true);" in source
    assert source.count("UNION ALL") == 1


def test_both_selects_list_the_export_columns_in_order(source):
    trade_aliases, plan_aliases = select_aliases(source)
    assert trade_aliases == list(EXPECTED_COLUMNS)
    assert plan_aliases == list(EXPECTED_COLUMNS)


def test_psql_runs_in_the_db_container_quietly(source):
    assert "docker compose exec -T db psql -U swingbot -d swingbot" in source
    assert " -q " in source          # no "SET" / "COPY n" tags in the CSV
    assert "ON_ERROR_STOP=1" in source


def test_logs_are_read_on_the_host_not_the_container_path(source):
    assert "/opt/swing-bot/logs" in source
    assert "/app/logs" not in source
    assert 'grep -h "plan rejected ("' in source
    assert 'echo "date,reason,count"' in source


def test_no_python_runs_on_the_vm(source):
    assert "python" not in source.lower()


def test_the_body_is_parsed_before_it_runs(source):
    """The script arrives on stdin: everything sits in functions, run by the last line."""
    lines = [ln for ln in source.splitlines() if ln.strip()]
    assert lines[-1] == 'main "$@"'


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("no bash on PATH")
    return bash


def test_bash_parses_the_script(source):
    done = subprocess.run([_bash(), "-n"], input=source, text=True,
                          capture_output=True, timeout=30)
    assert done.returncode == 0, done.stderr


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


def _seen_by_bash(env: dict, var: str) -> bool:
    probe = subprocess.run([_bash(), "-c", f'test -d "${var}"'], env=env, timeout=30)
    return probe.returncode == 0


def test_rejections_reduce_to_date_reason_count(source, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    _write_log(logs / "bot.log", [
        "2026-03-05 10:00:00,000 INFO swingbot.scan: NVDA (2w, up): plan rejected "
        "(no_qualifying_target, stop 1.00% from entry) -- not posted",
        "2026-03-05 10:00:01,000 INFO swingbot.scan: scan finished",
    ])
    _write_log(logs / "bot.log.1", [
        "2026-03-04 15:01:02,123 INFO swingbot.scan: AAPL (2w, up): plan rejected "
        "(risk_cap, stop 3.10% from entry) -- not posted",
        "2026-03-04 15:02:02,123 INFO swingbot.scan: MSFT (1m, up): plan rejected "
        "(risk_cap, stop 2.00% from entry) -- not posted",
    ])
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix(), BOOK_LOGS_DIR=logs.as_posix())
    if not _seen_by_bash(env, "BOOK_LOGS_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    done = subprocess.run([_bash(), "-s", "--", "rejections"], input=source, env=env,
                          text=True, capture_output=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "date,reason,count",
        "2026-03-04,risk_cap,2",
        "2026-03-05,no_qualifying_target,1",
    ]
    assert "bot.log.1 starts 2026-03-04 15:01:02" in done.stderr


def test_an_unknown_mode_exits_two(source, tmp_path):
    env = dict(os.environ, SWING_BOT_DIR=tmp_path.as_posix())
    if not _seen_by_bash(env, "SWING_BOT_DIR"):
        pytest.skip("this bash cannot see the Windows temp dir (WSL bash)")
    done = subprocess.run([_bash(), "-s", "--", "nope"], input=source, env=env,
                          text=True, capture_output=True, timeout=30)
    assert done.returncode == 2
    assert "rows|rejections" in done.stderr
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_export_script.py`
Expected: FAIL — `scripts/ops/export_book_rows.sh is missing` (fixture errors); `test_the_keyword_guard_itself_catches_a_write` passes.

- [ ] **Step 4: Write the script**

Create `$WT/scripts/ops/export_book_rows.sh` (LF line endings; it runs on Linux). Keep every SQL write keyword out of it, comments included — the test is case-sensitive and word-bounded.

```bash
#!/usr/bin/env bash
# v161 trade scout: the read-only book export. It runs ON THE VM, piped over
# stdin through ssh-hetzner.sh from the dev machine (Git Bash):
#   bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rows" \
#       < scripts/ops/export_book_rows.sh > "$SCRATCH/rows.csv"
#   bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && bash -s -- rejections" \
#       < scripts/ops/export_book_rows.sh > "$SCRATCH/rejections.csv"
#
# rows:       one psql session, opened READ ONLY, one COPY ... TO STDOUT (CSV
#             with a header): every closed trade (journal x trades, left-joined
#             to its plan), then every plan not represented by those rows.
#             psql's \copy must fit on one line; COPY ... TO STDOUT sent from
#             psql is the same client-side stream, and it is a read.
# rejections: grep of the HOST logs for "plan rejected (", reduced to
#             date,reason,count. Each file's first timestamp goes to stderr so
#             the current-versus-rotated coverage is visible.
#
# Nothing here writes: no interpreter, no repository helper, no file on the VM.
# The output columns are fixed; tests/scout/test_export_script.py pins them.
# Everything sits in functions run by the last line, so bash has parsed the
# whole script before anything runs: this script arrives on stdin, and no
# child process may read the rest of it.
# SWING_BOT_DIR / BOOK_LOGS_DIR are test seams; a real run takes the defaults.
set -euo pipefail

export_rows() {
  docker compose exec -T db psql -U swingbot -d swingbot -X -q -v ON_ERROR_STOP=1 <<'SQL'
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
SET TIME ZONE 'UTC';
COPY (
  SELECT
    'trade'::text AS row_kind,
    j.trade_id AS trade_id,
    t.doc->>'plan_id' AS plan_id,
    t.ticker AS ticker,
    t.strategy AS strategy,
    t.horizon AS horizon,
    t.direction AS direction,
    p.created_at::text AS plan_created_at,
    (p.doc->'status_history'->0)->>'at' AS plan_first_status_at,
    p.status AS plan_status,
    (p.doc->'status_history'->(-1))->>'reason' AS plan_status_reason,
    p.doc->>'entry_type' AS entry_type,
    p.doc->>'expiry_bars' AS expiry_bars,
    p.valid_session AS valid_session,
    p.doc->>'trigger_price' AS planned_entry,
    t.opened_at::text AS opened_at,
    t.entry::text AS entry,
    t.stop_loss::text AS stop_loss,
    t.doc->>'take_profit' AS take_profit,
    t.doc->>'target2' AS target2,
    j.closed_at::text AS closed_at,
    t.doc->>'exit_price' AS exit_price,
    t.doc->>'close_reason' AS close_reason,
    (t.doc->'legs'->(-1))->>'reason' AS last_leg_reason,
    j.outcome AS outcome,
    j.doc->>'r_realized' AS r_realized,
    j.doc->>'mfe_r' AS mfe_r,
    j.doc->>'mae_r' AS mae_r,
    j.doc->>'exit_efficiency' AS exit_efficiency,
    j.doc->>'holding_days' AS holding_days,
    j.doc->'risk_features'->>'stop_width_atr' AS stop_width_atr,
    j.doc->'risk_features'->>'atr_pct' AS atr_pct,
    j.doc->'risk_features'->>'regime2_state' AS regime2_state,
    j.doc->'risk_features'->>'session_bucket' AS session_bucket,
    j.doc->'risk_features'->>'days_to_earnings' AS days_to_earnings,
    j.doc->'risk_features'->>'rs_percentile' AS rs_percentile
  FROM journal_entries j
  JOIN trades t ON t.trade_id = j.trade_id
  LEFT JOIN plans p ON p.plan_id = t.doc->>'plan_id'
  WHERE j.closed_at IS NOT NULL
  UNION ALL
  SELECT
    'plan'::text AS row_kind,
    NULL::text AS trade_id,
    p.plan_id AS plan_id,
    p.ticker AS ticker,
    p.strategy AS strategy,
    p.horizon_key AS horizon,
    p.doc->>'direction' AS direction,
    p.created_at::text AS plan_created_at,
    (p.doc->'status_history'->0)->>'at' AS plan_first_status_at,
    p.status AS plan_status,
    (p.doc->'status_history'->(-1))->>'reason' AS plan_status_reason,
    p.doc->>'entry_type' AS entry_type,
    p.doc->>'expiry_bars' AS expiry_bars,
    p.valid_session AS valid_session,
    p.doc->>'trigger_price' AS planned_entry,
    NULL::text AS opened_at,
    NULL::text AS entry,
    NULL::text AS stop_loss,
    NULL::text AS take_profit,
    NULL::text AS target2,
    NULL::text AS closed_at,
    NULL::text AS exit_price,
    NULL::text AS close_reason,
    NULL::text AS last_leg_reason,
    NULL::text AS outcome,
    NULL::text AS r_realized,
    NULL::text AS mfe_r,
    NULL::text AS mae_r,
    NULL::text AS exit_efficiency,
    NULL::text AS holding_days,
    NULL::text AS stop_width_atr,
    NULL::text AS atr_pct,
    NULL::text AS regime2_state,
    NULL::text AS session_bucket,
    NULL::text AS days_to_earnings,
    NULL::text AS rs_percentile
  FROM plans p
  WHERE NOT EXISTS (
    SELECT 1
    FROM trades t2
    JOIN journal_entries j2 ON j2.trade_id = t2.trade_id
    WHERE t2.doc->>'plan_id' = p.plan_id
      AND j2.closed_at IS NOT NULL
  )
  ORDER BY 1 DESC, 21, 8, 2, 3
) TO STDOUT WITH (FORMAT csv, HEADER true);
SQL
}

export_rejections() {
  local logs="${BOOK_LOGS_DIR:-/opt/swing-bot/logs}"
  local f
  for f in "$logs"/*.log*; do
    [ -f "$f" ] || continue
    echo "export_book_rows: $f starts $(head -c 19 "$f")" >&2
  done
  echo "date,reason,count"
  { grep -h "plan rejected (" "$logs"/*.log* || true; } \
    | sed -n 's/^\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\) .*plan rejected (\([^,)]*\).*/\1,\2/p' \
    | LC_ALL=C sort | uniq -c \
    | awk '{ n = $1; sub(/^ *[0-9]+ /, ""); print $0 "," n }'
}

main() {
  cd "${SWING_BOT_DIR:-/opt/swing-bot}"
  case "${1:-}" in
    rows) export_rows ;;
    rejections) export_rejections ;;
    *) echo "usage: bash -s -- rows|rejections" >&2; exit 2 ;;
  esac
}

main "$@"
```

`ORDER BY 1 DESC, 21, 8, 2, 3` sorts trades before plans (`'trade' > 'plan'`), then by `closed_at`, `plan_created_at`, `trade_id`, `plan_id`, so two exports of the same book are byte-identical. The header comment says "no interpreter" rather than naming one: `test_no_python_runs_on_the_vm` rejects the word anywhere in the file.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_export_script.py`
Expected: PASS, `0 failed` (the two subprocess tests report `skipped` only where `bash` is WSL's; under Git Bash and on CI they run).

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/dev/test_suites.py`
Expected: PASS — `tests/scout/` belongs to exactly one suite and the matrix lists `scout`.

- [ ] **Step 6: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout add scripts/ops/export_book_rows.sh tests/scout/__init__.py tests/scout/test_export_script.py tests/suites.toml
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout commit -m "feat(v161): read-only book export script and the scout test suite

TS1. One READ ONLY psql session with one COPY ... TO STDOUT, plus a host log
grep reduced to date,reason,count. tests/scout/ joins the new suite scout.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged by this task.

# Phase B: Autopsy core — rows and cell statistics (categorical cuts continue in part 1b)

### Task TS2: Rows loader and modelled net R

**Model:** sonnet — a typed CSV loader and one friction formula inside one new module, behaviour fixed by the ledger and the spec's Data availability block.

**Files:**
- Create: `scripts/reports/autopsy/__init__.py`
- Create: `scripts/reports/autopsy/rows.py`
- Create: `tests/scout/test_autopsy_rows.py`

**Interfaces:**
- Consumes: TS1's `tests/scout/test_export_script.py` names `EXPECTED_COLUMNS` and `select_aliases(source)`; `scripts/ops/export_book_rows.sh`. Existing: `swingbot/core/edge/frictions.py:15 apply_frictions(fill_price: float, side: str, slippage_bps: float | None = None) -> float` (buys fill higher, sells lower; default `config.SLIPPAGE_BPS`, 5.0) and `:22 commission_r(risk_dollars=None, commission=None) -> float` (`2 * COMMISSION_PER_TRADE / COMMISSION_RISK_BASIS`, defaults 1.0 / 100.0); `swingbot/core/market/session.py:12 US_MARKET_TZ` (`ZoneInfo("America/New_York")`).
- Produces (ledger, binding for TS3–TS7):
  - `EXPORT_COLUMNS: tuple[str, ...]` — the 36 export columns in order.
  - `@dataclass BookRow` — fields in this order, **every one defaulted** (`None`; `close_reason` `""`; `bars` `field(default_factory=dict)`): `row_kind, trade_id, plan_id, ticker, strategy, horizon, direction, plan_date: str | None, plan_hour: int | None, plan_status, plan_status_reason, entry_type, expiry_bars: int | None, valid_session, planned_entry: float | None, entry_date: str | None, entry: float | None, stop: float | None, take_profit: float | None, target2: float | None, exit_date: str | None, exit_price: float | None, close_reason: str, outcome, gross_r: float | None, net_r: float | None, mfe_r, mae_r, exit_efficiency, holding_days: float | None, stop_width_atr, atr_pct, days_to_earnings, rs_percentile: float | None, regime2_state, session_bucket: str | None, bars: dict`. Dates are ISO `YYYY-MM-DD` in **US/Eastern** (`entry_date` from `opened_at`, `exit_date` from `closed_at`); `plan_date` is `plan_created_at[:10]` (the plan's bar date); `plan_hour` is the Eastern hour of `plan_first_status_at`, falling back to `plan_created_at` only when that carries a time other than 00:00 UTC; `close_reason` is the last leg's reason when present, else `close_reason`, lower-cased, never `None` (same rule as `swingbot/core/analytics/metrics.py:82 close_reason_text`); `atr_pct` is in percent (`risk_features.py:66`).
  - `load_rows(path: Path) -> list[BookRow]` (refuses a header that is not `EXPORT_COLUMNS`; fills `net_r` with `modelled_net_r`).
  - `closed_trades(rows) -> list[BookRow]` (`row_kind == "trade"` and `gross_r is not None`).
  - `plan_rows(rows) -> list[BookRow]` (`row_kind == "plan"`).
  - `modelled_net_r(row: BookRow) -> float | None`.
  - `@dataclass(frozen=True) RejectionCount(date: str, reason: str, count: int)`; `load_rejections(path: Path) -> list[RejectionCount]`.

**Modelled net R (spec, Data availability):** `net_r = gross_r − (slip(entry) + slip(exit)) / |entry − stop| − commission_r()`, where `slip(p) = |apply_frictions(p, side) − p|`, the entry side is `buy` for a long and `sell` for a short (reversed on exit), and the exit price falls back to the entry when the export has none. `None` when `gross_r`, `entry` or `stop` is missing, or when the risk is below `MIN_RISK_FRACTION = 0.001` of the entry (a stop already moved to breakeven would otherwise turn a cent of slippage into whole R). The header flag `net_of_frictions: "modelled"` (TS7) labels it.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/scout/test_autopsy_rows.py`:

```python
"""autopsy.rows: the VM export CSV as typed BookRows, with modelled net R."""
import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))

from autopsy import rows  # noqa: E402
from autopsy.rows import BookRow, RejectionCount  # noqa: E402
from swingbot import config  # noqa: E402
from tests.scout.test_export_script import EXPECTED_COLUMNS, SCRIPT, select_aliases  # noqa: E402


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    """Pin the friction model so the arithmetic below is exact."""
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _write_csv(tmp_path: Path, records: list[dict], columns=EXPECTED_COLUMNS) -> Path:
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for record in records:
            writer.writerow({c: record.get(c, "") for c in columns})
    return path


TRADE = {
    "row_kind": "trade", "trade_id": "T1", "plan_id": "P1", "ticker": "AAA",
    "strategy": "RSI", "horizon": "2w", "direction": "bullish",
    "plan_created_at": "2026-03-02 00:00:00+00",
    "plan_first_status_at": "2026-03-02T14:35:10.123456+00:00",
    "plan_status": "CLOSED", "plan_status_reason": "tp1_runner_tp2",
    "entry_type": "stop_entry", "expiry_bars": "3", "valid_session": "2026-03-03",
    "planned_entry": "99.5", "opened_at": "2026-03-03 15:00:00+00", "entry": "100",
    "stop_loss": "95", "take_profit": "110", "target2": "115",
    "closed_at": "2026-03-10 01:30:00+00", "exit_price": "110",
    "close_reason": "auto (price monitor)", "last_leg_reason": "", "outcome": "win",
    "r_realized": "2.0", "mfe_r": "2.5", "mae_r": "-0.4", "exit_efficiency": "0.8",
    "holding_days": "6", "stop_width_atr": "1.5", "atr_pct": "2.4",
    "regime2_state": "bull_quiet", "session_bucket": "open",
    "days_to_earnings": "12", "rs_percentile": "81",
}

PLAN = {
    "row_kind": "plan", "plan_id": "P2", "ticker": "BBB", "strategy": "RSI",
    "horizon": "1m", "direction": "bullish",
    "plan_created_at": "2026-03-04 00:00:00+00", "plan_status": "CANCELLED",
    "plan_status_reason": "expired", "entry_type": "stop_entry", "expiry_bars": "2",
    "planned_entry": "50.25",
}


def test_export_columns_match_the_script():
    source = SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert rows.EXPORT_COLUMNS == EXPECTED_COLUMNS
    assert tuple(select_aliases(source)[0]) == rows.EXPORT_COLUMNS


def test_every_book_row_field_has_a_default():
    a, b = BookRow(), BookRow()
    assert a.ticker is None and a.gross_r is None and a.close_reason == ""
    assert a.bars == {} and a.bars is not b.bars


def test_a_closed_trade_row_parses_into_eastern_dates(tmp_path):
    [row] = rows.load_rows(_write_csv(tmp_path, [TRADE]))
    assert (row.row_kind, row.trade_id, row.plan_id, row.ticker) == ("trade", "T1", "P1", "AAA")
    assert (row.strategy, row.horizon, row.direction) == ("RSI", "2w", "bullish")
    assert row.plan_date == "2026-03-02"
    assert row.plan_hour == 9                    # 14:35 UTC = 09:35 EST
    assert row.entry_date == "2026-03-03"
    assert row.exit_date == "2026-03-09"         # 01:30 UTC on the 10th = 21:30 EDT on the 9th
    assert row.expiry_bars == 3 and row.planned_entry == 99.5
    assert (row.entry, row.stop, row.take_profit, row.target2) == (100.0, 95.0, 110.0, 115.0)
    assert row.exit_price == 110.0 and row.gross_r == 2.0
    assert (row.mfe_r, row.mae_r, row.exit_efficiency) == (2.5, -0.4, 0.8)
    assert (row.holding_days, row.stop_width_atr, row.atr_pct) == (6.0, 1.5, 2.4)
    assert (row.days_to_earnings, row.rs_percentile) == (12.0, 81.0)
    assert (row.regime2_state, row.session_bucket) == ("bull_quiet", "open")
    assert row.close_reason == "auto (price monitor)" and row.outcome == "win"
    assert row.bars == {}


def test_the_last_leg_reason_wins_and_is_lower_cased(tmp_path):
    record = dict(TRADE, close_reason="closed", last_leg_reason="TP1_runner_TP2")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.close_reason == "tp1_runner_tp2"


def test_a_missing_close_reason_is_an_empty_string(tmp_path):
    record = dict(TRADE, close_reason="", last_leg_reason="")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.close_reason == ""


def test_a_date_only_created_at_gives_no_alert_hour(tmp_path):
    record = dict(TRADE, plan_first_status_at="")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.plan_hour is None


def test_postgres_and_date_only_timestamps_parse():
    assert rows._eastern_date("2026-03-10 01:30:00+00") == "2026-03-09"
    assert rows._eastern_date("2026-03-02") == "2026-03-01"   # naive = UTC midnight
    assert rows._eastern_date("") is None


def test_a_timed_created_at_is_the_alert_hour_fallback(tmp_path):
    record = dict(TRADE, plan_first_status_at="", plan_created_at="2026-03-02 15:10:00+00")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.plan_hour == 10


def test_modelled_net_r_subtracts_slippage_and_commission():
    row = BookRow(direction="bullish", entry=100.0, stop=95.0, exit_price=110.0, gross_r=2.0)
    # slippage 0.05 + 0.055 = 0.105 over risk 5 = 0.021 R; commission 2 x 1 / 100 = 0.02 R
    assert rows.modelled_net_r(row) == pytest.approx(2.0 - 0.021 - 0.02)


def test_modelled_net_r_of_a_short():
    row = BookRow(direction="bearish", entry=50.0, stop=52.0, exit_price=46.0, gross_r=2.0)
    # slippage 0.025 + 0.023 = 0.048 over risk 2 = 0.024 R
    assert rows.modelled_net_r(row) == pytest.approx(2.0 - 0.024 - 0.02)


def test_modelled_net_r_without_an_exit_price_charges_the_entry_twice():
    row = BookRow(direction="bullish", entry=100.0, stop=95.0, gross_r=-1.0)
    assert rows.modelled_net_r(row) == pytest.approx(-1.0 - 0.1 / 5.0 - 0.02)


@pytest.mark.parametrize("kwargs", [
    {"entry": 100.0, "stop": None, "gross_r": 1.0},
    {"entry": None, "stop": 95.0, "gross_r": 1.0},
    {"entry": 100.0, "stop": 95.0, "gross_r": None},
    {"entry": 100.0, "stop": 100.0, "gross_r": 1.0},
    {"entry": 100.0, "stop": 99.95, "gross_r": 1.0},   # risk below 0.1% of entry
])
def test_modelled_net_r_is_none_without_a_usable_risk(kwargs):
    assert rows.modelled_net_r(BookRow(direction="bullish", **kwargs)) is None


def test_load_rows_fills_net_r_and_splits_the_kinds(tmp_path):
    loaded = rows.load_rows(_write_csv(tmp_path, [TRADE, PLAN]))
    [trade] = rows.closed_trades(loaded)
    [plan] = rows.plan_rows(loaded)
    assert trade.net_r == pytest.approx(2.0 - 0.021 - 0.02)
    assert plan.plan_id == "P2" and plan.plan_status_reason == "expired"
    assert plan.gross_r is None and plan.net_r is None and plan.entry_date is None
    assert plan.plan_date == "2026-03-04" and plan.expiry_bars == 2


def test_a_trade_without_realised_r_is_not_a_closed_trade(tmp_path):
    loaded = rows.load_rows(_write_csv(tmp_path, [dict(TRADE, r_realized="")]))
    assert rows.closed_trades(loaded) == []


def test_a_wrong_header_is_refused_naming_the_gap(tmp_path):
    path = _write_csv(tmp_path, [TRADE], columns=EXPECTED_COLUMNS[:-1])
    with pytest.raises(ValueError, match="rs_percentile"):
        rows.load_rows(path)


def test_rejections_load_as_counts(tmp_path):
    path = tmp_path / "rejections.csv"
    path.write_bytes(b"date,reason,count\n2026-03-04,risk_cap,2\n2026-03-05,no_qualifying_target,1\n")
    assert rows.load_rejections(path) == [
        RejectionCount("2026-03-04", "risk_cap", 2),
        RejectionCount("2026-03-05", "no_qualifying_target", 1),
    ]


def test_a_wrong_rejections_header_is_refused(tmp_path):
    path = tmp_path / "rejections.csv"
    path.write_bytes(b"day,reason,n\n2026-03-04,risk_cap,2\n")
    with pytest.raises(ValueError, match="date,reason,count"):
        rows.load_rejections(path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'autopsy'`.

- [ ] **Step 3: Write the package and the loader**

Create `$WT/scripts/reports/autopsy/__init__.py`:

```python
"""v161 book autopsy: rows -> cells -> cuts -> report.

Imported as the top-level package ``autopsy`` with ``scripts/reports`` on
``sys.path`` (``scripts/reports/book_autopsy.py`` puts it there). Local,
deterministic, no network: bars come only from a directory the caller names.
"""
```

Create `$WT/scripts/reports/autopsy/rows.py`:

```python
"""Book rows: the VM export CSV (scripts/ops/export_book_rows.sh) as typed rows.

A ``trade`` row is one closed trade (journal x trades, left-joined to its
plan); a ``plan`` row is a plan not represented by a closed trade, its trade columns
empty. Dates are US/Eastern ISO dates. Net R is MODELLED here with the backtest
friction model: no live store holds a net figure (spec, Data availability).
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from swingbot.core.edge.frictions import apply_frictions, commission_r
from swingbot.core.market.session import US_MARKET_TZ

EXPORT_COLUMNS = (
    "row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction",
    "plan_created_at", "plan_first_status_at", "plan_status", "plan_status_reason",
    "entry_type", "expiry_bars", "valid_session", "planned_entry", "opened_at", "entry",
    "stop_loss", "take_profit", "target2", "closed_at", "exit_price", "close_reason",
    "last_leg_reason", "outcome", "r_realized", "mfe_r", "mae_r", "exit_efficiency",
    "holding_days", "stop_width_atr", "atr_pct", "regime2_state", "session_bucket",
    "days_to_earnings", "rs_percentile",
)
REJECTION_COLUMNS = ("date", "reason", "count")

#: Below this fraction of the entry the stop is no longer the planned risk
#: (moved to breakeven): modelled slippage over it would be whole R of noise.
MIN_RISK_FRACTION = 0.001

_NULLS = {"", "nan", "none", "null"}
_SHORT = {"bearish", "short"}
# "...14:31:00+00" (Postgres text) -> "+00:00"; a date-only "2026-03-02" never matches.
_BARE_HOUR_OFFSET = re.compile(r"(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)([+-]\d{2})$")


@dataclass
class BookRow:
    row_kind: str | None = None
    trade_id: str | None = None
    plan_id: str | None = None
    ticker: str | None = None
    strategy: str | None = None
    horizon: str | None = None
    direction: str | None = None
    plan_date: str | None = None
    plan_hour: int | None = None
    plan_status: str | None = None
    plan_status_reason: str | None = None
    entry_type: str | None = None
    expiry_bars: int | None = None
    valid_session: str | None = None
    planned_entry: float | None = None
    entry_date: str | None = None
    entry: float | None = None
    stop: float | None = None
    take_profit: float | None = None
    target2: float | None = None
    exit_date: str | None = None
    exit_price: float | None = None
    close_reason: str = ""
    outcome: str | None = None
    gross_r: float | None = None
    net_r: float | None = None
    mfe_r: float | None = None
    mae_r: float | None = None
    exit_efficiency: float | None = None
    holding_days: float | None = None
    stop_width_atr: float | None = None
    atr_pct: float | None = None
    days_to_earnings: float | None = None
    rs_percentile: float | None = None
    regime2_state: str | None = None
    session_bucket: str | None = None
    bars: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RejectionCount:
    date: str
    reason: str
    count: int


def _text(raw: str | None) -> str | None:
    value = (raw or "").strip()
    return value or None


def _float(raw: str | None) -> float | None:
    value = (raw or "").strip()
    if value.lower() in _NULLS:
        return None
    number = float(value)
    return None if math.isnan(number) else number


def _int(raw: str | None) -> int | None:
    number = _float(raw)
    return None if number is None else int(number)


def _timestamp(raw: str | None) -> dt.datetime | None:
    """A Postgres or ISO timestamp as an aware datetime; naive text is UTC."""
    value = _text(raw)
    if value is None:
        return None
    value = _BARE_HOUR_OFFSET.sub(r"\1\2:00", value.replace("Z", "+00:00"))
    stamp = dt.datetime.fromisoformat(value)
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=dt.timezone.utc)


def _eastern_date(raw: str | None) -> str | None:
    stamp = _timestamp(raw)
    return None if stamp is None else stamp.astimezone(US_MARKET_TZ).date().isoformat()


def _alert_hour(first_status_at: str | None, created_at: str | None) -> int | None:
    """Eastern hour the plan was issued. A created_at at exactly 00:00 UTC is a
    bar date with no time (TradePlanV2.created_at), so it gives no hour."""
    stamp = _timestamp(first_status_at)
    if stamp is None:
        stamp = _timestamp(created_at)
        if stamp is None or stamp.astimezone(dt.timezone.utc).time() == dt.time(0, 0):
            return None
    return stamp.astimezone(US_MARKET_TZ).hour


def _close_reason(close_reason: str | None, last_leg_reason: str | None) -> str:
    """metrics.close_reason_text: the last leg's reason wins, lower-cased."""
    return (_text(last_leg_reason) or _text(close_reason) or "").lower()


def _plan_fields(raw: dict) -> dict:
    created = _text(raw["plan_created_at"])
    return {
        "plan_date": created[:10] if created else None,
        "plan_hour": _alert_hour(raw["plan_first_status_at"], raw["plan_created_at"]),
        "plan_status": _text(raw["plan_status"]),
        "plan_status_reason": _text(raw["plan_status_reason"]),
        "entry_type": _text(raw["entry_type"]),
        "expiry_bars": _int(raw["expiry_bars"]),
        "valid_session": _text(raw["valid_session"]),
        "planned_entry": _float(raw["planned_entry"]),
    }


def _trade_fields(raw: dict) -> dict:
    return {
        "entry_date": _eastern_date(raw["opened_at"]),
        "entry": _float(raw["entry"]),
        "stop": _float(raw["stop_loss"]),
        "take_profit": _float(raw["take_profit"]),
        "target2": _float(raw["target2"]),
        "exit_date": _eastern_date(raw["closed_at"]),
        "exit_price": _float(raw["exit_price"]),
        "close_reason": _close_reason(raw["close_reason"], raw["last_leg_reason"]),
        "outcome": _text(raw["outcome"]),
    }


_JOURNAL_FLOATS = ("mfe_r", "mae_r", "exit_efficiency", "holding_days", "stop_width_atr",
                   "atr_pct", "days_to_earnings", "rs_percentile")


def _journal_fields(raw: dict) -> dict:
    out = {name: _float(raw[name]) for name in _JOURNAL_FLOATS}
    out["gross_r"] = _float(raw["r_realized"])
    out["regime2_state"] = _text(raw["regime2_state"])
    out["session_bucket"] = _text(raw["session_bucket"])
    return out


def _row(raw: dict) -> BookRow:
    ident = {name: _text(raw[name]) for name in
             ("row_kind", "trade_id", "plan_id", "ticker", "strategy", "horizon", "direction")}
    row = BookRow(**ident, **_plan_fields(raw), **_trade_fields(raw), **_journal_fields(raw))
    row.net_r = modelled_net_r(row)
    return row


def _check_header(found, expected: tuple[str, ...], label: str) -> None:
    found = tuple(found or ())
    if found != expected:
        missing = [c for c in expected if c not in found]
        extra = [c for c in found if c not in expected]
        raise ValueError(f"{label}: header is not {','.join(expected)} "
                         f"(missing {missing}, extra {extra})")


def load_rows(path: Path) -> list[BookRow]:
    """Every row of a ``rows`` export, net R modelled. Refuses any other header."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        _check_header(reader.fieldnames, EXPORT_COLUMNS, str(path))
        return [_row(raw) for raw in reader]


def closed_trades(rows) -> list[BookRow]:
    return [r for r in rows if r.row_kind == "trade" and r.gross_r is not None]


def plan_rows(rows) -> list[BookRow]:
    return [r for r in rows if r.row_kind == "plan"]


def _slip(price: float, side: str) -> float:
    return abs(apply_frictions(price, side) - price)


def modelled_net_r(row: BookRow) -> float | None:
    """Gross R less modelled slippage on both fills and the round-trip commission."""
    if row.gross_r is None or row.entry is None or row.stop is None:
        return None
    risk = abs(row.entry - row.stop)
    if risk < MIN_RISK_FRACTION * abs(row.entry) or risk == 0:
        return None
    short = (row.direction or "").lower() in _SHORT
    side_in, side_out = ("sell", "buy") if short else ("buy", "sell")
    exit_price = row.exit_price if row.exit_price is not None else row.entry
    slippage = _slip(row.entry, side_in) + _slip(exit_price, side_out)
    return row.gross_r - slippage / risk - commission_r()


def load_rejections(path: Path) -> list[RejectionCount]:
    """A ``rejections`` export: one count per (date, reason)."""
    with Path(path).open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        _check_header(reader.fieldnames, REJECTION_COLUMNS, str(path))
        return [RejectionCount(r["date"].strip(), r["reason"].strip(), int(r["count"]))
                for r in reader]
```

The `ValueError` message contains `date,reason,count` for a bad rejections header and names `rs_percentile` among the missing columns for the rows test — both tests match on that text.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/reports/autopsy/rows.py`
Expected: no output (every function below complexity 15).

- [ ] **Step 5: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout add scripts/reports/autopsy/__init__.py scripts/reports/autopsy/rows.py tests/scout/test_autopsy_rows.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout commit -m "feat(v161): autopsy rows loader with modelled net R

TS2. The export CSV as typed BookRows (Eastern dates, alert hour, leg-first
close reason); net R modelled with apply_frictions and commission_r.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged by this task.

### Task TS3: Cell statistics: Δ vs complement, week bootstrap, BH

**Model:** opus — statistical code that feeds the slate's ranking (Δ, week-paired bootstrap, BH); the spec asks a quant-engineer review of this path (TS7).

**Files:**
- Create: `scripts/reports/autopsy/cells.py`
- Create: `tests/scout/test_autopsy_cells.py`

**Interfaces:**
- Consumes: TS2 `autopsy.rows.BookRow` (fields `ticker`, `entry_date`, `gross_r`, `net_r`). Existing, verified at HEAD 35a36cdb: `swingbot/core/backtesting/instrument/stats.py:25 iso_week_key(entry_date) -> str` (raises `ValueError` on empty), `:39 group_by_week(trades)` (reads `getattr(trade, "entry_date")`, so items must carry an `.entry_date` attribute), `:57 week_cluster_bootstrap(baseline, component, statistic, *, n_resamples, seed) -> np.ndarray` (`statistic(baseline_draw, component_draw)`, both arms from the same week resample, `None` drops the draw, empty array when no weeks), `:86 bh_qvalues(pvalues) -> list` (`None` passes through, not counted in m); `swingbot/core/analytics/gate_counterfactual_report.py:42 two_sided_bootstrap_p(draws) -> float` (raises on an empty array).
- Produces (ledger, binding for TS4–TS7):
  - `THIN_MIN_N = 30`, `THIN_MIN_WEEKS = 8`, `is_thin(n: int, weeks: int) -> bool` (`n < 30 or weeks < 8`).
  - `@dataclass CellStats(id: str, cut: str, value: str, n: int, weeks: int, win_rate: float, net_expr: float, gross_expr: float, delta: float | None, ci: tuple[float, float] | None, p: float | None, q: float | None, thin: bool, bar_covered_n: int | None = None, extra: dict = field(default_factory=dict))`, `to_json() -> dict` (the index's Autopsy JSON cell, keys in that order, floats rounded to 4 places, `ci` a two-item list or `null`).
  - `@dataclass Tally(id: str, cut: str, value: str, count: int, extra: dict = field(default_factory=dict))`, `to_json() -> dict`.
  - `cell_stats(cut: str, value: str, members: list, complement: list, *, n_resamples: int, seed: int) -> CellStats` — `extra` always carries `tickers: int` and `top_ticker_share: float`; also `net_modelled_missing: int` when a member had no modelled net R (its gross R stands in).
  - `cut_cells(cut: str, trades: list, key: Callable[[BookRow], str | None], *, n_resamples: int, seed: int) -> list[CellStats]` — one cell per distinct non-`None` key, sorted by value, each with `extra["uncovered"]` = trades the key could not place (excluded from both arms); a `;` in a value becomes `,` (cell-id contract).
  - `apply_bh(cells: list[CellStats]) -> int` — sets every cell's `q` with one BH pass over all of them, returns the number tested (cells with a `p`).
  - Also exported for TS5–TS7: `net_value(trade) -> float` (net R, gross when net is missing), `week_sums(trades) -> list[WeekSum]` (`WeekSum = namedtuple("WeekSum", "entry_date total n")`).

**Statistic (Global Constraints, binding):** `Δ = mean net R(cell) − mean net R(complement)`, point estimate on the actual trades; the 95% interval is the 2.5th/97.5th percentile of `week_cluster_bootstrap(week_sums(complement), week_sums(cell), _mean_gap)`, where `_mean_gap(complement_draw, cell_draw)` returns the cell's pooled mean minus the complement's pooled mean for that draw (`None` when either arm drew no trade); `p = two_sided_bootstrap_p(draws)`. `delta`, `ci` and `p` are `None` together when there is no complement or no draw. Week sums, not trades, go into the bootstrap, so each draw touches ~one object per week.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/scout/test_autopsy_cells.py`:

```python
"""autopsy.cells: cell vs complement, week-clustered bootstrap, BH over every cell."""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))

from autopsy import cells  # noqa: E402
from autopsy.cells import CellStats, Tally  # noqa: E402
from autopsy.rows import BookRow  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

FAST = {"n_resamples": 200, "seed": 42}
MONDAYS = [(date(2026, 1, 5) + timedelta(weeks=i)).isoformat() for i in range(12)]


def _trade(day, net, gross=None, ticker="AAA"):
    return BookRow(row_kind="trade", ticker=ticker, entry_date=day, net_r=net,
                   gross_r=net if gross is None else gross)


def test_thin_by_n_or_by_weeks():
    assert cells.is_thin(29, 12)
    assert cells.is_thin(40, 7)
    assert not cells.is_thin(30, 8)


def test_a_cell_reports_its_own_numbers():
    members = [_trade(MONDAYS[0], 0.9, 1.0), _trade(MONDAYS[0], -1.1, -1.0, "BBB"),
               _trade(MONDAYS[1], 1.9, 2.0)]
    complement = [_trade(MONDAYS[0], -0.5), _trade(MONDAYS[1], 0.5)]
    cell = cells.cell_stats("strategy_horizon", "RSI|2w", members, complement, **FAST)
    assert (cell.id, cell.cut, cell.value) == ("strategy_horizon=RSI|2w", "strategy_horizon", "RSI|2w")
    assert (cell.n, cell.weeks) == (3, 2)
    assert cell.win_rate == pytest.approx(2 / 3)
    assert cell.net_expr == pytest.approx(1.7 / 3)
    assert cell.gross_expr == pytest.approx(2 / 3)
    assert cell.delta == pytest.approx(1.7 / 3 - 0.0)
    assert cell.ci is not None and cell.p is not None and cell.q is None
    assert cell.thin is True
    assert cell.extra == {"tickers": 2, "top_ticker_share": pytest.approx(0.6667)}


def test_the_bootstrap_gets_complement_then_cell_as_week_sums(monkeypatch):
    seen = {}

    def fake(baseline, component, statistic, *, n_resamples, seed):
        seen.update(baseline=baseline, component=component, statistic=statistic,
                    n_resamples=n_resamples, seed=seed)
        return np.array([0.1, 0.2, 0.3])

    monkeypatch.setattr(stats, "week_cluster_bootstrap", fake)
    members = [_trade(MONDAYS[0], 1.0), _trade(MONDAYS[0], 2.0), _trade(MONDAYS[1], 3.0)]
    complement = [_trade(MONDAYS[0], -1.0), _trade(MONDAYS[2], 0.0)]
    cell = cells.cell_stats("direction", "bullish", members, complement, **FAST)
    assert [(w.entry_date, w.total, w.n) for w in seen["component"]] == [
        (MONDAYS[0], 3.0, 2), (MONDAYS[1], 3.0, 1)]
    assert [(w.entry_date, w.total, w.n) for w in seen["baseline"]] == [
        (MONDAYS[0], -1.0, 1), (MONDAYS[2], 0.0, 1)]
    assert (seen["n_resamples"], seen["seed"]) == (200, 42)
    # the statistic is cell minus complement, on pooled means of the drawn weeks
    assert seen["statistic"](seen["baseline"], seen["component"]) == pytest.approx(2.0 - (-0.5))
    assert seen["statistic"]([], seen["component"]) is None
    assert cell.ci == pytest.approx((np.percentile([0.1, 0.2, 0.3], 2.5),
                                     np.percentile([0.1, 0.2, 0.3], 97.5)))


def test_a_clearly_better_cell_has_an_interval_above_zero():
    members = [_trade(d, 1.0 + 0.1 * (i % 3)) for d in MONDAYS for i in range(3)]
    complement = [_trade(d, -0.5 + 0.1 * (i % 3), ticker="ZZZ") for d in MONDAYS for i in range(3)]
    cell = cells.cell_stats("regime", "bull_quiet", members, complement, **FAST)
    assert cell.thin is False                      # 36 trades over 12 weeks
    assert cell.ci[0] > 0
    assert cell.p == pytest.approx(2 / 201)        # every draw positive: (0 + 1) x 2 / 201


def test_no_complement_means_no_delta_interval_or_p():
    cell = cells.cell_stats("direction", "bullish", [_trade(MONDAYS[0], 1.0)], [], **FAST)
    assert (cell.delta, cell.ci, cell.p) == (None, None, None)
    assert cell.n == 1 and cell.net_expr == 1.0


def test_the_same_seed_gives_the_same_interval():
    members = [_trade(d, 0.5 * (i - 1)) for i, d in enumerate(MONDAYS)]
    complement = [_trade(d, -0.2 * i) for i, d in enumerate(MONDAYS)]
    a = cells.cell_stats("weekday", "Mon", members, complement, **FAST)
    b = cells.cell_stats("weekday", "Mon", members, complement, **FAST)
    assert a.ci == b.ci and a.p == b.p


def test_a_missing_net_r_falls_back_to_gross_and_is_counted():
    member = BookRow(row_kind="trade", ticker="AAA", entry_date=MONDAYS[0], gross_r=1.0, net_r=None)
    cell = cells.cell_stats("direction", "bullish", [member], [], **FAST)
    assert cell.net_expr == 1.0
    assert cell.extra["net_modelled_missing"] == 1


def test_cut_cells_places_each_trade_once_and_counts_the_uncovered():
    trades = [_trade(MONDAYS[i], 1.0) for i in range(4)]
    trades += [_trade(MONDAYS[i], -1.0) for i in range(4)]
    trades += [_trade(MONDAYS[0], 100.0)]          # the key cannot place this one
    keys = {id(t): ("a" if t.net_r == 1.0 else "b" if t.net_r == -1.0 else None) for t in trades}
    out = cells.cut_cells("c", trades, lambda t: keys[id(t)], **FAST)
    assert [c.id for c in out] == ["c=a", "c=b"]
    assert [c.n for c in out] == [4, 4]
    assert all(c.extra["uncovered"] == 1 for c in out)
    # the unplaced 100 R trade is in neither arm: a's complement is exactly b
    assert out[0].delta == pytest.approx(2.0)
    assert out[1].delta == pytest.approx(-2.0)


def test_a_semicolon_in_a_value_cannot_break_the_cell_id():
    trades = [_trade(MONDAYS[0], 1.0), _trade(MONDAYS[1], -1.0)]
    out = cells.cut_cells("c", trades, lambda t: "x;y" if t.net_r > 0 else "z", **FAST)
    assert [c.id for c in out] == ["c=x,y", "c=z"]


def _bare(cell_id, p):
    cut, value = cell_id.split("=", 1)
    return CellStats(id=cell_id, cut=cut, value=value, n=1, weeks=1, win_rate=1.0,
                     net_expr=1.0, gross_expr=1.0, delta=None, ci=None, p=p, q=None, thin=True)


def test_bh_runs_once_over_every_tested_cell():
    pool = [_bare("a=1", 0.01), _bare("a=2", 0.04), _bare("b=1", 0.03), _bare("b=2", None)]
    tested = cells.apply_bh(pool)
    assert tested == 3
    assert [c.q for c in pool] == stats.bh_qvalues([0.01, 0.04, 0.03, None])
    assert pool[3].q is None


def test_cell_json_has_the_contract_keys_in_order():
    cell = _bare("a=1", 0.012345678)
    cell.ci, cell.delta, cell.bar_covered_n = (-0.123456, 0.654321), 0.3, 7
    out = cell.to_json()
    assert list(out) == ["id", "cut", "value", "n", "weeks", "win_rate", "net_expr",
                         "gross_expr", "delta", "ci", "p", "q", "thin", "bar_covered_n", "extra"]
    assert out["ci"] == [-0.1235, 0.6543] and out["p"] == 0.0123 and out["q"] is None
    assert _bare("a=2", None).to_json()["ci"] is None


def test_tally_json():
    assert Tally("fill_status=filled", "fill_status", "filled", 4).to_json() == {
        "id": "fill_status=filled", "cut": "fill_status", "value": "filled",
        "count": 4, "extra": {}}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_autopsy_cells.py`
Expected: FAIL — `ImportError: cannot import name 'cells' from 'autopsy'`.

- [ ] **Step 3: Write the implementation**

Create `$WT/scripts/reports/autopsy/cells.py`:

```python
"""Cell statistics for the book autopsy (spec section 1, binding).

A cell is the trades of one cut whose key equals one value. It is compared with
its COMPLEMENT -- the same cut's other placed trades -- never with a pool that
contains it: delta = mean net R(cell) - mean net R(complement). The 95% interval
is the percentile interval of week_cluster_bootstrap(complement, cell, ...),
both arms drawn with the same ISO-week resample; p is two-sided; q is
Benjamini-Hochberg over every cell tested in the run. The bootstrap is fed
per-week sums (objects with an ``.entry_date``), not trades, so a 10 000
resample run finishes in minutes. Thin cells are tested and counted, never
ranked as evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict, namedtuple
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from swingbot.core.analytics.gate_counterfactual_report import two_sided_bootstrap_p
from swingbot.core.backtesting.instrument import stats

from .rows import BookRow

THIN_MIN_N = 30
THIN_MIN_WEEKS = 8

WeekSum = namedtuple("WeekSum", "entry_date total n")


def _r4(value):
    return None if value is None else round(float(value), 4)


@dataclass
class CellStats:
    id: str
    cut: str
    value: str
    n: int
    weeks: int
    win_rate: float
    net_expr: float
    gross_expr: float
    delta: float | None
    ci: tuple[float, float] | None
    p: float | None
    q: float | None
    thin: bool
    bar_covered_n: int | None = None
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id, "cut": self.cut, "value": self.value,
            "n": self.n, "weeks": self.weeks, "win_rate": _r4(self.win_rate),
            "net_expr": _r4(self.net_expr), "gross_expr": _r4(self.gross_expr),
            "delta": _r4(self.delta),
            "ci": None if self.ci is None else [_r4(self.ci[0]), _r4(self.ci[1])],
            "p": _r4(self.p), "q": _r4(self.q), "thin": self.thin,
            "bar_covered_n": self.bar_covered_n, "extra": dict(self.extra),
        }


@dataclass
class Tally:
    id: str
    cut: str
    value: str
    count: int
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"id": self.id, "cut": self.cut, "value": self.value,
                "count": self.count, "extra": dict(self.extra)}


def is_thin(n: int, weeks: int) -> bool:
    return n < THIN_MIN_N or weeks < THIN_MIN_WEEKS


def net_value(trade) -> float:
    """Modelled net R; the gross R stands in when the net could not be modelled."""
    return trade.net_r if trade.net_r is not None else trade.gross_r


def week_sums(trades) -> list[WeekSum]:
    """One (entry_date, total net R, n) per ISO week, in week order."""
    by_week = defaultdict(list)
    for trade in trades:
        by_week[stats.iso_week_key(trade.entry_date)].append(trade)
    return [WeekSum(group[0].entry_date, sum(net_value(t) for t in group), len(group))
            for _, group in sorted(by_week.items())]


def _mean_gap(complement_draw, cell_draw) -> float | None:
    """Cell pooled mean minus complement pooled mean for one week draw."""
    complement_n = sum(w.n for w in complement_draw)
    cell_n = sum(w.n for w in cell_draw)
    if not complement_n or not cell_n:
        return None
    return (sum(w.total for w in cell_draw) / cell_n
            - sum(w.total for w in complement_draw) / complement_n)


def _mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _interval(members, complement, n_resamples: int, seed: int):
    """((low, high), p), or (None, None) when there is nothing to compare."""
    if not members or not complement:
        return None, None
    draws = stats.week_cluster_bootstrap(week_sums(complement), week_sums(members), _mean_gap,
                                         n_resamples=n_resamples, seed=seed)
    if draws.size == 0:
        return None, None
    low, high = np.percentile(draws, [2.5, 97.5])
    return (float(low), float(high)), two_sided_bootstrap_p(draws)


def _extra(members) -> dict:
    counts = Counter(t.ticker for t in members)
    out = {"tickers": len(counts),
           "top_ticker_share": round(max(counts.values()) / len(members), 4) if members else 0.0}
    missing = sum(1 for t in members if t.net_r is None)
    if missing:
        out["net_modelled_missing"] = missing
    return out


def cell_stats(cut: str, value: str, members: list, complement: list, *,
               n_resamples: int, seed: int) -> CellStats:
    """One cell against its complement (the same cut's other placed trades)."""
    n = len(members)
    weeks = len({stats.iso_week_key(t.entry_date) for t in members})
    net = [net_value(t) for t in members]
    ci, p = _interval(members, complement, n_resamples, seed)
    delta = None if ci is None else _mean(net) - _mean([net_value(t) for t in complement])
    return CellStats(
        id=f"{cut}={value}", cut=cut, value=value, n=n, weeks=weeks,
        win_rate=sum(1 for t in members if t.gross_r > 0) / n if n else 0.0,
        net_expr=_mean(net), gross_expr=_mean([t.gross_r for t in members]),
        delta=delta, ci=ci, p=p, q=None, thin=is_thin(n, weeks), extra=_extra(members),
    )


def cut_cells(cut: str, trades: list, key: Callable[[BookRow], str | None], *,
              n_resamples: int, seed: int) -> list[CellStats]:
    """One cell per distinct key value; unplaced trades sit in neither arm."""
    keyed = [(key(t), t) for t in trades]
    uncovered = sum(1 for k, _ in keyed if k is None)
    placed = [(str(k).replace(";", ","), t) for k, t in keyed if k is not None]
    out = []
    for value in sorted({k for k, _ in placed}):
        members = [t for k, t in placed if k == value]
        complement = [t for k, t in placed if k != value]
        cell = cell_stats(cut, value, members, complement, n_resamples=n_resamples, seed=seed)
        cell.extra["uncovered"] = uncovered
        out.append(cell)
    return out


def apply_bh(cells: list[CellStats]) -> int:
    """One BH pass over every cell of the run; returns how many were tested."""
    for cell, q in zip(cells, stats.bh_qvalues([c.p for c in cells])):
        cell.q = q
    return sum(1 for c in cells if c.p is not None)
```

`_interval` calls `stats.week_cluster_bootstrap` through the module attribute, which is what lets the test monkeypatch it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_autopsy_cells.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/reports/autopsy/cells.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout add scripts/reports/autopsy/cells.py tests/scout/test_autopsy_cells.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout commit -m "feat(v161): autopsy cell statistics against the complement

TS3. Delta = cell minus complement, 95% interval from the week-clustered
bootstrap over week sums, two-sided p, one BH pass over every cell; thin by
N or by distinct weeks.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged by this task.
