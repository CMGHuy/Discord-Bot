# v85 Part 12 — Versions, the stubs, the gallery, and the wave 3 release

Header block, global constraints, waves, parallelisation and exit criteria live
in `2026-09-11-v85-dashboard-shell-redesign_0-index.md`.

**R12-01 … R12-03 are Group W3-BE.** **R12-04 … R12-06 are Group W3-UI.**
**R12-07 runs after the whole UI group, alone** — it edits `gallery.ts`, which
every primitive contributes to. **R12-08 runs last and alone.**

---

## The one place this plan writes into the bot process

R12-01 adds a boot-time marker to `bot.py`. Spec D29 and the plan's global
constraints both allow it and both fence it:

- It writes **one append-only line at startup** and nothing else, ever.
- It touches **no scan, strategy, sizing or exit path**.
- Its failure **degrades to "window unknown"**, never to a crash. A bot that
  refuses to start because a telemetry marker could not be written would be a
  self-inflicted outage caused by a reporting feature.

A task here that finds itself adding a second write, or a marker anywhere but
process start, has exceeded what the spec permits.

---

### Task R12-01: The boot-time deploy marker

**Files:**
- Create: `swingbot/core/infra/deploy_marker.py`
- Modify: `bot.py`
- Modify: `admin_ui.py`
- Create: `tests/infra/test_deploy_marker.py`

**Interfaces:**
- Consumes: `VERSION.json`.
- Produces: `record_boot(component: str) -> None` and
  `read_markers() -> list[dict]`, each marker
  `{"component": "bot" | "admin", "ui": "1.15.2", "bot": "1.7.2",
    "sha": "1cc2089a", "at": "2026-09-11T18:02:11Z"}`. Consumed by R12-02.

- [ ] **Step 1: Verify the events path before writing to it**

Dispatch the `symbol-verifier` subagent: "In this repo, what file path does
`swingbot/admin/events/stream.py` read events from, and what function appends to
it?" Use that path and that appender. **Do not create a new JSONL file** — the
plan's global constraints forbid a new top-level data file, and this marker is
an event.

- [ ] **Step 2: Write the failing test**

Create `tests/infra/test_deploy_marker.py`:

```python
import json

import pytest

from swingbot.core.infra import deploy_marker as dm


def test_a_boot_appends_one_marker(events_path):
    dm.record_boot("bot")
    assert len(dm.read_markers()) == 1


def test_the_marker_carries_both_version_lines_and_the_component(events_path):
    dm.record_boot("bot")
    m = dm.read_markers()[0]
    assert m["component"] == "bot"
    assert m["ui"] and m["bot"]
    assert m["at"].endswith("Z")


def test_two_boots_append_rather_than_overwrite(events_path):
    dm.record_boot("bot")
    dm.record_boot("admin")
    assert [m["component"] for m in dm.read_markers()] == ["bot", "admin"]


def test_a_write_failure_does_not_raise(events_path, monkeypatch):
    monkeypatch.setattr(dm, "_append", lambda _: (_ for _ in ()).throw(OSError("read-only")))
    dm.record_boot("bot")  # must not raise


def test_an_unreadable_log_yields_no_markers_rather_than_raising(events_path):
    events_path.write_text("{not json\n")
    assert dm.read_markers() == []


def test_a_malformed_line_is_skipped_not_fatal(events_path):
    dm.record_boot("bot")
    with events_path.open("a") as fh:
        fh.write("{broken\n")
    dm.record_boot("admin")
    assert len(dm.read_markers()) == 2


def test_non_marker_events_are_ignored(events_path):
    with events_path.open("a") as fh:
        fh.write(json.dumps({"type": "scan_complete"}) + "\n")
    dm.record_boot("bot")
    assert len(dm.read_markers()) == 1
```

- [ ] **Step 3: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/infra/test_deploy_marker.py
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 4: Write the module and call it at both entry points**

Create `swingbot/core/infra/deploy_marker.py`. `record_boot` reads
`VERSION.json`, resolves the short sha (`git rev-parse --short HEAD`, falling
back to the `SWINGBOT_SHA` environment variable, then to `None` — a container
has no git), and appends one event of `type: "deploy"`.

