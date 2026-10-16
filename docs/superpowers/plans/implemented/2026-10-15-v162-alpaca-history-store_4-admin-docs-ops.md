# v162 Alpaca history store, part 4: admin Tuning, docs, routing, ops scripts

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. **Never read this plan whole:** pull one task with `grep -n "^### Task AH16:" -A 400 docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_4-admin-docs-ops.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v162-alpaca-history-store-design.md`](../specs/2026-10-15-v162-alpaca-history-store-design.md) (§3 "The admin Tuning page", § Docs and tests this changes, §2 weekly cron, §4 pulling, § Research discipline, Acceptance 6 and 8, Amendments)
**Bump:** bot patch
**Edge:** none (integrity)
**Index:** [`2026-10-15-v162-alpaca-history-store_0-index.md`](2026-10-15-v162-alpaca-history-store_0-index.md) carries the Global Constraints, `## Parallelisation` and the task ledger. This part holds AH16–AH20.

**Conventions used in every task of this part**

- `$WT` = `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v162-alpaca-history-store`, `$R` = the main tree. Never `cd`; use `git -C $WT` and absolute paths. After each task `git -C $R status --short` shows the main tree unchanged.
- Contracts this part consumes, exactly as the ledger and AH10 define them: `config.TRAINING_DATA_SOURCE` (`"alpaca"` | `"yfinance"`, read at call time, hot-reloadable); `training_data.DATA_SOURCES = ("alpaca", "yfinance")`; `training_data.select(None)` resolves to `"yfinance"` whenever env `BACKTEST_CACHE_DIR` is set and non-blank, else to the config value; `training_data.provenance_path(out)` = `<out>.provenance.json`; `training_data.reset()`. AH12 makes `tune_strategy.py` accept `--data-source {alpaca,yfinance}` and adds the keys `data_source` (str) and `provenance` (dict) to its `--json` payload. AH11 keys registry rows on `(source, strategy, horizon, data_source)`; AH14 adds the optional ledger field `data_source`; AH15 makes `get_badge` prefer the active source and fall back to `yfinance`. AH13: an explicit `--cache-dir` forces `select("yfinance")`.
- Per-task runs: `python $WT/scripts/dev/testrun.py file <test>`. Frontend: `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>` (a 60-second `Timeout waiting for worker` with `no tests` is load: re-run it, `testing-cost.md` § Frontend). Complexity: `python -m radon cc -s -n C <files>` prints nothing new.
- The worktree has no store and a 3-ticker watchlist; no test here reads the real `data/market_data/` or reaches the VM.

# Phase D: admin Tuning page

### Task AH16: Admin Tuning API: source choice, defaults, result source

**Model:** sonnet — a whitelisted argv flag, one read-only route and one extra response key, all over existing Flask patterns; the only judgement (always emit the flag) is fixed below

**Files:**
- Modify: `swingbot/admin/jobs.py` (`build_tune_args` at :73-96; two new helpers beside it)
- Modify: `swingbot/admin/api_v1/jobs.py` (imports at :21-30; `get_job_result` at :68-108; new route after `start_tune_job` at :111-128)
- Modify: `tests/admin/test_jobs.py` (`test_build_tune_args_passes_be_trigger_through` at :197-200)
- Modify: `tests/admin/test_api_v1_jobs.py` (`test_job_result_is_empty_not_404_while_a_job_is_still_running`, its `assert_shape` line)
- Test: `tests/admin/test_jobs_data_source.py`

The two modified test files are not in the ledger row: they pin the old argv and the old three-key result shape, so this task has to update them.

