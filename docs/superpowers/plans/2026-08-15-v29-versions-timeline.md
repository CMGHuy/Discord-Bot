# v29 — Versions Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.3.1 · bot 1.1.2
Bump: `ui minor (1.3.x → 1.4.0)` · `bot none`
Spec: `docs/superpowers/specs/2026-08-15-v28-versions-timeline-design.md`
Blocked on: nothing. Touches no file that `v25-trade-chart` or `v27-repo-restructure`
owns — but **v27 moves `scripts/` and `tests/`**, so if v27 lands first, every path
below gains its new prefix. Check `git log --oneline -5` before starting.

**Goal:** Replace the ui×bot matrix with an N-component release timeline — a
full-history strip over a paginated change stream — and make adding a component a
one-key edit to `VERSION.json`.

**Architecture:** Nine sequential tasks in four phases. The payload is a chain
(generator → API → store → component), so each task consumes the previous task's
output; there is no wide parallel group. Phases 1–2 are Python and end with the
frozen file regenerated and the endpoint serving the new shape. Phases 3–4 are
Angular. The old matrix keeps working until Task 7 replaces it, so every commit
before that is independently green.

**Tech Stack:** Python 3.11+, pytest, Flask; Angular 21 signals, `@ngrx/signals`,
vitest.

## Global Constraints

- **`VERSION.json`'s format does not change.** Adding a component is adding a key.
- **A component may never be named `<something>_updated`.** The discovery filter
  excludes those as timestamp stamps, and such a component would silently never
  appear. Comment this at the filter.
- **The "release missing a component" guard is at-least-one, never all.** Requiring
  every component deletes all history predating a newly added one.
- **`basis` is rendered verbatim.** Never paraphrase it, never relabel a pair
  "tested" or "supported".
- **Releases are oldest-first on the wire, newest-first on screen.** Exactly one
  reversal, in the store.
- **`--date=short` means day resolution.** Same-day releases are real (four on
  2026-08-14, three on 2026-08-15) and must not collapse to zero width.
- Run the suite via `python scripts/dev/testrun.py file <path>` while iterating and
  `python scripts/dev/testrun.py full` at the gate — never raw pytest for a full run.
- Frontend tests run via `npx ng test`, never `npx vitest run` (the latter loses
  the jsdom environment and every file errors with `document is not defined`).
- **Never edit files under `.claude/worktrees/`** from this working tree.

---

# Phase 1 — The generator

## Parallelisation

**Sequential throughout.** Task 2 consumes the state shape Task 1 produces, and
Task 3 regenerates the file Task 2 defines. Nothing here is parallelisable, and
saying so is worth as much as a wide group: it stops the next session re-deriving
the dependency graph.

## Task 1: Component discovery and a generic state walk

**Files:**
- Modify: `scripts/dev/build_version_matrix.py:50-97` (`_states`), add `_components`
- Test: `tests/scripts/test_build_version_matrix.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `_components(doc: dict) -> list[str]`; `_states() -> list[dict]` where
  each state is `{"sha": str, "date": str, "subject": str, "versions": dict[str, str]}`.
  Task 2 consumes `versions` as a dict, replacing today's flat `ui`/`bot` keys.

- [ ] **Step 1: Write the failing tests**

```python
def test_components_are_every_key_that_is_not_a_timestamp():
    doc = {"ui": "1.3.1", "bot": "1.1.2",
           "ui_updated": "2026-08-15 11-58-58", "bot_updated": "2026-08-07 20-59-24"}
    assert bvm._components(doc) == ["ui", "bot"]


def test_a_new_component_needs_no_code_change():
    """The whole interface for adding a component is a key in VERSION.json."""
    doc = {"ui": "1.3.1", "bot": "1.1.2", "worker": "0.2.0", "ui_updated": "x"}
    assert bvm._components(doc) == ["ui", "bot", "worker"]


