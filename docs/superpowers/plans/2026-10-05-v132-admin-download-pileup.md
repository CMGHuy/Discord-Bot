# v132 — Admin download pile-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-10-05-v132-admin-download-pileup-design.md`
**Bump:** bot patch, ui patch
**Edge:** none (integrity) — the admin UI stops taking itself down; no trade, signal or plan changes

**Goal:** Stop `/api/v1/market/tape` traffic from queueing hundreds of threads on the yfinance download lock.

**Architecture:** Three independent guards. A per-symbol single-flight cache in front of the tape's two batch fetches; a wait limit on the yfinance download lock that only the admin web process switches on; a throttled `scan` subscription in the SPA for the three stores that hit market data.

**Tech Stack:** Python 3.11, Flask, pytest; Angular signals, vitest.

## Progress (2026-10-10)

- P1–P3 are implemented on `codex/v132-admin-download-pileup-integration`; the concurrency and throttle review findings were repaired in `7107f023`.
- P4 local verification: `python scripts/dev/testrun.py full` passed with 7,626 passed, 3 skipped, 0 failed, 0 xfailed. `npx ng test --watch=false` passed 2,689 tests; `npx ng build` passed. Bot `2.3.1` and UI `1.22.1` are committed with regenerated version history; the post-bump version-matrix test passed 13 tests.
- P4 remains open for the merge to `main`, Hetzner deployment, ten-minute production check, and close-out. The shared `main` checkout has another session's uncommitted setup files. Production deployment requires an explicit request under `AGENTS.md`.

## Global Constraints

- The scanner, backtests and every `allow_stale=False` caller keep today's behaviour exactly: no cache, unlimited lock wait.
- No server event contract change: `scan_progress` keeps raising `scan`. No migration.
- Every function written or changed stays under cyclomatic complexity 15.
- Tape tests patch `swingbot.core.marketdata.data.get_current_price_batch` / `get_daily_data_batch` as module attributes; the cache must look both up at call time so those patches keep working.

## File map

| File | Role |
|---|---|
| `swingbot/admin/tape_cache.py` (new) | `SingleFlightCache` plus the two module-level instances and `reset()` |
| `swingbot/admin/api_v1/market.py` | `tape()` calls the cache |
| `swingbot/core/marketdata/yf_safe.py` | `DownloadBusy`, `set_default_lock_timeout`, `lock_timeout=` |
| `swingbot/core/infra/retry.py` | never retries an exception marked `no_retry` |
| `swingbot/core/marketdata/data.py` | the two yfinance batch paths log `DownloadBusy` at info |
| `swingbot/config.py`, `swingbot/admin/app.py` | `ADMIN_YF_LOCK_TIMEOUT_SECONDS`, applied in `main()` |
| `frontend/src/app/api/event-stream.ts` | throttled `changes()`, hidden-tab pause |
| `frontend/src/app/stores/{tape,market-index,chart}.store.ts` | subscribe to `scan` throttled |

---

### Task P1: Single-flight tape cache

**Files:**
- Create: `swingbot/admin/tape_cache.py`
- Modify: `swingbot/admin/api_v1/market.py` (`tape()`, the two `market_data.get_*_batch` calls)
- Test: `tests/admin/test_tape_cache.py` (new), `tests/admin/test_api_v1_tape.py` (add an autouse reset)

**Interfaces:**
- Produces: `tape_cache.prices(symbols: list[str]) -> dict`, `tape_cache.daily_frames(symbols: list[str]) -> dict`, `tape_cache.reset() -> None`, `SingleFlightCache(ttl: float, wait: float = 10.0, clock=time.monotonic).get(symbols, fetch) -> dict`

- [ ] **Step 1: Write the failing tests** — `tests/admin/test_tape_cache.py`

