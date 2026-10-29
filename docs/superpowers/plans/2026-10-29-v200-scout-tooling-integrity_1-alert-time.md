# Scout tooling integrity — Part 1: alert time (V200-1 … V200-8)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [Scout tooling integrity](../specs/2026-10-29-v200-scout-tooling-integrity.md) — Part 1 (alert time)
**Index:** [`_0-index.md`](2026-10-29-v200-scout-tooling-integrity_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there; every task below includes the Global Constraints.

`<wt>` is the plan's worktree under `.claude/worktrees/`; `<scratchpad>` is the session scratchpad. Every command uses absolute paths or `git -C <wt>`; stage explicit paths only.

Hour-source vocabulary (index § Cross-task contracts): `"live"`, `"discord"`, `"unknown"`. A plan doc with `issued_at` but no `issued_at_source` counts as `live` (controller decision, 2026-10-29).

# Phase A — Production facts and the source tag

### Task V200-1: Read the `b4ef2e87` deploy time and the stall windows from production

**Model:** sonnet — read-only production queries and one results file, no code.

**Files:**
- Create: `docs/superpowers/results/2026-10-29-v200-prod-reads.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the production facts file (index § Cross-task contracts). Its first fenced `json` block holds exactly
  `{"era_boundary_utc": "YYYY-MM-DDTHH:MM:SSZ", "era_boundary_source": "<one line>", "stall_windows": [{"start": "...Z", "end": "...Z"}, {"start": "...Z", "end": "...Z"}], "pitr_last_drill": "YYYY-MM-DD" | null}`.
  V200-9 copies `stall_windows`, V200-11 copies `era_boundary_*`, V200-8 re-checks `pitr_last_drill`.

Every production command goes through `bash <wt>/scripts/ops/ssh-hetzner.sh` and is read-only. Raw outputs go to `<scratchpad>/`, never into the repo; the results file quotes only the lines each value came from.

- [ ] **Step 1: Read the VM deploy record (git reflog of the deploy checkout)**

`deploy/deploy.sh` runs `git fetch` + `git reset --hard origin/main` on the VM before `docker compose up -d --wait`, so the checkout's reflog is the deploy log with a clock time per deploy.

```bash
bash <wt>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && git reflog show --date=iso-strict --format='%H|%gd|%gs' HEAD | head -n 600" \
  > <scratchpad>/v200_reflog.txt
```

Find the **earliest** reflog entry whose commit contains `b4ef2e87` (the first deploy that ran it). The reflog is newest-first, so walk it in reverse:

```bash
tac <scratchpad>/v200_reflog.txt | while IFS='|' read -r sha sel subject; do
  if git -C <wt> merge-base --is-ancestor b4ef2e87 "$sha" 2>/dev/null; then
    echo "$sha|$sel|$subject"; break
  fi
done
```

Expected: one line such as `<sha>|HEAD@{2026-09-11T10:12:40+00:00}|reset: moving to origin/main`. Convert the selector's time to UTC, to the second (`2026-09-11T10:12:40Z`). That is `era_boundary_utc`; `era_boundary_source` is `"VM /opt/swing-bot git reflog: <sha12> reset at <selector time>"`.

If a reflog sha is unknown locally (`merge-base` fails for every line), run `git -C <wt> fetch origin` once and repeat.

- [ ] **Step 2: Cross-check against the CI deploy run**

```bash
gh run list --workflow deploy.yml --branch main --limit 300 \
  --json databaseId,headSha,createdAt,updatedAt,conclusion > <scratchpad>/v200_deploy_runs.json
```

Take the earliest run with `conclusion == "success"` whose `headSha` contains `b4ef2e87` (`git -C <wt> merge-base --is-ancestor b4ef2e87 <headSha>`), then
`gh run view <databaseId> --json jobs --jq '.jobs[] | select(.name | test("deploy"; "i")) | [.name, .completedAt] | @tsv'`.
Its `deploy` job's `completedAt` should be within ~15 minutes after the Step 1 reflog time. Record both in the results file.

- If Step 1 found no entry (reflog expired) but Step 2 found the run, use the `deploy` job's `completedAt` as `era_boundary_utc`, with `era_boundary_source = "GitHub Actions deploy.yml run <id>, deploy job completedAt"`.
- **If neither gives a clock time, stop: write nothing and return `BLOCKED: no deploy clock time for b4ef2e87 -- reflog and deploy runs both silent; partner to supply the boundary`.** The commit time (`2026-09-11 09:59:35 +0200`) is never the boundary (spec Part 3), and `swingbot/admin/version_history.json` carries dates only.

- [ ] **Step 3: Read the stall closes from the production database**

```bash
bash <wt>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot -At -F '|' -v ON_ERROR_STOP=1" \
  > <scratchpad>/v200_stall.txt <<'SQL'
BEGIN READ ONLY;
SELECT 'w1_last_close_before', to_char(max(closed_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  FROM journal_entries WHERE closed_at < '2026-08-04 18:55:43+00';
SELECT 'w1_batch_first_close', to_char(min(closed_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  FROM journal_entries WHERE closed_at >= '2026-08-04 18:55:00+00';
SELECT 'w2_last_close_before', to_char(max(closed_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  FROM journal_entries WHERE closed_at < '2026-08-05 15:34:08+00';
SELECT 'w2_batch_first_close', to_char(min(closed_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
  FROM journal_entries WHERE closed_at >= '2026-08-05 15:34:00+00';
SELECT 'by_minute', to_char(date_trunc('minute', closed_at) AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI"Z"'), count(*)
  FROM journal_entries
  WHERE closed_at >= '2026-08-03 12:00+00' AND closed_at < '2026-08-05 20:00+00'
  GROUP BY 2 ORDER BY 2;
COMMIT;
SQL
```

Expected:
- `w1_last_close_before` is `2026-08-03T16:18:02.…Z` and `w1_batch_first_close` is `2026-08-04T18:55:43.…Z` (spec, confirmed values). A mismatch is a finding: record it and use the database value.
- `w2_batch_first_close` is `2026-08-05T15:34:08.…Z`; `w2_last_close_before` is window 2's start.
- `by_minute` shows nothing between the window-1 start and the 08-04 batch.

`stall_windows` = `[{"start": <w1_last_close_before>, "end": <w1_batch_first_close>}, {"start": <w2_last_close_before>, "end": <w2_batch_first_close>}]`, each truncated to the second with a `Z` suffix. Quote the microsecond values in the raw lines.

- [ ] **Step 4: Read the last PITR drill date**

```bash
grep -n "^### Drill" <wt>/docs/deploy/DB_RESTORE.md | tail -n 1
bash <wt>/scripts/ops/ssh-hetzner.sh "ls -l --time-style=+%F /opt/swing-bot/logs 2>/dev/null | grep -i -E 'pitr|drill' | tail -n 3"
```

`pitr_last_drill` is the later of the two dates (the `### Drill YYYY-MM-DD` heading or a drill log's date), or `null` if neither exists.

- [ ] **Step 5: Write the results file**

`docs/superpowers/results/2026-10-29-v200-prod-reads.md`:

````markdown
# v200 production reads, 2026-10-29

Read-only reads for plan v200 (V200-1). Consumers: V200-9 (stall windows), V200-11 (era boundary), V200-8 (PITR).

```json
{"era_boundary_utc": "<Step 1/2>", "era_boundary_source": "<Step 1/2>",
 "stall_windows": [{"start": "<w1 start>", "end": "<w1 end>"}, {"start": "<w2 start>", "end": "<w2 end>"}],
 "pitr_last_drill": "<Step 4>"}
```

## Era boundary
<Step 1 command, the matching reflog line; Step 2 run id and deploy-job completedAt; the gap between them>

## Stall windows
<Step 3 SQL and its raw output lines; whether the spec's window-1 values were confirmed>

Rule note for V200-9: under the index rule (`opened_at < end` and `closed_at >= start`) the trade whose close defines a window start is itself inside the window.

## PITR drill
<Step 4 output>
````

Fill every `<…>` with the real values. The json block must parse:
`python -c "import json,re,sys; t=open(sys.argv[1],encoding='utf-8').read(); d=json.loads(re.search(r'```json\n(.*?)\n```', t, re.S).group(1)); assert set(d)=={'era_boundary_utc','era_boundary_source','stall_windows','pitr_last_drill'} and len(d['stall_windows'])==2; print(d)" <wt>/docs/superpowers/results/2026-10-29-v200-prod-reads.md`
Expected: the dict prints, no traceback.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add docs/superpowers/results/2026-10-29-v200-prod-reads.md
git -C <wt> commit -m "docs(v200): production reads -- b4ef2e87 deploy time, August stall windows, PITR drill"
```

### Task V200-2: `TradePlanV2.issued_at_source` and the live stamp

**Model:** opus — a persisted plan-doc field in `swingbot/core` (schema ADD) plus a live-scan stamp; a mistake changes every new plan doc.

**Files:**
- Modify: `swingbot/core/planning/plan_types.py` (comment at the `issued_at` field, ~l.123-129; new field after `risk_notice`, ~l.210; `_OMIT_WHEN_NONE`, ~l.231)
- Modify: `swingbot/core/scanning/analyze.py` (`attach_plan_v2`, the `plan.issued_at = …` line, ~l.543)
- Create: `tests/planning/test_issued_at_source.py`
- Modify: `tests/planning/test_gap_sizing.py` (`test_attach_plan_v2_leaves_a_long_unstamped`, ~l.225-228)
- Modify: `tests/backtesting/test_backtest_scenarios.py` (twin of `test_replayed_plans_carry_no_issued_at`, ~l.99)

**Interfaces:**
- Consumes: nothing.
- Produces: `TradePlanV2.issued_at_source: str | None = None` — `"live"` (set only by `attach_plan_v2` when it stamps the wall clock), `"discord"` (written only by the V200-7 revision), `None` otherwise (replay, records written before v200). Listed in `_OMIT_WHEN_NONE`, so a doc without a source has no key. Read by the export (V200-3) as `plan_issued_at_source`.

This is an **add** (`docs/claude/schema-evolution.md` § The four operations): new docs carry the key when set; old docs load with the dataclass default; no read-time upcasting.

- [ ] **Step 1: Write the failing tests**

`tests/planning/test_issued_at_source.py`:

```python
"""v200: TradePlanV2.issued_at_source -- "live" only where attach_plan_v2 stamps
the wall clock, "discord" only from revision v200_001, None everywhere else."""
import json
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from swingbot.core.scanning import analyze
from tests.planning.test_gap_sizing import PRE_V183_PLAN_KEYS, _attach, _plan, _signed_gaps

ISSUED = "2026-08-04T13:02:11+00:00"


def _attach_issued(monkeypatch, plan, df, issued_at):
    """tests.planning.test_gap_sizing._attach, with an explicit issued_at (the replay path)."""
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(analyze, "_build_quality_inputs", lambda *args, **kwargs: {})
    monkeypatch.setattr(analyze, "build_confluence_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(analyze, "primary_strategy_for", lambda scenario: "MACD")
    monkeypatch.setattr(analyze, "stamp_entry_context", lambda plan, df, asof: None)
    item = SimpleNamespace(rs_combined=None, sector_rs_percentile=None, conf=None, htf_bias=None,
                           target_confluence=None)
    scenario = SimpleNamespace(direction=plan.direction, entry=100.0)
    analyze.attach_plan_v2(item, scenario, df, "ZZZ", "3m", issued_at=issued_at)
    return item.plan_v2


def test_the_field_defaults_to_none_and_leaves_the_doc_unchanged():
    plan = _plan("bullish")
    assert plan.issued_at_source is None
    assert "issued_at_source" not in plan_to_dict(plan)
    assert list(plan_to_dict(plan)) == PRE_V183_PLAN_KEYS


@pytest.mark.parametrize("source", ["live", "discord"])
def test_the_source_round_trips_through_json(source):
    plan = _plan("bullish")
    plan.issued_at, plan.issued_at_source = ISSUED, source
    doc = json.loads(json.dumps(plan_to_dict(plan)))
    assert doc["issued_at_source"] == source
    restored = plan_from_dict(doc)
    assert (restored.issued_at, restored.issued_at_source) == (ISSUED, source)


def test_a_doc_written_before_v200_loads_with_no_source():
    doc = plan_to_dict(_plan("bullish"))
    doc["issued_at"] = ISSUED
    doc.pop("issued_at_source", None)
    restored = plan_from_dict(doc)
    assert restored.issued_at == ISSUED and restored.issued_at_source is None


def test_the_live_wall_clock_stamp_is_tagged_live(monkeypatch):
    plan = _attach(monkeypatch, _plan("bullish"), _signed_gaps())
    assert plan.issued_at is not None
    assert plan.issued_at_source == "live"
    assert list(plan_to_dict(plan)) == PRE_V183_PLAN_KEYS + ["issued_at_source"]


@pytest.mark.parametrize("passed", [ISSUED, "2025-01-10T21:00:00+00:00"])
def test_a_passed_issued_at_is_kept_and_carries_no_source(monkeypatch, passed):
    plan = _attach_issued(monkeypatch, _plan("bullish"), _signed_gaps(), passed)
    assert plan.issued_at == passed
    assert plan.issued_at_source is None
    assert "issued_at_source" not in plan_to_dict(plan)
```

`tests/planning/test_gap_sizing.py` — the live attach now stamps the source, appended at the end of the doc:

```python
def test_attach_plan_v2_leaves_a_long_unstamped(monkeypatch):
    plan = _attach(monkeypatch, _plan("bullish"), _signed_gaps())
    assert plan.gap_sizing is None
    # v200: the live wall-clock stamp adds issued_at_source = "live" (omitted while None).
    assert list(plan_to_dict(plan)) == PRE_V183_PLAN_KEYS + ["issued_at_source"]
```

`tests/backtesting/test_backtest_scenarios.py`, directly below `test_replayed_plans_carry_no_issued_at`:

```python
def test_replayed_plans_carry_no_issued_at_source():
    """v200: only the live wall-clock stamp tags a source; a replayed plan has none."""
    out = bs.replay_scenarios("AAPL", _structured_df(), "4w", gates=GATES)
    assert out, "fixture must produce at least one plan"
    assert all(plan.issued_at_source is None for _, plan in out)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/planning/test_issued_at_source.py`
Expected: FAIL — `AttributeError: 'TradePlanV2' object has no attribute 'issued_at_source'`.

- [ ] **Step 3: Add the field in `swingbot/core/planning/plan_types.py`**

- The field goes **after `risk_notice`** (the last field of `TradePlanV2`), so a set value appends one key at the end of the doc and every unset doc keeps its exact pre-v200 key list:

```python
    # v200: where issued_at came from. "live" = attach_plan_v2 stamped the wall
    # clock; "discord" = a pre-v87 plan whose issue time revision v200_001
    # recovered from its Discord alert message. None = replayed (no issued_at),
    # or written live before v200 -- readers count an issued_at without a
    # source as live. Omitted from plan_to_dict while None (_OMIT_WHEN_NONE).
    issued_at_source: str | None = None
```

- `_OMIT_WHEN_NONE = ("gap_sizing", "risk_notice", "issued_at_source")`.
- Extend the `issued_at` comment (~l.123-128), after "…and for records persisted before v87.": `From v200 a pre-v87 record may carry a Discord-recovered value (revision v200_001); issued_at_source says which.`

- [ ] **Step 4: Stamp the source in `swingbot/core/scanning/analyze.py`**

Replace the single line `plan.issued_at = issued_at or datetime.now(timezone.utc).isoformat()` with:

```python
        if issued_at:
            plan.issued_at = issued_at
        else:
            plan.issued_at = datetime.now(timezone.utc).isoformat()
            plan.issued_at_source = "live"
```

`issued_at` behaves as before (a falsy argument still gets the wall clock, as `or` did). Replay callers (`qualify.py:59,95`, `scan_replay.py:213`) pass `issued_at` and stay untouched.

- [ ] **Step 5: Run the tests and the neighbours that pin the plan doc**

```bash
python <wt>/scripts/dev/testrun.py file tests/planning/test_issued_at_source.py
python <wt>/scripts/dev/testrun.py file tests/planning/test_gap_sizing.py
python <wt>/scripts/dev/testrun.py file tests/planning/test_plan_serialization.py
python <wt>/scripts/dev/testrun.py file tests/scanning/test_risk_notice_snapshot.py
python <wt>/scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py
python <wt>/scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py
```

Expected: each `0 failed`. (`test_risk_notice_snapshot.py` compares three live attaches after popping `issued_at`; all three carry `issued_at_source = "live"`, so they stay equal.) If another test pins the full key list of a *live attach*, add `+ ["issued_at_source"]` there with the same comment and name it in the commit body.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C <wt>/swingbot/core/scanning/analyze.py <wt>/swingbot/core/planning/plan_types.py`
Expected: `attach_plan_v2` at C(13) or lower; nothing at 15 or above. Then `python <wt>/scripts/dev/complexity_gate.py` exits 0.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/core/planning/plan_types.py swingbot/core/scanning/analyze.py \
  tests/planning/test_issued_at_source.py tests/planning/test_gap_sizing.py \
  tests/backtesting/test_backtest_scenarios.py
git -C <wt> commit -m "feat(v200): TradePlanV2.issued_at_source, stamped live only with the wall clock"
```

# Phase B — Export and autopsy hour

### Task V200-3: Export the issue time; hour from `issued_at` only; tolerant header

**Model:** opus — retires two hour sources on a lookahead ground (no-lookahead) and changes the CSV contract every later autopsy task reads.

**Files:**
- Modify: `scripts/ops/export_book_rows.sh` (header comment l.19; trade branch last column ~l.68; plan branch last column ~l.109)
- Modify: `scripts/reports/autopsy/rows.py` (`EXPORT_COLUMNS` l.23-31, `BookRow` l.44-82, `_alert_hour` l.125-133, `_plan_fields` l.141-152, `_trade_fields` l.155-166, `_check_header` l.189-195, `load_rows` l.215-221)
- Modify: `tests/scout/test_export_script.py` (`EXPECTED_COLUMNS` l.18-25; the sqlite query adaptation l.218-221)
- Modify: `tests/scout/test_autopsy_rows.py` (`TRADE` dict; tests at ~l.72-79, ~l.108-125, ~l.169-172)
- Modify: `tests/scout/test_book_autopsy.py` (`_trade`, ~l.38-52)

(`tests/scout/test_autopsy_exits.py` builds `BookRow`s directly and needs no change here; V200-4 edits it.)

**Interfaces:**
- Consumes: V200-2's doc field `issued_at_source` (read by SQL only, no import).
- Produces:
  - export columns `plan_issued_at`, `plan_issued_at_source`, appended at the **end** of both UNION branches (`ORDER BY 1 DESC, 21, 8, 2, 3` is positional and unaffected);
  - `rows.ISSUED_COLUMNS = ("plan_issued_at", "plan_issued_at_source")`; `rows.EXPORT_COLUMNS` (38 names, ending with them); `rows.LEGACY_EXPORT_COLUMNS = EXPORT_COLUMNS[:-2]`;
  - `rows._alert_hour(issued_at: str | None) -> int | None`;
  - `BookRow.hour_source: str = "unknown"` (`"live"` / `"discord"` / `"unknown"`), `BookRow.opened_at_utc: dt.datetime | None = None`, `BookRow.closed_at_utc: dt.datetime | None = None` (tz-aware UTC). V200-4 counts `hour_source`; V200-9 and V200-11 read the two UTC timestamps.

Rule (spec Part 1.3): the hour comes from `plan_issued_at` only. `plan_first_status_at` (a fill or expiry time for non-market plans: lookahead) and `plan_created_at` (a bar date) are never hour sources. Both stay in the export, unread for the hour. `hour_source` is `"unknown"` whenever the hour is `None`; otherwise `"discord"` when the source column says so, else `"live"` (an `issued_at` written before v200 has no source and counts as live).

- [ ] **Step 1: Write the failing tests**

`tests/scout/test_export_script.py`:
- `EXPECTED_COLUMNS` gains `"plan_issued_at", "plan_issued_at_source",` after `"rs_percentile",`.
- Move the sqlite adaptation in `test_rows_include_each_plan_and_preserve_closed_trades` into a helper and reuse it:

```python
def _sqlite_query(source: str) -> str:
    """The rows COPY body, with projection-only PostgreSQL syntax adapted for sqlite."""
    query = source.split("COPY (", 1)[1].split(") TO STDOUT", 1)[0]
    return query.replace("::text", "").replace("->(-1)", "->'$[#-1]'")


def test_the_issued_columns_read_the_plan_doc(source, book_rows_db):
    book_rows_db.execute(
        "UPDATE plans SET doc = ? WHERE plan_id = 'unfilled-plan'",
        ('{"issued_at": "2026-08-04T13:02:11+00:00", "issued_at_source": "discord"}',))
    book_rows_db.execute(
        "UPDATE plans SET doc = ? WHERE plan_id = 'closed-plan'",
        ('{"issued_at": "2026-10-15T14:31:07+00:00"}',))
    cursor = book_rows_db.execute(_sqlite_query(source))
    names = [column[0] for column in cursor.description]
    pid, at, src = (names.index(n) for n in ("plan_id", "plan_issued_at", "plan_issued_at_source"))
    got = {row[pid]: (row[at], row[src]) for row in cursor.fetchall()}
    assert got["unfilled-plan"] == ("2026-08-04T13:02:11+00:00", "discord")   # plan branch
    assert got["closed-plan"] == ("2026-10-15T14:31:07+00:00", None)         # trade branch
    assert got["open-plan"] == (None, None)
```

(The `WRITE_KEYWORDS` check reads the script only; an UPDATE in the in-memory fixture is fine.)

`tests/scout/test_autopsy_rows.py`:
- `TRADE` gains `"plan_issued_at": "2026-03-02T14:35:10.123456+00:00", "plan_issued_at_source": "live"`, and its `"plan_first_status_at"` becomes the fill time `"2026-03-03 15:00:00+00"` (what a non-market plan's first status really is).
- `test_a_closed_trade_row_parses_into_eastern_dates` keeps `assert row.plan_hour == 9  # issued 14:35 UTC = 09:35 EST` and adds `assert row.hour_source == "live"`.
- `test_every_book_row_field_has_a_default` adds `assert a.hour_source == "unknown" and a.opened_at_utc is None and a.closed_at_utc is None`.
- **Delete** `test_a_date_only_created_at_gives_no_alert_hour` and `test_a_timed_created_at_is_the_alert_hour_fallback` (they pin the retired sources) and **replace** `test_a_wrong_header_is_refused_naming_the_gap`. Add:

```python
import datetime as dt

UTC = dt.timezone.utc


def test_export_columns_end_with_the_issued_columns():
    assert len(rows.EXPORT_COLUMNS) == 38
    assert rows.EXPORT_COLUMNS[-2:] == rows.ISSUED_COLUMNS == ("plan_issued_at", "plan_issued_at_source")
    assert rows.LEGACY_EXPORT_COLUMNS == rows.EXPORT_COLUMNS[:-2]


def test_alert_hour_reads_a_real_issue_time_only():
    assert rows._alert_hour("2026-03-02T14:35:10+00:00") == 9         # EST
    assert rows._alert_hour("2026-08-04T23:40:00+00:00") == 19        # EDT
    assert rows._alert_hour("2026-08-04 13:02:11+00") == 9            # Postgres text
    assert rows._alert_hour("2026-03-02") is None                     # a date has no hour
    assert rows._alert_hour("") is None and rows._alert_hour(None) is None


def test_neither_first_status_nor_created_at_is_an_hour_source(tmp_path):
    record = dict(TRADE, plan_issued_at="", plan_issued_at_source="",
                  plan_first_status_at="2026-03-02T14:35:10+00:00",
                  plan_created_at="2026-03-02 15:10:00+00")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert row.plan_hour is None and row.hour_source == "unknown"
    assert row.plan_date == "2026-03-02"                              # the date still comes from created_at


def test_issued_at_without_a_source_counts_as_live(tmp_path):
    [row] = rows.load_rows(_write_csv(tmp_path, [dict(TRADE, plan_issued_at_source="")]))
    assert (row.plan_hour, row.hour_source) == (9, "live")


def test_a_discord_issue_time_is_tagged_discord(tmp_path):
    record = dict(TRADE, plan_issued_at="2026-08-04T23:40:00+00:00", plan_issued_at_source="discord")
    [row] = rows.load_rows(_write_csv(tmp_path, [record]))
    assert (row.plan_hour, row.hour_source) == (19, "discord")


def test_a_date_only_issued_at_is_unknown(tmp_path):
    [row] = rows.load_rows(_write_csv(tmp_path, [dict(TRADE, plan_issued_at="2026-03-02")]))
    assert (row.plan_hour, row.hour_source) == (None, "unknown")


def test_an_old_csv_without_the_issued_columns_loads_with_unknown_hours(tmp_path):
    path = _write_csv(tmp_path, [TRADE, PLAN], columns=EXPECTED_COLUMNS[:-2])
    trade, plan = rows.load_rows(path)
    assert (trade.plan_hour, trade.hour_source) == (None, "unknown")
    assert (plan.plan_hour, plan.hour_source) == (None, "unknown")
    assert trade.gross_r == 2.0 and trade.entry_date == "2026-03-03"


def test_a_wrong_header_is_still_refused_naming_the_gap(tmp_path):
    for columns in ([c for c in EXPECTED_COLUMNS if c != "rs_percentile"],
                    [c for c in EXPECTED_COLUMNS[:-2] if c != "rs_percentile"],
                    list(EXPECTED_COLUMNS[:-1])):
        path = _write_csv(tmp_path, [TRADE], columns=columns)
        with pytest.raises(ValueError, match="missing"):
            rows.load_rows(path)
    path = _write_csv(tmp_path, [TRADE], columns=[c for c in EXPECTED_COLUMNS if c != "rs_percentile"])
    with pytest.raises(ValueError, match="rs_percentile"):
        rows.load_rows(path)


def test_open_and_close_keep_their_utc_timestamps(tmp_path):
    trade, plan = rows.load_rows(_write_csv(tmp_path, [TRADE, PLAN]))
    assert trade.opened_at_utc == dt.datetime(2026, 3, 3, 15, 0, tzinfo=UTC)
    assert trade.closed_at_utc == dt.datetime(2026, 3, 10, 1, 30, tzinfo=UTC)
    assert trade.closed_at_utc.utcoffset() == dt.timedelta(0)
    assert plan.opened_at_utc is None and plan.closed_at_utc is None
```

`tests/scout/test_book_autopsy.py` `_trade`: add `"plan_issued_at": f"{plan_day}T13:00:00+00:00", "plan_issued_at_source": "live",` beside `plan_first_status_at`, so the `alert_hour` cut keeps its 48 placed trades.

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py`
Expected: FAIL — `AttributeError: module 'autopsy.rows' has no attribute 'ISSUED_COLUMNS'`, and header errors naming `plan_issued_at`.

- [ ] **Step 3: Extend the export (`scripts/ops/export_book_rows.sh`)**

Trade branch, last column becomes:

```sql
    j.doc->'risk_features'->>'rs_percentile' AS rs_percentile,
    p.doc->>'issued_at' AS plan_issued_at,
    p.doc->>'issued_at_source' AS plan_issued_at_source
```

Plan branch, last column becomes:

```sql
    NULL::text AS rs_percentile,
    p.doc->>'issued_at' AS plan_issued_at,
    p.doc->>'issued_at_source' AS plan_issued_at_source
```

Header comment l.19 becomes: `# The output columns are fixed (rows: 38, the last two plan_issued_at and plan_issued_at_source, appended by v200); tests/scout/test_export_script.py pins them.` No SQL write keyword anywhere, comments included.

- [ ] **Step 4: Rework `scripts/reports/autopsy/rows.py`**

- `ISSUED_COLUMNS = ("plan_issued_at", "plan_issued_at_source")`; `EXPORT_COLUMNS = (<the 36 names unchanged>, *ISSUED_COLUMNS)`; `LEGACY_EXPORT_COLUMNS = EXPORT_COLUMNS[:-2]` with a comment: `#: Exports written before v200: no issue-time columns; every hour reads as unknown.`
- `BookRow` gains, after `session_bucket`: `hour_source: str = "unknown"`, `opened_at_utc: dt.datetime | None = None`, `closed_at_utc: dt.datetime | None = None`.
- `_alert_hour(issued_at: str | None) -> int | None` — docstring: `Eastern hour of the plan's real issue time (TradePlanV2.issued_at: the live stamp or the v200 Discord backfill). Nothing else is an hour source: status_history[0].at is a fill or expiry time for non-market plans (lookahead) and created_at is a bar date.` Returns `None` for an empty value or a date-only text (`len(text) <= 10`), else `_timestamp(text).astimezone(US_MARKET_TZ).hour`.
- `_hour_source(hour: int | None, source: str | None) -> str` — `"unknown"` when `hour is None`, `"discord"` when `_text(source) == "discord"`, else `"live"`.
- `_plan_fields(raw)`: `hour = _alert_hour(raw.get("plan_issued_at"))`; `"plan_hour": hour`, `"hour_source": _hour_source(hour, raw.get("plan_issued_at_source"))`. `plan_first_status_at` is no longer read.
- `_utc(raw: str | None) -> dt.datetime | None` — `_timestamp(raw)` converted with `.astimezone(dt.timezone.utc)`, `None` passes through. `_trade_fields` adds `"opened_at_utc": _utc(raw["opened_at"])`, `"closed_at_utc": _utc(raw["closed_at"])`.
- `_check_header(found, expected, label, accepted: tuple[tuple[str, ...], ...] = ())` — returns when `found == expected` or `found in accepted`; otherwise raises the existing message (missing/extra computed against `expected`). `load_rows` passes `accepted=(LEGACY_EXPORT_COLUMNS,)`; `load_rejections` is unchanged.

- [ ] **Step 5: Run the tests**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_export_script.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_rows.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py
python <wt>/scripts/dev/testrun.py suite scout
```

Expected: each `0 failed`, `0 xfailed`.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C <wt>/scripts/reports/autopsy/rows.py`
Expected: no output (every function below C).

- [ ] **Step 7: Commit**

```bash
git -C <wt> add scripts/ops/export_book_rows.sh scripts/reports/autopsy/rows.py \
  tests/scout/test_export_script.py tests/scout/test_autopsy_rows.py tests/scout/test_book_autopsy.py
git -C <wt> commit -m "fix(v200): autopsy alert hour from issued_at only; export the issue time and its source"
```

### Task V200-4: Alert-hour coverage by source in the report

**Model:** sonnet — additive counting and rendering on an existing report, contract fixed by the ledger.

**Files:**
- Modify: `scripts/reports/autopsy/exits.py` (constants block ~l.16-27; `alert_supply_tallies` l.151-154)
- Modify: `scripts/reports/autopsy/report.py` (`NOTES` l.20-30; `build_report` l.87-107; `_header_lines` l.119-129; `_tally_lines` l.~200; `render_markdown` l.~218)
- Modify: `tests/scout/test_autopsy_exits.py`
- Modify: `tests/scout/test_book_autopsy.py`

**Interfaces:**
- Consumes: `BookRow.hour_source` (V200-3).
- Produces:
  - `exits.HOUR_SOURCES = ("live", "discord", "unknown")`;
  - `exits.hour_coverage(rows) -> dict[str, int]` — all three keys, zeros kept; a row whose `hour_source` is not one of the three (e.g. `None` on a hand-built `BookRow`) counts as `"unknown"`;
  - `exits.issued_rows(rows) -> list` — the rows with a `plan_date` (the population the alert-supply tallies already count);
  - header key `alert_hour_coverage = {"trades": hour_coverage(trades), "plans": hour_coverage(issued_rows(rows))}`;
  - every JSON cell whose `cut` starts with `alert_hour` carries `"hour_coverage"` = the `trades` dict; every JSON tally whose `cut` starts with `alert_hour` carries `"hour_coverage"` = the `plans` dict;
  - markdown: `- alert-hour coverage (trades): live a, discord b, unknown c` in the header block (above the cell table) and `- alert-hour coverage (plans): live a, discord b, unknown c` directly under `## Tallies`.

The JSON keeps exactly the four top-level keys. The markdown stays within `report.MD_MAX_LINES` (the cell table absorbs the two extra lines through its budget).

- [ ] **Step 1: Write the failing tests**

`tests/scout/test_autopsy_exits.py` (uses the file's `_row(**kw)` helper, which sets every unnamed field to `None`):

```python
def test_hour_coverage_counts_every_source_and_keeps_zeros():
    rows_ = [_row(hour_source="live"), _row(hour_source="live"),
             _row(hour_source="discord"), _row(hour_source="unknown"), _row()]
    assert exits.hour_coverage(rows_) == {"live": 2, "discord": 1, "unknown": 2}
    assert exits.hour_coverage([]) == {"live": 0, "discord": 0, "unknown": 0}
    assert tuple(exits.HOUR_SOURCES) == ("live", "discord", "unknown")


def test_issued_rows_are_the_rows_with_a_plan_date():
    with_date = _row(row_kind="plan", plan_date="2026-03-02")
    assert exits.issued_rows([with_date, _row(row_kind="trade", plan_date=None)]) == [with_date]
```

`tests/scout/test_book_autopsy.py` (`_files` writes 48 trades issued live at 13:00 UTC plus `EXPIRED_PLAN`, which has no `plan_issued_at`):

```python
def test_alert_hour_coverage_is_reported_by_source(tmp_path):
    out = _build(tmp_path)
    cov = out["header"]["alert_hour_coverage"]
    assert cov == {"trades": {"live": 48, "discord": 0, "unknown": 0},
                   "plans": {"live": 48, "discord": 0, "unknown": 1}}
    assert set(out) == {"header", "cells", "tallies", "giveback"}
    hour_cells = [c for c in out["cells"] if c["cut"] == "alert_hour"]
    assert hour_cells and all(c["hour_coverage"] == cov["trades"] for c in hour_cells)
    assert all("hour_coverage" not in c for c in out["cells"] if not c["cut"].startswith("alert_hour"))
    sessions = [t for t in out["tallies"] if t["cut"] == "alert_hour_session"]
    assert sessions and all(t["hour_coverage"] == cov["plans"] for t in sessions)
    assert all("hour_coverage" not in t for t in out["tallies"] if not t["cut"].startswith("alert_hour"))


def test_alert_hour_coverage_lines_sit_above_the_cells_and_the_tallies(tmp_path):
    md = report.render_markdown(_build(tmp_path))
    trades_line = "- alert-hour coverage (trades): live 48, discord 0, unknown 0"
    plans_line = "- alert-hour coverage (plans): live 48, discord 0, unknown 1"
    assert trades_line in md and plans_line in md
    assert md.index(trades_line) < md.index("## Cells")
    assert md.index("## Tallies") < md.index(plans_line)
    assert len(md.splitlines()) <= report.MD_MAX_LINES


def test_a_report_without_coverage_still_renders():
    """An autopsy JSON written before v200 has no alert_hour_coverage key."""
    built = {"header": {"window": [None, None], "n": 0, "bar_covered_n": 0, "pooled_net_expr": None,
                        "pooled_win_rate": None, "net_of_frictions": "modelled", "cells_tested": 0,
                        "resamples": 200, "seed": 42, "notes": []},
             "cells": [], "tallies": [], "giveback": {"n": 0, "mean": None, "median": None}}
    md = report.render_markdown(built)
    assert "alert-hour coverage" not in md
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_exits.py`
Expected: FAIL — `AttributeError: module 'autopsy.exits' has no attribute 'hour_coverage'`.

- [ ] **Step 3: Implement in `scripts/reports/autopsy/exits.py`**

- `HOUR_SOURCES = ("live", "discord", "unknown")` beside `SESSIONS`.
- `issued_rows(rows: list) -> list` returns `[r for r in rows if r.plan_date]`; `alert_supply_tallies` uses it instead of its inline list.
- `hour_coverage(rows: list) -> dict[str, int]`: a `Counter` over `r.hour_source if r.hour_source in HOUR_SOURCES else "unknown"`, returned as `{s: counts[s] for s in HOUR_SOURCES}`.

- [ ] **Step 4: Implement in `scripts/reports/autopsy/report.py`**

- `NOTES` gains: `"alert hour comes only from issued_at (the live stamp or the v200 Discord backfill); a plan without one is unknown, never a bar-date or fill hour"`.
- `_with_hour_coverage(items: list[dict], coverage: dict) -> list[dict]` sets `item["hour_coverage"] = dict(coverage)` on every item whose `item["cut"].startswith("alert_hour")` and returns `items`.
- `build_report`: after `header.update(...)`, set `header["alert_hour_coverage"] = {"trades": exits.hour_coverage(trades), "plans": exits.hour_coverage(exits.issued_rows(rows))}`; return `"cells": _with_hour_coverage([c.to_json() for c in cells], coverage["trades"])` and `"tallies": _with_hour_coverage([t.to_json() for t in tallies], coverage["plans"])`.
- `_coverage_line(label: str, cov: dict) -> str` returns `f"- alert-hour coverage ({label}): live {cov['live']}, discord {cov['discord']}, unknown {cov['unknown']}"`.
- `_header_lines(h)`: when `h.get("alert_hour_coverage")` is set, append `_coverage_line("trades", …["trades"])` after the `Cells tested` line, before provenance.
- `_tally_lines(tallies, coverage: dict | None = None)`: when `coverage` is set, the line `_coverage_line("plans", coverage)` follows `"## Tallies", ""`. `render_markdown` passes `report["header"].get("alert_hour_coverage", {}).get("plans")`.

- [ ] **Step 5: Run the tests**

```bash
python <wt>/scripts/dev/testrun.py file tests/scout/test_autopsy_exits.py
python <wt>/scripts/dev/testrun.py file tests/scout/test_book_autopsy.py
```

Expected: each `0 failed`.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C <wt>/scripts/reports/autopsy/exits.py <wt>/scripts/reports/autopsy/report.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add scripts/reports/autopsy/exits.py scripts/reports/autopsy/report.py \
  tests/scout/test_autopsy_exits.py tests/scout/test_book_autopsy.py
git -C <wt> commit -m "feat(v200): autopsy reports alert-hour coverage by source beside every alert_hour cell and tally"
```

# Phase C — Discord backfill

### Task V200-5: Discord backfill dry-run script (pure matching + REST read)

**Model:** opus — the one-to-one matching is the spec's anti-guess guarantee, and the script runs against the production bot token.

**Files:**
- Create: `scripts/ops/backfill_issued_at_discord.py`
- Create: `tests/scout/test_backfill_issued_at_discord.py`

**Interfaces:**
- Consumes: `swingbot.core.market.strategy_types.HORIZONS` (label per key), `swingbot.core.market.session.US_MARKET_TZ` and `nyse_calendar()` (`SessionCalendar.next_session(d)`), `swingbot.config.TOKEN` / `DISCORD_CHANNEL_TRADES_ID`, `swingbot.core.db.engine.get_engine()`.
- Produces (V200-6 runs it; V200-7 pins its CSV):
  - `PlanKey(plan_id: str, ticker: str, direction: str, strategy: str, horizon_key: str, created_date: dt.date)` (frozen dataclass)
  - `AlertKey(message_id: str, posted_at: dt.datetime, plan_id: str | None, ticker: str | None, direction: str | None, strategy: str | None, horizon_key: str | None)` (frozen dataclass; `plan_id` is a full id from the embed url or the 8-character prefix from the footer)
  - `HORIZON_LABEL_TO_KEY: dict[str, str]` = `{spec["label"]: key for key, spec in HORIZONS.items()}`
  - `alert_key(message: dict) -> AlertKey | None`
  - `MatchRow(plan_id, plan_candidates: int, message_candidates: int, message_id: str | None, issued_at: str | None, lag_hours: float | None, method: str)`; `method` ∈ `"exact"`, `"key"`, `"none"`
  - `match(plans: list[PlanKey], alerts: list[AlertKey]) -> list[MatchRow]` (one row per plan, input order)
  - `summary_lines(rows, *, messages_read: int = 0, messages_parsed: int = 0) -> list[str]`
  - `CSV_COLUMNS = ("plan_id", "plan_candidates", "message_candidates", "message_id", "issued_at", "lag_hours", "method")`; `write_csv(rows, fh) -> None`
  - run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - [--sample N]" < scripts/ops/backfill_issued_at_discord.py > <scratchpad>/v200_backfill.csv` — CSV on stdout, summary on stderr.

Message dict shape (what the REST read builds and every test feeds): `{"id": "<snowflake>", "created_at": "<ISO with offset>", "embeds": [<discord.Embed.to_dict()>]}` — an embed dict has `title`, optional `url`, optional `footer: {"text"}`, `fields: [{"name", "value", "inline"}]`.

Embed layouts known from the code (V200-6 confirms on sampled messages and adds any other):
- **Aug-Sep 2026 full alert** (`alert_embeds.build_embed`, `51f59913`): title `"<chips> · 🟢 BULLISH — AAPL"` style (`{arrow} {direction} — {ticker}`); field `Setup` = `"{strategy}"` or `"{strategy}  +N more horizon(s)"`; field `Swing type` = `HORIZONS[key]["label"]`; no plan id.
- **From 2026-09-30** (`kinds.title`, `kinds.footer`, `components.plan_link`): title `"🆕 ▲ LONG AAPL · ALERT · Lv4 ⭐"`; footer `"<disclaimer> · plan abcd1234"` (8-char prefix); `url` = `<base>/plans/<full plan_id>`.

Match rules (spec Part 1.4a):
1. **Exact first.** An alert with a `plan_id` resolves to the plans whose id equals it, or starts with it when it is 8 characters. It is an exact candidate only when it resolves to exactly one plan. A plan with exactly one exact candidate is `exact`; with two or more it is `none`. Any plan with an exact candidate leaves the key pool, and every alert carrying a `plan_id` stays out of the key pool, resolved or not.
2. **Key.** A remaining plan's candidates are the remaining alerts with equal `ticker`, `direction`, `strategy`, `horizon_key` (none of them `None`) and an Eastern posting date equal to `created_date` or `nyse_calendar().next_session(created_date)`.
3. **One-to-one.** A plan is `key`-matched when it has exactly one candidate and that message is a candidate for exactly one plan. Otherwise every plan involved is `none`.
- `message_candidates` = how many messages are candidates for the plan; `plan_candidates` = the most plans any of those messages is a candidate for (0 with no candidate).
- `issued_at` = the message's `posted_at` in UTC ISO (`.astimezone(dt.timezone.utc).isoformat()`); `lag_hours` = hours from 00:00 America/New_York on `created_date` to `posted_at`, rounded to 2 places. Both are `None` for `none`.

- [ ] **Step 1: Write the failing tests**

`tests/scout/test_backfill_issued_at_discord.py`:

```python
"""v200 V200-5: the Discord issue-time backfill dry run -- embed parsing, the
exact-then-one-to-one match, the summary. Pure functions only: no Discord, no DB."""
import datetime as dt
import importlib.util
import io
import re
from pathlib import Path

from swingbot.core.market.strategy_types import HORIZONS

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "ops" / "backfill_issued_at_discord.py"
_spec = importlib.util.spec_from_file_location("backfill_issued_at_discord", SCRIPT)
bf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bf)

PID_A = "abcd1234-0000-4000-8000-000000000001"
PID_B = "ef567890-0000-4000-8000-000000000002"
LABEL_2W = HORIZONS["2w"]["label"]


def _msg(mid, posted, title, *, setup="RSI", label=LABEL_2W, url=None, footer=None):
    embed = {"title": title, "fields": [{"name": "Setup", "value": setup, "inline": True},
                                        {"name": "Swing type", "value": label, "inline": True}]}
    if url:
        embed["url"] = url
    if footer:
        embed["footer"] = {"text": footer}
    return {"id": mid, "created_at": posted, "embeds": [embed]}


def _plan(pid=PID_A, ticker="AAPL", created=dt.date(2026, 8, 3), **kw):
    base = dict(plan_id=pid, ticker=ticker, direction="bullish", strategy="RSI",
                horizon_key="2w", created_date=created)
    base.update(kw)
    return bf.PlanKey(**base)


def _alert(mid, posted, *, plan_id=None, ticker="AAPL", direction="bullish", strategy="RSI",
           horizon_key="2w"):
    return bf.AlertKey(message_id=mid, posted_at=dt.datetime.fromisoformat(posted), plan_id=plan_id,
                       ticker=ticker, direction=direction, strategy=strategy, horizon_key=horizon_key)


def test_alert_key_reads_the_august_layout():
    key = bf.alert_key(_msg("1", "2026-08-03T21:10:00+00:00", "5️⃣ ✅ VALIDATED · 🟢 BULLISH — AAPL",
                            setup="RSI  +1 more horizon(s)"))
    assert (key.ticker, key.direction, key.strategy, key.horizon_key, key.plan_id) == \
        ("AAPL", "bullish", "RSI", "2w", None)
    assert key.posted_at == dt.datetime(2026, 8, 3, 21, 10, tzinfo=dt.timezone.utc)


def test_alert_key_reads_the_kinds_layout_and_the_full_id_from_the_url():
    key = bf.alert_key(_msg("2", "2026-10-01T13:31:00+00:00", "🆕 ▼ SHORT MSFT · ALERT · Lv4 ⭐",
                            url=f"https://bomeo-capital.com/plans/{PID_A}",
                            footer="Not financial advice · plan abcd1234"))
    assert (key.ticker, key.direction, key.plan_id) == ("MSFT", "bearish", PID_A)


def test_alert_key_falls_back_to_the_footer_prefix():
    key = bf.alert_key(_msg("3", "2026-10-01T13:31:00+00:00", "🆕 ▲ LONG MSFT · ALERT",
                            footer="Not financial advice · plan abcd1234"))
    assert key.plan_id == "abcd1234"


def test_non_alert_messages_are_skipped():
    assert bf.alert_key({"id": "4", "created_at": "2026-08-03T21:10:00+00:00", "embeds": []}) is None
    assert bf.alert_key(_msg("5", "2026-08-03T21:10:00+00:00", "📊 Daily summary")) is None


def test_an_unknown_horizon_label_leaves_the_key_incomplete():
    key = bf.alert_key(_msg("6", "2026-08-03T21:10:00+00:00", "🟢 BULLISH — AAPL", label="weird"))
    assert key.horizon_key is None


def test_a_one_to_one_key_match_is_matched_with_its_lag():
    [row] = bf.match([_plan()], [_alert("m1", "2026-08-03T21:10:00+00:00")])
    assert (row.method, row.message_id, row.plan_candidates, row.message_candidates) == ("key", "m1", 1, 1)
    assert row.issued_at == "2026-08-03T21:10:00+00:00"
    assert row.lag_hours == 17.17                         # 00:00 EDT = 04:00 UTC


def test_the_next_trading_day_matches_across_a_holiday():
    plan = _plan(created=dt.date(2026, 7, 2))             # Thursday; 3 July is the observed holiday
    assert bf.match([plan], [_alert("m1", "2026-07-06T13:30:00+00:00")])[0].method == "key"
    assert bf.match([plan], [_alert("m2", "2026-07-07T13:30:00+00:00")])[0].method == "none"
    assert bf.match([plan], [_alert("m3", "2026-07-01T23:00:00+00:00")])[0].method == "none"


def test_a_two_way_key_collision_leaves_every_plan_unknown():
    rows = bf.match([_plan(PID_A), _plan(PID_B)], [_alert("m1", "2026-08-03T21:10:00+00:00")])
    assert [(r.method, r.plan_candidates, r.message_candidates) for r in rows] == [("none", 2, 1)] * 2
    [row] = bf.match([_plan()], [_alert("m1", "2026-08-03T21:10:00+00:00"),
                                 _alert("m2", "2026-08-04T13:40:00+00:00")])
    assert (row.method, row.message_candidates, row.issued_at, row.lag_hours) == ("none", 2, None, None)


def test_an_exact_plan_id_match_wins_over_key_candidates():
    plans = [_plan(PID_A), _plan(PID_B)]
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id=PID_A),
              _alert("m2", "2026-08-03T21:11:00+00:00")]
    a, b = bf.match(plans, alerts)
    assert (a.method, a.message_id) == ("exact", "m1")
    assert (b.method, b.message_id, b.plan_candidates) == ("key", "m2", 1)


def test_an_eight_character_prefix_resolves_only_when_unique():
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id="abcd1234")]
    assert bf.match([_plan(PID_A)], alerts)[0].method == "exact"
    twin = _plan("abcd1234-ffff-4000-8000-000000000003")
    assert [r.method for r in bf.match([_plan(PID_A), twin], alerts)] == ["none", "none"]


def test_two_exact_messages_for_one_plan_stay_unknown():
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id=PID_A),
              _alert("m2", "2026-08-03T21:12:00+00:00", plan_id=PID_A)]
    [row] = bf.match([_plan()], alerts)
    assert (row.method, row.message_candidates) == ("none", 2)


def test_a_message_carrying_an_unresolved_plan_id_never_key_matches():
    alerts = [_alert("m1", "2026-08-03T21:10:00+00:00", plan_id="99999999")]
    assert bf.match([_plan()], alerts)[0].method == "none"


def test_summary_reports_rate_methods_ambiguity_and_lags():
    rows = [bf.MatchRow("p1", 1, 1, "m1", "2026-08-03T21:10:00+00:00", 17.17, "exact"),
            bf.MatchRow("p2", 1, 1, "m2", "2026-08-04T13:40:00+00:00", 33.67, "key"),
            bf.MatchRow("p3", 2, 1, None, None, None, "none"),
            bf.MatchRow("p4", 0, 0, None, None, None, "none")]
    text = "\n".join(bf.summary_lines(rows, messages_read=9, messages_parsed=7))
    assert "matched 2 of 4 plans (50.0%)" in text
    assert "exact 1, key 1" in text
    assert "ambiguous 1, no candidate 1" in text
    assert "messages read 9, parsed as alerts 7" in text
    assert re.search(r"lag hours: min 17\.17, p25 [\d.]+, median 25\.42, p75 [\d.]+, max 33\.67", text)


def test_the_csv_has_the_pinned_columns():
    buf = io.StringIO()
    bf.write_csv([bf.MatchRow("p1", 1, 1, "m1", "2026-08-03T21:10:00+00:00", 17.17, "key")], buf)
    lines = buf.getvalue().splitlines()
    assert lines[0] == ",".join(bf.CSV_COLUMNS) == \
        "plan_id,plan_candidates,message_candidates,message_id,issued_at,lag_hours,method"
    assert lines[1] == "p1,1,1,m1,2026-08-03T21:10:00+00:00,17.17,key"


def test_the_script_is_read_only_rest_only_and_never_the_mirror():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "config.DISCORD_CHANNEL_TRADES_SIMPLE_ID" not in source
    assert "config.DISCORD_CHANNEL_TRADES_ID" in source
    assert not re.search(r"client\.(connect|start|run)\(", source)      # no gateway session
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|ALTER|DROP)\b", source)
    assert "READ ONLY" in source
    assert not re.search(r"print\([^)]*TOKEN", source)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_backfill_issued_at_discord.py`
Expected: FAIL — `FileNotFoundError` for `scripts/ops/backfill_issued_at_discord.py`.

- [ ] **Step 3: Write `scripts/ops/backfill_issued_at_discord.py`**

Module docstring (required by the spec): what it reads (`DISCORD_CHANNEL_TRADES_ID` only, never the `…_SIMPLE_ID` mirror; bot-authored messages 2026-07-01..2026-09-16 Eastern inclusive; plans with `created_at` in that range and no `issued_at`), how (`Client.login` without the gateway, so the live bot's session is untouched; the token comes from the container environment and is never printed), the two embed layouts and fields above, the three match rules, the output (CSV on stdout, summary on stderr, nothing written anywhere), the run command, exit codes (`0` done, `1` Discord login/HTTP error, `2` token or channel unset). No SQL write keyword anywhere in the file, docstring included.

Pure part (module level imports only `csv`, `datetime`, `re`, `statistics`, `sys`, `os`, `argparse`, `asyncio`, `collections`, `dataclasses`, `HORIZONS`, `US_MARKET_TZ`, `nyse_calendar`; `discord`, `config` and the engine are imported inside the functions that need them):
- Title parsing: `_SIDE_RE = re.compile(r"(?i:\b(LONG|SHORT|BULLISH|BEARISH)\b)\s+(?:—\s+)?([A-Z0-9][A-Z0-9.^=\-]*)")`; `LONG`/`BULLISH` → `"bullish"`, `SHORT`/`BEARISH` → `"bearish"`.
- `Setup` value: strip `re.compile(r"\s+\+\d+ more horizon\(s\)$")`, then `.strip()`. `Swing type` → `HORIZON_LABEL_TO_KEY.get(value.strip())`.
- Plan id: `re.search(r"/plans/([0-9a-f-]{8,})", url)` first, else `re.search(r"\bplan ([0-9a-f]{8})\b", footer_text)`.
- `alert_key` returns `None` when no embed has a title, or when neither (ticker and direction) nor a plan id was found. Use the first embed with a title.
- `_eastern_date(ts) = ts.astimezone(US_MARKET_TZ).date()`; keep one module-level `_CALENDAR = None` filled lazily by `nyse_calendar()`.

`match` (the algorithm the tests pin; split into helpers to stay under complexity 15):

```python
def match(plans, alerts):
    exact = _exact_candidates(plans, alerts)                  # plan_id -> [AlertKey]
    pool_plans = [p for p in plans if p.plan_id not in exact]
    pool_alerts = [a for a in alerts if not a.plan_id]
    keyed = {p.plan_id: [a for a in pool_alerts if _key_matches(p, a)] for p in pool_plans}
    plans_per_message = Counter(a.message_id for cands in keyed.values() for a in cands)
    return [_exact_row(p, exact[p.plan_id]) if p.plan_id in exact
            else _key_row(p, keyed[p.plan_id], plans_per_message) for p in plans]
```

`_exact_candidates`: for each alert with a `plan_id`, resolve (equal, or 8-char prefix); keep it only when it resolves to exactly one plan. `_exact_row`: one candidate → `exact` with `plan_candidates=1`, `message_candidates=1`; more → `none` with `message_candidates=len(cands)`, `plan_candidates=1`. `_key_row`: one candidate whose `plans_per_message` is 1 → `key`; else `none`; counts as defined above. `_row_for(plan, alert, method)` computes `issued_at` and `lag_hours` (`dt.datetime.combine(plan.created_date, dt.time(0), tzinfo=US_MARKET_TZ)`).

`summary_lines`: `matched M of N plans (P%)` (one decimal; `0.0%` when N is 0), `exact E, key K`, `ambiguous A, no candidate Z` (`none` rows with `message_candidates > 0` or `plan_candidates > 1` versus the rest), `messages read R, parsed as alerts S`, `lag hours: min …, p25 …, median …, p75 …, max …` (2 decimals, `statistics.quantiles(..., n=4)` when ≥ 2 lags; `lag hours: n/a` with none).

`write_csv(rows, fh)`: `csv.writer(fh, lineterminator="\n")`, header `CSV_COLUMNS`, `None` → empty field.

I/O part:

```python
WINDOW_FIRST = dt.date(2026, 7, 1)
WINDOW_LAST = dt.date(2026, 9, 16)
_PLANS_SQL = ("SELECT plan_id, doc->>'ticker', doc->>'direction', doc->>'strategy', "
              "doc->>'horizon_key', left(doc->>'created_at', 10) FROM plans "
              "WHERE doc->>'issued_at' IS NULL "
              "AND left(doc->>'created_at', 10) BETWEEN :first AND :last ORDER BY plan_id")


def load_plans() -> list[PlanKey]:
    import sqlalchemy as sa
    from swingbot.core.db.engine import get_engine
    with get_engine().connect() as conn:
        conn.execute(sa.text("SET TRANSACTION READ ONLY"))
        rows = conn.execute(sa.text(_PLANS_SQL), {"first": WINDOW_FIRST.isoformat(),
                                                  "last": WINDOW_LAST.isoformat()}).fetchall()
        conn.rollback()
    return [PlanKey(r[0], (r[1] or "").upper(), _norm_side(r[2]), r[3] or "", r[4] or "",
                    dt.date.fromisoformat(r[5])) for r in rows if r[5]]


async def read_messages(token: str, channel_id: int) -> list[dict]:
    import discord
    client = discord.Client(intents=discord.Intents.none())
    after = dt.datetime.combine(WINDOW_FIRST, dt.time(0), tzinfo=US_MARKET_TZ) - dt.timedelta(seconds=1)
    before = dt.datetime.combine(WINDOW_LAST + dt.timedelta(days=1), dt.time(0), tzinfo=US_MARKET_TZ)
    out = []
    async with client:
        await client.login(token)        # HTTP only: no gateway session beside the live bot
        channel = await client.fetch_channel(channel_id)
        async for msg in channel.history(limit=None, after=after, before=before, oldest_first=True):
            if msg.author.id == client.user.id:
                out.append({"id": str(msg.id), "created_at": msg.created_at.isoformat(),
                            "embeds": [e.to_dict() for e in msg.embeds]})
    return out
```

`_norm_side` maps `long`/`bullish` → `"bullish"`, `short`/`bearish` → `"bearish"`, anything else unchanged lower-cased.

`main(argv=None) -> int`: `argparse` with `--sample N` (default 0). Insert `os.getcwd()` at `sys.path[0]` (the script arrives on stdin inside the container, cwd `/app`). Return 2 with a stderr line when `config.TOKEN` or `config.DISCORD_CHANNEL_TRADES_ID` is unset. Catch `discord.LoginFailure, discord.HTTPException` → stderr line, return 1. With `--sample N`: print to stderr, for the first N parsed and the first N unparsed bot messages, `title`, `url`, `footer.text`, every field `name: value` and the parsed `AlertKey`; write no CSV; return 0. Otherwise: `write_csv(match(plans, alerts), sys.stdout)` and the `summary_lines` to stderr; return 0. Keep `main` small: `_sample_report(messages, n)` and `_run(plans, messages)` helpers.

- [ ] **Step 4: Run the tests**

Run: `python <wt>/scripts/dev/testrun.py file tests/scout/test_backfill_issued_at_discord.py`
Expected: `0 failed`.

- [ ] **Step 5: Lint, complexity, local smoke**

```bash
python -m py_compile <wt>/scripts/ops/backfill_issued_at_discord.py
python -m radon cc -s -n C <wt>/scripts/ops/backfill_issued_at_discord.py
python <wt>/scripts/ops/backfill_issued_at_discord.py --help
```

Expected: no compile error, no radon output, the usage text. Do **not** run it against Discord here; V200-6 does, on the VM.

- [ ] **Step 6: Commit**

```bash
git -C <wt> add scripts/ops/backfill_issued_at_discord.py tests/scout/test_backfill_issued_at_discord.py
git -C <wt> commit -m "feat(v200): read-only Discord issue-time backfill dry run (exact plan id, then one-to-one key)"
```

### Task V200-6: Production dry-run, then STOP for the partner

**Model:** sonnet — runs a finished script read-only and records numbers; parser fixes are small and test-first.

**Files:**
- Create: `docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md`
- Modify (only if the sampled embed layout differs from V200-5's two layouts): `scripts/ops/backfill_issued_at_discord.py`, `tests/scout/test_backfill_issued_at_discord.py`

**Interfaces:**
- Consumes: V200-5's script, `CSV_COLUMNS`, `alert_key`, `HORIZON_LABEL_TO_KEY`.
- Produces: `<scratchpad>/v200_backfill.csv` (the dry-run CSV, **never committed**; V200-7 pins its matched rows) and the results file with the match rate, exact vs key counts, ambiguous and no-candidate counts, the lag distribution, and the parser layouts seen.

Read-only throughout: the script reads the plans table inside `SET TRANSACTION READ ONLY` and Discord over REST. Nothing is written on the VM (the script arrives on stdin). Never print, echo or log the token; never paste message bodies beyond title/field/footer text into the repo.

- [ ] **Step 1: Sample the embed layouts**

```bash
bash <wt>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --sample 8" \
  < <wt>/scripts/ops/backfill_issued_at_discord.py > /dev/null 2> <scratchpad>/v200_sample.txt
```

Expected: `<scratchpad>/v200_sample.txt` lists up to 8 parsed and 8 unparsed bot messages from 2026-07-01..09-16 with their title, url, footer, fields and parsed key. Exit 2 means the token or channel id is unset in the container: stop and report `BLOCKED:`.

Check, from the sample:
- July messages: is the title still `{arrow} {direction} — {ticker}` (or another shape)? Is the strategy in a `Setup` field and the horizon in `Swing type`?
- Does any message carry a plan id (url or `plan xxxxxxxx` footer)?
- Do the unparsed messages include alerts (setup alerts the parser missed), or only non-alert posts (digests, summaries)?
- Does every `Swing type` label map through `HORIZON_LABEL_TO_KEY`? A label from an older `HORIZONS` text (`git -C <wt> log -p -S'"label"' -- swingbot/core/market/strategy_types.py`) is added to a `HISTORICAL_HORIZON_LABELS: dict[str, str]` merged into `HORIZON_LABEL_TO_KEY`.

- [ ] **Step 2: Only if a layout or label is missing — extend the parser test-first**

For each missing layout: add a test to `tests/scout/test_backfill_issued_at_discord.py` built from the sampled title/fields (ticker and values may be kept; it is alert text, not a secret), named `test_alert_key_reads_the_<month>_layout`, run it (expected FAIL), extend `alert_key` / `_SIDE_RE` / the field names / `HISTORICAL_HORIZON_LABELS`, run `python <wt>/scripts/dev/testrun.py file tests/scout/test_backfill_issued_at_discord.py` (expected `0 failed`), and repeat Step 1 until no alert is in the unparsed sample. Record each added layout in the module docstring's layout list. If no layout is missing, skip this step and say so in the results file.

- [ ] **Step 3: Run the full dry run**

```bash
bash <wt>/scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" \
  < <wt>/scripts/ops/backfill_issued_at_discord.py \
  > <scratchpad>/v200_backfill.csv 2> <scratchpad>/v200_backfill_summary.txt
head -n 1 <scratchpad>/v200_backfill.csv
cat <scratchpad>/v200_backfill_summary.txt
```

Expected: the CSV header is exactly `plan_id,plan_candidates,message_candidates,message_id,issued_at,lag_hours,method`; the summary prints the match line, the method line, the ambiguity line, the message counts and the lag line.

Sanity checks, recorded in the results file:
- The plan count is close to the spec's 373 Jul–Aug plans plus the September plans without `issued_at` (spec: 140 − 96 = 44).
- `python -c "import csv,sys; r=list(csv.DictReader(open(sys.argv[1],encoding='utf-8'))); m=[x for x in r if x['method']!='none']; ids=[x['message_id'] for x in m]; assert len(ids)==len(set(ids)), 'a message matched twice'; print(len(r), len(m))" <scratchpad>/v200_backfill.csv` prints the counts with no assertion error (one-to-one held).
- No matched `lag_hours` is negative (a post before the bar date began cannot be that plan's alert); list any negative or above-72 lags by plan id.

- [ ] **Step 4: Write the results file**

`docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md`:

```markdown
# v200 Discord issue-time backfill: dry run, <date>

Read-only. Script `scripts/ops/backfill_issued_at_discord.py` at <commit>, run in the bot container
over REST against DISCORD_CHANNEL_TRADES_ID (never the simple mirror), messages 2026-07-01..2026-09-16 ET.

## Result
- Plans without issued_at, created 2026-07-01..09-16: N
- Matched: M of N (P%) -- exact E, key K
- Ambiguous (left unknown): A; no candidate: Z
- Messages read R, parsed as alerts S
- Lag hours (00:00 ET on the bar date to the post): min, p25, median, p75, max
- One-to-one check: no message matched twice

## Embed layouts seen
<per period: title shape, Setup / Swing type fields, plan id present or not; labels added>

## Outliers
<negative or very large lags, by plan id; or "none">

## Decision needed
The partner decides whether V200-7 pins these M matches in revision v200_001.
The raw CSV stays in the scratchpad (<scratchpad>/v200_backfill.csv) and is never committed.
```

- [ ] **Step 5: Commit**

```bash
git -C <wt> add docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md
# plus the script and its test, only if Step 2 changed them
git -C <wt> commit -m "docs(v200): Discord issue-time backfill dry run -- match rate for the partner"
```

- [ ] **Step 6: STOP — partner checkpoint**

End the task with `STATUS: CHECKPOINT` and report the match rate, the exact/key split, the ambiguous count and the lag median to the controller. **V200-7 does not start until the partner has seen this match rate and said go** (spec Part 1.4c, Verification 3). Keep `<scratchpad>/v200_backfill.csv` in place for V200-7; if the session ends first, V200-7 re-runs Step 3 at the same commit and checks that the summary is unchanged.

### Task V200-7: Data revision `v200_001` pinning the Discord issue times

**Model:** opus — a data revision on the trading store; its refusal and no-op contract is what makes the production write safe.

**Precondition:** the partner has seen V200-6's match rate and said go. Without that, stop with `BLOCKED: waiting for the partner's go on the V200-6 match rate`.

**Files:**
- Create: `swingbot/core/db/migrations/versions/v200_001_discord_issued_at.py`
- Create: `tests/db/test_v200_discord_issued_at.py`
- Modify: `tests/db/test_v173_002_preregistration_verdicts.py` (`test_v173_002_sits_on_v173_001_and_is_the_single_head`, ~l.46-50)

**Interfaces:**
- Consumes: `<scratchpad>/v200_backfill.csv` (V200-6; rows with `method` `exact` or `key`); the V200-6 results file's `Matched: M of N` line; `TradePlanV2.issued_at_source` vocabulary (V200-2).
- Produces: `revision = "v200_001"`, `down_revision = "v173_002"`; `PINNED_ISSUED_AT: dict[str, str]` (plan_id → UTC ISO issue time); pure `stamp(docs, pins) -> dict[str, dict]` and `unstamp(docs, pins) -> list[str]`, both raising `RuntimeError` naming the ids; `apply_upgrade(conn, pins=PINNED_ISSUED_AT) -> int`, `apply_downgrade(conn, pins=PINNED_ISSUED_AT) -> int`. It sets / removes `issued_at` and `issued_at_source = "discord"` only. Alembic head becomes `v200_001`.

Contract (copied from `v173_001_manual_bulk_retag.py`; spec Part 1.4b):
- rows are locked with `SELECT … FOR UPDATE`; every check runs before the first write;
- **refuse** (raise) when only some pinned plans exist, or (upgrade) when a pinned plan already carries `issued_at`, or (downgrade) when a pinned plan does not carry exactly `{issued_at: <pinned>, issued_at_source: "discord"}`;
- **no-op** when none of the pinned plans exist (test DB, fresh install, a dev book): one log line, nothing written, so `alembic upgrade head` still works there;
- `downgrade()` removes both fields from exactly the pinned ids.

- [ ] **Step 1: Generate the pinned mapping from the dry-run CSV**

```bash
python - <scratchpad>/v200_backfill.csv > <scratchpad>/v200_pins.txt <<'EOF'
import csv, sys
rows = [r for r in csv.DictReader(open(sys.argv[1], encoding="utf-8")) if r["method"] in ("exact", "key")]
for r in sorted(rows, key=lambda r: r["plan_id"]):
    print(f'    "{r["plan_id"]}": "{r["issued_at"]}",  # {r["method"]}, lag {r["lag_hours"]} h')
print(f"# {len(rows)} pins", file=sys.stderr)
EOF
```

Expected: the stderr count equals the results file's `Matched: M`. If the CSV is gone, re-run V200-6 Step 3 at the same commit first and confirm the summary is unchanged.

- [ ] **Step 2: Write the failing tests**

`tests/db/test_v200_discord_issued_at.py` (fake connection only: no database, never the production replica):

```python
"""v200_001: stamp exactly the pinned Discord issue times, refusing before any write."""
from __future__ import annotations

import copy
import datetime as dt
import importlib.util
import logging
import pathlib
import re
import types

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION_FILE = (REPO / "swingbot" / "core" / "db" / "migrations" / "versions"
                 / "v200_001_discord_issued_at.py")
DRY_RUN = REPO / "docs" / "superpowers" / "results" / "2026-10-29-v200-backfill-dry-run.md"


def _load_revision():
    spec = importlib.util.spec_from_file_location("v200_001_discord_issued_at", REVISION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIG = _load_revision()
PINS = {"p-1": "2026-08-03T21:10:00+00:00", "p-2": "2026-08-04T13:40:00+00:00"}


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class FakeConn:
    """`plans` maps plan_id -> doc (a dict), like the jsonb doc column."""

    def __init__(self, plans):
        self.plans = plans
        self.select_sql = None
        self.selected_ids = None
        self.updates = []

    def execute(self, statement, params):
        sql = str(statement).strip()
        if sql.upper().startswith("SELECT"):
            self.select_sql, self.selected_ids = sql, list(params["ids"])
            return _Result([(pid, doc.get("issued_at"), doc.get("issued_at_source"))
                            for pid, doc in self.plans.items() if pid in params["ids"]])
        assert sql.upper().startswith("UPDATE PLANS"), sql
        doc = self.plans[params["plan_id"]]
        if "jsonb_build_object" in sql:
            doc.update(issued_at=params["issued_at"], issued_at_source="discord")
        else:
            doc.pop("issued_at", None)
            doc.pop("issued_at_source", None)
        self.updates.append(params["plan_id"])
        return _Result([])


def _book(pins=PINS, **extra):
    book = {pid: {"ticker": "AAA", "status": "CLOSED"} for pid in pins}
    book.update(extra)
    return book


def test_upgrade_stamps_exactly_the_pinned_plans():
    conn = FakeConn(_book(other={"ticker": "ZZZ"}))
    assert MIG.apply_upgrade(conn, PINS) == 2
    for pid, at in PINS.items():
        assert conn.plans[pid] == {"ticker": "AAA", "status": "CLOSED",
                                   "issued_at": at, "issued_at_source": "discord"}
    assert conn.plans["other"] == {"ticker": "ZZZ"}
    assert sorted(conn.updates) == sorted(PINS)
    assert "FOR UPDATE" in conn.select_sql and conn.selected_ids == list(PINS)


def test_downgrade_removes_both_fields_from_exactly_the_pinned_plans():
    live = {"issued_at": "2026-10-01T13:31:00+00:00", "issued_at_source": "live"}
    conn = FakeConn(_book(other=dict(live)))
    MIG.apply_upgrade(conn, PINS)
    assert MIG.apply_downgrade(conn, PINS) == 2
    for pid in PINS:
        assert conn.plans[pid] == {"ticker": "AAA", "status": "CLOSED"}
    assert conn.plans["other"] == live


def test_a_partial_book_is_refused_before_any_write():
    conn = FakeConn({"p-1": {}})
    with pytest.raises(RuntimeError, match=r"missing.*p-2"):
        MIG.apply_upgrade(conn, PINS)
    assert conn.updates == []


def test_a_pinned_plan_already_carrying_issued_at_is_refused():
    conn = FakeConn(_book(**{"p-2": {"issued_at": "2026-08-04T13:00:00+00:00"}}))
    with pytest.raises(RuntimeError, match=r"already carry issued_at.*p-2"):
        MIG.apply_upgrade(conn, PINS)
    assert conn.updates == []


def test_downgrade_refuses_a_plan_that_is_not_the_pinned_stamp():
    conn = FakeConn(_book())
    MIG.apply_upgrade(conn, PINS)
    conn.plans["p-2"]["issued_at_source"] = "live"
    conn.updates.clear()
    with pytest.raises(RuntimeError, match=r"p-2"):
        MIG.apply_downgrade(conn, PINS)
    assert conn.updates == []


def test_a_book_without_any_pinned_plan_is_a_logged_no_op(caplog):
    conn = FakeConn({"other": {}})
    with caplog.at_level(logging.INFO, logger="alembic.runtime.migration"):
        assert MIG.apply_upgrade(conn, PINS) == 0
        assert MIG.apply_downgrade(conn, PINS) == 0
    assert conn.updates == []
    assert "none of the 2 pinned plans" in caplog.text


def test_the_pure_steps_never_mutate_their_input():
    docs = {pid: {"issued_at": None, "issued_at_source": None} for pid in PINS}
    before = copy.deepcopy(docs)
    assert MIG.stamp(docs, PINS) == {pid: {"issued_at": at, "issued_at_source": "discord"}
                                     for pid, at in PINS.items()}
    assert docs == before


def test_upgrade_and_downgrade_run_on_the_alembic_bind(monkeypatch):
    conn = FakeConn(_book(MIG.PINNED_ISSUED_AT))
    monkeypatch.setattr(MIG, "op", types.SimpleNamespace(get_bind=lambda: conn))
    MIG.upgrade()
    assert all(conn.plans[p]["issued_at_source"] == "discord" for p in MIG.PINNED_ISSUED_AT)
    MIG.downgrade()
    assert all("issued_at" not in conn.plans[p] for p in MIG.PINNED_ISSUED_AT)


def test_the_revision_writes_only_the_two_fields():
    assert set(re.findall(r"'(\w+)'", str(MIG._STAMP))) == {"issued_at", "issued_at_source", "discord"}
    assert set(re.findall(r"'(\w+)'", str(MIG._UNSTAMP))) == {"issued_at", "issued_at_source"}


def test_the_pinned_mapping_is_well_formed_and_matches_the_dry_run():
    pins = MIG.PINNED_ISSUED_AT
    assert pins
    for pid, at in pins.items():
        assert re.fullmatch(r"[0-9a-f-]{36}", pid), pid
        stamp = dt.datetime.fromisoformat(at)
        assert stamp.utcoffset() == dt.timedelta(0), pid
        assert dt.date(2026, 7, 1) <= stamp.date() <= dt.date(2026, 9, 18), pid
    matched = re.search(r"Matched: (\d+) of", DRY_RUN.read_text(encoding="utf-8"))
    assert matched and int(matched.group(1)) == len(pins)


@pytest.fixture(scope="module")
def scripts():
    return ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))


def test_v200_001_sits_on_v173_002_and_is_the_single_head(scripts):
    assert (MIG.revision, MIG.down_revision) == ("v200_001", "v173_002")
    assert scripts.get_revision("v200_001").down_revision == "v173_002"
    assert scripts.get_heads() == ["v200_001"]
```

`tests/db/test_v173_002_preregistration_verdicts.py`: the head assertion becomes `assert scripts.get_heads() == ["v200_001"]   # v200_001 chains on v173_002`, and the test is renamed `test_v173_002_sits_on_v173_001_below_v200_001`.

- [ ] **Step 3: Run them to verify they fail**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v200_discord_issued_at.py`
Expected: FAIL — `FileNotFoundError` for the revision file.

- [ ] **Step 4: Write `swingbot/core/db/migrations/versions/v200_001_discord_issued_at.py`**

- Module docstring in the `v173_001` style: why (spec v200 Part 1.4b: pre-v87 plans have no `issued_at`; the issue time is recovered from the Discord alert by the V200-6 dry run, partner-approved on <date>; exact plan-id or one-to-one key matches only), the refusals and the no-op, the NOTIFY burst (the `plans` trigger fires once per touched row; the admin UI's SSE stream sees a burst; expected), `Revision ID: v200_001`, `Revises: v173_002`.
- `revision = "v200_001"`; `down_revision = "v173_002"   # = python -m alembic heads on main when written`; `branch_labels = None`; `depends_on = None`; `log = logging.getLogger("alembic.runtime.migration")`.
- `PINNED_ISSUED_AT: dict[str, str] = {` + the lines of `<scratchpad>/v200_pins.txt` + `}`, preceded by `# Copied verbatim from the V200-6 dry-run CSV (method exact or key); <M> plans.`
- SQL:

```python
# FOR UPDATE: the pinned rows stay locked from the check to the write (one transaction).
_SELECT = sa.text(
    "SELECT plan_id, doc->>'issued_at' AS issued_at, doc->>'issued_at_source' AS source "
    "FROM plans WHERE plan_id = ANY(:ids) FOR UPDATE")
_STAMP = sa.text(
    "UPDATE plans SET doc = doc || jsonb_build_object("
    "'issued_at', CAST(:issued_at AS text), 'issued_at_source', 'discord') WHERE plan_id = :plan_id")
_UNSTAMP = sa.text(
    "UPDATE plans SET doc = doc - 'issued_at' - 'issued_at_source' WHERE plan_id = :plan_id")
```

- `stamp(docs: dict[str, dict], pins: dict[str, str]) -> dict[str, dict]` — `docs` maps plan_id → `{"issued_at", "issued_at_source"}` as selected. Raises `RuntimeError(f"v200_001: pinned plans missing: {missing}")`, then `RuntimeError(f"v200_001: pinned plans already carry issued_at: {already}")`; returns `{pid: {"issued_at": pins[pid], "issued_at_source": "discord"}}` for every pin. Never mutates `docs`.
- `unstamp(docs, pins) -> list[str]` — the same missing check, then `RuntimeError(f"v200_001: not the pinned discord stamp: {wrong}")` for any pin whose doc is not exactly `{"issued_at": pins[pid], "issued_at_source": "discord"}`; returns `sorted(pins)`.
- `_selected(conn, pins) -> dict[str, dict]` runs `_SELECT` with `{"ids": list(pins)}`.
- `apply_upgrade(conn, pins=PINNED_ISSUED_AT) -> int` / `apply_downgrade(conn, pins=PINNED_ISSUED_AT) -> int`: select; on an empty selection `log.info("v200_001: none of the %d pinned plans exist here (not the production book); nothing to %s", len(pins), "stamp"|"unstamp")` and return 0; else run the pure step, then one `_STAMP` (`{"issued_at": …, "plan_id": …}`) / `_UNSTAMP` (`{"plan_id": …}`) per id, log the count, return it.
- `upgrade()` → `apply_upgrade(op.get_bind())`; `downgrade()` → `apply_downgrade(op.get_bind())`.

- [ ] **Step 5: Run the tests**

```bash
python <wt>/scripts/dev/testrun.py file tests/db/test_v200_discord_issued_at.py
python <wt>/scripts/dev/testrun.py file tests/db/test_v173_002_preregistration_verdicts.py
python <wt>/scripts/dev/testrun.py file tests/db/test_v173_manual_bulk_retag.py
python -m alembic -c <wt>/alembic.ini heads
```

Expected: `0 failed` each (run `/replicate-prod-db` first if `test_v173_002_preregistration_verdicts.py` needs the database and the replica has not been synced this session); `heads` prints `v200_001 (head)`.

- [ ] **Step 6: Complexity**

Run: `python -m radon cc -s -n C <wt>/swingbot/core/db/migrations/versions/v200_001_discord_issued_at.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git -C <wt> add swingbot/core/db/migrations/versions/v200_001_discord_issued_at.py \
  tests/db/test_v200_discord_issued_at.py tests/db/test_v173_002_preregistration_verdicts.py
git -C <wt> commit -m "feat(v200): data revision v200_001 pins the Discord-recovered issue times (refuse/no-op contract)"
```

### Task V200-8: Verify `v200_001` up and down on the replica; deploy note

**Model:** sonnet — runs a fixed verification script against the local replica and records numbers; no production write, no shipped code.

**Precondition:** V200-7 is committed in `<wt>` and `python -m alembic -c <wt>/alembic.ini heads` prints `v200_001 (head)`.

**Files:**
- Modify: `docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md` (append `## Replica verification` and `## Deploy note`)
- Scratch only (never committed): `<scratchpad>/v200_replica_check.py`, `<scratchpad>/v200_replica_check.txt`

**Interfaces:**
- Consumes: V200-7's module (`revision`, `PINNED_ISSUED_AT`, `apply_upgrade(conn, pins)`); V200-1's `docs/superpowers/results/2026-10-29-v200-prod-reads.md` json (`pitr_last_drill`); the `plans` NOTIFY trigger (channel `trades`, `swingbot/core/db/events.py:11`, raised by `pg_notify(TG_ARGV[0], '')` in `swingbot/core/db/notify.py:27`).
- Produces: nothing a later task consumes. The deploy note is for the partner's normal deploy, which is not a plan task.

Rules for this task:
- The target is the database `swingbot_prod_replica` in the one shared `swing-db` container — **never** `swingbot` (the working local database), never a new container or database, never production. Nothing here touches the VM except `/replicate-prod-db`'s read-only dump.
- The `DATABASE_URL` is read from the main checkout's `.env` inside the script and only its database name is swapped; the URL is never printed, echoed or logged.
- `swingbot/config.py` loads `.env` with `override=True`, so exporting `DATABASE_URL` in the shell does **not** redirect Alembic. The script hands Alembic an explicit connection through `Config.attributes["connection"]`, which `swingbot/core/db/migrations/env.py:34-39` honours.

- [ ] **Step 1: Refresh the replica**

Run `/replicate-prod-db` (default target `swingbot_prod_replica`) from the main checkout, unless it already ran this session after V200-6.
Expected: the final line `replicate_prod_db: MATCH|DRIFT target=swingbot_prod_replica tables=… alembic=…`. `MISMATCH` or `FAIL` → stop and report `BLOCKED:` with the printed lines. An `alembic=` below `v173_002` is handled by Step 2's script (it brings the replica to `v173_002` first, replica only); `alembic=v200_001` means production was migrated outside this plan: stop with `BLOCKED:`.

- [ ] **Step 2: Write the verification script**

`<scratchpad>/v200_replica_check.py` is this task's test: every expectation is an `assert`, and a failed assert is the task failing.

```python
"""v200_001 up/down on swingbot_prod_replica. Usage: python v200_replica_check.py <wt> <main checkout>"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import psycopg
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

WT, MAIN = (pathlib.Path(p) for p in sys.argv[1:3])
REPLICA = "swingbot_prod_replica"
url = make_url(dotenv_values(MAIN / ".env")["DATABASE_URL"]).set(database=REPLICA)
assert url.database == REPLICA                     # never the working `swingbot` database
engine = sa.create_engine(url)
pg_dsn = url.set(drivername="postgresql").render_as_string(hide_password=False)

spec = importlib.util.spec_from_file_location(
    "v200_001", WT / "swingbot/core/db/migrations/versions/v200_001_discord_issued_at.py")
MIG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MIG)
PINS = MIG.PINNED_ISSUED_AT
M = len(PINS)
PARAMS = {"ids": list(PINS), "pins": json.dumps(PINS)}

cfg = Config(str(WT / "alembic.ini"))
cfg.set_main_option("script_location", str(WT / "swingbot/core/db/migrations"))

# Pinned docs are compared without the two fields, so a pre-existing `"issued_at": null`
# key (which the downgrade drops) is reported separately instead of failing the round trip.
_STRIPPED = ("CASE WHEN plan_id = ANY(:ids) THEN doc - 'issued_at' - 'issued_at_source' "
             "ELSE doc END")
QUERIES = {
    "head": "SELECT version_num FROM alembic_version",
    "plans": "SELECT count(*) FROM plans",
    "pinned_present": "SELECT count(*) FROM plans WHERE plan_id = ANY(:ids)",
    "pinned_with_issued_at": ("SELECT count(*) FROM plans WHERE plan_id = ANY(:ids) "
                              "AND doc->>'issued_at' IS NOT NULL"),
    "pinned_null_keys": ("SELECT count(*) FROM plans WHERE plan_id = ANY(:ids) "
                         "AND doc->'issued_at' = 'null'::jsonb"),
    "discord_tagged": "SELECT count(*) FROM plans WHERE doc->>'issued_at_source' = 'discord'",
    "pinned_matching_pin": (
        "SELECT count(*) FROM plans p JOIN jsonb_each_text(CAST(:pins AS jsonb)) j "
        "ON j.key = p.plan_id WHERE p.doc->>'issued_at' = j.value "
        "AND p.doc->>'issued_at_source' = 'discord'"),
    "docs_md5": f"SELECT md5(string_agg(plan_id || ({_STRIPPED})::text, '|' ORDER BY plan_id)) FROM plans",
    "unpinned_md5": ("SELECT md5(string_agg(plan_id || doc::text, '|' ORDER BY plan_id)) "
                     "FROM plans WHERE NOT (plan_id = ANY(:ids))"),
}


def snapshot() -> dict:
    with engine.connect() as conn:
        return {k: conn.execute(sa.text(q), PARAMS).scalar() for k, q in QUERIES.items()}


def migrate(fn, target: str) -> None:
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        fn(cfg, target)


def notifies_during(fn) -> int:
    with psycopg.connect(pg_dsn, autocommit=True) as listener:
        listener.execute("LISTEN trades")
        fn()
        return sum(1 for _ in listener.notifies(timeout=2.0))


before = snapshot()
assert before["head"] != "v200_001", "replica already at v200_001: production migrated outside the plan"
if before["head"] != "v173_002":
    migrate(command.upgrade, "v173_002")
    before = snapshot()
print("before", before)
assert before["head"] == "v173_002"
assert before["pinned_present"] == M, "replica lacks pinned plans: re-run /replicate-prod-db"
assert before["pinned_with_issued_at"] == 0
assert before["discord_tagged"] == 0

n_up = notifies_during(lambda: migrate(command.upgrade, "v200_001"))
up = snapshot()
print("after upgrade", up, "NOTIFY trades:", n_up)
assert up["head"] == "v200_001"
assert up["plans"] == before["plans"]
assert up["pinned_with_issued_at"] == up["discord_tagged"] == up["pinned_matching_pin"] == M
assert up["unpinned_md5"] == before["unpinned_md5"]
assert n_up >= 1    # Postgres folds identical payloads per transaction: often 1, not M

# The refusal on real data: a second stamp raises before writing; the transaction rolls back.
with engine.connect() as conn, conn.begin() as tx:
    try:
        MIG.apply_upgrade(conn, PINS)
    except RuntimeError as exc:
        print("second upgrade refused:", str(exc)[:80])
    else:
        raise AssertionError("second upgrade did not refuse")
    tx.rollback()

n_down = notifies_during(lambda: migrate(command.downgrade, "v173_002"))
down = snapshot()
print("after downgrade", down, "NOTIFY trades:", n_down)
assert down["head"] == "v173_002"
assert down["pinned_with_issued_at"] == down["discord_tagged"] == 0
assert down["docs_md5"] == before["docs_md5"], "downgrade did not restore the plan docs"
assert down["unpinned_md5"] == before["unpinned_md5"]

migrate(command.upgrade, "v200_001")               # leave the replica at the checkout's head
assert snapshot()["discord_tagged"] == M
print("v200_replica_check: PASS", M, "pins;", before["pinned_null_keys"], "pinned null issued_at keys")
```

- [ ] **Step 3: Run it**

```bash
cd <wt> && python <scratchpad>/v200_replica_check.py <wt> E:/Documents/Private/Projects/Discord-Bot \
  > <scratchpad>/v200_replica_check.txt 2>&1; echo "exit $?"; tail -n 8 <scratchpad>/v200_replica_check.txt
```

Expected: `exit 0` and the last line `v200_replica_check: PASS <M> pins; <K> pinned null issued_at keys`, with `<M>` equal to the dry-run file's `Matched: M`. The output holds counts, md5 digests and the refusal message (plan ids only), never the URL. Any `AssertionError` → stop and report it; do not edit V200-7's revision from this task (a revision defect goes back to V200-7 through the controller).

- [ ] **Step 4: Re-run V200-7's tests**

Run: `python <wt>/scripts/dev/testrun.py file tests/db/test_v200_discord_issued_at.py`
Expected: `0 failed`.

- [ ] **Step 5: Re-check the last PITR drill**

```bash
grep -n "^### Drill" <wt>/docs/deploy/DB_RESTORE.md | tail -n 1
grep -n '"pitr_last_drill"' <wt>/docs/superpowers/results/2026-10-29-v200-prod-reads.md
```

Expected: the newest `### Drill <date>` heading and V200-1's `pitr_last_drill` agree. If they differ, take the later date and name both sources. If V200-1 recorded `null` and `DB_RESTORE.md` has no drill, the deploy note says **no PITR drill on record** in bold; the deploy decision stays the partner's.

- [ ] **Step 6: Append the two sections to the results file**

Append to `docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md`, filled from `<scratchpad>/v200_replica_check.txt`:

```markdown
## Replica verification

Run <date> against `swingbot_prod_replica` in `swing-db` (refreshed by /replicate-prod-db: <verdict, table
count, alembic>), revision file at <wt commit>. The script stayed in the scratchpad; it asserts every line below.

| State | alembic | plans | pinned present | pinned with issued_at | issued_at_source = discord |
|---|---|---|---|---|---|
| before | v173_002 | P | M | 0 | 0 |
| after upgrade | v200_001 | P | M | M | M |
| after downgrade | v173_002 | P | M | 0 | 0 |

- Unpinned plan docs unchanged by upgrade and downgrade (md5 equal).
- Pinned plan docs restored by the downgrade apart from the two fields (md5 equal); K pinned docs held an
  `"issued_at": null` key that the downgrade drops (reads back as None either way).
- A second stamp on the upgraded replica refused before writing: `<first 80 chars of the message>`.
- NOTIFY on channel `trades`: <n_up> during upgrade, <n_down> during downgrade.
- Replica left at `v200_001`.

## Deploy note

Not a plan task: the partner ships v200_001 with the normal deploy (`alembic upgrade head`,
`docs/deploy/DEPLOY_HETZNER.md`). Never generate or edit the revision on the VM.

- Writes: M plan docs gain `issued_at` and `issued_at_source = "discord"`; nothing else changes.
- Last PITR drill: <date> (<source>). Rollback is `scripts/ops/rollback_to.sh` to the second before
  the upgrade ran; note the UTC time before `alembic upgrade head`.
- The `plans` NOTIFY trigger fires once per touched row (channel `trades`); Postgres folds identical
  payloads within the transaction, so the admin UI's SSE stream sees a short burst (<n_up> on the
  replica) and refreshes the trades views. Expected, not an incident.
- Refusals on production: the revision raises (the upgrade stops, nothing written) if any pinned plan
  is missing or already carries `issued_at`. A refusal is a stop to report; never edit the pins on the VM.
- After the deploy: `alembic current` prints `v200_001`; the autopsy coverage line (V200-4) shows
  `discord` = M.
```

- [ ] **Step 7: Commit**

```bash
git -C <wt> add docs/superpowers/results/2026-10-29-v200-backfill-dry-run.md
git -C <wt> commit -m "docs(v200): v200_001 verified up and down on the replica; deploy note"
```