def test_a_component_named_like_a_stamp_is_invisible():
    """Documents the trap rather than fixing it: `_updated` is reserved."""
    assert bvm._components({"ui": "1.0.0", "cache_updated": "0.1.0"}) == ["ui"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/scripts/test_build_version_matrix.py -k components -v`
Expected: FAIL — `AttributeError: module 'build_version_matrix' has no attribute '_components'`

- [ ] **Step 3: Add `_components`**

```python
def _components(doc: dict) -> list[str]:
    """Component keys in a VERSION.json document, in file order.

    Every key that is not a `*_updated` stamp. This is the ENTIRE interface for
    adding a component: put a key in VERSION.json and it appears here, in the
    payload, and on the admin page. No code change, no migration.

    The cost of that convenience: a component may never be named
    `<something>_updated`. It would be filtered out here and simply never
    appear, with no error raised anywhere -- which is why this is written down
    rather than left to be rediscovered.
    """
    return [k for k in doc if not k.endswith("_updated")]
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/scripts/test_build_version_matrix.py -k components -v`
Expected: 3 passed

- [ ] **Step 5: Write the failing test for the generic state walk**

```python
def test_a_release_missing_one_component_is_kept_not_skipped(monkeypatch):
    """The guard is at-least-one. Requiring EVERY component would delete all
    history predating a component the day someone adds one."""
    blobs = {
        "aaaaaaa1": '{"ui": "1.0.0", "bot": "1.0.0"}',
        "aaaaaaa2": '{"ui": "1.1.0", "bot": "1.0.0", "worker": "0.1.0"}',
    }
    _fake_git(monkeypatch, blobs)
    states = bvm._states()
    assert len(states) == 2, "the pre-worker release must survive"
    assert states[0]["versions"] == {"ui": "1.0.0", "bot": "1.0.0"}
    assert "worker" not in states[0]["versions"]


def test_a_release_with_no_components_at_all_is_skipped(monkeypatch):
    _fake_git(monkeypatch, {"aaaaaaa1": '{"ui_updated": "x"}',
                            "aaaaaaa2": '{"ui": "1.0.0"}'})
    assert [s["versions"] for s in bvm._states()] == [{"ui": "1.0.0"}]
```

Add this helper at the top of the test file — the existing tests monkeypatch
`_states` wholesale, but these two need the walk itself:

```python
def _fake_git(monkeypatch, blobs: dict[str, str]):
    """Stub `subprocess.run` for both calls the walk makes: the log, then one
    `git show` per commit. Keys of `blobs` are shas, in log order."""
    log = "\n".join(f"{sha}0000000|2026-07-{i+1:02d}|subject {i}"
                    for i, sha in enumerate(blobs))

    class R:
        def __init__(self, stdout, code=0):
            self.stdout, self.returncode = stdout, code

    def fake_run(cmd, **kwargs):
        if cmd[1] == "log":
            return R(log)
        sha = cmd[2].split(":")[0][:8]
        return R(blobs.get(sha, ""), 0 if sha in blobs else 1)

    monkeypatch.setattr(bvm.subprocess, "run", fake_run)
    monkeypatch.setattr(bvm.Path, "exists", lambda self: False)
```

- [ ] **Step 6: Run to verify they fail**

Run: `python -m pytest tests/scripts/test_build_version_matrix.py -k state -v`
Expected: FAIL — `KeyError: 'versions'` (states still carry flat `ui`/`bot`)

- [ ] **Step 7: Generalise `_states`**

Replace lines 72-76 (the `ui, bot = ...` guard and append) with:

```python
        versions = {k: str(v) for k, v in doc.items()
                    if not k.endswith("_updated") and v}
        # AT LEAST ONE, never all. A release predating a component simply does
        # not carry its key; requiring every known component here would drop
        # every historical release the first time anyone extends VERSION.json.
        if not versions:
            continue
        states.append({"sha": sha[:8], "date": date, "subject": subject,
                       "versions": versions})
```

And replace lines 90-96 (the working-tree append) with:

```python
        live_versions = {k: str(v) for k, v in live.items()
                         if not k.endswith("_updated") and v}
        if live_versions and (not states or states[-1]["versions"] != live_versions):
            states.append({
                "sha": "uncommitted",
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "subject": "working tree", "versions": live_versions,
            })
```

- [ ] **Step 8: Run the whole generator test file**

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: the `_components` and `_states` tests pass; the `build()` tests FAIL
(they read `doc["pairs"]`, which Task 2 replaces). That is the expected
intermediate state — do not fix them here.

- [ ] **Step 9: Commit**

```bash
git add scripts/dev/build_version_matrix.py tests/scripts/test_build_version_matrix.py
git commit -m "feat(versions): discover components from VERSION.json keys

The generator hardcoded ui and bot and skipped any release missing either.
Components now come from the file's own keys, so adding one is a one-key
edit -- and the guard becomes at-least-one, because requiring every known
component would delete all history predating a newly added one."
```

## Task 2: The release payload and `changed` derivation

**Files:**
- Modify: `scripts/dev/build_version_matrix.py:100-158` (`build`, `main`)
- Test: `tests/scripts/test_build_version_matrix.py`

**Interfaces:**
- Consumes: `_states()` from Task 1.
- Produces: `build() -> dict` with keys `generated_at`, `basis`, `components`,
  `current`, `releases`. Each release is
  `{"date": str, "last_seen": str, "commit": str, "subject": str,
    "versions": dict[str, str | None], "changed": list[str]}`.
  Task 4 serves this; Task 5 types it.

- [ ] **Step 1: Write the failing tests**

```python
def test_build_derives_components_releases_and_changed(monkeypatch):
    states = [
        {"sha": "aaaaaaa1", "date": "2026-07-01", "subject": "a",
         "versions": {"ui": "1.0.0", "bot": "1.0.0"}},
        {"sha": "aaaaaaa2", "date": "2026-07-02", "subject": "b",
         "versions": {"ui": "1.0.0", "bot": "1.0.1"}},
        # Repeat of the whole tuple: extends last_seen, does not add a release.
        {"sha": "aaaaaaa3", "date": "2026-07-03", "subject": "c",
         "versions": {"ui": "1.0.0", "bot": "1.0.1"}},
        # A component appearing for the first time, mid-history.
        {"sha": "aaaaaaa4", "date": "2026-07-04", "subject": "d",
         "versions": {"ui": "1.0.0", "bot": "1.0.1", "worker": "0.1.0"}},
    ]
    monkeypatch.setattr(bvm, "_states", lambda: states)
    doc = bvm.build()

    assert doc["components"] == ["ui", "bot", "worker"], "first-appearance order"
    assert doc["current"] == {"ui": "1.0.0", "bot": "1.0.1", "worker": "0.1.0"}
    assert len(doc["releases"]) == 3, "the repeated tuple must not add a release"

    first, second, third = doc["releases"]
    assert first["changed"] == ["ui", "bot"], "everything is new at the first release"
    assert second["changed"] == ["bot"]
    assert second["last_seen"] == "2026-07-03", "the repeat extended it"
    assert third["changed"] == ["worker"]


def test_a_component_is_null_before_it_existed(monkeypatch):
    """null distinguishes 'did not exist yet' from 'unchanged' -- the strip
    draws those differently and cannot recover the difference from equality."""
    monkeypatch.setattr(bvm, "_states", lambda: [
        {"sha": "a1", "date": "2026-07-01", "subject": "a",
         "versions": {"ui": "1.0.0"}},
        {"sha": "a2", "date": "2026-07-02", "subject": "b",
         "versions": {"ui": "1.0.0", "worker": "0.1.0"}},
    ])
    releases = bvm.build()["releases"]
    assert releases[0]["versions"] == {"ui": "1.0.0", "worker": None}
    assert "worker" not in releases[0]["changed"], "absent is not changed"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/scripts/test_build_version_matrix.py -k "derives or null" -v`
Expected: FAIL — `KeyError: 'components'`

- [ ] **Step 3: Rewrite `build`**

Replace the whole body of `build()` (lines 100-150) with:

```python
def build() -> dict:
    states = _states()
    if not states:
        raise SystemExit(f"no committed states of {TRACKED} found — is this a git checkout?")

    # First-appearance order, oldest release first. NOT sorted: lane order on
    # the page should be stable as components are added, and alphabetical order
    # re-sorts every existing lane the day someone adds `api`. Appending only.
    components: list[str] = []
    for st in states:
        for name in st["versions"]:
            if name not in components:
                components.append(name)

    # One entry per DISTINCT tuple. `changed` is derived here rather than in the
    # SPA because it is a property of the sequence: a client would recompute it
    # on every render, would need the whole ordered list in hand to draw any
    # single row (breaking pagination), and would have to special-case the
    # first release in a second place.
    releases: list[dict] = []
    previous: dict[str, str | None] = {}
    for st in states:
        versions = {c: st["versions"].get(c) for c in components}
        changed = [c for c in components
                   if versions[c] is not None and versions[c] != previous.get(c)]
        if releases and not changed:
            releases[-1]["last_seen"] = st["date"]     # same tuple, still current
            continue
        releases.append({
            "date": st["date"], "last_seen": st["date"],
            "commit": st["sha"], "subject": st["subject"],
            "versions": versions, "changed": changed,
        })
        previous = versions

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "basis": "Versions observed together in VERSION.json. Both containers "
                 "build from one image, so a pair here shipped as a unit. This "
                 "is a record of what was released together, not a statement "
                 "that the pair was tested.",
        "components": components,
        "current": {c: v for c, v in releases[-1]["versions"].items() if v is not None},
        "releases": releases,
    }
```

- [ ] **Step 4: Update `main`'s summary line**

```python
def main() -> None:
    doc = build()
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: "
          f"{len(doc['components'])} components, "
          f"{len(doc['releases'])} releases", file=sys.stderr)