```python
"""SingleFlightCache -- one download per expiry, however many callers."""
import threading
import time

from swingbot.admin.tape_cache import SingleFlightCache


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_concurrent_callers_share_one_fetch():
    calls = []
    release = threading.Event()

    def fetch(symbols):
        calls.append(list(symbols))
        release.wait(5)
        return {s: 1.0 for s in symbols}

    cache = SingleFlightCache(ttl=30)
    results = []
    threads = [threading.Thread(target=lambda: results.append(cache.get(["A", "B"], fetch)))
               for _ in range(20)]
    for t in threads:
        t.start()
    time.sleep(0.2)
    release.set()
    for t in threads:
        t.join(5)
    assert calls == [["A", "B"]]
    assert results == [{"A": 1.0, "B": 1.0}] * 20


def test_fresh_entries_skip_the_fetch_and_overlapping_lists_share():
    calls = []

    def fetch(symbols):
        calls.append(list(symbols))
        return {s: 2.0 for s in symbols}

    cache = SingleFlightCache(ttl=30, clock=_Clock())
    cache.get(["A", "B"], fetch)
    assert cache.get(["B", "C"], fetch) == {"B": 2.0, "C": 2.0}
    assert calls == [["A", "B"], ["C"]]


def test_failed_fetch_is_not_cached():
    answers = iter([{}, {"A": 3.0}])
    cache = SingleFlightCache(ttl=30, clock=_Clock())
    assert cache.get(["A"], lambda s: next(answers)) == {}
    assert cache.get(["A"], lambda s: next(answers)) == {"A": 3.0}


def test_expired_entry_survives_a_failed_refetch():
    clock = _Clock()
    cache = SingleFlightCache(ttl=30, clock=clock)
    cache.get(["A"], lambda s: {"A": 4.0})
    clock.now = 31.0

    def boom(symbols):
        raise RuntimeError("yahoo down")

    assert cache.get(["A"], boom) == {"A": 4.0}
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/admin/test_tape_cache.py` — expect FAIL (`No module named swingbot.admin.tape_cache`).

- [ ] **Step 3: Implement** `swingbot/admin/tape_cache.py`

```python
"""Single-flight cache in front of the tape's two batch fetches (v132).

`/market/tape` is refetched by every open tab, and each call used to make two
yfinance downloads behind the process-wide download lock. Under load the
requests queued on that lock until the admin process ran out of file handles
(2026-10-05). Here any number of concurrent callers cost one download per TTL:
the first caller with a missing symbol fetches, the rest wait for it and then
serve whatever the cache holds.

Display-only. Trading decisions never read this.
"""
from __future__ import annotations

import threading
import time

#: Daily bars feed only the previous close, which changes once a day.
DAILY_TTL_SECONDS = 300.0
#: Matches data._BATCH_PRICE_CACHE_TTL_SECONDS.
PRICE_TTL_SECONDS = 15.0


class SingleFlightCache:
    """Per-symbol TTL cache with at most one fetch in flight."""

    def __init__(self, ttl: float, wait: float = 10.0, clock=time.monotonic):
        self._ttl = ttl
        self._wait = wait
        self._clock = clock
        self._entries: dict = {}
        self._cond = threading.Condition()
        self._fetching = False

    def get(self, symbols: list, fetch) -> dict:
        """`{symbol: value}` for every symbol the cache can answer.

        A failed or empty fetch caches nothing, so an expired entry keeps
        being served (stale beats blank) and a never-seen symbol is absent.
        """
        missing = self._claim(symbols)
        if missing:
            self._lead(missing, fetch)
        with self._cond:
            return {s: self._entries[s][0] for s in symbols if s in self._entries}

    def clear(self) -> None:
        with self._cond:
            self._entries.clear()

    def _claim(self, symbols: list) -> list:
        """The symbols this caller must fetch -- empty when all are fresh or
        another caller's fetch was waited on instead."""
        with self._cond:
            missing = self._missing(symbols)
            if not missing:
                return []
            if self._fetching:
                self._cond.wait(timeout=self._wait)
                return []
            self._fetching = True
            return missing

    def _missing(self, symbols: list) -> list:
        now = self._clock()
        return [s for s in symbols
                if s not in self._entries or now - self._entries[s][1] >= self._ttl]

    def _lead(self, missing: list, fetch) -> None:
        got: dict = {}
        try:
            got = fetch(missing) or {}
        except Exception:  # a dead feed degrades to stale rows, never a 500
            got = {}
        finally:
            with self._cond:
                now = self._clock()
                for symbol, value in got.items():
                    self._entries[symbol] = (value, now)
                self._fetching = False
                self._cond.notify_all()


_prices = SingleFlightCache(PRICE_TTL_SECONDS)
_daily = SingleFlightCache(DAILY_TTL_SECONDS)


def prices(symbols: list) -> dict:
    from swingbot.core.marketdata import data as market_data
    return _prices.get(symbols, lambda missing: market_data.get_current_price_batch(missing))


def daily_frames(symbols: list) -> dict:
    from swingbot.core.marketdata import data as market_data
    return _daily.get(symbols, lambda missing: market_data.get_daily_data_batch(missing))


def reset() -> None:
    """Tests only: drop every cached entry."""
    _prices.clear()
    _daily.clear()
```