**Interfaces:**
- Consumes (AH10): `config.TRAINING_DATA_SOURCE`, `training_data.DATA_SOURCES`. (AH12): `tune_strategy.py --data-source`, and the tune payload key `data_source` that `_ingest_tuning_result` (`jobs.py:143`) stores through `tuning_repo().save_result`. Existing: `build_tune_args`, `assert_train_only` (`jobs.py:54`), `job_manager.start(kind, args)`, `_load_result(job_id)` (`admin/queries.py:275`), `tests.store_seed.seed_store`, `tests.admin.api_v1_contract.assert_error` / `assert_shape`.
- Produces (ledger AH16, the Admin API in the index's Shared contracts, consumed by AH17):
  - `build_tune_args(strategy, params)` always emits `--data-source <v>` right after `--strategy <s>`. `v` is `params["data_source"]` when present and non-empty, else `config.TRAINING_DATA_SOURCE` read at call time. A value outside `DATA_SOURCES` raises `ValueError` whose message contains `data_source`.
  - `POST /api/v1/jobs/tune` body `{"strategy": str, "params": {"data_source": "alpaca" | "yfinance", ...}}` (unchanged route; a bad source is `400 invalid` carrying the message).
  - `GET /api/v1/jobs/tune/defaults` → `{"data_source": <config value>, "choices": ["alpaca", "yfinance"]}` (auth required).
  - `GET /api/v1/jobs/<id>/result` gains `"data_source"`: the stored payload's `data_source`; `"yfinance"` when the payload has none (a pre-v162 result); `null` while the job has no result yet.

**Rules this task freezes (spec §3 "The admin Tuning page"; staff-engineer BLOCKING finding):**
- **The flag is always emitted.** A job's stored argv (`admin_jobs`) then records the data it ran on, even after the `.env` default flips. Rollback stays one `.env` line: with `TRAINING_DATA_SOURCE=yfinance`, every admin grid launched without an explicit choice runs on yfinance.
- **No new firewall hole.** The value is checked against `DATA_SOURCES` before it reaches argv, and `assert_train_only` still runs over the finished argv. `--data-source` carries no date, so it can never open the VALIDATION window (spec § Research discipline: a data source grants no validation run, and the admin page cannot launch one at all).
- **Route prefix kept.** `/jobs/tune` is unchanged; only `/jobs/tune/defaults` is new. It cannot collide with `/jobs/<job_id>` (one segment) or `/jobs/<job_id>/result` (literal `result`).

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/admin/test_jobs_data_source.py`:

```python
"""v162 AH16: the admin Tuning page chooses its training data (spec §3).

Without this the TRAINING_DATA_SOURCE flip would silently change every
admin-run grid (staff-engineer BLOCKING finding). The flag is always on the
argv, so a stored job says which data it ran on."""
import pytest

from swingbot import config
from swingbot.admin.jobs import assert_train_only, build_tune_args
from tests.admin.api_v1_contract import assert_error, assert_shape
from tests.store_seed import seed_store

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def default_yfinance(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")


# --- build_tune_args ---------------------------------------------------------

def test_the_config_default_is_emitted_when_no_source_is_given(default_yfinance):
    assert build_tune_args("RSI", None) == ["--strategy", "RSI", "--data-source", "yfinance"]


def test_the_default_is_read_at_call_time_not_import_time(monkeypatch):
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    assert build_tune_args("RSI", {})[2:4] == ["--data-source", "alpaca"]
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "yfinance")
    assert build_tune_args("RSI", {})[2:4] == ["--data-source", "yfinance"]


def test_an_explicit_source_wins_over_the_default(default_yfinance):
    args = build_tune_args("RSI", {"data_source": "alpaca", "be_trigger": 0.6})
    assert args == ["--strategy", "RSI", "--data-source", "alpaca", "--be-trigger", "0.6"]


def test_an_empty_source_means_the_default(default_yfinance):
    assert build_tune_args("RSI", {"data_source": ""})[3] == "yfinance"


@pytest.mark.parametrize("bad", ["polygon", "ALPACA", 5, ["alpaca"]])
def test_a_source_outside_the_whitelist_is_refused(default_yfinance, bad):
    with pytest.raises(ValueError, match="data_source"):
        build_tune_args("RSI", {"data_source": bad})


def test_the_source_flag_never_trips_the_train_only_guard(default_yfinance):
    assert_train_only(build_tune_args("RSI", {"data_source": "alpaca"}))  # must not raise


# --- POST /jobs/tune -----------------------------------------------------------

class _CapturingManager:
    def __init__(self):
        self.calls = []

    def start(self, kind, args):
        self.calls.append((kind, list(args)))
        return "job123"


def _patch_manager(monkeypatch, manager):
    # api_v1/jobs.py binds the manager at import; patch that reference.
    monkeypatch.setattr("swingbot.admin.api_v1.jobs.job_manager", manager)


def test_start_tune_passes_the_chosen_source_to_the_job(logged_in, monkeypatch, default_yfinance):
    manager = _CapturingManager()
    _patch_manager(monkeypatch, manager)
    r = logged_in.post("/api/v1/jobs/tune",
                       json={"strategy": "VWAP", "params": {"data_source": "alpaca"}})
    assert r.status_code == 200
    assert manager.calls == [("tune", ["--strategy", "VWAP", "--data-source", "alpaca"])]


def test_start_tune_without_a_choice_uses_the_config_default(logged_in, monkeypatch, default_yfinance):
    manager = _CapturingManager()
    _patch_manager(monkeypatch, manager)
    logged_in.post("/api/v1/jobs/tune", json={"strategy": "VWAP"})
    assert manager.calls[0][1][2:] == ["--data-source", "yfinance"]


def test_start_tune_refuses_an_unknown_source(logged_in, monkeypatch):
    manager = _CapturingManager()
    _patch_manager(monkeypatch, manager)
    r = logged_in.post("/api/v1/jobs/tune",
                       json={"strategy": "VWAP", "params": {"data_source": "polygon"}})
    assert_error(r, "invalid", 400)
    assert "data_source" in r.get_json()["error"]["message"]
    assert manager.calls == []


# --- GET /jobs/tune/defaults -----------------------------------------------------

def test_defaults_require_auth(client):
    assert_error(client.get("/api/v1/jobs/tune/defaults"), "auth", 401)


def test_defaults_name_the_config_value_and_every_choice(logged_in, default_yfinance):
    body = logged_in.get("/api/v1/jobs/tune/defaults").get_json()
    assert_shape(body, {"data_source": str, "choices": list})
    assert body == {"data_source": "yfinance", "choices": ["alpaca", "yfinance"]}


# --- GET /jobs/<id>/result ---------------------------------------------------------

def _row():
    return {"params": {"a": 1}, "n_eval": 40, "win_rate": 82.0,
            "expectancy_r": 0.4, "excluded_share": 0.2}


def test_a_result_reports_the_source_it_ran_on(logged_in):
    seed_store("tuning", {"job1.json": {"strategy": "RSI", "grid": [_row()],
                                        "data_source": "alpaca",
                                        "provenance": {"data_source": "alpaca"}}})
    body = logged_in.get("/api/v1/jobs/job1/result").get_json()
    assert body["data_source"] == "alpaca"
    assert set(body) == {"job_id", "strategy", "grid", "data_source"}


def test_a_pre_v162_result_reads_as_yfinance(logged_in):
    """Old payloads carry no source; every one of them ran on yfinance."""
    seed_store("tuning", {"job1.json": {"strategy": "RSI", "grid": [_row()]}})
    assert logged_in.get("/api/v1/jobs/job1/result").get_json()["data_source"] == "yfinance"


def test_a_running_job_has_no_source_yet(logged_in):
    body = logged_in.get("/api/v1/jobs/stillgoing/result").get_json()
    assert body["data_source"] is None
```

Modify `$WT/tests/admin/test_jobs.py`: the exact argv now carries the source flag. Replace `test_build_tune_args_passes_be_trigger_through` with:

```python
def test_build_tune_args_passes_be_trigger_through(monkeypatch):
    from swingbot import config
    from swingbot.admin.jobs import build_tune_args
    monkeypatch.setattr(config, "TRAINING_DATA_SOURCE", "alpaca")
    args = build_tune_args("RSI", {"be_trigger": 0.6})
    assert args == ["--strategy", "RSI", "--data-source", "alpaca", "--be-trigger", "0.6"]
```

Modify `$WT/tests/admin/test_api_v1_jobs.py`, in `test_job_result_is_empty_not_404_while_a_job_is_still_running`: the empty response now carries four keys. Replace its `assert_shape` line with:

```python
    assert_shape(body, {"job_id": str, "strategy": type(None), "grid": list,
                        "data_source": type(None)})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_jobs_data_source.py`
Expected: FAIL. `build_tune_args` returns no `--data-source`, `/jobs/tune/defaults` is not routed, and the result has no `data_source` key.

- [ ] **Step 3: Implement**

In `$WT/swingbot/admin/jobs.py`, replace `build_tune_args` (:73-96) with the function below and put the two helpers above it:

```python
def _be_trigger_args(params: dict | None) -> list[str]:
    """`--be-trigger <float>` when params carry one, else nothing."""
    if not params or "be_trigger" not in params:
        return []
    be_trigger = params["be_trigger"]
    try:
        be_trigger = float(be_trigger)
    except (TypeError, ValueError):
        raise ValueError(f"be_trigger must be a number, got {be_trigger!r}")
    return ["--be-trigger", str(be_trigger)]


def _data_source_args(params: dict | None) -> list[str]:
    """`--data-source <v>` (v162): the param when given, else
    TRAINING_DATA_SOURCE read now (it is hot-reloadable). Always emitted, so a
    stored job's argv names the data it ran on even after the default flips."""
    from swingbot.core.marketdata.training_data import DATA_SOURCES

    value = (params or {}).get("data_source") or config.TRAINING_DATA_SOURCE
    if not isinstance(value, str) or value not in DATA_SOURCES:
        raise ValueError(f"data_source must be one of {list(DATA_SOURCES)}, got {value!r}")
    return ["--data-source", value]


def build_tune_args(strategy: str, params: dict | None) -> list[str]:
    """THE only constructor of a tuning job's argv. Whitelists strategy
    against backtest.ALL_STRATEGIES, appends only the flags
    scripts/backtest/tune_strategy.py accepts (--strategy, --data-source
    always, optional --be-trigger), and accepts no date argument at all.
    Every call site (api_v1/jobs.py's POST /jobs/tune) must route through
    this. Also the single place that validates params' own shape -- callers
    only need to catch ValueError, never TypeError, for any malformed input."""
    if strategy not in ALL_STRATEGIES:
        raise ValueError(f"unknown strategy {strategy!r}; must be one of {ALL_STRATEGIES}")
    if params is not None and not isinstance(params, dict):
        raise ValueError(f"params must be a dict or null, got {type(params).__name__}")
    args = ["--strategy", strategy, *_data_source_args(params), *_be_trigger_args(params)]
    assert_train_only(args)
    return args
```

The `isinstance(value, str)` check runs first, so a numeric or list value gives the `ValueError` the API turns into a 400, never a `TypeError`.

In `$WT/swingbot/admin/api_v1/jobs.py`, add `from swingbot import config` to the imports (after `from flask import jsonify, request`), then:

1. Add a helper above `get_job_result`:

```python
def _result_data_source(result: dict) -> str:
    """The training data a stored tuning result ran on (v162). A payload
    written before v162 carries none, and every one of those ran on yfinance."""
    return result.get("data_source") or "yfinance"
```

2. In `get_job_result`, the no-result branch becomes:

```python
        return jsonify({"job_id": job_id, "strategy": None, "grid": [], "data_source": None})
```

and the final `jsonify` gains one key after `"grid": grid,`:

```python
        "data_source": _result_data_source(result),
```

3. After `start_tune_job`, add the route:

```python
@api_v1.route("/jobs/tune/defaults", methods=["GET"])
@require_auth
def tune_defaults():
    """The Tuning launcher's source picker (v162): the configured default and
    every allowed value. Read per request, so a SIGHUP reload of
    TRAINING_DATA_SOURCE shows on the next page load."""
    from swingbot.core.marketdata.training_data import DATA_SOURCES

    return jsonify({"data_source": config.TRAINING_DATA_SOURCE, "choices": list(DATA_SOURCES)})
```

4. In `start_tune_job`, the comment above `return error("invalid", str(exc), 400)` becomes:

```python
        # build_tune_args also enforces TRAIN-only windows and the data_source
        # whitelist. A ValueError here can mean "you asked to tune against the
        # validation window", which is a spent resource -- surface its message
        # rather than a generic one.
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_jobs_data_source.py`
Expected: PASS (19 tests: the bad-source test runs four times).
Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_jobs.py`, then `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_jobs.py`
Expected: PASS, 0 failed each.
Run: `python -m radon cc -s -n C $WT/swingbot/admin/jobs.py $WT/swingbot/admin/api_v1/jobs.py`
Expected: no line for `build_tune_args`, `_be_trigger_args`, `_data_source_args`, `_result_data_source`, `get_job_result` or `tune_defaults`.

- [ ] **Step 5: Commit**

```bash
git -C $WT add swingbot/admin/jobs.py swingbot/admin/api_v1/jobs.py tests/admin/test_jobs_data_source.py tests/admin/test_jobs.py tests/admin/test_api_v1_jobs.py
git -C $WT commit -m "feat(v162): AH16 admin Tuning API chooses its training data and reports it per result"
```

### Task AH17: Admin Tuning frontend: source select and result source

**Model:** sonnet — one extra select, one fetched-once default and one heading suffix over an existing signal store; the test harness patterns are already in the two spec files

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`JobResult` at :993-1001; new `TuneDefaults` after it)
- Modify: `frontend/src/app/api/api-client.ts` (models import list at :7-60; new `getTuneDefaults()` after `startTuneJob` at :330-332)
- Modify: `frontend/src/app/stores/analytics.store.ts` (state interface at :379-400; initial state at :460-471; `loadJob` at :750-770; `loadTuning` at :772-795; `startTune` at :991-1018)
- Modify: `frontend/src/app/workspaces/analytics/tabs/tuning.ts` (imports at :1-26; launcher template at :52-91; `launch()` at :360-363; `gridHeading` at :402-405)
- Modify: `frontend/src/app/workspaces/analytics/tabs/tuning.spec.ts`
- Modify: `frontend/src/app/stores/analytics.store.spec.ts` (the `openTuning` helper at :257-276; the launch test at :593-612)
- Modify: `frontend/src/app/stores/analytics.snapshot.spec.ts` (`GRID` at :93; `openTuning` at :121-139)