```

- [ ] **Step 5: Delete the now-dead `_semver_key` call sites, keep the function**

`ui_versions`/`bot_versions`/`ranges` are gone, so nothing calls `_semver_key`
any more. **Keep the function and its three tests** — Task 6 needs semver
ordering for the version filter, and deleting a tested pure helper to re-add it
two tasks later is churn. Add one line above it:

```python
# Retained for the SPA-side version filter (v29 Task 6); no caller in this
# module since the cross-product fields were removed.
```

- [ ] **Step 6: Run the generator tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: the old `test_build_derives_pairs_and_ranges` FAILS (it asserts
`doc["pairs"]`). Delete that test — it asserts a payload that no longer exists,
and its behaviour is covered by `test_build_derives_components_releases_and_changed`.
`test_the_committed_file_matches_the_current_generator` also fails; Task 3 fixes it.

- [ ] **Step 7: Commit**

```bash
git add scripts/dev/build_version_matrix.py tests/scripts/test_build_version_matrix.py
git commit -m "feat(versions): emit releases with derived changed, not a cross-product

ui_versions/bot_versions/pairs/ranges were artefacts of a 2D matrix: 256
cells for 26 pairs, 10.2% fill. One entry per distinct tuple replaces them,
carrying which components moved. Absent components are null, never omitted,
so 'did not exist yet' stays distinct from 'unchanged'."
```

## Task 3: Regenerate the frozen file and repair its guard test

**Files:**
- Modify: `swingbot/admin/version_history.json` (regenerated)
- Modify: `tests/scripts/test_build_version_matrix.py` (the committed-file test)

**Interfaces:**
- Consumes: `build()` from Task 2.
- Produces: the committed payload Task 4 serves.

- [ ] **Step 1: Update the committed-file guard test**

```python
def test_the_committed_file_matches_the_current_generator():
    """The frozen file is committed; this notices when it drifts from what the
    generator would produce today — the same drift the endpoint's `stale` flag
    reports at runtime, caught earlier.

    Compares the whole component dict, not two hardcoded keys: with components
    discovered from VERSION.json, a NEW component appearing in the live file and
    not in the frozen one is exactly the drift worth catching."""
    import json

    frozen_path = ROOT / "swingbot" / "admin" / "version_history.json"
    assert frozen_path.exists(), "run: python scripts/dev/build_version_matrix.py"
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))

    live_doc = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))
    live = {k: str(v) for k, v in live_doc.items()
            if not k.endswith("_updated") and v}

    assert frozen["current"] == live, (
        "VERSION.json moved without regenerating: run "
        "python scripts/dev/build_version_matrix.py")
```

- [ ] **Step 2: Regenerate**

Run: `python scripts/dev/build_version_matrix.py`
Expected on stderr: `wrote swingbot\admin\version_history.json: 2 components, N releases`

- [ ] **Step 3: Eyeball the output before trusting it**

Run: `python -c "import json;d=json.load(open('swingbot/admin/version_history.json'));print(d['components']);print(d['current']);print(len(d['releases']));print(d['releases'][-1])"`

Expected: `['ui', 'bot']`; current matching `VERSION.json`; the last release
carrying `"changed": ["ui"]` and a real commit sha — **not** `"uncommitted"`.
If it says `uncommitted`, the bump was not committed first; see Global
Constraints in `working-conventions.md`.

- [ ] **Step 4: Run the generator tests**

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/version_history.json tests/scripts/test_build_version_matrix.py
git commit -m "feat(versions): regenerate the frozen history in the new shape

The guard test now compares the whole component dict rather than ui and bot
by name -- with components discovered from VERSION.json, a new component
present live and absent from the frozen file is precisely the drift it exists
to catch."
```

---

# Phase 2 — The endpoint

## Parallelisation

**Sequential.** One task, consuming Phase 1's payload.

## Task 4: Serve the new shape and generalise `stale`

**Files:**
- Modify: `swingbot/admin/helpers.py` (add `get_component_versions`)
- Modify: `swingbot/admin/api_v1/versions.py:36-80`
- Test: `tests/admin/test_api_v1_versions.py`

**Interfaces:**
- Consumes: the frozen payload from Task 3.
- Produces: `GET /api/v1/versions` returning `generated_at`, `basis`, `live`,
  `stale`, `components`, `current`, `releases`. Task 5 types this.

- [x] **Step 1: Write the failing tests**

```python
def test_payload_shape(logged_in):
    body = logged_in.get("/api/v1/versions").get_json()
    for key in ("generated_at", "basis", "live", "stale",
                "components", "current", "releases"):
        assert key in body, f"missing {key}"
    assert isinstance(body["components"], list)
    assert isinstance(body["releases"], list)
    assert isinstance(body["stale"], bool)
    for dead in ("ui_versions", "bot_versions", "pairs", "ranges"):
        assert dead not in body, f"{dead} is a matrix artefact and must be gone"


def test_stale_is_true_when_a_component_set_differs(logged_in, monkeypatch):
    """Adding a component to VERSION.json without regenerating leaves a page
    that looks complete and is missing a whole lane. That must read as stale."""
    from swingbot.admin.api_v1 import versions as mod
    monkeypatch.setattr(mod._helpers, "get_component_versions",
                        lambda: {"ui": "9.9.9", "bot": "9.9.9", "worker": "0.1.0"})
    assert logged_in.get("/api/v1/versions").get_json()["stale"] is True


def test_stale_is_false_when_live_matches_frozen(logged_in, monkeypatch):
    import json as _json
    from swingbot.admin.api_v1 import versions as mod
    frozen = mod._load_history()["current"]
    monkeypatch.setattr(mod._helpers, "get_component_versions", lambda: dict(frozen))
    assert logged_in.get("/api/v1/versions").get_json()["stale"] is False
```

- [x] **Step 2: Run to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_versions.py`
Expected: FAIL — `missing components`, and `_helpers` has no `get_component_versions`

- [x] **Step 3: Add the helper**

In `swingbot/admin/helpers.py`, beside `get_versions()`:

```python
def get_component_versions() -> dict:
    """Every component in VERSION.json, discovered from its keys.

    Distinct from `get_versions()` above, which is deliberately left alone: the
    sidebar and `/health` want a fixed `{ui, bot, last_updated}` shape and would
    break on a third key. This one returns whatever the file declares, which is
    what the Versions page needs.

    Empty dict on a missing or malformed file — the caller renders "no history"
    rather than erroring a page out over a version display.
    """
    if not os.path.exists(VERSION_PATH):
        return {}
    try:
        with open(VERSION_PATH, "r") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return {k: str(v) for k, v in data.items()
            if not k.endswith("_updated") and v}
