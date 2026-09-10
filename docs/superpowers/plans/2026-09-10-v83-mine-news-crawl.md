# MINE news crawl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a scrolling breaking-news/headline sub-row under the terminal's MINE tape lane, merging per-symbol and general market headlines from FMP within a rolling recency window.

**Architecture:** A dedicated backend route (`GET /market/news`, following the existing `tape()` view's stateless/degrade-not-fail pattern) merges per-symbol FMP news with a new general-news FMP call, dedupes by URL, filters to a recency window, and TTL-caches the result. A dedicated frontend `NewsStore` polls that route on its own 60s timer (independent of `TapeStore`'s scan-event refetch), and a new `NewsCrawl` component renders the result as a scrolling sub-row beneath the existing MINE lane.

**Tech Stack:** Python 3.11 / Flask (backend), Angular 18 + `@ngrx/signals` + Vitest (frontend), Financial Modeling Prep (FMP) as the news source.

**Spec:** `docs/superpowers/specs/2026-09-10-v83-mine-news-crawl-design.md`

## Global Constraints

- Bump: ui minor · bot none.
- Edge: none (integrity) — this is a situational-awareness display, not a new trading signal; it must never feed any strategy/expectancy computation.
- Recency window: 3 hours (the midpoint of the spec's 2–4h range — a concrete decision, not left open).
- Client poll interval: 60 seconds, independent of `TapeStore`'s scan-event refetch.
- Server-side cache TTL: 55 seconds (just under the client poll, so concurrent sessions don't multiply FMP calls).
- Per-symbol FMP `news()` call: `limit=10`. General FMP `general_news()` call: `limit=20`.
- Every external FMP call degrades to an empty result on failure — this route must never 500 on a dead/rate-limited feed (same philosophy as the existing `tape()` view).
- A headline row's shape (backend JSON and frontend type) is exactly: `{symbol: string | null, headline: string, source: string, url: string, published_at: string}`.

---

### Task N1: `FMPClient.general_news()`

**Files:**
- Modify: `swingbot/core/marketdata/fmp_client.py:249-250` (insert after the existing `news()` method)
- Test: `tests/marketdata/test_fmp_client.py`

**Interfaces:**
- Produces: `FMPClient.general_news(limit: int = 20) -> Any` — same shape as the existing `FMPClient.news(symbol, limit)`: returns FMP's parsed JSON (a `list` of article dicts, each with at least `title`, `site`, `url`, `publishedDate`), or whatever `_get()`/`_parse()` already produce on a gated/error body. Consumed by Task N2's `/market/news` route.

- [ ] **Step 1: Write the failing test**

Add to `tests/marketdata/test_fmp_client.py` (near the other endpoint tests, after `test_build_url_injects_key_and_drops_none`):

```python
def test_general_news_hits_general_latest_endpoint(monkeypatch):
    c = _client()
    captured = {}

    def fake_raw_get(url):
        captured["url"] = url
        return 200, json.dumps([
            {"title": "Fed holds rates", "site": "AP",
             "url": "https://example.com/a", "publishedDate": "2026-09-10 12:00:00"},
        ])

    monkeypatch.setattr(c, "_raw_get", fake_raw_get)
    result = c.general_news(limit=5)

    assert result == [
        {"title": "Fed holds rates", "site": "AP",
         "url": "https://example.com/a", "publishedDate": "2026-09-10 12:00:00"},
    ]
    assert captured["url"].startswith(
        "https://financialmodelingprep.com/stable/news/general-latest?")
    assert "limit=5" in captured["url"]
    assert "apikey=TESTKEY" in captured["url"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_fmp_client.py`
Expected: FAIL with `AttributeError: 'FMPClient' object has no attribute 'general_news'`

- [ ] **Step 3: Write minimal implementation**

In `swingbot/core/marketdata/fmp_client.py`, insert immediately after the `news()` method (currently lines 249-250):

```python
    def general_news(self, limit: int = 20) -> Any:
        return self._get("news/general-latest", limit=limit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/marketdata/test_fmp_client.py`
Expected: PASS

- [ ] **Step 5: Verify the endpoint against the live FMP API before moving on**

This is the one genuinely external unknown in this plan: FMP's `news/general-latest` path and its `title`/`site`/`url`/`publishedDate` field names were confirmed against FMP's public docs during planning, but not against a live call. If `FMP_API_KEY` is set in this machine's `.env`, run:

```bash
python -c "from swingbot.core.marketdata.fmp_client import FMPClient; import json; print(json.dumps(FMPClient().general_news(limit=2), indent=2)[:800])"
```

Confirm the returned articles carry `title`, `site`, `url`, and `publishedDate` keys. If a field name differs, fix it now in Task N2's `_news_article()` helper (Step 3 below) before writing that task's tests — do not carry a wrong field name forward. If no `FMP_API_KEY` is configured on this machine, skip this step and flag it explicitly in the Task N2 commit message so the next session with a key can verify it.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/marketdata/fmp_client.py tests/marketdata/test_fmp_client.py
git commit -m "feat(v83): FMPClient.general_news for the MINE news crawl"
```

---

### Task N2: `GET /market/news` backend route

**Files:**
- Modify: `swingbot/admin/api_v1/market.py` (new route, near `tape()` at line 647; reuses `_tape_symbols()` at line 519-530)
- Test: Create `tests/admin/test_api_v1_news.py`

**Interfaces:**
- Consumes: `FMPClient.news(symbol, limit)` (existing), `FMPClient.general_news(limit)` (Task N1), `_tape_symbols(raw: str) -> list[str]` (existing, market.py:519-530).
- Produces: `GET /api/v1/market/news?symbols=<comma-separated>` → `{"as_of": <iso str>, "rows": [{"symbol": str | null, "headline": str, "source": str, "url": str, "published_at": <iso str>}, ...]}`, newest-first, deduped by `url`, filtered to the last 3 hours. Consumed by Task N3's `ApiClient.news()`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_api_v1_news.py`:

```python
"""GET /api/v1/market/news -- the MINE lane's headline crawl (v83).
FMP calls are always mocked; nothing here hits the network."""
from unittest.mock import patch

import pytest

from swingbot.admin.api_v1 import market as market_module

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture(autouse=True)
def clear_news_cache():
    """The route's TTL cache is a module-level dict -- shared across every
    test in this process. Cleared on both sides so a cache hit from one test
    never masks what the next test's mocks would have returned."""
    market_module._NEWS_CACHE.clear()
    yield
    market_module._NEWS_CACHE.clear()


def _article(title, site, url, published):
    return {"title": title, "site": site, "url": url, "publishedDate": published}


def test_news_merges_per_symbol_and_general(logged_in):
    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news",
               return_value=[_article("NVDA beats", "Reuters", "https://x/1", "2026-09-10 14:00:00")]), \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news",
               return_value=[_article("Fed holds rates", "AP", "https://x/2", "2026-09-10 13:30:00")]):
        resp = logged_in.get("/api/v1/market/news?symbols=NVDA")
    assert resp.status_code == 200
    rows = resp.get_json()["rows"]
    assert [r["headline"] for r in rows] == ["NVDA beats", "Fed holds rates"]
    assert rows[0]["symbol"] == "NVDA"
    assert rows[1]["symbol"] is None


def test_news_drops_articles_outside_the_recency_window(logged_in):
    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news", return_value=[]), \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news",
               return_value=[_article("Old news", "AP", "https://x/3", "2020-01-01 00:00:00")]):
        resp = logged_in.get("/api/v1/market/news?symbols=")
    assert resp.get_json()["rows"] == []


def test_news_dedupes_by_url_across_symbol_and_general(logged_in):
    shared = _article("Everyone's covering this", "Reuters", "https://x/4", "2026-09-10 14:00:00")
    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news", return_value=[shared]), \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news", return_value=[shared]):
        resp = logged_in.get("/api/v1/market/news?symbols=NVDA")
    assert len(resp.get_json()["rows"]) == 1


def test_news_degrades_to_empty_when_both_fmp_calls_fail(logged_in):
    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news", side_effect=Exception("boom")), \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news", side_effect=Exception("boom")):
        resp = logged_in.get("/api/v1/market/news?symbols=NVDA")
    assert resp.status_code == 200
    assert resp.get_json()["rows"] == []


def test_news_serves_stale_cache_when_a_later_call_yields_nothing(logged_in):
    fresh = _article("NVDA beats", "Reuters", "https://x/1", "2026-09-10 14:00:00")
    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news", return_value=[fresh]), \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news", return_value=[]):
        first = logged_in.get("/api/v1/market/news?symbols=NVDA")
    assert first.get_json()["rows"]

    key = ("NVDA",)
    ts, rows = market_module._NEWS_CACHE[key]
    market_module._NEWS_CACHE[key] = (ts - market_module._NEWS_CACHE_TTL_S - 1, rows)

    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news", side_effect=Exception("boom")), \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news", side_effect=Exception("boom")):
        second = logged_in.get("/api/v1/market/news?symbols=NVDA")
    assert second.get_json()["rows"] == first.get_json()["rows"]


def test_news_degrades_on_rate_limit_without_crashing(logged_in):
    from swingbot.core.marketdata.fmp_client import FMPRateLimitError

    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news",
               side_effect=FMPRateLimitError("429")), \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news",
               side_effect=FMPRateLimitError("429")):
        resp = logged_in.get("/api/v1/market/news?symbols=NVDA")
    assert resp.status_code == 200
    assert resp.get_json()["rows"] == []


def test_news_caches_within_the_ttl_window(logged_in):
    with patch("swingbot.core.marketdata.fmp_client.FMPClient.news",
               return_value=[_article("NVDA beats", "Reuters", "https://x/1", "2026-09-10 14:00:00")]) as news_call, \
         patch("swingbot.core.marketdata.fmp_client.FMPClient.general_news", return_value=[]):
        logged_in.get("/api/v1/market/news?symbols=NVDA")
        logged_in.get("/api/v1/market/news?symbols=NVDA")
    assert news_call.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_news.py`
Expected: FAIL — `404 NOT FOUND` (no `/market/news` route yet) or `AttributeError` on `market_module._NEWS_CACHE`.

- [ ] **Step 3: Write minimal implementation**

In `swingbot/admin/api_v1/market.py`, add module-level state near the top of the file (alongside `_TAPE_MAX_SYMBOLS` at line 519) and the new route near `tape()` (after line 720):

```python
import threading
import time

_NEWS_CACHE: dict[tuple[str, ...], tuple[float, list[dict]]] = {}
_NEWS_CACHE_LOCK = threading.Lock()
_NEWS_CACHE_TTL_S = 55.0
_NEWS_RECENCY_HOURS = 3
_NEWS_PER_SYMBOL_LIMIT = 10
_NEWS_GENERAL_LIMIT = 20


def _news_cache_get(key: tuple[str, ...]) -> list[dict] | None:
    with _NEWS_CACHE_LOCK:
        entry = _NEWS_CACHE.get(key)
    if entry is None:
        return None
    ts, rows = entry
    if time.time() - ts > _NEWS_CACHE_TTL_S:
        return None
    return rows


def _news_cache_get_stale(key: tuple[str, ...]) -> list[dict] | None:
    with _NEWS_CACHE_LOCK:
        entry = _NEWS_CACHE.get(key)
    return entry[1] if entry else None


def _news_cache_set(key: tuple[str, ...], rows: list[dict]) -> None:
    with _NEWS_CACHE_LOCK:
        _NEWS_CACHE[key] = (time.time(), rows)


def _parse_fmp_date(raw):
    from datetime import datetime, timezone

    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _news_article(article, symbol: str | None):
    """One FMP article -> `(published_at, row)`, or `None` if unusable.

    Kept as a `(datetime, dict)` pair rather than putting the parsed
    timestamp straight into the row: the caller needs the real `datetime`
    to filter/sort by, but the JSON response wants an ISO string.
    """
    if not isinstance(article, dict):
        return None
    url = article.get("url")
    title = article.get("title")
    published = _parse_fmp_date(article.get("publishedDate"))
    if not url or not title or published is None:
        return None
    return published, {
        "symbol": symbol,
        "headline": title,
        "source": article.get("site") or "",
        "url": url,
        "published_at": published.isoformat(),
    }
```

Then the route itself:

```python
@api_v1.route("/market/news", methods=["GET"])
@require_auth
def news():
    """The MINE lane's headline crawl -- per-flagged-symbol FMP news plus
    general market news, merged, deduped by URL, and filtered to the last
    `_NEWS_RECENCY_HOURS` hours. Stateless and cached the same way `tape()`
    is priced: nothing is written to `data/`, freshness is a TTL, not a
    persisted preference.

    Degrades to an empty list on any FMP failure (rate limit, gating,
    network) -- never a 500. On an otherwise-empty result, serves the last
    cached rows past their TTL rather than blanking the crawl on a
    transient outage.
    """
    import logging
    from datetime import datetime, timedelta, timezone

    from swingbot.core.marketdata.fmp_client import FMPClient, FMPRateLimitError

    symbols = _tape_symbols(request.args.get("symbols", ""))
    as_of = datetime.now(timezone.utc).isoformat()
    cache_key = tuple(symbols)

    cached = _news_cache_get(cache_key)
    if cached is not None:
        return jsonify({"as_of": as_of, "rows": cached})

    client = FMPClient()
    dated: list[tuple] = []
    seen_urls: set[str] = set()

    for symbol in symbols:
        try:
            articles = client.news(symbol, limit=_NEWS_PER_SYMBOL_LIMIT)
        except FMPRateLimitError:
            logging.getLogger(__name__).warning("FMP rate-limited on news for %s", symbol)
            articles = []
        except Exception:
            articles = []
        for article in articles if isinstance(articles, list) else []:
            parsed = _news_article(article, symbol)
            if parsed and parsed[1]["url"] not in seen_urls:
                seen_urls.add(parsed[1]["url"])
                dated.append(parsed)

    try:
        general = client.general_news(limit=_NEWS_GENERAL_LIMIT)
    except FMPRateLimitError:
        logging.getLogger(__name__).warning("FMP rate-limited on general news")
        general = []
    except Exception:
        general = []
    for article in general if isinstance(general, list) else []:
        parsed = _news_article(article, None)
        if parsed and parsed[1]["url"] not in seen_urls:
            seen_urls.add(parsed[1]["url"])
            dated.append(parsed)

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_NEWS_RECENCY_HOURS)
    dated = [pair for pair in dated if pair[0] >= cutoff]
    dated.sort(key=lambda pair: pair[0], reverse=True)
    rows = [row for _, row in dated]

    if not rows:
        stale = _news_cache_get_stale(cache_key)
        if stale:
            return jsonify({"as_of": as_of, "rows": stale})

    _news_cache_set(cache_key, rows)
    return jsonify({"as_of": as_of, "rows": rows})
```

`threading` and `time` may already be imported elsewhere in this module for other routes — check the existing top-of-file imports first and only add what's missing rather than duplicating an import line.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_api_v1_news.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/market.py tests/admin/test_api_v1_news.py
git commit -m "feat(v83): GET /market/news -- merged, deduped, TTL-cached headline feed"
```

---

### Task N3: Frontend API surface — `NewsRow`/`NewsResponse` and `ApiClient.news()`

**Files:**
- Modify: `frontend/src/app/api/models.ts` (near `TapeRow`/`TapeResponse`, lines 1105-1123)
- Modify: `frontend/src/app/api/api-client.ts` (near `tape()`)
- Modify: `frontend/src/app/api/interceptors.spec.ts` (the `ApiClient` HTTP-shape tests, near the existing `tape()` tests at the end of that `describe` block)

**Interfaces:**
- Produces: `NewsRow`/`NewsResponse` types matching Task N2's JSON shape exactly; `ApiClient.news(symbols: string[]): Observable<NewsResponse>`. Consumed by Task N4's `NewsStore`.

- [ ] **Step 1: Write the failing tests**

In `frontend/src/app/api/interceptors.spec.ts`, add to the `describe('ApiClient', ...)` block, right after the existing `it('does not call the API for an empty symbol list', ...)` test for `tape`:

```ts
  it('requests news with a comma-joined symbol list', () => {
    api.news(['NVDA', 'AMD']).subscribe();
    const request = backend.expectOne('/api/v1/market/news?symbols=NVDA%2CAMD');
    expect(request.request.method).toBe('GET');
  });

  it('still calls the API for an empty symbol list', () => {
    // Unlike tape(), news() must fetch even with nothing flagged: general
    // market headlines have no symbol to gate on.
    api.news([]).subscribe();
    backend.expectOne((r) => r.url.includes('/market/news'));
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- --include src/app/api/interceptors.spec.ts`
Expected: FAIL with `TypeError: api.news is not a function`

- [ ] **Step 3: Write minimal implementation**

In `frontend/src/app/api/models.ts`, add next to `TapeRow`/`TapeResponse`:

```ts
export interface NewsRow {
  symbol: string | null;
  headline: string;
  source: string;
  url: string;
  published_at: string;
}
export interface NewsResponse {
  as_of: string;
  rows: NewsRow[];
}
```

In `frontend/src/app/api/api-client.ts`, add right after the `tape()` method:

```ts
  /** The MINE lane's headline crawl: per-flagged-symbol + general market
   *  news, merged and deduped server-side within a rolling recency window
   *  (v83). Unlike `tape()`, this is NOT short-circuited on an empty symbol
   *  list -- general market headlines are still worth fetching with nothing
   *  flagged. */
  news(symbols: string[]): Observable<NewsResponse> {
    const query = encodeURIComponent(symbols.join(','));
    return this.http.get<NewsResponse>(`${this.base}/market/news?symbols=${query}`);
  }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- --include src/app/api/interceptors.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/interceptors.spec.ts
git commit -m "feat(v83): NewsRow/NewsResponse and ApiClient.news()"
```

---

### Task N4: `NewsStore`

**Files:**
- Create: `frontend/src/app/stores/news.store.ts`
- Test: Create `frontend/src/app/stores/news.store.spec.ts`

**Interfaces:**
- Consumes: `ApiClient.news(symbols)` (Task N3), `readTapeSymbols(prefs.values())` from `../ui/tape-prefs` (existing, shared with `TapeStore` — same MINE-flagged symbol set).
- Produces: `NewsStore` — a `signalStore` exposing `rows: Signal<NewsRow[]>`, `asOf: Signal<string | null>`, `visible: Signal<boolean>`. Consumed by Task N5's `NewsCrawl`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/stores/news.store.spec.ts`:

```ts
import { ApplicationRef, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Observable, of } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { PreferencesStore } from './preferences.store';
import { NewsStore } from './news.store';

describe('NewsStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function setup(newsImpl: (symbols: string[]) => ReturnType<ApiClient['news']>) {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: ApiClient, useValue: { news: vi.fn(newsImpl) } },
        { provide: PreferencesStore, useValue: {
            values: () => ({ 'tape.symbols': ['NVDA'] }),
            update: () => undefined,
            isLoaded: () => true,
          } },
      ],
    });
    return TestBed.inject(ApiClient) as unknown as { news: ReturnType<typeof vi.fn> };
  }

  it('loads once on init and again every 60s', () => {
    const api = setup(() => of({ as_of: '2026-09-10T14:35:00+00:00', rows: [] }));

    TestBed.inject(NewsStore);
    TestBed.inject(ApplicationRef).tick();
    expect(api.news).toHaveBeenCalledTimes(1);
    expect(api.news).toHaveBeenCalledWith(['NVDA']);

    vi.advanceTimersByTime(60_000);
    TestBed.inject(ApplicationRef).tick();
    expect(api.news).toHaveBeenCalledTimes(2);
  });

  it('ignores a stale response that resolves after a newer request', () => {
    const responses = [
      { as_of: 'first', rows: [{ symbol: 'NVDA', headline: 'stale', source: 'A',
          url: 'https://x/1', published_at: '2026-09-10T14:00:00+00:00' }] },
      { as_of: 'second', rows: [{ symbol: 'NVDA', headline: 'fresh', source: 'B',
          url: 'https://x/2', published_at: '2026-09-10T14:01:00+00:00' }] },
    ];
    // The first request's Observable does not emit until flushed manually,
    // so it resolves AFTER the second one already has -- exactly the
    // out-of-order case `latestRequest` guards against.
    let resolveFirst: (() => void) | undefined;
    const first = new Promise<void>((resolve) => { resolveFirst = resolve; });
    let call = 0;
    const api = setup(() => {
      call += 1;
      if (call === 1) {
        return new Observable((subscriber) => {
          first.then(() => { subscriber.next(responses[0]); subscriber.complete(); });
        });
      }
      return of(responses[1]);
    });

    const store = TestBed.inject(NewsStore);
    TestBed.inject(ApplicationRef).tick();
    vi.advanceTimersByTime(60_000);
    TestBed.inject(ApplicationRef).tick();
    resolveFirst?.();
    return first.then(() => {
      expect(store.rows()[0].headline).toBe('fresh');
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/stores/news.store.spec.ts`
Expected: FAIL — `Cannot find module './news.store'`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/app/stores/news.store.ts`:

```ts
import { computed, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { NewsRow } from '../api/models';
import { readTapeSymbols } from '../ui/tape-prefs';
import { PreferencesStore } from './preferences.store';

interface NewsSlice {
  rows: NewsRow[];
  asOf: string | null;
}

const NEWS_POLL_MS = 60_000;

/**
 * The MINE lane's headline crawl -- spec v83.
 *
 * **Independent 60s poll, unlike `TapeStore`.** "Breaking" is a recency
 * property, not a scan-event property: a headline can go stale between scan
 * ticks (which fire on a completed scan cycle, not on a clock), so this
 * store keeps its own timer rather than piggybacking on `EventStream`.
 *
 * **A failed refetch keeps the previous rows** -- same reasoning as
 * `TapeStore`: a transient FMP outage should read as "no update yet", not
 * "nothing is happening".
 */
export const NewsStore = signalStore(
  { providedIn: 'root' },
  withState<NewsSlice>({ rows: [], asOf: null }),
  withComputed((store) => ({
    visible: computed(() => store.rows().length > 0),
  })),
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;
    const load = (): void => {
      const symbols = readTapeSymbols(prefs.values());
      const request = ++latestRequest;
      api.news(symbols).subscribe({
        next: (response) => {
          if (request !== latestRequest) return;
          if (!response || !Array.isArray(response.rows)) return;
          patchState(store, { rows: response.rows, asOf: response.as_of ?? null });
        },
        error: () => undefined,
      });
    };
    return { load };
  }),
  withHooks((store) => {
    let pollId: ReturnType<typeof setInterval> | undefined;
    return {
      onInit() {
        store.load();
        pollId = setInterval(() => store.load(), NEWS_POLL_MS);
      },
      onDestroy() {
        if (pollId !== undefined) clearInterval(pollId);
      },
    };
  }),
);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/stores/news.store.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/stores/news.store.ts frontend/src/app/stores/news.store.spec.ts
git commit -m "feat(v83): NewsStore -- independent 60s poll for the MINE headline crawl"
```

---

### Task N5: `NewsCrawl` component and shell wiring

**Files:**
- Create: `frontend/src/app/shell/tape/news-crawl.ts`
- Create: `frontend/src/app/shell/tape/news-crawl.spec.ts`
- Modify: `frontend/src/app/shell/shell.ts:27` (import), `:62` (imports array)
- Modify: `frontend/src/app/shell/shell.html:155-159` (template)
- Modify: `frontend/src/app/shell/tape/tape.css:40-41` (comment: "both lanes" -> "all lanes", now that a third lane exists)

**Interfaces:**
- Consumes: `NewsStore` (Task N4) — `rows()`, `visible()`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/shell/tape/news-crawl.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { NewsStore } from '../../stores/news.store';
import { NewsCrawl } from './news-crawl';

describe('NewsCrawl', () => {
  function setup(rows: unknown[]) {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: NewsStore, useValue: {
          rows: () => rows, visible: () => rows.length > 0, load: () => undefined,
        } },
      ],
    });
    const fixture = TestBed.createComponent(NewsCrawl);
    fixture.detectChanges();
    return fixture;
  }

  it('renders nothing when there is no news', () => {
    const el = setup([]).nativeElement as HTMLElement;
    expect(el.querySelector('.lane')).toBeNull();
  });

  it('renders the track twice so the loop is seamless', () => {
    const el = setup([{ symbol: 'NVDA', headline: 'NVDA beats on revenue', source: 'Reuters',
      url: 'https://example.com/a', published_at: '2026-09-10T14:00:00+00:00' }])
      .nativeElement as HTMLElement;
    expect(el.querySelectorAll('.tile').length).toBe(2);
  });

  it('opens the article in a new tab', () => {
    const el = setup([{ symbol: null, headline: 'Fed holds rates', source: 'AP',
      url: 'https://example.com/b', published_at: '2026-09-10T14:00:00+00:00' }])
      .nativeElement as HTMLElement;
    const link = el.querySelector('.tile') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('https://example.com/b');
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('omits the symbol chip for general market news', () => {
    const el = setup([{ symbol: null, headline: 'Fed holds rates', source: 'AP',
      url: 'https://example.com/b', published_at: '2026-09-10T14:00:00+00:00' }])
      .nativeElement as HTMLElement;
    expect(el.querySelector('.sym')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --include src/app/shell/tape/news-crawl.spec.ts`
Expected: FAIL — `Cannot find module './news-crawl'`

- [ ] **Step 3: Write minimal implementation**

Create `frontend/src/app/shell/tape/news-crawl.ts`:

```ts
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { NewsStore } from '../../stores/news.store';

@Component({
  selector: 'sb-news-crawl',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './tape.css',
  template: `
    @if (news.visible()) {
      <div class="lane" role="region" aria-label="Breaking news">
        <div class="cap">news</div>
        <div class="viewport">
          <div class="track">
            @for (pass of [0, 1]; track pass) {
              @for (row of news.rows(); track row.url) {
                <a class="tile" [href]="row.url" target="_blank" rel="noopener noreferrer"
                   [attr.aria-hidden]="pass === 1 ? 'true' : null"
                   [attr.tabindex]="pass === 1 ? -1 : null">
                  @if (row.symbol) {
                    <span class="sym">{{ row.symbol }}</span>
                  }
                  <span class="ctx">{{ row.headline }}</span>
                  <span class="ctx muted">{{ row.source }}</span>
                </a>
              }
            }
          </div>
        </div>
      </div>
    }
  `,
})
export class NewsCrawl {
  protected readonly news = inject(NewsStore);
}
```

In `frontend/src/app/shell/shell.ts`, add the import after line 27 (`import { NamesLane } from './tape/names-lane';`):

```ts
import { NewsCrawl } from './tape/news-crawl';
```

And add `NewsCrawl` to the `@Component` `imports` array (line 62):

```ts
    Button, Icon, ProfileMenu, MarketLane, NamesLane, NewsCrawl,
```

In `frontend/src/app/shell/shell.html`, add the sibling element right after `<sb-names-lane />` (around line 159):

```html
<sb-market-lane />
<sb-names-lane />
<sb-news-crawl />
```

In `frontend/src/app/shell/tape/tape.css`, update the comment above the `@media (max-width: 640px)` block (currently "Below sm both lanes stay, compressed.") to:

```css
/* Below sm every lane stays, compressed. Spec: the layered read is wanted on
   every device, not only where it is cheap. */
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --include src/app/shell/tape/news-crawl.spec.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/tape/news-crawl.ts frontend/src/app/shell/tape/news-crawl.spec.ts \
        frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.html frontend/src/app/shell/tape/tape.css
git commit -m "feat(v83): NewsCrawl -- scrolling headline sub-row under the MINE lane"
```

---

### Task N6: Full-suite verification and release

**Files:** None (verification only).

- [ ] **Step 1: Dispatch the backend full suite to `test-runner`**

Per this repo's convention, the full backend suite is run once, at the end, via the `test-runner` subagent (never inline) so ~1150 progress lines never enter this session's context:

> Dispatch `test-runner` with: "Run `python scripts/dev/testrun.py full` and report only the one-line verdict."

Expected: `0 failed`, `0 xfailed` (a changed pass count is not itself a failure — see `docs/claude/testing-cost.md` if the count differs from a prior run).

- [ ] **Step 2: Run the full frontend suite**

Run: `cd frontend && npm test`
Expected: all suites pass, including the five new/modified spec files from Tasks N3-N5.

- [ ] **Step 3: Manual smoke check**

Start the admin UI (`python admin_ui.py`) and open the terminal shell in a browser with at least one symbol flagged in MINE. Confirm:
- The new "news" lane appears beneath the MINE lane within 60s of load.
- Clicking a headline opens the source article in a new tab.
- Unflagging every MINE symbol still shows general market headlines (the crawl does not disappear the way the MINE lane itself does).

- [ ] **Step 4: Bump `VERSION.json` and close out**

Per `docs/claude/working-conventions.md`: bump the `ui` line only (minor), leave `bot` untouched. Then follow `docs/claude/document-lifecycle.md` to move this plan and its spec to `docs/superpowers/plans/implemented/` and `docs/superpowers/specs/implemented/`, and commit.

```bash
git add VERSION.json
git commit -m "release(ui): <new-version> -- MINE lane news crawl"
```