The two store spec files are not in the ledger row. Their `openTuning` helpers settle every request the Tuning tab makes, and the launch test pins the old POST body, so this task has to update them.

**Interfaces:**
- Consumes (AH16): `GET /api/v1/jobs/tune/defaults` → `{"data_source": str, "choices": str[]}`; `POST /api/v1/jobs/tune` body `{"strategy", "params": {"data_source"}}` (absent `params.data_source` means the server's default); `GET /api/v1/jobs/<id>/result` key `data_source` (`"yfinance"` for a pre-v162 result, `null` while running).
- Produces (ledger AH17): `TuneDefaults { data_source: string; choices: string[] }`; `JobResult.data_source: string | null`; `ApiClient.getTuneDefaults(): Observable<TuneDefaults>`; `AnalyticsStore.startTune(strategy: string, dataSource: string)` (an empty `dataSource` sends no `params`); store state `tuneDefaults: TuneDefaults | null` and `gridDataSource: string | null`.

**Rules this task freezes (spec §3 "The admin Tuning page", Acceptance 6):**
- **The launcher offers the source; the default comes from the server.** The defaults are fetched once per store, on the first Tuning load, never on each `jobs` event (a running grid raises one per log flush).
- **The default is the first option.** `sb-select` binds `[value]` before its `@for` renders the options, so a browser shows the first option until the user picks one. Putting the server's default first keeps what is shown and what is sent the same. It is labelled `(default)`.
- **No defaults, no picker.** If `/jobs/tune/defaults` fails, the picker is hidden, Launch still works, and the POST carries no `params`: the server then applies `TRAINING_DATA_SOURCE` itself (AH16). The failure is quiet, like the result fetch's.
- **Each result shows its source.** The grid heading reads `Grid results — <strategy> · training data: <source>`. A pre-v162 result shows `yfinance` because AH16 reports it that way.
- **Still no date input.** The help text keeps the TRAIN firewall wording, and the new sentence says the data choice grants no validation run.

- [ ] **Step 1: Write the failing tests**

In `$WT/frontend/src/app/workspaces/analytics/tabs/tuning.spec.ts`:

1. Import `TuneDefaults` beside `AnalyticsStrategies`:

```ts
import { AnalyticsStrategies, TuneDefaults } from '../../../api/models';
```

2. Add two members to `StoreStub` (after `gridStrategy`):

```ts
  gridDataSource: WritableSignal<string | null>;
  tuneDefaults: WritableSignal<TuneDefaults | null>;
```

and to `storeStub()`'s object (after `gridStrategy: signal(null),`):

```ts
    gridDataSource: signal(null),
    tuneDefaults: signal({ data_source: 'alpaca', choices: ['alpaca', 'yfinance'] }),
```

3. The first test now reads only the strategy select's options. Replace its `options` line with:

```ts
    const options = [...el.querySelector('sb-select')!.querySelectorAll('option')].map((o) => o.textContent!.trim());
```

4. In `'launches the picked strategy and hides the form while a job is queued or running'`, the launch now carries the source:

```ts
    expect(store.startTune).toHaveBeenCalledWith('RSI', 'alpaca');
```

5. Add these tests at the end of the `describe` block:

```ts
  /* -- v162: training data --------------------------------------------- */

  function sourceSelect(el: HTMLElement): HTMLSelectElement {
    return el.querySelectorAll<HTMLSelectElement>('sb-select select')[1];
  }

  function pickStrategy(fixture: { detectChanges(): void }, el: HTMLElement, value: string) {
    const select = el.querySelector<HTMLSelectElement>('sb-select select')!;
    select.value = value;
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
  }

  function launchButton(el: HTMLElement): HTMLButtonElement {
    return [...el.querySelectorAll('button')].find((b) => b.textContent!.includes('Launch TRAIN grid'))!;
  }

  it('offers the training data with the server default first and preselected', () => {
    const store = storeStub({ tuneDefaults: signal({ data_source: 'yfinance', choices: ['alpaca', 'yfinance'] }) });
    const { el } = render(store);
    const select = sourceSelect(el);
    const labels = [...select.querySelectorAll('option')].map((o) => o.textContent!.trim());
    expect(labels).toEqual(['yfinance cache (default)', 'Alpaca history store']);
    expect(select.value).toBe('yfinance');
    expect(el.textContent).toContain('Training data');
  });

  it('launches with the source the user picked', () => {
    const store = storeStub();
    const { fixture, el } = render(store);
    pickStrategy(fixture, el, 'MACD');
    const source = sourceSelect(el);
    source.value = 'yfinance';
    source.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    launchButton(el).click();
    expect(store.startTune).toHaveBeenCalledWith('MACD', 'yfinance');
  });

  it('hides the source picker when the defaults never arrived, and still launches', () => {
    const store = storeStub({ tuneDefaults: signal(null) });
    const { fixture, el } = render(store);
    expect(el.querySelectorAll('sb-select')).toHaveLength(1);
    pickStrategy(fixture, el, 'RSI');
    launchButton(el).click();
    // An empty source: the server applies TRAINING_DATA_SOURCE itself.
    expect(store.startTune).toHaveBeenCalledWith('RSI', '');
  });

  it('names the training data a grid was measured on in its heading', () => {
    const { el } = render(storeStub({
      grid: signal([gridRow()]), gridStrategy: signal('RSI'), gridDataSource: signal('alpaca'),
    }));
    expect(el.textContent).toContain('Grid results — RSI · training data: alpaca');
  });
```

In `$WT/frontend/src/app/stores/analytics.store.spec.ts`:

1. Add a constant after `FINISHED_JOB`:

```ts
const TUNE_DEFAULTS = { data_source: 'alpaca', choices: ['alpaca', 'yfinance'] };
```

2. In `openTuning`, settle the defaults request right after `respondStrategies();`:

```ts
    // v162: the launcher's source picker, fetched once on the first Tuning load.
    backend.expectOne('/api/v1/jobs/tune/defaults').flush(TUNE_DEFAULTS);
```

3. In `'launches a TRAIN grid and reloads the tuning view'`, replace `store.startTune('RSI');` and the body assertion with:

```ts
    store.startTune('RSI', 'yfinance');
    const posted = backend.expectOne('/api/v1/jobs/tune');
    expect(posted.request.method).toBe('POST');
    // Strategy and training data. No date argument exists, because the window
    // is TRAIN and the server refuses anything else.
    expect(posted.request.body).toEqual({ strategy: 'RSI', params: { data_source: 'yfinance' } });
```

4. In `'reports a launch conflict separately from a stale-data error'`, replace `store.startTune('RSI');` with `store.startTune('RSI', 'alpaca');`.

5. Add after the launch test:

```ts
  it('sends no params when no source was chosen, so the server default applies', () => {
    tick();
    respondOverview();
    openTuning([]);

    store.startTune('RSI', '');
    const posted = backend.expectOne('/api/v1/jobs/tune');
    expect(posted.request.body).toEqual({ strategy: 'RSI' });
  });

  it('fetches the tuning defaults once, not on every jobs event', () => {
    tick();
    respondOverview();
    openTuning();
    expect(store.tuneDefaults()).toEqual(TUNE_DEFAULTS);

    events.raise('jobs');
    store.load();
    respondJobs([RUNNING_JOB]);
    respondProposals();
    backend.expectOne('/api/v1/jobs/abc123').flush({ ...RUNNING_JOB, log_tail: '' });
    backend.expectNone('/api/v1/jobs/tune/defaults');
  });
```

In `$WT/frontend/src/app/stores/analytics.snapshot.spec.ts`:

1. `GRID` gains `data_source: 'alpaca',` after `strategy: 'RSI Divergence',`.
2. In `openTuning`, after the strategies `expectOne(...).flush(...)` line, add:

```ts
    backend.expectOne('/api/v1/jobs/tune/defaults')
      .flush({ data_source: 'alpaca', choices: ['alpaca', 'yfinance'] });
```

3. Add after `'fetches the tracked job result and reads its rows'`:

```ts
  it('reads which training data the grid ran on', () => {
    openTuning();
    expect(store.gridDataSource()).toBe('alpaca');
  });

  it('has no grid source while a job is still running', () => {
    openTuning({ job_id: 'job1', strategy: null, grid: [], data_source: null });
    expect(store.gridDataSource()).toBeNull();
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/tuning.spec.ts --include src/app/stores/analytics.store.spec.ts --include src/app/stores/analytics.snapshot.spec.ts`
Expected: FAIL. TypeScript reports `TuneDefaults` missing from `models`, `startTune` called with two arguments, and `tuneDefaults` / `gridDataSource` unknown on the store. (If `--include` is rejected by this builder version, run the same command without the three `--include` flags.)

- [ ] **Step 3: Implement**

`$WT/frontend/src/app/api/models.ts`: replace `JobResult` and add `TuneDefaults` after it:

```ts
/** `GET /jobs/:id/result` — a finished tuning job's grid.
 *
 *  `strategy` is null and `grid` empty while the job is still running: the
 *  endpoint answers 200 with the same keys either way, so nothing here has to
 *  branch on which shape arrived (SR51). `data_source` (v162) is the training
 *  data the grid ran on: `"yfinance"` for a result written before v162, null
 *  while there is no result yet. */
export interface JobResult {
  job_id: string;
  strategy: string | null;
  grid: unknown[];
  data_source: string | null;
}

/** `GET /jobs/tune/defaults` (v162) — the launcher's training-data picker:
 *  the server's TRAINING_DATA_SOURCE and every value it accepts. */
export interface TuneDefaults {
  data_source: string;
  choices: string[];
}
```

`$WT/frontend/src/app/api/api-client.ts`: add `TuneDefaults` to the `./models` import list (keep its alphabetical order), and after `startTuneJob`:

```ts
  /** v162 — the Tuning launcher's training-data default and choices. */
  getTuneDefaults(): Observable<TuneDefaults> {
    return this.http.get<TuneDefaults>(`${this.base}/jobs/tune/defaults`);
  }
```

`$WT/frontend/src/app/stores/analytics.store.ts`:

1. Add `TuneDefaults` to the `'../api/models'` import list (after `BookScope`).
2. In the state interface, after `gridStrategy: string | null;`:

```ts
  /** v162 — the training data the tracked job's grid ran on. */
  gridDataSource: string | null;
  /** v162 — the launcher's source picker. Fetched once: the default only
   *  changes on a config reload, and a running grid raises a `jobs` event per
   *  log flush. Null until it arrives, or when it failed (picker hidden). */
  tuneDefaults: TuneDefaults | null;
```

3. In the initial state, after `gridStrategy: null,`:

```ts
      gridDataSource: null,
      tuneDefaults: null,
```

4. In `loadJob`'s `api.jobResult(id)` subscription, the two `patchState` calls become:

```ts
        next: (result) =>
          patchState(store, {
            gridStrategy: result.strategy,
            gridDataSource: result.data_source ?? null,
            grid: toGridRows(result.grid ?? []),
          }),
```

```ts
        error: () => patchState(store, { grid: [], gridStrategy: null, gridDataSource: null }),
```

5. Above `loadTuning`, add:

```ts
    /** v162. Quiet on failure, like the result fetch: without defaults the
     *  picker is hidden and the server applies its own default. */
    const loadTuneDefaults = (): void => {
      api.getTuneDefaults().subscribe({
        next: (defaults) => patchState(store, { tuneDefaults: defaults }),
        error: () => undefined,
      });
    };
```

and at the end of `loadTuning`, after `if (store.strategies() === null) loadStrategies();`:

```ts
      if (store.tuneDefaults() === null) loadTuneDefaults();
```

6. Replace `startTune` and its comment with:

```ts
      /**
       * Launch a TRAIN-window grid search on the chosen training data (v162).
       *
       * No date argument is sent, and none can be: `build_tune_args` accepts
       * only `--strategy`, `--data-source` and an optional `--be-trigger`, and
       * asserts the window is TRAIN. That firewall keeps the VALIDATION badges
       * on the Strategies tab meaningful, so the UI offers a strategy and a
       * data source and nothing else. An empty `dataSource` sends no params:
       * the server then uses TRAINING_DATA_SOURCE.
       */
      startTune(strategy: string, dataSource: string): void {
        patchState(store, { launching: true, launchError: null });
        const body = dataSource ? { strategy, params: { data_source: dataSource } } : { strategy };
        api.startTuneJob(body).subscribe({
```

Everything from `next: () => {` to the end of the method stays as it is.

`$WT/frontend/src/app/workspaces/analytics/tabs/tuning.ts`:

1. Add `linkedSignal` to the `@angular/core` import list.
2. In the launcher's first `section-help` paragraph, append after `...anywhere in this workbench.`:

```html
        Training data defaults to the server's setting; the choice is recorded
        with the job, shown on its results, and grants no validation run.
```

3. In the `<sb-control-row class="launch">`, between the strategy `<sb-select ... />` and the Launch button:

```html
          @if (dataSourceOptions().length) {
            <sb-select
              label="Training data"
              [(value)]="dataSource"
              [options]="dataSourceOptions()"
            />
          }
```

4. After `protected readonly strategyOptions = ...;` add:

```ts
  /** v162. Seeded from the server's default and re-seeded if that changes;
   *  the user's pick overrides it until then. */
  protected readonly dataSource = linkedSignal(() => this.store.tuneDefaults()?.data_source ?? '');

  /** The server's default first: `sb-select` binds its value before its
   *  options render, so the browser shows the first option until a pick, and
   *  that has to be the value `dataSource` holds. */
  protected readonly dataSourceOptions = computed(() => {
    const defaults = this.store.tuneDefaults();
    if (!defaults) return [];
    const ordered = [defaults.data_source, ...defaults.choices.filter((c) => c !== defaults.data_source)];
    return ordered.map((value) => ({
      value,
      label: (SOURCE_LABELS[value] ?? value) + (value === defaults.data_source ? ' (default)' : ''),
    }));
  });
```

5. `launch()` becomes:

```ts
  protected launch(): void {
    const strategy = this.strategy();
    if (strategy) this.store.startTune(strategy, this.dataSource());
  }
```

6. `gridHeading` becomes:

```ts
  protected readonly gridHeading = computed(() => {
    const strategy = this.store.gridStrategy();
    const source = this.store.gridDataSource();
    const head = strategy ? `Grid results — ${strategy}` : 'Grid results';
    return source ? `${head} · training data: ${source}` : head;
  });
```

7. Above `function attach<T>(` at the bottom, add:

```ts
/** v162 picker labels. An unknown value from a newer server shows as-is. */
const SOURCE_LABELS: Record<string, string> = {
  alpaca: 'Alpaca history store',
  yfinance: 'yfinance cache',
};
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/workspaces/analytics/tabs/tuning.spec.ts --include src/app/stores/analytics.store.spec.ts --include src/app/stores/analytics.snapshot.spec.ts`
Expected: PASS, 0 failed (tuning.spec 16 tests, both store specs green). A 60-second `Timeout waiting for worker` with `no tests` is load: re-run it.
Run: `npm --prefix $WT/frontend exec -- ng build`
Expected: build succeeds with no type error (catches a template binding the spec stubs could miss).

- [ ] **Step 5: Commit**

```bash
git -C $WT add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/stores/analytics.store.ts frontend/src/app/stores/analytics.store.spec.ts frontend/src/app/stores/analytics.snapshot.spec.ts frontend/src/app/workspaces/analytics/tabs/tuning.ts frontend/src/app/workspaces/analytics/tabs/tuning.spec.ts
git -C $WT commit -m "feat(v162): AH17 Tuning tab picks the training data and shows it on each grid"
```

# Phase E: docs, routing, ops scripts

### Task AH18: Docs: three stores, research discipline, Codex mirror

**Model:** haiku — exact text replacements given below, verified by greps and the existing doc-shape tests; no code behaviour changes

**Files:**
- Modify: `docs/claude/known-traps.md` (§ Two OHLCV caches, :7-44)
- Modify: `docs/claude/architecture.md` (:17-18)
- Modify: `docs/claude/backtest-methodology.md` (§ Windows :6-12; the ledger paragraph ending before "**The v72 procedure change does not reopen anything below.**")
- Modify: `docs/claude/skills-tools.md` (:208, the `quant-engineer` row)
- Modify: `AGENTS.md` (:261; one new paragraph at the end of `## Decision standards`)
- Modify: `CLAUDE.md` (:186, the `known-traps.md` table row; the line count must not change)
- Modify: `scripts/data/fetch_backtest_data.py` (module docstring :2-30), `scripts/data/validate_data.py` (docstring :4-8), `swingbot/core/marketdata/spot_metals.py` (docstring :10-13)

**Interfaces:**
- Consumes: the finished behaviour of AH1–AH17 as the ledger and AH10 state it. Names quoted in the text: `history_store.py`, `training_data.py`, `TRAINING_DATA_SOURCE`, `--data-source`, `BACKTEST_CACHE_DIR`, `--cache-dir`, `<out>.provenance.json`, `scripts/data/fetch_alpaca_history.py`, `scripts/data/check_history_store.py`, `scripts/ops/install_v162_history_cron.sh`, `scripts/ops/pull_history_store.sh`, `OPTIONAL_LEDGER_FIELDS`, `get_badge`.
- Produces: nothing code consumes.

**Rules this task freezes (spec § Docs and tests this changes, § Research discipline):**
- **The heading `## Two OHLCV caches` and the first-bullet prefix `- **Two parallel OHLCV cache subsystems` stay verbatim.** `tests/hooks/test_doc_sections.py:36` pins both, and the `data-check`, `alert-surface` and `no-lookahead` skills read the section by that heading through `doc_section.py`. The section's content becomes three stores; its name does not change.
- **The two `market_data` paths are named apart every time.** `data/market_data/` (the v162 history store, research only) and the root `market_data/` (the live cache, `data_store.py`) share folder names (`daily`, `hourly`, `15min`). Every new sentence says which one it means.
- `CLAUDE.md` stays under 200 lines: the edit replaces words inside one existing line.
- `AGENTS.md` gets the condensed version only, in the same commit (Codex mirror rule).
- No skill file changes. The `quant-engineer`, `alert-surface` and `no-lookahead` skill texts still say "two OHLCV caches"; their pointer (the section heading) still resolves, and editing skills would also need `python scripts/dev/sync_codex.py`, outside this task's ledger row.

- [ ] **Step 1: Write the failing check**

Run each; every one must print `0` now:

```bash
git -C $WT grep -c "Alpaca history store is the third store" -- docs/claude/known-traps.md
git -C $WT grep -c "A new data source resets no budget" -- docs/claude/backtest-methodology.md
git -C $WT grep -c "Training data (v162)" -- AGENTS.md
git -C $WT grep -c "the v162 Alpaca history store" -- docs/claude/architecture.md
```

(`git grep -c` prints nothing and exits 1 when there is no match; that is the failing state.)

- [ ] **Step 2: Edit `docs/claude/known-traps.md`**

1. In the first bullet, replace the sentence `Both are gitignored.` with:

```markdown
  Both are gitignored. A third, research-only store joined them in v162
  (next bullet); it is the training data, not a cache.
```

2. Insert this bullet directly after the first bullet (before `- **Spot metals are never cached under their own name (v109).**`):

```markdown
- **The Alpaca history store is the third store (v162), and the training data.**
  `data/market_data/{15min,hourly,daily}/{TICKER}.csv` sits under `data/`; it
  is NOT the root `market_data/` live cache, although the folder names match.
  Written only by `scripts/data/fetch_alpaca_history.py` (the VM backfill and
  the Sunday `--mode update` cron, `scripts/ops/install_v162_history_cron.sh`),
  read only through `core/marketdata/history_store.py` and
  `core/marketdata/training_data.py`. The live scan, `data_refresh` and
  `backtest_cache.ensure_cached` never touch it. SIP tape, `Adjustment.ALL`,
  from 2016-01-04 or listing. Intraday index = naive America/New_York
  wall-clock bar start (`Datetime`), daily = naive date (`Date`). `15min`
  stores all sessions and readers keep regular hours unless asked for
  `session="all"`; `hourly` is built from 30-minute bars, 09:30-anchored, and
  its last bar (15:30-16:00) is a half-hour. Each timeframe has a
  `_manifest.json` (per-ticker status, rows, SHA-256, identity check against
  `data/backtest_cache/`); `scripts/data/check_history_store.py` checks row
  counts against SPY's calendar and `--verify-hashes` the files. An update
  that sees any stored daily close move (a new split or dividend rescales the
  whole `Adjustment.ALL` history) refetches all three timeframes of that
  ticker together.
- **Which data a backtest reads is one switch (v162).** `TRAINING_DATA_SOURCE`
  (`alpaca` default, `yfinance`) is read by `fetch_backtest_data.load_cached`
  and `backtest_wf._frame_for`, so every training reader follows it;
  `--data-source` overrides it per run and `TRAINING_DATA_SOURCE=yfinance` in
  `.env` rolls everything back. Two cases mean yfinance without being told:
  env `BACKTEST_CACHE_DIR` set (the ext-cache screens and the v162 snapshot
  legs) and an explicit `--cache-dir`. `alpaca` with no `daily` manifest
  (a worktree, CI, a fresh checkout) **stops with an error naming the path**,
  never a zero-ticker run: pass `--data-source yfinance` or pull the store with
  `scripts/ops/pull_history_store.sh`. Tickers whose manifest status is not
  `ok` are left out, printed and written to the `<out>.provenance.json`
  sidecar next to every `--json` result. A run never mixes sources.
  `data/backtest_cache/` stays: it is the live bot's daily cache, the journal
  backfill's source, the `yfinance` training source and the identity-check
  reference.
- **The history store holds the same tickers as `data/backtest_cache/`:** the
  watchlist plus `MARKET_REGIME_TICKER`. The sector ETFs of
  `data/universe/etfs.json` (QQQ, IWM, DIA, the XL* funds, GLD, TLT) are in
  it only when they are on the watchlist, exactly as in `data/backtest_cache/`,
  so `run_backtest_range`'s sector-relative context is equally thin on either
  source. The weekly update follows the current watchlist: a ticker dropped
  from it stops updating and `check_history_store.py` reports it as ending
  early; a ticker fetched once with `--tickers` is not kept current unless the
  cron line names it too.
```

3. In the last bullet of the section (`- **Yahoo's intraday depth is a hard ceiling, not a tuning knob.**`), append after `Do not write a task that assumes otherwise.`:

```markdown
  The research way past it is the v162 history store: Alpaca's SIP 15m and
  1h bars back to 2016 (training only, never the live scan).
```

- [ ] **Step 3: Edit `architecture.md`, `backtest-methodology.md`, `skills-tools.md`**

`docs/claude/architecture.md`: replace `(fetching and caching, both OHLCV caches together)` with:

```markdown
(fetching and caching: both OHLCV caches, the v162 Alpaca history store
  `history_store.py` and the training-data switch `training_data.py`)
```

`docs/claude/backtest-methodology.md`:

1. In `## Windows`, add a second bullet after the `- **Windows:** TRAIN = ...` bullet (which stays first: `test_doc_sections.py` pins it):

```markdown
- **A new data source resets no budget (v162).** A validation shot spent on
  yfinance bars stays spent: `--data-source` on `--validation` gives no
  component a second run, and 2024-2025 stays tainted. Every closed
  pre-registration stays closed on Alpaca bars too (the same hypothesis on a
  new dataset; v122, v127, v129, v135, v139 and v143 included). The v162
  re-baseline describes a data change, is never quoted as a lift and decides
  nothing: no switching back, no per-ticker or per-strategy source. Each new
  pre-registration names its `data_source` in its frozen block before TRAIN
  is read.
```

2. Insert this paragraph between the `**Pre-registration ledger (v136 §4).**` paragraph and `**The v72 procedure change does not reopen anything below.**`:

```markdown
**Data source on registry and ledger rows (v162).** New registry rows carry
`data_source` and merge on `(source, strategy, horizon, data_source)`, so the
yfinance and Alpaca populations sit side by side. New ledger rows may carry
the optional field `data_source` (`OPTIONAL_LEDGER_FIELDS`). A row without
the field means `yfinance`; old rows are never rewritten. `get_badge` takes
the row of the active `TRAINING_DATA_SOURCE`, falls back to the `yfinance`
row, logs which one it used, and never blends the two. Every `--json` result
has a `<out>.provenance.json` sidecar (source, feed, adjustment, manifest
hash, excluded tickers); the result JSON's own shape is unchanged.
```

`docs/claude/skills-tools.md` :208: in the `quant-engineer` row replace `the two OHLCV caches` with `the OHLCV caches and the v162 training-data store`.

- [ ] **Step 4: Edit `AGENTS.md` and `CLAUDE.md`**

`AGENTS.md` :261: replace `the two OHLCV caches` with `the OHLCV caches and training-data store`. Then add this paragraph at the end of `## Decision standards` (after the paragraph ending `` `Edge: harvest`, not cosmetics (`edge-priorities.md`). ``):

```markdown
**Training data (v162).** Backtests and grids read `TRAINING_DATA_SOURCE`
(default `alpaca`: the Alpaca history store under `data/market_data/`, not the
root `market_data/` live cache). `--data-source yfinance` or that `.env` line
rolls back; `BACKTEST_CACHE_DIR` or an explicit `--cache-dir` means yfinance.
A missing store is an error, never an empty run. A new data source resets no
validation budget and reopens no closed pre-registration; each new
pre-registration names its `data_source`. Detail: `known-traps.md` § Two OHLCV
caches, `backtest-methodology.md` § Windows.
```

`CLAUDE.md` :186: in the `known-traps.md` row replace `two OHLCV caches` with `OHLCV caches and the training-data store`. Nothing else in `CLAUDE.md` changes.

- [ ] **Step 5: Edit the three docstrings**

`scripts/data/fetch_backtest_data.py`: after the first docstring paragraph (ending `pass --force (or delete the folder) to overwrite and re-fetch.`), insert:

```text
v162: `load_cached` (imported by most backtest scripts) no longer reads this
cache directly. It returns `training_data.load_daily`, which reads the
selected training data: the Alpaca history store (data/market_data/, the
default) or this cache (`--data-source yfinance`, TRAINING_DATA_SOURCE=yfinance,
or BACKTEST_CACHE_DIR set). This script still writes only
data/backtest_cache/ (or BACKTEST_CACHE_DIR); the history store has its own
writer, scripts/data/fetch_alpaca_history.py.
```

`scripts/data/validate_data.py`: replace `--universe flag -- two caches exist in this repo and they are NOT unified:` with:

```text
--universe flag -- two caches exist in this repo and they are NOT unified
(v162 added a third store, data/market_data/, which
scripts/data/check_history_store.py checks instead):
```

`swingbot/core/marketdata/spot_metals.py`: replace `Cache rule (docs/claude/known-traps.md, two OHLCV caches): only the raw` with `Cache rule (docs/claude/known-traps.md § Two OHLCV caches): only the raw`, and add after the paragraph's last line (`ratio into every later day's levels.`):

```text
The v162 Alpaca history store never holds a spot metal either: its backfill
marks XAUUSD / XAGUSD `skipped: spot metal (built from futures)`.
```

- [ ] **Step 6: Verify**

Re-run the four `git -C $WT grep -c` commands of Step 1: each now prints `1` (or more).
Run: `python $WT/scripts/dev/doc_section.py $WT/docs/claude/known-traps.md "Two OHLCV caches"`
Expected: prints the section with the three new bullets.
Run: `python $WT/scripts/dev/testrun.py file tests/hooks/test_doc_sections.py`, `... file tests/hooks/test_codex_mirror.py`, `... file tests/hooks/test_guardrails.py`, `... file tests/dev/test_doc_section.py`, `... file tests/hooks/test_role_skills.py`
Expected: PASS, 0 failed each.
Run: `wc -l $WT/CLAUDE.md` → `199` (unchanged, under 200).
Run: `python -m py_compile $WT/scripts/data/fetch_backtest_data.py $WT/scripts/data/validate_data.py $WT/swingbot/core/marketdata/spot_metals.py` → no output.

- [ ] **Step 7: Commit**

```bash
git -C $WT add docs/claude/known-traps.md docs/claude/architecture.md docs/claude/backtest-methodology.md docs/claude/skills-tools.md AGENTS.md CLAUDE.md scripts/data/fetch_backtest_data.py scripts/data/validate_data.py swingbot/core/marketdata/spot_metals.py
git -C $WT commit -m "docs(v162): AH18 three OHLCV stores, the training-data switch and its research discipline; Codex mirror"
```

### Task AH19: `DATA_READERS` row and `.gitignore` snapshot pattern

**Model:** haiku — one table row and one ignore line, each pinned by a test against the real repo

**Files:**
- Modify: `scripts/dev/select_tests.py` (`DATA_READERS` at :247-293; one row before the closing `)`)
- Modify: `.gitignore` (the "Data directories" block at :28-35, after `data/backtest_cache_ext/`)
- Test: `tests/history_store/test_routing.py`

**Interfaces:**
- Consumes: `tests/history_store/test_history_store.py` (AH2) and `tests/history_store/test_training_data.py` (AH10) must exist (a missing target widens to the full suite, `select_tests._data_targets`). Existing: `select_tests.select(changed, repo) -> Selection` (`.full`, `.targets`, `.reason`), `select_tests._threshold_reason`.
- Produces (ledger AH19): `DATA_READERS` row `("data/market_data/", ("tests/history_store/test_history_store.py", "tests/history_store/test_training_data.py"))`; `.gitignore` line `data/backtest_cache_snapshot_v162*/` (covers AH23/AH24's frozen yfinance snapshot and its 2016-truncated copy).

**Rules this task freezes (spec § Docs and tests this changes; Amendments last bullet):**
- The row is a prefix key (ends in `/`), so any file under the store routes to the two reader tests. `data/` is gitignored, so the row only fires when a path is handed to `select()` by name; it exists so a test that names a store path (`test_no_path_a_test_reads_is_classified_inert`) is routed, never classified inert.
- The spec's "history_store fixtures" need no row of their own: every `tests/history_store/` test builds its store in `tmp_path` (index, "Where to work"), so there is no fixture data file to route.
- `data/market_data/` itself is already ignored by the unanchored `market_data/` line (`.gitignore:31`); the test proves it rather than adding a second line.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/history_store/test_routing.py`:

```python
"""v162 AH19: the history store routes to its reader tests, and neither the
store nor the frozen snapshot can ever be committed."""
import importlib.util
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
READERS = ["tests/history_store/test_history_store.py",
           "tests/history_store/test_training_data.py"]


@pytest.fixture(scope="module")
def sel():
    spec = importlib.util.spec_from_file_location(
        "select_tests_v162", REPO / "scripts" / "dev" / "select_tests.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # @dataclass resolves annotations through sys.modules
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", [
    "data/market_data/daily/AAPL.csv",
    "data/market_data/15min/_manifest.json",
])
def test_a_store_path_selects_its_reader_tests(sel, monkeypatch, path):
    # The threshold can only widen; stubbing it keeps the check about routing.
    monkeypatch.setattr(sel, "_threshold_reason", lambda *_a: None)
    result = sel.select([path], REPO)
    assert (result.full, result.targets) == (False, READERS)


def test_the_root_live_cache_is_not_routed_as_the_store(sel):
    """`market_data/` (live, data_store.py) and `data/market_data/` (v162) share
    folder names; only the second one is the history store."""
    assert sel._readers_of("market_data/daily/AAPL.csv") == ()


@pytest.mark.parametrize("path", [
    "data/market_data/daily/AAPL.csv",
    "data/backtest_cache_snapshot_v162/AAPL.csv",
    "data/backtest_cache_snapshot_v162/_hashes.json",
    "data/backtest_cache_snapshot_v162_2016/AAPL.csv",
])
def test_store_and_snapshot_are_gitignored(path):
    rc = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", path]).returncode
    assert rc == 0, f"{path} is not ignored"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_routing.py`