```

- [x] **Step 4: Rewrite the endpoint body**

```python
@api_v1.route("/versions", methods=["GET"])
@require_auth
def get_versions():
    history = _load_history()
    live = _helpers.get_component_versions()
    frozen_current = history.get("current") or {}

    # Stale means the generator has not been re-run since the last bump, not
    # that anything is broken. A whole-dict comparison rather than key-by-key:
    # a component ADDED to VERSION.json and absent from the frozen file is the
    # same failure -- a page that looks complete while missing an entire lane.
    stale = bool(live) and live != frozen_current

    return jsonify({
        "generated_at": history.get("generated_at"),
        "basis": history.get("basis"),
        "live": live,
        "stale": stale,
        "components": history.get("components", []),
        "current": frozen_current,
        "releases": history.get("releases", []),
    })
```

- [x] **Step 5: Update `_load_history`'s empty shape (line 50-52)**

```python
        return {"generated_at": None, "basis": None, "current": {},
                "components": [], "releases": []}
```

- [x] **Step 6: Run the endpoint tests**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_versions.py`
Expected: PASS

- [x] **Step 7: Commit**

```bash
git add swingbot/admin/helpers.py swingbot/admin/api_v1/versions.py tests/admin/test_api_v1_versions.py
git commit -m "feat(versions): serve components and releases, drop the cross-product

stale becomes a whole-dict comparison so that adding a component without
regenerating reads as stale -- otherwise the page renders a confidently
complete history with a lane missing. get_versions() is left alone: the
sidebar and /health want a fixed ui/bot shape and would break on a third key."
```

**Note (found during implementation):** `tests/admin/test_api_v1_versions.py` predates
this plan and still carried the old ui×bot-matrix tests (`pairs`, `ranges`,
`ui_versions`, `bot_versions`) — Task 3's guard-test repair only touched
`tests/scripts/test_build_version_matrix.py`, not this file. Those tests are
structurally incompatible with this task's own `dead not in body` assertion, so
they were removed as part of Step 7's commit rather than left to rot; the
missing/corrupt-history coverage they carried was kept, adapted to the new
`components`/`releases` keys. Actual commit: `9289b02`.

---

# Phase 3 — The store

## Parallelisation

**Sequential.** Task 6's geometry consumes Task 5's `releases()`.

## Task 5: Types, ordering, pagination and the version filter

**Files:**
- Modify: `frontend/src/app/api/models.ts:946-961`
- Rewrite: `frontend/src/app/stores/versions.store.ts`
- Rewrite: `frontend/src/app/stores/versions.store.spec.ts`

**Interfaces:**
- Consumes: the Task 4 payload.
- Produces: `VersionHistory`, `Release`, `VersionFilter` types;
  `VersionsStore` exposing `components()`, `releases()`, `visible()`,
  `current()`, `live()`, `stale()`, `basis()`, `generatedAt()`, `page()`,
  `pageSpec()`, `filter()`, `setPage(n)`, `toggleFilter(component, version)`.
  Task 6 adds geometry to this store; Task 7 renders it.

**Carried over unchanged, and they must be** — the retained template blocks call
them, so a rewrite that drops them compiles to a broken page: `empty()`,
`loading()`, `error()`, and the `load()` method with its `onInit` hook and its
`unavailable` error mapping. Copy them across verbatim.

**Removed, so their call sites must go in Task 7:** `rows()` (matrix geometry,
replaced by `visible()`) and `pairCount()` (a count of cross-product pairs,
replaced by `pageSpec().total`, which counts releases). Grep the template for
both before declaring Task 7 done.

- [ ] **Step 1: Replace the model types**

Delete `VersionPair` and `VersionRange` (grep first — they are referenced only
by `VersionHistory` and the old store) and write:

```ts
/** One release: a distinct tuple of component versions, with the commit that
 *  introduced it. `versions` is keyed by component name and carries `null` for
 *  a component that did not exist yet — which is a different fact from a
 *  component that did not change, and the strip draws the two differently. */
export interface Release {
  date: string;
  /** The last date this exact tuple was still current. Equal to `date` for a
   *  tuple superseded the same day. */
  last_seen: string;
  commit: string;
  subject: string;
  versions: Record<string, string | null>;
  /** Components whose value differs from the previous release. Derived by the
   *  generator, never here — see the note in `build_version_matrix.py`. */
  changed: string[];
}

export interface VersionHistory {
  generated_at: string | null;
  /** The server's own sentence about what the data does and does not claim.
   *  Rendered verbatim rather than restated, so the page cannot drift into
   *  promising "tested" where the API says "shipped". */
  basis: string | null;
  /** Read from VERSION.json per request, so it always matches the sidebar. */
  live: Record<string, string>;
  stale: boolean;
  /** Lane and chip order: first-appearance, so adding a component appends. */
  components: string[];
  current: Record<string, string>;
  /** Oldest first on the wire. The store reverses exactly once. */
  releases: Release[];
}

/** A selected `{component, version}` pair, or null for "no filter". */
export type VersionFilter = { component: string; version: string } | null;
```

- [ ] **Step 2: Write the failing store tests**

Keep the file's existing TestBed setup (providers, `HttpTestingController`) —
only the fixture and the assertions change. Add this harness above the tests;
Task 6 uses `seed()` too:

```ts
let store: InstanceType<typeof VersionsStore>;

/** Stand the store up and answer its one request.
 *
 *  Takes the payload rather than assuming one, because two tests need a
 *  different history (the single-release case below, and the six-component
 *  case in Task 8). `VersionsStore.load()` runs from `onInit`, so the request
 *  is in flight as soon as the store is injected — flushing is all that is
 *  left to do. */
function seed(payload: VersionHistory): void {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      VersionsStore,
    ],
  });
  const http = TestBed.inject(HttpTestingController);
  store = TestBed.inject(VersionsStore);
  http.expectOne('/api/v1/versions').flush(payload);
}

beforeEach(() => seed(RESPONSE));
```

```ts
const RESPONSE: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '1.2.0', bot: '1.1.2' },
  stale: false,
  components: ['ui', 'bot', 'worker'],
  current: { ui: '1.2.0', bot: '1.1.2', worker: '0.1.0' },
  releases: [
    { date: '2026-07-01', last_seen: '2026-07-04', commit: 'a1', subject: 'first',
      versions: { ui: '1.0.0', bot: '1.0.0', worker: null }, changed: ['ui', 'bot'] },
    { date: '2026-07-05', last_seen: '2026-07-05', commit: 'a2', subject: 'bot moves',
      versions: { ui: '1.0.0', bot: '1.1.2', worker: null }, changed: ['bot'] },
    { date: '2026-07-06', last_seen: '2026-08-15', commit: 'a3', subject: 'worker joins',
      versions: { ui: '1.2.0', bot: '1.1.2', worker: '0.1.0' }, changed: ['ui', 'worker'] },
  ],
};

it('reverses the wire order exactly once', () => {
  expect(store.releases().map((r) => r.commit)).toEqual(['a3', 'a2', 'a1']);
});

it('filters to the releases carrying a component version', () => {
  store.toggleFilter('bot', '1.1.2');
  expect(store.visible().map((r) => r.commit)).toEqual(['a3', 'a2']);
});

it('clears the filter when the same chip is chosen twice', () => {
  store.toggleFilter('bot', '1.1.2');
  store.toggleFilter('bot', '1.1.2');
  expect(store.filter()).toBeNull();
  expect(store.visible()).toHaveLength(3);
});

it('never matches a null version — absent is not a value', () => {
  store.toggleFilter('worker', '');
  expect(store.visible()).toHaveLength(0);
});

it('resets to page 1 when the filter changes', () => {
  store.setPage(2);
  store.toggleFilter('bot', '1.1.2');
  expect(store.page()).toBe(1);
});
```

