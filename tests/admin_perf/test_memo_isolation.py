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
(heapq) would not be caught; none is used on these paths."""
import copy
import json

import pytest
import sqlalchemy as sa

from swingbot.core.db.codec import normalise
from swingbot.core.db.repositories.trades import trades_repo
from swingbot.core.infra import read_memo
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
    return gb.mask(live, pointers) == gb.mask(golden, pointers)


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