**The entire body of `record_boot` is inside one `try/except Exception`.** The
except logs at debug and returns. Add the call as the first statement of
`bot.py`'s and `admin_ui.py`'s startup, before any scheduling.

- [ ] **Step 5: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/infra/test_deploy_marker.py
```

Expected: PASS.

- [ ] **Step 6: Confirm the bot still starts with the events path unwritable**

```bash
python -c "from swingbot.core.infra import deploy_marker as dm; dm.record_boot('bot'); print('ok')"
```

Expected: `ok`, with or without a writable path.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/infra/deploy_marker.py bot.py admin_ui.py tests/infra/test_deploy_marker.py
git commit -m "feat(infra): append-only boot deploy marker, fail-degrading (v85 D29)"
```

---

### Task R12-02: Release windows and their telemetry

**Files:**
- Create: `swingbot/admin/release_windows.py`
- Create: `tests/admin/test_release_windows.py`

**Interfaces:**
- Consumes: `read_markers()` from R12-01, the log and scan-telemetry sources
  `api_v1/system.py` already reads.
- Produces:
  - `windows() -> list[dict]` — `{"component", "version", "sha", "from", "to"}`,
    newest first, `to` being `None` for the current window.
  - `telemetry_for(window) -> dict` — `{"uptime_pct", "error_rate",
    "median_scan_sec", "n_days"}`, every value nullable.

  Consumed by R12-03.

**A window runs from one marker to the next marker for the same component.**
Not to the next marker of any component: the bot and admin are deployed from one
image but restart independently, and merging their markers would cut every
window in half.

**Backfill is a separate, clearly-labelled path.** Releases that predate R12-01
have no markers. `windows()` reconstructs them from git tags and `VERSION.json`
history and marks each `"source": "backfill"`, so the page can say the
telemetry is inferred rather than measured. An inferred figure presented as a
measurement is the failure this field prevents.

- [ ] **Step 1: Write the failing test**

```python
def test_a_window_runs_to_the_next_marker_for_the_same_component(markers):
    markers([
        {"component": "bot", "bot": "1.7.1", "at": "2026-09-01T00:00:00Z"},
        {"component": "admin", "ui": "1.15.1", "at": "2026-09-03T00:00:00Z"},
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"},
    ])
    bot_windows = [w for w in windows() if w["component"] == "bot"]
    assert bot_windows[-1]["to"] == "2026-09-05T00:00:00Z"


def test_the_newest_window_is_open(markers):
    markers([{"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"}])
    assert windows()[0]["to"] is None


def test_windows_are_newest_first(markers):
    markers([
        {"component": "bot", "bot": "1.7.1", "at": "2026-09-01T00:00:00Z"},
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"},
    ])
    assert [w["version"] for w in windows() if w["component"] == "bot"] == ["1.7.2", "1.7.1"]


def test_a_restart_on_the_same_version_does_not_open_a_new_window(markers):
    markers([
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"},
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-06T00:00:00Z"},
    ])
    assert len([w for w in windows() if w["component"] == "bot"]) == 1


def test_releases_without_markers_are_backfilled_and_labelled(markers, git_tags):
    markers([])
    git_tags([("v1.7.0", "2026-08-01T00:00:00Z")])
    assert windows()[0]["source"] == "backfill"


def test_a_measured_window_is_not_labelled_backfill(markers):
    markers([{"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"}])
    assert windows()[0]["source"] == "marker"


def test_telemetry_is_null_rather_than_zero_for_a_window_with_no_data(markers):
    markers([{"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"}])
    t = telemetry_for(windows()[0])
    assert t["median_scan_sec"] is None
    assert t["n_days"] is not None


def test_error_rate_is_errors_over_total_events_in_the_window(markers, log_events):
    markers([{"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"}])
    log_events(errors=2, total=100, at="2026-09-06T00:00:00Z")
    assert telemetry_for(windows()[0])["error_rate"] == pytest.approx(0.02)


def test_events_outside_the_window_do_not_count(markers, log_events):
    markers([
        {"component": "bot", "bot": "1.7.1", "at": "2026-09-01T00:00:00Z"},
        {"component": "bot", "bot": "1.7.2", "at": "2026-09-05T00:00:00Z"},
    ])
    log_events(errors=50, total=50, at="2026-09-02T00:00:00Z")
    current = [w for w in windows() if w["version"] == "1.7.2"][0]
    assert telemetry_for(current)["error_rate"] in (None, 0.0)
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_release_windows.py
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the module**

Group markers by component, collapse consecutive same-version markers into one
window, and close each window at the next version change for that component.
Backfill from git tags for versions with no marker. `telemetry_for` filters the
existing log and scan-telemetry sources to `[from, to)`.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_release_windows.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/release_windows.py tests/admin/test_release_windows.py
git commit -m "feat(versions): release windows and their telemetry (v85 D29)"
```