- [ ] **Step 3: Run to verify they fail**

Run: `npx ng test`
Expected: FAIL — `store.releases is not a function`

- [ ] **Step 4: Implement the store's non-geometry half**

```ts
export const PAGE_SIZE = 25;

interface VersionsSlice {
  data: VersionHistory | null;
  loading: boolean;
  error: string | null;
  page: number;
  filter: VersionFilter;
}
```

`withComputed`:

```ts
      components: computed<string[]>(() => data()?.components ?? []),

      /** Newest first. THE one reversal — the wire is oldest-first because
       *  that is how the generator walks git, and two conventions that can
       *  disagree is one more than this needs. */
      releases: computed<Release[]>(() => [...(data()?.releases ?? [])].reverse()),
```

and, in a second `withComputed` that can see `releases`:

```ts
      /** Releases matching the filter, before paging. An empty-string version
       *  matches nothing: `versions[c]` is `null` when the component did not
       *  exist, and absent must never look like a value. */
      matching: computed<Release[]>(() => {
        const active = filter();
        const all = releases();
        if (!active) return all;
        return all.filter((r) => r.versions[active.component] === active.version);
      }),
```

then `visible`, `pageSpec` and the methods:

```ts
      visible: computed<Release[]>(() => {
        const start = (page() - 1) * PAGE_SIZE;
        return matching().slice(start, start + PAGE_SIZE);
      }),

      pageSpec: computed<PageSpec>(() => ({
        // The count BEFORE slicing. `visible().length` here would silently
        // show a single page however much history is behind it.
        total: matching().length,
        page: page(),
        perPage: PAGE_SIZE,
      })),
```

```ts
      setPage(n: number): void {
        patchState(store, { page: Math.max(1, n) });
      },

      /** Selecting the same chip twice clears — the chip IS the toggle, which
       *  is why there is no separate "clear filter" control. Always returns to
       *  page 1: staying on page 3 of a filter that now has one page shows an
       *  empty list that looks like "no results". */
      toggleFilter(component: string, version: string): void {
        const active = store.filter();
        const same = active?.component === component && active?.version === version;
        patchState(store, {
          filter: same ? null : { component, version },
          page: 1,
        });
      },
```

- [ ] **Step 5: Run to verify they pass**

Run: `npx ng test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/stores/versions.store.ts frontend/src/app/stores/versions.store.spec.ts
git commit -m "feat(versions): store reads releases, pages them, filters by chip

One reversal, in one place: the wire is oldest-first because that is how the
generator walks git. The chip is its own toggle, so lookup needs no new
control, and it resets to page 1 -- staying on page 3 of a one-page filter
shows an empty list that reads as 'no results'."
```

## Task 6: Strip geometry — time axis, width floor, absent regions, bracket

**Files:**
- Modify: `frontend/src/app/stores/versions.store.ts`
- Modify: `frontend/src/app/stores/versions.store.spec.ts`

**Interfaces:**
- Consumes: `releases()`, `components()`, `visible()` from Task 5.
- Produces: `LaneSegment` and `Lane` types; `lanes()`, `bracket()`,
  `setStripWidth(px)`. Task 7 renders these.

- [ ] **Step 1: Write the failing geometry tests**

```ts
it('lays segments out on a time axis, not by release index', () => {
  // a1 held for 4 days, a2 for 1, a3 to now. Index order would make them equal.
  const ui = store.lanes().find((l) => l.component === 'ui')!;
  expect(ui.segments[0].width).toBeGreaterThan(ui.segments[1].width);
});

it('every lane sums to 1', () => {
  for (const lane of store.lanes()) {
    const total = lane.segments.reduce((sum, s) => sum + s.width, 0)
      + lane.absentWidth;
    expect(total).toBeCloseTo(1, 5);
  }
});

it('floors a sub-pixel segment and takes the surplus from its neighbours', () => {
  store.setStripWidth(200);           // floor = 2/200 = 0.01
  const ui = store.lanes().find((l) => l.component === 'ui')!;
  for (const s of ui.segments) expect(s.width).toBeGreaterThanOrEqual(0.01);
  expect(ui.segments.reduce((sum, s) => sum + s.width, 0)).toBeCloseTo(1, 5);
});

it('gives a late component an absent region, not a segment', () => {
  const worker = store.lanes().find((l) => l.component === 'worker')!;
  // The leading gap is a region with no version, never a segment carrying a
  // falsy one — the two render differently and must not be conflated.
  expect(worker.absentWidth).toBeGreaterThan(0);
  expect(worker.segments).toHaveLength(1);
  expect(worker.segments[0].version).toBe('0.1.0');
});

it('brackets the visible page', () => {
  const b = store.bracket();
  expect(b.start).toBeGreaterThanOrEqual(0);
  expect(b.start + b.width).toBeLessThanOrEqual(1.000001);
});

it('survives a single release without dividing by zero', () => {
  // One release means a zero-length time span. `tEnd` is floored at `t0 + 1`
  // precisely so this divides by 1 rather than 0 and yields a full-width
  // segment instead of NaN — which would render as an invisible strip.
  const ONE: VersionHistory = {
    ...RESPONSE,
    components: ['ui'],
    current: { ui: '1.0.0' },
    releases: [{
      date: '2026-07-01', last_seen: '2026-07-01', commit: 'a1', subject: 'only',
      versions: { ui: '1.0.0' }, changed: ['ui'],
    }],
  };
  seed(ONE);
  expect(store.lanes()[0].segments[0].width).toBeCloseTo(1, 5);
  expect(Number.isNaN(store.lanes()[0].segments[0].width)).toBe(false);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npx ng test`
Expected: FAIL — `store.lanes is not a function`

- [ ] **Step 3: Add the types**

```ts
/** One component's run at one version, as a fraction of the strip. */
export interface LaneSegment {
  version: string;
  /** Left edge, 0-1. */ start: number;
  /** Width, 0-1, never below the pixel floor. */ width: number;
  firstSeen: string;
  lastSeen: string;
  current: boolean;
}

export interface Lane {
  component: string;
  segments: LaneSegment[];
  /** Width of the leading "did not exist yet" region, 0 when the component was
   *  present at the first release. Deliberately not a segment: it must never
   *  be mistaken for a version, and it carries no version to show. */
  absentWidth: number;
}
```

