"""v205 V205-8: no read path writes into a memoised record's nested values.

Inside read_memo.scope() each caller gets shallow copies: the top level of a record
is the caller's own, but nested values (legs, status_history, legs_realized,
cohort_stats, ...) are shared by every reader in the request. This module
deep-freezes everything the memo stores and runs the eight profiled endpoints inside
a scope: a nested write raises TypeError, the endpoint answers 500, and the traceback
names the writer. A guard on the test engine also fails any INSERT/UPDATE/DELETE or
row lock issued while a scope is open: a scoped GET must never write.

Audit verdict, per GET-path mutator (static audit 2026-11-04 plus this module):
- api_v1/trades.py _attach_current_prices (+ _attach_layer_prices, _attach_door_prices):
  top-level keys of rows built fresh by _row_from_plan/_row_from_trade -- acquitted.
- api_v1/trades.py _attach_unrealized_pnl: top-level row keys -- acquitted.
- api_v1/trades.py _strip_internal_fields: pops a top-level row key -- acquitted.
- admin/queries.py _plan_rows/_ranked_plan_rows: new dicts from plan_to_dict -- acquitted.
- api_v1/dashboard.py: writes only into its own `out` dicts -- acquitted.
- core/analytics/pnl_calendar.py:430: appends to a local bucket list -- acquitted.
- core/marketdata/fx_convert.to_account_currency: copies each row before writing -- acquitted.
- core/planning/plan_store._normalised: rewrites created_at in the loader, before
  the memo stores the record -- acquitted.
(A conviction found by this module is recorded here as "convicted: <fix>".)

Limit: a C-level helper that writes a list in place without calling its methods
(heapq) would not be caught; none is used on these paths.

v218 V218-5: the same audit on the cross-request snapshot. frozen_snapshot freezes what the
snapshot stores, and each endpoint is read in two separate requests, the second served from
the snapshot."""
import copy
import json
import pathlib
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db.codec import normalise
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.infra import read_memo, store_snapshot
from swingbot.core.planning import plan_store
from swingbot.core.tracking import performance
from tests.admin_perf import golden_book as gb
from tests.admin_perf import money_reference as mr

NAMES = list(gb.ENDPOINTS)
_WRITES = ("INSERT", "UPDATE", "DELETE")


def _refuse(self, *args, **kwargs):
    raise TypeError("v205: a read path wrote into a memoised record's nested value; copy it first")


class _FrozenList(list):
    append = extend = insert = remove = pop = clear = sort = reverse = _refuse
    __setitem__ = __delitem__ = __iadd__ = __imul__ = _refuse

    def __copy__(self):
        return list(self)

    def __deepcopy__(self, memo):
        return [copy.deepcopy(item, memo) for item in self]


