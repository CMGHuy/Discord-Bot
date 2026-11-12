# v218 — Part 2: build identity, conditional responses, Server-Timing, route audits (V218-7..V218-13)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v206 — Admin under load](../specs/2026-11-05-v206-admin-under-load-design.md) § Plan 3 (P3-c, P3-d), § Error handling, § Testing; [v205 — Admin read performance](../specs/2026-11-04-v205-admin-read-performance-design.md) § Layer 2.
**Index:** [`2026-11-06-v218-admin-snapshot-etag_0-index.md`](2026-11-06-v218-admin-snapshot-etag_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation`, `## Task ledger` and `## Handoff` live there and bind every task below.

Worktree for every task: `.claude/worktrees/2026-11-06-v218-admin-snapshot-etag` (branch of the same name). Paths below are relative to it.

Symbols this part consumes from Part 1 (created there, verify with `git grep -n` before starting a task):
`store_generation.token() / connected() / bump() / reset()` (V218-2), `config.ADMIN_STORE_SNAPSHOT` (V218-2),
`store_snapshot.request_versions() / request_state() / reset()` (V218-4), `store_snapshot.begin_request()` wired into
`request_timing._begin` (V218-5), fixtures `snapshot_on` and `frozen_snapshot` in `tests/admin_perf/conftest.py` (V218-5).

# Phase P3-c/P3-d — conditional responses and Server-Timing

### Task V218-7: Build identity (`VERSION.json` + image tag); verify `SWING_BOT_IMAGE` on the VM read-only

**Model:** sonnet — one small leaf module with a cache, plus a read-only production check following a given command.

**Files:**
- Create: `swingbot/admin/build_identity.py`
- Create: `tests/admin/test_build_identity.py`
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (append `### Plan 3 build tag on the VM (V218-7)` at the end of the file, after V218-1's `### Plan 3 version() gap (V218-1)`)

**Interfaces:**
- Consumes: nothing from earlier tasks (`swingbot.config._PROJECT_ROOT` exists in `config.py`; `helpers.VERSION_PATH` at `swingbot/admin/helpers.py:39` is built the same way).
- Produces: `build_identity.build_version() -> str` = `"<sha256(VERSION.json bytes) hex[:16]>|<SWING_BOT_IMAGE or ''>"`, cached per process; `build_identity.reset_cache() -> None`; module attribute `build_identity.VERSION_PATH: str` (tests repoint it). A missing or unreadable `VERSION.json` **raises** `OSError` and caches nothing. V218-8's `compute_etag` swallows it and sends no ETag, because a tag that cannot tell two builds apart must never be issued.

Why this exists: the ETag (V218-8) must change on every deploy and every rollback, so a browser never gets a 304 for a body another image produced. `VERSION.json` changes on every release bump. The image tag (`SWING_BOT_IMAGE`, written into `.env` by `deploy/deploy.sh:239` and loaded through the admin service's `env_file: .env`) also tells apart two images with the same `VERSION.json` (a rollback to a hotfix image). The image tag is not a `config.FIELDS` entry, so it is read from `os.environ` directly. `core/infra/deploy_marker.py:_sha()` is no help: it shells out to `git`, which is absent in the image.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_build_identity.py`:

```python
"""v218 V218-7: the build a response came from, the first ETag input (P3-c)."""
import hashlib

import pytest

from swingbot.admin import build_identity


@pytest.fixture
def version_file(tmp_path, monkeypatch):
    path = tmp_path / "VERSION.json"
    path.write_text('{"ui": "1.40.3", "bot": "2.17.3"}', encoding="utf-8")
    monkeypatch.setattr(build_identity, "VERSION_PATH", str(path))
    monkeypatch.delenv("SWING_BOT_IMAGE", raising=False)
    build_identity.reset_cache()
    yield path
    build_identity.reset_cache()


def test_the_value_is_the_version_file_hash_and_the_image_tag(version_file, monkeypatch):
    monkeypatch.setenv("SWING_BOT_IMAGE", "ghcr.io/cmghuy/discord-bot:sha-abc")
    digest = hashlib.sha256(version_file.read_bytes()).hexdigest()[:16]
    assert build_identity.build_version() == f"{digest}|ghcr.io/cmghuy/discord-bot:sha-abc"


def test_without_the_image_tag_the_version_file_alone_names_the_build(version_file):
    digest, _, image = build_identity.build_version().partition("|")
    assert len(digest) == 16 and image == ""


def test_a_version_file_change_changes_the_value_after_a_cache_reset(version_file):
    before = build_identity.build_version()
    version_file.write_text('{"ui": "1.40.4", "bot": "2.17.4"}', encoding="utf-8")
    assert build_identity.build_version() == before          # cached per process
    build_identity.reset_cache()
    assert build_identity.build_version() != before


def test_the_image_tag_present_or_absent_gives_different_values(version_file, monkeypatch):
    absent = build_identity.build_version()
    monkeypatch.setenv("SWING_BOT_IMAGE", "ghcr.io/cmghuy/discord-bot:sha-def")
    build_identity.reset_cache()
    assert build_identity.build_version() != absent


def test_a_missing_version_file_raises_and_caches_nothing(version_file, monkeypatch):
    monkeypatch.setattr(build_identity, "VERSION_PATH", str(version_file.with_name("absent.json")))
    with pytest.raises(OSError):
        build_identity.build_version()
    monkeypatch.setattr(build_identity, "VERSION_PATH", str(version_file))
    assert build_identity.build_version().count("|") == 1    # recovers once the file is back


def test_the_default_path_is_the_repo_version_file():
    build_identity.reset_cache()
    assert build_identity.VERSION_PATH.replace("\\", "/").endswith("/VERSION.json")
    assert len(build_identity.build_version().partition("|")[0]) == 16
    build_identity.reset_cache()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin/test_build_identity.py`
Expected: FAIL with `ImportError: cannot import name 'build_identity'`.

- [ ] **Step 3: Write the module**

Create `swingbot/admin/build_identity.py`:

```python
"""v218 P3-c: the build a response came from -- the first input of every ETag.

``build_version()`` is the SHA-256 of ``VERSION.json``'s bytes (16 hex chars)
plus the image tag ``SWING_BOT_IMAGE`` when the environment carries it. The
deploy writes that tag into ``.env`` (``deploy/deploy.sh``) and the admin
service loads ``.env`` as its ``env_file``, so a rollback to another image
changes the value even when ``VERSION.json`` did not. It is read from
``os.environ`` because it is not a ``config.FIELDS`` entry.

Cached per process: the image cannot change under a running worker. A
missing ``VERSION.json`` raises and caches nothing -- the ETag code swallows
that and sends no tag, never a tag that cannot tell two builds apart.
Imports nothing from ``swingbot.admin``, so ``api_v1`` modules may import it.
"""
from __future__ import annotations

import hashlib
import os
import threading

from swingbot import config

VERSION_PATH = os.path.join(config._PROJECT_ROOT, "VERSION.json")
IMAGE_ENV = "SWING_BOT_IMAGE"

_LOCK = threading.Lock()
_CACHE: str | None = None


def build_version() -> str:
    """``"<sha256(VERSION.json)[:16]>|<image tag or ''>"``; raises OSError without the file."""
    global _CACHE
    cached = _CACHE
    if cached is not None:
        return cached
    with _LOCK:
        if _CACHE is None:
            _CACHE = _compute()
        return _CACHE


def _compute() -> str:
    with open(VERSION_PATH, "rb") as handle:
        digest = hashlib.sha256(handle.read()).hexdigest()[:16]
    return f"{digest}|{os.environ.get(IMAGE_ENV, '')}"


def reset_cache() -> None:
    """Forget the cached value (tests; never needed in a running worker)."""
    global _CACHE
    with _LOCK:
        _CACHE = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin/test_build_identity.py`
Expected: PASS (6 passed).

Check complexity: `python -m radon cc -s swingbot/admin/build_identity.py`. Every function is grade A.

- [ ] **Step 5: Verify on the VM, read-only, that the admin container sees the image tag**

The standing permission covers this read-only call (CLAUDE.md). It reports presence only and never echoes the value:

```bash
bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin sh -c 'test -n \"\$SWING_BOT_IMAGE\" && echo present || echo absent'"
```

Expected: one line, `present` or `absent`. Note the Berlin date. Compute it from `date -u`: Git Bash has no timezone data, and Berlin is UTC+1 in November.

- [ ] **Step 6: Record the result in v206 `## Results`**

Append at the very end of `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (after `### Plan 3 version() gap (V218-1)`). Use the block that matches Step 5's output, with the date filled in.

When it printed `present`:

```markdown
### Plan 3 build tag on the VM (V218-7)

Checked <YYYY-MM-DD> (Berlin), read-only through `scripts/ops/ssh-hetzner.sh`:
the admin container's environment carries `SWING_BOT_IMAGE` (presence only;
the value was not printed). `swingbot/admin/build_identity.build_version()`
therefore names the build as the SHA-256 of `VERSION.json` plus the image
tag, and a rollback to another image changes every ETag even when
`VERSION.json` is the same.
```

When it printed `absent`:

```markdown
### Plan 3 build tag on the VM (V218-7)

Checked <YYYY-MM-DD> (Berlin), read-only through `scripts/ops/ssh-hetzner.sh`:
the admin container's environment does **not** carry `SWING_BOT_IMAGE`.
`swingbot/admin/build_identity.build_version()` therefore rests on the
SHA-256 of `VERSION.json` alone. Every release bumps `VERSION.json`, so a
deploy or a rollback across releases still changes every ETag. Two images
with the same `VERSION.json` (a hotfix redeployed without a bump) would
share tags. Passing `SWING_BOT_IMAGE` into the admin service's
`environment:` in `docker-compose.yml` closes that gap. It is a deploy
change outside this plan, raised with the partner.
```

When it printed `absent`, also tell the controller in the task report, so the partner can decide on the compose change.

- [ ] **Step 7: Commit**

```bash
git add swingbot/admin/build_identity.py tests/admin/test_build_identity.py
git commit -m "feat(admin): build identity from VERSION.json and the image tag, for the v218 ETag"
git add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git commit -m "docs(v206): Plan 3 build tag on the VM (V218-7)"
```

### Task V218-8: Conditional-response decorator: tag before body, 304, `private, no-cache`

**Model:** opus — cache-correctness code where a wrong tag silently serves a stale body; header semantics and failure paths must be exact.

**Files:**
- Create: `swingbot/admin/api_v1/conditional.py`
- Create: `tests/admin_perf/test_conditional.py`

**Interfaces:**
- Consumes: `build_identity.build_version()` (V218-7); `store_generation.token() -> tuple[int, int, int]` and `store_generation.connected() -> bool` (V218-2); `config.ADMIN_STORE_SNAPSHOT` (V218-2); `store_snapshot.request_versions() -> tuple` (V218-4, the plans, trades and journal `version()` tuples, read once per request and shared with the snapshot). Existing: `fx_daily_rate_repo().version()` (`swingbot/core/db/repositories/market_refresh.py:122`, `(count, max(snapped_at))`), `fx_convert.berlin_today()` (`swingbot/core/marketdata/fx_convert.py:40`), `app.resolve_principal()` (`swingbot/admin/app.py:181`), `freshness.FRESH_HEADER` (`swingbot/admin/freshness.py`), `swallowed` (`swingbot/core/infra/swallowed.py`).
- Produces (V218-10..13 rely on these exact names):
  - `conditional.CONDITIONAL_ATTR = "__conditional__"` (the view's route key is stored under it)
  - `conditional.CACHE_CONTROL = "private, no-cache"`
  - `conditional(route_key: str, admit: Callable[[MultiDict], bool]) -> Callable[[F], F]`
  - `etag_inputs(route_key: str, args: MultiDict) -> tuple`
  - `compute_etag(route_key: str, args: MultiDict) -> str | None` (`W/"<sha256 hex[:32]>"`, or None when ineligible or on any exception)
  - `normalised_query(args: MultiDict) -> str`
  - `if_none_match_hits(header: str | None, tag: str) -> bool`

Placement on a view (V218-10 applies it): `@api_v1.route(...)` → `@require_auth` → `@conditional(...)` → `@read_scope` → `def`. Under `@require_auth`, so a 401 never reaches the tag. Above `@read_scope`, so a 304 opens no read scope and builds nothing. `functools.wraps` copies `__dict__`, so `READ_SCOPE_ATTR` survives outward, and `require_auth`'s own `wraps` carries both markers to the function Flask registers.

The flow (index § Architecture): when ineligible, run the view unchanged. Otherwise compute the tag from the inputs alone, **before** the view runs. On a matching `If-None-Match`, return a bodiless 304 carrying `ETag` and `Cache-Control: private, no-cache`. Otherwise run the view, and on a 200 set both headers. Any other status gets neither header. `_no_store` (`api_v1/__init__.py:39`) only `setdefault`s `Cache-Control`, so it leaves `private, no-cache` alone and still sets `no-store` on everything else.

Ineligible means any of: `config.ADMIN_STORE_SNAPSHOT != "on"`; `store_generation.connected()` false (the snapshot listener is down, so NOTIFYs from other processes may be lost); `X-Swingbot-Fresh: 1` (the client asked for fresh market data); `admit(request.args)` false or raising. The decorator deliberately checks the switch and `connected()` itself and does **not** call `store_snapshot.enabled()`: the tag is computed outside the read scope, and whatever `enabled()` adds for the snapshot's own reads must not switch the tag off.

Principal: `resolve_principal()` covers session logins (admin and viewer). A scripted Basic-auth caller passed `require_auth` with the admin credentials and has no session principal, so it is keyed as `("admin", <basic username>, None)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin_perf/test_conditional.py`. It uses a tiny Flask app with every input monkeypatched, so no database is reached.

```python
"""v218 V218-8: the conditional-response decorator (v206 P3-c).

Every input is monkeypatched on a tiny Flask app; the admitted-route behaviour
on the real app is tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

import pytest
from flask import Flask, jsonify, request
from werkzeug.datastructures import MultiDict

from swingbot import config
from swingbot.admin import build_identity
from swingbot.admin.api_v1 import conditional as cond
from swingbot.admin.api_v1.read_scope import READ_SCOPE_ATTR, read_scope
from swingbot.core.infra import store_generation, store_snapshot
from swingbot.core.marketdata import fx_convert


@pytest.fixture
def inputs(monkeypatch):
    """The ETag's inputs, each one settable by a test."""
    state = {
        "build": "0123456789abcdef|img:1",
        "token": (1, 2, 3),
        "versions": ((5, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:00+00:00"), (2, None)),
        "fx": (40, dt.datetime(2026, 11, 4, 6, 0, tzinfo=dt.timezone.utc)),
        "today": dt.date(2026, 11, 4),
        "principal": ("admin", "boss", None),
    }
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "on", raising=False)
    monkeypatch.setattr(store_generation, "connected", lambda: True)
    monkeypatch.setattr(build_identity, "build_version", lambda: state["build"])
    monkeypatch.setattr(store_generation, "token", lambda: state["token"])
    monkeypatch.setattr(store_snapshot, "request_versions", lambda: state["versions"])
    monkeypatch.setattr(cond, "_fx_version", lambda: state["fx"])
    monkeypatch.setattr(fx_convert, "berlin_today", lambda: state["today"])
    monkeypatch.setattr(cond, "_principal", lambda: state["principal"])
    return state


@pytest.fixture
def tiny():
    """GET /thing behind @conditional("thing"); ?ok=0 is not admitted, ?ok=boom makes admit
    raise, ?fail=<code> answers that status."""
    app = Flask(__name__)
    calls = []

    def admit(args):
        if args.get("ok") == "boom":
            raise RuntimeError("v218 boom")
        return args.get("ok") != "0"

    @app.get("/thing")
    @cond.conditional("thing", admit)
    @read_scope
    def thing():
        calls.append(request.args.to_dict())
        if request.args.get("fail"):
            return jsonify(error="nope"), int(request.args["fail"])
        return jsonify(n=len(calls))

    app.calls = calls
    return app


def _tag(args=None, key="thing"):
    with Flask(__name__).test_request_context("/thing", query_string=args or {}):
        return cond.compute_etag(key, request.args)


# --- tag shape and inputs ---------------------------------------------------

def test_the_tag_is_weak_and_32_hex(inputs):
    tag = _tag()
    assert tag.startswith('W/"') and tag.endswith('"')
    opaque = tag[3:-1]
    assert len(opaque) == 32 and int(opaque, 16) >= 0


def test_the_same_inputs_give_the_same_tag(inputs):
    assert _tag({"status": "CLOSED"}) == _tag({"status": "CLOSED"})


@pytest.mark.parametrize("name, value", [
    ("build", "fedcba9876543210|img:2"),
    ("token", (2, 2, 3)),
    ("token", (1, 3, 3)),
    ("token", (1, 2, 4)),
    ("versions", ((6, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:00+00:00"), (2, None))),
    ("versions", ((5, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:01+00:00"), (2, None))),
    ("versions", ((5, "2026-11-04T10:00:00+00:00"), (7, "2026-11-04T11:00:00+00:00"), (3, "x"))),
    ("fx", (41, dt.datetime(2026, 11, 4, 6, 0, tzinfo=dt.timezone.utc))),
    ("today", dt.date(2026, 11, 5)),
    ("principal", ("viewer", "anna", 7)),
])
def test_each_input_changes_the_tag_on_its_own(inputs, name, value):
    before = _tag({"status": "CLOSED"})
    inputs[name] = value
    assert _tag({"status": "CLOSED"}) != before


def test_the_query_and_the_route_key_change_the_tag(inputs):
    base = _tag({"status": "CLOSED"})
    assert _tag({"status": "CLOSED", "page": "2"}) != base
    assert _tag({"status": "CLOSED"}, key="other") != base


def test_the_inputs_are_exactly_the_documented_ones(inputs):
    with Flask(__name__).test_request_context("/thing?status=CLOSED"):
        got = cond.etag_inputs("thing", request.args)
    assert got == ("thing", inputs["build"], inputs["token"], inputs["versions"], inputs["fx"],
                   "status=CLOSED", "2026-11-04", inputs["principal"])


def test_normalised_query_ignores_order_and_keeps_every_value():
    a = MultiDict([("status", "CLOSED"), ("sort", "-closed_at"), ("ticker", "a"), ("ticker", "b")])
    b = MultiDict([("ticker", "a"), ("sort", "-closed_at"), ("ticker", "b"), ("status", "CLOSED")])
    assert cond.normalised_query(a) == cond.normalised_query(b)
    assert cond.normalised_query(a) != cond.normalised_query(MultiDict([("ticker", "a")]))
    assert cond.normalised_query(MultiDict()) == ""


# --- If-None-Match ----------------------------------------------------------

@pytest.mark.parametrize("header, hit", [
    (None, False), ("", False),
    ('W/"abc"', True), ('"abc"', True), ('W/"zzz", W/"abc"', True), ("*", True),
    ('W/"abcd"', False), ('W/"ab"', False),
])
def test_if_none_match_accepts_weak_strong_lists_and_star(header, hit):
    assert cond.if_none_match_hits(header, 'W/"abc"') is hit


# --- the decorator ----------------------------------------------------------

def test_a_200_carries_the_tag_and_private_no_cache(inputs, tiny):
    response = tiny.test_client().get("/thing")
    assert response.status_code == 200
    assert response.headers["ETag"].startswith('W/"')
    assert response.headers["Cache-Control"] == "private, no-cache"


def test_a_matching_if_none_match_is_a_bodiless_304_that_skips_the_view(inputs, tiny):
    client = tiny.test_client()
    tag = client.get("/thing").headers["ETag"]
    response = client.get("/thing", headers={"If-None-Match": tag})
    assert response.status_code == 304
    assert response.get_data() == b""
    assert response.headers["ETag"] == tag
    assert response.headers["Cache-Control"] == "private, no-cache"
    assert len(tiny.calls) == 1                     # the body was built once, for the 200


def test_a_stale_if_none_match_gets_a_fresh_200(inputs, tiny):
    client = tiny.test_client()
    tag = client.get("/thing").headers["ETag"]
    inputs["token"] = (9, 9, 9)
    response = client.get("/thing", headers={"If-None-Match": tag})
    assert response.status_code == 200 and response.headers["ETag"] != tag


@pytest.mark.parametrize("code", [400, 401, 403, 404, 500])
def test_an_error_status_never_carries_a_tag(inputs, tiny, code):
    response = tiny.test_client().get(f"/thing?fail={code}")
    assert response.status_code == code
    assert "ETag" not in response.headers
    assert response.headers.get("Cache-Control") != "private, no-cache"


@pytest.mark.parametrize("setup", ["switch_off", "disconnected", "fresh", "not_admitted",
                                   "admit_raises", "input_raises", "build_missing"])
def test_every_ineligible_or_failing_request_runs_the_view_without_a_tag(inputs, tiny, monkeypatch,
                                                                        setup):
    headers, query = {}, ""
    if setup == "switch_off":
        monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "off", raising=False)
    elif setup == "disconnected":
        monkeypatch.setattr(store_generation, "connected", lambda: False)
    elif setup == "fresh":
        headers["X-Swingbot-Fresh"] = "1"
    elif setup == "not_admitted":
        query = "?ok=0"
    elif setup == "admit_raises":
        query = "?ok=boom"
    elif setup == "input_raises":
        monkeypatch.setattr(store_snapshot, "request_versions", _raise)
    else:
        monkeypatch.setattr(build_identity, "build_version", _raise_os)
    response = tiny.test_client().get("/thing" + query, headers={**headers, "If-None-Match": "*"})
    assert response.status_code == 200                 # '*' would 304 if a tag were computed
    assert "ETag" not in response.headers
    assert len(tiny.calls) == 1                         # the view ran, unchanged


def test_the_markers_survive_and_name_the_route():
    @cond.conditional("thing", lambda args: True)
    @read_scope
    def view():
        return "ok"

    assert getattr(view, cond.CONDITIONAL_ATTR) == "thing"
    assert getattr(view, READ_SCOPE_ATTR) is True
    assert view.__name__ == "view"


def _raise(*_a, **_k):
    raise RuntimeError("v218 boom")


def _raise_os(*_a, **_k):
    raise OSError("VERSION.json missing")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_conditional.py`
Expected: FAIL with `ImportError: cannot import name 'conditional'`.

- [ ] **Step 3: Write the module**

Create `swingbot/admin/api_v1/conditional.py`:

```python
"""v218 P3-c: weak ETag and 304 for allow-listed admin GET views.

``@conditional(route_key, admit)`` sits under ``@require_auth`` (a 401 never
reaches it) and above ``@read_scope`` (a 304 opens no scope and builds
nothing). The tag is computed **before** the view runs, from its inputs
alone: the build, the store generations, the plans/trades/journal
``version()`` tuples (read once per request, shared with the snapshot), the
FX daily table's version, the normalised query, the Berlin date and the
principal. A matching ``If-None-Match`` returns a bodiless 304, which skips
the route's work as well as its bytes. A 200 carries the tag and
``Cache-Control: private, no-cache``; any other status carries neither.

No tag at all -- the view runs exactly as before -- when the switch
``ADMIN_STORE_SNAPSHOT`` is off, the snapshot listener is not connected, the
client sent ``X-Swingbot-Fresh: 1``, ``admit(request.args)`` says no, or any
input raises (logged once through ``swallowed``). Which views carry the
decorator is pinned exactly by tests/admin_perf/test_conditional_routes.py.
"""
from __future__ import annotations

import functools
import hashlib
import logging
from typing import Callable, TypeVar
from urllib.parse import urlencode

from flask import make_response, request
from werkzeug.datastructures import MultiDict

from swingbot import config
from swingbot.admin import build_identity
from swingbot.core.infra import store_generation, store_snapshot
from swingbot.core.infra.swallowed import swallowed
from swingbot.core.marketdata import fx_convert

log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable)

CONDITIONAL_ATTR = "__conditional__"
CACHE_CONTROL = "private, no-cache"
_TAG_HEX = 32


def normalised_query(args: MultiDict) -> str:
    """Every (key, value) pair, sorted, url-encoded: order never changes the tag."""
    return urlencode(sorted(args.items(multi=True)))


def _fx_version() -> tuple:
    from swingbot.core.db.repositories.market_refresh import fx_daily_rate_repo
    return fx_daily_rate_repo().version()


def _principal() -> tuple:
    """(role, username, user_id); a Basic-auth caller passed require_auth as the admin."""
    from swingbot.admin import app as _app
    who = _app.resolve_principal()
    if who is not None:
        return (who.get("role"), who.get("username"), who.get("user_id"))
    auth = request.authorization
    return ("admin", auth.username if auth else None, None)


def etag_inputs(route_key: str, args: MultiDict) -> tuple:
    """Exactly the documented inputs, in a fixed order."""
    return (route_key, build_identity.build_version(), store_generation.token(),
            store_snapshot.request_versions(), _fx_version(), normalised_query(args),
            fx_convert.berlin_today().isoformat(), _principal())


def _eligible() -> bool:
    from swingbot.admin.freshness import FRESH_HEADER
    return (config.ADMIN_STORE_SNAPSHOT == "on" and store_generation.connected()
            and request.headers.get(FRESH_HEADER) != "1")


def compute_etag(route_key: str, args: MultiDict) -> str | None:
    """``W/"<32 hex>"``, or None when ineligible or when any input raises."""
    try:
        if not _eligible():
            return None
        digest = hashlib.sha256(repr(etag_inputs(route_key, args)).encode("utf-8")).hexdigest()
    except Exception as exc:
        swallowed(log, "ops.admin.etag", exc)
        return None
    return f'W/"{digest[:_TAG_HEX]}"'


def _opaque(tag: str) -> str:
    tag = tag.strip()
    return tag[2:] if tag.startswith("W/") else tag


def if_none_match_hits(header: str | None, tag: str) -> bool:
    """True for ``*`` or any listed tag equal to ``tag``, weak or strong form."""
    if not header:
        return False
    want = _opaque(tag)
    return any(part.strip() == "*" or _opaque(part) == want for part in header.split(","))


def _admitted(admit: Callable[[MultiDict], bool]) -> bool:
    try:
        return bool(admit(request.args))
    except Exception as exc:
        swallowed(log, "ops.admin.etag", exc)
        return False


def _with_tag(response, tag: str):
    response.headers["ETag"] = tag
    response.headers["Cache-Control"] = CACHE_CONTROL
    return response


def conditional(route_key: str, admit: Callable[[MultiDict], bool]) -> Callable[[F], F]:
    """Weak ETag / 304 for one GET view; place it under @require_auth, above @read_scope."""

    def decorate(view: F) -> F:
        @functools.wraps(view)
        def wrapper(*args, **kwargs):
            tag = compute_etag(route_key, request.args) if _admitted(admit) else None
            if tag is not None and if_none_match_hits(request.headers.get("If-None-Match"), tag):
                return _with_tag(make_response("", 304), tag)
            response = make_response(view(*args, **kwargs))
            if tag is not None and response.status_code == 200:
                _with_tag(response, tag)
            return response

        setattr(wrapper, CONDITIONAL_ATTR, route_key)
        return wrapper  # type: ignore[return-value]

    return decorate
```

Notes for the implementer:
- `config`, `store_generation`, `store_snapshot`, `build_identity` and `fx_convert` are imported as **modules** and looked up at call time, which is what lets the tests (and V218-13) monkeypatch them.
- A view that raises `ApiError` (a 400 or 404) propagates through `wrapper` before any header is set, and the blueprint's error handler builds the response, so an error never carries a tag.
- `swallowed(log, "ops.admin.etag", exc)` matches the call shape used in `request_timing.py`. Check `swingbot/core/infra/swallowed.py` for its exact signature before relying on extra arguments.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_conditional.py`
Expected: PASS (all cases green).

Check complexity: `python -m radon cc -s swingbot/admin/api_v1/conditional.py`. Every function stays below 15 (all are grade A).

Check that nothing else moved: `python scripts/dev/testrun.py file tests/admin_perf/test_read_scope_routes.py`. Expected PASS, since no view carries the decorator yet.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/conditional.py tests/admin_perf/test_conditional.py
git commit -m "feat(admin): conditional-response decorator -- weak ETag before the body, bodiless 304, private no-cache"
```

### Task V218-9: `Server-Timing` gains `app;dur` and `snap;desc`

**Model:** sonnet — a pinned header format extended in one function, its parser and their tests, with the exact strings given.

**Files:**
- Modify: `swingbot/admin/request_timing.py` (`server_timing`, `_finish`, new `_snap_state`)
- Modify: `tests/admin_perf/test_server_timing.py`
- Modify: `scripts/ops/admin_endpoint_timing.py` (`parse_server_timing`, `time_endpoints`)
- Modify: `tests/scripts/test_admin_endpoint_timing.py`

**Interfaces:**
- Consumes: `store_snapshot.request_state() -> str` in `{"off", "miss", "hit"}` (V218-4); `store_snapshot.begin_request()` already called from `request_timing._begin` (V218-5, same file: this task runs after it); fixture `snapshot_on` (V218-5, `tests/admin_perf/conftest.py`).
- Produces: `request_timing.server_timing(total_s: float, tally: SqlTally, snap: str = "off") -> str`, giving `total;dur=<ms>, db;dur=<ms>;desc="<n> statements", app;dur=<ms>, snap;desc=<hit|miss|off>`. `admin_endpoint_timing.parse_server_timing` also returns `"app": {"dur"}` and `"snap": {"desc"}` when present, and every `time_endpoints` row gains `"app_ms"` and `"snap"` (None when absent).

Rules (index § Global Constraints): `total` and `db` stay first and unchanged; `app` and `snap` are appended. `app` is wall time minus db time, computed from the two **rounded** values (`round(total_ms, 1) - round(db_ms, 1)`, floored at 0) so the three numbers in one header always add up. `snap` comes from `store_snapshot.request_state()`; if that raises, the header says `off` (a timing header must never fail a response). The regex and the exact-string test change in the same commit. Production captures are never asserted whole, because Cloudflare appends `cfExtPri`.

- [ ] **Step 1: Write the failing tests**

In `tests/admin_perf/test_server_timing.py`, replace `HEADER_RE` and `test_the_header_has_exactly_the_documented_format`, and add the new tests below the existing ones. Keep every other existing test as it is (they use `HEADER_RE`, which now requires the two new entries).

```python
HEADER_RE = re.compile(r'^total;dur=\d+\.\d, db;dur=\d+\.\d;desc="(\d+) statements", '
                       r'app;dur=\d+\.\d, snap;desc=(hit|miss|off)$')


def test_the_header_has_exactly_the_documented_format():
    tally = request_timing.SqlTally(statements=3, db_s=0.01234)
    assert request_timing.server_timing(1.23456, tally) == (
        'total;dur=1234.6, db;dur=12.3;desc="3 statements", app;dur=1222.3, snap;desc=off')


def test_app_is_total_minus_db_and_never_negative():
    tally = request_timing.SqlTally(statements=1, db_s=0.5)
    assert request_timing.server_timing(0.4, tally, "miss").endswith("app;dur=0.0, snap;desc=miss")
    assert "app;dur=990.0" in request_timing.server_timing(1.0, request_timing.SqlTally(1, 0.01), "hit")


@pytest.mark.parametrize("state", ["hit", "miss", "off"])
def test_the_snap_entry_carries_the_request_state(client, auth, sql_counted, monkeypatch, state):
    from swingbot.core.infra import store_snapshot
    monkeypatch.setattr(store_snapshot, "request_state", lambda: state)
    header = client.get("/api/v1/trades", headers=auth).headers["Server-Timing"]
    match = HEADER_RE.match(header)
    assert match and match.group(2) == state, header


def test_a_failing_state_read_says_off_and_the_response_still_succeeds(client, auth, sql_counted,
                                                                       monkeypatch):
    from swingbot.core.infra import store_snapshot

    def boom():
        raise RuntimeError("v218 state read failed")

    monkeypatch.setattr(store_snapshot, "request_state", boom)
    response = client.get("/api/v1/trades", headers=auth)
    assert response.status_code == 200
    assert response.headers["Server-Timing"].endswith("snap;desc=off")


def test_with_the_switch_off_every_request_says_off(client, auth, sql_counted, monkeypatch):
    from swingbot import config
    monkeypatch.setattr(config, "auto_reload_if_changed", lambda *a, **k: None)
    monkeypatch.setattr(config, "ADMIN_STORE_SNAPSHOT", "off")
    for _ in range(2):
        header = client.get("/api/v1/trades", headers=auth).headers["Server-Timing"]
        assert header.endswith("snap;desc=off"), header


def test_a_second_scoped_request_on_a_connected_snapshot_is_a_hit(client, auth, sql_counted,
                                                                  snapshot_on):
    first = client.get("/api/v1/trades", headers=auth).headers["Server-Timing"]
    second = client.get("/api/v1/trades", headers=auth).headers["Server-Timing"]
    assert first.endswith("snap;desc=miss"), first
    assert second.endswith("snap;desc=hit"), second
```

Add `import pytest` to the file's imports (it has `logging`, `re`, `config`, `request_timing` today).

In `tests/scripts/test_admin_endpoint_timing.py`, add:

```python
def test_parse_reads_app_and_snap_and_ignores_the_cdn_entry():
    header = ('total;dur=1234.6, db;dur=12.3;desc="3 statements", app;dur=1222.3, '
              'snap;desc=hit, cfExtPri')
    assert timing.parse_server_timing(header) == {
        "total": {"dur": 1234.6}, "db": {"dur": 12.3, "statements": 3},
        "app": {"dur": 1222.3}, "snap": {"desc": "hit"}}


@pytest.mark.parametrize("header", ["snap;desc=maybe", "snap", "app;dur=x"])
def test_an_unknown_snap_or_a_malformed_app_is_left_out(header):
    parsed = timing.parse_server_timing(header)
    assert "snap" not in parsed and "app" not in parsed


def test_time_endpoints_rows_carry_app_and_snap():
    client = _Client(_Response(header='total;dur=5.0, db;dur=1.5;desc="3 statements", '
                                      'app;dur=3.5, snap;desc=miss'))
    [row] = timing.time_endpoints(client, {}, {"trades": "/api/v1/trades"}, runs=1)
    assert (row["app_ms"], row["snap"]) == (3.5, "miss")


def test_an_older_server_without_the_entries_gives_none():
    client = _Client(_Response(header='total;dur=5.0, db;dur=1.5;desc="3 statements"'))
    [row] = timing.time_endpoints(client, {}, {"trades": "/api/v1/trades"}, runs=1)
    assert row["app_ms"] is None and row["snap"] is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_server_timing.py`
Expected: FAIL. The header has no `app;dur` or `snap;desc`, and `server_timing()` takes no `snap` argument.

Run: `python scripts/dev/testrun.py file tests/scripts/test_admin_endpoint_timing.py`
Expected: FAIL with `KeyError: 'app_ms'`, and the parse test misses `app`/`snap`.

- [ ] **Step 3: Implement**

In `swingbot/admin/request_timing.py`, add the import beside the others:

```python
from swingbot.core.infra import store_snapshot
```

Replace `server_timing` and `_finish`, and add `_snap_state` below `_finish`:

```python
def server_timing(total_s: float, tally: SqlTally, snap: str = "off") -> str:
    """The header value. ``total`` and ``db`` first and unchanged (V205-1's
    script parses them); ``app`` is total minus db from the rounded values,
    so the three always add up; ``snap`` is the snapshot's state (v218 P3-d)."""
    total_ms = round(total_s * 1000, 1)
    db_ms = round(tally.db_s * 1000, 1)
    app_ms = max(round(total_ms - db_ms, 1), 0.0)
    return (f"total;dur={total_ms:.1f}, "
            f'db;dur={db_ms:.1f};desc="{tally.statements} statements", '
            f"app;dur={app_ms:.1f}, snap;desc={snap}")


def _finish(response):
    state = g.get(_G_KEY)
    if state is None:
        return response
    total_s = time.perf_counter() - state[0]
    tally = current() or SqlTally()
    response.headers["Server-Timing"] = server_timing(total_s, tally, _snap_state())
    _log_if_slow(request.path, total_s, tally)
    return response


def _snap_state() -> str:
    """hit | miss | off for this request; a failing read is ``off``, never a failed response."""
    try:
        return store_snapshot.request_state()
    except Exception as exc:
        swallowed(log, "ops.request_timing.snap_state", exc, level=logging.DEBUG)
        return "off"
```

Leave `_begin` exactly as V218-5 left it (it calls `store_snapshot.begin_request()`). If V218-5 imported `store_snapshot` under another name, reuse that import rather than adding a second one.

In `scripts/ops/admin_endpoint_timing.py`, replace `parse_server_timing` and add `_snap_desc` above it:

```python
_DUR_METRICS = ("total", "db", "app")
_SNAP_STATES = ("hit", "miss", "off")


def _snap_desc(params: list[str]) -> str | None:
    """The ``desc`` of a v218 ``snap`` entry when it is one of the three states."""
    for param in params:
        key, _, value = param.partition("=")
        if key == "desc" and value.strip('"') in _SNAP_STATES:
            return value.strip('"')
    return None


def parse_server_timing(header: str | None) -> dict[str, dict]:
    """``total``/``db``/``app`` durations (``db`` with its statements) and v218's
    ``snap`` state; foreign entries (Cloudflare's ``cfExtPri``) and anything
    unreadable are left out, so an older server simply lacks the new keys."""
    parsed: dict[str, dict] = {}
    for part in (header or "").split(","):
        bits = [bit.strip() for bit in part.split(";")]
        if bits[0] in _DUR_METRICS:
            entry = _metric(bits[1:])
            if "dur" in entry:
                parsed[bits[0]] = entry
        elif bits[0] == "snap" and (state := _snap_desc(bits[1:])) is not None:
            parsed["snap"] = {"desc": state}
    return parsed
```

In `time_endpoints`, parse once and add the two fields to each row. Replace the loop body after `elapsed_ms` with:

```python
            timing = parse_server_timing(response.headers.get("Server-Timing"))
            db = timing.get("db", {})
            rows.append({"name": name, "path": path, "run": run,
                         "status": response.status_code, "ms": round(elapsed_ms, 1),
                         "bytes": len(response.get_data()),
                         "db_ms": db.get("dur"), "statements": db.get("statements"),
                         "app_ms": timing.get("app", {}).get("dur"),
                         "snap": timing.get("snap", {}).get("desc")})
```

`format_table` keeps its columns: the probe's comparison tables do not change shape in this plan.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_server_timing.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/scripts/test_admin_endpoint_timing.py`
Expected: PASS.

Find any other parser of the header and run it: `git grep -n "Server-Timing\|server_timing" -- tests scripts`. Run every test file that the search shows asserting the header string (for example probe tests under `tests/scripts/`) with `python scripts/dev/testrun.py file <file>`. Fix only assertions on the exact `total, db` string. The probe stores the raw header, so its own code needs no change.

Check complexity: `python -m radon cc -s swingbot/admin/request_timing.py scripts/ops/admin_endpoint_timing.py`. `parse_server_timing` stays below 15 (about 6), and `time_endpoints` stays below 15.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/request_timing.py tests/admin_perf/test_server_timing.py
git commit -m "feat(admin): Server-Timing gains app;dur and snap;desc (v206 P3-d)"
git add scripts/ops/admin_endpoint_timing.py tests/scripts/test_admin_endpoint_timing.py
git commit -m "feat(ops): endpoint timing reads app;dur and snap;desc"
```


# Phase P3-c audits — which routes may answer 304

### Task V218-10: Audit `/trades`: classify every key of the closed page, record the verdict

**Model:** opus — a cache-admission audit where one unclassified input silently serves a stale body; the ET-date finding below has to be reasoned about, not pattern-matched.

**Files:**
- Create: `tests/admin_perf/test_trades_conditional_audit.py`
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (append `### Plan 3 route audits (V218-10..12)` at the end of the file, after V218-7's `### Plan 3 build tag on the VM (V218-7)`)

This task pins the evidence and writes the verdict. It changes no production code. V218-10b turns the verdict into `closed_only_query` and the decorator (split from this task at the 20 KB cap).

**Interfaces:**
- Consumes: fixture `snapshot_on` (V218-5, `tests/admin_perf/conftest.py`). Existing: `rank.follow_score(plan, *, today=None)` (`swingbot/core/analytics/rank.py:48`), fixtures `golden_seed`, `frozen_clock`, `logged_in`, `gb.FROZEN_NOW`, golden `tests/admin_perf/golden/trades.json` (its four CLOSED rows carry exactly the `ROW_KEYS` below, checked when this plan was written).
- Produces (V218-10b and V218-13 rely on these exact names in `tests/admin_perf/test_trades_conditional_audit.py`): `CLOSED = "/api/v1/trades?status=CLOSED"`; `UTC`; fixture `refresher_on` (config `ADMIN_REFRESHER` and `MARKETDATA_LAYER` on, `auto_reload_if_changed` a no-op); fixture `closed_page` (`golden_seed` + `frozen_clock` + `refresher_on` + `snapshot_on` + `logged_in`, returns the logged-in client).

**The audit.** Every top-level key and every row key of `GET /api/v1/trades?status=CLOSED` on the golden book is classified in the test by where its value comes from. A key missing from the table, or a table key the page no longer carries, fails the test, so a future field forces a re-audit.

| Class | Meaning | Covered by |
|---|---|---|
| `stored` | copied or computed from the plan and trade records alone | the trades generation and `TradeRepository`/`PlanRepository.version()` |
| `day` | depends on the Berlin date (`today`, via `dash.is_today_berlin`) | `fx_convert.berlin_today()` in the tag |
| `journal` | `has_note` (`_noted_ids`, `trades.py:722`) | the journal generation and `JournalRepository.version()` |
| `fx-daily` | the converted `realized_pnl_amount` and its `fx_missing` flag | `fx_daily_rate_repo().version()`, **only with the refresher on** (finding 1) |
| `et-day` | `follow_score`: the ET date through `session.market_today()` | the Berlin date, **only while the ET and Berlin dates agree** (finding 2) |
| `unpriced` | live-price fields, always None or False on a closed row | nothing to key: asserted empty |
| `query` | paging (`page`, `per_page`, `total`) | the normalised query and the stored records |
| `rows` | `market_meta`: built from the page rows alone (`total_meta([], extra_missing=fx)`) | the rows' own classes |

Settings (the account currency through `config.CURRENCY_SYMBOL`) reach every money field and are covered by the settings generation.

Findings (V218-10b implements the shape they allow):
1. **FX source.** With the refresher off, `to_account_currency` fetches (`money.py:29`): a closed row's rate can come from the pair frame (`fx.fx_rate` → `rate_before`), which `fx_daily_rate_repo().version()` does not cover. A trade closed today can change its converted amount when yesterday's bar lands. So the shape is admitted only while `admin_refresh.refresher_on()` (production runs with it on), when conversion reads the stored daily rows alone.
2. **ET date.** `_attach_follow_scores` (`trades.py:772`) scores every plan-backed row, closed ones included, and `follow_score`'s freshness component counts days from `session.market_today()`, the **ET** date (`rank.py:48-73`). In November the ET date turns at 05:00 UTC, which is 06:00 Berlin, inside a Berlin day, so a tag keyed on the Berlin date alone could serve a stale `follow_score` after 06:00. The tag's inputs stay exactly as V218-8 fixed them. Instead the shape is admitted only while `session.market_today() == fx_convert.berlin_today()`: from 06:00 to 24:00 Berlin the two dates are the same, so the Berlin date in the tag also keys the ET date. Between 00:00 and 06:00 Berlin the page is served without a tag.
3. **Sorts that price rows.** `sort` on `pnl_pct` or `r_multiple`, or on `status` (an alias of `progress_pct`, `trades.py:1058`), prices the whole set before slicing. These shapes are excluded, so the admitted shape never touches a live price.
4. **`held_hours`** measures to now only when `closed_at` is missing (`_held_hours`, `trades.py:184`). A CLOSED row always has one (`_terminal_at`), and the test asserts it on every row.
5. **`outcome`** is the legacy trade status (`trades.py:642`), so `outcome=win|loss` returns closed rows only. The test asserts that on the golden book.

- [ ] **Step 1: Write the audit tests**

Tests reach Postgres: run `/replicate-prod-db` once per session first (shared `swing-db`, never a per-task database).

Create `tests/admin_perf/test_trades_conditional_audit.py`:

```python
"""v218 V218-10: /trades audited for the conditional allow-list (v206 P3-c).

Admitted shape: status=closed or outcome=win|loss, no sort that prices rows,
the refresher on, and the ET date equal to the Berlin date. The record is
docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
`### Plan 3 route audits (V218-10..12)`; the allow-list and the ETag behaviour
are tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

import pytest

CLOSED = "/api/v1/trades?status=CLOSED"
UTC = dt.timezone.utc

TOP_LEVEL = {"items": "rows", "market_meta": "rows", "page": "query", "per_page": "query",
             "total": "query", "prices_as_of": "unpriced"}

_STORED = (
    "badge banked_contribution_r banked_exit_price banked_fraction banked_r bar_kind "
    "bars_to_expiry best_pnl_pct closed_at cohort_label cohort_stats confidence_level "
    "confidence_score created_at direction distance_to_trigger_r entry entry_shares exit_price "
    "floor_r headroom_r held_hours horizon id leg_exit_reason leg_index leg_total open_shares "
    "opened_at origin outcome pnl_pct position_value price_r quality_score r_multiple "
    "risk_reward risk_stop runner_best runner_exit_price runner_exit_reason shares status "
    "status_label stop_kind stop_loss stop_pnl_pct strategy target target1 target2 "
    "target_is_banked_tp1 ticker tier tp1 trigger_price").split()
_UNPRICED = ("current_price current_price_stale price_age_s price_as_of progress_pct entry_pct "
             "progress_band blink_seconds").split()
ROW_KEYS = {**{k: "stored" for k in _STORED}, **{k: "unpriced" for k in _UNPRICED},
            "today": "day", "has_note": "journal", "realized_pnl_amount": "fx-daily",
            "fx_missing": "fx-daily", "follow_score": "et-day"}


@pytest.fixture
def refresher_on(admin_app, monkeypatch):
    """The refresher on (closed-row FX from the stored daily rows only); no .env reload."""
    from swingbot import config
    monkeypatch.setattr(config, "auto_reload_if_changed", lambda *a, **k: {})
    monkeypatch.setattr(config, "ADMIN_REFRESHER", "on")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")


@pytest.fixture
def closed_page(golden_seed, frozen_clock, refresher_on, snapshot_on, logged_in):
    """The golden book behind an admitted /trades shape: snapshot vouched for, refresher on."""
    return logged_in


def _body(client, path=CLOSED):
    response = client.get(path)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


# --- the classification ----------------------------------------------------

def test_every_key_of_a_closed_page_is_classified(closed_page):
    body = _body(closed_page)
    assert set(body) == set(TOP_LEVEL)
    seen = set().union(*(set(row) for row in body["items"]))
    assert seen - set(ROW_KEYS) == set(), f"unclassified keys, re-audit: {seen - set(ROW_KEYS)}"
    assert set(ROW_KEYS) - seen == set(), f"keys gone from the page: {set(ROW_KEYS) - seen}"


def test_a_closed_page_holds_closed_rows_with_nothing_priced(closed_page):
    body = _body(closed_page)
    assert len(body["items"]) == 4
    assert body["prices_as_of"] is None
    assert body["market_meta"]["as_of"] is None and body["market_meta"]["refreshing"] is False
    for row in body["items"]:
        assert row["status"] == "CLOSED" and row["closed_at"], row["id"]
        for key in _UNPRICED:
            assert row[key] in (None, False), (row["id"], key, row[key])


@pytest.mark.parametrize("outcome", ["win", "loss", "WIN"])
def test_an_outcome_filter_returns_closed_rows_only(closed_page, outcome):
    rows = _body(closed_page, f"/api/v1/trades?outcome={outcome}")["items"]
    assert rows and all(row["status"] == "CLOSED" for row in rows)


def test_follow_score_moves_with_the_et_date():
    from swingbot.core.analytics.rank import follow_score
    plan = {"badge": "VALIDATED", "quality_score": 72, "created_at": "2026-11-03"}
    assert follow_score(plan, today=dt.date(2026, 11, 4)) != follow_score(plan, today=dt.date(2026, 11, 5))
```

- [ ] **Step 2: Run the audit tests**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_trades_conditional_audit.py`
Expected: PASS. This task pins existing behaviour, so there is no red phase. The tests are evidence, and a failure here is a finding.

If the classification test fails on a key, stop. Classify the key by reading where `_row_from_plan` / `_row_from_trade` / the `_attach_*` helpers set it, and say so in the task report. A key that reads the clock or a live input is a new finding. It goes in the Results subsection, and if no tag input covers it, the shape cannot be admitted. That calls for a report to the controller before V218-10b starts, not a code change.

If `refresher_on` makes the closed page fail (a 500, or a request reaching the network), report it. The admitted shape requires the refresher on, so V218-10b cannot proceed without it.

- [ ] **Step 3: Record the audit in the v206 spec**

Append to the end of `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md`:

```markdown
### Plan 3 route audits (V218-10..12)

Each allow-list candidate was audited against the ETag inputs (v218 index
§ Global Constraints): every field of its body is either covered by an input,
or the route (or the query shape) stays off the list. A dropped route keeps
`Cache-Control: no-store`. The exact allow-list is pinned by
`tests/admin_perf/test_conditional_routes.py`.

- **`/trades`: admitted per query shape** (`trades.closed_only_query`, route
  key `trades`). The shape: `status=closed` or `outcome=win|loss`; no `sort` on
  `pnl_pct`, `r_multiple` or `status` (an alias of `progress_pct`), which price
  every row; the refresher on; and the ET date equal to the Berlin date.
  `tests/admin_perf/test_trades_conditional_audit.py` classifies every key of
  the closed page (stored records, Berlin day, journal, FX daily, ET day,
  unpriced, paging), and a new key fails it. Findings:
  - With the refresher off, a closed row's FX can come from the pair frame
    (`fx.fx_rate` → `rate_before`), which `fx_daily_rate_repo().version()`
    does not cover. So the shape needs the refresher on.
  - `follow_score` (`_attach_follow_scores`, `trades.py:772`) counts days from
    the ET date (`rank.follow_score`, `session.market_today()`), which turns
    at 06:00 Berlin. The tag keys the Berlin date, so the shape is admitted
    only while the two dates agree (06:00–24:00 Berlin). The tag inputs did
    not change.
  - `held_hours` reads the clock only for a row without `closed_at`; every
    closed row has one (asserted).
  - Unfiltered `/trades`, `status=open` and every other shape keep
    `no-store`: open rows carry live prices, `held_hours` to now,
    `prices_as_of` and `market_meta`.
```

- [ ] **Step 4: Commit**

```bash
git add tests/admin_perf/test_trades_conditional_audit.py
git commit -m "test(admin): /trades closed page audited key by key for the conditional allow-list"
git add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git commit -m "docs(v206): Plan 3 /trades conditional audit"
```

### Task V218-10b: Admit the `/trades` closed-only shape: `closed_only_query` and the decorator

**Model:** sonnet — the audit's verdict (V218-10) turned into a predicate and one decorator line, with the code and every test case given.

**Files:**
- Modify: `swingbot/admin/api_v1/trades.py` (decorator on `list_trades`; new `_PRICED_SORT_FIELDS`, `_CLOSED_OUTCOMES`, `_closed_filter`, `_priced_sort`, `closed_only_query`)
- Modify: `tests/admin_perf/test_trades_conditional_audit.py` (append the admission tests)

Split from V218-10 at the 20 KB cap. That task's audit table and its five findings are the reason for each clause below.

**Interfaces:**
- Consumes: `conditional(route_key, admit)`, `conditional.CONDITIONAL_ATTR`, `conditional.CACHE_CONTROL` (V218-8); `CLOSED`, `UTC`, fixtures `refresher_on` and `closed_page` (V218-10, same test file); `store_snapshot.request_versions()` (V218-4, through the decorator). Existing: `admin_refresh.refresher_on()` (`swingbot/core/marketdata/shared/admin_refresh.py:40`), `session.market_today()` (`swingbot/core/market/session.py:115`, the ET date), `fx_convert.berlin_today()` (`swingbot/core/marketdata/fx_convert.py:40`, already imported by `trades.py`), `_SORT_ALIASES` (`trades.py:1058`, `{"status": "progress_pct"}`), `READ_SCOPE_ATTR` (`swingbot/admin/api_v1/read_scope.py`), fixtures `admin_app`, `frozen_clock`, `gb.FROZEN_NOW`.
- Produces (V218-13 relies on these exact names): `trades.closed_only_query(args: MultiDict) -> bool`; route key `"trades"` on `list_trades` (`getattr(view, CONDITIONAL_ATTR) == "trades"`).

The admitted shape, all four required: `status` (stripped, lowercased) equals `closed`, or `outcome` is `win` or `loss`; `sort` (with or without a leading `-`) does not resolve, through `_SORT_ALIASES`, to `progress_pct`, `pnl_pct` or `r_multiple`; `admin_refresh.refresher_on()`; and `session.market_today() == fx_convert.berlin_today()`.

- [ ] **Step 1: Write the failing tests**

Tests reach Postgres: run `/replicate-prod-db` once per session first, unless a sibling task in this session already did.

Add to the imports of `tests/admin_perf/test_trades_conditional_audit.py`:

```python
from werkzeug.datastructures import MultiDict

from swingbot.admin.api_v1 import conditional as cond
from swingbot.admin.api_v1.read_scope import READ_SCOPE_ATTR
from tests.admin_perf import golden_book as gb
```

Append to the end of the file:

```python
# --- the admitted shape (V218-10b) ------------------------------------------

@pytest.mark.parametrize("pairs, admitted", [
    ([("status", "CLOSED")], True),
    ([("status", " closed ")], True),
    ([("outcome", "win")], True),
    ([("outcome", "LOSS")], True),
    ([("status", "closed"), ("sort", "-closed_at")], True),
    ([("status", "closed"), ("ticker", "aapl"), ("page", "2")], True),
    ([], False),
    ([("status", "open")], False),
    ([("status", "cancelled")], False),
    ([("outcome", "open")], False),
    ([("status", "closed"), ("sort", "-pnl_pct")], False),
    ([("status", "closed"), ("sort", "r_multiple")], False),
    ([("status", "closed"), ("sort", "status")], False),
])
def test_closed_only_query_admits_exactly_the_closed_shapes(admin_app, frozen_clock, refresher_on,
                                                            pairs, admitted):
    from swingbot.admin.api_v1 import trades
    assert trades.closed_only_query(MultiDict(pairs)) is admitted


def test_closed_only_query_needs_the_refresher(admin_app, frozen_clock):
    from swingbot.admin.api_v1 import trades
    assert trades.closed_only_query(MultiDict([("status", "closed")])) is False


@pytest.mark.parametrize("now, admitted", [
    (dt.datetime(2026, 11, 4, 4, 30, tzinfo=UTC), False),   # 05:30 Berlin 4 Nov, 23:30 ET 3 Nov
    (dt.datetime(2026, 11, 4, 5, 30, tzinfo=UTC), True),    # 06:30 Berlin 4 Nov, 00:30 ET 4 Nov
    (dt.datetime(2026, 11, 4, 22, 30, tzinfo=UTC), True),   # 23:30 Berlin 4 Nov, 17:30 ET 4 Nov
    (dt.datetime(2026, 11, 4, 23, 30, tzinfo=UTC), False),  # 00:30 Berlin 5 Nov, 18:30 ET 4 Nov
])
def test_closed_only_query_needs_the_et_and_berlin_dates_to_agree(admin_app, frozen_clock, refresher_on,
                                                                  monkeypatch, now, admitted):
    from swingbot.admin.api_v1 import trades
    monkeypatch.setattr(gb, "FROZEN_NOW", now)
    assert trades.closed_only_query(MultiDict([("status", "closed")])) is admitted


# --- the decorator on the real view ------------------------------------------

def test_list_trades_carries_the_trades_route_key_and_its_read_scope(admin_app):
    view = admin_app.view_functions["api_v1.list_trades"]
    assert getattr(view, cond.CONDITIONAL_ATTR) == "trades"
    assert getattr(view, READ_SCOPE_ATTR) is True


def test_a_304_skips_build_rows(closed_page, monkeypatch):
    from swingbot.admin.api_v1 import trades
    calls = []
    real = trades.build_rows

    def spying(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(trades, "build_rows", spying)
    first = closed_page.get(CLOSED)
    assert first.status_code == 200 and first.headers["ETag"].startswith('W/"')
    assert first.headers["Cache-Control"] == cond.CACHE_CONTROL
    second = closed_page.get(CLOSED, headers={"If-None-Match": first.headers["ETag"]})
    assert second.status_code == 304 and second.get_data() == b""
    assert calls == [1]                                     # the 304 built nothing


def test_the_unfiltered_list_keeps_no_store(closed_page):
    response = closed_page.get("/api/v1/trades")
    assert response.status_code == 200
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
```

US daylight time ended on 1 November 2026 and Berlin's on 25 October, so on 4 November ET is UTC−5 and Berlin is UTC+1. The four timestamps sit on either side of 05:00 UTC (ET midnight) and 23:00 UTC (Berlin midnight).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_trades_conditional_audit.py`
Expected: FAIL. The V218-10 audit tests and `test_the_unfiltered_list_keeps_no_store` still pass. The `closed_only_query` tests fail with `AttributeError: module 'swingbot.admin.api_v1.trades' has no attribute 'closed_only_query'`, the route-key test with `AttributeError: ... '__conditional__'`, and the 304 test with `KeyError: 'ETag'`.

- [ ] **Step 3: Admit the shape in `trades.py`**

Add the import beside the existing third-party imports (near `from flask import jsonify, request`):

```python
from werkzeug.datastructures import MultiDict
```

and beside `from .read_scope import read_scope`:

```python
from .conditional import conditional
```

Directly above `@api_v1.route("/trades", methods=["GET"])`, add:

```python
#: v218 P3-c: sorts that price the whole set before slicing (see `list_trades`),
#: so a page sorted on one may read a live price and is never conditional.
_PRICED_SORT_FIELDS = frozenset({"progress_pct", "pnl_pct", "r_multiple"})
_CLOSED_OUTCOMES = frozenset({"win", "loss"})


def _closed_filter(args: MultiDict) -> bool:
    """status=closed or outcome=win|loss, read the way `list_trades` reads them."""
    status = str(args.get("status") or "").strip().lower()
    outcome = str(args.get("outcome") or "").strip().lower()
    return status == "closed" or outcome in _CLOSED_OUTCOMES


def _priced_sort(args: MultiDict) -> bool:
    field = str(args.get("sort") or "").lstrip("-")
    return _SORT_ALIASES.get(field, field) in _PRICED_SORT_FIELDS


def closed_only_query(args: MultiDict) -> bool:
    """v218 P3-c: may this /trades query answer 304? The audit's verdict, as code.

    Only a page that can hold closed rows alone, with no sort that prices rows.
    Two more conditions come from the audit (v206 `### Plan 3 route audits`).
    The refresher must be on: off, a closed row's FX can come from the pair
    frame, which no tag input versions. And the ET date must equal the Berlin
    date: `follow_score` counts days in ET (`rank.follow_score`), and the tag
    keys only the Berlin date, so the shape is admitted from 06:00 to 24:00
    Berlin, when one date also names the other.
    """
    from swingbot.core.market import session
    from swingbot.core.marketdata.shared import admin_refresh
    return (_closed_filter(args) and not _priced_sort(args) and admin_refresh.refresher_on()
            and session.market_today() == fx_convert.berlin_today())
```

Change the decorators on `list_trades` (the body does not change; its complexity stays 32):

```python
@api_v1.route("/trades", methods=["GET"])
@require_auth
@conditional("trades", closed_only_query)
@read_scope
def list_trades():
```

`session` and `admin_refresh` are imported inside the function, the same way `_prices_as_of` imports `admin_refresh`, so the module's import graph does not change. Both date reads go through modules that `frozen_clock` already patches (`swingbot.core.market.session` and `swingbot.core.marketdata.fx_convert` are in `gb.CLOCK_MODULES`), so `CLOCK_MODULES` gains nothing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_trades_conditional_audit.py`
Expected: PASS.

Check that every existing `/trades` behaviour and golden is unchanged. In the admin suite `store_generation.connected()` is False (no listener in testing), so the decorator runs the view untouched:
- `python scripts/dev/testrun.py file tests/admin/test_api_v1_trades.py` (expected PASS)
- `python scripts/dev/testrun.py file tests/admin_perf/test_golden_endpoints.py` (expected PASS)
- `python scripts/dev/testrun.py file tests/admin_perf/test_read_scope_routes.py` (expected PASS: the read-scope marker survives the new decorator)
- `python scripts/dev/testrun.py file tests/admin_perf/test_snapshot_goldens.py` (expected PASS)

Check complexity: `python -m radon cc -s swingbot/admin/api_v1/trades.py | grep -E "list_trades|closed_only_query|_closed_filter|_priced_sort"`. `list_trades` stays E (32), the baseline value, and the three new functions are grade A. Then run `python scripts/dev/complexity_gate.py` and expect it to pass.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/api_v1/trades.py tests/admin_perf/test_trades_conditional_audit.py
git commit -m "feat(admin): /trades answers 304 for its closed-only shape -- refresher on, ET and Berlin dates agree"
```

### Task V218-11: Audit `/calendar/pnl` (admit or drop and record)

**Model:** sonnet — an evidence test of an existing payload and one Results bullet; the expected verdict and its file:line evidence are given.

**Files:**
- Create: `tests/admin_perf/test_calendar_conditional_audit.py`
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (append one bullet at the end of the file, under V218-10's `### Plan 3 route audits (V218-10..12)`)
- Modify: `swingbot/admin/api_v1/calendar.py` **only if the route is admitted**, which the evidence below rules out. If it does not, stop and report (Step 2).

**Interfaces:**
- Consumes: `conditional.CONDITIONAL_ATTR` (V218-8); the `### Plan 3 route audits (V218-10..12)` subsection (V218-10). Existing: `gb.ENDPOINTS["calendar_month"]` (`/api/v1/calendar/pnl?month=2026-11`), `gb.FROZEN_NOW`, `gb.diff_pointers(a, b) -> set[str]` (`tests/admin_perf/golden_book.py:283`), fixtures `golden_seed`, `frozen_clock`, `logged_in`, `admin_app`.
- Produces (V218-13's expected set): verdict `calendar_pnl` **dropped**, so `"api_v1.calendar_pnl"` is not in `CONDITIONAL`.

**Expected verdict: dropped.** The month body carries `as_of = dt.datetime.now(dt.timezone.utc).isoformat()`, documented as "the time this filtered view was composed" (`swingbot/core/analytics/page_bodies.py:352-354`). That is a `generated_at`-style stamp below day resolution, which v206 P3-c's rule excludes: no ETag input can cover it, so a 304 would hand the client an older `as_of` than a 200 would. Changing `as_of` would be a payload change outside this spec. Two more inputs sit outside the tag. `market_meta` comes from `request_market_meta` (refresher off), or, with the refresher on, from a stored `admin_snapshots` row whose `computed_at`, `refreshing`, `stale_inputs` and `error` follow the refresher (`swingbot/admin/api_v1/analytics.py:132-165`). And the default month, when `?month=` is absent, is `dt.date.today()` (`swingbot/admin/api_v1/calendar.py:62`), the process-local date rather than Berlin's.

- [ ] **Step 1: Write the evidence tests**

Tests reach Postgres: run `/replicate-prod-db` once per session first, unless a sibling task in this session already did.

Create `tests/admin_perf/test_calendar_conditional_audit.py`:

```python
"""v218 V218-11: /calendar/pnl audited for the conditional allow-list -- dropped (v206 P3-c).

The month body's `as_of` is the time the view was composed
(core/analytics/page_bodies.py:352-354): two requests five minutes apart on an
unchanged book differ, and no ETag input covers a value below day resolution.
`market_meta` follows the refresher (api_v1/analytics.py:132-165) and the
default month is the process-local date (api_v1/calendar.py:62). Recorded in
v206 `### Plan 3 route audits (V218-10..12)`; the allow-list itself is pinned by
tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

from swingbot.admin.api_v1 import conditional as cond
from tests.admin_perf import golden_book as gb

MONTH = gb.ENDPOINTS["calendar_month"]
NOON = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
REFRESHER_META = {"refreshing", "computed_at", "stale_inputs", "error", "source"}


def _month(client) -> dict:
    response = client.get(MONTH)
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


def test_as_of_moves_within_one_berlin_day_on_an_unchanged_book(golden_seed, frozen_clock, logged_in,
                                                                monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON)
    first = _month(logged_in)
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON + dt.timedelta(minutes=5))
    second = _month(logged_in)
    assert first["as_of"] != second["as_of"]
    assert "/as_of" in gb.diff_pointers(first, second)
    # The book did not change: the month's own numbers are identical.
    assert (first["days"], first["totals"]) == (second["days"], second["totals"])


def test_market_meta_carries_the_refresher_fields(golden_seed, frozen_clock, logged_in):
    assert REFRESHER_META <= set(_month(logged_in)["market_meta"])


def test_the_month_view_is_not_conditional(admin_app):
    view = admin_app.view_functions["api_v1.calendar_pnl"]
    assert not hasattr(view, cond.CONDITIONAL_ATTR)


def test_the_month_view_keeps_no_store(golden_seed, frozen_clock, logged_in):
    response = logged_in.get(MONTH)
    assert response.status_code == 200
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
```

- [ ] **Step 2: Run the evidence tests**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_calendar_conditional_audit.py`
Expected: PASS. The tests pin existing behaviour, so there is no red phase.

If `test_as_of_moves_within_one_berlin_day_on_an_unchanged_book` fails because `as_of` did **not** move, the evidence contradicts the expected verdict. Stop and report to the controller with the observed body. Admitting the route changes V218-13's expected set, and it needs its own key audit like V218-10's (`market_meta`, the default month), so it is not done inside this task. Any other failure is a test bug: fix the test, not the route.

- [ ] **Step 3: Record the verdict in the v206 spec**

Append to the end of `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (directly after V218-10's `/trades` bullet):

```markdown
- **`/calendar/pnl`: dropped.** The body's `as_of` is the time the filtered
  view was composed (`core/analytics/page_bodies.py:352-354`), a per-request
  stamp below day resolution that no ETag input covers: two requests five
  minutes apart on an unchanged book differ in `as_of` and nothing else in the
  month (`tests/admin_perf/test_calendar_conditional_audit.py`). Also outside
  the tag: `market_meta` follows the refresher (`computed_at`, `refreshing`,
  `stale_inputs`, `error` from the stored `admin_snapshots` row,
  `api_v1/analytics.py:132-165`), and the default month is the process-local
  `dt.date.today()` (`api_v1/calendar.py:62`). Admitting it would first need
  `as_of` changed, which is a payload change outside v206. It keeps `no-store`.
```

- [ ] **Step 4: Commit**

```bash
git add tests/admin_perf/test_calendar_conditional_audit.py
git commit -m "test(admin): /calendar/pnl audited for the conditional allow-list -- dropped, as_of is per request"
git add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git commit -m "docs(v206): Plan 3 /calendar/pnl audit verdict"
```

### Task V218-12: Audit `/calendar/pnl/day` (admit or drop and record)

**Model:** sonnet — the same evidence test as V218-11 on the day route, plus one recorded line for the sparklines route; verdicts and file:line evidence given.

**Files:**
- Create: `tests/admin_perf/test_calendar_day_conditional_audit.py`
- Modify: `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (append two bullets at the end of the file, after V218-11's `/calendar/pnl` bullet)
- Modify: `swingbot/admin/api_v1/calendar.py` **only if the route is admitted**, which the evidence below rules out. If it does not, stop and report (Step 2).

**Interfaces:**
- Consumes: `conditional.CONDITIONAL_ATTR` (V218-8); the `### Plan 3 route audits (V218-10..12)` subsection (V218-10, V218-11). Existing: `gb.ENDPOINTS["calendar_day"]` (`/api/v1/calendar/pnl/day?date=2026-11-03`), `gb.ENDPOINTS["calendar_sparklines"]` (`/api/v1/calendar/pnl/day/sparklines?date=2026-11-03`), `gb.FROZEN_NOW`, `gb.diff_pointers`, fixtures `golden_seed`, `frozen_clock`, `logged_in`, `admin_app`.
- Produces (V218-13's expected set): verdict `calendar_pnl_day` **dropped**, and `calendar_pnl_day_sparklines` **off without a key audit**, so neither `"api_v1.calendar_pnl_day"` nor `"api_v1.calendar_pnl_day_sparklines"` is in `CONDITIONAL`.

**Expected verdict: dropped.** The day body carries `as_of = dt.datetime.now(dt.timezone.utc).isoformat()` (`swingbot/admin/api_v1/calendar.py:157`), a per-request stamp below day resolution, the same rule as V218-11. One more input sits outside the tag: the day's rows are converted with `to_account_currency`, whose `fetch` flips with `admin_refresh.refresher_on()` (`swingbot/admin/api_v1/money.py:26-29`). With the refresher off, a rate can come from the pair frame, which no tag input versions (V218-10's finding 1).

**Sparklines: off without an audit.** `/calendar/pnl/day/sparklines` also stamps `as_of` per request (`calendar.py:202`). It reads daily bar frames through `data_store.load_normalized(ticker, "daily")` (`calendar.py:198-199`), and those frames are not snapshot-backed and have no version among the tag inputs. It stays off the allow-list; the test only pins the stamp and the missing marker.

- [ ] **Step 1: Write the evidence tests**

Tests reach Postgres: run `/replicate-prod-db` once per session first, unless a sibling task in this session already did.

Create `tests/admin_perf/test_calendar_day_conditional_audit.py`:

```python
"""v218 V218-12: /calendar/pnl/day audited for the conditional allow-list -- dropped (v206 P3-c).

The day body's `as_of` is stamped per request (api_v1/calendar.py:157), and its
FX `fetch` flag follows the refresher (api_v1/money.py:26-29). The sparklines
route also stamps `as_of` (calendar.py:202) and reads daily frames that no tag
input versions (calendar.py:198-199): it stays off without a key audit.
Recorded in v206 `### Plan 3 route audits (V218-10..12)`; the allow-list itself
is pinned by tests/admin_perf/test_conditional_routes.py (V218-13)."""
import datetime as dt

import pytest

from swingbot.admin.api_v1 import conditional as cond
from tests.admin_perf import golden_book as gb

NOON = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
ROUTES = {"calendar_day": "api_v1.calendar_pnl_day",
          "calendar_sparklines": "api_v1.calendar_pnl_day_sparklines"}


def _get(client, name: str) -> dict:
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, response.get_data(as_text=True)
    return response.get_json()


@pytest.mark.parametrize("name", list(ROUTES))
def test_as_of_moves_within_one_berlin_day_on_an_unchanged_book(name, golden_seed, frozen_clock,
                                                                logged_in, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON)
    first = _get(logged_in, name)
    monkeypatch.setattr(gb, "FROZEN_NOW", NOON + dt.timedelta(minutes=5))
    second = _get(logged_in, name)
    assert first["as_of"] != second["as_of"]
    assert gb.diff_pointers(first, second) == {"/as_of"}     # nothing about the book moved


def test_the_day_converts_with_a_fetch_flag_that_follows_the_refresher(admin_app, monkeypatch):
    from swingbot import config
    from swingbot.admin.api_v1 import money
    seen = []
    monkeypatch.setattr(money.fx_convert, "to_account_currency",
                        lambda rows, *, account=None, fetch: seen.append(fetch) or rows)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    for refresher in ("off", "on"):
        monkeypatch.setattr(config, "ADMIN_REFRESHER", refresher)
        money.to_account_currency([])
    assert seen == [True, False]


@pytest.mark.parametrize("name", list(ROUTES))
def test_the_day_views_are_not_conditional(name, admin_app):
    assert not hasattr(admin_app.view_functions[ROUTES[name]], cond.CONDITIONAL_ATTR)


@pytest.mark.parametrize("name", list(ROUTES))
def test_the_day_views_keep_no_store(name, golden_seed, frozen_clock, logged_in):
    response = logged_in.get(gb.ENDPOINTS[name])
    assert response.status_code == 200
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"
```

`gb.diff_pointers` returns the pointers of the leaves that differ. Only `/as_of` moving shows that the stamp is the clock and that the rest of each body is a function of the book.

- [ ] **Step 2: Run the evidence tests**

Run: `python scripts/dev/testrun.py file tests/admin_perf/test_calendar_day_conditional_audit.py`
Expected: PASS. The tests pin existing behaviour, so there is no red phase.

If the day route's `as_of` does **not** move, the evidence contradicts the expected verdict. Stop and report to the controller with the observed body. Admitting the route changes V218-13's expected set and needs a key audit like V218-10's (FX source, refresher on), so it is not done inside this task. If `diff_pointers` shows a pointer besides `/as_of`, that is a second clock-dependent field. Record it in the bullet below; it strengthens the drop. Any other failure is a test bug: fix the test, not the route.

- [ ] **Step 3: Record the verdicts in the v206 spec**

Append to the end of `docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md` (directly after V218-11's `/calendar/pnl` bullet):

```markdown
- **`/calendar/pnl/day`: dropped.** The body's `as_of` is stamped per request
  (`api_v1/calendar.py:157`), below day resolution: two requests five minutes
  apart on an unchanged book differ in `as_of` alone
  (`tests/admin_perf/test_calendar_day_conditional_audit.py`). Its FX
  conversion also fetches pair frames while the refresher is off
  (`api_v1/money.py:26-29`), which no tag input versions. It keeps `no-store`.
- **`/calendar/pnl/day/sparklines`: off, no key audit.** It stamps `as_of` per
  request (`calendar.py:202`) and reads daily bar frames through
  `data_store.load_normalized` (`calendar.py:198-199`), which are not
  snapshot-backed and have no version among the tag inputs.
```

- [ ] **Step 4: Commit**

```bash
git add tests/admin_perf/test_calendar_day_conditional_audit.py
git commit -m "test(admin): /calendar/pnl/day and sparklines audited for the conditional allow-list -- dropped"
git add docs/superpowers/specs/2026-11-05-v206-admin-under-load-design.md
git commit -m "docs(v206): Plan 3 calendar day and sparklines audit verdicts"
```