- [ ] **Step 4: Implement the floor, as a pure exported function**

Exported so it can be tested without a store, and so the redistribution is
readable on its own:

```ts
/**
 * Raise every width to `floor`, taking the surplus proportionally from those
 * above it. Iterative, not single-pass: raising the small ones shrinks the
 * large ones, which can push a previously-fine segment below the floor.
 *
 * Why a floor at all: `git log --date=short` gives day resolution, and this
 * repo really does ship several times a day (four releases on 2026-08-14).
 * On a six-week axis those are ~0.6% wide each — sub-pixel — and would simply
 * vanish, so the strip would under-report exactly the burst activity it is
 * meant to show.
 *
 * The cost, which is accepted and documented on the page: once segments are
 * floored the lane is honest about ORDER and approximate about DURATION. The
 * date ticks below the strip are the ground truth.
 */
export function applyFloor(widths: number[], floor: number): number[] {
  if (widths.length === 0) return [];
  // Nothing to do, and the fully-saturated case: if even equal shares are
  // below the floor, equal shares are the best available answer.
  if (widths.length * floor >= 1) return widths.map(() => 1 / widths.length);

  const out = [...widths];
  const pinned = new Set<number>();
  for (;;) {
    const newly = out
      .map((w, i) => [w, i] as const)
      .filter(([w, i]) => !pinned.has(i) && w < floor)
      .map(([, i]) => i);
    if (newly.length === 0) return out;

    for (const i of newly) { out[i] = floor; pinned.add(i); }

    const budget = 1 - pinned.size * floor;
    const free = out.reduce((sum, w, i) => (pinned.has(i) ? sum : sum + w), 0);
    if (free <= 0) {
      const share = budget / (out.length - pinned.size || 1);
      out.forEach((_, i) => { if (!pinned.has(i)) out[i] = share; });
      return out;
    }
    out.forEach((w, i) => { if (!pinned.has(i)) out[i] = (w / free) * budget; });
  }
}
```

- [ ] **Step 5: Implement `lanes` and `bracket`**

Add `stripWidth: 800` to the slice (a sane default so the store is usable
before the component has measured itself), plus:

```ts
      /** Segments per component, on a TIME axis.
       *
       *  Time and not release index, because index would space every release
       *  equally and destroy the signal this strip exists to carry: bot sat at
       *  1.1.2 through ten consecutive ui releases, and that only shows up
       *  when width means duration. */
      lanes: computed<Lane[]>(() => {
        const ordered = [...(data()?.releases ?? [])];   // oldest first
        if (ordered.length === 0) return [];

        const t = (iso: string) => new Date(iso).getTime();
        const t0 = t(ordered[0].date);
        const tEnd = Math.max(t(ordered[ordered.length - 1].last_seen), t0 + 1);
        const span = tEnd - t0;                          // never 0 — see above
        const floor = 2 / Math.max(1, stripWidth());

        return components().map((component) => {
          // Collapse consecutive releases that leave this component alone: a
          // lane's segments are ITS changes, not every release.
          const runs: { version: string; from: number; to: number }[] = [];
          for (const r of ordered) {
            const version = r.versions[component];
            if (version === null || version === undefined) continue;
            const last = runs[runs.length - 1];
            if (last && last.version === version) last.to = t(r.last_seen);
            else runs.push({ version, from: t(r.date), to: t(r.last_seen) });
          }
          if (runs.length === 0) return { component, segments: [], absentWidth: 1 };

          runs[runs.length - 1].to = tEnd;               // the live one runs to now
          const absentWidth = (runs[0].from - t0) / span;
          const raw = runs.map((run) => (run.to - run.from) / span);
          const scale = 1 - absentWidth;
          const widths = applyFloor(raw.map((w) => w / (scale || 1)), floor / (scale || 1))
            .map((w) => w * scale);

          let cursor = absentWidth;
          const segments = runs.map((run, i) => {
            const segment: LaneSegment = {
              version: run.version, start: cursor, width: widths[i],
              firstSeen: ordered.find((r) => t(r.date) === run.from)?.date ?? '',
              lastSeen: ordered.find((r) => t(r.last_seen) === run.to)?.last_seen ?? '',
              current: i === runs.length - 1,
            };
            cursor += widths[i];
            return segment;
          });
          return { component, segments, absentWidth };
        });
      }),
```

```ts
      /** Where the visible page sits on the full-history strip. This is the
       *  whole reason the strip can show all of history and still say where
       *  you are — the alternative was a zoom control nobody asked for. */
      bracket: computed<{ start: number; width: number }>(() => {
        const rows = visible();
        const ordered = [...(data()?.releases ?? [])];
        if (rows.length === 0 || ordered.length === 0) return { start: 0, width: 0 };

        const t = (iso: string) => new Date(iso).getTime();
        const t0 = t(ordered[0].date);
        const tEnd = Math.max(t(ordered[ordered.length - 1].last_seen), t0 + 1);
        const span = tEnd - t0;

        // `visible` is newest-first, so its last row is the oldest on screen.
        const from = t(rows[rows.length - 1].date);
        const to = t(rows[0].last_seen);
        const start = (from - t0) / span;
        return { start, width: Math.max((to - from) / span, 2 / Math.max(1, stripWidth())) };
      }),
```

and the setter:

```ts
      /** Measured by the component. The floor is a PIXEL rule, so the geometry
       *  cannot be computed without knowing how wide the strip actually is. */
      setStripWidth(px: number): void {
        patchState(store, { stripWidth: Math.max(1, Math.round(px)) });
      },
```

- [ ] **Step 6: Run to verify they pass**

Run: `npx ng test`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/stores/versions.store.ts frontend/src/app/stores/versions.store.spec.ts
git commit -m "feat(versions): lane geometry on a time axis with a pixel floor

Time and not release index: index spaces releases equally and destroys the
one signal the strip carries -- bot held 1.1.2 across ten ui releases, which
is only visible when width means duration. The floor exists because
--date=short gives day resolution and this repo ships several times a day;
four same-day releases are sub-pixel on a six-week axis and would vanish."
```

---

# Phase 4 — The page

## Parallelisation

**Sequential between 7 and 8** — both rewrite `versions.ts`, and this working
tree is shared, so two agents on that file overwrite rather than merge. Task 9's
generator-side work shares no file with either and **may run alongside Task 8**.

## Task 7: Headline, strip, stream, pagination

**Files:**
- Rewrite: `frontend/src/app/workspaces/versions/versions.ts`

**Interfaces:**
- Consumes: everything Tasks 5-6 produce.
- Produces: the rendered workspace. Task 8 annotates it.

- [ ] **Step 1: Replace the template**

Four regions, top to bottom. Keep the existing `head`, `error`, `muted` and
`stale` blocks verbatim — they are unchanged by this work.

```html
<div class="headline">
  <span class="label">Running now</span>
  <div class="chips">
    @for (component of store.components(); track component) {
      @if (store.current()[component]; as version) {
        <button type="button" class="chip" [class.on]="isFiltered(component, version)"
                (click)="store.toggleFilter(component, version)"
                [attr.title]="component + ' ' + version + ' — click to filter'">
          {{ component }} <strong>{{ version }}</strong>
        </button>
      }
    }
  </div>