- [ ] **Step 4: Run** the file again — expect 4 passed.

- [ ] **Step 5: Wire `tape()`.** In `swingbot/admin/api_v1/market.py` replace the two `try` blocks that call `market_data.get_current_price_batch(symbols)` and `market_data.get_daily_data_batch(symbols)` with:

```python
    # v132: both batches go through the single-flight cache -- any number of
    # tabs costs one download per TTL instead of one per request.
    prices = tape_cache.prices(symbols)
    frames = tape_cache.daily_frames(symbols)
```

Add `from swingbot.admin import tape_cache` beside the view's other in-function imports and drop the now-unused `market_data` import. The cache already swallows a raising fetch, which is what the removed `except` blocks did.

- [ ] **Step 6: Reset between tests.** In `tests/admin/test_api_v1_tape.py`, inside the existing autouse fixture `no_daily_batch_network`, add as its first line:

```python
    from swingbot.admin import tape_cache
    tape_cache.reset()
```

- [ ] **Step 7: Add the regression test** to `tests/admin/test_api_v1_tape.py`:

```python
def test_concurrent_tape_requests_share_one_download(app, logged_in):
    """v132: the 2026-10-05 pile-up. Twenty tabs, one slow download each for
    prices and daily bars -- not twenty of each."""
    import threading
    import time

    calls = {"prices": 0, "daily": 0}

    def slow_prices(symbols):
        calls["prices"] += 1
        time.sleep(0.3)
        return {s: 10.0 for s in symbols}

    def slow_daily(symbols):
        calls["daily"] += 1
        time.sleep(0.3)
        return {s: _frame(9.0, 10.0) for s in symbols}

    cookie = logged_in.get_cookie("session")

    def hit(statuses):
        c = app.test_client()
        c.set_cookie("session", cookie.value)
        statuses.append(c.get("/api/v1/market/tape?symbols=NVDA,AMD").status_code)

    with patch("swingbot.core.marketdata.data.get_current_price_batch", side_effect=slow_prices), \
         patch("swingbot.core.marketdata.data.get_daily_data_batch", side_effect=slow_daily):
        statuses: list = []
        threads = [threading.Thread(target=hit, args=(statuses,)) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
    assert statuses == [200] * 20
    assert calls == {"prices": 1, "daily": 1}
```

If the suite's fixture is not named `app`, or the session cookie has another name, use what `tests/admin/conftest.py` (or the root `conftest.py`) defines — read it first.

- [ ] **Step 8: Run** `python scripts/dev/testrun.py file tests/admin/test_api_v1_tape.py` — expect all passed. `python -m radon cc -s -n C swingbot/admin/tape_cache.py swingbot/admin/api_v1/market.py` — expect no new entries.

- [ ] **Step 9: Commit** `feat(v132): single-flight cache in front of the tape's batch fetches`

---

### Task P2: Download lock wait limit

**Files:**
- Modify: `swingbot/core/marketdata/yf_safe.py`, `swingbot/core/infra/retry.py`, `swingbot/core/marketdata/data.py` (`_yf_daily_batch`, `_yf_batch_prices`), `swingbot/config.py`, `swingbot/admin/app.py` (`main`)
- Test: `tests/marketdata/test_yf_safe_lock_timeout.py` (new)

**Interfaces:**
- Produces: `yf_safe.DownloadBusy` (a `RuntimeError` with class attribute `no_retry = True`), `yf_safe.set_default_lock_timeout(seconds: float | None) -> None`, `yf_safe.download(*args, lock_timeout: float | None = None, **kwargs)`

- [ ] **Step 1: Write the failing tests** — `tests/marketdata/test_yf_safe_lock_timeout.py`