Expected: FAIL. The two routing cases widen to the full suite (`data/market_data/daily/AAPL.csv is not placeable by an import graph`), and the three snapshot paths are not ignored. The root-cache case and the `data/market_data/` ignore case already pass.

- [ ] **Step 3: Implement**

In `$WT/scripts/dev/select_tests.py`, add as the last row of `DATA_READERS`, after the `docs/superpowers/results/` row:

```python
    # The v162 Alpaca history store (data/market_data/, NOT the root
    # market_data/ live cache): history_store reads it, training_data selects
    # it. Gitignored, so this fires only when a path is named explicitly.
    ("data/market_data/", ("tests/history_store/test_history_store.py",
                           "tests/history_store/test_training_data.py")),
```

In `$WT/.gitignore`, after the `data/backtest_cache_ext/` line:

```gitignore
# v162 section 5: the frozen yfinance inputs of the re-baseline (and its
# 2016-truncated copy), rebuilt by scripts/data/snapshot_backtest_cache.py.
data/backtest_cache_snapshot_v162*/
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_routing.py`
Expected: PASS (7 tests).
Run: `python $WT/scripts/dev/testrun.py file tests/dev/test_select_tests.py`
Expected: PASS, 0 failed (includes `test_no_path_a_test_reads_is_classified_inert` over the real repo).