</div>

<div class="strip" #strip>
  @for (lane of store.lanes(); track lane.component) {
    <div class="lane">
      <span class="lane-name">{{ lane.component }}</span>
      <div class="track">
        @if (lane.absentWidth > 0) {
          <div class="absent" [style.width.%]="lane.absentWidth * 100"
               title="This component did not exist yet"></div>
        }
        @for (segment of lane.segments; track segment.start) {
          <button type="button" class="segment" [class.current]="segment.current"
                  [style.left.%]="segment.start * 100"
                  [style.width.%]="segment.width * 100"
                  (click)="store.toggleFilter(lane.component, segment.version)"
                  [attr.title]="lane.component + ' ' + segment.version
                    + ' · ' + segment.firstSeen + ' → ' + segment.lastSeen"></button>
        }
      </div>
    </div>
  }
  <div class="bracket-row">
    <div class="bracket" [style.left.%]="store.bracket().start * 100"
         [style.width.%]="store.bracket().width * 100"
         title="The releases listed below"></div>
  </div>
</div>

<ul class="stream">
  @for (release of store.visible(); track release.commit) {
    <li class="entry">
      <span class="when">{{ release.date }}</span>
      <div class="what">
        <div class="chips">
          @for (component of store.components(); track component) {
            @if (release.versions[component]; as version) {
              @if (release.changed.includes(component)) {
                <button type="button" class="chip moved"
                        (click)="store.toggleFilter(component, version)">
                  {{ component }} {{ previousOf(release, component) }}<strong>{{ version }}</strong>
                </button>
              } @else {
                <span class="chip quiet">{{ component }} {{ version }}</span>
              }
            }
          }
        </div>
        <p class="subject">{{ release.subject }}</p>
      </div>
    </li>
  }
</ul>

<sb-pagination [pagination]="store.pageSpec()" (pageChange)="store.setPage($event)" />
```

- [ ] **Step 2: Add the component members**

```ts
  protected readonly store = inject(VersionsStore);
  private readonly strip = viewChild<ElementRef<HTMLElement>>('strip');

  protected isFiltered(component: string, version: string): boolean {
    const active = this.store.filter();
    return active?.component === component && active?.version === version;
  }

  /** "1.2.4 → " for a bump, "· new " for a component's first appearance. The
   *  two are distinguishable because the previous release's value is null,
   *  and they must be: a component appearing is not a component upgrading. */
  protected previousOf(release: Release, component: string): string {
    const all = this.store.releases();          // newest first
    const at = all.indexOf(release);
    const previous = all[at + 1]?.versions[component] ?? null;
    return previous === null ? '· new ' : `${previous} → `;
  }

  /** The floor is a pixel rule, so the store needs the real width. */
  private readonly measure = effect((onCleanup) => {
    const host = this.strip()?.nativeElement;
    if (!host) return;
    const observer = new ResizeObserver(([entry]) =>
      this.store.setStripWidth(entry.contentRect.width));
    observer.observe(host);
    onCleanup(() => observer.disconnect());
  });
```

- [ ] **Step 3: Write the styles**

Delete every `.matrix`, `.corner`, `.colhead`, `.rowhead`, `.track .bar`,
`.dot` and `.scroller` rule — the matrix is gone. Add:

```css
    /* minmax(0, 1fr): an auto track is floored at its widest child, which is
       how one panel takes the page sideways. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }

    /* Chips WRAP and lanes STACK. This is the property the whole design rests
       on: a new component costs vertical space and never horizontal, so the
       page cannot be widened by adding one. Do not replace with a grid. */
    .chips { display: flex; flex-wrap: wrap; gap: var(--space-6); }

    .lane { display: flex; align-items: center; gap: var(--space-8); }
    .lane-name { width: 4.5rem; flex: none; font-family: var(--font-mono);
                 font-size: var(--text-micro); color: var(--text-muted); }
    .track { position: relative; flex: 1; height: 15px; min-width: 0; }
    .segment { position: absolute; top: 0; height: 100%; border: 0; padding: 0;
               border-radius: 2px; background: var(--accent-soft); cursor: pointer; }
    .segment.current { background: var(--accent); }
    .absent { position: absolute; left: 0; top: 0; height: 100%;
              border: 1px dashed var(--border-strong); border-radius: 2px; }
    .bracket-row { position: relative; height: 12px; margin-left: calc(4.5rem + var(--space-8)); }
    .bracket { position: absolute; top: 0; height: 100%; border: 1px solid var(--text-faint);
               border-radius: 3px; background: var(--surface-raised); }
```

- [ ] **Step 4: Remove the two dead call sites**

Run: `cd frontend && grep -n "rows()\|pairCount()" src/app/workspaces/versions/versions.ts`
Expected: no output. `rows()` was matrix geometry — the stream uses
`store.visible()`. `pairCount()` counted cross-product pairs — the legend's
tally becomes `store.pageSpec().total` releases. Both are gone from the store
after Task 5, so a leftover is a compile error, not a silent bug.

- [ ] **Step 5: Build and check it compiles**

Run: `cd frontend && npx ng build`
Expected: `Application bundle generation complete.`

- [ ] **Step 6: Run the frontend suite**

Run: `cd frontend && npx ng test`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/versions/versions.ts
git commit -m "feat(versions): the matrix becomes a strip over a change stream

Chips wrap and lanes stack, so component count costs vertical space and
never horizontal -- the property that makes an open-ended component set
representable at all. A 2D grid gives each component an axis and there is
no third axis, which is why this is a rewrite and not new CSS."
```

## Task 8: Annotation — legend, ticks, tooltips, and the states

**Files:**
- Modify: `frontend/src/app/workspaces/versions/versions.ts`
- Modify: `frontend/src/app/workspaces/versions/versions.spec.ts` (create)

**Interfaces:**
- Consumes: Task 7's rendered page.
- Produces: nothing downstream. This is the last UI task.

- [ ] **Step 1: Write the failing overflow test**