---

### Task R12-03: Provenance, and both blocks on `GET /versions`

**Files:**
- Modify: `swingbot/admin/api_v1/versions.py:55-120`
- Test: `tests/admin/test_api_versions.py`

**Interfaces:**
- Consumes: R12-02's `windows` and `telemetry_for`, and `git log`.
- Produces: each release on the existing payload widened with

```json
"provenance": {"commit_range": "8479a909..1cc2089a", "commits": 22,
               "spec": "docs/superpowers/specs/2026-09-11-v85-...-design.md",
               "changelog": ["..."]},
"telemetry": {"uptime_pct": 99.98, "error_rate": 0.0002,
              "median_scan_sec": 41.7, "n_days": 12, "source": "marker"}
```

Consumed by R12-05.

**Provenance comes from git, not from a hand-maintained file.** The commit range
is between release tags; the spec path is grepped out of the range's commit
messages, which in this repo name their plan. A release with no tag reports
`null` for the range rather than guessing one.

- [ ] **Step 1: Write the failing test**

```python
def test_each_release_carries_provenance_and_telemetry(client, releases):
    releases(["1.7.2", "1.7.1"])
    row = client.get("/api/v1/versions").get_json()["releases"][0]
    assert "provenance" in row and "telemetry" in row


def test_the_commit_range_is_between_release_tags(client, releases):
    releases(["1.7.2", "1.7.1"])
    row = client.get("/api/v1/versions").get_json()["releases"][0]
    assert ".." in row["provenance"]["commit_range"]


def test_an_untagged_release_reports_a_null_range_rather_than_guessing(client, releases):
    releases(["1.7.3"], tagged=False)
    row = client.get("/api/v1/versions").get_json()["releases"][0]
    assert row["provenance"]["commit_range"] is None


def test_telemetry_says_whether_it_was_measured_or_inferred(client, releases):
    releases(["1.7.2"])
    assert client.get("/api/v1/versions").get_json()["releases"][0]["telemetry"]["source"] \
        in ("marker", "backfill")


def test_the_existing_payload_is_unchanged(client, releases):
    releases(["1.7.2"])
    body = client.get("/api/v1/versions").get_json()
    assert "releases" in body


def test_a_git_failure_degrades_provenance_not_the_endpoint(client, releases, monkeypatch):
    releases(["1.7.2"])
    monkeypatch.setattr("swingbot.admin.api_v1.versions._git",
                        lambda *a: (_ for _ in ()).throw(OSError("no git")))
    resp = client.get("/api/v1/versions")
    assert resp.status_code == 200
    assert resp.get_json()["releases"][0]["provenance"]["commit_range"] is None
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_versions.py
```

Expected: FAIL.

- [ ] **Step 3: Wire the endpoint**

Add both blocks. Wrap every git call in a helper that returns `None` on
failure: a container without git history must still serve this page.

- [ ] **Step 4: Run the tests and confirm they pass**

```bash
python scripts/dev/testrun.py file tests/admin/test_api_versions.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/versions.py tests/admin/test_api_versions.py
git commit -m "feat(api): release provenance and telemetry on GET /versions (v85 D28)"
```

---