- [ ] **Step 5: Commit**

```bash
git -C $WT add scripts/dev/select_tests.py .gitignore tests/history_store/test_routing.py
git -C $WT commit -m "chore(v162): AH19 route data/market_data/ to its reader tests; ignore the re-baseline snapshot"
```

### Task AH20: Ops scripts: weekly cron installer, pull with hash verify

**Model:** sonnet — two bash scripts on established repo patterns (`install_intraday_coverage_cron.sh`, `pull_backups.sh`) with shape tests; the VM-facing rules are fixed below

**Files:**
- Create: `scripts/ops/install_v162_history_cron.sh`
- Create: `scripts/ops/pull_history_store.sh`
- Test: `tests/history_store/test_ops_scripts.py`

**Interfaces:**
- Consumes (AH8): `python scripts/data/fetch_alpaca_history.py --mode update` (exit 0 ok, 1 guard refused, 2 auth error; default tickers = watchlist + `MARKET_REGIME_TICKER`; default root = `history_store.store_root()` = `/app/data/market_data` in the container). (AH9): `python scripts/data/check_history_store.py [--root DIR] --verify-hashes`, whose last line is `check: <n> unexplained gap(s), <m> hash problem(s)` and whose hash problems are lines starting `HASH `. Existing: `scripts/ops/ssh-hetzner.sh` (uncommitted wrapper, `bash "$SSH_HETZNER" "bash -s -- <args>"` with the script on stdin), the `./data:/app/data` bind mount (`docker-compose.yml:140`), `SWING_BOT_IMAGE` in the VM's `.env` (written by `deploy/deploy.sh:198`; compose reads it from `/opt/swing-bot/.env` for interpolation, so `compose run` uses the deployed image).
- Produces (ledger AH20, used by AH22 and AH25): cron `30 6 * * 0` (Sunday 06:30 UTC) running `docker compose run --rm -T bot python scripts/data/fetch_alpaca_history.py --mode update`, then `docker compose run --rm -T bot python scripts/data/check_history_store.py --verify-hashes`, logged to `/opt/swing-bot/logs/history_store_cron.log`, under the marker `# v162 alpaca history store weekly update (installed by install_v162_history_cron.sh)`; `bash scripts/ops/pull_history_store.sh [--probe]`.