```python
"""v132: a caller with a wait limit gives up instead of queueing forever."""
import threading

import pytest

from swingbot.core.infra.retry import with_retry
from swingbot.core.marketdata import yf_safe


@pytest.fixture(autouse=True)
def _no_default():
    yield
    yf_safe.set_default_lock_timeout(None)


@pytest.fixture
def held_lock():
    yf_safe._DOWNLOAD_LOCK.acquire()
    yield
    yf_safe._DOWNLOAD_LOCK.release()


def test_explicit_limit_raises_busy_when_lock_is_held(held_lock):
    with pytest.raises(yf_safe.DownloadBusy):
        yf_safe.download("NVDA", lock_timeout=0.05)


def test_process_default_applies_when_no_argument_is_passed(held_lock):
    yf_safe.set_default_lock_timeout(0.05)
    with pytest.raises(yf_safe.DownloadBusy):
        yf_safe.download("NVDA")


def test_without_a_limit_the_caller_still_waits(monkeypatch, held_lock):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: "frame")
    out = []
    t = threading.Thread(target=lambda: out.append(yf_safe.download("NVDA")))
    t.start()
    t.join(0.2)
    assert t.is_alive() and out == []          # still queued, not failed
    yf_safe._DOWNLOAD_LOCK.release()
    t.join(2)
    yf_safe._DOWNLOAD_LOCK.acquire()            # hand back to the fixture
    assert out == ["frame"]


def test_lock_is_released_after_a_limited_download(monkeypatch):
    monkeypatch.setattr("yfinance.download", lambda *a, **k: "frame")
    assert yf_safe.download("NVDA", lock_timeout=1) == "frame"
    assert yf_safe._DOWNLOAD_LOCK.acquire(blocking=False)
    yf_safe._DOWNLOAD_LOCK.release()


def test_with_retry_does_not_retry_busy(held_lock):
    calls = []

    def fn():
        calls.append(1)
        return yf_safe.download("NVDA", lock_timeout=0.01)

    with pytest.raises(yf_safe.DownloadBusy):
        with_retry(fn, attempts=3, base_delay=0)
    assert len(calls) == 1
```

- [ ] **Step 2: Run** `python scripts/dev/testrun.py file tests/marketdata/test_yf_safe_lock_timeout.py` — expect FAIL (`DownloadBusy` not defined).

- [ ] **Step 3: Implement.** Replace `download` in `swingbot/core/marketdata/yf_safe.py` and add above it:

```python
class DownloadBusy(RuntimeError):
    """The download lock could not be taken inside the caller's wait limit.

    Expected under load, not a fault: the caller renders without the data and
    the next refresh retries. `no_retry` stops `with_retry` multiplying the
    wait by its attempt count.
    """
    no_retry = True


#: Wait limit applied when a caller passes none. `None` (every process but the
#: admin web process, v132) means wait as long as it takes -- the scanner and
#: backtests must never lose a download to a busy lock.
_default_lock_timeout: float | None = None


def set_default_lock_timeout(seconds: float | None) -> None:
    global _default_lock_timeout
    _default_lock_timeout = seconds


def download(*args, lock_timeout: float | None = None, **kwargs):
    limit = lock_timeout if lock_timeout is not None else _default_lock_timeout
    if not _DOWNLOAD_LOCK.acquire(timeout=-1 if limit is None else limit):
        raise DownloadBusy(f"yfinance download lock busy for {limit:g}s")
    try:
        frame = yf.download(*args, **kwargs)
    finally:
        _DOWNLOAD_LOCK.release()
    if frame is None or getattr(frame, "empty", False):
        log.debug("yfinance download returned no rows: tickers=%r",
                  kwargs.get("tickers", args[0] if args else None))
    return frame
```

In `swingbot/core/infra/retry.py`, inside `with_retry`'s `except Exception as exc:` block, as its first statement:

```python
            if getattr(exc, "no_retry", False):
                raise
```

In `swingbot/core/marketdata/data.py`, in both `_yf_daily_batch` and `_yf_batch_prices`, add ahead of the existing `except Exception as exc:`:

```python
    except yf_safe.DownloadBusy as exc:
        log.info("yfinance busy, skipped %d ticker(s): %s", len(tickers), exc)
        return {}
```

- [ ] **Step 4: Config and startup.** In `swingbot/config.py`, directly after the `ALPACA_BARS_TIMEOUT_SECONDS` field:

```python
    Field("ADMIN_YF_LOCK_TIMEOUT_SECONDS", "ADMIN_YF_LOCK_TIMEOUT_SECONDS", "Data Sources",
          "Admin: yfinance wait limit (s)", type="number", default="10", min=1, max=120, step=1,
          help="How long an admin page request waits for the shared yfinance download lock "
               "before rendering without that data. Stops slow Yahoo responses queueing "
               "requests until the admin runs out of connections. Admin web process only; "
               "the scanner always waits. Read at admin start -- restart the admin to apply."),
```

In `swingbot/admin/app.py`, in `main()` before `app.run(...)`:

```python
    from swingbot.core.marketdata import yf_safe
    yf_safe.set_default_lock_timeout(float(config.ADMIN_YF_LOCK_TIMEOUT_SECONDS))
```

Use the module's existing `config` import; if `app.py` reads settings another way, follow how it reads `ALPACA_TIMEOUT_SECONDS`-style fields elsewhere in `swingbot/admin/`.

- [ ] **Step 5: Run** the new file — expect 5 passed. Then `python scripts/dev/testrun.py changed` — expect `0 failed` (config-schema and docs-drift tests may require the new field in a generated doc or `.env.example`; add it where they point).

- [ ] **Step 6: Commit** `feat(v132): wait limit on the yfinance download lock for the admin process`

---

### Task P3: Throttled scan subscription and hidden-tab pause

**Files:**
- Modify: `frontend/src/app/api/event-stream.ts`, `frontend/src/app/stores/tape.store.ts`, `frontend/src/app/stores/market-index.store.ts`, `frontend/src/app/stores/chart.store.ts`
- Test: `frontend/src/app/api/event-stream.spec.ts`

**Interfaces:**
- Produces: `EventStream.changes(name: EventName, options?: { minIntervalMs: number }): Signal<number>`, exported `MARKET_DATA_MIN_INTERVAL_MS = 30_000`

- [ ] **Step 1: Write the failing tests** — append inside `describe('EventStream', …)` in `event-stream.spec.ts`:

```ts
  /* -- throttled subscription (v132) ------------------------------------ */

  it('collapses a burst into one immediate and one trailing bump', () => {
    const raw = stream.changes('scan');
    const slow = stream.changes('scan', { minIntervalMs: 30_000 });
    for (let i = 0; i < 10; i++) FakeEventSource.latest().emit('scan', i + 1);
    expect(raw()).toBe(10);
    expect(slow()).toBe(1);
    vi.advanceTimersByTime(30_000);
    expect(slow()).toBe(2);
    vi.advanceTimersByTime(60_000);
    expect(slow()).toBe(2);
  });

  it('passes a lone event straight through after a quiet interval', () => {
    const slow = stream.changes('scan', { minIntervalMs: 30_000 });
    FakeEventSource.latest().emit('scan', 1);
    vi.advanceTimersByTime(31_000);
    FakeEventSource.latest().emit('scan', 2);
    expect(slow()).toBe(2);
  });

  it('shares one throttle between subscribers of the same event and interval', () => {
    expect(stream.changes('scan', { minIntervalMs: 30_000 }))
      .toBe(stream.changes('scan', { minIntervalMs: 30_000 }));
  });
```

For the hidden-tab pause, add beside the existing degraded-mode tests, reusing whatever helper they use to force `degraded` (three `onerror` calls inside the failure window):

```ts
  it('does not poll while the document is hidden, and catches up once on return', () => {
    degrade();   // the spec file's existing helper for reaching degraded mode
    const trades = stream.changes('trades');
    const before = trades();
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 3);
    expect(trades()).toBe(before);
    hidden.mockReturnValue(false);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(trades()).toBe(before + 1);
  });
```

If the file has no such helper, write one from its existing degraded-mode test's first lines.

- [ ] **Step 2: Run** `cd frontend && npx ng test --include src/app/api/event-stream.spec.ts --watch=false` — expect the four new tests to FAIL.

- [ ] **Step 3: Implement** in `event-stream.ts`.

Beside `POLL_INTERVAL_MS`:

```ts
/** How often a store that hits market data may react to `scan` (v132).
 *  `scan` fires about once a second while a scan runs, and each reaction
 *  used to cost the server a Yahoo download. */
export const MARKET_DATA_MIN_INTERVAL_MS = 30_000;

interface Throttle {
  readonly out: WritableSignal<number>;
  readonly interval: number;
  last: number;
  timer: ReturnType<typeof setTimeout> | null;
}
```

(`WritableSignal` joins the existing `@angular/core` import.)

Fields, beside `counters`:

```ts
  private readonly throttles = new Map<string, Throttle & { name: EventName }>();
  private visibilityBound = false;
```

Replace `changes`:

```ts
  changes(name: EventName, options?: { minIntervalMs: number }): Signal<number> {
    if (!options) return this.counterFor(name).asReadonly();
    const key = `${name}:${options.minIntervalMs}`;
    let throttle = this.throttles.get(key);
    if (!throttle) {
      throttle = { name, out: signal(0), interval: options.minIntervalMs, last: -Infinity, timer: null };
      this.throttles.set(key, throttle);
    }
    return throttle.out;
  }
```