### Task R12-04: The timeline page

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Test: `frontend/src/app/workspaces/versions/versions.spec.ts`

**Interfaces:**
- Consumes: `sb-timeline` (R2-05), `sb-control-bar` (R2-02), R12-03's payload.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```typescript
it('renders the releases on the timeline, newest first', () => {
  const titles = entryTitles({ releases: [{ version: '2.14.0' }, { version: '2.13.1' }] });
  expect(titles).toEqual(['v2.14.0', 'v2.13.1']);
});

it('marks the current release of each component', () => {
  const el = render({ releases: [
    { version: '2.14.0', component: 'ui', current: true },
    { version: '1.6.3', component: 'bot', current: true },
  ]}).nativeElement as HTMLElement;
  expect(el.querySelectorAll('.badge').length).toBe(2);
});

it('offers the component filter in the control bar', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelector('sb-control-bar select.component')).not.toBeNull();
});

it('filters the timeline to one component', () => {
  const f = render({ releases: [
    { version: '2.14.0', component: 'ui' }, { version: '1.6.3', component: 'bot' },
  ]});
  selectComponent(f, 'bot');
  expect(entryTitles(f)).toEqual(['v1.6.3']);
});

it('keeps the existing component matrix below the timeline', () => {
  expect((render().nativeElement as HTMLElement).querySelector('.component-matrix')).not.toBeNull();
});