**Rules this task freezes (spec §2 weekly cron, §4 pulling, Acceptance 8; production rule):**
- **`compose run --rm`, never `exec`.** The update gets its own container instead of sharing the CPU-capped live bot (`docker-compose.yml:118`). Sunday 06:30 UTC is outside every US session, and the script's own hours guard would refuse otherwise.
- **The check runs after the update and both exit codes are logged.** A non-zero check (an unexplained gap, such as a ticker dropped from the watchlist that has stopped updating, or a hash mismatch) is a line in the log, not a page; AH25 records where to read it.
- **The installer is idempotent.** It drops any earlier line carrying the marker or `fetch_alpaca_history.py --mode update`, then writes its two lines. It runs on the VM as root: `bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v162_history_cron.sh`. Installing it is AH25's step, after the merge, because the cron needs the deployed image.
- **The pull reaches the VM only through the wrapper**, with the remote script on stdin and plain-word arguments (an inline `$(...)` would expand in WSL first). Binary data crosses as `tar czf - | base64 -w0` (the `pull_backups.sh` transport), one timeframe per stream, so a failed stream costs one timeframe.
- **The pull writes `data/market_data/` of the MAIN tree** (the parent of git's common dir, as `pull_backups.sh` does), never the root `market_data/` live cache and never a worktree. It extracts into `data/market_data.partial/`, verifies every file against the manifest hashes with `check_history_store.py --verify-hashes`, and only then swaps it in (the previous copy is kept as `data/market_data.prev/` until the next pull). A hash problem leaves `.partial` in place and exits 1. Unexplained row-count gaps are printed, not fatal: they are AH21's acceptance question, not the transport's.
- **`--probe`** streams one small file (`daily/_manifest.json`) and compares its SHA-256 with the VM's, so the binary path through WSL is proven on a few KB before 1.2 GB (the code brief flags it as unverified).
- **The remote side only reads.** No `rm`, no write redirect, no `docker` in the pull's remote script.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/history_store/test_ops_scripts.py`:

```python
"""v162 AH20: the weekly update cron installer and the store pull. Both reach
the VM, so what is pinned is what an edit could silently break."""
import os
import pathlib
import re
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
OPS = REPO / "scripts" / "ops"
INSTALL = OPS / "install_v162_history_cron.sh"
PULL = OPS / "pull_history_store.sh"
MARKER = "# v162 alpaca history store weekly update (installed by install_v162_history_cron.sh)"


def _text(path):
    return path.read_text(encoding="utf-8")


def _remote_block(src):
    return src[src.index("<<'REMOTE_EOF'"):src.index("\nREMOTE_EOF")]


@pytest.mark.parametrize("path", [INSTALL, PULL])
def test_house_rules(path):
    src = _text(path)
    assert src.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in src
    assert "sed -i" not in src
    assert b"\r" not in path.read_bytes()


# --- installer ---------------------------------------------------------------

def test_cron_runs_the_update_then_the_check_in_their_own_containers():
    src = _text(INSTALL)
    assert MARKER in src
    line = next(l for l in src.splitlines() if l.startswith("CRON_LINE="))
    assert "'30 6 * * 0 cd /opt/swing-bot && " in line
    update = "/usr/bin/docker compose run --rm -T bot python scripts/data/fetch_alpaca_history.py --mode update"
    check = "/usr/bin/docker compose run --rm -T bot python scripts/data/check_history_store.py --verify-hashes"
    assert line.index(update) < line.index(check)
    assert 'echo "update exit $?"' in line and 'echo "check exit $?"' in line
    assert ">> /opt/swing-bot/logs/history_store_cron.log 2>&1" in line
    assert "compose exec" not in src


def test_cron_percent_signs_are_escaped():
    """cron turns a bare % into a newline."""
    line = next(l for l in _text(INSTALL).splitlines() if l.startswith("CRON_LINE="))
    assert re.search(r"(?<!\\)%", line) is None


def _working_bash(*paths):
    """A bash that resolves these host paths, or None (on Windows `bash` can be
    WSL's, which cannot see C:/...; Git for Windows' bash is tried next)."""
    git = shutil.which("git")
    candidates = [shutil.which("bash")]
    if git:
        candidates.append(str(pathlib.Path(git).resolve().parents[1] / "usr" / "bin" / "bash.exe"))
    test = " && ".join(f'test -e "{p.as_posix()}"' for p in paths)
    for bash in filter(None, candidates):
        try:
            if subprocess.run([bash, "-c", test], capture_output=True, timeout=20).returncode == 0:
                return bash
        except OSError:
            continue
    return None


def test_installer_is_idempotent_and_replaces_an_older_line(tmp_path):
    bash = _working_bash(INSTALL, tmp_path)
    if bash is None:
        pytest.skip("no bash that can see host paths")
    store = tmp_path / "cron.txt"
    store.write_text("0 3 * * * /x/backup_db.sh\n"
                     "0 5 * * 0 cd /old && docker compose run bot python scripts/data/fetch_alpaca_history.py --mode update\n")
    # crontab is an exported bash function: a stub file is not executable on Windows.
    fn = (f'crontab() {{ if [ "$1" = "-l" ]; then cat "{store.as_posix()}"; '
          f'else d=$(cat); printf "%s\\n" "$d" > "{store.as_posix()}"; fi; }}; export -f crontab; '
          f'bash "{INSTALL.as_posix()}"')
    env = {**os.environ, "BASE": tmp_path.as_posix()}
    for _ in range(2):
        subprocess.run([bash, "-c", fn], env=env, check=True, capture_output=True)
    lines = store.read_text().splitlines()
    assert sum(l == MARKER for l in lines) == 1
    assert sum("fetch_alpaca_history.py --mode update" in l for l in lines) == 1
    assert not any("/old" in l for l in lines)
    assert sum("backup_db.sh" in l for l in lines) == 1
    assert (tmp_path / "logs").is_dir()


@pytest.mark.parametrize("path", [INSTALL, PULL])
def test_scripts_parse(path):
    bash = _working_bash(path)
    if bash is None:
        pytest.skip("no bash that can see host paths")
    assert subprocess.run([bash, "-n", path.as_posix()], capture_output=True).returncode == 0


# --- pull --------------------------------------------------------------------

def test_pull_reaches_the_vm_only_through_the_wrapper():
    src = _text(PULL)
    assert 'SSH_HETZNER="${SSH_HETZNER:-' in src
    assert 'bash "$SSH_HETZNER" "bash -s -- $*"' in src
    assert not re.search(r"(^|[\s;|&(])(ssh|scp)\s", src, re.M)
    for line in src.splitlines():
        if "SSH_HETZNER" in line and "bash -s" in line:
            assert "$(" not in line, line


def test_pull_streams_each_timeframe_as_base64_tar():
    src = _text(PULL)
    remote = _remote_block(src)
    assert "cd /opt/swing-bot/data/market_data" in remote
    assert 'tar czf - "$ARG" | base64 -w0' in remote
    assert "15min|hourly|daily)" in remote
    assert 'TIMEFRAMES="15min hourly daily"' in src
    assert 'base64 -d | tar xzf - -C "$PARTIAL"' in src


def test_the_remote_side_only_reads():
    remote = _remote_block(_text(PULL))
    assert "rm " not in remote
    assert "docker" not in remote
    assert not re.search(r"[^2&]>\s*[\"'$/a-zA-Z]", remote)


def test_pull_targets_the_main_trees_history_store_not_the_live_cache():
    src = _text(PULL)
    assert 'DEST="${HISTORY_PULL_DEST:-$MAIN_ROOT/data/market_data}"' in src
    assert "git rev-parse --path-format=absolute --git-common-dir" in src
    assert 'PARTIAL="$DEST.partial"' in src


def test_hashes_are_verified_before_the_swap():
    src = _text(PULL)
    body = src[src.index("pull() {"):]
    body = body[:body.index("\n}")]
    verify = body.index('verify "$PARTIAL"')
    assert verify < body.index('mv "$DEST" "$DEST.prev"')
    assert verify < body.index('mv "$PARTIAL" "$DEST"')
    assert "check_history_store.py --root" in src and "--verify-hashes" in src


def test_an_existing_partial_is_never_overwritten():
    body = _text(PULL)
    body = body[body.index("pull() {"):]
    assert body.index('if [ -e "$PARTIAL" ]') < body.index('mkdir -p "$PARTIAL"')


def test_probe_compares_one_small_file_by_sha256():
    src = _text(PULL)
    remote = _remote_block(src)
    assert "probe-hash)" in remote and "probe-stream)" in remote
    assert "daily/_manifest.json" in remote
    assert '"${1:-}" = "--probe"' in src
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_ops_scripts.py`
Expected: FAIL with `FileNotFoundError` for both scripts.

- [ ] **Step 3: Write the installer**

Create `$WT/scripts/ops/install_v162_history_cron.sh` (LF line endings, mode 755: `git -C $WT update-index --chmod=+x` after `git add`):

```bash
#!/usr/bin/env bash
# Installs (idempotently) the v162 weekly crontab entry on the Hetzner VM:
# Sunday 06:30 UTC, `fetch_alpaca_history.py --mode update` in its own
# container (`compose run --rm`, never `exec` into the CPU-capped live bot),
# then `check_history_store.py --verify-hashes`. Both exit codes are logged
# to logs/history_store_cron.log; a non-zero check is something to read, not
# a failure of the cron.
#
# Plan v162 (docs/superpowers/plans/2026-10-15-v162-alpaca-history-store_0-index.md),
# task AH20; installed by AH25 after the merge, because `compose run` uses
# the deployed image (SWING_BOT_IMAGE from /opt/swing-bot/.env).
#
# Run this ON the VM as root, from a dev machine via:
#   bash scripts/ops/ssh-hetzner.sh "bash -s" < scripts/ops/install_v162_history_cron.sh
#
# Safe to re-run: it replaces any earlier line this script installed.
set -euo pipefail

MARKER='# v162 alpaca history store weekly update (installed by install_v162_history_cron.sh)'
BASE="${BASE:-/opt/swing-bot}"
CRON_LINE='30 6 * * 0 cd /opt/swing-bot && { echo "=== $(date -u +\%Y-\%m-\%dT\%H:\%M:\%SZ) ==="; /usr/bin/docker compose run --rm -T bot python scripts/data/fetch_alpaca_history.py --mode update; echo "update exit $?"; /usr/bin/docker compose run --rm -T bot python scripts/data/check_history_store.py --verify-hashes; echo "check exit $?"; } >> /opt/swing-bot/logs/history_store_cron.log 2>&1'

mkdir -p "$BASE/logs"
{
    crontab -l 2>/dev/null | grep -vF "$MARKER" | grep -vF "fetch_alpaca_history.py --mode update" || true
    echo "$MARKER"
    echo "$CRON_LINE"
} | crontab -

echo "Installed crontab:"
crontab -l
```

- [ ] **Step 4: Write the pull script**

Create `$WT/scripts/ops/pull_history_store.sh` (LF, mode 755):

```bash
#!/usr/bin/env bash
# Pull the v162 Alpaca history store off the VM into data/market_data/ (spec
# section 4). Dev machine only (Git Bash). Reaches the VM solely through
# ssh-hetzner.sh, with the remote script piped over stdin.
#   bash scripts/ops/pull_history_store.sh           # pull, verify every hash, swap in
#   bash scripts/ops/pull_history_store.sh --probe   # prove the binary path on one small file
# Writes the MAIN tree's data/market_data/ (never the root market_data/ live
# cache, never a worktree), so a pull made from a worktree session survives
# the worktree. HISTORY_PULL_DEST overrides the destination.
set -euo pipefail
cd "$(dirname "$0")/../.."
SSH_HETZNER="${SSH_HETZNER:-E:/Documents/Private/Projects/Discord-Bot/scripts/ops/ssh-hetzner.sh}"

# The main worktree's root: the parent of git's common dir, else this checkout.
resolve_main_root() {
  MAIN_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")" || MAIN_ROOT=""
  if [ -z "$MAIN_ROOT" ] || [ "$MAIN_ROOT" = "." ] || [ ! -d "$MAIN_ROOT" ]; then
    MAIN_ROOT="$PWD"
  fi
}
resolve_main_root
DEST="${HISTORY_PULL_DEST:-$MAIN_ROOT/data/market_data}"
PARTIAL="$DEST.partial"
TIMEFRAMES="15min hourly daily"

# The VM-side script. Quoted heredoc: nothing expands locally. It only reads.
read -r -d '' REMOTE <<'REMOTE_EOF' || true
set -euo pipefail
cd /opt/swing-bot/data/market_data
MODE="$1"
ARG="${2:-}"
case "$MODE" in
  stream)
    case "$ARG" in
      15min|hourly|daily) ;;
      *) echo "pull_history_store: bad timeframe '$ARG'" >&2; exit 2 ;;
    esac
    tar czf - "$ARG" | base64 -w0
    ;;
  probe-hash)
    sha256sum daily/_manifest.json | cut -d' ' -f1
    ;;
  probe-stream)
    tar czf - daily/_manifest.json | base64 -w0
    ;;
  *)
    echo "pull_history_store: unknown remote mode '$MODE'" >&2
    exit 2
    ;;
esac
REMOTE_EOF

# remote <mode> [arg]: run one mode on the VM (plain words after `bash -s --`).
remote() {
  printf '%s\n' "$REMOTE" | bash "$SSH_HETZNER" "bash -s -- $*"
}

probe() {
  local tmp want got
  tmp="$(mktemp -d)"
  want="$(remote probe-hash | tr -d '\r\n')"
  remote probe-stream | base64 -d | tar xzf - -C "$tmp"
  got="$(sha256sum "$tmp/daily/_manifest.json" | cut -d' ' -f1)"
  rm -rf "$tmp"
  if [ "$want" != "$got" ]; then
    echo "pull_history_store: probe FAIL local $got != VM $want" >&2
    exit 1
  fi
  echo "pull_history_store: probe PASS $got"
}

# verify <root>: 0 when every file matches its manifest SHA-256. Row-count
# gaps are printed in the saved log but never fail the transport.
verify() {
  local out problems
  out="$(python scripts/data/check_history_store.py --root "$1" --verify-hashes || true)"
  printf '%s\n' "$out" > "$1.check.txt"
  printf '%s\n' "$out" | grep -E '^(HASH |check: )' || true
  problems="$(printf '%s\n' "$out" | sed -n 's/^check: .*, \([0-9][0-9]*\) hash problem(s)$/\1/p')"
  [ "$problems" = "0" ]
}

pull() {
  if [ -e "$PARTIAL" ]; then
    echo "pull_history_store: $PARTIAL exists from an earlier pull; inspect it, then delete it by hand" >&2
    exit 2
  fi
  mkdir -p "$PARTIAL"
  for tf in $TIMEFRAMES; do
    echo "pull_history_store: streaming $tf"
    remote stream "$tf" | base64 -d | tar xzf - -C "$PARTIAL"
  done
  if ! verify "$PARTIAL"; then
    echo "pull_history_store: FAIL hash verify, left $PARTIAL (see $PARTIAL.check.txt)" >&2
    exit 1
  fi
  if [ -e "$DEST" ]; then
    rm -rf "$DEST.prev"
    mv "$DEST" "$DEST.prev"
  fi
  mv "$PARTIAL" "$DEST"
  mv "$PARTIAL.check.txt" "$DEST.check.txt"
  echo "pull_history_store: PASS $DEST bytes=$(du -sb "$DEST" | cut -f1)"
}

if [ "${1:-}" = "--probe" ]; then
  probe
else
  pull
fi
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/history_store/test_ops_scripts.py`
Expected: PASS (14 tests). On a machine with no bash that sees host paths, the installer run and the two parse checks SKIP; on this dev machine Git for Windows' bash runs them.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/ops/install_v162_history_cron.sh scripts/ops/pull_history_store.sh tests/history_store/test_ops_scripts.py
git -C $WT update-index --chmod=+x scripts/ops/install_v162_history_cron.sh scripts/ops/pull_history_store.sh
git -C $WT commit -m "feat(v162): AH20 weekly history-store update cron installer and hash-verified pull"
```

Nothing here touches the VM. AH22 runs `--probe` and then the pull; AH25 installs the cron.

