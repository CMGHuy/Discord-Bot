# v206 Plan 1, part 2b — release, deploy and the after-probe

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md)
**Index:** [`2026-11-05-v206-admin-under-load_0-index.md`](2026-11-05-v206-admin-under-load_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Task V206-13 (index group H). It sits in its own file because part 2 (`_2-client-and-release.md`, V206-7..V206-12) would otherwise pass the 1500-line cap; a task is never split across files. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v206-admin-under-load`; `<main>` is the main tree, `E:/Documents/Private/Projects/Discord-Bot`. No step runs the full suite: CI does after the push.

# Phase F — release and measure

### Task V206-13: Release, deploy, after-probe during a scan, Results

**Model:** sonnet — a scripted release, merge and measurement run with read-only production checks; every figure is generated, none judged.

**Files:**
- Modify: `VERSION.json` (ui patch, bot patch)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (`## Results` → new `### Plan 1 after (committed probe)`, below V206-3's `### Plan 1 baseline (committed probe)`)

**Interfaces:**
- Consumes: every task V206-1..V206-12 committed on the worktree branch; V206-3's baseline section and its output directory `<wt>/.superpowers/probe/v206-baseline/` (run with `--date 2026-11-03`); the probe CLI and `probe.json` shape `{"raw": {meta, pages[], idle}, "report": {meta, label, goal, rounds, endpoints, pages, idle}}` (V206-1b/V206-2); `normalise_endpoint(url)` from `scripts/ops/admin_browser_probe.py`; `/api/v1/health` `sse_streams` (V206-4), read by the probe into `meta.sse_streams`.
- Produces: the deployed release and the after-table the spec's Plan 1 result rests on.

Index § Parallelisation: V206-3's baseline must exist before this task pushes, because it has to measure the code production runs today. Nothing deploys before this task, because the branch merges only here. The after-run must pass **the same `--date 2026-11-03`** as the baseline, and it records `sse_streams`, which the baseline could not (it reads `-` there). Success for this plan (index Goal): the idle-tab rate falls from about 120 to **under 10 requests a minute** during a scan. The heavy-call goals (first heavy call under 2 s p90, no endpoint over 5 s p90) belong to plans 2–4; this task records where they stand and claims nothing for them. A run counts as evidence only with label `scan`. Production is touched read-only, only through `bash scripts/ops/ssh-hetzner.sh`; the deploy itself is push-to-`main` → CI (`docs/deploy/DEPLOY_HETZNER.md`), so nothing is changed by hand on the VM and `mirror-prod` does not apply. Credentials stay inside the probe; never echo `.env` values.

- [ ] **Step 1: Check the preconditions**

```bash
git -C "<wt>" log --oneline main..HEAD
grep -n "^### Plan 1 baseline (committed probe)" "<wt>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md"
git -C "<wt>" status --short
```

Expected: one or more commits for each of V206-1, 1b, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12; the baseline heading found; a clean status. **No baseline heading: stop.** V206-3 has to run first, during a scan, against today's production.

- [ ] **Step 2: Narrow verification of everything this plan touched**

The storage-reaching admin tests need the shared `swing-db` replica: run `/replicate-prod-db` first if no task in this session has. Then, from `<wt>`, one file at a time (never the full suite):

```bash
cd "<wt>" && for t in tests/scripts/test_admin_browser_probe.py tests/admin/test_api_v1_session.py tests/admin/test_api_v1_dashboard.py tests/scanning/test_progress_store_strict.py tests/admin/test_event_broker.py tests/admin/test_event_stream.py tests/scripts/test_build_version_matrix.py; do python scripts/dev/testrun.py file "$t" > "<wt>/.superpowers/v206-$(basename "$t" .py).log" 2>&1 && echo "PASS $t" || echo "FAIL $t"; done
cd "<wt>" && python scripts/dev/complexity_gate.py
node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/api/scan-event-progress.spec.ts --include src/app/api/event-stream.spec.ts --include src/app/stores/connection.store.spec.ts --include src/app/routing/route-refresh.service.spec.ts --include src/app/stores/live.store.spec.ts --include src/app/stores/tape-feed.spec.ts --include src/app/shell/shell.spec.ts --include src/app/workspaces/trades/trade-detail.spec.ts --include src/app/shell/tape/tape.spec.ts --include src/app/stores/system.store.spec.ts
```

Expected: seven `PASS` lines, the complexity gate passes, and the frontend run reports 0 failed. A `FAIL` line: read only that log's failing test names and assertion lines, fix, and rerun that one file alone (`working-conventions.md`).

- [ ] **Step 3: Bump `ui` and `bot` as two release commits**

Both lines change what runs: the SPA (`ui`) and the admin's broker and `/health` (`bot`, index header `Bump: ui patch, bot patch`). Read the current values, never assume them:

```bash
python - "<wt>/VERSION.json" ui <<'EOF'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
path, line = Path(sys.argv[1]), sys.argv[2]
data = json.loads(path.read_text(encoding="utf-8"))
major, minor, patch = (int(x) for x in data[line].split("."))
data[line] = f"{major}.{minor}.{patch + 1}"
data[f"{line}_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(line, data[line])
EOF
```

Expected: `ui <x.y.z+1>`. Check the file's formatting matches the committed one (`git -C "<wt>" diff VERSION.json` shows only the two `ui` lines changing); if the original had no trailing newline or another indent, match it. Commit:

```bash
git -C "<wt>" add VERSION.json
git -C "<wt>" commit -m "release(ui): <new ui> -- admin under load: the scan strip rides the scan event, no polling on scan (v206)"
```

Run the same script with `bot` instead of `ui`, then:

```bash
git -C "<wt>" add VERSION.json
git -C "<wt>" commit -m "release(bot): <new bot> -- admin under load: scan events carry progress, /health reports sse_streams (v206)"
```

- [ ] **Step 4: Regenerate the version history and check it**

The generator walks `git log` for `VERSION.json`, so it runs **after** both release commits:

```bash
cd "<wt>" && python scripts/dev/build_version_matrix.py
cd "<wt>" && python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git -C "<wt>" add swingbot/admin/version_history.json
git -C "<wt>" commit -m "chore(ui,bot): <new ui> / <new bot> -- admin under load: scan progress in the scan event, no scan polling, sse_streams (v206)"
```

Expected: the test passes; `git -C "<wt>" show --stat HEAD` lists only `swingbot/admin/version_history.json`, and its newest pair is the two new versions, never `"commit": "uncommitted"`.

- [ ] **Step 5: Merge into `main` and push**

Invoke the `worktree-lifecycle` skill for the merge: another session may be committing on `main`. Then:

```bash
git -C "<main>" fetch origin
git -C "<main>" status --short --branch
git -C "<main>" log --oneline -1 origin/main
```

Expected: `main` is not behind `origin/main` (pull with `--ff-only` first if it is), and no uncommitted change in `<main>` touches a file this plan changed. Uncommitted files of another session (for example `.claude/settings.local.json`) stay as they are; never stash or reset them.

```bash
git -C "<main>" merge --no-ff 2026-11-05-v206-admin-under-load -m "merge: v206 Plan 1 -- admin under load: probe and polling"
git -C "<main>" push origin main
```

- [ ] **Step 6: Watch the pipeline**

```bash
gh run list --branch main --limit 1 --json databaseId,status,conclusion
```

Then `gh run watch <id> --exit-status` with `run_in_background`, and wait for its exit notification (do not poll). Green: continue. Red: `gh run view <id> --log-failed > <scratchpad>/v206-ci.log`, read only the failing test names and assertion lines, fix each in `<main>` (one file at a time with `testrun.py file`), commit scoped, push, watch again (`working-conventions.md` § Pipeline watch).

- [ ] **Step 7: Confirm production runs the new code**

The deploy follows a green run by itself. Then, read-only:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose ps --format '{{.Image}}' admin"
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -c 'from swingbot.admin.events.broker import Event; print(\"progress\" in Event.__dataclass_fields__)'"
```

Expected: an image reference different from the one V206-3 recorded (keep it as `<tag>`), and `True`. `False` means the deploy has not landed: wait a few minutes and repeat; do not probe the old image.

- [ ] **Step 8: Wait for a scan, then confirm it**

The session scan runs during US hours (15:30–22:00 Berlin; Git Bash has no timezone data, so Berlin is `date -u` plus 1 h in winter).

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin python -c 'from swingbot.core.scanning.runstate import is_scan_running; print(is_scan_running())'"
```

Expected: `True`. If `False`, wait and check again every few minutes; never start the run on `False`.

- [ ] **Step 9: Run the after-probe in the background**

Same date as the baseline. About an hour: run it with `run_in_background` and wait for the exit notification.

```bash
python "<wt>/scripts/ops/admin_browser_probe.py" --date 2026-11-03 --out "<wt>/.superpowers/probe/v206-after" --image-tag "<tag>" > "<wt>/.superpowers/probe/v206-after.log" 2>&1
```

Expected: exit 0 and the last log line `probe: scan run, 36 pages -> ...`. Exit 2 is a failed login (the log names the HTTP status only): fix the cause and rerun from Step 8.

- [ ] **Step 10: Verify the run: label, shape, stream count, no credential**

```bash
python - "<wt>/.superpowers/probe/v206-after" "<main>/.env" <<'EOF'
import json, re, sys
from pathlib import Path
out, env = Path(sys.argv[1]), Path(sys.argv[2])
pattern = re.compile(r"\s*(ADMIN_USERNAME|ADMIN_PASSWORD)\s*=\s*(.*?)\s*$")
values = [m.group(2).strip('"').strip("'") for m in map(pattern.match, env.read_text(encoding="utf-8").splitlines()) if m]
texts = [(out / "probe.json").read_text(encoding="utf-8"), (out / "probe.md").read_text(encoding="utf-8")]
print("credentials absent:", len(values) == 2 and all(v not in t for v in values for t in texts))
report = json.loads(texts[0])["report"]
print("label:", report["label"], "| pages:", len(report["pages"]), "| idle rpm:", report["idle"]["rpm"],
      "| sse_streams:", report["meta"]["sse_streams"])
assert report["label"] == "scan", "not a scan run: record it, then rerun from Step 8 during a scan"
assert len(report["pages"]) == 36
assert isinstance(report["meta"]["sse_streams"], int), "sse_streams missing: is V206-4 deployed?"
EOF
```

Expected: `credentials absent: True`, `label: scan | pages: 36 | idle rpm: <n> | sse_streams: <int>`, no assertion error. The script prints booleans and figures only. A `mixed` or `quiet` run: rename its directory `v206-after-<label>-1`, keep it for Step 12's "Not evidence" line, and rerun from Step 8.

- [ ] **Step 11: Generate the before/after table from the two runs**

No figure is retyped: the table comes from both `probe.json` files, with the probe's own endpoint normaliser.

```bash
python - "<wt>/.superpowers/probe/v206-baseline" "<wt>/.superpowers/probe/v206-after" "<wt>/scripts/ops" > "<wt>/.superpowers/probe/v206-compare.md" <<'EOF'
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[3])
import admin_browser_probe as probe
base, after = (json.loads((Path(d) / "probe.json").read_text(encoding="utf-8")) for d in sys.argv[1:3])
WATCHED = ("/system/scan", "/health", "/live", "/market/tape")

def count(calls, endpoint):
    return sum(1 for call in calls if probe.normalise_endpoint(call["url"]) == endpoint)

def spread(s):
    tail = f"max {s['max']} (thin)" if s["thin"] else f"p90 {s['p90']}, max {s['max']}"
    return f"n {s['n']}, median {s['median']}, {tail}"

def rows(doc):
    report, raw = doc["report"], doc["raw"]
    page_calls = [c for page in raw["pages"] for c in page["calls"]]
    out = {"Label": report["label"],
           "Idle tab, requests per minute": report["goal"]["idle_rpm"],
           "First heavy call per page (ms)": spread(report["goal"]["first_heavy_ms"]),
           "Endpoints over 5 s": ", ".join(report["goal"]["endpoints_over_5s"]) or "none",
           "Open SSE streams at start": "-" if report["meta"].get("sse_streams") is None else report["meta"]["sse_streams"]}
    for name in WATCHED:
        out[f"`{name}` calls, idle hold"] = count(raw["idle"]["calls"], name)
        out[f"`{name}` calls, all pages"] = count(page_calls, name)
    for r in report["rounds"]:
        out[f"Round {r['round']} capped share"] = r["capped_share"]
    return out

b, a = rows(base), rows(after)
print("| Measure | Baseline | After |")
print("|---|---|---|")
for key in b:
    print(f"| {key} | {b[key]} | {a.get(key, '-')} |")
EOF
cat "<wt>/.superpowers/probe/v206-compare.md"
```

Expected: a markdown table of about 17 rows, label `scan` in both columns. If a key is missing (`KeyError`), the report shape differs from V206-1b's contract: fix the script to read the field that exists, never edit `probe.json`.

- [ ] **Step 12: Record the result in the spec**

In `<main>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md`, append after the whole `### Plan 1 baseline (committed probe)` subsection (it is on `main` since the merge):

```markdown
### Plan 1 after (committed probe)

After v206 Plan 1 deployed (ui <new ui>, bot <new bot>), with
`scripts/ops/admin_browser_probe.py` at `<probe_sha>`, against image `<tag>`,
`<berlin_time>` Berlin, `--date 2026-11-03`, 3 rounds × 12 pages, cap 90 s,
quiet 2 s. Label **scan** (every page sampled `running: true`). Open SSE
streams at start: <sse_streams>.

#### Before and after

<the table from v206-compare.md, pasted unchanged>

**Plan 1 goal (idle tab under 10 requests a minute during a scan):** <met | not met>,
<after idle rpm> against <baseline idle rpm>. The heavy-call goals (first heavy
call under 2 s p90, no endpoint over 5 s p90) are plans 2–4's to reach; the
rows above record where they stand after Plan 1.

<the body of the after-run probe.md from "## Goal" to the end, with every "##" heading demoted to "####">
```

Fill `<probe_sha>`, `<berlin_time>`, `<sse_streams>` from the after-run `probe.json` `report.meta`, and the versions from `VERSION.json`. Write `met` only when the after idle rpm is below 10. If it is not met, say so plainly and list which watched endpoint still appears in the idle hold; do not change code here, and tell the partner. Any `mixed`/`quiet` run from Step 10 goes below as `#### Not evidence: <label> run, <berlin_time>` with its Goal lines only.

- [ ] **Step 13: Check the section reads back, then commit on `main`**

```bash
python "<main>/scripts/dev/doc_section.py" "<main>/docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md" "Plan 1 after (committed probe)" | head -30
git -C "<main>" add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git -C "<main>" commit -m "docs(v206): Plan 1 after-probe during a scan -- idle tab <after> rpm vs <baseline> before (V206-13)"
git -C "<main>" push origin main
```

Expected: the provenance paragraph and the `#### Before and after` table print (exit 2 from `doc_section.py` means read the file at `## Results` directly). The push is docs-only; watch its run as in Step 6. Then run `/close-out` for v206 Plan 1 (standing permission, `document-lifecycle.md`).