it('renders no in-page heading', () => {
  expect((render().nativeElement as HTMLElement).querySelector('h1')).toBeNull();
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/versions/versions.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build the page**

Timeline as the main column, the existing component matrix retained beneath it.
The two "Current UI / Current Bot" chips sheet 2 shows are rendered from the
payload's current flags.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/versions/versions.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/versions
git commit -m "feat(versions): release timeline with a component filter (v85 D28)"
```

---

### Task R12-05: Provenance and telemetry cards

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Test: `frontend/src/app/workspaces/versions/versions.spec.ts`

**Interfaces:**
- Consumes: R12-03's two blocks, `sb-stat-tile` (R2-01).
- Produces: nothing new.

**The `source` field is not optional chrome.** A backfilled window's telemetry
is inferred from tag dates, not measured from markers, and a page that renders
the two identically is claiming a measurement it does not have.

- [ ] **Step 1: Write the failing test**

```typescript
it('shows the commit range and commit count', () => {
  const card = provenanceCard({ commit_range: '8479a909..1cc2089a', commits: 22 });
  expect(card.textContent).toContain('8479a909..1cc2089a');
  expect(card.textContent).toContain('22');
});

it('links the originating spec when there is one', () => {
  const card = provenanceCard({ spec: 'docs/superpowers/specs/x-design.md' });
  expect(card.querySelector('a')!.textContent).toContain('x-design.md');
});

it('says no range rather than showing an empty one', () => {
  expect(provenanceCard({ commit_range: null }).textContent).toContain('No tagged range');
});

it('shows uptime, error rate and scan duration', () => {
  const card = telemetryCard({ uptime_pct: 99.98, error_rate: 0.0002, median_scan_sec: 41.7 });
  expect(card.textContent).toContain('99.98');
  expect(card.textContent).toContain('41.7');
});

it('marks inferred telemetry as inferred', () => {
  expect(telemetryCard({ source: 'backfill' }).textContent).toContain('inferred');
});

it('does not mark measured telemetry as inferred', () => {
  expect(telemetryCard({ source: 'marker' }).textContent).not.toContain('inferred');
});

it('renders a window with no telemetry as unknown rather than as perfect uptime', () => {
  const card = telemetryCard({ uptime_pct: null, error_rate: null, median_scan_sec: null });
  expect(card.textContent).not.toContain('100');
  expect(card.textContent).toContain('—');
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/versions/versions.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build both cards**

Render them into the timeline's projected `body` slot. Telemetry figures use
`sb-stat-tile` with `n_days` as the sample.

- [ ] **Step 4: Run the spec and the guard**

```bash
cd frontend && npx ng test --include src/app/workspaces/versions/versions.spec.ts
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: versions spec PASSES; the guard no longer names any versions file.

- [ ] **Step 5: Screenshot at both widths**

Screenshot `/versions` at 1440px and 390px. Confirm at 390px the cards stack
under each entry rather than squeezing beside it.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/versions
git commit -m "feat(versions): provenance and telemetry cards, inferred marked as inferred (v85 D28)"
```

---

### Task R12-06: The Research and Reports stubs

**Files:**
- Create: `frontend/src/app/workspaces/stubs/planned-workspace.ts`
- Create: `frontend/src/app/workspaces/stubs/planned-workspace.spec.ts`
- Create: `frontend/src/app/workspaces/stubs/research.routes.ts`
- Create: `frontend/src/app/workspaces/stubs/reports.routes.ts`
- Modify: `frontend/src/app/app.routes.ts`
- Modify: `frontend/src/app/shell/shell.html`
- Modify: `swingbot/admin/spa.py`
- Test: `frontend/src/app/app.routes.spec.ts`

**Interfaces:**
- Consumes: the route title/subtitle mechanism from R1-04.
- Produces: two routes, `/research` and `/reports`, both `loadComponent`.

**An honest stub, not a blank page** (spec D24). Each names what is planned for
it and links to the surface that serves the need today: Research → Ticker
detail, Reports → Analytics and the CSV export. The nav must not advertise a
dead end.

**`spa.py` needs both paths in `WORKSPACES`**, or the server will not serve
`index.html` for a deep link to either — the same reason `cockpit` is still
listed there.

- [ ] **Step 1: Write the failing test**

```typescript
// planned-workspace.spec.ts
it('names what is planned for the page', () => {
  const el = render({ planned: 'A symbol research desk' });
  expect(el.textContent).toContain('A symbol research desk');
});

it('links to the surface that serves the need today', () => {
  const el = render({ insteadLabel: 'Ticker detail', insteadLink: '/watchlist' });
  expect(el.querySelector('a')!.getAttribute('href')).toContain('/watchlist');
});

it('says plainly that it is not built yet', () => {
  expect(render().textContent).toContain('not built yet');
});

it('does not render a disabled control that suggests it might work', () => {
  expect(render().querySelector('button[disabled]')).toBeNull();
});
```

```typescript
// app.routes.spec.ts
it('routes /research and /reports to their stubs', () => {
  expect(paths()).toContain('research');
  expect(paths()).toContain('reports');
});

it('guards both like every other workspace', () => {
  for (const p of ['research', 'reports']) {
    expect(routeFor(p).canMatch).toBeDefined();
  }
});

it('gives both a title and a subtitle for the top bar', () => {
  for (const p of ['research', 'reports']) {
    expect(routeFor(p).data?.title).toBeTruthy();
    expect(routeFor(p).data?.subtitle).toBeTruthy();
  }
});
```

- [ ] **Step 2: Run them to make sure they fail**

```bash
cd frontend && npx ng test --include src/app/app.routes.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Build the stub, the routes and the nav entries**

One parameterised component, two route files. Add both to the nav's second
group. Add both paths to `WORKSPACES` in `swingbot/admin/spa.py`.

- [ ] **Step 4: Run both specs and confirm they pass**

```bash
cd frontend && npx ng test --include src/app/app.routes.spec.ts
cd frontend && npx ng test --include src/app/workspaces/stubs/planned-workspace.spec.ts
```

Expected: both PASS.

- [ ] **Step 5: Confirm a deep link is served**

With the admin running, request `/research` directly (not via in-app
navigation). Expected: the SPA loads rather than a 404.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/workspaces/stubs frontend/src/app/app.routes.ts frontend/src/app/app.routes.spec.ts frontend/src/app/shell/shell.html swingbot/admin/spa.py
git commit -m "feat(nav): honest Research and Reports stubs (v85 D24)"
```

---

### Task R12-07: The new primitives in the `/ui` gallery

**Files:**
- Modify: `frontend/src/app/workspaces/gallery/gallery.ts`
- Test: `frontend/src/app/workspaces/gallery/gallery.spec.ts`

**Interfaces:**
- Consumes: all seven new primitives — `sb-stat-tile`, `sb-control-bar`,
  `sb-gauge`, `sb-matrix`, `sb-timeline`, `sb-freshness`, `sb-date-range`.
- Produces: nothing new.

**Run this alone.** Every primitive task would otherwise contend for this one
file.

- [ ] **Step 1: Write the failing test**

```typescript
it('exhibits every primitive added by v85', () => {
  const el = render().nativeElement as HTMLElement;
  for (const sel of ['sb-stat-tile', 'sb-control-bar', 'sb-gauge', 'sb-matrix',
                     'sb-timeline', 'sb-freshness', 'sb-date-range']) {
    expect(el.querySelector(sel)).not.toBeNull();
  }
});

it('shows each states-bearing primitive in its edge states', () => {
  const el = render().nativeElement as HTMLElement;
  expect(el.querySelectorAll('sb-stat-tile .thin').length).toBeGreaterThan(0);
  expect(el.querySelectorAll('sb-gauge .over').length).toBeGreaterThan(0);
  expect(el.querySelectorAll('sb-freshness .stale').length).toBeGreaterThan(0);
  expect(el.querySelectorAll('sb-matrix .missing').length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run it to make sure it fails**

```bash
cd frontend && npx ng test --include src/app/workspaces/gallery/gallery.spec.ts
```

Expected: FAIL.

- [ ] **Step 3: Add the exhibits**

One section per primitive, following the gallery's existing structure. Show the
edge states as well as the ordinary one — a gallery that only shows the happy
path is where a thin-sample or stale treatment quietly rots.

- [ ] **Step 4: Run the spec and confirm it passes**

```bash
cd frontend && npx ng test --include src/app/workspaces/gallery/gallery.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/workspaces/gallery
git commit -m "docs(ui): exhibit the v85 primitives and their edge states in /ui"
```

---

# Phase 2 — Wave 3 verification and release

### Task R12-08: Wave 3 — the guard turns green, full suite, release

**Files:**
- Modify: `VERSION.json`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: every task in the plan.
- Produces: the final release.

- [ ] **Step 1: Turn the consistency guard green**

```bash
cd frontend && npx ng test --include src/app/workspaces/workspace-consistency.spec.ts
```

Expected: **PASS, naming no file.** If it still names one, fix that workspace
here — the guard is the plan's exit criterion 1 and it is not waived.

- [ ] **Step 2: Run the frontend suite**

```bash
cd frontend && npx ng test
```

Expected: PASS, with no deliberately-failing spec left anywhere.

- [ ] **Step 3: Run the backend suite**

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed` and `0 xfailed`. Dispatch the `test-runner` subagent.

- [ ] **Step 4: Walk every exit criterion in the index**

Open `_0-index.md`'s exit criteria and check all twelve by hand, naming the
evidence for each. A criterion you cannot evidence is not met.

- [ ] **Step 5: Screenshot all twelve routes at both widths**

Dashboard, Trades, Trade detail, Watchlist, Ticker detail, Risk, Analytics,
Calendar, System, Versions, Research, Reports — 1440px and 390px each.

- [ ] **Step 6: Verify the deploy marker on the real deployment**

After deploying, confirm both containers appended a marker and that Versions
shows the new release with `source: "marker"` rather than `"backfill"`.

- [ ] **Step 7: Bump the version**

Read `VERSION.json` **now**. Bump `ui` one minor and `bot` one patch.

- [ ] **Step 8: Commit, merge and close the plan out**

```bash
git add VERSION.json CHANGELOG.md
git commit -m "release(ui,bot): <resolved versions> -- Analytics, Calendar, System and Versions redesign"
```

Before merging, check for other live sessions on this tree. Then move the plan
and its spec to `docs/superpowers/plans/implemented/` and
`docs/superpowers/specs/implemented/`, and append the final entry to
`.superpowers/sdd/progress.md`.

- [ ] **Step 9: Mirror anything changed on production back into the repo**

If any fix or config change was made directly on the Hetzner VM during this
plan, mirror it into the repo and commit it. The task is not done until that
is true.