Returning `throttle.out` itself (not `.asReadonly()`, which builds a new object per call) is what makes two subscribers share one signal; the declared return type keeps callers read-only.

In `bump`, after the counter update:

```ts
    for (const throttle of this.throttles.values()) {
      if (throttle.name === name) this.pass(throttle);
    }
```

New private methods:

```ts
  /** Leading edge at once, everything else inside the interval as one
   *  trailing bump -- so the last event of a burst is never lost. */
  private pass(throttle: Throttle): void {
    const wait = throttle.last + throttle.interval - Date.now();
    if (wait <= 0) {
      this.release(throttle);
    } else if (throttle.timer === null) {
      throttle.timer = setTimeout(() => this.release(throttle), wait);
    }
  }

  private release(throttle: Throttle): void {
    throttle.timer = null;
    throttle.last = Date.now();
    throttle.out.update((n) => n + 1);
  }
```

Replace `startPolling`:

```ts
  private startPolling(): void {
    if (this.pollTimer !== null) return;
    this.pollTimer = setInterval(() => {
      // A tab nobody is looking at must not cost the server a refetch.
      if (typeof document !== 'undefined' && document.hidden) return;
      this.bumpAll();
    }, POLL_INTERVAL_MS);
    if (!this.visibilityBound && typeof document !== 'undefined') {
      this.visibilityBound = true;
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && this.pollTimer !== null) this.bumpAll();
      });
    }
  }
```

In `disconnect()`, also clear pending throttle timers:

```ts
    for (const throttle of this.throttles.values()) {
      if (throttle.timer !== null) clearTimeout(throttle.timer);
      throttle.timer = null;
    }
```

- [ ] **Step 4: Subscribe the three stores throttled.** In `tape.store.ts`, `market-index.store.ts` and `chart.store.ts`, change

```ts
      const scan = events.changes('scan');
```

to

```ts
      // v132: `scan` fires ~1/s during a scan; this store's refetch hits Yahoo.
      const scan = events.changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
```

and add `MARKET_DATA_MIN_INTERVAL_MS` to each file's existing `event-stream` import. Leave `connection.store.ts` untouched — scan progress keeps the raw signal.

- [ ] **Step 5: Run** `cd frontend && npx ng test --watch=false` — expect 0 failed. Store specs that fake `EventStream.changes` with a one-argument stub still work (the second argument is ignored); a spec that emits two `scan` events back to back and expects two refetches from one of the three stores must advance timers by 30 s between them.

- [ ] **Step 6: Commit** `feat(v132): market-data stores react to scan at most every 30s; hidden tabs stop polling`

---

### Task P4: Full suite, version bump, deploy, production check

- [ ] **Step 1:** Dispatch `test-runner` for `python scripts/dev/testrun.py full` — green is `0 failed` and `0 xfailed`. Run `cd frontend && npx ng test --watch=false` and `npx ng build`.
- [ ] **Step 2:** Bump `VERSION.json` per `docs/claude/working-conventions.md` (`bot` patch, `ui` patch) and commit with the bump.
- [ ] **Step 3:** Merge to `main`, deploy per `docs/deploy/DEPLOY_HETZNER.md`.
- [ ] **Step 4: Production check.** With two admin tabs open for ten minutes, sample every two minutes:

```bash
bash scripts/ops/ssh-hetzner.sh "bash -s" <<'EOF'
cd /opt/swing-bot && docker compose exec -T admin sh -c 'echo "fds=$(ls /proc/1/fd | wc -l) threads=$(ls /proc/1/task | wc -l)"' </dev/null
docker compose logs admin --since 2m 2>&1 | grep -c 'market/tape'
EOF
```

Pass: handle and thread counts flat (no upward trend across the five samples), tape requests at most about 2 per minute per open tab.
- [ ] **Step 5:** Close out per `docs/claude/document-lifecycle.md` (move plan and spec to `implemented/`).

## Parallelisation

P1, P2 and P3 touch disjoint files and can run in parallel: P1 owns `swingbot/admin/`, P2 owns `swingbot/core/` and `swingbot/config.py` plus one line in `swingbot/admin/app.py` (`main`, which P1 does not touch), P3 owns `frontend/`. P4 is sequential after all three because it gates on the merged result.