```ts
/** Six components, one of them arriving late. The point is the count: this is
 *  three times what the matrix could represent at all, and the assertion is
 *  that it costs vertical space only. */
const SIX: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
  stale: false,
  components: ['ui', 'bot', 'worker', 'schema', 'api', 'cron'],
  current: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
  releases: [
    { date: '2026-07-01', last_seen: '2026-07-09', commit: 'b1', subject: 'start',
      versions: { ui: '1.0.0', bot: '1.0.0', worker: null, schema: null, api: null, cron: null },
      changed: ['ui', 'bot'] },
    { date: '2026-07-10', last_seen: '2026-08-15', commit: 'b2', subject: 'the rest arrive',
      versions: { ui: '2.0.0', bot: '1.1.2', worker: '0.3.0', schema: '4', api: '1.0.0', cron: '0.9.1' },
      changed: ['ui', 'bot', 'worker', 'schema', 'api', 'cron'] },
  ],
};

it('does not widen when components are added', async () => {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
    ],
  });
  const fixture = TestBed.createComponent(Versions);
  // A narrow host is the real test: the page must fit the container it is
  // given, not merely fit on a wide screen.
  fixture.nativeElement.style.width = '640px';
  TestBed.inject(HttpTestingController).expectOne('/api/v1/versions').flush(SIX);
  await fixture.whenStable();
  fixture.detectChanges();

  const host = fixture.nativeElement as HTMLElement;
  expect(host.scrollWidth).toBeLessThanOrEqual(host.clientWidth);
});
```

- [ ] **Step 2: Run to verify it fails or passes**

Run: `cd frontend && npx ng test`
Expected: PASS if Task 7's CSS is right. **If it fails, Task 7 has a bug** —
fix it there rather than working around it here. This test exists because the
no-horizontal-growth property is the design's foundation and a comment cannot
enforce it.

- [ ] **Step 3: Add the legend and axis ticks**

```html
<div class="legend">
  <span><i class="sw seg"></i>a version was live</span>
  <span><i class="sw abs"></i>the component did not exist yet</span>
  <span><i class="sw cur"></i>running now</span>
  <span><i class="sw brk"></i>the releases listed below</span>
</div>

<div class="ticks">
  <span>{{ store.firstDate() }}</span>
  <span class="now">{{ store.lastDate() }} &#9650; now</span>
</div>

@if (store.dense()) {
  <p class="note">
    Ordered by time; at this density segment widths are approximate — the dates
    above are the ground truth.
  </p>
}
```

Add to the store:

```ts
      firstDate: computed(() => data()?.releases?.[0]?.date ?? ''),
      lastDate: computed(() => {
        const all = data()?.releases ?? [];
        return all[all.length - 1]?.last_seen ?? '';
      }),
      /** True once enough segments are floored that width has stopped meaning
       *  duration. Drives the caveat above rather than hiding it. */
      dense: computed(() =>
        lanes().some((lane) => lane.segments.length > stripWidth() / 8)),
```

- [ ] **Step 4: Add the missing states**

```html
@if (store.filter(); as active) {
  <p class="filtered" role="status">
    Showing releases with {{ active.component }} {{ active.version }}.
    <button type="button" class="link" (click)="store.toggleFilter(active.component, active.version)">
      Show all
    </button>
  </p>
}
@if (store.filter() && !store.visible().length) {
  <p class="muted">No releases carry that version.</p>
}
```

Keep the existing "no history recorded" copy for the generator-never-run case —
it answers a different question and must stay distinguishable from the above.

- [ ] **Step 5: Confirm `basis` still renders verbatim**

Run: `cd frontend && grep -n "basis" src/app/workspaces/versions/versions.ts`
Expected: a `{{ store.basis() }}` interpolation with no surrounding rewording.
This is a Global Constraint — the page must not drift into promising "tested".

- [ ] **Step 6: Build and test**

Run: `cd frontend && npx ng build && npx ng test`
Expected: bundle complete; all tests pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/workspaces/versions/
git commit -m "feat(versions): annotate every mark the reader could misread

A timeline has more marks that can be misread than a table does, so each one
is named in the page: legend, date ticks with an explicit now, per-segment
tooltips carrying what the compressed geometry cannot show, and a caveat that
appears exactly when width stops meaning duration. Plus a test for the
no-horizontal-growth property, which a comment cannot enforce."
```

---

# Phase 5 — Close

## Parallelisation

**Sequential.** The gate is the last thing.

## Task 9: Full gate, release, regenerate

**Files:**
- Modify: `VERSION.json`, `swingbot/admin/version_history.json`
- Modify: `docs/superpowers/specs/2026-08-15-v28-versions-timeline-design.md` (move)
- Modify: `docs/superpowers/plans/2026-08-15-v29-versions-timeline.md` (move)

- [ ] **Step 1: Confirm nothing still reads the dead fields**

Run: `git grep -n "ui_versions\|bot_versions\|VersionPair\|VersionRange" -- '*.py' '*.ts'`
Expected: no output. Any hit is a leftover — remove it before proceeding.

- [ ] **Step 2: Run both suites**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`. The passed/skipped counts will have moved and
that is not a failure — see `docs/claude/testing-cost.md`.

Run: `cd frontend && npx ng test`
Expected: all files pass.

- [ ] **Step 3: Bump `ui` to 1.4.0**

Edit `VERSION.json`: `"ui": "1.4.0"`, and set `ui_updated` to now
(`YYYY-MM-DD HH-MM-SS`, UTC). Leave `bot` and `bot_updated` alone.

```bash
git add VERSION.json
git commit -m "release(ui): 1.4.0 -- the Versions timeline

Minor, as v28 predicted: the workspace is replaced rather than adjusted.
Different visualisation, different question answered, and a payload sharing
no field names with the old one."
```

- [ ] **Step 4: Regenerate — AFTER the bump commit, never before**

The generator walks `git log` for `VERSION.json`. Run before the bump is
committed and the newest release records as `"commit": "uncommitted"`, which is
what shipped in 1.3.0. See `working-conventions.md`.

```bash
python scripts/dev/build_version_matrix.py
python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py
git add swingbot/admin/version_history.json
git commit -m "chore(versions): regenerate version_history.json for 1.4.0"
```

- [ ] **Step 5: Move the spec and plan to `implemented/`**

```bash
git mv docs/superpowers/specs/2026-08-15-v28-versions-timeline-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-15-v29-versions-timeline.md docs/superpowers/plans/implemented/
git commit -m "docs: v28/v29 close, so they leave the live list"
```

- [ ] **Step 6: Push**

```bash
git fetch origin && git rev-list --left-right --count main...origin/main
git push origin main
```

---

## Parallelisation

- **Sequential throughout Phases 1-3.** The payload is a chain: the generator
  defines the shape, the endpoint serves it, the store reads it, the component
  draws it. Each task consumes the previous task's output, and no two of them
  touch disjoint files without a contract dependency. Saying this explicitly is
  worth as much as a wide group — it stops the next session re-deriving the
  graph to discover there isn't one.
- **The one genuine parallel pair:** Task 8 (frontend annotation) and Task 9
  Step 1 (the dead-field grep, which touches only Python) share no file.
  Everything else in Phase 4 collides on `versions.ts`.
- **This working tree is shared between sessions.** Two agents on `versions.ts`
  overwrite rather than merge.