class _FrozenDict(dict):
    __setitem__ = __delitem__ = __ior__ = _refuse
    update = pop = popitem = setdefault = clear = _refuse

    def __copy__(self):
        return dict(self)

    def __deepcopy__(self, memo):
        return {key: copy.deepcopy(value, memo) for key, value in self.items()}


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenDict({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return _FrozenList(_freeze(item) for item in value)
    return value


def _freeze_record(record: dict) -> dict:
    """A plain top-level dict (the caller's own copy is made from it) over frozen nested values."""
    return {key: _freeze(item) for key, item in record.items()}


@pytest.fixture
def frozen_memo(monkeypatch):
    """Everything the memo stores is deep-frozen below its top level."""
    real_records, real_mapping = read_memo.records, read_memo.mapping
    monkeypatch.setattr(read_memo, "records", lambda key, loader: real_records(
        key, lambda: [_freeze_record(record) for record in loader()]))
    monkeypatch.setattr(read_memo, "mapping", lambda key, loader: real_mapping(
        key, lambda: {name: _freeze_record(record) for name, record in loader().items()}))


@pytest.fixture
def no_writes(db_engine):
    """Statements that write or lock rows while a read scope is open."""
    seen: list[str] = []

    def guard(conn, cursor, statement, parameters, context, executemany):
        text = statement.lstrip().upper()
        if read_memo.active() and (text.startswith(_WRITES) or " FOR UPDATE" in text):
            seen.append(statement.strip().splitlines()[0][:160])

    sa.event.listen(db_engine, "before_cursor_execute", guard)
    yield seen
    sa.event.remove(db_engine, "before_cursor_execute", guard)


def _get(client, name):
    response = client.get(gb.ENDPOINTS[name])
    assert response.status_code == 200, (name, response.status_code, response.get_data()[:600])
    return response.get_json()


def _matches_golden(name, live) -> bool:
    golden = json.loads(gb.golden_path(name).read_text(encoding="utf-8"))
    pointers = list(mr.EXPECTED_MONEY[name])
    return gb.mask(gb.without_added(name, live), pointers) == gb.mask(golden, pointers)


def test_the_frozen_memo_refuses_nested_writes_only():
    record = _freeze_record({"id": "t", "legs": [{"r": 1.0}], "meta": {"a": 1}})
    record["id"] = "mine"                                # the top level is the caller's
    for write in (lambda: record["legs"].append({}), lambda: record["legs"][0].update(r=2.0),
                  lambda: record["meta"].__setitem__("a", 2), lambda: record["legs"].sort()):
        with pytest.raises(TypeError, match="v205"):
            write()
    thawed = copy.deepcopy(record)
    thawed["legs"].append({"r": 2.0})                    # a deep copy is plain and mutable
    assert type(thawed["legs"]) is list and type(thawed["meta"]) is dict
    assert isinstance(record["legs"], list) and json.loads(json.dumps(record))["legs"] == [{"r": 1.0}]


def test_a_view_reads_through_the_tests_scope(golden_seed, frozen_clock, logged_in):
    """The Flask test client runs the view in this thread and context, so the
    scopes below really cover the views (otherwise this module proves nothing)."""
    with read_memo.scope():
        _get(logged_in, "dashboard")
        assert read_memo.peek(read_memo.TRADES) is not None
        assert read_memo.peek(read_memo.PLANS) is not None


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_writes_into_no_memoised_record(name, golden_seed, frozen_clock, logged_in,
                                                 frozen_memo, no_writes):
    with read_memo.scope():
        first = _get(logged_in, name)
        second = _get(logged_in, name)                  # the same request's memo, read again
    assert gb.mask(second) == gb.mask(first)
    assert _matches_golden(name, first)
    assert no_writes == [], f"{name} wrote inside a read scope: {no_writes}"


def test_all_eight_endpoints_in_one_scope_match_their_goldens(golden_seed, frozen_clock, logged_in,
                                                              frozen_memo, no_writes):
    with read_memo.scope():
        for _ in range(2):
            mismatched = [name for name in NAMES if not _matches_golden(name, _get(logged_in, name))]
            assert mismatched == []
    assert no_writes == []


def test_memoised_records_still_equal_a_fresh_load(golden_seed, frozen_clock, logged_in, frozen_memo):
    with read_memo.scope():
        for name in NAMES:
            _get(logged_in, name)
        trades = read_memo.peek(read_memo.TRADES)
        assert sorted(trades, key=lambda t: t["id"]) == sorted(
            performance._load_trade_records(), key=lambda t: t["id"])
        assert read_memo.peek(read_memo.PLANS) == plan_store._load_plan_records()
        rows = read_memo.peek(read_memo.TRADE_ROWS)
        if rows is not None:
            assert sorted(rows, key=lambda t: t["trade_id"]) == sorted(
                normalise(trades_repo().list_all()), key=lambda t: t["trade_id"])


@pytest.fixture
def snap_states(monkeypatch):
    """store_snapshot.request_state() of each /api/v1 request, taken as request_timing tears it down."""
    states: list[str] = []
    real = store_snapshot.end_request

    def recording():
        states.append(store_snapshot.request_state())
        real()

    monkeypatch.setattr(store_snapshot, "end_request", recording)
    return states


def test_a_backing_serves_each_scopes_first_load_only(monkeypatch):
    seen = []
    monkeypatch.setattr(read_memo, "_BACKING", None)        # restored on teardown
    read_memo.set_backing(lambda key, loader: seen.append(key) or loader())
    with read_memo.scope():
        read_memo.records(read_memo.TRADES, lambda: [{"a": 1}])
        assert read_memo.records(read_memo.TRADES, lambda: []) == [{"a": 1}]
    assert seen == [read_memo.TRADES]
    read_memo.records(read_memo.TRADES, lambda: [])         # outside a scope: never the backing
    read_memo.set_backing(None)
    with read_memo.scope():
        assert read_memo.mapping(read_memo.PLANS, lambda: {"p": {"x": 1}}) == {"p": {"x": 1}}
    assert seen == [read_memo.TRADES]


def test_the_admin_app_installs_the_snapshot_backing(admin_app):
    assert read_memo._BACKING is store_snapshot.read


@pytest.mark.parametrize("name", NAMES)
def test_endpoint_writes_into_no_snapshot_record_across_two_requests(
        name, golden_seed, frozen_clock, logged_in, frozen_snapshot, no_writes, snap_states):
    first = _get(logged_in, name)
    second = _get(logged_in, name)                          # a new request, on the same snapshot
    assert gb.mask(second) == gb.mask(first)
    assert _matches_golden(name, first)
    assert no_writes == [], f"{name} wrote inside a read scope: {no_writes}"
    assert snap_states[-2:] == ["miss", "hit"], snap_states


BEFORE_MIDNIGHT = datetime(2026, 11, 3, 22, 30, tzinfo=timezone.utc)   # 23:30 Berlin, 3 Nov
AFTER_MIDNIGHT = datetime(2026, 11, 3, 23, 30, tzinfo=timezone.utc)    # 00:30 Berlin, 4 Nov


def _today_counts(client) -> tuple[int, int]:
    """(/trades rows flagged today, /dashboard?mode=today realized n)."""
    items = _get_path(client, "/api/v1/trades")["items"]
    realized = _get_path(client, "/api/v1/dashboard?mode=today")["realized"]
    return sum(bool(row["today"]) for row in items), realized["n"]


def _get_path(client, path):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code, response.get_data()[:300])
    return response.get_json()


def test_berlin_midnight_moves_the_time_fields_while_the_snapshot_stays_a_hit(
        golden_seed, frozen_clock, logged_in, snapshot_on, snap_states, monkeypatch):
    monkeypatch.setattr(gb, "FROZEN_NOW", BEFORE_MIDNIGHT)
    rows_before, realized_before = _today_counts(logged_in)
    monkeypatch.setattr(gb, "FROZEN_NOW", AFTER_MIDNIGHT)
    rows_after, realized_after = _today_counts(logged_in)
    assert realized_before > 0 and realized_after == 0      # computed per request, not stored
    assert rows_after < rows_before
    assert snap_states[-2:] == ["hit", "hit"], snap_states  # the stored records did not change


def test_the_snapshot_reads_no_clock():
    for name in ("swingbot.core.infra.store_snapshot", "swingbot.core.infra.store_generation"):
        assert name not in gb.CLOCK_MODULES
    for module in (store_snapshot, store_snapshot.store_generation):
        source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        assert "datetime" not in source and "import time" not in source, module.__name__
